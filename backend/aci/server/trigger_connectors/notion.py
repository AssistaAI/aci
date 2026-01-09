"""
Notion Trigger Connector

Notion webhooks are configured manually through the Notion integration UI,
not via API. This connector provides verification and manual setup guidance.

Documentation: https://developers.notion.com/reference/webhooks
"""

import hashlib
import hmac
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import Request

from aci.common.db.sql_models import Trigger
from aci.server.trigger_connectors.base import (
    ParsedWebhookEvent,
    TriggerConnectorBase,
    WebhookRegistrationResult,
    WebhookVerificationResult,
)

logger = logging.getLogger(__name__)


class NotionTriggerConnector(TriggerConnectorBase):
    """
    Notion webhook connector with manual setup process.

    Unlike other integrations, Notion requires manual webhook configuration
    through their developer portal. This connector handles verification
    and provides setup instructions.
    """

    def __init__(self):
        """Initialize Notion trigger connector without required auth parameters."""
        # We'll get auth from the trigger's linked_account directly
        pass

    async def register_webhook(self, trigger: Trigger) -> WebhookRegistrationResult:
        """
        Provide manual setup instructions for Notion webhooks.

        Since Notion doesn't support programmatic webhook creation,
        this returns instructions for manual configuration.

        Args:
            trigger: Trigger configuration

        Returns:
            WebhookRegistrationResult with manual setup instructions
        """
        try:
            # Generate verification token for this trigger
            verification_token = trigger.verification_token

            # Build detailed setup instructions (for documentation/logging purposes)
            self._build_setup_instructions(
                trigger.webhook_url, trigger.trigger_type, verification_token
            )

            logger.info(f"Generated Notion webhook setup instructions for trigger {trigger.id}")

            # Return success with external_webhook_id as "manual" to indicate
            # this was not programmatically created
            return WebhookRegistrationResult(
                success=True,
                external_webhook_id="manual_setup_required",
                error_message=None,
            )

        except Exception as e:
            logger.error(f"Failed to prepare Notion webhook setup: {e!s}")
            return WebhookRegistrationResult(
                success=False,
                external_webhook_id=None,
                error_message=f"Setup preparation failed: {e!s}",
            )

    async def unregister_webhook(self, trigger: Trigger) -> bool:
        """
        Provide instructions to manually delete Notion webhook.

        Args:
            trigger: Trigger to unregister

        Returns:
            True (manual deletion required)
        """
        logger.info(
            f"Notion webhook for trigger {trigger.id} requires manual deletion "
            "through the Notion developer portal"
        )
        # Since webhooks are manual, we consider this "successful"
        # but the user must manually delete in Notion UI
        return True

    async def test_webhook(self, trigger: Trigger) -> bool:
        """
        Test webhook connectivity.

        Since Notion handles delivery, we just verify the configuration.

        Args:
            trigger: Trigger to test

        Returns:
            True if configuration looks valid
        """
        return bool(trigger.webhook_url and trigger.verification_token)

    async def verify_webhook(self, request: Request, trigger: Trigger) -> WebhookVerificationResult:
        """
        Verify Notion webhook authenticity using HMAC-SHA256 signature.

        Args:
            request: The incoming webhook request
            trigger: Trigger that should receive this webhook

        Returns:
            WebhookVerificationResult indicating if webhook is valid
        """
        try:
            # Get signature from header
            signature = request.headers.get("X-Notion-Signature")
            if not signature:
                return WebhookVerificationResult(
                    is_valid=False, error_message="Missing X-Notion-Signature header"
                )

            # Get raw body
            body = await request.body()

            # Verify signature
            is_valid = self.verify_webhook_signature(body, signature, trigger)

            if not is_valid:
                return WebhookVerificationResult(is_valid=False, error_message="Invalid signature")

            return WebhookVerificationResult(is_valid=True)

        except Exception as e:
            logger.error(f"Notion webhook verification failed: {e!s}")
            return WebhookVerificationResult(
                is_valid=False, error_message=f"Verification error: {e!s}"
            )

    def parse_event(self, payload: dict[str, Any]) -> ParsedWebhookEvent:
        """
        Parse Notion webhook payload into standardized event format.

        Args:
            payload: Raw webhook JSON payload

        Returns:
            ParsedWebhookEvent with standardized fields
        """
        # Parse using the existing helper method
        parsed_data = self.parse_webhook_payload(payload)

        # Extract key fields for the standardized format
        event_type = payload.get("type", "unknown")
        event_id = payload.get("id")
        timestamp_str = payload.get("timestamp")

        # Parse timestamp if available
        timestamp = None
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except Exception:
                timestamp = datetime.now(UTC)
        else:
            timestamp = datetime.now(UTC)

        return ParsedWebhookEvent(
            event_type=event_type,
            event_data=parsed_data,
            external_event_id=event_id,
            timestamp=timestamp,
        )

    def verify_webhook_signature(self, payload: bytes, signature: str, trigger: Trigger) -> bool:
        """
        Verify Notion webhook signature using HMAC-SHA256.

        Notion uses the verification_token as the signing secret.
        Signature format: HMAC-SHA256 in hex format

        Args:
            payload: Raw webhook payload bytes
            signature: Signature from X-Notion-Signature header
            trigger: Trigger configuration with verification_token

        Returns:
            True if signature is valid
        """
        try:
            # Notion uses the verification_token as the signing secret
            secret = trigger.verification_token.encode("utf-8")

            # Compute HMAC-SHA256
            computed_signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()

            # Compare using timing-safe comparison
            return hmac.compare_digest(computed_signature, signature)

        except Exception as e:
            logger.error(f"Notion signature verification failed: {e!s}")
            return False

    def parse_webhook_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Parse Notion webhook payload into standardized format.

        Notion webhook payload structure:
        {
          "id": "event_id",
          "timestamp": "2025-01-10T12:00:00.000Z",
          "type": "page.content_updated",
          "authors": [{"type": "user", "user": {...}}],
          "entity": {"type": "page", "id": "page_id"},
          "workspace_id": "workspace_id",
          "workspace_name": "My Workspace"
        }

        Args:
            payload: Raw Notion webhook payload

        Returns:
            Standardized event data
        """
        return {
            "event_id": payload.get("id"),
            "event_type": payload.get("type"),
            "timestamp": payload.get("timestamp"),
            "workspace_id": payload.get("workspace_id"),
            "workspace_name": payload.get("workspace_name"),
            "entity": payload.get("entity"),
            "authors": payload.get("authors", []),
            "subscription_id": payload.get("subscription_id"),
            "raw_payload": payload,
        }

    def _build_setup_instructions(
        self, webhook_url: str, trigger_type: str, verification_token: str
    ) -> str:
        """
        Build detailed manual setup instructions.

        Args:
            webhook_url: Target webhook URL
            trigger_type: Type of trigger event
            verification_token: Token for verification

        Returns:
            Formatted setup instructions
        """
        return f"""
