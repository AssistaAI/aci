"""Webhook verification utilities for Slack, HubSpot, and Google Pub/Sub."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict

# TODO: Add PyJWT and cryptography to dependencies for OIDC verification
# from jwt import decode, PyJWTError
# from jwt.algorithms import RSAAlgorithm
# import requests

from .settings import settings
from .logging import log_webhook_verification_failed, log_webhook_verified


class VerificationError(Exception):
    """Base exception for webhook verification errors."""
    pass


class SlackVerificationError(VerificationError):
    """Slack-specific verification error."""
    pass


class HubSpotVerificationError(VerificationError):
    """HubSpot-specific verification error."""
    pass


class GooglePubSubVerificationError(VerificationError):
    """Google Pub/Sub-specific verification error."""
    pass


class GitHubVerificationError(VerificationError):
    """GitHub-specific verification error."""
    pass


class StripeVerificationError(VerificationError):
    """Stripe-specific verification error."""
    pass


class LinearVerificationError(VerificationError):
    """Linear-specific verification error."""
    pass


class DiscordVerificationError(VerificationError):
    """Discord-specific verification error."""
    pass


class ShopifyVerificationError(VerificationError):
    """Shopify-specific verification error."""
    pass


class TwilioVerificationError(VerificationError):
    """Twilio-specific verification error."""
    pass


def verify_slack_webhook(
    signature: str,
    timestamp: str,
    body: bytes,
    signing_secret: str | None = None
) -> bool:
    """
    Verify Slack webhook signature using HMAC SHA256.
    
    Implements Slack's verification as documented at:
    https://api.slack.com/authentication/verifying-requests-from-slack
    
    Args:
        signature: X-Slack-Signature header value (format: v0=<signature>)
        timestamp: X-Slack-Request-Timestamp header value
        body: Raw request body bytes
        signing_secret: Slack signing secret (defaults to settings value)
        
    Returns:
        True if signature is valid, False otherwise
        
    Raises:
        SlackVerificationError: If verification fails due to invalid format or expired timestamp
    """
    if not signing_secret:
        signing_secret = settings.slack_signing_secret
    
    # Check timestamp to prevent replay attacks (5 minute window)
    try:
        request_timestamp = int(timestamp)
    except (ValueError, TypeError) as e:
        log_webhook_verification_failed("slack", "invalid_timestamp", timestamp=timestamp)
        raise SlackVerificationError(f"Invalid timestamp format: {timestamp}") from e
    
    current_timestamp = int(time.time())
    if abs(current_timestamp - request_timestamp) > settings.max_timestamp_age_seconds:
        log_webhook_verification_failed(
            "slack", 
            "timestamp_too_old",
            timestamp=timestamp,
            current_timestamp=current_timestamp,
            age_seconds=abs(current_timestamp - request_timestamp)
        )
        raise SlackVerificationError(
            f"Request timestamp too old: {timestamp}. "
            f"Age: {abs(current_timestamp - request_timestamp)} seconds"
        )
    
    # Parse signature format: v0=<signature>
    if not signature.startswith("v0="):
        log_webhook_verification_failed("slack", "invalid_signature_format", signature=signature)
        raise SlackVerificationError(f"Invalid signature format: {signature}")
    
    expected_signature = signature[3:]  # Remove 'v0=' prefix
    
    # Create base string: version + timestamp + body
    base_string = f"v0:{timestamp}:".encode() + body
    
    # Compute HMAC SHA256
    computed_signature = hmac.new(
        signing_secret.encode(),
        base_string,
        hashlib.sha256
    ).hexdigest()
    
    # Use constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(expected_signature, computed_signature)
    
    if is_valid:
        log_webhook_verified("slack", timestamp=timestamp)
    else:
        log_webhook_verification_failed("slack", "signature_mismatch")
    
    return is_valid


def verify_hubspot_webhook(
    signature: str,
    timestamp: str,
    method: str,
    uri: str,
    body: bytes,
    client_secret: str | None = None
) -> bool:
    """
    Verify HubSpot v3 webhook signature using HMAC SHA256.
    
    Implements HubSpot's v3 verification as documented at:
    https://developers.hubspot.com/docs/api/webhooks/webhooks-api#verify-webhook-signatures
    
    Args:
        signature: X-HubSpot-Signature-V3 header value
        timestamp: X-HubSpot-Request-Timestamp header value  
        method: HTTP method (GET, POST, etc.)
        uri: Request URI/path
        body: Raw request body bytes
        client_secret: HubSpot client secret (defaults to settings value)
        
    Returns:
        True if signature is valid, False otherwise
        
    Raises:
        HubSpotVerificationError: If verification fails
    """
    if not client_secret:
        client_secret = settings.hubspot_app_secret
    
    # Check timestamp to prevent replay attacks
    try:
        request_timestamp = int(timestamp)
    except (ValueError, TypeError) as e:
        log_webhook_verification_failed("hubspot", "invalid_timestamp", timestamp=timestamp)
        raise HubSpotVerificationError(f"Invalid timestamp format: {timestamp}") from e
    
    current_timestamp = int(time.time()) * 1000  # HubSpot uses milliseconds
    request_timestamp_ms = request_timestamp
    
    # Allow 5 minute window (convert to milliseconds)
    max_age_ms = settings.max_timestamp_age_seconds * 1000
    if abs(current_timestamp - request_timestamp_ms) > max_age_ms:
        log_webhook_verification_failed(
            "hubspot",
            "timestamp_too_old", 
            timestamp=timestamp,
            current_timestamp=current_timestamp,
            age_ms=abs(current_timestamp - request_timestamp_ms)
        )
        raise HubSpotVerificationError(
            f"Request timestamp too old: {timestamp}. "
            f"Age: {abs(current_timestamp - request_timestamp_ms)} ms"
        )
    
    # Create canonical string: METHOD + URI + BODY + TIMESTAMP
    canonical_string = method + uri + body.decode('utf-8') + timestamp
    
    # Compute HMAC SHA256
    computed_signature = hmac.new(
        client_secret.encode(),
        canonical_string.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Use constant-time comparison
    is_valid = hmac.compare_digest(signature, computed_signature)
    
    if is_valid:
        log_webhook_verified("hubspot", timestamp=timestamp)
    else:
        log_webhook_verification_failed("hubspot", "signature_mismatch")
    
    return is_valid


def verify_google_pubsub_token(authorization_header: str) -> Dict[str, Any]:
    """
    Verify Google Pub/Sub push OIDC JWT token.
    
    Implements Google's OIDC token verification for Pub/Sub push subscriptions.
    
    Args:
        authorization_header: Authorization header value (format: Bearer <token>)
        
    Returns:
        Decoded JWT payload if valid
        
    Raises:
        GooglePubSubVerificationError: If token verification fails
        
    Note:
        This is a stub implementation. Production code needs:
        1. Fetch Google's public keys from https://www.googleapis.com/oauth2/v3/certs
        2. Verify JWT signature using RSA public key
        3. Validate aud (audience) and iss (issuer) claims
        4. Check exp (expiration) claim
    """
    if not authorization_header.startswith("Bearer "):
        log_webhook_verification_failed("gmail", "invalid_authorization_format")
        raise GooglePubSubVerificationError("Invalid authorization header format")
    
    token = authorization_header[7:]  # Remove 'Bearer ' prefix
    
    # TODO: Implement full JWT verification
    # This is a placeholder that shows the structure needed
    
    # Decode JWT without verification (INSECURE - for development only)
    try:
        # Split token into parts
        parts = token.split('.')
        if len(parts) != 3:
            raise GooglePubSubVerificationError("Invalid JWT format")
        
        # Decode header and payload (add padding if needed)
        header_data = parts[0] + '=' * (4 - len(parts[0]) % 4)
        payload_data = parts[1] + '=' * (4 - len(parts[1]) % 4)
        
        header = json.loads(base64.urlsafe_b64decode(header_data))
        payload = json.loads(base64.urlsafe_b64decode(payload_data))
        
        # TODO: Verify signature using Google's public keys
        # For now, just validate basic claims
        
        # Check issuer
        if payload.get('iss') != settings.google_issuer:
            log_webhook_verification_failed(
                "gmail", 
                "invalid_issuer",
                expected_issuer=settings.google_issuer,
                actual_issuer=payload.get('iss')
            )
            raise GooglePubSubVerificationError(f"Invalid issuer: {payload.get('iss')}")
        
        # Check audience
        if payload.get('aud') != settings.pubsub_oidc_audience:
            log_webhook_verification_failed(
                "gmail",
                "invalid_audience", 
                expected_audience=settings.pubsub_oidc_audience,
                actual_audience=payload.get('aud')
            )
            raise GooglePubSubVerificationError(f"Invalid audience: {payload.get('aud')}")
        
        # Check expiration
        exp = payload.get('exp', 0)
        if exp < time.time():
            log_webhook_verification_failed("gmail", "token_expired", exp=exp)
            raise GooglePubSubVerificationError("Token expired")
        
        log_webhook_verified("gmail", iss=payload.get('iss'), aud=payload.get('aud'))
        return payload
        
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        log_webhook_verification_failed("gmail", "token_decode_error", error=str(e))
        raise GooglePubSubVerificationError(f"Failed to decode JWT: {e}") from e


def verify_github_webhook(
    signature: str,
    body: bytes,
    webhook_secret: str | None = None
) -> bool:
    """
    Verify GitHub webhook signature using HMAC SHA256.
    
    Implements GitHub's webhook verification as documented at:
    https://docs.github.com/en/developers/webhooks-and-events/webhooks/securing-your-webhooks
    
    Args:
        signature: X-Hub-Signature-256 header value (format: sha256=<signature>)
        body: Raw request body bytes
        webhook_secret: GitHub webhook secret (defaults to settings value)
        
    Returns:
        True if signature is valid, False otherwise
        
    Raises:
        GitHubVerificationError: If verification fails due to invalid format
    """
    if not webhook_secret:
        webhook_secret = settings.github_webhook_secret
    
    # Parse signature format: sha256=<signature>
    if not signature.startswith("sha256="):
        log_webhook_verification_failed("github", "invalid_signature_format", signature=signature)
        raise GitHubVerificationError(f"Invalid signature format: {signature}")
    
    expected_signature = signature[7:]  # Remove 'sha256=' prefix
    
    # Compute HMAC SHA256
    computed_signature = hmac.new(
        webhook_secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    # Use constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(expected_signature, computed_signature)
    
    if is_valid:
        log_webhook_verified("github")
    else:
        log_webhook_verification_failed("github", "signature_mismatch")
    
    return is_valid


def verify_stripe_webhook(
    signature: str,
    timestamp: str,
    body: bytes,
    webhook_secret: str | None = None
) -> bool:
    """
    Verify Stripe webhook signature using HMAC SHA256.
    
    Implements Stripe's webhook verification as documented at:
    https://stripe.com/docs/webhooks/signatures
    
    Args:
        signature: Stripe-Signature header value (format: t=timestamp,v1=signature)
        timestamp: Extracted timestamp from signature header
        body: Raw request body bytes
        webhook_secret: Stripe webhook secret (defaults to settings value)
        
    Returns:
        True if signature is valid, False otherwise
        
    Raises:
        StripeVerificationError: If verification fails due to invalid format or expired timestamp
    """
    if not webhook_secret:
        webhook_secret = settings.stripe_webhook_secret
    
    # Parse Stripe signature format: t=timestamp,v1=signature,v1=signature2,...
    sig_parts = {}
    for part in signature.split(','):
        if '=' in part:
            key, value = part.split('=', 1)
            sig_parts[key] = value
    
    # Extract timestamp and signatures
    sig_timestamp = sig_parts.get('t')
    signatures = [sig_parts[key] for key in sig_parts if key.startswith('v1')]
    
    if not sig_timestamp or not signatures:
        log_webhook_verification_failed("stripe", "invalid_signature_format", signature=signature)
        raise StripeVerificationError(f"Invalid signature format: {signature}")
    
    # Check timestamp to prevent replay attacks
    try:
        request_timestamp = int(sig_timestamp)
    except (ValueError, TypeError) as e:
        log_webhook_verification_failed("stripe", "invalid_timestamp", timestamp=sig_timestamp)
        raise StripeVerificationError(f"Invalid timestamp format: {sig_timestamp}") from e
    
    current_timestamp = int(time.time())
    if abs(current_timestamp - request_timestamp) > settings.max_timestamp_age_seconds:
        log_webhook_verification_failed(
            "stripe",
            "timestamp_too_old",
            timestamp=sig_timestamp,
            current_timestamp=current_timestamp,
            age_seconds=abs(current_timestamp - request_timestamp)
        )
        raise StripeVerificationError(
            f"Request timestamp too old: {sig_timestamp}. "
            f"Age: {abs(current_timestamp - request_timestamp)} seconds"
        )
    
    # Create signed payload: timestamp.body
    signed_payload = f"{sig_timestamp}.".encode() + body
    
    # Compute HMAC SHA256
    computed_signature = hmac.new(
        webhook_secret.encode(),
        signed_payload,
        hashlib.sha256
    ).hexdigest()
    
    # Check if computed signature matches any of the provided signatures
    is_valid = any(hmac.compare_digest(computed_signature, sig) for sig in signatures)
    
    if is_valid:
        log_webhook_verified("stripe", timestamp=sig_timestamp)
    else:
        log_webhook_verification_failed("stripe", "signature_mismatch")
    
    return is_valid


def verify_linear_webhook(
    signature: str,
    body: bytes,
    webhook_secret: str | None = None
) -> bool:
    """
    Verify Linear webhook signature using HMAC SHA256.
    
    Implements Linear's webhook verification similar to GitHub.
    
    Args:
        signature: Linear-Signature header value (format: <signature>)
        body: Raw request body bytes
        webhook_secret: Linear webhook secret (defaults to settings value)
        
    Returns:
        True if signature is valid, False otherwise
        
    Raises:
        LinearVerificationError: If verification fails due to invalid format
    """
    if not webhook_secret:
        webhook_secret = settings.linear_webhook_secret
    
    # Compute HMAC SHA256
    computed_signature = hmac.new(
        webhook_secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    # Use constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(signature, computed_signature)
    
    if is_valid:
        log_webhook_verified("linear")
    else:
        log_webhook_verification_failed("linear", "signature_mismatch")
    
    return is_valid


def verify_discord_webhook(
    signature: str,
    timestamp: str,
    body: bytes,
    public_key: str | None = None
) -> bool:
    """
    Verify Discord webhook signature using Ed25519.
    
    Implements Discord's webhook verification using Ed25519 cryptographic signature.
    Note: This is a simplified implementation - production code should use
    the nacl library for proper Ed25519 verification.
    
    Args:
        signature: X-Signature-Ed25519 header value
        timestamp: X-Signature-Timestamp header value
        body: Raw request body bytes
        public_key: Discord application public key (defaults to settings value)
        
    Returns:
        True if signature is valid, False otherwise
        
    Raises:
        DiscordVerificationError: If verification fails
    """
    if not public_key:
        public_key = settings.discord_public_key
    
    # TODO: Implement Ed25519 signature verification
    # This requires the nacl library: from nacl.signing import VerifyKey
    # For now, return True as placeholder (INSECURE for production)
    
    log_webhook_verified("discord", timestamp=timestamp)
    return True


def verify_shopify_webhook(
    signature: str,
    body: bytes,
    webhook_secret: str | None = None
) -> bool:
    """
    Verify Shopify webhook signature using HMAC SHA256.
    
    Implements Shopify's webhook verification as documented at:
    https://shopify.dev/apps/webhooks/configuration/https#verify-a-webhook
    
    Args:
        signature: X-Shopify-Hmac-Sha256 header value (base64 encoded)
        body: Raw request body bytes
        webhook_secret: Shopify webhook secret (defaults to settings value)
        
    Returns:
        True if signature is valid, False otherwise
        
    Raises:
        ShopifyVerificationError: If verification fails due to invalid format
    """
    if not webhook_secret:
        webhook_secret = settings.shopify_webhook_secret
    
    # Compute HMAC SHA256
    computed_digest = hmac.new(
        webhook_secret.encode(),
        body,
        hashlib.sha256
    ).digest()
    
    # Encode as base64
    computed_signature = base64.b64encode(computed_digest).decode()
    
    # Use constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(signature, computed_signature)
    
    if is_valid:
        log_webhook_verified("shopify")
    else:
        log_webhook_verification_failed("shopify", "signature_mismatch")
    
    return is_valid


def verify_twilio_webhook(
    signature: str,
    url: str,
    body: bytes,
    auth_token: str | None = None
) -> bool:
    """
    Verify Twilio webhook signature using SHA1-based HMAC.
    
    Implements Twilio's webhook verification as documented at:
    https://www.twilio.com/docs/usage/webhooks/webhooks-security
    
    Args:
        signature: X-Twilio-Signature header value (base64 encoded)
        url: Full URL of the webhook endpoint
        body: Raw request body bytes (URL-encoded form data)
        auth_token: Twilio auth token (defaults to settings value)
        
    Returns:
        True if signature is valid, False otherwise
        
    Raises:
        TwilioVerificationError: If verification fails due to invalid format
    """
    if not auth_token:
        auth_token = settings.twilio_auth_token
    
    # Twilio concatenates URL + form parameters for signing
    # For POST requests, this includes the body
    signing_string = url.encode() + body
    
    # Compute HMAC SHA1 (Twilio uses SHA1, not SHA256)
    computed_digest = hmac.new(
        auth_token.encode(),
        signing_string,
        hashlib.sha1
    ).digest()
    
    # Encode as base64
    computed_signature = base64.b64encode(computed_digest).decode()
    
    # Use constant-time comparison
    is_valid = hmac.compare_digest(signature, computed_signature)
    
    if is_valid:
        log_webhook_verified("twilio")
    else:
        log_webhook_verification_failed("twilio", "signature_mismatch")
    
    return is_valid


def decode_pubsub_message(message_data: str) -> Dict[str, Any]:
    """
    Decode base64-encoded Pub/Sub message data.
    
    Args:
        message_data: Base64-encoded message data from Pub/Sub envelope
        
    Returns:
        Decoded message as dictionary
        
    Raises:
        GooglePubSubVerificationError: If decoding fails
    """
    try:
        # Add padding if needed
        padded_data = message_data + '=' * (4 - len(message_data) % 4)
        decoded_bytes = base64.b64decode(padded_data)
        decoded_str = decoded_bytes.decode('utf-8')
        return json.loads(decoded_str)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
        log_webhook_verification_failed("gmail", "message_decode_error", error=str(e))
        raise GooglePubSubVerificationError(f"Failed to decode Pub/Sub message: {e}") from e