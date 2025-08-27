"""Tests for Gmail Pub/Sub webhook handling."""

import json
import base64
import time
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from ..api import router
from ..verify import (
    verify_google_pubsub_token, 
    decode_pubsub_message,
    GooglePubSubVerificationError
)
from ..normalize import normalize_gmail_event, get_event_id_for_provider
from ..models import WebhookProvider


# Create test app
app = FastAPI()
app.include_router(router, prefix="/webhooks")
client = TestClient(app)


class TestGmailPubSubVerification:
    """Test Gmail Pub/Sub OIDC token verification."""
    
    @pytest.fixture(autouse=True)
    def setup_settings(self, monkeypatch):
        """Mock settings for testing."""
        monkeypatch.setattr(
            "aci.triggers.settings.settings.google_issuer",
            "https://accounts.google.com"
        )
        monkeypatch.setattr(
            "aci.triggers.settings.settings.pubsub_oidc_audience",
            "https://mydomain.com/webhooks/gmail/pubsub"
        )
    
    def test_valid_jwt_token_mock(self, mock_jwt_token):
        """Test that valid JWT token passes verification (mock implementation)."""
        auth_header = f"Bearer {mock_jwt_token}"
        
        payload = verify_google_pubsub_token(auth_header)
        
        assert payload is not None
        assert payload["iss"] == "https://accounts.google.com"
        assert payload["aud"] == "https://mydomain.com/webhooks/gmail/pubsub"
        assert "exp" in payload
    
    def test_invalid_authorization_header_format(self):
        """Test that invalid Authorization header format is rejected."""
        invalid_auth_header = "InvalidFormat token"
        
        with pytest.raises(GooglePubSubVerificationError, match="Invalid authorization header format"):
            verify_google_pubsub_token(invalid_auth_header)
    
    def test_invalid_jwt_format(self):
        """Test that invalid JWT format is rejected."""
        invalid_jwt = "invalid.jwt"
        auth_header = f"Bearer {invalid_jwt}"
        
        with pytest.raises(GooglePubSubVerificationError, match="Invalid JWT format"):
            verify_google_pubsub_token(auth_header)
    
    def test_invalid_issuer_rejected(self, monkeypatch):
        """Test that invalid issuer is rejected."""
        # Create JWT with wrong issuer
        header = {"typ": "JWT", "alg": "RS256"}
        payload = {
            "iss": "https://wrong-issuer.com",  # Wrong issuer
            "aud": "https://mydomain.com/webhooks/gmail/pubsub",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time())
        }
        
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        signature_b64 = "mock_signature"
        invalid_token = f"{header_b64}.{payload_b64}.{signature_b64}"
        
        auth_header = f"Bearer {invalid_token}"
        
        with pytest.raises(GooglePubSubVerificationError, match="Invalid issuer"):
            verify_google_pubsub_token(auth_header)
    
    def test_invalid_audience_rejected(self, monkeypatch):
        """Test that invalid audience is rejected.""" 
        # Create JWT with wrong audience
        header = {"typ": "JWT", "alg": "RS256"}
        payload = {
            "iss": "https://accounts.google.com",
            "aud": "https://wrong-audience.com",  # Wrong audience
            "exp": int(time.time()) + 3600,
            "iat": int(time.time())
        }
        
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        signature_b64 = "mock_signature"
        invalid_token = f"{header_b64}.{payload_b64}.{signature_b64}"
        
        auth_header = f"Bearer {invalid_token}"
        
        with pytest.raises(GooglePubSubVerificationError, match="Invalid audience"):
            verify_google_pubsub_token(auth_header)
    
    def test_expired_token_rejected(self, monkeypatch):
        """Test that expired token is rejected."""
        # Create expired JWT
        header = {"typ": "JWT", "alg": "RS256"}
        payload = {
            "iss": "https://accounts.google.com", 
            "aud": "https://mydomain.com/webhooks/gmail/pubsub",
            "exp": int(time.time()) - 3600,  # Expired 1 hour ago
            "iat": int(time.time()) - 7200   # Issued 2 hours ago
        }
        
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        signature_b64 = "mock_signature"
        expired_token = f"{header_b64}.{payload_b64}.{signature_b64}"
        
        auth_header = f"Bearer {expired_token}"
        
        with pytest.raises(GooglePubSubVerificationError, match="Token expired"):
            verify_google_pubsub_token(auth_header)


