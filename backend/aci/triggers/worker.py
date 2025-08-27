"""RQ worker for processing normalized events."""

import json
from datetime import datetime
from typing import Any, Dict

# TODO: Add RQ to dependencies in pyproject.toml:
# rq>=1.15.0
# redis>=5.0.0

try:
    from rq import Worker
    from redis import Redis
except ImportError as e:
    raise ImportError(
        "RQ and Redis are required for the triggers module. "
        "Add 'rq>=1.15.0' and 'redis>=5.0.0' to pyproject.toml dependencies."
    ) from e

from .settings import settings
from .normalize import NormalizedEvent
from .logging import (
    log_event_processing_started,
    log_event_processing_completed,
    log_event_processing_failed,
    get_triggers_logger
)

logger = get_triggers_logger()


def process_normalized_event(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a normalized event by routing it to appropriate ACI actions.
    
    This function is called by RQ workers as a background job.
    
    Args:
        event_data: Dictionary containing normalized event data
        
    Returns:
        Dictionary with processing results
        
    Raises:
        Exception: If processing fails
    """
    # Reconstruct NormalizedEvent from serialized data
    normalized_event = NormalizedEvent(
        provider=event_data["provider"],
        type=event_data["type"], 
        subject_id=event_data["subject_id"],
        ts=datetime.fromisoformat(event_data["ts"]),
        data=event_data["data"]
    )
    
    log_event_processing_started(
        provider=normalized_event.provider,
        event_type=normalized_event.type,
        event_id=normalized_event.subject_id
    )
    
    try:
        # Route to appropriate handler based on event type
        result = dispatch_to_aci(normalized_event)
        
        log_event_processing_completed(
            provider=normalized_event.provider,
            event_type=normalized_event.type,
            event_id=normalized_event.subject_id,
            result=result
        )
        
        logger.info(
            f"Successfully processed {normalized_event.type} event "
            f"for {normalized_event.subject_id}"
        )
        
        return {
            "status": "success",
            "event_type": normalized_event.type,
            "subject_id": normalized_event.subject_id,
            "result": result,
            "processed_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        error_msg = str(e)
        log_event_processing_failed(
            provider=normalized_event.provider,
            event_type=normalized_event.type,
            error=error_msg,
            event_id=normalized_event.subject_id
        )
        
        logger.error(
            f"Failed to process {normalized_event.type} event "
            f"for {normalized_event.subject_id}: {error_msg}"
        )
        
        # Re-raise so RQ can handle retries and failure tracking
        raise


def dispatch_to_aci(normalized_event: NormalizedEvent) -> Dict[str, Any]:
    """
    Dispatch normalized event to ACI actions layer.
    
    This is the main integration point between the triggers system
    and the existing ACI function execution infrastructure.
    
    Args:
        normalized_event: The normalized event to process
        
    Returns:
        Result from ACI action execution
        
    TODO: Wire this to real ACI function calls. Current implementation
    provides examples of how to route different event types.
    """
    
    if normalized_event.provider == "slack":
        return _handle_slack_event(normalized_event)
    elif normalized_event.provider == "hubspot":
        return _handle_hubspot_event(normalized_event)
    elif normalized_event.provider == "gmail":
        return _handle_gmail_event(normalized_event)
    elif normalized_event.provider == "github":
        return _handle_github_event(normalized_event)
    elif normalized_event.provider == "stripe":
        return _handle_stripe_event(normalized_event)
    elif normalized_event.provider == "linear":
        return _handle_linear_event(normalized_event)
    elif normalized_event.provider == "discord":
        return _handle_discord_event(normalized_event)
    elif normalized_event.provider == "shopify":
        return _handle_shopify_event(normalized_event)
    elif normalized_event.provider == "twilio":
        return _handle_twilio_event(normalized_event)
    else:
        raise ValueError(f"Unsupported provider: {normalized_event.provider}")


def _handle_slack_event(event: NormalizedEvent) -> Dict[str, Any]:
    """
    Handle Slack events by calling appropriate ACI actions.
    
    Args:
        event: Normalized Slack event
        
    Returns:
        Processing result
    """
    if event.type == "slack.message":
        # TODO: Call ACI Slack function to process the message
        # Example: Could trigger sentiment analysis, auto-responses, etc.
        
        # Mock implementation - replace with actual ACI function call
        return {
            "action": "slack_message_processed",
            "channel_id": event.data.get("channel_id"),
            "user_id": event.data.get("user_id"),
            "message_text": event.data.get("text"),
            "processed_actions": [
                "sentiment_analysis",
                "keyword_extraction"
            ]
        }
        
    elif event.type.startswith("slack.channel"):
        # TODO: Call ACI Slack function for channel events
        # Example: Update internal channel registry, notify admins, etc.
        
        return {
            "action": "slack_channel_event_processed",
            "event_type": event.type,
            "channel_id": event.data.get("channel_id"),
            "channel_name": event.data.get("channel_name")
        }
    
    else:
        logger.warning(f"Unhandled Slack event type: {event.type}")
        return {"action": "no_action", "reason": f"unhandled_event_type: {event.type}"}


def _handle_hubspot_event(event: NormalizedEvent) -> Dict[str, Any]:
    """
    Handle HubSpot events by calling appropriate ACI actions.
    
    Args:
        event: Normalized HubSpot event
        
    Returns:
        Processing result
    """
    if event.type == "hubspot.contact.propertyChange":
        # TODO: Call ACI HubSpot function to process contact changes
        # Example: Sync to other systems, trigger workflows, etc.
        
        return {
            "action": "hubspot_contact_updated",
            "object_id": event.data.get("object_id"),
            "property_name": event.data.get("property_name"),
            "property_value": event.data.get("property_value"),
            "processed_actions": [
                "sync_to_crm",
                "update_lead_score"
            ]
        }
        
    elif event.type.startswith("hubspot.deal"):
        # TODO: Call ACI HubSpot function for deal events
        # Example: Update pipeline status, notify sales team, etc.
        
        return {
            "action": "hubspot_deal_event_processed",
            "event_type": event.type,
            "object_id": event.data.get("object_id")
        }
    
    else:
        logger.warning(f"Unhandled HubSpot event type: {event.type}")
        return {"action": "no_action", "reason": f"unhandled_event_type: {event.type}"}


def _handle_gmail_event(event: NormalizedEvent) -> Dict[str, Any]:
    """
    Handle Gmail events by calling appropriate ACI actions.
    
    Args:
        event: Normalized Gmail event
        
    Returns:
        Processing result
    """
    if event.type == "gmail.history":
        # TODO: Call Gmail History API to get actual changes
        # Then call appropriate ACI Gmail functions based on the changes
        # Example: Process new emails, handle label changes, etc.
        
        email_address = event.data.get("email_address")
        history_id = event.data.get("history_id")
        
        # Mock implementation - replace with actual Gmail History API call
        return {
            "action": "gmail_history_processed",
            "email_address": email_address,
            "history_id": history_id,
            "changes_detected": [
                "new_messages",
                "message_labels_changed"
            ],
            "processed_actions": [
                "email_classification", 
                "auto_reply_check"
            ]
        }
    
    else:
        logger.warning(f"Unhandled Gmail event type: {event.type}")
        return {"action": "no_action", "reason": f"unhandled_event_type: {event.type}"}


def _handle_github_event(event: NormalizedEvent) -> Dict[str, Any]:
    """Handle GitHub events by calling appropriate ACI actions."""
    if event.type == "github.push":
        return {
            "action": "github_push_processed",
            "repository": event.data.get("repository"),
            "event_type": event.data.get("event_type"),
            "sender": event.data.get("sender"),
            "processed_actions": ["code_analysis", "ci_trigger"]
        }
    elif event.type.startswith("github.issues"):
        return {
            "action": "github_issue_processed",
            "repository": event.data.get("repository"),
            "action_type": event.data.get("action"),
            "processed_actions": ["issue_classification", "auto_assignment"]
        }
    else:
        logger.warning(f"Unhandled GitHub event type: {event.type}")
        return {"action": "no_action", "reason": f"unhandled_event_type: {event.type}"}


def _handle_stripe_event(event: NormalizedEvent) -> Dict[str, Any]:
    """Handle Stripe events by calling appropriate ACI actions."""
    if event.type.startswith("stripe.payment_intent"):
        return {
            "action": "stripe_payment_processed",
            "object_id": event.data.get("object_id"),
            "object_type": event.data.get("object_type"),
            "processed_actions": ["payment_tracking", "customer_notification"]
        }
    elif event.type.startswith("stripe.customer"):
        return {
            "action": "stripe_customer_processed",
            "object_id": event.data.get("object_id"),
            "processed_actions": ["customer_sync", "profile_update"]
        }
    else:
        logger.warning(f"Unhandled Stripe event type: {event.type}")
        return {"action": "no_action", "reason": f"unhandled_event_type: {event.type}"}


def _handle_linear_event(event: NormalizedEvent) -> Dict[str, Any]:
    """Handle Linear events by calling appropriate ACI actions."""
    if event.type.startswith("linear.issue"):
        return {
            "action": "linear_issue_processed",
            "object_id": event.data.get("object_id"),
            "action_type": event.data.get("action"),
            "team_id": event.data.get("team_id"),
            "processed_actions": ["task_tracking", "progress_update"]
        }
    else:
        logger.warning(f"Unhandled Linear event type: {event.type}")
        return {"action": "no_action", "reason": f"unhandled_event_type: {event.type}"}


def _handle_discord_event(event: NormalizedEvent) -> Dict[str, Any]:
    """Handle Discord events by calling appropriate ACI actions."""
    if event.type == "discord.message_create":
        return {
            "action": "discord_message_processed",
            "guild_id": event.data.get("guild_id"),
            "channel_id": event.data.get("channel_id"),
            "user_id": event.data.get("user_id"),
            "processed_actions": ["content_moderation", "bot_response"]
        }
    else:
        logger.warning(f"Unhandled Discord event type: {event.type}")
        return {"action": "no_action", "reason": f"unhandled_event_type: {event.type}"}


def _handle_shopify_event(event: NormalizedEvent) -> Dict[str, Any]:
    """Handle Shopify events by calling appropriate ACI actions."""
    if event.type.startswith("shopify.orders"):
        return {
            "action": "shopify_order_processed",
            "object_id": event.data.get("object_id"),
            "shop_domain": event.data.get("shop_domain"),
            "topic": event.data.get("topic"),
            "processed_actions": ["inventory_update", "fulfillment_trigger"]
        }
    elif event.type.startswith("shopify.customers"):
        return {
            "action": "shopify_customer_processed",
            "object_id": event.data.get("object_id"),
            "processed_actions": ["customer_sync", "marketing_automation"]
        }
    else:
        logger.warning(f"Unhandled Shopify event type: {event.type}")
        return {"action": "no_action", "reason": f"unhandled_event_type: {event.type}"}


def _handle_twilio_event(event: NormalizedEvent) -> Dict[str, Any]:
    """Handle Twilio events by calling appropriate ACI actions."""
    if event.type.startswith("twilio.sms"):
        return {
            "action": "twilio_sms_processed",
            "message_sid": event.data.get("message_sid"),
            "status": event.data.get("status"),
            "from": event.data.get("from"),
            "to": event.data.get("to"),
            "processed_actions": ["delivery_tracking", "response_automation"]
        }
    elif event.type.startswith("twilio.voice"):
        return {
            "action": "twilio_voice_processed",
            "message_sid": event.data.get("message_sid"),
            "status": event.data.get("status"),
            "processed_actions": ["call_logging", "analytics_update"]
        }
    else:
        logger.warning(f"Unhandled Twilio event type: {event.type}")
        return {"action": "no_action", "reason": f"unhandled_event_type: {event.type}"}


def create_worker() -> Worker:
    """
    Create and configure an RQ worker for the triggers queue.
    
    Returns:
        Configured RQ Worker instance
    """
    redis_conn = Redis.from_url(settings.redis_url)
    
    worker = Worker(
        queues=["triggers"],
        connection=redis_conn,
        name="triggers-worker"
    )
    
    return worker


def run_worker() -> None:
    """
    Run the triggers worker.
    
    This function can be called from a CLI command or Docker container
    to start processing background jobs.
    """
    logger.info("Starting triggers worker...")
    
    worker = create_worker()
    
    # Register exception handler
    def exception_handler(job, exc_type, exc_value, traceback):
        logger.error(
            f"Job {job.id} failed with {exc_type.__name__}: {exc_value}",
            exc_info=(exc_type, exc_value, traceback)
        )
    
    worker.push_exc_handler(exception_handler)
    
    try:
        worker.work(with_scheduler=True)
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Worker crashed: {e}")
        raise


if __name__ == "__main__":
    # Allow running worker directly: python -m aci.triggers.worker
    run_worker()