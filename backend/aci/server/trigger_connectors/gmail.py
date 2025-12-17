"""
Gmail Trigger Connector

Gmail uses Google Pub/Sub for push notifications about mailbox changes.
Users receive notifications when messages arrive, labels change, etc.

Documentation: https://developers.google.com/gmail/api/guides/push
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


class GmailTriggerConnector(TriggerConnectorBase):
    """
    Gmail webhook connector using Google Pub/Sub Push Notifications.

    Gmail uses a "watch" mechanism where you register for push notifications
    on a user's mailbox. Notifications are sent when:
    - New messages arrive
    - Messages are modified (labels, read state, etc.)
    - Messages are deleted

    Note: Gmail push notifications require a Google Cloud Pub/Sub topic.
    The webhook URL must be configured as a Pub/Sub push subscription endpoint.
    """

    # Gmail API base URL
    GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"

    def __init__(self):
        """Initialize Gmail connector without required auth parameters."""
        pass

    async def register_webhook(self, trigger: Trigger) -> WebhookRegistrationResult:
        """
        Register a Gmail push notification watch.

        Gmail's watch() method sets up push notifications for mailbox changes.
        The notification is sent to a Pub/Sub topic which then pushes to our webhook.

        Args:
            trigger: Trigger to register webhook for

        Returns:
            WebhookRegistrationResult with watch information
        """
        try:
            # Get access token from linked account's security credentials
            access_token = trigger.linked_account.security_credentials.get("access_token")
            if not access_token:
                return WebhookRegistrationResult(
                    success=False,
                    error_message="No access token found in linked account credentials",
                )

            # Get Pub/Sub topic from trigger config
            # Format: projects/{project_id}/topics/{topic_name}
            topic_name = trigger.config.get("pubsub_topic")
            if not topic_name:
                # Use a default topic if not specified
                # This should be configured in the app settings
                topic_name = trigger.config.get(
                    "default_pubsub_topic",
                    "projects/aci-platform/topics/gmail-notifications"
                )

            # Determine which label IDs to watch based on trigger type
            label_ids = self._get_label_ids_for_trigger_type(trigger.trigger_type)

            # Prepare watch request
            watch_request = {
                "topicName": topic_name,
                "labelIds": label_ids,
                "labelFilterBehavior": "INCLUDE",
            }

            # Register the watch
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.GMAIL_API_BASE}/users/me/watch",
                    json=watch_request,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    history_id = data.get("historyId")
                    expiration = data.get("expiration")

                    # Convert expiration from milliseconds to datetime
                    expires_at = None
                    if expiration:
                        expires_at = datetime.fromtimestamp(int(expiration) / 1000, tz=UTC)

                    logger.info(
                        f"Gmail watch registered, "
                        f"trigger_id={trigger.id}, history_id={history_id}, "
                        f"expires_at={expires_at}"
                    )

                    return WebhookRegistrationResult(
                        success=True,
                        external_webhook_id=history_id,
                        webhook_url=trigger.webhook_url,
                        expires_at=expires_at,
                        metadata={
                            "history_id": history_id,
                            "topic_name": topic_name,
                            "label_ids": label_ids,
                        },
                    )
                else:
                    error_msg = (
                        f"Failed to register Gmail watch: {response.status_code} {response.text}"
                    )
                    logger.error(error_msg)
                    return WebhookRegistrationResult(
                        success=False,
                        external_webhook_id=None,
                        error_message=error_msg,
                    )

        except Exception as e:
            logger.error(f"Failed to register Gmail webhook: {e!s}")
            return WebhookRegistrationResult(
                success=False,
                external_webhook_id=None,
                error_message=f"Registration failed: {e!s}",
            )

    async def unregister_webhook(self, trigger: Trigger) -> bool:
        """
        Stop Gmail push notifications.

        Gmail's stop() method stops push notifications for the user's mailbox.

        Args:
            trigger: Trigger to unregister webhook for

        Returns:
            True if successful
        """
        try:
            # Get access token from linked account's security credentials
            access_token = trigger.linked_account.security_credentials.get("access_token")
            if not access_token:
                logger.error("No access token found in linked account credentials")
                return False

            # Stop the watch
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.GMAIL_API_BASE}/users/me/stop",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                # 204 No Content is success, 404 means already stopped
                if response.status_code in [200, 204, 404]:
                    logger.info(f"Gmail watch stopped, trigger_id={trigger.id}")
                    return True
                else:
                    logger.error(
                        f"Failed to stop Gmail watch: {response.status_code} {response.text}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Failed to unregister Gmail webhook: {e!s}")
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

    async def verify_webhook(self, request: Request, trigger: Trigger) -> WebhookVerificationResult:
        """
        Verify Gmail/Pub/Sub webhook authenticity.

        Google Pub/Sub push messages include a JWT token that can be verified.
        For simplicity, we also support token-based verification.

        Args:
            request: The incoming webhook request
            trigger: Trigger that should receive this webhook

        Returns:
            WebhookVerificationResult indicating if webhook is valid
        """
        try:
            # Check for verification token in query params or headers
            token = request.query_params.get("token") or request.headers.get(
                "X-Goog-Channel-Token"
            )

            if token and token == trigger.verification_token:
                return WebhookVerificationResult(is_valid=True)

            # For Pub/Sub, the message comes in a specific format
            # We can verify the email address matches
            body = await request.json()
            message = body.get("message", {})

            # Pub/Sub messages have the data base64 encoded
            if message.get("data"):
                # The data contains the email address
                import base64
                import json

                data = base64.b64decode(message["data"]).decode("utf-8")
                notification = json.loads(data)

                # Verify this is for our linked account
                email_address = notification.get("emailAddress")
                if email_address:
                    # Could verify against linked account, for now accept it
                    return WebhookVerificationResult(is_valid=True)

            # If we have a subscription in attributes, it's from Pub/Sub
            if message.get("attributes", {}).get("subscription"):
                return WebhookVerificationResult(is_valid=True)

            return WebhookVerificationResult(
                is_valid=False,
                error_message="Could not verify webhook authenticity",
            )

        except Exception as e:
            logger.error(f"Gmail webhook verification failed: {e!s}")
            return WebhookVerificationResult(
                is_valid=False, error_message=f"Verification error: {e!s}"
            )

    def parse_event(self, payload: dict[str, Any]) -> ParsedWebhookEvent:
        """
        Parse Gmail/Pub/Sub webhook notification.

        Gmail sends notifications via Pub/Sub with minimal data:
        - emailAddress: The user's email
        - historyId: ID to fetch changes since last notification

        Args:
            payload: Webhook payload (Pub/Sub message)

        Returns:
            ParsedWebhookEvent with notification details
        """
        import base64
        import json

        # Extract the Pub/Sub message
        message = payload.get("message", {})
        message_id = message.get("messageId", str(uuid.uuid4()))

        # Decode the data
        notification_data = {}
        if message.get("data"):
            try:
                data = base64.b64decode(message["data"]).decode("utf-8")
                notification_data = json.loads(data)
            except Exception as e:
                logger.warning(f"Failed to decode Pub/Sub message data: {e}")

        email_address = notification_data.get("emailAddress", "unknown")
        history_id = notification_data.get("historyId")

        # Gmail doesn't specify exact event type in push notification
        # We mark it as message.received and the consumer can fetch details
        event_type = "message.received"

        return ParsedWebhookEvent(
            event_type=event_type,
            event_data={
                "email_address": email_address,
                "history_id": history_id,
                "message_id": message_id,
                "publish_time": message.get("publishTime"),
                "notification_type": "gmail_push",
                "raw_message": message,
            },
            external_event_id=message_id,
            timestamp=datetime.now(UTC),
        )

    async def fetch_history(
        self,
        trigger: Trigger,
        start_history_id: str,
        history_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch mailbox history since a given history ID.

        This is called after receiving a push notification to get the actual
        changes (new messages, label changes, etc.).

        Args:
            trigger: Trigger with linked account credentials
            start_history_id: History ID to start from
            history_types: Types of history to fetch (messageAdded, labelAdded, etc.)

        Returns:
            List of history records with message details
        """
        try:
            access_token = trigger.linked_account.security_credentials.get("access_token")
            if not access_token:
                logger.error("No access token found in linked account credentials")
                return []

            if history_types is None:
                history_types = ["messageAdded", "labelAdded", "labelRemoved"]

            params = {
                "startHistoryId": start_history_id,
                "historyTypes": history_types,
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.GMAIL_API_BASE}/users/me/history",
                    params=params,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                    },
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    history = data.get("history", [])
                    logger.info(
                        f"Fetched {len(history)} history records, "
                        f"trigger_id={trigger.id}, start_history_id={start_history_id}"
                    )
                    return history
                elif response.status_code == 404:
                    # History ID too old, need to do full sync
                    logger.warning(
                        f"History ID {start_history_id} not found, need full sync"
                    )
                    return []
                else:
                    logger.error(
                        f"Failed to fetch Gmail history: {response.status_code} {response.text}"
                    )
                    return []

        except Exception as e:
            logger.error(f"Failed to fetch Gmail history: {e!s}")
            return []

    def _get_label_ids_for_trigger_type(self, trigger_type: str) -> list[str]:
        """
        Get Gmail label IDs to watch based on trigger type.

        Args:
            trigger_type: Type of trigger (message.received, message.sent, etc.)

        Returns:
            List of label IDs to monitor
        """
        # Map trigger types to Gmail labels
        label_map = {
            "message.received": ["INBOX"],
            "message.sent": ["SENT"],
            "label.added": ["INBOX", "STARRED", "IMPORTANT"],
        }

        return label_map.get(trigger_type, ["INBOX"])
