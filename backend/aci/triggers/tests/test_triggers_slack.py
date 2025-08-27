"""Tests for Slack webhook handling."""

import json
import time
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from ..api import router
from ..verify import verify_slack_webhook, SlackVerificationError
from ..normalize import normalize_slack_event, get_event_id_for_provider
from ..models import WebhookProvider, IncomingEvent
from .conftest import create_slack_signature


# Create test app
app = FastAPI()
app.include_router(router, prefix="/webhooks")
client = TestClient(app)


class TestSlackVerification:
    """Test Slack webhook signature verification."""
    
    def test_valid_slack_signature(self, slack_signing_secret, current_timestamp):
        """Test that valid Slack signature passes verification."""
        payload = '{"test": "data"}'
        signature = create_slack_signature(payload, current_timestamp, slack_signing_secret)
        
        result = verify_slack_webhook(
            signature=signature,
            timestamp=current_timestamp,
            body=payload.encode(),
            signing_secret=slack_signing_secret
        )
        
        assert result is True
    
    def test_invalid_slack_signature(self, slack_signing_secret, current_timestamp):
        """Test that invalid Slack signature fails verification."""
        payload = '{"test": "data"}'
        invalid_signature = "v0=invalid_signature_hash"
        
        result = verify_slack_webhook(
            signature=invalid_signature,
            timestamp=current_timestamp,
            body=payload.encode(),
            signing_secret=slack_signing_secret
        )
        
        assert result is False
    
    def test_replay_attack_protection(self, slack_signing_secret):
        """Test that old timestamps are rejected (replay attack protection)."""
        # Use timestamp from 10 minutes ago
        old_timestamp = str(int(time.time()) - 600)
        payload = '{"test": "data"}'
        signature = create_slack_signature(payload, old_timestamp, slack_signing_secret)
        
        with pytest.raises(SlackVerificationError, match="timestamp too old"):
            verify_slack_webhook(
                signature=signature,
                timestamp=old_timestamp,
                body=payload.encode(),
                signing_secret=slack_signing_secret
            )
    
    def test_invalid_signature_format(self, slack_signing_secret, current_timestamp):
        """Test that invalid signature format is rejected."""
        payload = '{"test": "data"}'
        invalid_format_signature = "invalid_format"
        
        with pytest.raises(SlackVerificationError, match="Invalid signature format"):
            verify_slack_webhook(
                signature=invalid_format_signature,
                timestamp=current_timestamp,
                body=payload.encode(),
                signing_secret=slack_signing_secret
            )
    
    def test_invalid_timestamp_format(self, slack_signing_secret):
        """Test that invalid timestamp format is rejected."""
        payload = '{"test": "data"}'
        signature = "v0=some_signature"
        invalid_timestamp = "not_a_number"
        
        with pytest.raises(SlackVerificationError, match="Invalid timestamp format"):
            verify_slack_webhook(
                signature=signature,
                timestamp=invalid_timestamp,
                body=payload.encode(),
                signing_secret=slack_signing_secret
            )


class TestSlackNormalization:
    """Test Slack event normalization."""
    
    def test_normalize_slack_message_event(self, slack_message_payload):
        """Test normalization of Slack message event."""
        normalized_events = normalize_slack_event(slack_message_payload)
        
        assert len(normalized_events) == 1
        
        event = normalized_events[0]
        assert event.provider == "slack"
        assert event.type == "slack.message"
        assert event.subject_id == "C1234567890:U1234567890"
        assert event.data["channel_id"] == "C1234567890"
        assert event.data["user_id"] == "U1234567890"
        assert event.data["text"] == "Hello, world!"
    
    def test_normalize_url_verification(self, slack_url_verification_payload):
        """Test that URL verification doesn't generate normalized events."""
        normalized_events = normalize_slack_event(slack_url_verification_payload)
        assert len(normalized_events) == 0
    
    def test_normalize_channel_created_event(self):
        """Test normalization of Slack channel created event."""
        channel_event = {
            "type": "event_callback",
            "event": {
                "type": "channel_created",
                "channel": {
                    "id": "C1234567890",
                    "name": "test-channel"
                },
                "event_ts": "1234567890.123456"
            },
            "team_id": "T1234567890"
        }
        
        normalized_events = normalize_slack_event(channel_event)
        
        assert len(normalized_events) == 1
        event = normalized_events[0]
        assert event.type == "slack.channel_created"
        assert event.subject_id == "C1234567890"
        assert event.data["channel_name"] == "test-channel"
    
    def test_get_event_id_for_slack(self, slack_message_payload):
        """Test extracting event ID from Slack payload."""
        event_id = get_event_id_for_provider(WebhookProvider.SLACK, slack_message_payload)
        assert event_id == "1234567890.123456"  # event.event_ts
    
    def test_get_event_id_for_url_verification(self, slack_url_verification_payload):
        """Test extracting event ID from URL verification payload."""
        event_id = get_event_id_for_provider(WebhookProvider.SLACK, slack_url_verification_payload)
        assert event_id is None  # URL verification doesn't have event_id


