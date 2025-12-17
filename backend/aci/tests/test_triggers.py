"""
Comprehensive Unit Tests for Trigger System

Tests cover:
- Trigger CRUD operations
- Webhook receiver functionality
- Rate limiting
- Metrics collection
- Background jobs
- Connector base class
"""

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from aci.common.db import crud
from aci.common.db.sql_models import Trigger, TriggerEvent
from aci.common.enums import TriggerEventStatus, TriggerStatus
from aci.server.rate_limiter import RateLimiter
from aci.server.trigger_connectors.base import (
    ParsedWebhookEvent,
    TriggerConnectorBase,
    WebhookRegistrationResult,
    WebhookVerificationResult,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db_session():
    """Mock database session"""
    return Mock(spec=Session)


@pytest.fixture
def sample_trigger():
    """Sample trigger for testing"""
    trigger = Trigger(
        project_id=uuid4(),
        app_id=uuid4(),
        linked_account_id=uuid4(),
        trigger_name="Test Trigger",
        trigger_type="test.event",
        description="Test Description",
        webhook_url="https://example.com/webhook",
        external_webhook_id=None,
        verification_token="test_token_123",
        config={"key": "value"},
        status=TriggerStatus.ACTIVE,
    )
    # Manually set id for testing (init=False in model)
    object.__setattr__(trigger, "id", uuid4())
    return trigger


@pytest.fixture
def sample_trigger_event():
    """Sample trigger event for testing"""
    trigger_event = TriggerEvent(
        trigger_id=uuid4(),
        event_type="test.event",
        event_data={"test": "data"},
        external_event_id="ext_123",
        status=TriggerEventStatus.PENDING,
    )
    # Manually set id for testing (init=False in model)
    object.__setattr__(trigger_event, "id", uuid4())
    return trigger_event


# ============================================================================
# Rate Limiter Tests
# ============================================================================


class TestRateLimiter:
    """Test rate limiting functionality"""

    def test_rate_limiter_allows_within_limit(self):
        """Test that requests within limit are allowed"""
        limiter = RateLimiter(rate=10, capacity=20)

        # Should allow 20 requests (capacity)
        for _i in range(20):
            allowed, metadata = limiter.allow("test_id")
            assert allowed is True
            assert metadata["remaining"] >= 0

    def test_rate_limiter_blocks_over_limit(self):
        """Test that requests over limit are blocked"""
        limiter = RateLimiter(rate=10, capacity=20)

        # Exhaust capacity
        for _i in range(20):
            limiter.allow("test_id")

        # Next request should be blocked
        allowed, metadata = limiter.allow("test_id")
        assert allowed is False
        assert metadata["retry_after"] > 0

    def test_rate_limiter_refills_over_time(self):
        """Test that tokens refill over time"""
        limiter = RateLimiter(rate=100, capacity=10)  # 100 tokens/second

        # Exhaust capacity
        for _i in range(10):
            limiter.allow("test_id")

        # Wait for refill (0.1 second = 10 tokens)
        time.sleep(0.1)

        # Should allow requests again
        allowed, metadata = limiter.allow("test_id")
        assert allowed is True

    def test_rate_limiter_different_identifiers(self):
        """Test that different identifiers have separate buckets"""
        limiter = RateLimiter(rate=1, capacity=5)

        # Exhaust capacity for id1
        for _i in range(5):
            limiter.allow("id1")

        # id1 should be blocked
        allowed1, _ = limiter.allow("id1")
        assert allowed1 is False

        # id2 should still be allowed
        allowed2, _ = limiter.allow("id2")
        assert allowed2 is True

    def test_rate_limiter_reset(self):
        """Test rate limiter reset functionality"""
        limiter = RateLimiter(rate=1, capacity=5)

        # Exhaust capacity
        for _i in range(5):
            limiter.allow("test_id")

        # Reset
        limiter.reset("test_id")

        # Should be allowed again
        allowed, _ = limiter.allow("test_id")
        assert allowed is True

    def test_rate_limiter_cleanup(self):
        """Test that old buckets are cleaned up"""
        limiter = RateLimiter(rate=10, capacity=20, cleanup_interval=1)

        # Create some buckets
        limiter.allow("id1")
        limiter.allow("id2")

        assert len(limiter.buckets) == 2

        # Manually trigger cleanup with old timestamp
        limiter._cleanup(time.time() + 7200)  # 2 hours later

        # Buckets should be cleaned
        assert len(limiter.buckets) == 0


# ============================================================================
# Connector Base Class Tests
# ============================================================================


class TestTriggerConnectorBase:
    """Test base connector functionality"""

    class MockConnector(TriggerConnectorBase):
        """Mock connector for testing"""

        async def register_webhook(self, trigger: Trigger) -> WebhookRegistrationResult:
            return WebhookRegistrationResult(
                success=True,
                external_webhook_id="mock_webhook_123",
            )

        async def unregister_webhook(self, trigger: Trigger) -> bool:
            return True

        async def verify_webhook(self, request, trigger: Trigger) -> WebhookVerificationResult:
            return WebhookVerificationResult(is_valid=True)

        def parse_event(self, payload: dict) -> ParsedWebhookEvent:
            return ParsedWebhookEvent(
                event_type="test.event",
                event_data=payload,
                external_event_id="test_123",
                timestamp=datetime.now(UTC),
            )

    def test_connector_initialization(self):
        """Test connector can be initialized"""
        connector = self.MockConnector()
        assert connector is not None

    @pytest.mark.asyncio
    async def test_connector_register_webhook(self, sample_trigger):
        """Test webhook registration"""
        connector = self.MockConnector()
        result = await connector.register_webhook(sample_trigger)

        assert result.success is True
        assert result.external_webhook_id == "mock_webhook_123"

    @pytest.mark.asyncio
    async def test_connector_unregister_webhook(self, sample_trigger):
        """Test webhook unregistration"""
        connector = self.MockConnector()
        result = await connector.unregister_webhook(sample_trigger)

        assert result is True

    @pytest.mark.asyncio
    async def test_connector_verify_webhook(self, sample_trigger):
        """Test webhook verification"""
        connector = self.MockConnector()
        result = await connector.verify_webhook(None, sample_trigger)

        assert result.is_valid is True

    def test_connector_parse_event(self):
        """Test event parsing"""
        connector = self.MockConnector()
        payload = {"test": "data"}
        result = connector.parse_event(payload)

        assert result.event_type == "test.event"
        assert result.event_data == payload
        assert result.external_event_id == "test_123"

    def test_verify_hmac_signature_valid(self):
        """Test HMAC signature verification with valid signature"""
        connector = self.MockConnector()

        payload = b"test payload"
        secret = "secret_key"

        # Generate valid signature
        import hashlib
        import hmac

        expected_sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        is_valid = connector.verify_hmac_signature(
            payload, expected_sig, secret, algorithm="sha256", signature_format="hex"
        )

        assert is_valid is True

    def test_verify_hmac_signature_invalid(self):
        """Test HMAC signature verification with invalid signature"""
        connector = self.MockConnector()

        payload = b"test payload"
        secret = "secret_key"
        wrong_signature = "wrong_signature_123"

        is_valid = connector.verify_hmac_signature(
            payload, wrong_signature, secret, algorithm="sha256", signature_format="hex"
        )

        assert is_valid is False

    def test_validate_timestamp_recent(self):
        """Test timestamp validation with recent timestamp"""
        connector = self.MockConnector()

        # Current timestamp
        now = int(time.time())

        is_valid = connector.validate_timestamp(now, max_age_seconds=300)
        assert is_valid is True

    def test_validate_timestamp_old(self):
        """Test timestamp validation with old timestamp"""
        connector = self.MockConnector()

        # Old timestamp (1 hour ago)
        old_timestamp = int(time.time()) - 3600

        is_valid = connector.validate_timestamp(old_timestamp, max_age_seconds=300)
        assert is_valid is False

    def test_get_oauth_token(self):
        """Test getting OAuth token from trigger"""
        connector = self.MockConnector()

        mock_trigger = Mock()
        mock_trigger.linked_account.security_credentials = {"access_token": "test_token_123"}

        token = connector.get_oauth_token(mock_trigger)
        assert token == "test_token_123"

    def test_get_oauth_token_missing(self):
        """Test error when OAuth token is missing"""
        connector = self.MockConnector()

        mock_trigger = Mock()
        mock_trigger.linked_account.security_credentials = {}

        with pytest.raises(ValueError, match="No access_token found"):
            connector.get_oauth_token(mock_trigger)

    def test_get_api_key(self):
        """Test getting API key from trigger"""
        connector = self.MockConnector()

        mock_trigger = Mock()
        mock_trigger.linked_account.security_credentials = {"secret_key": "test_api_key_123"}

        api_key = connector.get_api_key(mock_trigger)
        assert api_key == "test_api_key_123"


# ============================================================================
# CRUD Operations Tests
# ============================================================================


class TestTriggerCRUD:
    """Test trigger CRUD operations"""

    def test_create_trigger(self, mock_db_session):
        """Test trigger creation"""
        project_id = uuid4()
        app_id = uuid4()
        linked_account_id = uuid4()

        trigger = crud.triggers.create_trigger(
            mock_db_session,
            project_id=project_id,
            app_id=app_id,
            linked_account_id=linked_account_id,
            trigger_name="Test Trigger",
            trigger_type="test.event",
            description="Test Description",
            webhook_url="https://example.com/webhook",
            verification_token="token_123",
            config={"key": "value"},
        )

        assert trigger.project_id == project_id
        assert trigger.app_id == app_id
        assert trigger.trigger_name == "Test Trigger"
        assert trigger.status == TriggerStatus.ACTIVE
        mock_db_session.add.assert_called_once()
        mock_db_session.flush.assert_called()

    def test_update_trigger_status(self, mock_db_session, sample_trigger):
        """Test trigger status update"""
        updated_trigger = crud.triggers.update_trigger_status(
            mock_db_session, sample_trigger, TriggerStatus.PAUSED
        )

        assert updated_trigger.status == TriggerStatus.PAUSED
        mock_db_session.flush.assert_called_once()

    def test_update_trigger_config(self, mock_db_session, sample_trigger):
        """Test trigger config update"""
        new_config = {"new_key": "new_value"}

        updated_trigger = crud.triggers.update_trigger_config(
            mock_db_session, sample_trigger, new_config
        )

        assert updated_trigger.config == new_config
        mock_db_session.flush.assert_called_once()

    def test_delete_trigger(self, mock_db_session, sample_trigger):
        """Test trigger deletion"""
        crud.triggers.delete_trigger(mock_db_session, sample_trigger)

        mock_db_session.delete.assert_called_once_with(sample_trigger)
        mock_db_session.flush.assert_called_once()


class TestTriggerEventCRUD:
    """Test trigger event CRUD operations"""

    def test_create_trigger_event(self, mock_db_session):
        """Test trigger event creation"""
        trigger_id = uuid4()

        event = crud.trigger_events.create_trigger_event(
            mock_db_session,
            trigger_id=trigger_id,
            event_type="test.event",
            event_data={"test": "data"},
            external_event_id="ext_123",
            status=TriggerEventStatus.PENDING,
        )

        assert event.trigger_id == trigger_id
        assert event.event_type == "test.event"
        assert event.status == TriggerEventStatus.PENDING
        mock_db_session.add.assert_called_once()

    def test_mark_event_delivered(self, mock_db_session, sample_trigger_event):
        """Test marking event as delivered"""
        crud.trigger_events.mark_event_delivered(mock_db_session, sample_trigger_event)

        assert sample_trigger_event.status == TriggerEventStatus.DELIVERED
        assert sample_trigger_event.delivered_at is not None
        mock_db_session.flush.assert_called_once()

    def test_mark_event_processed_success(self, mock_db_session, sample_trigger_event):
        """Test marking event as successfully processed"""
        crud.trigger_events.mark_event_processed(
            mock_db_session, sample_trigger_event, success=True
        )

        assert sample_trigger_event.status == TriggerEventStatus.DELIVERED
        assert sample_trigger_event.processed_at is not None

    def test_mark_event_processed_failure(self, mock_db_session, sample_trigger_event):
        """Test marking event as failed"""
        error_msg = "Test error"

        crud.trigger_events.mark_event_processed(
            mock_db_session, sample_trigger_event, success=False, error_message=error_msg
        )

        assert sample_trigger_event.status == TriggerEventStatus.FAILED
        assert sample_trigger_event.error_message == error_msg


# ============================================================================
# Metrics Tests
# ============================================================================


class TestMetrics:
    """Test metrics collection"""

    def test_increment_counter(self):
        """Test counter increment"""
        from aci.server.metrics import MetricsCollector

        collector = MetricsCollector()

        collector.increment_counter("test_counter", 1.0)
        collector.increment_counter("test_counter", 2.0)

        metrics = collector.get_metrics()
        assert metrics["counters"]["test_counter"] == 3.0

    def test_set_gauge(self):
        """Test gauge setting"""
        from aci.server.metrics import MetricsCollector

        collector = MetricsCollector()

        collector.set_gauge("test_gauge", 42.0)
        collector.set_gauge("test_gauge", 100.0)

        metrics = collector.get_metrics()
        assert metrics["gauges"]["test_gauge"] == 100.0  # Latest value

    def test_record_histogram(self):
        """Test histogram recording"""
        from aci.server.metrics import MetricsCollector

        collector = MetricsCollector()

        collector.record_histogram("test_histogram", 10.0)
        collector.record_histogram("test_histogram", 20.0)
        collector.record_histogram("test_histogram", 30.0)

        metrics = collector.get_metrics()
        histogram = metrics["histograms"]["test_histogram"]

        assert histogram["count"] == 3
        assert histogram["sum"] == 60.0
        assert histogram["min"] == 10.0
        assert histogram["max"] == 30.0
        assert histogram["avg"] == 20.0

    def test_metrics_with_labels(self):
        """Test metrics with labels"""
        from aci.server.metrics import MetricsCollector

        collector = MetricsCollector()

        collector.increment_counter("requests", 1.0, labels={"app": "github"})
        collector.increment_counter("requests", 2.0, labels={"app": "slack"})

        metrics = collector.get_metrics()
        assert "requests{app=github}" in metrics["counters"]
        assert "requests{app=slack}" in metrics["counters"]

    def test_metrics_reset(self):
        """Test metrics reset"""
        from aci.server.metrics import MetricsCollector

        collector = MetricsCollector()

        collector.increment_counter("test", 10.0)
        collector.set_gauge("gauge", 20.0)
        collector.record_histogram("hist", 30.0)

        collector.reset()

        metrics = collector.get_metrics()
        assert len(metrics["counters"]) == 0
        assert len(metrics["gauges"]) == 0
        assert len(metrics["histograms"]) == 0


# ============================================================================
# Background Jobs Tests
# ============================================================================


class TestBackgroundJobs:
    """Test background job functionality"""

    @pytest.mark.asyncio
    @patch("aci.common.db.crud.triggers.get_expiring_triggers")
    @patch("aci.server.trigger_connectors.get_trigger_connector")
    async def test_renew_expiring_triggers(
        self, mock_get_connector, mock_get_expiring, mock_db_session
    ):
        """Test webhook renewal job"""
        from aci.server.background_jobs import renew_expiring_triggers

        # Setup mocks
        mock_trigger = Mock()
        mock_trigger.id = uuid4()
        mock_trigger.app_name = "GOOGLE_CALENDAR"
        mock_trigger.expires_at = datetime.now(UTC) + timedelta(hours=12)

        mock_get_expiring.return_value = [mock_trigger]

        mock_connector = Mock()
        mock_connector.renew_webhook = AsyncMock(
            return_value=WebhookRegistrationResult(
                success=True,
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
        )
        mock_get_connector.return_value = mock_connector

        # Run job
        stats = await renew_expiring_triggers(mock_db_session)

        # Assertions
        assert stats["renewed"] == 1
        assert stats["failed"] == 0
        mock_connector.renew_webhook.assert_called_once()

    @pytest.mark.asyncio
    @patch("aci.common.db.crud.trigger_events.cleanup_expired_events")
    async def test_cleanup_expired_events(self, mock_cleanup, mock_db_session):
        """Test event cleanup job"""
        from aci.server.background_jobs import cleanup_expired_events

        mock_cleanup.return_value = 42

        deleted_count = await cleanup_expired_events(mock_db_session)

        assert deleted_count == 42
        mock_cleanup.assert_called_once()


# ============================================================================
# Integration Tests
# ============================================================================


class TestWebhookReceiver:
    """Test webhook receiver endpoint (integration)"""

    @pytest.mark.asyncio
    async def test_webhook_rate_limiting(self):
        """Test that rate limiting works on webhook receiver"""
        from aci.server.rate_limiter import RateLimiter

        limiter = RateLimiter(rate=1, capacity=2)

        # First 2 requests should succeed
        allowed1, _ = limiter.allow("trigger_123")
        allowed2, _ = limiter.allow("trigger_123")

        assert allowed1 is True
        assert allowed2 is True

        # Third request should be rate limited
        allowed3, metadata = limiter.allow("trigger_123")

        assert allowed3 is False
        assert metadata["retry_after"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