class TestGmailPubSubDecoding:
    """Test Gmail Pub/Sub message decoding."""
    
    def test_decode_valid_message(self, gmail_pubsub_message):
        """Test decoding valid base64-encoded message."""
        message_json = json.dumps(gmail_pubsub_message)
        message_b64 = base64.b64encode(message_json.encode()).decode()
        
        decoded = decode_pubsub_message(message_b64)
        
        assert decoded == gmail_pubsub_message
        assert decoded["emailAddress"] == "user@example.com"
        assert decoded["historyId"] == "12345678"
    
    def test_decode_message_with_padding(self):
        """Test decoding message that needs base64 padding."""
        message = {"test": "data"}
        message_json = json.dumps(message)
        # Create base64 without padding
        message_b64 = base64.b64encode(message_json.encode()).decode().rstrip('=')
        
        decoded = decode_pubsub_message(message_b64)
        
        assert decoded == message
    
    def test_decode_invalid_base64(self):
        """Test that invalid base64 is rejected."""
        invalid_b64 = "invalid_base64_data!"
        
        with pytest.raises(GooglePubSubVerificationError, match="Failed to decode Pub/Sub message"):
            decode_pubsub_message(invalid_b64)
    
    def test_decode_invalid_json(self):
        """Test that invalid JSON is rejected."""
        invalid_json = "not json data"
        invalid_json_b64 = base64.b64encode(invalid_json.encode()).decode()
        
        with pytest.raises(GooglePubSubVerificationError, match="Failed to decode Pub/Sub message"):
            decode_pubsub_message(invalid_json_b64)
    
    def test_decode_non_utf8(self):
        """Test that non-UTF-8 data is rejected."""
        # Create invalid UTF-8 bytes
        invalid_utf8 = b'\xff\xfe\xfd'
        invalid_utf8_b64 = base64.b64encode(invalid_utf8).decode()
        
        with pytest.raises(GooglePubSubVerificationError, match="Failed to decode Pub/Sub message"):
            decode_pubsub_message(invalid_utf8_b64)


class TestGmailNormalization:
    """Test Gmail event normalization."""
    
    def test_normalize_gmail_history_event(self, gmail_pubsub_message):
        """Test normalization of Gmail history event."""
        normalized_events = normalize_gmail_event(gmail_pubsub_message)
        
        assert len(normalized_events) == 1
        
        event = normalized_events[0]
        assert event.provider == "gmail"
        assert event.type == "gmail.history"
        assert event.subject_id == "user@example.com"
        assert event.data["email_address"] == "user@example.com"
        assert event.data["history_id"] == "12345678"
        assert event.data["original_payload"] == gmail_pubsub_message
    
    def test_normalize_missing_email_address(self):
        """Test normalization handles missing emailAddress."""
        incomplete_message = {"historyId": "12345678"}
        
        normalized_events = normalize_gmail_event(incomplete_message)
        assert len(normalized_events) == 0
    
    def test_normalize_missing_history_id(self):
        """Test normalization handles missing historyId."""
        incomplete_message = {"emailAddress": "user@example.com"}
        
        normalized_events = normalize_gmail_event(incomplete_message)
        assert len(normalized_events) == 0
    
    def test_get_event_id_for_gmail(self, gmail_pubsub_message):
        """Test extracting event ID from Gmail message."""
        event_id = get_event_id_for_provider(WebhookProvider.GMAIL, gmail_pubsub_message)
        assert event_id == "user@example.com:12345678"
    
    def test_get_event_id_for_gmail_missing_data(self):
        """Test extracting event ID handles missing data."""
        incomplete_message = {"emailAddress": "user@example.com"}
        event_id = get_event_id_for_provider(WebhookProvider.GMAIL, incomplete_message)
        assert event_id is None


