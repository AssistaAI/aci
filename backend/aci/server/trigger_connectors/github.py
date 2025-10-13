"""
GitHub Trigger Connector - Handles repository webhook subscriptions via REST API.

GitHub webhooks are created per-repository and send events to a configured payload URL.
Webhook verification uses HMAC-SHA256 with X-Hub-Signature-256 header.
"""

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


class GitHubTriggerConnector(TriggerConnectorBase):
    """
    GitHub Webhooks trigger connector using REST API.

    Webhook Subscription Flow:
    1. POST /repos/{owner}/{repo}/hooks with webhook configuration
    2. GitHub sends a "ping" event to verify the webhook URL
    3. GitHub sends events based on subscribed event types

    Event Security:
    - X-Hub-Signature-256: sha256={HMAC-SHA256 hex signature}
    - Signature calculated using webhook secret
    - Timing-safe comparison using hmac.compare_digest

    Important Notes:
    - Requires repository owner/admin permissions
    - Webhook secret should be high-entropy random string
    - Each repository has its own webhooks (not workspace-level)
    """

    BASE_URL = "https://api.github.com"

    def __init__(self, linked_account: LinkedAccount):
        """
        Initialize GitHub trigger connector.

        Args:
            linked_account: LinkedAccount with OAuth2 credentials for GitHub
        """
        super().__init__(linked_account)

    def _get_webhook_secret(self) -> str:
        """
        Get webhook secret for signature verification.

        The webhook secret should be generated during webhook creation
        and stored in trigger metadata.

        Returns:
            Webhook secret string
        """
        # Webhook secret will be stored per-trigger in trigger.config
        # For verification, it's passed from trigger metadata
        # This is a placeholder - actual implementation in verify_webhook
        return ""

    def _get_repo_info(self, trigger: Trigger) -> tuple[str, str]:
        """
        Extract repository owner and name from trigger config.

        Args:
            trigger: Trigger instance with config containing owner and repo

        Returns:
            Tuple of (owner, repo)

        Raises:
            ValueError: If owner or repo not found in config
        """
        config = trigger.config or {}
        owner = config.get("owner")
        repo = config.get("repo")

        if not owner or not repo:
            raise ValueError(
                f"Repository owner and name required in trigger config, "
                f"trigger_id={trigger.id}, "
                f"config={config}"
            )

        return owner, repo

    async def register_webhook(self, trigger: Trigger) -> WebhookRegistrationResult:
        """
        Register a webhook with GitHub repository using REST API.

        POST /repos/{owner}/{repo}/hooks
        {
            "name": "web",
            "active": true,
            "events": ["push", "pull_request"],
            "config": {
                "url": "https://example.com/webhook",
                "content_type": "json",
                "secret": "random_high_entropy_secret"
            }
        }

        Args:
            trigger: Trigger instance with subscription details

        Returns:
            WebhookRegistrationResult with webhook ID and URL
        """
        try:
            owner, repo = self._get_repo_info(trigger)
        except ValueError as e:
            return WebhookRegistrationResult(
                success=False,
                error_message=str(e),
            )

        logger.info(
            f"Registering GitHub webhook, "
            f"trigger_id={trigger.id}, "
            f"trigger_type={trigger.trigger_type}, "
            f"owner={owner}, "
            f"repo={repo}"
        )

        access_token = self.get_oauth_token()

        # Generate webhook secret for signature verification
        webhook_secret = self.generate_random_secret()

        # Prepare webhook configuration
        webhook_config = {
            "name": "web",
            "active": True,
            "events": [trigger.trigger_type],  # e.g., "push", "pull_request"
            "config": {
                "url": trigger.webhook_url,
                "content_type": "json",
                "secret": webhook_secret,
                "insecure_ssl": "0",  # Require SSL verification
            },
        }

        url = f"{self.BASE_URL}/repos/{owner}/{repo}/hooks"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json=webhook_config,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )

                if response.status_code not in (200, 201):
                    error_msg = f"GitHub API request failed with status {response.status_code}"
                    logger.error(
                        f"{error_msg}, "
                        f"trigger_id={trigger.id}, "
                        f"response={response.text}"
                    )
                    return WebhookRegistrationResult(
                        success=False,
                        error_message=f"{error_msg}: {response.text}",
                    )

                result_data = response.json()

                webhook_id = str(result_data.get("id"))
                webhook_url = result_data.get("url")  # API URL for webhook management

                if not webhook_id:
                    error_msg = "Webhook ID not returned from GitHub"
                    logger.error(
                        f"GitHub webhook registration failed, "
                        f"trigger_id={trigger.id}, "
                        f"response={result_data}"
                    )
                    return WebhookRegistrationResult(
                        success=False,
                        error_message=error_msg,
                    )

                logger.info(
                    f"GitHub webhook registered successfully, "
                    f"trigger_id={trigger.id}, "
                    f"webhook_id={webhook_id}, "
                    f"webhook_url={webhook_url}"
                )

                # Store webhook secret in trigger config for later verification
                # This should be encrypted in production
                return WebhookRegistrationResult(
                    success=True,
                    external_webhook_id=webhook_id,
                    webhook_url=webhook_url,
                    metadata={"webhook_secret": webhook_secret},  # Store securely!
                )

        except Exception as e:
            error_msg = f"Exception during webhook registration: {e!s}"
            logger.error(
                f"GitHub webhook registration exception, "
                f"trigger_id={trigger.id}, "
                f"error={e!s}"
            )
            return WebhookRegistrationResult(
                success=False,
                error_message=error_msg,
            )

    async def unregister_webhook(self, trigger: Trigger) -> bool:
        """
        Unregister/delete a webhook from GitHub repository.

        DELETE /repos/{owner}/{repo}/hooks/{hook_id}

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

        try:
            owner, repo = self._get_repo_info(trigger)
        except ValueError as e:
            logger.error(
                f"Failed to extract repo info for webhook deletion, "
                f"trigger_id={trigger.id}, "
                f"error={e!s}"
            )
            return False

        logger.info(
            f"Unregistering GitHub webhook, "
            f"trigger_id={trigger.id}, "
            f"webhook_id={trigger.external_webhook_id}, "
            f"owner={owner}, "
            f"repo={repo}"
        )

        access_token = self.get_oauth_token()

        url = f"{self.BASE_URL}/repos/{owner}/{repo}/hooks/{trigger.external_webhook_id}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )

                if response.status_code == 204:
                    logger.info(
                        f"GitHub webhook unregistered successfully, "
                        f"trigger_id={trigger.id}, "
                        f"webhook_id={trigger.external_webhook_id}"
                    )
                    return True

                logger.error(
                    f"GitHub webhook deletion failed with status {response.status_code}, "
                    f"trigger_id={trigger.id}, "
                    f"response={response.text}"
                )
                return False

        except Exception as e:
            logger.error(
                f"GitHub webhook deletion exception, "
                f"trigger_id={trigger.id}, "
                f"error={e!s}"
            )
            return False

    async def verify_webhook(
        self, request: Request, trigger: Trigger
    ) -> WebhookVerificationResult:
        """
        Verify GitHub webhook signature using HMAC-SHA256.

        GitHub Verification Process:
        1. Get X-Hub-Signature-256 header (format: sha256={hex_signature})
        2. Calculate HMAC-SHA256 of raw request body using webhook secret
        3. Format as sha256={calculated_hex}
        4. Compare with X-Hub-Signature-256 using timing-safe comparison

        Args:
            request: FastAPI Request with headers and body
            trigger: Trigger instance with webhook_secret in config

        Returns:
            WebhookVerificationResult indicating validity
        """
        github_signature = request.headers.get("X-Hub-Signature-256")

        if not github_signature:
            logger.warning(
                f"Missing X-Hub-Signature-256 header, "
                f"trigger_id={trigger.id}"
            )
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Missing X-Hub-Signature-256 header",
            )

        # Extract webhook secret from trigger config
        config = trigger.config or {}
        webhook_secret = config.get("webhook_secret")

        if not webhook_secret:
            logger.error(
                f"Webhook secret not found in trigger config, "
                f"trigger_id={trigger.id}"
            )
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Webhook secret not configured",
            )

        # Get raw request body
        request_body = await request.body()

        # Calculate HMAC-SHA256
        calculated_signature = (
            "sha256="
            + hmac.new(
                webhook_secret.encode("utf-8"),
                request_body,
                hashlib.sha256,
            ).hexdigest()
        )

        # Timing-safe comparison
        try:
            is_valid = hmac.compare_digest(calculated_signature, github_signature)
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
                f"GitHub webhook signature verification failed, "
                f"trigger_id={trigger.id}"
            )
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Invalid signature",
            )

        logger.info(
            f"GitHub webhook signature verified successfully, "
            f"trigger_id={trigger.id}"
        )

        return WebhookVerificationResult(is_valid=True)

    def parse_event(self, payload: dict[str, Any]) -> ParsedWebhookEvent:
        """
        Parse GitHub webhook payload into standardized format.

        GitHub Webhook Payload Structure:
        - Event type in X-GitHub-Event header (not in payload)
        - Delivery ID in X-GitHub-Delivery header
        - Payload structure varies by event type

        Common fields:
        {
            "action": "opened",  # For events with actions (PR, issues, etc.)
            "repository": {...},
            "sender": {...},
            "created_at": "2023-01-01T00:00:00Z",
            ...event-specific fields
        }

        Args:
            payload: Raw webhook payload from GitHub

        Returns:
            ParsedWebhookEvent with standardized fields
        """
        # Event ID usually comes from X-GitHub-Delivery header
        # For now, extract from payload if available
        event_id = payload.get("hook_id") or payload.get("delivery_id")

        # Event type should be extracted from X-GitHub-Event header
        # For now, try to infer from payload action
        action = payload.get("action")
        event_type = action if action else None

        # Parse timestamp
        timestamp = None
        created_at = (
            payload.get("created_at")
            or payload.get("updated_at")
            or payload.get("pushed_at")
        )

        if created_at:
            try:
                timestamp = datetime.fromisoformat(
                    created_at.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                timestamp = datetime.now(UTC)

        return ParsedWebhookEvent(
            event_id=str(event_id) if event_id else None,
            event_type=event_type,
            timestamp=timestamp or datetime.now(UTC),
            data=payload,
        )

    def generate_random_secret(self) -> str:
        """
        Generate a high-entropy random secret for webhook verification.

        Returns:
            Random hex string (64 characters)
        """
        import secrets

        return secrets.token_hex(32)  # 32 bytes = 64 hex characters
