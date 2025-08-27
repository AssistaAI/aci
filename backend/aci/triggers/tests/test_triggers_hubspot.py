"""Tests for HubSpot webhook handling."""

import json
import time
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from ..api import router
from ..verify import verify_hubspot_webhook, HubSpotVerificationError
from ..normalize import normalize_hubspot_event, get_event_id_for_provider
from ..models import WebhookProvider
from .conftest import create_hubspot_signature


# Create test app
app = FastAPI()
app.include_router(router, prefix="/webhooks")
client = TestClient(app)


class TestHubSpotVerification:
    """Test HubSpot webhook signature verification."""
    
    def test_valid_hubspot_signature(self, hubspot_app_secret):
        """Test that valid HubSpot v3 signature passes verification."""
        timestamp = str(int(time.time() * 1000))
        method = "POST"
        uri = "/webhooks/hubspot"
        body = '{"test": "data"}'
        
        signature = create_hubspot_signature(method, uri, body, timestamp, hubspot_app_secret)
        
        result = verify_hubspot_webhook(
            signature=signature,
            timestamp=timestamp,
            method=method,
            uri=uri,
            body=body.encode(),
            client_secret=hubspot_app_secret
        )
        
        assert result is True
    
    def test_invalid_hubspot_signature(self, hubspot_app_secret):
        """Test that invalid HubSpot signature fails verification."""
        timestamp = str(int(time.time() * 1000))
        method = "POST"
        uri = "/webhooks/hubspot"
        body = '{"test": "data"}'
        
        invalid_signature = "invalid_signature_hash"
        
        result = verify_hubspot_webhook(
            signature=invalid_signature,
            timestamp=timestamp,
            method=method,
            uri=uri,
            body=body.encode(),
            client_secret=hubspot_app_secret
        )
        
        assert result is False
    
    def test_hubspot_replay_attack_protection(self, hubspot_app_secret):
        """Test that old timestamps are rejected (replay attack protection)."""
        # Use timestamp from 10 minutes ago (in milliseconds)
        old_timestamp = str(int((time.time() - 600) * 1000))
        method = "POST"
        uri = "/webhooks/hubspot"
        body = '{"test": "data"}'
        
        signature = create_hubspot_signature(method, uri, body, old_timestamp, hubspot_app_secret)
        
        with pytest.raises(HubSpotVerificationError, match="timestamp too old"):
            verify_hubspot_webhook(
                signature=signature,
                timestamp=old_timestamp,
                method=method,
                uri=uri,
                body=body.encode(),
                client_secret=hubspot_app_secret
            )
    
    def test_invalid_hubspot_timestamp_format(self, hubspot_app_secret):
        """Test that invalid timestamp format is rejected."""
        invalid_timestamp = "not_a_number"
        method = "POST"
        uri = "/webhooks/hubspot"
        body = '{"test": "data"}'
        signature = "some_signature"
        
        with pytest.raises(HubSpotVerificationError, match="Invalid timestamp format"):
            verify_hubspot_webhook(
                signature=signature,
                timestamp=invalid_timestamp,
                method=method,
                uri=uri,
                body=body.encode(),
                client_secret=hubspot_app_secret
            )
    
    def test_canonical_string_construction(self, hubspot_app_secret):
        """Test that canonical string is constructed correctly."""
        timestamp = str(int(time.time() * 1000))
        method = "POST"
        uri = "/webhooks/hubspot"
        body = '{"eventId":"123","subscriptionType":"contact.propertyChange"}'
        
        signature = create_hubspot_signature(method, uri, body, timestamp, hubspot_app_secret)
        
        # Verify with correct parameters
        result = verify_hubspot_webhook(
            signature=signature,
            timestamp=timestamp,
            method=method,
            uri=uri,
            body=body.encode(),
            client_secret=hubspot_app_secret
        )
        assert result is True
        
        # Verify fails with different URI
        result = verify_hubspot_webhook(
            signature=signature,
            timestamp=timestamp,
            method=method,
            uri="/different/path",
            body=body.encode(),
            client_secret=hubspot_app_secret
        )
        assert result is False


