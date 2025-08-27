"""Tests for triggers database models."""

import pytest
from sqlalchemy.exc import IntegrityError
from uuid import uuid4

from ..models import IncomingEvent, WebhookProvider


class TestIncomingEventModel:
    """Test IncomingEvent model functionality."""
    
    def test_create_incoming_event(self, db_session):
        """Test creating a basic IncomingEvent."""
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
        
        assert event.id is not None
        assert event.provider == WebhookProvider.SLACK
        assert event.event_id == "test_event_123"
        assert event.signature_valid is True
        assert event.payload == {"test": "data"}
        assert event.processed is False
        assert event.received_at is not None
    
    def test_create_hubspot_event(self, db_session):
        """Test creating HubSpot IncomingEvent."""
        payload = {
            "eventId": "hub123",
            "subscriptionType": "contact.propertyChange",
            "objectId": "987654321",
            "propertyName": "email",
            "propertyValue": "test@example.com"
        }
        
        event = IncomingEvent(
            provider=WebhookProvider.HUBSPOT,
            event_id="hub123",
            signature_valid=True,
            payload=payload,
            processed=False
        )
        
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        
        assert event.provider == WebhookProvider.HUBSPOT
        assert event.event_id == "hub123"
        assert event.payload["subscriptionType"] == "contact.propertyChange"
    
    def test_create_gmail_event(self, db_session):
        """Test creating Gmail IncomingEvent."""
        payload = {
            "emailAddress": "user@example.com",
            "historyId": "12345678"
        }
        
        event = IncomingEvent(
            provider=WebhookProvider.GMAIL,
            event_id="user@example.com:12345678",
            signature_valid=True,
            payload=payload,
            processed=False
        )
        
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        
        assert event.provider == WebhookProvider.GMAIL
        assert event.event_id == "user@example.com:12345678"
        assert event.payload["emailAddress"] == "user@example.com"


