"""
Notion Trigger Connector

Notion webhooks are configured manually through the Notion integration UI,
not via API. This connector provides verification and manual setup guidance.

Documentation: https://developers.notion.com/reference/webhooks
"""

import hashlib
import hmac
import logging
from typing import Any

from aci.common.db.sql_models import Trigger
from aci.server.trigger_connectors.base import (
    TriggerConnectorBase,
    WebhookRegistrationResult,
)

logger = logging.getLogger(__name__)


class NotionTriggerConnector(TriggerConnectorBase):
    """
    Notion webhook connector with manual setup process.

    Unlike other integrations, Notion requires manual webhook configuration
    through their developer portal. This connector handles verification
    and provides setup instructions.
    """

    def __init__(self, access_token: str):
        """
        Initialize Notion trigger connector.

        Args:
            access_token: OAuth2 access token (not used for webhook creation,
                         but kept for consistency with other connectors)
        """
        self.access_token = access_token

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
