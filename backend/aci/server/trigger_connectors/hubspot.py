"""
HubSpot Trigger Connector - Manages webhook subscriptions for HubSpot CRM events.

Supports events:
- contact.creation, contact.deletion, contact.propertyChange
- deal.creation, deal.deletion, deal.propertyChange
- company.creation, company.deletion, company.propertyChange

Uses HubSpot Webhooks API v3 with HMAC-SHA256 signature verification.
"""

import hashlib
import hmac
from datetime import datetime
from typing import Any

import httpx
from fastapi import Request

from aci.common.db.sql_models import Trigger
from aci.common.logging_setup import get_logger
from aci.server.trigger_connectors.base import (
    ParsedWebhookEvent,
    TriggerConnectorBase,
    WebhookRegistrationResult,
    WebhookVerificationResult,
)

logger = get_logger(__name__)


class HubSpotTriggerConnector(TriggerConnectorBase):
    """
    HubSpot webhook trigger connector.

    Implements HubSpot Webhooks API v3:
    https://developers.hubspot.com/docs/api/webhooks
    """

    BASE_URL = "https://api.hubapi.com"
    WEBHOOK_API_VERSION = "v3"

    def __init__(self):
        """
        Initialize HubSpot trigger connector.

        Credentials are retrieved from the trigger's linked_account at runtime.
        App ID should be stored in trigger.config["app_id"].
        """
        super().__init__()

    def _get_app_id(self, trigger: Trigger) -> int:
        """
        Get HubSpot app ID from trigger config.

        Args:
            trigger: Trigger with config containing app_id

        Returns:
            HubSpot app ID

        Raises:
            ValueError: If app_id not found in config
        """
        app_id = trigger.config.get("app_id")
        if not app_id:
            raise ValueError(f"HubSpot app_id not found in trigger config, trigger_id={trigger.id}")
        return int(app_id)

    # ========================================================================
    # Webhook Registration
    # ========================================================================

    async def register_webhook(self, trigger: Trigger) -> WebhookRegistrationResult:
        """
        Register a webhook subscription with HubSpot.

        Creates a subscription via POST /webhooks/v3/{appId}/subscriptions

        Args:
            trigger: Trigger configuration with webhook_url and config

        Returns:
            WebhookRegistrationResult with subscription ID
        """
        try:
            access_token = self.get_oauth_token(trigger)
            app_id = self._get_app_id(trigger)

            # Build subscription payload
            event_type = trigger.trigger_type  # e.g., "contact.creation"
            subscription_data: dict[str, Any] = {
                "eventType": event_type,
                "active": True,
            }

            # For propertyChange events, property_name is required
            if "propertyChange" in event_type:
                property_name = trigger.config.get("property_name")
                if not property_name:
                    return WebhookRegistrationResult(
                        success=False,
                        error_message=f"property_name is required for {event_type}",
                    )
                subscription_data["propertyName"] = property_name

            # Make API request
            url = f"{self.BASE_URL}/webhooks/{self.WEBHOOK_API_VERSION}/{app_id}/subscriptions"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=subscription_data,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code == 201:
                    result = response.json()
                    subscription_id = str(result.get("id"))

                    logger.info(
                        f"HubSpot webhook registered successfully, "
                        f"subscription_id={subscription_id}, "
                        f"event_type={event_type}, "
                        f"trigger_id={trigger.id}"
                    )

                    return WebhookRegistrationResult(
                        success=True,
                        external_webhook_id=subscription_id,
                        webhook_url=trigger.webhook_url,
                    )
                else:
                    error_msg = f"HubSpot API error: {response.status_code} - {response.text}"
                    logger.error(
                        f"Failed to register HubSpot webhook, "
                        f"status={response.status_code}, "
                        f"error={response.text}"
                    )
                    return WebhookRegistrationResult(
                        success=False,
                        error_message=error_msg,
                    )

        except Exception as e:
            logger.exception(f"Error registering HubSpot webhook: {e}")
            return WebhookRegistrationResult(
                success=False,
                error_message=str(e),
            )

    async def unregister_webhook(self, trigger: Trigger) -> bool:
        """
        Unregister/delete a webhook subscription from HubSpot.

        DELETE /webhooks/v3/{appId}/subscriptions/{subscriptionId}

        Args:
            trigger: Trigger with external_webhook_id (subscription ID)

        Returns:
            True if successfully deleted
        """
        if not trigger.external_webhook_id:
            logger.warning(f"No external_webhook_id found for trigger {trigger.id}")
            return False

        try:
            access_token = self.get_oauth_token(trigger)
            app_id = self._get_app_id(trigger)
            url = (
                f"{self.BASE_URL}/webhooks/{self.WEBHOOK_API_VERSION}/"
                f"{app_id}/subscriptions/{trigger.external_webhook_id}"
            )

            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0,
                )

                if response.status_code == 204:
                    logger.info(
                        f"HubSpot webhook unregistered successfully, "
                        f"subscription_id={trigger.external_webhook_id}"
                    )
                    return True
                else:
                    logger.error(
                        f"Failed to unregister HubSpot webhook, "
                        f"status={response.status_code}, "
                        f"error={response.text}"
                    )
                    return False

        except Exception as e:
            logger.exception(f"Error unregistering HubSpot webhook: {e}")
            return False

    # ========================================================================
    # Webhook Verification
    # ========================================================================

    async def verify_webhook(self, request: Request, trigger: Trigger) -> WebhookVerificationResult:
        """
        Verify HubSpot webhook signature.

        HubSpot uses HMAC-SHA256 signature in X-HubSpot-Signature header.
        The signature is computed as: sha256(client_secret + http_method + uri + body)

        More details: https://developers.hubspot.com/docs/api/webhooks/validating-requests

        Args:
            request: Incoming FastAPI request
            trigger: Trigger with verification_token (client_secret)

        Returns:
            WebhookVerificationResult indicating if signature is valid
        """
        try:
            # Get signature from header
            signature = request.headers.get("X-HubSpot-Signature")
            signature_version = request.headers.get("X-HubSpot-Signature-Version", "v1")

            if not signature:
                return WebhookVerificationResult(
                    is_valid=False,
                    error_message="Missing X-HubSpot-Signature header",
                )

            # Get request details
            request_body = await request.body()
            http_method = request.method
            request_uri = str(request.url)

            # For v1 signatures (deprecated but still supported)
            if signature_version == "v1":
                client_secret = trigger.verification_token
                source_string = (
                    client_secret + http_method + request_uri + request_body.decode("utf-8")
                )

                expected_signature = hashlib.sha256(source_string.encode("utf-8")).hexdigest()

                is_valid = hmac.compare_digest(expected_signature, signature)

                if not is_valid:
                    return WebhookVerificationResult(
                        is_valid=False,
                        error_message="Invalid signature",
                    )

                return WebhookVerificationResult(is_valid=True)

            # For v2 signatures (current)
            elif signature_version == "v2":
                # v2 uses timestamp + method + uri + body
                timestamp = request.headers.get("X-HubSpot-Request-Timestamp")
                if not timestamp:
                    return WebhookVerificationResult(
                        is_valid=False,
                        error_message="Missing X-HubSpot-Request-Timestamp header",
                    )

                client_secret = trigger.verification_token
                source_string = http_method + request_uri + request_body.decode("utf-8") + timestamp

                expected_signature = hashlib.sha256(
                    (client_secret + source_string).encode("utf-8")
                ).hexdigest()

                is_valid = hmac.compare_digest(expected_signature, signature)

                if not is_valid:
                    return WebhookVerificationResult(
                        is_valid=False,
                        error_message="Invalid signature (v2)",
                    )

                # Validate timestamp to prevent replay attacks
                if not self.validate_timestamp(timestamp, max_age_seconds=300):
                    return WebhookVerificationResult(
                        is_valid=False,
                        error_message="Timestamp too old (possible replay attack)",
                    )

                return WebhookVerificationResult(is_valid=True)

            else:
                return WebhookVerificationResult(
                    is_valid=False,
                    error_message=f"Unsupported signature version: {signature_version}",
                )

        except Exception as e:
            logger.exception(f"Error verifying HubSpot webhook signature: {e}")
            return WebhookVerificationResult(
                is_valid=False,
                error_message=str(e),
            )

    # ========================================================================
    # Event Parsing
    # ========================================================================

    def parse_event(self, payload: dict[str, Any]) -> ParsedWebhookEvent:
        """
        Parse HubSpot webhook payload into standardized format.

        HubSpot webhook payload structure:
        {
            "eventId": 123456789,
            "subscriptionId": 12345,
            "portalId": 98765,
            "occurredAt": 1616161616000,
            "eventType": "contact.creation",
            "objectId": 987654,
            "propertyName": "email",  # only for propertyChange events
            "propertyValue": "new@email.com"  # only for propertyChange events
        }

        Args:
            payload: Raw HubSpot webhook JSON

        Returns:
            ParsedWebhookEvent with standardized fields
        """
        event_type = payload.get("eventType", "unknown")
        event_id = str(payload.get("eventId")) if payload.get("eventId") else None

        # Convert occurredAt (milliseconds) to datetime
        occurred_at_ms = payload.get("occurredAt")
        timestamp = datetime.fromtimestamp(occurred_at_ms / 1000) if occurred_at_ms else None

        return ParsedWebhookEvent(
            event_type=event_type,
            event_data=payload,
            external_event_id=event_id,
            timestamp=timestamp,
        )

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def get_subscription_details(
        self, trigger: Trigger, subscription_id: str
    ) -> dict[str, Any] | None:
        """
        Get details of a specific webhook subscription.

        GET /webhooks/v3/{appId}/subscriptions/{subscriptionId}

        Args:
            trigger: Trigger with config containing app_id
            subscription_id: HubSpot subscription ID

        Returns:
            Subscription details or None if not found
        """
        try:
            access_token = self.get_oauth_token(trigger)
            app_id = self._get_app_id(trigger)
            url = (
                f"{self.BASE_URL}/webhooks/{self.WEBHOOK_API_VERSION}/"
                f"{app_id}/subscriptions/{subscription_id}"
            )

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(
                        f"Failed to get HubSpot subscription details, status={response.status_code}"
                    )
                    return None

        except Exception as e:
            logger.exception(f"Error getting HubSpot subscription details: {e}")
            return None

    async def list_subscriptions(self, trigger: Trigger) -> list[dict[str, Any]]:
        """
        List all webhook subscriptions for this app.

        GET /webhooks/v3/{appId}/subscriptions

        Args:
            trigger: Trigger with config containing app_id

        Returns:
            List of subscription objects
        """
        try:
            access_token = self.get_oauth_token(trigger)
            app_id = self._get_app_id(trigger)
            url = f"{self.BASE_URL}/webhooks/{self.WEBHOOK_API_VERSION}/{app_id}/subscriptions"

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get("results", [])
                else:
                    logger.error(
                        f"Failed to list HubSpot subscriptions, status={response.status_code}"
                    )
                    return []

        except Exception as e:
            logger.exception(f"Error listing HubSpot subscriptions: {e}")
            return []