class TestIdempotencyConstraints:
    """Test idempotency uniqueness constraints."""
    
    def test_unique_constraint_provider_event_id(self, db_session):
        """Test that (provider, event_id) must be unique."""
        # Create first event
        event1 = IncomingEvent(
            provider=WebhookProvider.SLACK,
            event_id="duplicate_event_123",
            signature_valid=True,
            payload={"first": "event"},
            processed=False
        )
        
        db_session.add(event1)
        db_session.commit()
        
        # Try to create duplicate event with same provider and event_id
        event2 = IncomingEvent(
            provider=WebhookProvider.SLACK,
            event_id="duplicate_event_123",  # Same event_id
            signature_valid=True,
            payload={"second": "event"},  # Different payload
            processed=False
        )
        
        db_session.add(event2)
        
        # Should raise IntegrityError due to unique constraint violation
        with pytest.raises(IntegrityError):
            db_session.commit()
    
    def test_same_event_id_different_providers_allowed(self, db_session):
        """Test that same event_id is allowed for different providers."""
        # Create Slack event
        slack_event = IncomingEvent(
            provider=WebhookProvider.SLACK,
            event_id="shared_event_123",
            signature_valid=True,
            payload={"source": "slack"},
            processed=False
        )
        
        # Create HubSpot event with same event_id (different provider)
        hubspot_event = IncomingEvent(
            provider=WebhookProvider.HUBSPOT,
            event_id="shared_event_123",  # Same event_id, different provider
            signature_valid=True,
            payload={"source": "hubspot"},
            processed=False
        )
        
        db_session.add(slack_event)
        db_session.add(hubspot_event)
        db_session.commit()  # Should not raise error
        
        # Verify both events were created
        slack_result = db_session.query(IncomingEvent).filter(
            IncomingEvent.provider == WebhookProvider.SLACK,
            IncomingEvent.event_id == "shared_event_123"
        ).first()
        
        hubspot_result = db_session.query(IncomingEvent).filter(
            IncomingEvent.provider == WebhookProvider.HUBSPOT,
            IncomingEvent.event_id == "shared_event_123"
        ).first()
        
        assert slack_result is not None
        assert hubspot_result is not None
        assert slack_result.payload["source"] == "slack"
        assert hubspot_result.payload["source"] == "hubspot"
    
    def test_different_event_ids_same_provider_allowed(self, db_session):
        """Test that different event_ids are allowed for same provider."""
        # Create first Slack event
        event1 = IncomingEvent(
            provider=WebhookProvider.SLACK,
            event_id="event_123",
            signature_valid=True,
            payload={"sequence": 1},
            processed=False
        )
        
        # Create second Slack event with different event_id
        event2 = IncomingEvent(
            provider=WebhookProvider.SLACK,
            event_id="event_456",  # Different event_id
            signature_valid=True,
            payload={"sequence": 2},
            processed=False
        )
        
        db_session.add(event1)
        db_session.add(event2)
        db_session.commit()  # Should not raise error
        
        # Verify both events were created
        events = db_session.query(IncomingEvent).filter(
            IncomingEvent.provider == WebhookProvider.SLACK
        ).all()
        
        assert len(events) == 2
        event_ids = [event.event_id for event in events]
        assert "event_123" in event_ids
        assert "event_456" in event_ids
    
    def test_idempotency_on_duplicate_slack_message(self, db_session):
        """Test idempotency for duplicate Slack message events."""
        slack_payload = {
            "type": "event_callback",
            "event": {
                "type": "message",
                "channel": "C1234567890",
                "user": "U1234567890",
                "text": "Hello, world!",
                "ts": "1234567890.123456",
                "event_ts": "1234567890.123456"
            },
            "event_id": "Ev1234567890"
        }
        
        # Create first event
        event1 = IncomingEvent(
            provider=WebhookProvider.SLACK,
            event_id="1234567890.123456",  # Using event_ts as event_id
            signature_valid=True,
            payload=slack_payload,
            processed=True
        )
        
        db_session.add(event1)
        db_session.commit()
        
        # Try to create duplicate (simulates webhook retry)
        event2 = IncomingEvent(
            provider=WebhookProvider.SLACK,
            event_id="1234567890.123456",  # Same event_id
            signature_valid=True,
            payload=slack_payload,  # Same payload
            processed=False  # Different processed status
        )
        
        db_session.add(event2)
        
        # Should raise IntegrityError
        with pytest.raises(IntegrityError):
            db_session.commit()
    
    def test_idempotency_on_duplicate_hubspot_event(self, db_session):
        """Test idempotency for duplicate HubSpot events."""
        hubspot_payload = {
            "eventId": "hubspot123",
            "subscriptionType": "contact.propertyChange",
            "objectId": "987654321",
            "occurredAt": 1234567890000,
            "propertyName": "email",
            "propertyValue": "test@example.com"
        }
        
        # Create first event
        event1 = IncomingEvent(
            provider=WebhookProvider.HUBSPOT,
            event_id="hubspot123",
            signature_valid=True,
            payload=hubspot_payload,
            processed=False
        )
        
        db_session.add(event1)
        db_session.commit()
        
        # Try to create duplicate
        event2 = IncomingEvent(
            provider=WebhookProvider.HUBSPOT,
            event_id="hubspot123",  # Same event_id
            signature_valid=True,
            payload=hubspot_payload,
            processed=False
        )
        
        db_session.add(event2)
        
        # Should raise IntegrityError
        with pytest.raises(IntegrityError):
            db_session.commit()
    
    def test_idempotency_on_duplicate_gmail_event(self, db_session):
        """Test idempotency for duplicate Gmail events."""
        gmail_payload = {
            "emailAddress": "user@example.com",
            "historyId": "12345678"
        }
        
        # Create first event
        event1 = IncomingEvent(
            provider=WebhookProvider.GMAIL,
            event_id="user@example.com:12345678",
            signature_valid=True,
            payload=gmail_payload,
            processed=False
        )
        
        db_session.add(event1)
        db_session.commit()
        
        # Try to create duplicate
        event2 = IncomingEvent(
            provider=WebhookProvider.GMAIL,
            event_id="user@example.com:12345678",  # Same event_id
            signature_valid=True,
            payload=gmail_payload,
            processed=False
        )
        
        db_session.add(event2)
        
        # Should raise IntegrityError
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestModelDefaults:
    """Test model default values."""
    
    def test_default_values(self, db_session):
        """Test that model fields have correct default values."""
        event = IncomingEvent(
            provider=WebhookProvider.SLACK,
            event_id="test_defaults",
            payload={"test": "data"}
            # Not setting signature_valid or processed
        )
        
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        
        # Check defaults
        assert event.signature_valid is False  # Default False
        assert event.processed is False  # Default False
        assert event.received_at is not None  # Auto-generated
        assert event.id is not None  # Auto-generated UUID


class TestModelRepresentation:
    """Test model string representation."""
    
    def test_incoming_event_repr(self, db_session):
        """Test IncomingEvent string representation."""
        event = IncomingEvent(
            provider=WebhookProvider.SLACK,
            event_id="repr_test_123",
            signature_valid=True,
            payload={"test": "data"},
            processed=False
        )
        
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        
        repr_str = repr(event)
        
        assert "IncomingEvent" in repr_str
        assert str(event.id) in repr_str
        assert "slack" in repr_str
        assert "repr_test_123" in repr_str
        assert "processed=False" in repr_str