"""
Triggers API Routes - FastAPI router for managing webhook triggers.

Uses modern FastAPI patterns:
- Dependency injection for database sessions and request context
- Type-safe response models with Pydantic V2
- Proper HTTP status codes
- Comprehensive error handling
"""

import secrets
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from aci.common.db import crud
from aci.common.db.sql_models import Trigger, TriggerEvent
from aci.common.exceptions import (
    AppConfigurationNotFound,
    AppNotFound,
    LinkedAccountNotFound,
)
from aci.common.logging_setup import get_logger
from aci.common.schemas.trigger import (
    TriggerCreate,
    TriggerEventPublic,
    TriggerEventsListQuery,
    TriggerHealthCheck,
    TriggerPublic,
    TriggersListQuery,
    TriggerStats,
    TriggerUpdate,
    TriggerWithToken,
)
from aci.server import config
from aci.server import dependencies as deps

router = APIRouter()
logger = get_logger(__name__)


# ============================================================================
# Helper Functions (DRY)
# ============================================================================


def generate_webhook_url(trigger_id: UUID, app_name: str) -> str:
    """Generate the webhook callback URL for a trigger"""
    # Use the configured webhook base URL (should be publicly accessible)
    # Set SERVER_WEBHOOK_BASE_URL environment variable to your ngrok URL for local dev
    base_url = config.WEBHOOK_BASE_URL
    return f"{base_url}/v1/webhooks/{app_name}/{trigger_id}"


def generate_verification_token() -> str:
    """Generate a secure verification token for webhook validation"""
    return secrets.token_urlsafe(32)


def get_trigger_or_404(db_session: Session, trigger_id: UUID, project_id: UUID) -> Trigger:
    """Get trigger by ID or raise 404"""
    trigger = crud.triggers.get_trigger_under_project(db_session, trigger_id, project_id)
    if not trigger:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trigger {trigger_id} not found or not accessible",
        )
    return trigger


# ============================================================================
# Trigger Management Endpoints
# ============================================================================


@router.post("", response_model=TriggerWithToken, status_code=status.HTTP_201_CREATED)
async def create_trigger(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    body: TriggerCreate,
) -> Trigger:
    """
    Create a new trigger subscription.

    This will:
    1. Validate the app and linked account exist
    2. Generate webhook URL and verification token
    3. Store trigger in database
    4. Attempt to register webhook with third-party service (TODO: Phase 2)

    Returns the created trigger with verification token.
    """
    db_session = context.db_session
    project_id = context.project.id

    # Validate app exists
    app = crud.apps.get_app(db_session, body.app_name, public_only=False, active_only=True)
    if not app:
        raise AppNotFound(f"App {body.app_name} not found")

    # Validate linked account exists and is enabled
    linked_account = crud.linked_accounts.get_linked_account(
        db_session, project_id, body.app_name, body.linked_account_owner_id
    )
    if not linked_account:
        raise LinkedAccountNotFound(
            f"Linked account for {body.app_name} with owner {body.linked_account_owner_id} not found"
        )

    if not linked_account.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Linked account is disabled",
        )

    # Check app configuration exists
    app_config = crud.app_configurations.get_app_configuration(
        db_session, project_id, body.app_name
    )
    if not app_config:
        raise AppConfigurationNotFound(f"App {body.app_name} not configured for this project")

    # Generate webhook URL and verification token
    temp_trigger_id = UUID("00000000-0000-0000-0000-000000000000")  # Placeholder
    webhook_url = generate_webhook_url(temp_trigger_id, body.app_name)
    verification_token = generate_verification_token()

    # Create trigger
    trigger = crud.triggers.create_trigger(
        db_session,
        project_id=project_id,
        app_id=app.id,
        linked_account_id=linked_account.id,
        trigger_name=body.trigger_name,
        trigger_type=body.trigger_type,
        description=body.description,
        webhook_url=webhook_url,  # Will be updated after creation with actual trigger ID
        verification_token=verification_token,
        config=body.config,
        status=body.status,
        expires_at=body.expires_at,
    )

    # Update webhook URL with actual trigger ID
    trigger.webhook_url = generate_webhook_url(trigger.id, body.app_name)
    db_session.commit()

    # Register webhook with third-party service using TriggerConnector
    try:
        from aci.server.trigger_connectors import get_trigger_connector

        connector = get_trigger_connector(body.app_name)
        result = await connector.register_webhook(trigger)

        if result.success:
            # Update trigger with external webhook details
            if result.external_webhook_id:
                crud.triggers.update_trigger_external_id(
                    db_session, trigger, result.external_webhook_id
                )
            if result.expires_at:
                trigger.expires_at = result.expires_at
            db_session.commit()

            logger.info(
                f"Webhook registered successfully for trigger {trigger.id}, "
                f"external_id={result.external_webhook_id}"
            )
        else:
            logger.error(
                f"Failed to register webhook for trigger {trigger.id}: {result.error_message}"
            )
            crud.triggers.update_trigger_status(db_session, trigger, "error")
            db_session.commit()

    except ValueError as e:
        # App doesn't have trigger connector support yet
        logger.warning(f"Trigger connector not available for {body.app_name}: {e}")
        # Keep trigger in active state - it was created successfully, just without auto-registration

    except Exception as e:
        logger.error(f"Unexpected error registering webhook: {e}", exc_info=True)
        crud.triggers.update_trigger_status(db_session, trigger, "error")
        db_session.commit()

    logger.info(
        f"Created trigger {trigger.id} for {body.app_name}, type={body.trigger_type}, "
        f"project_id={project_id}"
    )

    return trigger


