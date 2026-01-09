"""
Background Jobs for Trigger System

Periodic tasks for:
- Webhook renewal (Google Calendar, Microsoft Calendar)
- Expired event cleanup
- Failed trigger retry
"""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from aci.common.db import crud
from aci.common.enums import TriggerStatus
from aci.common.logging_setup import get_logger
from aci.server import dependencies as deps
from aci.server.trigger_connectors import get_trigger_connector

logger = get_logger(__name__)


async def renew_expiring_triggers(db_session: Session) -> dict[str, int]:
    """
    Renew triggers that are expiring within the next 24 hours.

    Google Calendar and Microsoft Calendar webhooks have expiration times
    and need to be renewed periodically.

    Args:
        db_session: Database session

    Returns:
        Dict with counts of renewed, failed, and skipped triggers
    """
    logger.info("Starting webhook renewal job")

    # Find triggers expiring within next 24 hours
    expires_before = datetime.now(UTC) + timedelta(hours=24)
    expiring_triggers = crud.triggers.get_expiring_triggers(db_session, expires_before)

    stats = {"renewed": 0, "failed": 0, "skipped": 0}

    for trigger in expiring_triggers:
        try:
            logger.info(
                f"Renewing trigger {trigger.id}, "
                f"app={trigger.app_name}, "
                f"expires_at={trigger.expires_at}"
            )

            # Get connector for this app
            try:
                connector = get_trigger_connector(trigger.app_name)
            except ValueError as e:
                logger.warning(
                    f"No connector available for {trigger.app_name}, skipping renewal: {e}"
                )
                stats["skipped"] += 1
                continue

            # Renew the webhook
            result = await connector.renew_webhook(trigger)

            if result.success:
                # Update expiration time
                if result.expires_at:
                    crud.triggers.update_trigger_expires_at(db_session, trigger, result.expires_at)
                if result.external_webhook_id:
                    crud.triggers.update_trigger_external_id(
                        db_session, trigger, result.external_webhook_id
                    )

                db_session.commit()
                stats["renewed"] += 1

                logger.info(
                    f"Successfully renewed trigger {trigger.id}, new_expires_at={result.expires_at}"
                )
            else:
                # Mark trigger as error if renewal failed
                crud.triggers.update_trigger_status(db_session, trigger, TriggerStatus.ERROR)
                db_session.commit()
                stats["failed"] += 1

                logger.error(f"Failed to renew trigger {trigger.id}: {result.error_message}")

        except Exception as e:
            logger.error(
                f"Unexpected error renewing trigger {trigger.id}: {e}",
                exc_info=True,
            )
            stats["failed"] += 1

            # Try to mark as error (but don't fail if this fails)
            try:
                crud.triggers.update_trigger_status(db_session, trigger, TriggerStatus.ERROR)
                db_session.commit()
            except Exception as commit_error:
                logger.error(f"Failed to mark trigger as error: {commit_error}")
                db_session.rollback()

    logger.info(
        f"Webhook renewal job completed: "
        f"renewed={stats['renewed']}, "
        f"failed={stats['failed']}, "
        f"skipped={stats['skipped']}"
    )

    return stats


async def cleanup_expired_events(db_session: Session) -> int:
    """
    Delete trigger events that have expired.

    Events have a 30-day retention policy by default.

    Args:
        db_session: Database session

    Returns:
        Number of events deleted
    """
    logger.info("Starting expired events cleanup job")

    try:
        deleted_count = crud.trigger_events.cleanup_expired_events(db_session)
        db_session.commit()

        logger.info(f"Expired events cleanup completed: deleted {deleted_count} events")
        return deleted_count

    except Exception as e:
        logger.error(f"Error during expired events cleanup: {e}", exc_info=True)
        db_session.rollback()
        return 0


async def mark_expired_triggers(db_session: Session) -> int:
    """
    Mark triggers as expired if they have passed their expiration time.

    Args:
        db_session: Database session

    Returns:
        Number of triggers marked as expired
    """
    logger.info("Starting expired triggers check job")

    try:
        now = datetime.now(UTC)

        # Find all active triggers that have expired
        expired_triggers = crud.triggers.get_expiring_triggers(db_session, now)

        count = 0
        for trigger in expired_triggers:
            if trigger.status == TriggerStatus.ACTIVE:
                crud.triggers.update_trigger_status(db_session, trigger, TriggerStatus.EXPIRED)
                count += 1

                logger.info(
                    f"Marked trigger {trigger.id} as expired, "
                    f"app={trigger.app_name}, "
                    f"expired_at={trigger.expires_at}"
                )

        db_session.commit()

        logger.info(f"Expired triggers check completed: marked {count} triggers as expired")
        return count

    except Exception as e:
        logger.error(f"Error during expired triggers check: {e}", exc_info=True)
        db_session.rollback()
        return 0