class TestHubSpotNormalization:
    """Test HubSpot event normalization."""
    
    def test_normalize_single_contact_event(self, hubspot_contact_event):
        """Test normalization of single HubSpot contact event."""
        normalized_events = normalize_hubspot_event(hubspot_contact_event)
        
        assert len(normalized_events) == 1
        
        event = normalized_events[0]
        assert event.provider == "hubspot"
        assert event.type == "hubspot.contact.propertyChange"
        assert event.subject_id == "987654321"
        assert event.data["event_id"] == "12345"
        assert event.data["property_name"] == "email"
        assert event.data["property_value"] == "test@example.com"
    
    def test_normalize_batched_events(self, hubspot_batched_events):
        """Test normalization of batched HubSpot events."""
        normalized_events = normalize_hubspot_event(hubspot_batched_events)
        
        assert len(normalized_events) == 2
        
        # First event
        event1 = normalized_events[0]
        assert event1.provider == "hubspot"
        assert event1.type == "hubspot.contact.propertyChange"
        assert event1.subject_id == "111111111"
        assert event1.data["event_id"] == "12345"
        
        # Second event
        event2 = normalized_events[1]
        assert event2.provider == "hubspot"
        assert event2.type == "hubspot.contact.propertyChange"
        assert event2.subject_id == "222222222"
        assert event2.data["event_id"] == "12346"
        assert event2.data["property_name"] == "firstname"
    
    def test_normalize_deal_event(self):
        """Test normalization of HubSpot deal event."""
        deal_event = {
            "eventId": "deal123",
            "subscriptionId": "67890",
            "portalId": "123456",
            "occurredAt": int(time.time() * 1000),
            "subscriptionType": "deal.creation",
            "objectId": "deal987654321"
        }
        
        normalized_events = normalize_hubspot_event(deal_event)
        
        assert len(normalized_events) == 1
        event = normalized_events[0]
        assert event.type == "hubspot.deal.creation"
        assert event.subject_id == "deal987654321"
    
    def test_normalize_company_event(self):
        """Test normalization of HubSpot company event."""
        company_event = {
            "eventId": "company123",
            "subscriptionId": "67890", 
            "portalId": "123456",
            "occurredAt": int(time.time() * 1000),
            "subscriptionType": "company.propertyChange",
            "objectId": "company123456",
            "propertyName": "name",
            "propertyValue": "Test Company Inc"
        }
        
        normalized_events = normalize_hubspot_event(company_event)
        
        assert len(normalized_events) == 1
        event = normalized_events[0]
        assert event.type == "hubspot.company.propertyChange"
        assert event.subject_id == "company123456"
        assert event.data["property_name"] == "name"
        assert event.data["property_value"] == "Test Company Inc"
    
    def test_get_event_id_for_hubspot_single(self, hubspot_contact_event):
        """Test extracting event ID from single HubSpot event."""
        event_id = get_event_id_for_provider(WebhookProvider.HUBSPOT, hubspot_contact_event)
        assert event_id == "12345"
    
    def test_get_event_id_for_hubspot_batched(self, hubspot_batched_events):
        """Test extracting event ID from batched HubSpot events."""
        event_id = get_event_id_for_provider(WebhookProvider.HUBSPOT, hubspot_batched_events)
        assert event_id == "12345"  # First event's ID
    
    def test_normalize_missing_fields(self):
        """Test normalization handles missing required fields gracefully."""
        incomplete_event = {
            "eventId": "123",
            # Missing objectId, subscriptionType, occurredAt
        }
        
        normalized_events = normalize_hubspot_event(incomplete_event)
        assert len(normalized_events) == 0  # Should skip incomplete events


