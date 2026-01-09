"""
Google Calendar Trigger Connector

Google Calendar uses push notifications for event changes.
Webhooks are registered via the Calendar API's watch mechanism.

Documentation: https://developers.google.com/calendar/api/guides/push
"""

import logging
import uuid
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


class GoogleCalendarTriggerConnector(TriggerConnectorBase):
    """
    Google Calendar webhook connector using Push Notifications.

    Google Calendar uses a "watch" mechanism where you register a notification
    channel for a specific calendar. The channel receives notifications when
    events in that calendar change.
    """

    def __init__(self):
        """Initialize Google Calendar connector without required auth parameters."""
        # We'll get auth from the trigger's linked_account directly
        pass

    async def register_webhook(self, trigger: Trigger) -> WebhookRegistrationResult:
        """
        Register a Google Calendar push notification channel.

        Args:
            trigger: Trigger to register webhook for

        Returns:
            WebhookRegistrationResult with channel information
        """
        try:
            # Get calendar ID from trigger config (defaults to 'primary')
            calendar_id = trigger.config.get("calendar_id", "primary")

            # Generate unique channel ID
            channel_id = str(uuid.uuid4())

            # Calculate expiration (Google allows max 7 days for calendars)
            expiration = datetime.now(UTC) + timedelta(days=7)
            expiration_ms = int(expiration.timestamp() * 1000)

            # Prepare watch request
            watch_request = {
                "id": channel_id,
                "type": "web_hook",
                "address": trigger.webhook_url,
                "token": trigger.verification_token,
                "expiration": expiration_ms,
            }

            # Get access token from linked account's security credentials
            access_token = trigger.linked_account.security_credentials.get("access_token")
            if not access_token:
                return WebhookRegistrationResult(
                    success=False,
                    error_message="No access token found in linked account credentials",
                )

            # Register the channel
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/watch",
                    json=watch_request,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    resource_id = data.get("resourceId")

                    logger.info(
                        f"Google Calendar channel registered, "
                        f"trigger_id={trigger.id}, channel_id={channel_id}, "
                        f"resource_id={resource_id}"
                    )

                    return WebhookRegistrationResult(
                        success=True,
                        external_webhook_id=channel_id,
                        webhook_url=trigger.webhook_url,
                        expires_at=expiration,
                        error_message=None,
                    )
                else:
                    error_msg = (
                        f"Failed to register channel: {response.status_code} {response.text}"
                    )
                    logger.error(error_msg)
                    return WebhookRegistrationResult(
                        success=False,
                        external_webhook_id=None,
                        error_message=error_msg,
                    )

        except Exception as e:
            logger.error(f"Failed to register Google Calendar webhook: {e!s}")
            return WebhookRegistrationResult(
                success=False,
                external_webhook_id=None,
                error_message=f"Registration failed: {e!s}",
            )

    async def unregister_webhook(self, trigger: Trigger) -> bool:
        """
        Stop a Google Calendar push notification channel.

        Args:
            trigger: Trigger to unregister webhook for

        Returns:
            True if successful
        """
        try:
            if not trigger.external_webhook_id:
                logger.warning("No external_webhook_id to stop")
                return True

            # Get access token from linked account's security credentials
            access_token = trigger.linked_account.security_credentials.get("access_token")
            if not access_token:
                logger.error("No access token found in linked account credentials")
                return False

            # Stop the channel
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://www.googleapis.com/calendar/v3/channels/stop",
                    json={
                        "id": trigger.external_webhook_id,
                        "resourceId": trigger.config.get("resource_id"),
                    },
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code in [200, 204, 404]:
                    logger.info(
                        f"Google Calendar channel stopped, channel_id={trigger.external_webhook_id}"
                    )
                    return True
                else:
                    logger.error(f"Failed to stop channel: {response.status_code} {response.text}")
                    return False

        except Exception as e:
            logger.error(f"Failed to unregister Google Calendar webhook: {e!s}")
            return False

    def test_configuration(self, trigger: Trigger) -> bool:
        """
        Test if the trigger configuration is valid.

        Args:
            trigger: Trigger to test

        Returns:
            True if configuration looks valid
        """
        return bool(trigger.webhook_url and trigger.verification_token and trigger.linked_account)

    async def verify_webhook(self, request: Request, trigger: Trigger) -> WebhookVerificationResult:
        """
        Verify Google Calendar webhook authenticity.

        Google Calendar uses the X-Goog-Channel-Token header for verification.

        Args:
            request: The incoming webhook request
            trigger: Trigger that should receive this webhook

        Returns:
            WebhookVerificationResult indicating if webhook is valid
        """
        try:
            # Google Calendar uses a token-based verification
            # The token we provided should match what we receive
            channel_token = request.headers.get("X-Goog-Channel-Token")

            if not channel_token:
                return WebhookVerificationResult(
                    is_valid=False, error_message="Missing X-Goog-Channel-Token header"
                )

            expected_token = trigger.verification_token
            is_valid = channel_token == expected_token

            if not is_valid:
                return WebhookVerificationResult(
                    is_valid=False, error_message="Invalid channel token"
                )

            return WebhookVerificationResult(is_valid=True)

        except Exception as e:
            logger.error(f"Google Calendar signature verification failed: {e!s}")
            return WebhookVerificationResult(
                is_valid=False, error_message=f"Verification error: {e!s}"
            )

    async def fetch_calendar_events(
        self, trigger: Trigger, calendar_id: str = "primary"
    ) -> list[dict[str, Any]]:
        """
        Fetch recent calendar events from Google Calendar API.

        This is called when a webhook notification is received to get the actual
        event details (title, description, start time, etc.) that aren't included
        in the webhook notification itself.

        Args:
            trigger: Trigger with linked account credentials
            calendar_id: Calendar ID to fetch events from (default: 'primary')

        Returns:
            List of calendar event dictionaries with full event details
        """
        try:
            # Get access token from linked account's security credentials
            access_token = trigger.linked_account.security_credentials.get("access_token")
            if not access_token:
                logger.error("No access token found in linked account credentials")
                return []

            # Fetch recent events (last 24 hours worth of changes)
            time_min = (datetime.now(UTC) - timedelta(days=1)).isoformat()

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
                    params={
                        "timeMin": time_min,
                        "orderBy": "updated",
                        "singleEvents": True,
                        "maxResults": 10,
                    },
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    events = data.get("items", [])
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
        Parse Google Calendar webhook notification.

        Note: Google Calendar notifications don't contain the actual event data.
        You need to make a separate API call to get the event details.

        Args:
            payload: Webhook payload from Google Calendar (headers as dict)

        Returns:
            ParsedWebhookEvent with notification details
        """
        # Google Calendar sends minimal data in notifications via headers
        # The actual event data needs to be fetched via API
        resource_state = payload.get("X-Goog-Resource-State", "unknown")
        resource_id = payload.get("X-Goog-Resource-ID")
        message_number = payload.get("X-Goog-Message-Number")

        # Determine event type based on resource state
        event_type_map = {
            "sync": "calendar.sync",
            "exists": "calendar.event.updated",
            "not_exists": "calendar.event.deleted",
        }
        event_type = event_type_map.get(resource_state, "calendar.event.changed")

        return ParsedWebhookEvent(
            event_type=event_type,
            event_data={
                "resource_state": resource_state,
                "resource_id": resource_id,
                "resource_uri": payload.get("X-Goog-Resource-URI"),
                "channel_id": payload.get("X-Goog-Channel-ID"),
                "message_number": message_number,
                "notification_type": "calendar_event_change",
            },
            external_event_id=f"{resource_id}_{message_number}"
            if resource_id and message_number
            else None,
            timestamp=datetime.now(UTC),
        )
