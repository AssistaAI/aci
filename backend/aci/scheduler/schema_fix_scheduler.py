"""
Schema Fix Scheduler

Runs periodic tasks for processing schema fixes automatically.
Uses APScheduler for reliable cron-like scheduling within Python.
"""

import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from openai import OpenAI

from aci.common import utils
from aci.common.db import crud
from aci.common.enums import SchemaFixStatus
from aci.common.logging_setup import get_logger, setup_logging
from aci.common.schema_fix_applier import SchemaFixApplier
from aci.common.schema_fix_validator import SchemaFixValidator
from aci.scheduler import config

setup_logging()
logger = get_logger(__name__)


def process_pending_fixes() -> None:
    """
    Process pending schema fixes with LLM validation.

    High-confidence fixes (>= 0.9) are auto-applied.
    """
    logger.info("Starting scheduled schema fix processing...")

    openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
    validator = SchemaFixValidator(openai_client)

    with utils.create_db_session(config.DB_FULL_URL) as db_session:
        pending_fixes = crud.schema_fixes.get_pending_fixes(
            db_session,
            limit=config.SCHEMA_FIX_BATCH_SIZE,
            min_occurrences=config.SCHEMA_FIX_MIN_OCCURRENCES,
        )

        if not pending_fixes:
            logger.info("No pending fixes to process")
            return

        logger.info(f"Processing {len(pending_fixes)} pending fixes...")

        approved_count = 0
        rejected_count = 0
        review_count = 0
        applied_count = 0

        for fix in pending_fixes:
            function = crud.functions.get_function_by_id(db_session, fix.function_id)
            if not function:
                logger.warning(f"Function not found for fix {fix.id}")
                continue

            logger.info(f"Validating: {function.name} -> {fix.property_name}")

            result = validator.validate_fix(function, fix)

            # Update fix status with LLM results
            crud.schema_fixes.update_fix_status(
                db_session,
                fix.id,
                result.decision,
                llm_reasoning=result.reasoning,
                llm_confidence=result.confidence,
            )

            if result.decision == SchemaFixStatus.APPROVED:
                approved_count += 1
                # Auto-apply high-confidence fixes
                if config.SCHEMA_FIX_AUTO_APPLY:
                    # Refresh fix to get updated status
                    refreshed_fix = crud.schema_fixes.get_fix_by_id(db_session, fix.id)
                    if refreshed_fix and SchemaFixApplier.apply_fix_to_function(
                        db_session, function, refreshed_fix
                    ):
                        applied_count += 1
                        logger.info(f"Auto-applied fix: {function.name}.{fix.property_name}")
            elif result.decision == SchemaFixStatus.REJECTED:
                rejected_count += 1
            else:
                review_count += 1

        db_session.commit()

        logger.info(
            f"Schema fix processing complete: "
            f"approved={approved_count}, rejected={rejected_count}, "
            f"review={review_count}, applied={applied_count}"
        )


def run_scheduler() -> None:
    """Run the scheduler with configured intervals."""
    scheduler = BlockingScheduler()

    # Schedule schema fix processing
    # Default: every hour at minute 0
    scheduler.add_job(
        process_pending_fixes,
        CronTrigger.from_crontab(config.SCHEMA_FIX_CRON_SCHEDULE),
        id="process_pending_fixes",
        name="Process pending schema fixes",
        replace_existing=True,
    )

    # Handle graceful shutdown
    def shutdown(signum: int, frame: object) -> None:
        logger.info("Received shutdown signal, stopping scheduler...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info(f"Starting schema fix scheduler (cron: {config.SCHEMA_FIX_CRON_SCHEDULE})")
    logger.info(f"Auto-apply enabled: {config.SCHEMA_FIX_AUTO_APPLY}")
    logger.info(f"Batch size: {config.SCHEMA_FIX_BATCH_SIZE}")
    logger.info(f"Min occurrences: {config.SCHEMA_FIX_MIN_OCCURRENCES}")

    # Run once immediately on startup
    logger.info("Running initial schema fix processing...")
    try:
        process_pending_fixes()
    except Exception as e:
        logger.exception(f"Error in initial processing: {e}")

    logger.info(f"Next scheduled run: {scheduler.get_jobs()[0].next_run_time}")
    scheduler.start()


if __name__ == "__main__":
    run_scheduler()
