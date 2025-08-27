"""Isolated tests for triggers verification utilities (no external dependencies)."""

import json
import time
import base64
import pytest

from ..verify import (
    verify_slack_webhook,
    verify_hubspot_webhook,
    verify_google_pubsub_token,
    decode_pubsub_message,
    SlackVerificationError,
    HubSpotVerificationError,
    GooglePubSubVerificationError
)
from ..normalize import (
    normalize_slack_event,
    normalize_hubspot_event,
    normalize_gmail_event,
    get_event_id_for_provider
)
from ..models import WebhookProvider
from .conftest import create_slack_signature, create_hubspot_signature


class TestSlackVerificationIsolated:
    """Test Slack verification without external dependencies."""
    
    def test_valid_slack_signature(self):
        """Test valid Slack signature verification."""
        secret = "test_secret_123"
        timestamp = str(int(time.time()))
        payload = '{"test": "data"}'
        signature = create_slack_signature(payload, timestamp, secret)
        
        result = verify_slack_webhook(signature, timestamp, payload.encode(), secret)
        assert result is True
    
    def test_invalid_slack_signature(self):
        """Test invalid Slack signature rejection."""
        secret = "test_secret_123"
        timestamp = str(int(time.time()))
        payload = '{"test": "data"}'
        
        result = verify_slack_webhook("v0=invalid", timestamp, payload.encode(), secret)
        assert result is False
    
    def test_slack_replay_protection(self):
        """Test replay attack protection."""
        secret = "test_secret_123"
        old_timestamp = str(int(time.time()) - 600)  # 10 minutes ago
        payload = '{"test": "data"}'
        signature = create_slack_signature(payload, old_timestamp, secret)
        
        with pytest.raises(SlackVerificationError, match="timestamp too old"):
            verify_slack_webhook(signature, old_timestamp, payload.encode(), secret)


class TestHubSpotVerificationIsolated:
    """Test HubSpot verification without external dependencies."""
    
    def test_valid_hubspot_signature(self):
        """Test valid HubSpot v3 signature verification."""
        secret = "test_hubspot_secret"
        timestamp = str(int(time.time() * 1000))
        method = "POST"
        uri = "/webhooks/hubspot"
        body = '{"test": "data"}'
        
        signature = create_hubspot_signature(method, uri, body, timestamp, secret)
        
        result = verify_hubspot_webhook(
            signature, timestamp, method, uri, body.encode(), secret
        )
        assert result is True
    
    def test_invalid_hubspot_signature(self):
        """Test invalid HubSpot signature rejection."""
        secret = "test_hubspot_secret"
        timestamp = str(int(time.time() * 1000))
        method = "POST"
        uri = "/webhooks/hubspot"
        body = '{"test": "data"}'
        
        result = verify_hubspot_webhook(
            "invalid_signature", timestamp, method, uri, body.encode(), secret
        )
        assert result is False


class TestGmailVerificationIsolated:
    """Test Gmail verification without external dependencies."""
    
    def test_decode_pubsub_message(self):
        """Test base64 message decoding."""
        message = {"emailAddress": "test@example.com", "historyId": "12345"}
        message_json = json.dumps(message)
        message_b64 = base64.b64encode(message_json.encode()).decode()
        
        decoded = decode_pubsub_message(message_b64)
        assert decoded == message
    
    def test_decode_invalid_base64(self):
        """Test invalid base64 handling."""
        with pytest.raises(GooglePubSubVerificationError):
            decode_pubsub_message("invalid_base64!")


class TestNormalizationIsolated:
    """Test event normalization without external dependencies."""
    
    def test_normalize_slack_message(self):
        """Test Slack message normalization."""
        payload = {
            "type": "event_callback",
            "event": {
                "type": "message",
                "channel": "C123456",
                "user": "U123456",
                "text": "Hello!",
                "ts": "1234567890.123456",
                "event_ts": "1234567890.123456"
            },
            "team_id": "T123456"
        }
        
        events = normalize_slack_event(payload)
        assert len(events) == 1
        
        event = events[0]
        assert event.provider == "slack"
        assert event.type == "slack.message"
        assert event.subject_id == "C123456:U123456"
        assert event.data["text"] == "Hello!"
    
    def test_normalize_hubspot_contact(self):
        """Test HubSpot contact normalization."""
        payload = {
            "eventId": "12345",
            "subscriptionType": "contact.propertyChange",
            "objectId": "67890",
            "occurredAt": int(time.time() * 1000),
            "propertyName": "email",
            "propertyValue": "test@example.com"
        }
        
        events = normalize_hubspot_event(payload)
        assert len(events) == 1
        
        event = events[0]
        assert event.provider == "hubspot"
        assert event.type == "hubspot.contact.propertyChange"
        assert event.subject_id == "67890"
        assert event.data["property_name"] == "email"
    
    def test_normalize_gmail_history(self):
        """Test Gmail history normalization."""
        payload = {
            "emailAddress": "test@example.com",
            "historyId": "12345678"
        }
        
        events = normalize_gmail_event(payload)
        assert len(events) == 1
        
        event = events[0]
        assert event.provider == "gmail"
        assert event.type == "gmail.history"
        assert event.subject_id == "test@example.com"
        assert event.data["history_id"] == "12345678"
    
    def test_get_event_id_slack(self):
        """Test Slack event ID extraction."""
        payload = {
            "type": "event_callback",
            "event": {"event_ts": "1234567890.123456"}
        }
        
        event_id = get_event_id_for_provider(WebhookProvider.SLACK, payload)
        assert event_id == "1234567890.123456"
    
    def test_get_event_id_hubspot(self):
        """Test HubSpot event ID extraction."""
        payload = {"eventId": "hub12345"}
        
        event_id = get_event_id_for_provider(WebhookProvider.HUBSPOT, payload)
        assert event_id == "hub12345"
    
    def test_get_event_id_gmail(self):
        """Test Gmail event ID extraction."""
        payload = {
            "emailAddress": "test@example.com",
            "historyId": "12345678"
        }
        
        event_id = get_event_id_for_provider(WebhookProvider.GMAIL, payload)
        assert event_id == "test@example.com:12345678"