"""Event normalization utilities for converting provider-specific events to unified format."""

from datetime import datetime, timezone
from typing import Any, Dict, List
from dataclasses import dataclass

from .models import WebhookProvider
from .logging import log_event_normalized


@dataclass
class NormalizedEvent:
    """Unified event format for all webhook providers."""
    
    provider: str  # slack, hubspot, gmail
    type: str  # e.g., "slack.message", "hubspot.contact.propertyChange", "gmail.history"
    subject_id: str  # Unique identifier for the event subject
    ts: datetime  # Event timestamp
    data: Dict[str, Any]  # Provider-specific event data
    
    def __post_init__(self) -> None:
        """Validate normalized event after creation."""
        if not self.provider:
            raise ValueError("Provider is required")
        if not self.type:
            raise ValueError("Event type is required")
        if not self.subject_id:
            raise ValueError("Subject ID is required")
        if not isinstance(self.data, dict):
            raise ValueError("Data must be a dictionary")


def normalize_slack_event(payload: Dict[str, Any]) -> List[NormalizedEvent]:
    """
    Normalize Slack webhook payload to unified event format.
    
    Args:
        payload: Raw Slack webhook payload
        
    Returns:
        List of normalized events (usually contains one event)
    """
    events = []
    
    # Handle URL verification challenge
    if payload.get("type") == "url_verification":
        # URL verification doesn't generate a normalized event
        return events
    
    # Handle event callbacks
    if payload.get("type") == "event_callback":
        event_data = payload.get("event", {})
        event_type = event_data.get("type")
        
        if event_type == "message":
            # Slack message event
            channel_id = event_data.get("channel")
            user_id = event_data.get("user")
            event_ts = event_data.get("ts")
            
            if channel_id and user_id and event_ts:
                # Convert Slack timestamp to datetime
                ts = datetime.fromtimestamp(float(event_ts))
                
                normalized_event = NormalizedEvent(
                    provider="slack",
                    type="slack.message", 
                    subject_id=f"{channel_id}:{user_id}",
                    ts=ts,
                    data={
                        "channel_id": channel_id,
                        "user_id": user_id,
                        "text": event_data.get("text", ""),
                        "event_ts": event_ts,
                        "team_id": payload.get("team_id"),
                        "original_event": event_data
                    }
                )
                events.append(normalized_event)
                
                log_event_normalized(
                    provider="slack",
                    event_type="slack.message",
                    event_id=event_ts,
                    channel_id=channel_id,
                    user_id=user_id
                )
        
        elif event_type in ["channel_created", "channel_deleted", "channel_rename"]:
            # Channel events
            channel_data = event_data.get("channel", {})
            channel_id = channel_data.get("id")
            event_ts = event_data.get("event_ts")
            
            if channel_id and event_ts:
                ts = datetime.fromtimestamp(float(event_ts))
                
                normalized_event = NormalizedEvent(
                    provider="slack",
                    type=f"slack.{event_type}",
                    subject_id=channel_id,
                    ts=ts,
                    data={
                        "channel_id": channel_id,
                        "channel_name": channel_data.get("name"),
                        "event_ts": event_ts,
                        "team_id": payload.get("team_id"),
                        "original_event": event_data
                    }
                )
                events.append(normalized_event)
                
                log_event_normalized(
                    provider="slack",
                    event_type=f"slack.{event_type}",
                    event_id=event_ts,
                    channel_id=channel_id
                )
    
    return events