class TestHubSpotWebhookEndpoint:
    """Test HubSpot webhook HTTP endpoint."""
    
    @pytest.fixture(autouse=True)
    def setup_settings(self, monkeypatch, hubspot_app_secret):
        """Mock settings for testing."""
        monkeypatch.setattr("aci.triggers.settings.settings.hubspot_app_secret", hubspot_app_secret)
    
    def test_valid_single_event_webhook(
        self,
        hubspot_contact_event,
        valid_hubspot_headers,
        monkeypatch
    ):
        """Test valid HubSpot single event webhook processing."""
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
        
        response = client.post(
            "/webhooks/hubspot",
            json=hubspot_contact_event,
            headers=valid_hubspot_headers
        )
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["status"] == "ok"
        assert response_data["events_processed"] == 1
        assert response_data["events_skipped"] == 0
    
    def test_valid_batched_events_webhook(
        self,
        hubspot_batched_events,
        hubspot_app_secret,
        monkeypatch
    ):
        """Test valid HubSpot batched events webhook processing."""
        # Create headers for batched events
        timestamp = str(int(time.time() * 1000))
        payload_str = json.dumps(hubspot_batched_events, separators=(',', ':'))
        signature = create_hubspot_signature("POST", "/webhooks/hubspot", payload_str, timestamp, hubspot_app_secret)
        
        headers = {
            "X-HubSpot-Signature-V3": signature,
            "X-HubSpot-Request-Timestamp": timestamp,
            "Content-Type": "application/json"
        }
        
        # Mock database and queue operations
        mock_db_session = type('MockSession', (), {
            'add': lambda self, obj: None,
            'commit': lambda self: None,
            'rollback': lambda self: None
        })()
        
        def mock_yield_db_session():
            return mock_db_session
        
        def mock_enqueue_multiple_events(events):
            return [type('MockJob', (), {'id': f'mock_job_{i}'})() for i in range(len(events))]
        
        monkeypatch.setattr("aci.triggers.api.deps.yield_db_session", mock_yield_db_session)
        monkeypatch.setattr("aci.triggers.api.enqueue_multiple_events", mock_enqueue_multiple_events)
        
        response = client.post(
            "/webhooks/hubspot",
            json=hubspot_batched_events,
            headers=headers
        )
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["status"] == "ok"
        assert response_data["events_processed"] == 2
        assert response_data["events_skipped"] == 0
    
    def test_invalid_signature_rejected(
        self,
        hubspot_contact_event,
        hubspot_app_secret
    ):
        """Test that invalid signature is rejected."""
        timestamp = str(int(time.time() * 1000))
        
        headers = {
            "X-HubSpot-Signature-V3": "invalid_signature",
            "X-HubSpot-Request-Timestamp": timestamp,
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/webhooks/hubspot",
            json=hubspot_contact_event,
            headers=headers
        )
        
        assert response.status_code == 401
        assert "Invalid signature" in response.json()["detail"]
    
    def test_missing_headers_rejected(self, hubspot_contact_event):
        """Test that missing required headers are rejected."""
        response = client.post(
            "/webhooks/hubspot",
            json=hubspot_contact_event,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 400
        assert "Missing required headers" in response.json()["detail"]
    
    def test_invalid_json_rejected(self, valid_hubspot_headers):
        """Test that invalid JSON payload is rejected."""
        response = client.post(
            "/webhooks/hubspot",
            content="invalid json",
            headers=valid_hubspot_headers
        )
        
        assert response.status_code == 400
        assert "Invalid JSON payload" in response.json()["detail"]
    
    def test_expired_timestamp_rejected(
        self,
        hubspot_contact_event,
        hubspot_app_secret
    ):
        """Test that expired timestamp is rejected."""
        # Use timestamp from 10 minutes ago (in milliseconds)
        old_timestamp = str(int((time.time() - 600) * 1000))
        payload_str = json.dumps(hubspot_contact_event, separators=(',', ':'))
        signature = create_hubspot_signature("POST", "/webhooks/hubspot", payload_str, old_timestamp, hubspot_app_secret)
        
        headers = {
            "X-HubSpot-Signature-V3": signature,
            "X-HubSpot-Request-Timestamp": old_timestamp,
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/webhooks/hubspot",
            content=payload_str,
            headers=headers
        )
        
        assert response.status_code == 401
        assert "timestamp too old" in response.json()["detail"]