class TestGmailWebhookEndpoint:
    """Test Gmail Pub/Sub webhook HTTP endpoint."""
    
    @pytest.fixture(autouse=True)
    def setup_settings(self, monkeypatch):
        """Mock settings for testing."""
        monkeypatch.setattr(
            "aci.triggers.settings.settings.google_issuer",
            "https://accounts.google.com"
        )
        monkeypatch.setattr(
            "aci.triggers.settings.settings.pubsub_oidc_audience",
            "https://mydomain.com/webhooks/gmail/pubsub"
        )
    
    def test_valid_gmail_webhook(
        self,
        gmail_pubsub_envelope,
        mock_jwt_token,
        monkeypatch
    ):
        """Test valid Gmail Pub/Sub webhook processing."""
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
        
        headers = {
            "Authorization": f"Bearer {mock_jwt_token}",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/webhooks/gmail/pubsub",
            json=gmail_pubsub_envelope,
            headers=headers
        )
        
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    
    def test_missing_authorization_header(self, gmail_pubsub_envelope):
        """Test that missing Authorization header is rejected."""
        response = client.post(
            "/webhooks/gmail/pubsub",
            json=gmail_pubsub_envelope,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 401
        assert "Missing Authorization header" in response.json()["detail"]
    
    def test_invalid_jwt_token(self, gmail_pubsub_envelope):
        """Test that invalid JWT token is rejected."""
        headers = {
            "Authorization": "Bearer invalid.jwt.token",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/webhooks/gmail/pubsub",
            json=gmail_pubsub_envelope,
            headers=headers
        )
        
        assert response.status_code == 401
        assert "Invalid JWT format" in response.json()["detail"]
    
    def test_missing_message_data(self, mock_jwt_token):
        """Test that missing message data is rejected."""
        envelope_no_data = {
            "message": {},  # No data field
            "subscription": "projects/test-project/subscriptions/test-subscription"
        }
        
        headers = {
            "Authorization": f"Bearer {mock_jwt_token}",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/webhooks/gmail/pubsub",
            json=envelope_no_data,
            headers=headers
        )
        
        assert response.status_code == 400
        assert "Missing message data" in response.json()["detail"]
    
    def test_invalid_message_encoding(self, mock_jwt_token):
        """Test that invalid message encoding is rejected."""
        envelope_bad_encoding = {
            "message": {
                "data": "invalid_base64_data!",
                "messageId": "message_id_123"
            },
            "subscription": "projects/test-project/subscriptions/test-subscription"
        }
        
        headers = {
            "Authorization": f"Bearer {mock_jwt_token}",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/webhooks/gmail/pubsub",
            json=envelope_bad_encoding,
            headers=headers
        )
        
        assert response.status_code == 400
        assert "Failed to decode Pub/Sub message" in response.json()["detail"]
    
    def test_missing_email_address_or_history_id(self, mock_jwt_token):
        """Test that missing emailAddress or historyId is rejected."""
        # Create message with missing emailAddress
        incomplete_message = {"historyId": "12345678"}
        message_json = json.dumps(incomplete_message)
        message_b64 = base64.b64encode(message_json.encode()).decode()
        
        envelope = {
            "message": {
                "data": message_b64,
                "messageId": "message_id_123"
            },
            "subscription": "projects/test-project/subscriptions/test-subscription"
        }
        
        headers = {
            "Authorization": f"Bearer {mock_jwt_token}",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/webhooks/gmail/pubsub",
            json=envelope,
            headers=headers
        )
        
        assert response.status_code == 400
        assert "Missing emailAddress or historyId" in response.json()["detail"]
    
    def test_invalid_json_payload(self, mock_jwt_token):
        """Test that invalid JSON payload is rejected."""
        headers = {
            "Authorization": f"Bearer {mock_jwt_token}",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/webhooks/gmail/pubsub",
            content="invalid json",
            headers=headers
        )
        
        assert response.status_code == 400
        assert "Invalid JSON payload" in response.json()["detail"]