@router.get("", response_model=list[TriggerPublic])
async def list_triggers(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    query: Annotated[TriggersListQuery, Query()],
) -> list[Trigger]:
    """
    List all triggers for the current project.

    Supports filtering by app name and status.
    """
    triggers = crud.triggers.get_triggers_by_project(
        context.db_session,
        project_id=context.project.id,
        app_name=query.app_name,
        status=query.status,
        limit=query.limit,
        offset=query.offset,
    )

    logger.info(
        f"Listed {len(triggers)} triggers, project_id={context.project.id}, "
        f"filters: app_name={query.app_name}, status={query.status}"
    )

    return triggers


@router.get("/{trigger_id}", response_model=TriggerPublic)
async def get_trigger(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    trigger_id: UUID,
) -> Trigger:
    """Get details of a specific trigger"""
    trigger = get_trigger_or_404(context.db_session, trigger_id, context.project.id)
    return trigger


@router.patch("/{trigger_id}", response_model=TriggerPublic)
async def update_trigger(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    trigger_id: UUID,
    body: TriggerUpdate,
) -> Trigger:
    """
    Update a trigger's configuration or status.

    Can update:
    - status: Pause/resume trigger
    - config: Update filters and settings
    - description: Update description
    """
    db_session = context.db_session
    trigger = get_trigger_or_404(db_session, trigger_id, context.project.id)

    # Apply updates
    if body.status is not None:
        crud.triggers.update_trigger_status(db_session, trigger, body.status)

    if body.config is not None:
        crud.triggers.update_trigger_config(db_session, trigger, body.config)

    if body.description is not None:
        trigger.description = body.description

    db_session.commit()

    logger.info(f"Updated trigger {trigger_id}, updates: {body.model_dump(exclude_none=True)}")

    return trigger


@router.delete("/{trigger_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trigger(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    trigger_id: UUID,
) -> None:
    """
    Delete a trigger and unsubscribe from webhook.

    This will:
    1. Attempt to unregister webhook with third-party service
    2. Delete trigger from database (cascade deletes events)
    """
    db_session = context.db_session
    trigger = get_trigger_or_404(db_session, trigger_id, context.project.id)

    # Unregister webhook with third-party service
    if trigger.external_webhook_id:
        try:
            from aci.server.trigger_connectors import get_trigger_connector

            connector = get_trigger_connector(trigger.app_name)
            unregister_success = await connector.unregister_webhook(trigger)

            if unregister_success:
                logger.info(
                    f"Successfully unregistered webhook, "
                    f"trigger_id={trigger_id}, external_webhook_id={trigger.external_webhook_id}"
                )
            else:
                logger.warning(
                    f"Failed to unregister webhook (continuing with deletion), "
                    f"trigger_id={trigger_id}, external_webhook_id={trigger.external_webhook_id}"
                )
        except ValueError as e:
            # App doesn't have trigger connector support
            logger.warning(
                f"Cannot unregister webhook - no connector available for {trigger.app_name}: {e}"
            )
        except Exception as e:
            # Log error but continue with deletion to avoid orphaned database records
            logger.error(
                f"Error unregistering webhook (continuing with deletion), "
                f"trigger_id={trigger_id}, error={e}",
                exc_info=True,
            )

    crud.triggers.delete_trigger(db_session, trigger)
    db_session.commit()

    logger.info(f"Deleted trigger {trigger_id}, project_id={context.project.id}")


