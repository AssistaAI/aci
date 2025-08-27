"""Shared test fixtures for triggers module tests."""

import json
import time
import hashlib
import hmac
import base64
from datetime import datetime
from typing import Dict, Any
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from ..models import Base, IncomingEvent, WebhookProvider


@pytest.fixture
def db_session():
    """Create test database session."""
    # Use PostgreSQL-compatible connection (the tests run with PostgreSQL service)
    import os
    database_url = os.getenv("TRIGGERS_DATABASE_URL", "sqlite:///:memory:")
    
    if database_url.startswith("postgresql"):
        # Use PostgreSQL if available
        engine = create_engine(database_url)
    else:
        # Fallback to SQLite with JSON instead of JSONB
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        
        # Monkey patch JSONB to JSON for SQLite compatibility
        import sqlalchemy.dialects.postgresql as postgresql
        from sqlalchemy import JSON
        postgresql.JSONB = JSON
    
    # Create tables
    Base.metadata.create_all(engine)
    
    # Create session
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        yield session
    finally:
        # Clean up all data after each test
        session.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        session.close()


@pytest.fixture
def slack_signing_secret():
    """Slack signing secret for testing."""
    return "test_slack_secret_123"


@pytest.fixture
def hubspot_app_secret():
    """HubSpot app secret for testing."""
    return "test_hubspot_secret_456"


@pytest.fixture
def current_timestamp():
    """Current timestamp for testing."""
    return str(int(time.time()))


@pytest.fixture
def slack_message_payload():
    """Sample Slack message event payload."""
    return {
        "token": "verification_token",
        "team_id": "T1234567890",
        "api_app_id": "A1234567890",
        "event": {
            "type": "message",
            "channel": "C1234567890",
            "user": "U1234567890", 
            "text": "Hello, world!",
            "ts": "1234567890.123456",
            "event_ts": "1234567890.123456"
        },
        "type": "event_callback",
        "event_id": "Ev1234567890",
        "event_time": 1234567890
    }


@pytest.fixture
def slack_url_verification_payload():
    """Slack URL verification challenge payload."""
    return {
        "token": "verification_token",
        "challenge": "test_challenge_string",
        "type": "url_verification"
    }


@pytest.fixture
def hubspot_contact_event():
    """Sample HubSpot contact property change event."""
    return {
        "eventId": "12345",
        "subscriptionId": "67890",
        "portalId": "123456",
        "occurredAt": int(time.time() * 1000),  # HubSpot uses milliseconds
        "subscriptionType": "contact.propertyChange",
        "objectId": "987654321",
        "propertyName": "email",
        "propertyValue": "test@example.com"
    }


@pytest.fixture
def hubspot_batched_events(hubspot_contact_event):
    """Sample HubSpot batched events payload."""
    event1 = hubspot_contact_event.copy()
    event1["eventId"] = "12345"
    event1["objectId"] = "111111111"
    
    event2 = hubspot_contact_event.copy()
    event2["eventId"] = "12346"
    event2["objectId"] = "222222222"
    event2["propertyName"] = "firstname"
    event2["propertyValue"] = "John"
    
    return [event1, event2]


@pytest.fixture
def gmail_pubsub_message():
    """Sample Gmail Pub/Sub message payload."""
    return {
        "emailAddress": "user@example.com",
        "historyId": "12345678"
    }


@pytest.fixture
def gmail_pubsub_envelope(gmail_pubsub_message):
    """Sample Gmail Pub/Sub envelope with base64-encoded message."""
    message_json = json.dumps(gmail_pubsub_message)
    message_b64 = base64.b64encode(message_json.encode()).decode()
    
    return {
        "message": {
            "data": message_b64,
            "messageId": "message_id_123",
            "message_id": "message_id_123",
            "publishTime": "2023-01-01T00:00:00.000Z",
            "publish_time": "2023-01-01T00:00:00.000Z"
        },
        "subscription": "projects/test-project/subscriptions/test-subscription"
    }


def create_slack_signature(payload: str, timestamp: str, secret: str) -> str:
    """Create valid Slack signature for testing."""
    base_string = f"v0:{timestamp}:{payload}"
    signature = hmac.new(
        secret.encode(),
        base_string.encode(),
        hashlib.sha256
    ).hexdigest()
    return f"v0={signature}"


def create_hubspot_signature(
    method: str, 
    uri: str, 
    body: str, 
    timestamp: str, 
    secret: str
) -> str:
    """Create valid HubSpot v3 signature for testing."""
    canonical_string = method + uri + body + timestamp
    signature = hmac.new(
        secret.encode(),
        canonical_string.encode(),
        hashlib.sha256
    ).hexdigest()
    return signature


@pytest.fixture
def valid_slack_headers(slack_message_payload, current_timestamp, slack_signing_secret):
    """Create valid Slack webhook headers."""
    payload_str = json.dumps(slack_message_payload, separators=(',', ':'))
    signature = create_slack_signature(payload_str, current_timestamp, slack_signing_secret)
    
    return {
        "X-Slack-Signature": signature,
        "X-Slack-Request-Timestamp": current_timestamp,
        "Content-Type": "application/json"
    }


@pytest.fixture  
def valid_hubspot_headers(hubspot_contact_event, hubspot_app_secret):
    """Create valid HubSpot webhook headers."""
    timestamp = str(int(time.time() * 1000))  # HubSpot uses milliseconds
    payload_str = json.dumps(hubspot_contact_event, separators=(',', ':'))
    signature = create_hubspot_signature("POST", "/webhooks/hubspot", payload_str, timestamp, hubspot_app_secret)
    
    return {
        "X-HubSpot-Signature-V3": signature,
        "X-HubSpot-Request-Timestamp": timestamp,
        "Content-Type": "application/json"
    }


@pytest.fixture
def mock_jwt_token():
    """Mock JWT token for testing (not cryptographically valid)."""
    # This is a mock token for testing - in production, use proper JWT validation
    header = {"typ": "JWT", "alg": "RS256"}
    payload = {
        "iss": "https://accounts.google.com",
        "aud": "https://mydomain.com/webhooks/gmail/pubsub",
        "exp": int(time.time()) + 3600,  # Expires in 1 hour
        "iat": int(time.time())
    }
    
    # Create mock token (not cryptographically valid)
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
    signature_b64 = "mock_signature"
    
    return f"{header_b64}.{payload_b64}.{signature_b64}"


@pytest.fixture
def invalid_slack_signature():
    """Invalid Slack signature for testing."""
    return "v0=invalid_signature_hash"


@pytest.fixture
def expired_timestamp():
    """Expired timestamp (older than 5 minutes)."""
    return str(int(time.time()) - 400)  # 400 seconds ago


@pytest.fixture
def sample_incoming_event(db_session):
    """Create a sample IncomingEvent in the database."""
    event = IncomingEvent(
        provider=WebhookProvider.SLACK,
        event_id="test_event_123",
        signature_valid=True,
        payload={"test": "data"},
        processed=False
    )
    
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    return event