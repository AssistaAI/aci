from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aci.common.db.sql_models import Trigger, TriggerEvent
from aci.common.enums import TriggerEventStatus
from aci.common.logging_setup import get_logger

logger = get_logger(__name__)


def create_trigger_event(
    db_session: Session,
    trigger_id: UUID,
    event_type: str,
    event_data: dict,
    external_event_id: str | None = None,
    status: TriggerEventStatus = TriggerEventStatus.PENDING,
    expires_at: datetime | None = None,
) -> TriggerEvent:
    """Create a new trigger event from an incoming webhook"""
    if expires_at is None:
        # Default: events expire after 30 days
        expires_at = datetime.now(UTC) + timedelta(days=30)

    trigger_event = TriggerEvent(
        trigger_id=trigger_id,
        event_type=event_type,
        event_data=event_data,
        external_event_id=external_event_id,
        status=status,
        expires_at=expires_at,
    )
    db_session.add(trigger_event)
    db_session.flush()
    logger.info(
        f"Created trigger_event, event_id={trigger_event.id}, trigger_id={trigger_id}, "
        f"event_type={event_type}, external_event_id={external_event_id}"
    )
    return trigger_event


def get_trigger_event(db_session: Session, event_id: UUID) -> TriggerEvent | None:
    """Get a specific trigger event by ID"""
    statement = select(TriggerEvent).filter_by(id=event_id)
    event: TriggerEvent | None = db_session.execute(statement).scalar_one_or_none()
    return event


def get_trigger_events(
    db_session: Session,
    trigger_id: UUID | None = None,
    project_id: UUID | None = None,
    status: str | None = None,
    event_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TriggerEvent]:
    """
    Get trigger events with various filters.
    Can filter by trigger_id, project_id, status, event_type, and time range.
    """
    statement = select(TriggerEvent)

    # Join with Trigger if filtering by project_id
    if project_id:
        statement = statement.join(Trigger, TriggerEvent.trigger_id == Trigger.id).filter(
            Trigger.project_id == project_id
        )

    if trigger_id:
        statement = statement.filter(TriggerEvent.trigger_id == trigger_id)

    if status:
        statement = statement.filter(TriggerEvent.status == status)

    if event_type:
        statement = statement.filter(TriggerEvent.event_type == event_type)

    if since:
        statement = statement.filter(TriggerEvent.received_at >= since)

    if until:
        statement = statement.filter(TriggerEvent.received_at <= until)

    statement = statement.order_by(TriggerEvent.received_at.desc()).limit(limit).offset(offset)

    return list(db_session.execute(statement).scalars().all())


def get_trigger_events_by_trigger(
    db_session: Session,
    trigger_id: UUID,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TriggerEvent]:
    """Get all events for a specific trigger"""
    statement = select(TriggerEvent).filter_by(trigger_id=trigger_id)

    if status:
        statement = statement.filter(TriggerEvent.status == status)

    statement = statement.order_by(TriggerEvent.received_at.desc()).limit(limit).offset(offset)

    return list(db_session.execute(statement).scalars().all())


def mark_event_processed(
    db_session: Session, event: TriggerEvent, success: bool = True, error_message: str | None = None
) -> TriggerEvent:
    """Mark an event as processed (or failed)"""
    event.status = TriggerEventStatus.DELIVERED if success else TriggerEventStatus.FAILED
    event.processed_at = datetime.now(UTC)
    if not success and error_message:
        event.error_message = error_message
    db_session.flush()
    logger.info(
        f"Marked event as processed, event_id={event.id}, status={event.status}, success={success}"
    )
    return event


def mark_event_delivered(db_session: Session, event: TriggerEvent) -> TriggerEvent:
    """Mark an event as successfully delivered to client"""
    event.status = TriggerEventStatus.DELIVERED
    event.delivered_at = datetime.now(UTC)
    db_session.flush()
    logger.info(f"Marked event as delivered, event_id={event.id}")
    return event


def update_event_status(
    db_session: Session, event: TriggerEvent, status: str, error_message: str | None = None
) -> TriggerEvent:
    """Update event status"""
    event.status = status
    if error_message:
        event.error_message = error_message
    db_session.flush()
    return event


def delete_trigger_event(db_session: Session, event: TriggerEvent) -> None:
    """Delete a trigger event (for cleanup or user request)"""
    event_id = event.id
    db_session.delete(event)
    db_session.flush()
    logger.info(f"Deleted trigger event, event_id={event_id}")


def cleanup_expired_events(db_session: Session) -> int:
    """
    Delete trigger events that have expired.
    Returns the number of events deleted.
    """
    now = datetime.now(UTC)
    statement = select(TriggerEvent).filter(TriggerEvent.expires_at <= now)

    expired_events = list(db_session.execute(statement).scalars().all())
    count = len(expired_events)

    for event in expired_events:
        db_session.delete(event)

    db_session.flush()
    logger.info(f"Cleaned up {count} expired trigger events")
    return count


def count_trigger_events(
    db_session: Session,
    trigger_id: UUID | None = None,
    project_id: UUID | None = None,
    status: str | None = None,
) -> int:
    """Count trigger events with optional filters"""
    statement = select(func.count(TriggerEvent.id))

    if project_id:
        statement = statement.join(Trigger, TriggerEvent.trigger_id == Trigger.id).filter(
            Trigger.project_id == project_id
        )

    if trigger_id:
        statement = statement.filter(TriggerEvent.trigger_id == trigger_id)

    if status:
        statement = statement.filter(TriggerEvent.status == status)

    count: int = db_session.execute(statement).scalar_one()
    return count


def check_duplicate_event(db_session: Session, trigger_id: UUID, external_event_id: str) -> bool:
    """
    Check if an event with the same external_event_id already exists for this trigger.
    Returns True if duplicate exists, False otherwise.
    Useful for preventing duplicate event processing.
    """
    statement = select(TriggerEvent).filter_by(
        trigger_id=trigger_id, external_event_id=external_event_id
    )
    existing_event = db_session.execute(statement).scalar_one_or_none()
    return existing_event is not None
