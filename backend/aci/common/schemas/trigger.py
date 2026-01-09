"""
Pydantic schemas for Trigger and TriggerEvent API operations.
Uses Pydantic V2 with modern patterns, type safety, and DRY principles.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aci.common.db.sql_models import MAX_STRING_LENGTH
from aci.common.enums import TriggerEventStatus, TriggerStatus

# ============================================================================
# Base Models (DRY - shared fields)
# ============================================================================


class TriggerBase(BaseModel):
    """Base model for shared Trigger fields"""

    trigger_name: Annotated[str, Field(max_length=MAX_STRING_LENGTH)]
    trigger_type: Annotated[
        str,
        Field(
            max_length=MAX_STRING_LENGTH, description="Event type (e.g., gmail.message_received)"
        ),
    ]
    description: str = Field(description="Human-readable description of the trigger")
    config: dict = Field(default_factory=dict, description="App-specific configuration and filters")


class TriggerEventBase(BaseModel):
    """Base model for shared TriggerEvent fields"""

    event_type: Annotated[str, Field(max_length=MAX_STRING_LENGTH)]
    event_data: dict = Field(description="Raw webhook payload from third-party service")
    external_event_id: Annotated[
        str | None,
        Field(
            None, max_length=MAX_STRING_LENGTH, description="Provider's event ID for deduplication"
        ),
    ]


# ============================================================================
# Request Models (API Input)
# ============================================================================


class TriggerCreate(TriggerBase):
    """Request schema for creating a new trigger"""

    app_name: Annotated[
        str, Field(max_length=MAX_STRING_LENGTH, description="Name of the app to subscribe to")
    ]
    linked_account_owner_id: Annotated[
        str,
        Field(
            max_length=MAX_STRING_LENGTH,
            description="Owner of the linked account to use for webhook registration",
        ),
    ]

    # Optional fields with sensible defaults
    status: TriggerStatus = Field(default="active")
    expires_at: datetime | None = Field(
        None, description="Optional expiration time (for Gmail push notifications)"
    )

    @field_validator("config")
    @classmethod
    def validate_config(cls, v: dict) -> dict:
        """Ensure config is a dict and not None"""
        if v is None:
            return {}
        return v


class TriggerUpdate(BaseModel):
    """Request schema for updating a trigger"""

    status: TriggerStatus | None = Field(None, description="Update trigger status")
    config: dict | None = Field(None, description="Update trigger configuration")
    description: str | None = Field(None, description="Update trigger description")


class TriggerEventCreate(TriggerEventBase):
    """Request schema for creating a trigger event (usually internal)"""

    trigger_id: UUID
    status: TriggerEventStatus = Field(default="pending")
    expires_at: datetime | None = None


# ============================================================================
# Response Models (API Output)
# ============================================================================


class TriggerPublic(TriggerBase):
    """Public response schema for Trigger"""

    id: UUID
    project_id: UUID
    app_id: UUID
    app_name: str  # Computed from relationship
    linked_account_id: UUID
    webhook_url: str
    external_webhook_id: str | None = None
    status: TriggerStatus
    last_triggered_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TriggerWithToken(TriggerPublic):
    """Extended response including verification token (for initial setup)"""

    verification_token: str


class TriggerEventPublic(TriggerEventBase):
    """Public response schema for TriggerEvent"""

    id: UUID
    trigger_id: UUID
    status: TriggerEventStatus
    error_message: str | None = None
    received_at: datetime
    processed_at: datetime | None = None
    delivered_at: datetime | None = None
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Query Parameter Models (for list endpoints)
# ============================================================================


class TriggersListQuery(BaseModel):
    """Query parameters for listing triggers"""

    app_name: Annotated[str | None, Field(None, max_length=MAX_STRING_LENGTH)] = None
    status: TriggerStatus | None = None
    limit: Annotated[int, Field(100, ge=1, le=250)] = 100
    offset: Annotated[int, Field(0, ge=0)] = 0


class TriggerEventsListQuery(BaseModel):
    """Query parameters for listing trigger events"""

    trigger_id: UUID | None = None
    status: TriggerEventStatus | None = None
    event_type: Annotated[str | None, Field(None, max_length=MAX_STRING_LENGTH)] = None
    since: datetime | None = Field(None, description="Filter events received after this timestamp")
    until: datetime | None = Field(None, description="Filter events received before this timestamp")
    limit: Annotated[int, Field(100, ge=1, le=250)] = 100
    offset: Annotated[int, Field(0, ge=0)] = 0


# ============================================================================
# Specialized Response Models
# ============================================================================


class TriggerStats(BaseModel):
    """Statistics for a trigger"""

    trigger_id: UUID
    total_events: int
    pending_events: int
    delivered_events: int
    failed_events: int
    last_event_at: datetime | None = None


class TriggerHealthCheck(BaseModel):
    """Health check response for a trigger"""

    trigger_id: UUID
    is_healthy: bool
    status: TriggerStatus
    last_triggered_at: datetime | None = None
    expires_at: datetime | None = None
    error_message: str | None = None


class WebhookVerificationChallenge(BaseModel):
    """Challenge-response verification for webhook registration (Slack, Stripe, etc.)"""

    challenge: str


class WebhookReceivedResponse(BaseModel):
    """Response after successfully receiving and storing a webhook"""

    event_id: UUID
    trigger_id: UUID
    event_type: str
    status: TriggerEventStatus
    received_at: datetime


# ============================================================================
# Bulk Operation Models
# ============================================================================


class TriggerBulkStatusUpdate(BaseModel):
    """Update status for multiple triggers"""

    trigger_ids: list[UUID] = Field(min_length=1, max_length=100)
    status: TriggerStatus


class TriggerEventBulkDelete(BaseModel):
    """Delete multiple events (for cleanup)"""

    event_ids: list[UUID] = Field(min_length=1, max_length=100)