def normalize_hubspot_event(payload: Dict[str, Any]) -> List[NormalizedEvent]:
    """
    Normalize HubSpot webhook payload to unified event format.
    
    Args:
        payload: Raw HubSpot webhook payload (may contain multiple events)
        
    Returns:
        List of normalized events (one per item in the payload)
    """
    events = []
    
    # HubSpot webhooks can contain multiple events in an array
    hubspot_events = payload if isinstance(payload, list) else [payload]
    
    for event_data in hubspot_events:
        event_id = event_data.get("eventId")
        object_id = event_data.get("objectId") 
        subscription_type = event_data.get("subscriptionType")
        occurred_at = event_data.get("occurredAt")
        
        if not all([event_id, object_id, subscription_type, occurred_at]):
            continue
            
        # Convert HubSpot timestamp to datetime (HubSpot uses milliseconds)
        ts = datetime.fromtimestamp(occurred_at / 1000.0)
        
        # Map HubSpot subscription types to our event types
        if subscription_type == "contact.propertyChange":
            event_type = "hubspot.contact.propertyChange"
        elif subscription_type == "company.propertyChange":
            event_type = "hubspot.company.propertyChange"
        elif subscription_type == "deal.propertyChange":
            event_type = "hubspot.deal.propertyChange"
        elif subscription_type.startswith("contact."):
            event_type = f"hubspot.contact.{subscription_type.split('.', 1)[1]}"
        elif subscription_type.startswith("company."):
            event_type = f"hubspot.company.{subscription_type.split('.', 1)[1]}"
        elif subscription_type.startswith("deal."):
            event_type = f"hubspot.deal.{subscription_type.split('.', 1)[1]}"
        else:
            event_type = f"hubspot.{subscription_type}"
        
        normalized_event = NormalizedEvent(
            provider="hubspot",
            type=event_type,
            subject_id=str(object_id),
            ts=ts,
            data={
                "event_id": event_id,
                "object_id": object_id,
                "subscription_type": subscription_type,
                "occurred_at": occurred_at,
                "portal_id": event_data.get("portalId"),
                "app_id": event_data.get("appId"),
                "property_name": event_data.get("propertyName"),
                "property_value": event_data.get("propertyValue"),
                "original_event": event_data
            }
        )
        events.append(normalized_event)
        
        log_event_normalized(
            provider="hubspot",
            event_type=event_type,
            event_id=event_id,
            object_id=object_id,
            subscription_type=subscription_type
        )
    
    return events


def normalize_github_event(payload: Dict[str, Any]) -> List[NormalizedEvent]:
    """
    Normalize GitHub webhook payload to unified event format.
    
    Args:
        payload: Raw GitHub webhook payload
        
    Returns:
        List of normalized events (usually contains one event)
    """
    events = []
    
    # Get common GitHub webhook headers that would be passed in payload
    event_type = payload.get("_event_type")  # X-GitHub-Event header
    delivery_id = payload.get("_delivery_id")  # X-GitHub-Delivery header
    
    if not event_type:
        return events
    
    # Extract repository info if available
    repo_data = payload.get("repository", {})
    repo_full_name = repo_data.get("full_name")
    
    # Use current timestamp since GitHub doesn't provide consistent timestamp format
    ts = datetime.utcnow()
    
    # Create subject_id based on event type
    if event_type in ["push"]:
        # For push events, use repository + ref
        ref = payload.get("ref", "")
        subject_id = f"{repo_full_name}:{ref}" if repo_full_name else ref
    elif event_type in ["issues", "issue_comment"]:
        # For issue events, use repository + issue number
        issue_data = payload.get("issue", {})
        issue_number = issue_data.get("number")
        subject_id = f"{repo_full_name}:issue:{issue_number}" if repo_full_name and issue_number else repo_full_name or ""
    elif event_type in ["pull_request", "pull_request_review"]:
        # For PR events, use repository + PR number
        pr_data = payload.get("pull_request", {})
        pr_number = pr_data.get("number")
        subject_id = f"{repo_full_name}:pr:{pr_number}" if repo_full_name and pr_number else repo_full_name or ""
    elif repo_full_name:
        subject_id = repo_full_name
    else:
        subject_id = delivery_id or event_type
    
    if subject_id:
        normalized_event = NormalizedEvent(
            provider="github",
            type=f"github.{event_type}",
            subject_id=subject_id,
            ts=ts,
            data={
                "event_type": event_type,
                "delivery_id": delivery_id,
                "repository": repo_data.get("full_name") if repo_data else None,
                "action": payload.get("action"),  # Most GitHub events have an action
                "sender": payload.get("sender", {}).get("login"),
                "original_payload": payload
            }
        )
        events.append(normalized_event)
        
        log_event_normalized(
            provider="github",
            event_type=f"github.{event_type}",
            event_id=delivery_id,
            repository=repo_data.get("full_name") if repo_data else None,
            action=payload.get("action")
        )
    
    return events


