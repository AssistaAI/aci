import secrets
import string
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from svix import Webhook, WebhookVerificationError

from aci.common.db import crud
from aci.common.enums import OrganizationRole
from aci.common.logging_setup import get_logger
from aci.common.schemas.trigger import WebhookReceivedResponse, WebhookVerificationChallenge
from aci.server import config
from aci.server import dependencies as deps
from aci.server.acl import get_propelauth

# Create router instance
router = APIRouter()
logger = get_logger(__name__)

auth = get_propelauth()


@router.post("/auth/user-created", status_code=status.HTTP_204_NO_CONTENT)
async def handle_user_created_webhook(
    request: Request,
    db_session: Annotated[Session, Depends(deps.yield_db_session)],
    response: Response,
) -> None:
    headers = request.headers
    payload = await request.body()

    # Verify the message following: https://docs.svix.com/receiving/verifying-payloads/how#python-fastapi
    try:
        wh = Webhook(config.SVIX_SIGNING_SECRET)
        msg = wh.verify(payload, dict(headers))
    except WebhookVerificationError as e:
        response.status_code = status.HTTP_400_BAD_REQUEST
        logger.error(
            f"Webhook verification error, "
            f"error={e!s} "
            f"error_type={type(e).__name__} "
            f"svix_id={headers.get('svix-id')} "
            f"svix_timestamp={headers.get('svix-timestamp')} "
            f"svix_signature={headers.get('svix-signature')}"
        )
        return

    if msg["event_type"] != "user.created":
        response.status_code = status.HTTP_400_BAD_REQUEST
        logger.error(f"Webhook event is not user.created, event={msg['event']}")
        return

    user = auth.fetch_user_metadata_by_user_id(msg["user_id"], include_orgs=True)
    if user is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        logger.error(f"User not found, user_id={msg['user_id']}")
        return

    logger.info(f"New user has signed up, user_id={user.user_id}")

    # No-Op if user already has a Personal Organization
    # This shouldn't happen because each user can only be created once
    if user.org_id_to_org_info:
        for org_id, org_info in user.org_id_to_org_info.items():
            # TODO: propel auth type hinting bug: org_info is not a dataclass but a dict here
            org_metadata = org_info["org_metadata"]
            if not isinstance(org_metadata, dict):
                logger.error(
                    f"Org metadata is not a dict, org_id={org_id}, org_metadata={org_metadata}"
                )
                response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
                return

            if org_metadata["personal"] is True:
                response.status_code = status.HTTP_409_CONFLICT
                logger.error(
                    f"User already has a personal organization, "
                    f"user_id={user.user_id} "
                    f"org_id={org_id}"
                )
                return

    org = auth.create_org(
        name=f"Personal {_generate_secure_random_alphanumeric_string()}",
        max_users=1,
    )
    logger.info(
        f"Created a default personal org for new user, user_id={user.user_id}, org_id={org.org_id}"
    )

    auth.update_org_metadata(org_id=org.org_id, metadata={"personal": True})
    logger.info(
        f"Updated org metadata (personal=True) for default personal org, "
        f"user_id={user.user_id}, "
        f"org_id={org.org_id}"
    )

    auth.add_user_to_org(user_id=user.user_id, org_id=org.org_id, role=OrganizationRole.OWNER)
    logger.info(
        f"Added new user to default personal org, user_id={user.user_id}, org_id={org.org_id}"
    )

    org_id_uuid = _convert_org_id_to_uuid(org.org_id)
    project = crud.projects.create_project(db_session, org_id_uuid, "Default Project")

    # Create a default Agent for the project
    agent = crud.projects.create_agent(
        db_session,
        project.id,
        name="Default Agent",
        description="Default Agent",
        allowed_apps=[],
        custom_instructions={},
    )
    db_session.commit()

    logger.info(
        f"Created default project and agent for new user, "
        f"user_id={user.user_id}, "
        f"org_id={org.org_id} "
        f"project_id={project.id} "
        f"agent_id={agent.id}"
    )