# ============================================================================
# Trigger Events Endpoints
# ============================================================================


@router.get("/{trigger_id}/events", response_model=list[TriggerEventPublic])
async def list_trigger_events(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    trigger_id: UUID,
    query: Annotated[TriggerEventsListQuery, Query()],
) -> list[TriggerEvent]:
    """
    List events for a specific trigger.

    Supports filtering by status, event type, and time range.
    """
    db_session = context.db_session

    # Verify trigger belongs to project
    get_trigger_or_404(db_session, trigger_id, context.project.id)

    # Get events
    events = crud.trigger_events.get_trigger_events_by_trigger(
        db_session,
        trigger_id=trigger_id,
        status=query.status,
        limit=query.limit,
        offset=query.offset,
    )

    logger.info(f"Listed {len(events)} events for trigger {trigger_id}")

    return events


@router.get("/events/all", response_model=list[TriggerEventPublic])
async def list_all_trigger_events(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    query: Annotated[TriggerEventsListQuery, Query()],
) -> list[TriggerEvent]:
    """
    List all trigger events for the current project.

    Useful for viewing events across all triggers.
    """
    events = crud.trigger_events.get_trigger_events(
        context.db_session,
        project_id=context.project.id,
        trigger_id=query.trigger_id,
        status=query.status,
        event_type=query.event_type,
        since=query.since,
        until=query.until,
        limit=query.limit,
        offset=query.offset,
    )

    logger.info(f"Listed {len(events)} events across all triggers, project_id={context.project.id}")

    return events


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trigger_event(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    event_id: UUID,
) -> None:
    """
    Mark an event as processed and optionally delete it.

    This is useful for acknowledging that an event has been handled by the client.
    """
    db_session = context.db_session
    event = crud.trigger_events.get_trigger_event(db_session, event_id)

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event {event_id} not found",
        )

    # Verify event belongs to project's trigger
    trigger = get_trigger_or_404(db_session, event.trigger_id, context.project.id)

    # Mark as delivered and delete
    crud.trigger_events.mark_event_delivered(db_session, event)
    crud.trigger_events.delete_trigger_event(db_session, event)
    db_session.commit()

    logger.info(f"Deleted event {event_id}, trigger_id={trigger.id}")


# ============================================================================
# Health & Stats Endpoints
# ============================================================================


@router.get("/{trigger_id}/health", response_model=TriggerHealthCheck)
async def get_trigger_health(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    trigger_id: UUID,
) -> TriggerHealthCheck:
    """Check health status of a trigger"""
    db_session = context.db_session
    trigger = get_trigger_or_404(db_session, trigger_id, context.project.id)

    from aci.common.enums import TriggerStatus

    is_healthy = trigger.status == TriggerStatus.ACTIVE

    # Check if expired
    if trigger.expires_at and trigger.expires_at < datetime.now(UTC):
        is_healthy = False

    return TriggerHealthCheck(
        trigger_id=trigger.id,
        is_healthy=is_healthy,
        status=trigger.status,
        last_triggered_at=trigger.last_triggered_at,
        expires_at=trigger.expires_at,
        error_message=None if is_healthy else "Trigger is not active or has expired",
    )


@router.get("/available-types/{app_name}")
async def get_available_trigger_types(
    app_name: str,
) -> list[dict]:
    """
    Get available trigger types for a specific app.

    Returns trigger definitions from the app's triggers.json file.
    This provides a single source of truth for available triggers.
    """
    import json
    import os

    # Construct path to triggers.json
    triggers_file = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "apps",
        app_name.lower(),
        "triggers.json",
    )

    if not os.path.exists(triggers_file):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No triggers available for app {app_name}",
        )

    try:
        with open(triggers_file) as f:
            data = json.load(f)
            triggers = data.get("triggers", [])

        logger.info(f"Fetched {len(triggers)} trigger types for app {app_name}")
        return triggers

    except json.JSONDecodeError as e:
        logger.error(f"Invalid triggers.json for {app_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to parse trigger configuration",
        ) from e
    except Exception as e:
        logger.error(f"Error reading triggers for {app_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load trigger types",
        ) from e