def normalize_stripe_event(payload: Dict[str, Any]) -> List[NormalizedEvent]:
    """
    Normalize Stripe webhook payload to unified event format.
    
    Args:
        payload: Raw Stripe webhook payload
        
    Returns:
        List of normalized events (usually contains one event)
    """
    events = []
    
    # Stripe webhook structure
    event_id = payload.get("id")
    event_type = payload.get("type")
    created = payload.get("created")
    
    if not event_id or not event_type:
        return events
    
    # Convert Stripe timestamp to datetime
    ts = datetime.fromtimestamp(created) if created else datetime.utcnow()
    
    # Extract object data if available
    data_obj = payload.get("data", {}).get("object", {})
    object_id = data_obj.get("id", "")
    object_type = data_obj.get("object", "")
    
    # Create subject_id based on event type
    if object_type and object_id:
        subject_id = f"{object_type}:{object_id}"
    elif object_id:
        subject_id = object_id
    else:
        subject_id = event_id
    
    normalized_event = NormalizedEvent(
        provider="stripe",
        type=f"stripe.{event_type}",
        subject_id=subject_id,
        ts=ts,
        data={
            "event_id": event_id,
            "event_type": event_type,
            "object_type": object_type,
            "object_id": object_id,
            "created": created,
            "livemode": payload.get("livemode"),
            "api_version": payload.get("api_version"),
            "original_payload": payload
        }
    )
    events.append(normalized_event)
    
    log_event_normalized(
        provider="stripe",
        event_type=f"stripe.{event_type}",
        event_id=event_id,
        object_type=object_type,
        object_id=object_id
    )
    
    return events


def normalize_linear_event(payload: Dict[str, Any]) -> List[NormalizedEvent]:
    """
    Normalize Linear webhook payload to unified event format.
    
    Args:
        payload: Raw Linear webhook payload
        
    Returns:
        List of normalized events (usually contains one event)
    """
    events = []
    
    # Linear webhook structure
    action = payload.get("action")
    event_type = payload.get("type")
    data_obj = payload.get("data", {})
    
    if not action or not event_type:
        return events
    
    # Use current timestamp
    ts = datetime.now(timezone.utc)
    
    # Extract object ID based on type
    object_id = ""
    if event_type == "Issue":
        object_id = data_obj.get("id", "")
    elif event_type == "Comment":
        object_id = data_obj.get("id", "")
    elif event_type == "Project":
        object_id = data_obj.get("id", "")
    
    # Create subject_id
    if object_id:
        subject_id = f"{event_type.lower()}:{object_id}"
    else:
        subject_id = event_type.lower()
    
    normalized_event = NormalizedEvent(
        provider="linear",
        type=f"linear.{event_type.lower()}.{action}",
        subject_id=subject_id,
        ts=ts,
        data={
            "action": action,
            "type": event_type,
            "object_id": object_id,
            "team_id": data_obj.get("teamId"),
            "organization_id": payload.get("organizationId"),
            "original_payload": payload
        }
    )
    events.append(normalized_event)
    
    log_event_normalized(
        provider="linear",
        event_type=f"linear.{event_type.lower()}.{action}",
        event_id=object_id,
        action=action,
        type=event_type
    )
    
    return events


def normalize_discord_event(payload: Dict[str, Any]) -> List[NormalizedEvent]:
    """
    Normalize Discord webhook payload to unified event format.
    
    Args:
        payload: Raw Discord webhook payload
        
    Returns:
        List of normalized events (usually contains one event)
    """
    events = []
    
    # Discord webhook structure
    event_type = payload.get("t")  # Event type
    event_data = payload.get("d", {})  # Event data
    
    if not event_type:
        return events
    
    # Use current timestamp
    ts = datetime.now(timezone.utc)
    
    # Create subject_id based on event type
    if event_type == "MESSAGE_CREATE":
        channel_id = event_data.get("channel_id")
        author_id = event_data.get("author", {}).get("id")
        subject_id = f"{channel_id}:{author_id}" if channel_id and author_id else channel_id or author_id or ""
    elif event_type == "GUILD_MEMBER_ADD":
        guild_id = event_data.get("guild_id")
        user_id = event_data.get("user", {}).get("id")
        subject_id = f"{guild_id}:{user_id}" if guild_id and user_id else guild_id or user_id or ""
    else:
        # Generic fallback
        guild_id = event_data.get("guild_id")
        subject_id = guild_id or event_type.lower()
    
    if subject_id:
        normalized_event = NormalizedEvent(
            provider="discord",
            type=f"discord.{event_type.lower()}",
            subject_id=subject_id,
            ts=ts,
            data={
                "event_type": event_type,
                "guild_id": event_data.get("guild_id"),
                "channel_id": event_data.get("channel_id"),
                "user_id": event_data.get("user", {}).get("id") if event_data.get("user") else None,
                "original_payload": payload
            }
        )
        events.append(normalized_event)
        
        log_event_normalized(
            provider="discord",
            event_type=f"discord.{event_type.lower()}",
            event_id=event_data.get("id", ""),
            guild_id=event_data.get("guild_id"),
            channel_id=event_data.get("channel_id")
        )
    
    return events


