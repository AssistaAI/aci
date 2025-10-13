"""
Base class for Trigger Connectors.

Modern, type-safe implementation using:
- ABC for interface definition
- Pydantic models for validation
- Dataclasses for data structures
- Proper error handling
"""

import hmac
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import Request

from aci.common.db.sql_models import LinkedAccount, Trigger
from aci.common.logging_setup import get_logger
from aci.common.schemas.security_scheme import (
    APIKeyScheme,
    APIKeySchemeCredentials,
    OAuth2Scheme,
    OAuth2SchemeCredentials,
)

logger = get_logger(__name__)


@dataclass
class WebhookRegistrationResult:
    """Result of webhook registration with third-party service"""

    success: bool
    external_webhook_id: str | None = None
    webhook_url: str | None = None
    expires_at: datetime | None = None
    error_message: str | None = None


@dataclass
class WebhookVerificationResult:
    """Result of webhook signature verification"""

    is_valid: bool
    error_message: str | None = None


@dataclass
class ParsedWebhookEvent:
    """Standardized webhook event after parsing"""

    event_type: str
    event_data: dict[str, Any]
    external_event_id: str | None = None
    timestamp: datetime | None = None


class TriggerConnectorBase(ABC):
    """
    Base class for all trigger connectors.

    Each third-party service implements its own subclass with specific
    webhook registration, verification, and parsing logic.

    Example:
        class HubSpotTriggerConnector(TriggerConnectorBase):
            async def register_webhook(self, trigger: Trigger) -> WebhookRegistrationResult:
                # HubSpot-specific registration logic
                ...
    """

    def __init__(
        self,
        linked_account: LinkedAccount,
        security_scheme: OAuth2Scheme | APIKeyScheme,
        security_credentials: OAuth2SchemeCredentials | APIKeySchemeCredentials,
    ):
        """
        Initialize trigger connector with authentication credentials.

        Args:
            linked_account: User's linked account for this app
            security_scheme: OAuth2 or API key security scheme
            security_credentials: Authentication credentials
        """
        self.linked_account = linked_account
        self.security_scheme = security_scheme
        self.security_credentials = security_credentials

    # ========================================================================
    # Abstract Methods (Must be implemented by subclasses)
    # ========================================================================

    @abstractmethod
    async def register_webhook(self, trigger: Trigger) -> WebhookRegistrationResult:
        """
        Register a webhook with the third-party service.

        This method should:
        1. Call the third-party API to create a webhook subscription
        2. Return the external webhook ID for tracking
        3. Handle any service-specific configuration (filters, events, etc.)

        Args:
            trigger: The trigger configuration with webhook URL and filters

        Returns:
            WebhookRegistrationResult with external_webhook_id on success

        Raises:
            Exception: If registration fails (will be caught and logged)
        """
        pass

    @abstractmethod
    async def unregister_webhook(self, trigger: Trigger) -> bool:
        """
        Unregister/delete a webhook from the third-party service.

        Args:
            trigger: The trigger with external_webhook_id to delete

        Returns:
            True if successfully unregistered, False otherwise
        """
        pass

    @abstractmethod
    async def verify_webhook(self, request: Request, trigger: Trigger) -> WebhookVerificationResult:
        """
        Verify the authenticity of an incoming webhook request.

        Common verification methods:
        - HMAC signature (HubSpot, Shopify, GitHub)
        - JWT tokens (some services)
        - IP whitelisting (less secure, avoid if possible)

        Args:
            request: The incoming webhook FastAPI request
            trigger: The trigger configuration with verification_token

        Returns:
            WebhookVerificationResult indicating if webhook is valid
        """
        pass

    @abstractmethod
    def parse_event(self, payload: dict[str, Any]) -> ParsedWebhookEvent:
        """
        Parse raw webhook payload into standardized event format.

        This method extracts:
        - Event type (e.g., "contact.updated")
        - Event data (the actual payload)
        - External event ID for deduplication
        - Timestamp (if available)

        Args:
            payload: Raw webhook JSON payload

        Returns:
            ParsedWebhookEvent with standardized fields
        """
        pass

    # ========================================================================
    # Optional Methods (Can be overridden by subclasses)
    # ========================================================================

    async def renew_webhook(self, trigger: Trigger) -> WebhookRegistrationResult:
        """
        Renew an expiring webhook subscription.

        Only needed for services with expiring webhooks (e.g., Gmail push notifications).
        Default implementation calls register_webhook again.

        Args:
            trigger: The trigger to renew

        Returns:
            WebhookRegistrationResult with new expiration
        """
        logger.info(
            f"Renewing webhook, trigger_id={trigger.id}, "
            f"external_webhook_id={trigger.external_webhook_id}"
        )
        return await self.register_webhook(trigger)

    async def test_webhook(self, trigger: Trigger) -> bool:
        """
        Test if webhook is still active and receiving events.

        Args:
            trigger: The trigger to test

        Returns:
            True if webhook is healthy, False otherwise
        """
        # Default implementation: just check if external_webhook_id exists
        return trigger.external_webhook_id is not None

    # ========================================================================
    # Helper Methods (Utility functions for subclasses)
    # ========================================================================

    def verify_hmac_signature(
        self,
        payload: bytes,
        signature: str,
        secret: str,
        algorithm: str = "sha256",
        signature_format: str = "hex",
    ) -> bool:
        """
        Verify HMAC signature for webhook payloads.

        Common pattern used by HubSpot, Shopify, GitHub, Stripe, etc.

        Args:
            payload: Raw request body bytes
            signature: Signature from webhook header
            secret: Secret key for HMAC calculation
            algorithm: Hash algorithm (sha256, sha1, etc.)
            signature_format: 'hex' or 'base64'

        Returns:
            True if signature is valid
        """
        try:
            # Compute expected signature
            hash_func = getattr(hashlib, algorithm)
            expected_mac = hmac.new(
                secret.encode("utf-8"),
                payload,
                hash_func,
            )

            if signature_format == "hex":
                expected_signature = expected_mac.hexdigest()
            elif signature_format == "base64":
                import base64
                expected_signature = base64.b64encode(expected_mac.digest()).decode("utf-8")
            else:
                raise ValueError(f"Unsupported signature format: {signature_format}")

            # Remove prefix if present (e.g., "sha256=")
            if "=" in signature:
                signature = signature.split("=", 1)[1]

            # Timing-safe comparison
            return hmac.compare_digest(expected_signature, signature)

        except Exception as e:
            logger.error(f"HMAC verification error: {e}")
            return False

    def validate_timestamp(
        self,
        timestamp: int | str,
        max_age_seconds: int = 300,
    ) -> bool:
        """
        Validate webhook timestamp to prevent replay attacks.

        Args:
            timestamp: Unix timestamp from webhook
            max_age_seconds: Maximum age of webhook (default 5 minutes)

        Returns:
            True if timestamp is recent and valid
        """
        try:
            from datetime import UTC, datetime

            timestamp_int = int(timestamp)
            webhook_time = datetime.fromtimestamp(timestamp_int, tz=UTC)
            current_time = datetime.now(UTC)
            age = (current_time - webhook_time).total_seconds()

            is_valid = 0 <= age <= max_age_seconds

            if not is_valid:
                logger.warning(
                    f"Webhook timestamp validation failed, "
                    f"age={age}s, max_age={max_age_seconds}s"
                )

            return is_valid

        except (ValueError, OSError) as e:
            logger.error(f"Timestamp validation error: {e}")
            return False

    def get_oauth_token(self) -> str:
        """
        Get OAuth2 access token from credentials.

        Returns:
            Access token string

        Raises:
            ValueError: If credentials are not OAuth2
        """
        if not isinstance(self.security_credentials, OAuth2SchemeCredentials):
            raise ValueError("Credentials are not OAuth2")

        return self.security_credentials.access_token

    def get_api_key(self) -> str:
        """
        Get API key from credentials.

        Returns:
            API key string

        Raises:
            ValueError: If credentials are not API key
        """
        if not isinstance(self.security_credentials, APIKeySchemeCredentials):
            raise ValueError("Credentials are not API key")

        return self.security_credentials.api_key
