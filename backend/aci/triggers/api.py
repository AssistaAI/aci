"""FastAPI routes for webhook endpoints."""

import json
from typing import Annotated, Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Import from existing ACI modules
from aci.server import dependencies as deps

from .models import IncomingEvent, WebhookProvider
from .settings import settings
from .verify import (
    verify_slack_webhook,
    verify_hubspot_webhook,
    verify_google_pubsub_token,
    verify_github_webhook,
    verify_stripe_webhook,
    verify_linear_webhook,
    verify_discord_webhook,
    verify_shopify_webhook,
    verify_twilio_webhook,
    decode_pubsub_message,
    SlackVerificationError,
    HubSpotVerificationError,
    GooglePubSubVerificationError,
    GitHubVerificationError,
    StripeVerificationError,
    LinearVerificationError,
    DiscordVerificationError,
    ShopifyVerificationError,
    TwilioVerificationError
)
from .normalize import normalize_webhook_payload, get_event_id_for_provider
from .queue import enqueue_multiple_events
from .logging import (
    log_webhook_received,
    log_webhook_verified,
    log_webhook_verification_failed,
    get_triggers_logger
)

# Create router instance
router = APIRouter()
logger = get_triggers_logger()


@router.post("/slack/events", status_code=status.HTTP_200_OK)
async def handle_slack_webhook(
    request: Request,
    response: Response,
    db_session: Annotated[Session, Depends(deps.yield_db_session)]
) -> Dict[str, Any]:
    """
    Handle Slack Events API webhooks.
    
    Supports:
    - URL verification challenges
    - Event callbacks with signature verification
    - Idempotency protection
    - Background job enqueueing
    """
    headers = request.headers
    body = await request.body()
    
    # Parse JSON payload
    try:
        payload = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Invalid JSON payload from Slack: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    
    log_webhook_received(
        provider="slack",
        event_id=payload.get("event_id"),
        payload_type=payload.get("type")
    )
    
    # Handle URL verification challenge
    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        if not challenge:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing challenge parameter"
            )
        
        logger.info("Slack URL verification challenge received")
        return {"challenge": challenge}
    
    # Verify webhook signature for all other events
    slack_signature = headers.get("X-Slack-Signature")
    slack_timestamp = headers.get("X-Slack-Request-Timestamp")
    
    if not slack_signature or not slack_timestamp:
        log_webhook_verification_failed(
            "slack",
            "missing_headers", 
            has_signature=bool(slack_signature),
            has_timestamp=bool(slack_timestamp)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required headers"
        )
    
    try:
        is_valid = verify_slack_webhook(
            signature=slack_signature,
            timestamp=slack_timestamp,
            body=body
        )
        
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature"
            )
            
    except SlackVerificationError as e:
        logger.warning(f"Slack webhook verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    
    # Extract event ID for idempotency
    event_id = get_event_id_for_provider(WebhookProvider.SLACK, payload)
    if not event_id:
        logger.warning("Could not extract event ID from Slack payload")
        # Generate a fallback ID
        event_id = f"slack-{slack_timestamp}"
    
    # Store in database with idempotency protection
    try:
        incoming_event = IncomingEvent(
            provider=WebhookProvider.SLACK,
            event_id=event_id,
            signature_valid=True,
            payload=payload,
            processed=False
        )
        
        db_session.add(incoming_event)
        db_session.commit()
        
        logger.info(f"Stored Slack event in database: {event_id}")
        
    except IntegrityError:
        # Event already exists - this is expected for duplicate webhooks
        db_session.rollback()
        logger.info(f"Slack event already exists, skipping: {event_id}")
        return {"status": "ok", "message": "Event already processed"}
    
    # Normalize and enqueue for background processing
    try:
        normalized_events = normalize_webhook_payload(WebhookProvider.SLACK, payload)
        
        if normalized_events:
            jobs = enqueue_multiple_events(normalized_events)
            logger.info(f"Enqueued {len(jobs)} Slack events for processing")
            
            # Mark as processed
            incoming_event.processed = True
            db_session.commit()
    
    except Exception as e:
        logger.error(f"Failed to process Slack webhook: {e}")
        # Don't return error - we've stored the event and can retry later
    
    return {"status": "ok"}


@router.post("/hubspot", status_code=status.HTTP_200_OK)
async def handle_hubspot_webhook(
    request: Request,
    response: Response,
    db_session: Annotated[Session, Depends(deps.yield_db_session)]
) -> Dict[str, Any]:
    """
    Handle HubSpot v3 webhooks.
    
    Supports:
    - v3 signature verification
    - Batched events processing
    - Idempotency protection
    - Background job enqueueing
    """
    headers = request.headers
    body = await request.body()
    
    # Parse JSON payload
    try:
        payload = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Invalid JSON payload from HubSpot: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    
    log_webhook_received(
        provider="hubspot",
        event_count=len(payload) if isinstance(payload, list) else 1
    )
    
    # Verify webhook signature
    hubspot_signature = headers.get("X-HubSpot-Signature-V3")
    hubspot_timestamp = headers.get("X-HubSpot-Request-Timestamp")
    
    if not hubspot_signature or not hubspot_timestamp:
        log_webhook_verification_failed(
            "hubspot",
            "missing_headers",
            has_signature=bool(hubspot_signature),
            has_timestamp=bool(hubspot_timestamp)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required headers"
        )
    
    try:
        is_valid = verify_hubspot_webhook(
            signature=hubspot_signature,
            timestamp=hubspot_timestamp,
            method=request.method,
            uri=str(request.url.path),
            body=body
        )
        
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature"
            )
            
    except HubSpotVerificationError as e:
        logger.warning(f"HubSpot webhook verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    
    # Process events (HubSpot can send batched events)
    events_processed = 0
    events_skipped = 0
    
    # Ensure payload is a list for consistent processing
    event_list = payload if isinstance(payload, list) else [payload]
    
    for event_data in event_list:
        event_id = event_data.get("eventId")
        if not event_id:
            logger.warning("HubSpot event missing eventId, skipping")
            continue
        
        # Store in database with idempotency protection
        try:
            incoming_event = IncomingEvent(
                provider=WebhookProvider.HUBSPOT,
                event_id=event_id,
                signature_valid=True,
                payload=event_data,
                processed=False
            )
            
            db_session.add(incoming_event)
            db_session.commit()
            
            logger.info(f"Stored HubSpot event in database: {event_id}")
            
            # Normalize and enqueue for background processing
            try:
                normalized_events = normalize_webhook_payload(
                    WebhookProvider.HUBSPOT, 
                    event_data
                )
                
                if normalized_events:
                    jobs = enqueue_multiple_events(normalized_events)
                    logger.info(f"Enqueued {len(jobs)} HubSpot events for processing")
                    
                    # Mark as processed
                    incoming_event.processed = True
                    db_session.commit()
                    events_processed += 1
                    
            except Exception as e:
                logger.error(f"Failed to process HubSpot event {event_id}: {e}")
                # Continue processing other events
        
        except IntegrityError:
            # Event already exists
            db_session.rollback()
            logger.info(f"HubSpot event already exists, skipping: {event_id}")
            events_skipped += 1
    
    return {
        "status": "ok",
        "events_processed": events_processed,
        "events_skipped": events_skipped
    }


@router.post("/gmail/pubsub", status_code=status.HTTP_200_OK)
async def handle_gmail_pubsub_webhook(
    request: Request,
    response: Response,
    db_session: Annotated[Session, Depends(deps.yield_db_session)]
) -> Dict[str, Any]:
    """
    Handle Google Pub/Sub push notifications for Gmail.
    
    Supports:
    - OIDC JWT token verification
    - Base64 message decoding
    - History ID extraction
    - Background job enqueueing
    """
    headers = request.headers
    body = await request.body()
    
    # Parse JSON payload
    try:
        pubsub_envelope = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Invalid JSON payload from Gmail Pub/Sub: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    
    log_webhook_received(
        provider="gmail",
        subscription=pubsub_envelope.get("subscription")
    )
    
    # Verify OIDC JWT token
    authorization_header = headers.get("Authorization")
    if not authorization_header:
        log_webhook_verification_failed("gmail", "missing_authorization_header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header"
        )
    
    try:
        jwt_payload = verify_google_pubsub_token(authorization_header)
        logger.info("Gmail Pub/Sub JWT token verified successfully")
        
    except GooglePubSubVerificationError as e:
        logger.warning(f"Gmail Pub/Sub token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    
    # Extract and decode the message
    message = pubsub_envelope.get("message", {})
    message_data = message.get("data")
    
    if not message_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing message data"
        )
    
    try:
        decoded_message = decode_pubsub_message(message_data)
    except GooglePubSubVerificationError as e:
        logger.error(f"Failed to decode Gmail Pub/Sub message: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # Extract event ID for idempotency
    email_address = decoded_message.get("emailAddress")
    history_id = decoded_message.get("historyId")
    
    if not email_address or not history_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing emailAddress or historyId"
        )
    
    event_id = f"{email_address}:{history_id}"
    
    # Store in database with idempotency protection
    try:
        incoming_event = IncomingEvent(
            provider=WebhookProvider.GMAIL,
            event_id=event_id,
            signature_valid=True,  # JWT verification passed
            payload=decoded_message,
            processed=False
        )
        
        db_session.add(incoming_event)
        db_session.commit()
        
        logger.info(f"Stored Gmail event in database: {event_id}")
        
    except IntegrityError:
        # Event already exists
        db_session.rollback()
        logger.info(f"Gmail event already exists, skipping: {event_id}")
        return {"status": "ok", "message": "Event already processed"}
    
    # Normalize and enqueue for background processing
    try:
        normalized_events = normalize_webhook_payload(
            WebhookProvider.GMAIL, 
            decoded_message
        )
        
        if normalized_events:
            jobs = enqueue_multiple_events(normalized_events)
            logger.info(f"Enqueued {len(jobs)} Gmail events for processing")
            
            # Mark as processed
            incoming_event.processed = True
            db_session.commit()
    
    except Exception as e:
        logger.error(f"Failed to process Gmail webhook: {e}")
        # Don't return error - we've stored the event and can retry later
    
    return {"status": "ok"}


@router.post("/github", status_code=status.HTTP_200_OK)
async def handle_github_webhook(
    request: Request,
    response: Response,
    db_session: Annotated[Session, Depends(deps.yield_db_session)]
) -> Dict[str, Any]:
    """Handle GitHub webhooks with signature verification."""
    headers = request.headers
    body = await request.body()
    
    try:
        payload = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    # Add GitHub headers to payload for normalization
    payload["_event_type"] = headers.get("X-GitHub-Event")
    payload["_delivery_id"] = headers.get("X-GitHub-Delivery")
    
    log_webhook_received(provider="github", event_type=payload.get("_event_type"))
    
    signature = headers.get("X-Hub-Signature-256")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature header")
    
    try:
        if not verify_github_webhook(signature, body):
            raise HTTPException(status_code=401, detail="Invalid signature")
    except GitHubVerificationError as e:
        raise HTTPException(status_code=401, detail=str(e))
    
    return await process_webhook(WebhookProvider.GITHUB, payload, db_session)


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def handle_stripe_webhook(
    request: Request,
    response: Response,
    db_session: Annotated[Session, Depends(deps.yield_db_session)]
) -> Dict[str, Any]:
    """Handle Stripe webhooks with signature verification."""
    headers = request.headers
    body = await request.body()
    
    try:
        payload = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    log_webhook_received(provider="stripe", event_type=payload.get("type"))
    
    signature = headers.get("Stripe-Signature")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature header")
    
    # Extract timestamp from signature for verification
    timestamp = signature.split(',')[0].split('=')[1] if 't=' in signature else ""
    
    try:
        if not verify_stripe_webhook(signature, timestamp, body):
            raise HTTPException(status_code=401, detail="Invalid signature")
    except StripeVerificationError as e:
        raise HTTPException(status_code=401, detail=str(e))
    
    return await process_webhook(WebhookProvider.STRIPE, payload, db_session)


@router.post("/linear", status_code=status.HTTP_200_OK)
async def handle_linear_webhook(
    request: Request,
    response: Response,
    db_session: Annotated[Session, Depends(deps.yield_db_session)]
) -> Dict[str, Any]:
    """Handle Linear webhooks with signature verification."""
    headers = request.headers
    body = await request.body()
    
    try:
        payload = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    log_webhook_received(provider="linear", event_type=payload.get("type"))
    
    signature = headers.get("Linear-Signature")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature header")
    
    try:
        if not verify_linear_webhook(signature, body):
            raise HTTPException(status_code=401, detail="Invalid signature")
    except LinearVerificationError as e:
        raise HTTPException(status_code=401, detail=str(e))
    
    return await process_webhook(WebhookProvider.LINEAR, payload, db_session)


@router.post("/shopify", status_code=status.HTTP_200_OK)
async def handle_shopify_webhook(
    request: Request,
    response: Response,
    db_session: Annotated[Session, Depends(deps.yield_db_session)]
) -> Dict[str, Any]:
    """Handle Shopify webhooks with signature verification."""
    headers = request.headers
    body = await request.body()
    
    try:
        payload = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    # Add Shopify headers to payload for normalization
    payload["_topic"] = headers.get("X-Shopify-Topic")
    payload["_shop_domain"] = headers.get("X-Shopify-Shop-Domain")
    
    log_webhook_received(provider="shopify", topic=payload.get("_topic"))
    
    signature = headers.get("X-Shopify-Hmac-Sha256")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature header")
    
    try:
        if not verify_shopify_webhook(signature, body):
            raise HTTPException(status_code=401, detail="Invalid signature")
    except ShopifyVerificationError as e:
        raise HTTPException(status_code=401, detail=str(e))
    
    return await process_webhook(WebhookProvider.SHOPIFY, payload, db_session)


async def process_webhook(
    provider: WebhookProvider,
    payload: Dict[str, Any],
    db_session: Session
) -> Dict[str, Any]:
    """Generic webhook processing helper."""
    event_id = get_event_id_for_provider(provider, payload)
    if not event_id:
        event_id = f"{provider.value}-{hash(str(payload))}"
    
    try:
        incoming_event = IncomingEvent(
            provider=provider,
            event_id=event_id,
            signature_valid=True,
            payload=payload,
            processed=False
        )
        
        db_session.add(incoming_event)
        db_session.commit()
        
        # Normalize and enqueue
        normalized_events = normalize_webhook_payload(provider, payload)
        if normalized_events:
            jobs = enqueue_multiple_events(normalized_events)
            incoming_event.processed = True
            db_session.commit()
        
        return {"status": "ok"}
        
    except IntegrityError:
        db_session.rollback()
        return {"status": "ok", "message": "Event already processed"}
    except Exception as e:
        logger.error(f"Failed to process {provider.value} webhook: {e}")
        return {"status": "ok"}


# Health check endpoint for the triggers module
@router.get("/health", status_code=status.HTTP_200_OK)
async def triggers_health_check() -> Dict[str, Any]:
    """Health check endpoint for triggers module."""
    try:
        # Check Redis connection
        from .queue import get_redis_connection, get_queue_stats
        
        redis_conn = get_redis_connection()
        redis_conn.ping()
        
        queue_stats = get_queue_stats()
        
        return {
            "status": "healthy",
            "redis_connected": True,
            "queue_stats": queue_stats
        }
        
    except Exception as e:
        logger.error(f"Triggers health check failed: {e}")
        return {
            "status": "unhealthy", 
            "error": str(e),
            "redis_connected": False
        }