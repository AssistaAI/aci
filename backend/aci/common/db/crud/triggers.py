from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from aci.common.db.sql_models import App, LinkedAccount, Trigger, TriggerEvent
from aci.common.logging_setup import get_logger

logger = get_logger(__name__)


def create_trigger(
    db_session: Session,
    project_id: UUID,
    app_id: UUID,
    linked_account_id: UUID,
    trigger_name: str,
    trigger_type: str,
    description: str,
    webhook_url: str,
    verification_token: str,
    config: dict,
    status: str = "active",
    external_webhook_id: str | None = None,
    expires_at: datetime | None = None,
) -> Trigger:
    """Create a new trigger subscription"""
    trigger = Trigger(
        project_id=project_id,
        app_id=app_id,
        linked_account_id=linked_account_id,
        trigger_name=trigger_name,
        trigger_type=trigger_type,
        description=description,
        webhook_url=webhook_url,
        verification_token=verification_token,
        config=config,
        status=status,
        external_webhook_id=external_webhook_id,
        expires_at=expires_at,
    )
    db_session.add(trigger)
    db_session.flush()
    logger.info(
        f"Created trigger, trigger_id={trigger.id}, trigger_name={trigger_name}, "
        f"trigger_type={trigger_type}, project_id={project_id}"
    )
    return trigger


def get_trigger(db_session: Session, trigger_id: UUID) -> Trigger | None:
    """Get a trigger by its ID"""
    statement = select(Trigger).filter_by(id=trigger_id)
    trigger: Trigger | None = db_session.execute(statement).scalar_one_or_none()
    return trigger


def get_trigger_under_project(
    db_session: Session, trigger_id: UUID, project_id: UUID
) -> Trigger | None:
    """Get a trigger by ID, ensuring it belongs to the specified project (access control)"""
    statement = select(Trigger).filter_by(id=trigger_id, project_id=project_id)
    trigger: Trigger | None = db_session.execute(statement).scalar_one_or_none()
    return trigger


def get_triggers_by_project(
    db_session: Session,
    project_id: UUID,
    app_name: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Trigger]:
    """Get all triggers for a project with optional filters"""
    statement = select(Trigger).filter_by(project_id=project_id)

    if app_name:
        statement = statement.join(App, Trigger.app_id == App.id).filter(App.name == app_name)

    if status:
        statement = statement.filter(Trigger.status == status)

    statement = statement.order_by(Trigger.created_at.desc()).limit(limit).offset(offset)

    return list(db_session.execute(statement).scalars().all())


def get_triggers_by_app(
    db_session: Session,
    app_name: str,
    status: str | None = None,
) -> list[Trigger]:
    """Get all triggers for a specific app"""
    statement = select(Trigger).join(App, Trigger.app_id == App.id).filter(App.name == app_name)

    if status:
        statement = statement.filter(Trigger.status == status)

    return list(db_session.execute(statement).scalars().all())


def get_expiring_triggers(
    db_session: Session, expires_before: datetime | None = None
) -> list[Trigger]:
    """Get triggers that are expiring soon (for renewal jobs)"""
    if expires_before is None:
        # Default: triggers expiring within next 24 hours
        expires_before = datetime.now(UTC) + timedelta(hours=24)

    statement = (
        select(Trigger)
        .filter(
            and_(
                Trigger.expires_at.isnot(None),
                Trigger.expires_at <= expires_before,
                Trigger.status == "active",
            )
        )
        .order_by(Trigger.expires_at.asc())
    )

    return list(db_session.execute(statement).scalars().all())


def update_trigger_status(
    db_session: Session, trigger: Trigger, status: str
) -> Trigger:
    """Update trigger status (active, paused, error, expired)"""
    trigger.status = status
    db_session.flush()
    logger.info(f"Updated trigger status, trigger_id={trigger.id}, new_status={status}")
    return trigger


def update_trigger_external_id(
    db_session: Session, trigger: Trigger, external_webhook_id: str
) -> Trigger:
    """Store the external webhook ID from the third-party service"""
    trigger.external_webhook_id = external_webhook_id
    db_session.flush()
    logger.info(
        f"Updated trigger external_webhook_id, trigger_id={trigger.id}, "
        f"external_webhook_id={external_webhook_id}"
    )
    return trigger


def update_trigger_expires_at(
    db_session: Session, trigger: Trigger, expires_at: datetime
) -> Trigger:
    """Update trigger expiration time (for renewals)"""
    trigger.expires_at = expires_at
    db_session.flush()
    logger.info(f"Updated trigger expires_at, trigger_id={trigger.id}, expires_at={expires_at}")
    return trigger


def update_trigger_last_triggered_at(
    db_session: Session, trigger: Trigger, last_triggered_at: datetime
) -> Trigger:
    """Update the last_triggered_at timestamp when webhook is received"""
    trigger.last_triggered_at = last_triggered_at
    db_session.flush()
    return trigger


def update_trigger_config(
    db_session: Session, trigger: Trigger, config: dict
) -> Trigger:
    """Update trigger configuration/filters"""
    trigger.config = config
    db_session.flush()
    logger.info(f"Updated trigger config, trigger_id={trigger.id}")
    return trigger


def delete_trigger(db_session: Session, trigger: Trigger) -> None:
    """Delete a trigger (should also unsubscribe from third-party service)"""
    trigger_id = trigger.id
    db_session.delete(trigger)
    db_session.flush()
    logger.info(f"Deleted trigger, trigger_id={trigger_id}")


def count_triggers_by_project(
    db_session: Session, project_id: UUID, status: str | None = None
) -> int:
    """Count total triggers for a project"""
    statement = select(func.count(Trigger.id)).filter_by(project_id=project_id)

    if status:
        statement = statement.filter(Trigger.status == status)

    count: int = db_session.execute(statement).scalar_one()
    return count
