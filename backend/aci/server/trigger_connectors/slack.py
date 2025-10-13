"""
Slack Trigger Connector - Handles Events API webhook subscriptions.

Slack Events API sends events to a configured request URL when subscribed events occur.
Webhook verification uses HMAC-SHA256 with X-Slack-Signature and X-Slack-Request-Timestamp headers.

Key Security Features:
- HMAC-SHA256 signature verification using signing secret
- Timestamp validation to prevent replay attacks (5-minute window)
- URL verification challenge during initial setup
"""

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any

from fastapi import Request

from aci.common.db.sql_models import LinkedAccount, Trigger
from aci.common.logging_setup import get_logger
from aci.server.trigger_connectors.base import (
    ParsedWebhookEvent,
    TriggerConnectorBase,
    WebhookRegistrationResult,
    WebhookVerificationResult,
)

logger = get_logger(__name__)


class SlackTriggerConnector(TriggerConnectorBase):
    """
    Slack Events API trigger connector.

    Webhook Subscription Flow:
    1. Configure Event Subscriptions in Slack App settings (manual step)
    2. Slack sends URL verification challenge to webhook URL
    3. Respond with challenge value to complete verification
    4. Slack sends events to verified URL

    Event Security:
    - X-Slack-Signature: v0={HMAC-SHA256 hex signature}
    - X-Slack-Request-Timestamp: Unix timestamp
    - Signature format: v0:{timestamp}:{body}
    - Timing-safe comparison using hmac.compare_digest

    Important Notes:
    - Slack requires manual Event Subscription configuration in App UI
    - This connector handles verification and event processing
    - Registration is informational only (no API endpoint for programmatic subscription)
    """

    # Unlike HubSpot/Shopify, Slack Events API subscriptions are managed via App UI
    # There is no programmatic API to create event subscriptions
    # Event subscriptions are tied to the app, not per-user

    def __init__(self, linked_account: LinkedAccount):
        """
        Initialize Slack trigger connector.

        Args:
            linked_account: LinkedAccount with OAuth2 credentials for Slack
        """
        super().__init__(linked_account)

    def _get_signing_secret(self) -> str | None:
        """
        Get Slack signing secret from app configuration.

        The signing secret is used for webhook verification and should be
        stored in the app's metadata during app setup/configuration.

        Returns:
            Signing secret string or None if not found
        """
        # TODO: Implement proper signing secret retrieval from app configuration
        # For now, this would need to be stored in environment or app metadata
        # Example: return config.SLACK_SIGNING_SECRET
        metadata = self.linked_account.metadata or {}
        return metadata.get("signing_secret")

    async def register_webhook(self, trigger: Trigger) -> WebhookRegistrationResult:
        """
        Register webhook information for Slack Events API.

        Important: Slack Events API subscriptions are configured manually via
        the Slack App UI at https://api.slack.com/apps/{app_id}/event-subscriptions

        This method stores the trigger but does NOT make API calls to Slack.
        The webhook URL must be added to Slack's Event Subscriptions page manually.

        Steps to complete setup:
        1. Go to Slack App settings > Event Subscriptions
        2. Enable Events
        3. Add Request URL: {trigger.webhook_url}
        4. Slack will send verification challenge to URL
        5. Subscribe to desired event types
        6. Save changes

        Args:
            trigger: Trigger instance with subscription details

        Returns:
            WebhookRegistrationResult indicating manual setup required
        """
        logger.info(
            f"Slack Events API subscription requires manual configuration, "
            f"trigger_id={trigger.id}, "
            f"trigger_type={trigger.trigger_type}, "
            f"webhook_url={trigger.webhook_url}"
        )

        # Return success with instructions for manual setup
        return WebhookRegistrationResult(
            success=True,
            external_webhook_id=None,  # No external ID since it's app-level config
            webhook_url=trigger.webhook_url,
            error_message=(
                "MANUAL_SETUP_REQUIRED: Add this webhook URL to Slack App Event Subscriptions: "
                f"https://api.slack.com/apps/{{app_id}}/event-subscriptions. "
                f"URL: {trigger.webhook_url}, Event Type: {trigger.trigger_type}"
            ),
        )

    async def unregister_webhook(self, trigger: Trigger) -> bool:
        """
        Unregister webhook from Slack Events API.

        Important: Slack Events API subscriptions must be removed manually via
        the Slack App UI. There is no programmatic API for event subscription management.

        Args:
            trigger: Trigger instance to unregister

        Returns:
            True (always, since it's a manual process)
        """
        logger.info(
            f"Slack Events API unsubscription requires manual action, "
            f"trigger_id={trigger.id}, "
            f"trigger_type={trigger.trigger_type}, "
            f"instructions=Remove event subscription from Slack App settings"
        )

        return True

    async def verify_webhook(
        self, request: Request, trigger: Trigger
    ) -> WebhookVerificationResult:
        """
        Verify Slack Events API webhook signature.

        Slack Verification Process:
        1. Extract X-Slack-Request-Timestamp and X-Slack-Signature headers
        2. Concatenate: v0:{timestamp}:{body}
        3. Compute HMAC-SHA256 using signing secret
        4. Format as v0={hex_signature}
        5. Compare with X-Slack-Signature using timing-safe comparison
        6. Validate timestamp within 5-minute window (replay attack prevention)

        Args:
            request: FastAPI Request with headers and body
            trigger: Trigger instance (not used for Slack, uses signing secret)

        Returns:
            WebhookVerificationResult indicating validity
        """
        # Get required headers
        slack_signature = request.headers.get("X-Slack-Signature")
        slack_timestamp = request.headers.get("X-Slack-Request-Timestamp")

        if not slack_signature or not slack_timestamp:
            logger.warning(
                f"Missing Slack signature headers, "
                f"trigger_id={trigger.id}, "
                f"has_signature={bool(slack_signature)}, "
                f"has_timestamp={bool(slack_timestamp)}"
            )
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Missing X-Slack-Signature or X-Slack-Request-Timestamp header",
            )

        # Validate timestamp (prevent replay attacks)
        try:
            timestamp_int = int(slack_timestamp)
            current_time = int(datetime.now(UTC).timestamp())
            time_diff = abs(current_time - timestamp_int)

            if time_diff > 60 * 5:  # 5 minutes
                logger.warning(
                    f"Slack webhook timestamp too old, "
                    f"trigger_id={trigger.id}, "
                    f"time_diff={time_diff}s"
                )
                return WebhookVerificationResult(
                    is_valid=False,
                    error_message=f"Request timestamp is too old (diff: {time_diff}s)",
                )
        except (ValueError, TypeError) as e:
            logger.error(
                f"Invalid timestamp format, "
                f"trigger_id={trigger.id}, "
                f"timestamp={slack_timestamp}, "
                f"error={e!s}"
            )
            return WebhookVerificationResult(
                is_valid=False,
                error_message=f"Invalid timestamp format: {e!s}",
            )

        # Get signing secret
        signing_secret = self._get_signing_secret()

        if not signing_secret:
            logger.error(
                f"Signing secret not found for webhook verification, "
                f"trigger_id={trigger.id}"
            )
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Signing secret not configured",
            )

        # Get raw request body
        request_body = await request.body()

        # Construct signature base string: v0:{timestamp}:{body}
        sig_basestring = f"v0:{slack_timestamp}:{request_body.decode('utf-8')}"

        # Calculate HMAC-SHA256
        calculated_signature = (
            "v0="
            + hmac.new(
                signing_secret.encode("utf-8"),
                sig_basestring.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        )

        # Timing-safe comparison
        try:
            is_valid = hmac.compare_digest(calculated_signature, slack_signature)
        except Exception as e:
            logger.error(
                f"HMAC comparison failed, "
                f"trigger_id={trigger.id}, "
                f"error={e!s}"
            )
            return WebhookVerificationResult(
                is_valid=False,
                error_message=f"HMAC comparison error: {e!s}",
            )

        if not is_valid:
            logger.warning(
                f"Slack webhook signature verification failed, "
                f"trigger_id={trigger.id}"
            )
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Invalid signature",
            )

        logger.info(
            f"Slack webhook signature verified successfully, "
            f"trigger_id={trigger.id}"
        )

        return WebhookVerificationResult(is_valid=True)

    def parse_event(self, payload: dict[str, Any]) -> ParsedWebhookEvent:
        """
        Parse Slack Events API payload into standardized format.

        Slack Events API Payload Structure:
        {
            "token": "verification_token",
            "team_id": "T123456",
            "api_app_id": "A123456",
            "event": {
                "type": "message",
                "channel": "C123456",
                "user": "U123456",
                "text": "Hello World",
                "ts": "1234567890.123456",
                "event_ts": "1234567890.123456",
                ...
            },
            "type": "event_callback",
            "event_id": "Ev123456",
            "event_time": 1234567890
        }

        Args:
            payload: Raw webhook payload from Slack

        Returns:
            ParsedWebhookEvent with standardized fields
        """
        # Extract event data
        event = payload.get("event", {})
        event_id = payload.get("event_id")
        event_type = event.get("type") or payload.get("type")
        event_time = payload.get("event_time")

        # Parse timestamp
        timestamp = None
        if event_time:
            try:
                timestamp = datetime.fromtimestamp(event_time, tz=UTC)
            except (ValueError, TypeError):
                timestamp = datetime.now(UTC)

        # Use event_ts from event object if event_time not available
        if not timestamp and "event_ts" in event:
            try:
                event_ts = float(event["event_ts"])
                timestamp = datetime.fromtimestamp(event_ts, tz=UTC)
            except (ValueError, TypeError):
                timestamp = datetime.now(UTC)

        return ParsedWebhookEvent(
            event_id=event_id,
            event_type=event_type,
            timestamp=timestamp or datetime.now(UTC),
            data=payload,
        )

    async def handle_url_verification(self, payload: dict[str, Any]) -> dict[str, str]:
        """
        Handle Slack URL verification challenge.

        When subscribing to Events API, Slack sends a url_verification request:
        {
            "token": "verification_token",
            "challenge": "random_challenge_string",
            "type": "url_verification"
        }

        Must respond with:
        {
            "challenge": "same_random_challenge_string"
        }

        Args:
            payload: Verification challenge payload from Slack

        Returns:
            Dict with challenge value to echo back
        """
        challenge = payload.get("challenge")

        if not challenge:
            logger.error(
                f"URL verification challenge missing in payload, "
                f"payload={payload}"
            )
            raise ValueError("Challenge value not found in url_verification payload")

        logger.info(
            f"Handling Slack URL verification challenge, "
            f"challenge_length={len(challenge)}"
        )

        return {"challenge": challenge}
