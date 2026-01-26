"""
CRUD operations for schema_fixes table.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from aci.common.db.sql_models import Function, SchemaFix
from aci.common.enums import SchemaFixErrorType, SchemaFixStatus
from aci.common.logging_setup import get_logger
from aci.common.schema_fix_detector import SchemaFixCandidate

logger = get_logger(__name__)


def create_or_increment_fix(
    db_session: Session,
    candidate: SchemaFixCandidate,
    function_id: UUID,
) -> SchemaFix | None:
    """
    Create a new schema fix or increment occurrence count if one already exists.

    Uses PostgreSQL's INSERT ... ON CONFLICT to handle the upsert atomically.

    Args:
        db_session: Database session
        candidate: The detected schema fix candidate
        function_id: The ID of the function to associate with

    Returns:
        The created or updated SchemaFix record
    """
    now = datetime.utcnow()

    # Use INSERT ... ON CONFLICT for atomic upsert
    stmt = insert(SchemaFix).values(
        function_id=function_id,
        property_path=candidate.property_path,
        property_name=candidate.property_name,
        property_schema=candidate.property_schema,
        error_type=candidate.error_type,
        status=SchemaFixStatus.PENDING,
        occurrence_count=1,
        first_seen_at=now,
        last_seen_at=now,
    )

    # On conflict, just update the occurrence count and last_seen_at
    stmt = stmt.on_conflict_do_update(
        constraint="uc_function_property_path_name",
        set_={
            "occurrence_count": SchemaFix.occurrence_count + 1,
            "last_seen_at": now,
            "updated_at": now,
        },
    )

    db_session.execute(stmt)
    db_session.flush()

    # Fetch and return the record
    return get_fix_by_function_property(
        db_session, function_id, candidate.property_path, candidate.property_name
    )


def get_fix_by_id(db_session: Session, fix_id: UUID) -> SchemaFix | None:
    """Get a schema fix by its ID."""
    statement = select(SchemaFix).filter(SchemaFix.id == fix_id)
    return db_session.execute(statement).scalar_one_or_none()


def get_fix_by_function_property(
    db_session: Session,
    function_id: UUID,
    property_path: str,
    property_name: str,
) -> SchemaFix | None:
    """Get a schema fix by function ID, property path, and property name."""
    statement = select(SchemaFix).filter(
        SchemaFix.function_id == function_id,
        SchemaFix.property_path == property_path,
        SchemaFix.property_name == property_name,
    )
    return db_session.execute(statement).scalar_one_or_none()


def get_pending_fixes(
    db_session: Session,
    limit: int = 100,
    min_occurrences: int = 1,
) -> list[SchemaFix]:
    """
    Get pending schema fixes awaiting LLM validation.

    Args:
        db_session: Database session
        limit: Maximum number of fixes to return
        min_occurrences: Minimum occurrence count to include

    Returns:
        List of pending SchemaFix records
    """
    statement = (
        select(SchemaFix)
        .filter(SchemaFix.status == SchemaFixStatus.PENDING)
        .filter(SchemaFix.occurrence_count >= min_occurrences)
        .order_by(SchemaFix.occurrence_count.desc(), SchemaFix.first_seen_at.asc())
        .limit(limit)
    )
    return list(db_session.execute(statement).scalars().all())


def get_approved_fixes_for_function(
    db_session: Session,
    function_id: UUID,
) -> list[SchemaFix]:
    """
    Get all approved (but not yet applied) schema fixes for a function.

    These are fixes that have been validated by LLM and are ready to be
    merged during the seeding process.

    Args:
        db_session: Database session
        function_id: The function ID to get fixes for

    Returns:
        List of approved SchemaFix records
    """
    statement = (
        select(SchemaFix)
        .filter(SchemaFix.function_id == function_id)
        .filter(SchemaFix.status == SchemaFixStatus.APPROVED)
        .order_by(SchemaFix.property_path)
    )
    return list(db_session.execute(statement).scalars().all())


def get_applied_fixes_for_function(
    db_session: Session,
    function_id: UUID,
) -> list[SchemaFix]:
    """
    Get all applied schema fixes for a function.

    Args:
        db_session: Database session
        function_id: The function ID to get fixes for

    Returns:
        List of applied SchemaFix records
    """
    statement = (
        select(SchemaFix)
        .filter(SchemaFix.function_id == function_id)
        .filter(SchemaFix.status == SchemaFixStatus.APPLIED)
        .order_by(SchemaFix.property_path)
    )
    return list(db_session.execute(statement).scalars().all())


def get_fixes_by_status(
    db_session: Session,
    status: SchemaFixStatus,
    limit: int = 100,
    offset: int = 0,
) -> list[SchemaFix]:
    """
    Get schema fixes by status with pagination.

    Args:
        db_session: Database session
        status: The status to filter by
        limit: Maximum number of fixes to return
        offset: Number of records to skip

    Returns:
        List of SchemaFix records
    """
    statement = (
        select(SchemaFix)
        .filter(SchemaFix.status == status)
        .order_by(SchemaFix.last_seen_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db_session.execute(statement).scalars().all())


def get_fixes_by_function_name(
    db_session: Session,
    function_name: str,
    status: SchemaFixStatus | None = None,
) -> list[SchemaFix]:
    """
    Get all schema fixes for a function by its name.

    Args:
        db_session: Database session
        function_name: The function name
        status: Optional status filter

    Returns:
        List of SchemaFix records
    """
    statement = (
        select(SchemaFix)
        .join(Function, SchemaFix.function_id == Function.id)
        .filter(Function.name == function_name)
    )

    if status is not None:
        statement = statement.filter(SchemaFix.status == status)

    statement = statement.order_by(SchemaFix.property_path)
    return list(db_session.execute(statement).scalars().all())


def update_fix_status(
    db_session: Session,
    fix_id: UUID,
    status: SchemaFixStatus,
    llm_reasoning: str | None = None,
    llm_confidence: float | None = None,
) -> SchemaFix | None:
    """
    Update the status of a schema fix.

    Args:
        db_session: Database session
        fix_id: The fix ID to update
        status: The new status
        llm_reasoning: Optional LLM reasoning
        llm_confidence: Optional LLM confidence score

    Returns:
        The updated SchemaFix record, or None if not found
    """
    values: dict = {"status": status}

    if llm_reasoning is not None:
        values["llm_reasoning"] = llm_reasoning
    if llm_confidence is not None:
        values["llm_confidence"] = llm_confidence

    if status == SchemaFixStatus.APPLIED:
        values["applied_at"] = datetime.utcnow()

    statement = update(SchemaFix).filter(SchemaFix.id == fix_id).values(**values)
    db_session.execute(statement)
    db_session.flush()

    return get_fix_by_id(db_session, fix_id)


def mark_fix_as_applied(
    db_session: Session,
    fix_id: UUID,
) -> SchemaFix | None:
    """
    Mark a schema fix as applied.

    Args:
        db_session: Database session
        fix_id: The fix ID to mark as applied

    Returns:
        The updated SchemaFix record, or None if not found
    """
    return update_fix_status(db_session, fix_id, SchemaFixStatus.APPLIED)


def delete_fix(db_session: Session, fix_id: UUID) -> bool:
    """
    Delete a schema fix.

    Args:
        db_session: Database session
        fix_id: The fix ID to delete

    Returns:
        True if deleted, False if not found
    """
    fix = get_fix_by_id(db_session, fix_id)
    if fix:
        db_session.delete(fix)
        db_session.flush()
        return True
    return False


def get_fix_statistics(db_session: Session) -> dict:
    """
    Get statistics about schema fixes.

    Returns:
        Dictionary with counts by status and error type
    """
    # Count by status
    status_counts = {}
    for status in SchemaFixStatus:
        count = db_session.execute(
            select(func.count(SchemaFix.id)).filter(SchemaFix.status == status)
        ).scalar()
        status_counts[status.value] = count

    # Count by error type
    error_type_counts = {}
    for error_type in SchemaFixErrorType:
        count = db_session.execute(
            select(func.count(SchemaFix.id)).filter(SchemaFix.error_type == error_type)
        ).scalar()
        error_type_counts[error_type.value] = count

    # Total count
    total_count = db_session.execute(select(func.count(SchemaFix.id))).scalar()

    return {
        "total": total_count,
        "by_status": status_counts,
        "by_error_type": error_type_counts,
    }