class TestSlackWebhookEndpoint:
    """Test Slack webhook HTTP endpoint."""
    
    @pytest.fixture(autouse=True)
    def setup_settings(self, monkeypatch, slack_signing_secret):
        """Mock settings for testing."""
        monkeypatch.setattr("aci.triggers.settings.settings.slack_signing_secret", slack_signing_secret)
    
    def test_url_verification_challenge(self, slack_url_verification_payload):
        """Test Slack URL verification challenge response."""
        response = client.post(
            "/webhooks/slack/events",
            json=slack_url_verification_payload,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        assert response.json() == {"challenge": "test_challenge_string"}
    
    def test_valid_message_webhook(
        self, 
        slack_message_payload, 
        valid_slack_headers,
        monkeypatch
    ):
        """Test valid Slack message webhook processing."""
        # Mock database and queue operations
        mock_db_session = type('MockSession', (), {
            'add': lambda self, obj: None,
            'commit': lambda self: None,
            'rollback': lambda self: None
        })()
        
        def mock_yield_db_session():
            return mock_db_session
        
        def mock_enqueue_multiple_events(events):
            return [type('MockJob', (), {'id': 'mock_job_123'})()]
        
        monkeypatch.setattr("aci.triggers.api.deps.yield_db_session", mock_yield_db_session)
        monkeypatch.setattr("aci.triggers.api.enqueue_multiple_events", mock_enqueue_multiple_events)
        
        payload_str = json.dumps(slack_message_payload, separators=(',', ':'))
        
        response = client.post(
            "/webhooks/slack/events",
            content=payload_str,
            headers=valid_slack_headers
        )
        
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    
    def test_invalid_signature_rejected(
        self, 
        slack_message_payload, 
        invalid_slack_signature,
        current_timestamp
    ):
        """Test that invalid signature is rejected."""
        headers = {
            "X-Slack-Signature": invalid_slack_signature,
            "X-Slack-Request-Timestamp": current_timestamp,
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/webhooks/slack/events",
            json=slack_message_payload,
            headers=headers
        )
        
        assert response.status_code == 401
        assert "Invalid signature" in response.json()["detail"]
    
    def test_missing_headers_rejected(self, slack_message_payload):
        """Test that missing required headers are rejected."""
        response = client.post(
            "/webhooks/slack/events",
            json=slack_message_payload,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 400
        assert "Missing required headers" in response.json()["detail"]
    
    def test_invalid_json_rejected(self, valid_slack_headers):
        """Test that invalid JSON payload is rejected."""
        response = client.post(
            "/webhooks/slack/events", 
            content="invalid json",
            headers=valid_slack_headers
        )
        
        assert response.status_code == 400
        assert "Invalid JSON payload" in response.json()["detail"]
    
    def test_expired_timestamp_rejected(
        self,
        slack_message_payload,
        slack_signing_secret,
        expired_timestamp
    ):
        """Test that expired timestamp is rejected."""
        payload_str = json.dumps(slack_message_payload, separators=(',', ':'))
        signature = create_slack_signature(payload_str, expired_timestamp, slack_signing_secret)
        
        headers = {
            "X-Slack-Signature": signature,
            "X-Slack-Request-Timestamp": expired_timestamp,
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/webhooks/slack/events",
            content=payload_str,
            headers=headers
        )
        
        assert response.status_code == 401
        assert "timestamp too old" in response.json()["detail"]