"""Structured logging utilities for the triggers module."""

from typing import Any, Dict

from aci.common.logging_setup import get_logger

logger = get_logger(__name__)


def log_webhook_received(provider: str, event_id: str | None = None, **kwargs: Any) -> None:
    """Log webhook received with structured data."""
    log_data = {
        "event": "webhook_received",
        "provider": provider,
        "event_id": event_id,
        **kwargs
    }
    logger.info("Webhook received", extra=log_data)


def log_webhook_verified(provider: str, event_id: str | None = None, **kwargs: Any) -> None:
    """Log successful webhook verification with structured data."""
    log_data = {
        "event": "webhook_verified", 
        "provider": provider,
        "event_id": event_id,
        **kwargs
    }
    logger.info("Webhook signature verified", extra=log_data)


def log_webhook_verification_failed(
    provider: str, 
    reason: str,
    event_id: str | None = None, 
    **kwargs: Any
) -> None:
    """Log failed webhook verification with structured data."""
    log_data = {
        "event": "webhook_verification_failed",
        "provider": provider, 
        "reason": reason,
        "event_id": event_id,
        **kwargs
    }
    logger.warning("Webhook verification failed", extra=log_data)


def log_event_normalized(
    provider: str,
    event_type: str, 
    event_id: str | None = None,
    **kwargs: Any
) -> None:
    """Log event normalization with structured data."""
    log_data = {
        "event": "event_normalized",
        "provider": provider,
        "event_type": event_type, 
        "event_id": event_id,
        **kwargs
    }
    logger.info("Event normalized", extra=log_data)


def log_event_enqueued(
    provider: str,
    event_type: str,
    event_id: str | None = None,
    **kwargs: Any
) -> None:
    """Log event enqueued for processing with structured data."""
    log_data = {
        "event": "event_enqueued",
        "provider": provider,
        "event_type": event_type,
        "event_id": event_id,
        **kwargs
    }
    logger.info("Event enqueued for processing", extra=log_data)


def log_event_processing_started(
    provider: str,
    event_type: str, 
    event_id: str | None = None,
    **kwargs: Any
) -> None:
    """Log event processing started with structured data."""
    log_data = {
        "event": "event_processing_started",
        "provider": provider,
        "event_type": event_type,
        "event_id": event_id,
        **kwargs
    }
    logger.info("Event processing started", extra=log_data)


def log_event_processing_completed(
    provider: str,
    event_type: str,
    event_id: str | None = None,
    **kwargs: Any
) -> None:
    """Log event processing completed with structured data."""
    log_data = {
        "event": "event_processing_completed", 
        "provider": provider,
        "event_type": event_type,
        "event_id": event_id,
        **kwargs
    }
    logger.info("Event processing completed", extra=log_data)


def log_event_processing_failed(
    provider: str,
    event_type: str,
    error: str,
    event_id: str | None = None,
    **kwargs: Any
) -> None:
    """Log event processing failure with structured data."""
    log_data = {
        "event": "event_processing_failed",
        "provider": provider, 
        "event_type": event_type,
        "error": error,
        "event_id": event_id,
        **kwargs
    }
    logger.error("Event processing failed", extra=log_data)


def get_triggers_logger() -> Any:
    """Get the triggers module logger."""
    return logger