@router.get("/{trigger_id}/stats", response_model=TriggerStats)
async def get_trigger_stats(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    trigger_id: UUID,
) -> TriggerStats:
    """Get statistics for a trigger"""
    db_session = context.db_session
    trigger = get_trigger_or_404(db_session, trigger_id, context.project.id)

    from aci.common.enums import TriggerEventStatus

    # Count events by status
    total_events = crud.trigger_events.count_trigger_events(db_session, trigger_id=trigger.id)
    pending_events = crud.trigger_events.count_trigger_events(
        db_session, trigger_id=trigger.id, status=TriggerEventStatus.PENDING
    )
    delivered_events = crud.trigger_events.count_trigger_events(
        db_session, trigger_id=trigger.id, status=TriggerEventStatus.DELIVERED
    )
    failed_events = crud.trigger_events.count_trigger_events(
        db_session, trigger_id=trigger.id, status=TriggerEventStatus.FAILED
    )

    # Get last event time
    recent_events = crud.trigger_events.get_trigger_events_by_trigger(
        db_session, trigger_id, limit=1
    )
    last_event_at = recent_events[0].received_at if recent_events else None

    return TriggerStats(
        trigger_id=trigger.id,
        total_events=total_events,
        pending_events=pending_events,
        delivered_events=delivered_events,
        failed_events=failed_events,
        last_event_at=last_event_at,
    )


# ============================================================================
# Bulk Operations
# ============================================================================


@router.patch("/bulk/status", status_code=status.HTTP_200_OK)
async def bulk_update_trigger_status(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    body: Annotated[dict, ...],
) -> dict:
    """
    Update status for multiple triggers at once.

    Request body:
    {
        "trigger_ids": ["uuid1", "uuid2", ...],
        "status": "paused" | "active"
    }

    Returns:
    {
        "updated": 5,
        "failed": 1,
        "errors": [{"trigger_id": "...", "error": "..."}]
    }
    """
    from aci.common.schemas.trigger import TriggerBulkStatusUpdate

    # Validate request
    try:
        request = TriggerBulkStatusUpdate(**body)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request: {e}",
        ) from e

    db_session = context.db_session
    project_id = context.project.id

    updated_count = 0
    failed_count = 0
    errors = []

    for trigger_id in request.trigger_ids:
        try:
            trigger = get_trigger_or_404(db_session, trigger_id, project_id)
            crud.triggers.update_trigger_status(db_session, trigger, request.status)
            updated_count += 1
        except Exception as e:
            failed_count += 1
            errors.append({"trigger_id": str(trigger_id), "error": str(e)})
            logger.error(f"Failed to update trigger {trigger_id}: {e}")

    db_session.commit()

    logger.info(f"Bulk status update completed: updated={updated_count}, failed={failed_count}")

    return {
        "updated": updated_count,
        "failed": failed_count,
        "errors": errors,
    }


@router.delete("/bulk", status_code=status.HTTP_200_OK)
async def bulk_delete_triggers(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    trigger_ids: Annotated[list[UUID], ...],
) -> dict:
    """
    Delete multiple triggers at once.

    Query params:
        trigger_ids: List of trigger UUIDs to delete

    Returns:
    {
        "deleted": 5,
        "failed": 1,
        "errors": [{"trigger_id": "...", "error": "..."}]
    }
    """
    db_session = context.db_session
    project_id = context.project.id

    deleted_count = 0
    failed_count = 0
    errors = []

    for trigger_id in trigger_ids:
        try:
            trigger = get_trigger_or_404(db_session, trigger_id, project_id)

            # Attempt to unregister webhook
            if trigger.external_webhook_id:
                try:
                    from aci.server.trigger_connectors import get_trigger_connector

                    connector = get_trigger_connector(trigger.app_name)
                    await connector.unregister_webhook(trigger)
                except Exception as e:
                    logger.warning(
                        f"Failed to unregister webhook for {trigger_id} (continuing): {e}"
                    )

            crud.triggers.delete_trigger(db_session, trigger)
            deleted_count += 1

        except Exception as e:
            failed_count += 1
            errors.append({"trigger_id": str(trigger_id), "error": str(e)})
            logger.error(f"Failed to delete trigger {trigger_id}: {e}")

    db_session.commit()

    logger.info(f"Bulk delete completed: deleted={deleted_count}, failed={failed_count}")

    return {
        "deleted": deleted_count,
        "failed": failed_count,
        "errors": errors,
    }