NOTION WEBHOOK MANUAL SETUP REQUIRED

To complete your Notion webhook setup:

1. Go to https://www.notion.so/my-integrations
2. Select your integration (or create one if needed)
3. Navigate to the "Webhooks" tab
4. Click "Add webhook subscription"
5. Enter this webhook URL:
   {webhook_url}

6. Notion will send a verification POST request to your URL
7. The request will contain a verification_token in the body
8. Save this verification token: {verification_token}
9. Go back to Notion and click "⚠️ Verify"
10. Paste the verification token and click "Verify subscription"

11. Select event types to monitor:
    - Recommended: {trigger_type}
    - You can add more event types as needed

12. Configure event filters (optional):
    - Choose specific databases or pages to monitor
    - Or monitor all content shared with your integration

13. Save and activate the webhook

IMPORTANT NOTES:
- Your webhook must be publicly accessible (HTTPS required)
- The integration must have access to pages/databases you want to monitor
- Events are delivered within 5 minutes
- Some events (like page.content_updated) are aggregated to reduce noise

For detailed documentation, visit:
https://developers.notion.com/reference/webhooks

Verification Token: {verification_token}
Webhook URL: {webhook_url}
        """.strip()

    @staticmethod
    def get_supported_events() -> list[str]:
        """
        Get list of supported Notion webhook events.

        Returns:
            List of event type strings
        """
        return [
            "page.created",
            "page.content_updated",
            "page.properties_updated",
            "page.moved",
            "page.deleted",
            "page.undeleted",
            "page.locked",
            "page.unlocked",
            "data_source.created",
            "data_source.content_updated",
            "data_source.schema_updated",
            "data_source.moved",
            "data_source.deleted",
            "data_source.undeleted",
            "comment.created",
            "comment.updated",
            "comment.deleted",
        ]
