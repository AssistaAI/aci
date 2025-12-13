"""
Microsoft Calendar (Graph API) Trigger Connector

Microsoft Calendar uses Graph API subscriptions for change notifications.

Documentation: https://learn.microsoft.com/en-us/graph/change-notifications-delivery-webhooks
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import Request

from aci.common.db.sql_models import Trigger
from aci.server.trigger_connectors.base import (
    ParsedWebhookEvent,
    TriggerConnectorBase,
    WebhookRegistrationResult,
    WebhookVerificationResult,
)

logger = logging.getLogger(__name__)


class MicrosoftCalendarTriggerConnector(TriggerConnectorBase):
    """
    Microsoft Calendar webhook connector using Graph API subscriptions.

    Microsoft Graph allows subscribing to change notifications for calendar events.
    Subscriptions have a maximum lifetime of ~3 days and must be renewed.
    """

    def __init__(self):
        """Initialize Microsoft Calendar connector without required auth parameters."""
        # We'll get auth from the trigger's linked_account directly
        pass

    async def register_webhook(self, trigger: Trigger) -> WebhookRegistrationResult:
        """
        Register a Microsoft Graph subscription for calendar events.

        Args:
            trigger: Trigger to register webhook for

        Returns:
            WebhookRegistrationResult with subscription information
        """
        try:
            # Determine resource and change types based on trigger type
            resource = "/me/events"
            change_type = "created,updated,deleted"

            if "created" in trigger.trigger_type:
                change_type = "created"
            elif "updated" in trigger.trigger_type:
                change_type = "updated"
            elif "deleted" in trigger.trigger_type:
                change_type = "deleted"

            # Calculate expiration (max 4230 minutes = ~3 days for calendar events)
            expiration = datetime.now(UTC) + timedelta(minutes=4230)

            # Prepare subscription request
            subscription_request = {
                "changeType": change_type,
                "notificationUrl": trigger.webhook_url,
                "resource": resource,
                "expirationDateTime": expiration.isoformat(),
                "clientState": trigger.verification_token,
            }

            # Get access token from linked account's security credentials
            access_token = trigger.linked_account.security_credentials.get('access_token')
            if not access_token:
                return WebhookRegistrationResult(
                    success=False,
                    error_message="No access token found in linked account credentials"
                )

            # Create the subscription
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://graph.microsoft.com/v1.0/subscriptions",
                    json=subscription_request,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code == 201:
                    data = response.json()
                    subscription_id = data.get("id")

                    logger.info(
                        f"Microsoft Graph subscription created, "
                        f"trigger_id={trigger.id}, subscription_id={subscription_id}"
                    )

                    return WebhookRegistrationResult(
                        success=True,
                        external_webhook_id=subscription_id,
                        webhook_url=trigger.webhook_url,
                        expires_at=expiration,
                        error_message=None,
                    )
                else:
                    error_msg = f"Failed to create subscription: {response.status_code} {response.text}"
                    logger.error(error_msg)
                    return WebhookRegistrationResult(
                        success=False,
                        external_webhook_id=None,
                        error_message=error_msg,
                    )

        except Exception as e:
            logger.error(f"Failed to register Microsoft Calendar webhook: {e!s}")
            return WebhookRegistrationResult(
                success=False,
                external_webhook_id=None,
                error_message=f"Registration failed: {e!s}",
            )

    async def unregister_webhook(self, trigger: Trigger) -> bool:
        """
        Delete a Microsoft Graph subscription.

        Args:
            trigger: Trigger to unregister webhook for

        Returns:
            True if successful
        """
        try:
            if not trigger.external_webhook_id:
                logger.warning("No external_webhook_id to delete")
                return True

            # Get access token from linked account's security credentials
            access_token = trigger.linked_account.security_credentials.get('access_token')
            if not access_token:
                logger.error("No access token found in linked account credentials")
                return False

            # Delete the subscription
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"https://graph.microsoft.com/v1.0/subscriptions/{trigger.external_webhook_id}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                    },
                    timeout=30.0,
                )

                if response.status_code in [204, 404]:
                    logger.info(
                        f"Microsoft Graph subscription deleted, "
                        f"subscription_id={trigger.external_webhook_id}"
                    )
                    return True
                else:
                    logger.error(
                        f"Failed to delete subscription: {response.status_code} {response.text}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Failed to unregister Microsoft Calendar webhook: {e!s}")
            return False

    def test_configuration(self, trigger: Trigger) -> bool:
        """
        Test if the trigger configuration is valid.

        Args:
            trigger: Trigger to test

        Returns:
            True if configuration looks valid
        """
        return bool(
            trigger.webhook_url
            and trigger.verification_token
            and trigger.linked_account
        )

    async def verify_webhook(
        self, request: Request, trigger: Trigger
    ) -> WebhookVerificationResult:
        """
        Verify Microsoft Graph webhook authenticity.

        Microsoft Graph uses clientState matching for verification.

        Args:
            request: The incoming webhook request
            trigger: Trigger that should receive this webhook

        Returns:
            WebhookVerificationResult indicating if webhook is valid
        """
        try:
            # Get the request body
            body = await request.json()

            # Check if this is a validation request
            if "validationToken" in body:
                # For validation requests, we always accept them
                return WebhookVerificationResult(is_valid=True)

            # For change notifications, verify clientState
            if "value" in body:
                notifications = body["value"]
                if notifications and len(notifications) > 0:
                    notification = notifications[0]
                    client_state = notification.get("clientState")

                    expected_token = trigger.verification_token
                    is_valid = client_state == expected_token

                    if not is_valid:
                        return WebhookVerificationResult(
                            is_valid=False,
                            error_message="Invalid clientState"
                        )

                    return WebhookVerificationResult(is_valid=True)

            # Unknown notification type
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Unknown notification format"
            )

        except Exception as e:
            logger.error(f"Microsoft Graph signature verification failed: {e!s}")
            return WebhookVerificationResult(
                is_valid=False,
                error_message=f"Verification error: {e!s}"
            )

    async def fetch_calendar_events(
        self, trigger: Trigger, calendar_id: str = "me"
    ) -> list[dict[str, Any]]:
        """
        Fetch recent calendar events from Microsoft Graph API.

        Args:
            trigger: Trigger with linked account credentials
            calendar_id: Calendar ID to fetch events from (default: 'me')

        Returns:
            List of calendar event dictionaries with full event details
        """
        try:
            # Get access token from linked account's security credentials
            access_token = trigger.linked_account.security_credentials.get('access_token')
            if not access_token:
                logger.error("No access token found in linked account credentials")
                return []

            # Fetch recent events (last 24 hours worth of changes)
            time_min = (datetime.now(UTC) - timedelta(days=1)).isoformat()

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://graph.microsoft.com/v1.0/{calendar_id}/calendar/events",
                    params={
                        "$filter": f"lastModifiedDateTime ge {time_min}",
                        "$orderby": "lastModifiedDateTime desc",
                        "$top": 10,
                    },
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    events = data.get("value", [])
                    logger.info(
                        f"Fetched {len(events)} recent calendar events, "
                        f"trigger_id={trigger.id}, calendar_id={calendar_id}"
                    )
                    return events
                else:
                    logger.error(
                        f"Failed to fetch calendar events: {response.status_code} {response.text}"
                    )
                    return []

        except Exception as e:
            logger.error(f"Failed to fetch calendar events: {e!s}")
            return []

    def parse_event(self, payload: dict[str, Any]) -> ParsedWebhookEvent:
        """
        Parse Microsoft Graph webhook notification.

        Args:
            payload: Webhook payload from Microsoft Graph

        Returns:
            ParsedWebhookEvent with notification details
        """
        # Check if this is a validation request
        if "validationToken" in payload:
            return ParsedWebhookEvent(
                event_type="calendar.validation",
                event_data={
                    "notification_type": "validation",
                    "validationToken": payload["validationToken"],
                },
                external_event_id=None,
                timestamp=datetime.now(UTC),
            )

        # Parse change notifications
        if "value" in payload:
            notifications = payload["value"]
            if notifications and len(notifications) > 0:
                notification = notifications[0]

                change_type = notification.get("changeType", "unknown")
                subscription_id = notification.get("subscriptionId")
                resource = notification.get("resource")
                resource_data = notification.get("resourceData", {})

                # Determine event type based on change type
                event_type_map = {
                    "created": "calendar.event.created",
                    "updated": "calendar.event.updated",
                    "deleted": "calendar.event.deleted",
                }
                event_type = event_type_map.get(change_type, "calendar.event.changed")

                # Extract event ID from resource if available
                event_id = resource_data.get("id")

                return ParsedWebhookEvent(
                    event_type=event_type,
                    event_data={
                        "notification_type": "change",
                        "subscriptionId": subscription_id,
                        "changeType": change_type,
                        "resource": resource,
                        "resourceData": resource_data,
                        "clientState": notification.get("clientState"),
                        "subscriptionExpirationDateTime": notification.get(
                            "subscriptionExpirationDateTime"
                        ),
                    },
                    external_event_id=f"{subscription_id}_{event_id}" if subscription_id and event_id else None,
                    timestamp=datetime.now(UTC),
                )

        # Unknown notification type
        return ParsedWebhookEvent(
            event_type="calendar.unknown",
            event_data={
                "notification_type": "unknown",
                "raw_payload": payload,
            },
            external_event_id=None,
            timestamp=datetime.now(UTC),
        )