def _generate_secure_random_alphanumeric_string(length: int = 6) -> str:
    charset = string.ascii_letters + string.digits

    secure_random_base64 = "".join(secrets.choice(charset) for _ in range(length))
    return secure_random_base64


def _convert_org_id_to_uuid(org_id: str | UUID) -> UUID:
    if isinstance(org_id, str):
        return UUID(org_id)
    elif isinstance(org_id, UUID):
        return org_id
    else:
        raise TypeError(f"org_id must be a str or UUID, got {type(org_id).__name__}")


# ============================================================================
# Third-Party Webhook Receiver Endpoints
# ============================================================================


@router.get("/{app_name}/{trigger_id}", response_model=WebhookVerificationChallenge)
async def webhook_challenge_verification(
    app_name: str,
    trigger_id: UUID,
    request: Request,
    db_session: Annotated[Session, Depends(deps.yield_db_session)],
) -> dict:
    """
    Handle challenge-response verification for webhook registration.

    Used by services like Slack, Stripe, etc. that send a challenge parameter
    during webhook subscription setup.
    """
    # Verify trigger exists and is active
    trigger = crud.triggers.get_trigger(db_session, trigger_id)
    if not trigger or trigger.app_name != app_name.upper():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trigger not found for app {app_name}",
        )

    if trigger.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trigger is not active, status={trigger.status}",
        )

    # Get challenge parameter from query string
    challenge = request.query_params.get("challenge")
    if not challenge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing challenge parameter",
        )

    logger.info(
        f"Webhook challenge verification successful, app={app_name}, trigger_id={trigger_id}"
    )

    # Echo back the challenge
    return {"challenge": challenge}