def normalize_shopify_event(payload: Dict[str, Any]) -> List[NormalizedEvent]:
    """
    Normalize Shopify webhook payload to unified event format.
    
    Args:
        payload: Raw Shopify webhook payload
        
    Returns:
        List of normalized events (usually contains one event)
    """
    events = []
    
    # Shopify webhook headers are typically passed in payload
    event_type = payload.get("_topic")  # X-Shopify-Topic header
    shop_domain = payload.get("_shop_domain")  # X-Shopify-Shop-Domain header
    
    if not event_type:
        return events
    
    # Use current timestamp or extract from payload
    created_at = payload.get("created_at")
    if created_at:
        try:
            # Parse ISO timestamp
            ts = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            ts = datetime.utcnow()
    else:
        ts = datetime.utcnow()
    
    # Create subject_id based on event type and object
    object_id = payload.get("id", "")
    if shop_domain and object_id:
        subject_id = f"{shop_domain}:{object_id}"
    elif shop_domain:
        subject_id = shop_domain
    elif object_id:
        subject_id = str(object_id)
    else:
        subject_id = event_type
    
    normalized_event = NormalizedEvent(
        provider="shopify",
        type=f"shopify.{event_type}",
        subject_id=subject_id,
        ts=ts,
        data={
            "topic": event_type,
            "shop_domain": shop_domain,
            "object_id": object_id,
            "created_at": created_at,
            "updated_at": payload.get("updated_at"),
            "original_payload": payload
        }
    )
    events.append(normalized_event)
    
    log_event_normalized(
        provider="shopify",
        event_type=f"shopify.{event_type}",
        event_id=str(object_id),
        shop_domain=shop_domain,
        topic=event_type
    )
    
    return events


def normalize_twilio_event(payload: Dict[str, Any]) -> List[NormalizedEvent]:
    """
    Normalize Twilio webhook payload to unified event format.
    
    Args:
        payload: Raw Twilio webhook payload (form-encoded data)
        
    Returns:
        List of normalized events (usually contains one event)
    """
    events = []
    
    # Twilio webhook common fields
    message_sid = payload.get("MessageSid") or payload.get("CallSid") or payload.get("Sid")
    account_sid = payload.get("AccountSid")
    event_type = payload.get("MessageStatus") or payload.get("CallStatus") or "unknown"
    
    if not message_sid:
        return events
    
    # Use current timestamp
    ts = datetime.now(timezone.utc)
    
    # Create subject_id
    if account_sid and message_sid:
        subject_id = f"{account_sid}:{message_sid}"
    else:
        subject_id = message_sid
    
    # Determine event type
    if payload.get("MessageSid"):
        normalized_type = f"twilio.sms.{event_type.lower()}"
    elif payload.get("CallSid"):
        normalized_type = f"twilio.voice.{event_type.lower()}"
    else:
        normalized_type = f"twilio.{event_type.lower()}"
    
    normalized_event = NormalizedEvent(
        provider="twilio",
        type=normalized_type,
        subject_id=subject_id,
        ts=ts,
        data={
            "message_sid": message_sid,
            "account_sid": account_sid,
            "status": event_type,
            "from": payload.get("From"),
            "to": payload.get("To"),
            "body": payload.get("Body"),
            "original_payload": payload
        }
    )
    events.append(normalized_event)
    
    log_event_normalized(
        provider="twilio",
        event_type=normalized_type,
        event_id=message_sid,
        account_sid=account_sid,
        status=event_type
    )
    
    return events


