"""
Shopify Trigger Connector - Handles webhook subscriptions via GraphQL Admin API.

Shopify uses GraphQL webhookSubscriptionCreate mutation for webhook management.
Webhook verification is done via X-Shopify-Hmac-SHA256 header with base64-encoded HMAC.
"""

import base64
import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any

import httpx
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


class ShopifyTriggerConnector(TriggerConnectorBase):
    """
    Shopify webhook trigger connector using GraphQL Admin API.

    Webhook Subscription Flow:
    1. Use webhookSubscriptionCreate GraphQL mutation
    2. Shopify sends webhooks to specified callback URL
    3. Verify using X-Shopify-Hmac-SHA256 header

    Event Deduplication:
    - Use X-Shopify-Event-Id header for deduplication
    - Shopify may retry webhooks up to 8 times over 4 hours

    Security:
    - HMAC-SHA256 signature verification using client secret
    - Compare base64-encoded digests using timing-safe comparison
    """

    GRAPHQL_API_VERSION = "2024-07"  # Update to latest stable version

    def __init__(self, linked_account: LinkedAccount):
        """
        Initialize Shopify trigger connector.

        Args:
            linked_account: LinkedAccount with OAuth2 credentials for Shopify
        """
        super().__init__(linked_account)
        self.shop_domain = self._get_shop_domain()

    def _get_shop_domain(self) -> str:
        """
        Extract shop domain from linked account metadata.

        Returns:
            Shop domain (e.g., "myshop.myshopify.com")
        """
        # Shop domain should be stored in linked_account metadata during OAuth
        metadata = self.linked_account.metadata or {}
        shop_domain = metadata.get("shop_domain") or metadata.get("shop")

        if not shop_domain:
            raise ValueError(
                f"Shop domain not found in linked account metadata, "
                f"linked_account_id={self.linked_account.id}"
            )

        return shop_domain

    def _get_graphql_endpoint(self) -> str:
        """Build GraphQL API endpoint URL."""
        return f"https://{self.shop_domain}/admin/api/{self.GRAPHQL_API_VERSION}/graphql.json"

    async def register_webhook(self, trigger: Trigger) -> WebhookRegistrationResult:
        """
        Register a webhook subscription with Shopify using GraphQL Admin API.

        GraphQL Mutation:
            mutation webhookSubscriptionCreate($topic: WebhookSubscriptionTopic!, $webhookSubscription: WebhookSubscriptionInput!) {
              webhookSubscriptionCreate(topic: $topic, webhookSubscription: $webhookSubscription) {
                webhookSubscription {
                  id
                  topic
                  endpoint {
                    __typename
                    ... on WebhookHttpEndpoint {
                      callbackUrl
                    }
                  }
                }
                userErrors {
                  field
                  message
                }
              }
            }

        Args:
            trigger: Trigger instance with subscription details

        Returns:
            WebhookRegistrationResult with subscription ID and webhook URL
        """
        logger.info(
            f"Registering Shopify webhook, "
            f"trigger_id={trigger.id}, "
            f"trigger_type={trigger.trigger_type}, "
            f"shop={self.shop_domain}"
        )

        access_token = self.get_oauth_token()

        # Convert trigger_type to Shopify topic format (e.g., "orders/create" -> "ORDERS_CREATE")
        shopify_topic = trigger.trigger_type.replace("/", "_").upper()

        # GraphQL mutation
        mutation = """
        mutation webhookSubscriptionCreate($topic: WebhookSubscriptionTopic!, $webhookSubscription: WebhookSubscriptionInput!) {
          webhookSubscriptionCreate(topic: $topic, webhookSubscription: $webhookSubscription) {
            webhookSubscription {
              id
              topic
              endpoint {
                __typename
                ... on WebhookHttpEndpoint {
                  callbackUrl
                }
              }
            }
            userErrors {
              field
              message
            }
          }
        }
        """

        variables = {
            "topic": shopify_topic,
            "webhookSubscription": {
                "callbackUrl": trigger.webhook_url,
                "format": "JSON",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self._get_graphql_endpoint(),
                    json={"query": mutation, "variables": variables},
                    headers={
                        "Content-Type": "application/json",
                        "X-Shopify-Access-Token": access_token,
                    },
                )

                if response.status_code != 200:
                    error_msg = f"GraphQL request failed with status {response.status_code}"
                    logger.error(
                        f"{error_msg}, "
                        f"trigger_id={trigger.id}, "
                        f"response={response.text}"
                    )
                    return WebhookRegistrationResult(
                        success=False,
                        error_message=error_msg,
                    )

                result_data = response.json()

                # Check for GraphQL errors
                if "errors" in result_data:
                    error_msg = f"GraphQL errors: {result_data['errors']}"
                    logger.error(
                        f"Shopify webhook registration failed, "
                        f"trigger_id={trigger.id}, "
                        f"errors={result_data['errors']}"
                    )
                    return WebhookRegistrationResult(
                        success=False,
                        error_message=error_msg,
                    )

                # Extract subscription data
                data = result_data.get("data", {}).get("webhookSubscriptionCreate", {})
                user_errors = data.get("userErrors", [])

                if user_errors:
                    error_msg = f"User errors: {user_errors}"
                    logger.error(
                        f"Shopify webhook registration failed, "
                        f"trigger_id={trigger.id}, "
                        f"user_errors={user_errors}"
                    )
                    return WebhookRegistrationResult(
                        success=False,
                        error_message=error_msg,
                    )

                webhook_subscription = data.get("webhookSubscription", {})
                subscription_id = webhook_subscription.get("id")
                callback_url = (
                    webhook_subscription.get("endpoint", {}).get("callbackUrl")
                )

                if not subscription_id:
                    error_msg = "Subscription ID not returned from Shopify"
                    logger.error(
                        f"Shopify webhook registration failed, "
                        f"trigger_id={trigger.id}, "
                        f"response={result_data}"
                    )
                    return WebhookRegistrationResult(
                        success=False,
                        error_message=error_msg,
                    )

                logger.info(
                    f"Shopify webhook registered successfully, "
                    f"trigger_id={trigger.id}, "
                    f"subscription_id={subscription_id}, "
                    f"callback_url={callback_url}"
                )

                return WebhookRegistrationResult(
                    success=True,
                    external_webhook_id=subscription_id,
                    webhook_url=callback_url,
                )

        except Exception as e:
            error_msg = f"Exception during webhook registration: {e!s}"
            logger.error(
                f"Shopify webhook registration exception, "
                f"trigger_id={trigger.id}, "
                f"error={e!s}"
            )
            return WebhookRegistrationResult(
                success=False,
                error_message=error_msg,
            )

    async def unregister_webhook(self, trigger: Trigger) -> bool:
        """
        Unregister/delete a webhook subscription from Shopify.

        GraphQL Mutation:
            mutation webhookSubscriptionDelete($id: ID!) {
              webhookSubscriptionDelete(id: $id) {
                deletedWebhookSubscriptionId
                userErrors {
                  field
                  message
                }
              }
            }

        Args:
            trigger: Trigger instance with external_webhook_id

        Returns:
            True if successfully deleted, False otherwise
        """
        if not trigger.external_webhook_id:
            logger.warning(
                f"Cannot unregister webhook without external_webhook_id, "
                f"trigger_id={trigger.id}"
            )
            return False

        logger.info(
            f"Unregistering Shopify webhook, "
            f"trigger_id={trigger.id}, "
            f"subscription_id={trigger.external_webhook_id}"
        )

        access_token = self.get_oauth_token()

        mutation = """
        mutation webhookSubscriptionDelete($id: ID!) {
          webhookSubscriptionDelete(id: $id) {
            deletedWebhookSubscriptionId
            userErrors {
              field
              message
            }
          }
        }
        """

        variables = {"id": trigger.external_webhook_id}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self._get_graphql_endpoint(),
                    json={"query": mutation, "variables": variables},
                    headers={
                        "Content-Type": "application/json",
                        "X-Shopify-Access-Token": access_token,
                    },
                )

                if response.status_code != 200:
                    logger.error(
                        f"Shopify webhook deletion failed with status {response.status_code}, "
                        f"trigger_id={trigger.id}, "
                        f"response={response.text}"
                    )
                    return False

                result_data = response.json()

                if "errors" in result_data:
                    logger.error(
                        f"Shopify webhook deletion failed, "
                        f"trigger_id={trigger.id}, "
                        f"errors={result_data['errors']}"
                    )
                    return False

                data = result_data.get("data", {}).get("webhookSubscriptionDelete", {})
                user_errors = data.get("userErrors", [])

                if user_errors:
                    logger.error(
                        f"Shopify webhook deletion failed, "
                        f"trigger_id={trigger.id}, "
                        f"user_errors={user_errors}"
                    )
                    return False

                deleted_id = data.get("deletedWebhookSubscriptionId")

                if deleted_id:
                    logger.info(
                        f"Shopify webhook unregistered successfully, "
                        f"trigger_id={trigger.id}, "
                        f"deleted_subscription_id={deleted_id}"
                    )
                    return True

                logger.error(
                    f"Shopify webhook deletion returned no deleted ID, "
                    f"trigger_id={trigger.id}, "
                    f"response={result_data}"
                )
                return False

        except Exception as e:
            logger.error(
                f"Shopify webhook deletion exception, "
                f"trigger_id={trigger.id}, "
                f"error={e!s}"
            )
            return False

    async def verify_webhook(
        self, request: Request, trigger: Trigger
    ) -> WebhookVerificationResult:
        """
        Verify Shopify webhook signature using HMAC-SHA256.

        Shopify Verification Process:
        1. Get X-Shopify-Hmac-SHA256 header (base64-encoded HMAC)
        2. Calculate HMAC-SHA256 of raw request body using client secret
        3. Base64-encode the calculated HMAC
        4. Compare using timing-safe comparison

        Security Note:
        - Use client secret (not access token) for verification
        - Client secret is stored in app configuration metadata

        Args:
            request: FastAPI Request with headers and body
            trigger: Trigger instance (not used for Shopify, uses client secret)

        Returns:
            WebhookVerificationResult indicating validity
        """
        shopify_hmac = request.headers.get("X-Shopify-Hmac-SHA256")

        if not shopify_hmac:
            logger.warning(
                f"Missing X-Shopify-Hmac-SHA256 header, "
                f"trigger_id={trigger.id}"
            )
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Missing X-Shopify-Hmac-SHA256 header",
            )

        # Get client secret from app configuration
        # In production, this should be stored securely in app metadata
        client_secret = self._get_client_secret()

        if not client_secret:
            logger.error(
                f"Client secret not found for webhook verification, "
                f"trigger_id={trigger.id}"
            )
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Client secret not configured",
            )

        # Get raw request body
        request_body = await request.body()

        # Calculate HMAC-SHA256
        calculated_hmac = hmac.new(
            client_secret.encode("utf-8"),
            request_body,
            hashlib.sha256,
        ).digest()

        # Base64-encode the calculated HMAC
        calculated_hmac_b64 = base64.b64encode(calculated_hmac).decode("utf-8")

        # Timing-safe comparison
        try:
            is_valid = hmac.compare_digest(calculated_hmac_b64, shopify_hmac)
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
                f"Shopify webhook signature verification failed, "
                f"trigger_id={trigger.id}"
            )
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Invalid HMAC signature",
            )

        logger.info(
            f"Shopify webhook signature verified successfully, "
            f"trigger_id={trigger.id}"
        )

        return WebhookVerificationResult(is_valid=True)

    def _get_client_secret(self) -> str | None:
        """
        Get Shopify client secret from app configuration.

        The client secret should be stored in the app's metadata
        during app setup/configuration.

        Returns:
            Client secret string or None if not found
        """
        # TODO: Implement proper client secret retrieval from app configuration
        # For now, this would need to be stored in environment or app metadata
        # Example: return config.SHOPIFY_CLIENT_SECRET
        metadata = self.linked_account.metadata or {}
        return metadata.get("client_secret")

    def parse_event(self, payload: dict[str, Any]) -> ParsedWebhookEvent:
        """
        Parse Shopify webhook payload into standardized format.

        Shopify Webhook Structure:
        - Event data is in the root payload
        - No nested "event" or "data" wrapper
        - Different structure depending on topic

        Args:
            payload: Raw webhook payload from Shopify

        Returns:
            ParsedWebhookEvent with standardized fields
        """
        # Extract common fields
        # Shopify webhook payloads vary by topic but generally include:
        # - id: Resource ID
        # - created_at / updated_at: Timestamps
        # - Resource-specific fields

        event_id = payload.get("id")
        created_at = payload.get("created_at") or payload.get("updated_at")

        # Parse timestamp if available
        timestamp = None
        if created_at:
            try:
                timestamp = datetime.fromisoformat(
                    created_at.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                timestamp = datetime.now(UTC)

        return ParsedWebhookEvent(
            event_id=str(event_id) if event_id else None,
            event_type=None,  # Will be set from trigger.trigger_type
            timestamp=timestamp or datetime.now(UTC),
            data=payload,
        )