async def retry_failed_trigger_registrations(
    db_session: Session, max_retries: int = 3
) -> dict[str, int]:
    """
    Retry webhook registration for triggers in error state.

    Args:
        db_session: Database session
        max_retries: Maximum number of retry attempts

    Returns:
        Dict with counts of succeeded, failed, and skipped triggers
    """
    logger.info("Starting failed trigger registration retry job")

    # Find triggers in error state created within last 24 hours
    # (Don't retry very old failures)
    cutoff_time = datetime.now(UTC) - timedelta(hours=24)
    error_triggers = crud.triggers.get_triggers_by_app(
        db_session, app_name=None, status=TriggerStatus.ERROR
    )

    # Filter to recent errors only
    recent_errors = [t for t in error_triggers if t.created_at >= cutoff_time]

    stats = {"succeeded": 0, "failed": 0, "skipped": 0}

    for trigger in recent_errors:
        try:
            # Check retry count from config (we'll store it there)
            retry_count = trigger.config.get("retry_count", 0)

            if retry_count >= max_retries:
                logger.info(f"Skipping trigger {trigger.id} - max retries ({max_retries}) reached")
                stats["skipped"] += 1
                continue

            logger.info(
                f"Retrying webhook registration for trigger {trigger.id}, "
                f"attempt {retry_count + 1}/{max_retries}"
            )

            # Get connector
            try:
                connector = get_trigger_connector(trigger.app_name)
            except ValueError as e:
                logger.warning(f"No connector for {trigger.app_name}, skipping: {e}")
                stats["skipped"] += 1
                continue

            # Retry registration
            result = await connector.register_webhook(trigger)

            if result.success:
                # Update trigger status and external ID
                crud.triggers.update_trigger_status(db_session, trigger, TriggerStatus.ACTIVE)

                if result.external_webhook_id:
                    crud.triggers.update_trigger_external_id(
                        db_session, trigger, result.external_webhook_id
                    )
                if result.expires_at:
                    crud.triggers.update_trigger_expires_at(db_session, trigger, result.expires_at)

                # Reset retry count
                trigger.config["retry_count"] = 0
                crud.triggers.update_trigger_config(db_session, trigger, trigger.config)

                db_session.commit()
                stats["succeeded"] += 1

                logger.info(f"Successfully retried registration for trigger {trigger.id}")
            else:
                # Increment retry count
                trigger.config["retry_count"] = retry_count + 1
                crud.triggers.update_trigger_config(db_session, trigger, trigger.config)
                db_session.commit()
                stats["failed"] += 1

                logger.error(f"Retry failed for trigger {trigger.id}: {result.error_message}")

        except Exception as e:
            logger.error(
                f"Unexpected error retrying trigger {trigger.id}: {e}",
                exc_info=True,
            )
            stats["failed"] += 1

    logger.info(
        f"Failed trigger registration retry completed: "
        f"succeeded={stats['succeeded']}, "
        f"failed={stats['failed']}, "
        f"skipped={stats['skipped']}"
    )

    return stats


# ============================================================================
# Job Scheduler (APScheduler Integration)
# ============================================================================


async def run_all_background_jobs():
    """
    Run all background jobs once.
    Called by scheduler or can be triggered manually.
    """
    logger.info("Running all background jobs")

    # Get database session
    db_session = next(deps.yield_db_session())

    try:
        # Run jobs in parallel
        results = await asyncio.gather(
            renew_expiring_triggers(db_session),
            cleanup_expired_events(db_session),
            mark_expired_triggers(db_session),
            retry_failed_trigger_registrations(db_session),
            return_exceptions=True,
        )

        logger.info(f"All background jobs completed: {results}")

    except Exception as e:
        logger.error(f"Error running background jobs: {e}", exc_info=True)
    finally:
        db_session.close()


def setup_scheduler():
    """
    Set up APScheduler for background jobs.

    Schedules:
    - Webhook renewal: Every 6 hours
    - Event cleanup: Daily at 2 AM
    - Expired triggers check: Every hour
    - Failed registration retry: Every 30 minutes
    """
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        scheduler = AsyncIOScheduler()

        # Get database session generator
        def get_db():
            return next(deps.yield_db_session())

        # Webhook renewal - every 6 hours
        scheduler.add_job(
            lambda: renew_expiring_triggers(get_db()),
            IntervalTrigger(hours=6),
            id="renew_webhooks",
            name="Renew expiring webhooks",
            replace_existing=True,
        )

        # Event cleanup - daily at 2 AM
        scheduler.add_job(
            lambda: cleanup_expired_events(get_db()),
            CronTrigger(hour=2, minute=0),
            id="cleanup_events",
            name="Cleanup expired events",
            replace_existing=True,
        )

        # Mark expired triggers - every hour
        scheduler.add_job(
            lambda: mark_expired_triggers(get_db()),
            IntervalTrigger(hours=1),
            id="mark_expired",
            name="Mark expired triggers",
            replace_existing=True,
        )

        # Retry failed registrations - every 30 minutes
        scheduler.add_job(
            lambda: retry_failed_trigger_registrations(get_db()),
            IntervalTrigger(minutes=30),
            id="retry_failed",
            name="Retry failed registrations",
            replace_existing=True,
        )

        scheduler.start()
        logger.info("Background job scheduler started successfully")

        return scheduler

    except ImportError:
        logger.warning(
            "APScheduler not installed. Background jobs will not run automatically. "
            "Install with: pip install apscheduler"
        )
        return None
    except Exception as e:
        logger.error(f"Failed to set up scheduler: {e}", exc_info=True)
        return None