def normalize_gmail_event(pubsub_payload: Dict[str, Any]) -> List[NormalizedEvent]:
    """
    Normalize Gmail Pub/Sub webhook payload to unified event format.
    
    Args:
        pubsub_payload: Decoded Pub/Sub message payload
        
    Returns:
        List of normalized events (usually contains one event)
    """
    events = []
    
    email_address = pubsub_payload.get("emailAddress")
    history_id = pubsub_payload.get("historyId")
    
    if not email_address or not history_id:
        return events
    
    # Use current timestamp since Pub/Sub doesn't provide event timestamp
    ts = datetime.utcnow()
    
    normalized_event = NormalizedEvent(
        provider="gmail",
        type="gmail.history",
        subject_id=email_address,
        ts=ts,
        data={
            "email_address": email_address,
            "history_id": str(history_id),
            "original_payload": pubsub_payload
        }
    )
    events.append(normalized_event)
    
    log_event_normalized(
        provider="gmail",
        event_type="gmail.history",
        event_id=f"{email_address}:{history_id}",
        email_address=email_address,
        history_id=history_id
    )
    
    return events


def normalize_webhook_payload(
    provider: WebhookProvider, 
    payload: Dict[str, Any]
) -> List[NormalizedEvent]:
    """
    Normalize webhook payload based on provider.
    
    Args:
        provider: The webhook provider (slack, hubspot, gmail, github, etc.)
        payload: Raw webhook payload
        
    Returns:
        List of normalized events
        
    Raises:
        ValueError: If provider is not supported
    """
    if provider == WebhookProvider.SLACK:
        return normalize_slack_event(payload)
    elif provider == WebhookProvider.HUBSPOT:
        return normalize_hubspot_event(payload)
    elif provider == WebhookProvider.GMAIL:
        return normalize_gmail_event(payload)
    elif provider == WebhookProvider.GITHUB:
        return normalize_github_event(payload)
    elif provider == WebhookProvider.STRIPE:
        return normalize_stripe_event(payload)
    elif provider == WebhookProvider.LINEAR:
        return normalize_linear_event(payload)
    elif provider == WebhookProvider.DISCORD:
        return normalize_discord_event(payload)
    elif provider == WebhookProvider.SHOPIFY:
        return normalize_shopify_event(payload)
    elif provider == WebhookProvider.TWILIO:
        return normalize_twilio_event(payload)
    else:
        raise ValueError(f"Unsupported webhook provider: {provider}")


def get_event_id_for_provider(
    provider: WebhookProvider,
    payload: Dict[str, Any]
) -> str | None:
    """
    Extract unique event ID for idempotency based on provider.
    
    Args:
        provider: The webhook provider
        payload: Raw webhook payload
        
    Returns:
        Unique event ID for the provider, or None if not found
    """
    if provider == WebhookProvider.SLACK:
        # For Slack, use event_id if available, fallback to event.event_ts
        if payload.get("type") == "event_callback":
            event_data = payload.get("event", {})
            return event_data.get("event_ts") or payload.get("event_id")
        return payload.get("event_id")
    
    elif provider == WebhookProvider.HUBSPOT:
        # For HubSpot, return the first eventId from the array
        if isinstance(payload, list) and payload:
            return payload[0].get("eventId")
        elif isinstance(payload, dict):
            return payload.get("eventId")
        return None
    
    elif provider == WebhookProvider.GMAIL:
        # For Gmail, combine emailAddress and historyId
        email_address = payload.get("emailAddress")
        history_id = payload.get("historyId")
        if email_address and history_id:
            return f"{email_address}:{history_id}"
        return None
    
    elif provider == WebhookProvider.GITHUB:
        # For GitHub, use delivery ID from X-GitHub-Delivery header
        return payload.get("_delivery_id")
    
    elif provider == WebhookProvider.STRIPE:
        # For Stripe, use event ID
        return payload.get("id")
    
    elif provider == WebhookProvider.LINEAR:
        # For Linear, use data object ID + action
        data_obj = payload.get("data", {})
        object_id = data_obj.get("id", "")
        action = payload.get("action", "")
        if object_id and action:
            return f"{object_id}:{action}"
        return object_id or action
    
    elif provider == WebhookProvider.DISCORD:
        # For Discord, use event sequence number or message ID
        event_data = payload.get("d", {})
        return event_data.get("id") or payload.get("s")
    
    elif provider == WebhookProvider.SHOPIFY:
        # For Shopify, use object ID + topic
        object_id = payload.get("id", "")
        topic = payload.get("_topic", "")
        if object_id and topic:
            return f"{topic}:{object_id}"
        return str(object_id) or topic
    
    elif provider == WebhookProvider.TWILIO:
        # For Twilio, use MessageSid or CallSid
        return payload.get("MessageSid") or payload.get("CallSid") or payload.get("Sid")
    
    else:
        return None