@router.post("/{app_name}/{trigger_id}", response_model=WebhookReceivedResponse)
async def receive_webhook(
    app_name: str,
    trigger_id: UUID,
    request: Request,
    db_session: Annotated[Session, Depends(deps.yield_db_session)],
) -> WebhookReceivedResponse:
    """
    Receive and store webhooks from third-party services.

    This endpoint:
    1. Validates the trigger exists and is active
    2. Verifies the webhook signature (TODO: Phase 2 - per-app verification)
    3. Stores the event in the database
    4. Returns success response

    Webhook signature verification will be handled by TriggerConnectors in Phase 2.
    """
    # Get trigger and validate
    trigger = crud.triggers.get_trigger(db_session, trigger_id)
    if not trigger or trigger.app_name != app_name.upper():
        logger.error(
            f"Webhook received for non-existent trigger, app={app_name}, trigger_id={trigger_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trigger not found for app {app_name}",
        )

    if trigger.status != "active":
        logger.warning(
            f"Webhook received for inactive trigger, "
            f"app={app_name}, trigger_id={trigger_id}, status={trigger.status}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trigger is not active, status={trigger.status}",
        )

    # Import connector
    from aci.server.trigger_connectors import get_trigger_connector

    # Parse webhook payload based on app type
    # Google Calendar and Microsoft Calendar send notifications via headers with empty body
    if app_name.upper() in ["GOOGLE_CALENDAR", "MICROSOFT_CALENDAR"]:
        # For calendar services, extract data from headers
        payload_dict = dict(request.headers)
        logger.info(
            f"Calendar webhook received with headers, "
            f"app={app_name}, trigger_id={trigger_id}, headers={list(payload_dict.keys())}"
        )
    else:
        # For other services, parse JSON body
        try:
            payload_dict = await request.json()
        except Exception as e:
            logger.error(f"Failed to parse webhook payload, error={e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload",
            ) from e

    # Verify webhook signature using TriggerConnector
    try:
        connector = get_trigger_connector(app_name.upper())
        verification_result = await connector.verify_webhook(request, trigger)
        if not verification_result.is_valid:
            logger.error(
                f"Webhook signature verification failed, "
                f"trigger_id={trigger_id}, error={verification_result.error_message}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid webhook signature: {verification_result.error_message}",
            )
    except Exception as e:
        logger.error(f"Webhook verification error, trigger_id={trigger_id}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook verification failed",
        ) from e

    # Parse event using TriggerConnector
    try:
        parsed_event = connector.parse_event(payload_dict)
        event_type = parsed_event.event_type
        external_event_id = parsed_event.external_event_id
        event_data = parsed_event.event_data
        event_timestamp = parsed_event.timestamp
    except Exception as e:
        logger.error(f"Failed to parse webhook event, trigger_id={trigger_id}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to parse webhook event",
        ) from e

    # For Google Calendar and Microsoft Calendar, fetch actual event details
    # The webhook notification only contains metadata, not the actual calendar events
    if app_name.upper() in ["GOOGLE_CALENDAR", "MICROSOFT_CALENDAR"]:
        # Skip sync notifications (initial setup) - these don't contain event data
        if event_data.get("resource_state") != "sync":
            try:
                calendar_id = trigger.config.get("calendar_id", "primary")
                calendar_events = await connector.fetch_calendar_events(trigger, calendar_id)

                # Add the fetched calendar events to event_data
                event_data["calendar_events"] = calendar_events
                event_data["event_count"] = len(calendar_events)

                logger.info(
                    f"Fetched {len(calendar_events)} calendar events for webhook, "
                    f"trigger_id={trigger_id}, calendar_id={calendar_id}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to fetch calendar events for webhook (continuing with metadata only), "
                    f"trigger_id={trigger_id}, error={e}"
                )
                # Continue processing even if event fetch fails - at least we have metadata

    # Check for duplicate events
    if external_event_id:
        is_duplicate = crud.trigger_events.check_duplicate_event(
            db_session, trigger_id, external_event_id
        )
        if is_duplicate:
            logger.info(
                f"Duplicate webhook event received, skipping, "
                f"trigger_id={trigger_id}, external_event_id={external_event_id}"
            )
            # Return success to avoid retries from provider
            existing_event = (
                db_session.query(crud.trigger_events.TriggerEvent)
                .filter_by(trigger_id=trigger_id, external_event_id=external_event_id)
                .first()
            )
            return WebhookReceivedResponse(
                event_id=existing_event.id,
                trigger_id=trigger.id,
                event_type=event_type,
                status=existing_event.status,
                received_at=existing_event.received_at,
            )

    # Store event with race condition protection
    try:
        event = crud.trigger_events.create_trigger_event(
            db_session,
            trigger_id=trigger.id,
            event_type=event_type,
            event_data=event_data,
            external_event_id=external_event_id,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(days=30),  # 30-day retention
        )

        # Update trigger's last_triggered_at
        crud.triggers.update_trigger_last_triggered_at(db_session, trigger, datetime.now(UTC))

        db_session.commit()

        logger.info(
            f"Webhook received and stored, "
            f"app={app_name}, trigger_id={trigger_id}, event_id={event.id}, "
            f"event_type={event_type}, external_event_id={external_event_id}"
        )

        return WebhookReceivedResponse(
            event_id=event.id,
            trigger_id=trigger.id,
            event_type=event_type,
            status=event.status,
            received_at=event.received_at,
        )
    except IntegrityError:
        # Handle race condition: two concurrent webhooks with same external_event_id
        db_session.rollback()
        if external_event_id:
            existing_event = (
                db_session.query(crud.trigger_events.TriggerEvent)
                .filter_by(trigger_id=trigger_id, external_event_id=external_event_id)
                .first()
            )
            if existing_event:
                logger.info(
                    f"Race condition on webhook event creation, returning existing event, "
                    f"trigger_id={trigger_id}, external_event_id={external_event_id}"
                )
                return WebhookReceivedResponse(
                    event_id=existing_event.id,
                    trigger_id=trigger.id,
                    event_type=event_type,
                    status=existing_event.status,
                    received_at=existing_event.received_at,
                )
        # If we land here without an existing event, re-raise
        raise
