"""SQLAlchemy models for triggers module."""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for triggers models."""
    pass


class WebhookProvider(str, Enum):
    """Supported webhook providers."""
    # Original providers
    SLACK = "slack"
    HUBSPOT = "hubspot"
    GMAIL = "gmail"
    
    # Development & Project Management
    GITHUB = "github"
    LINEAR = "linear"
    JIRA = "jira"
    TRELLO = "trello"
    
    # Communication & Support
    DISCORD = "discord"
    ZENDESK = "zendesk"
    INTERCOM = "intercom"
    TWILIO = "twilio"
    
    # Business & E-commerce
    STRIPE = "stripe"
    SHOPIFY = "shopify"
    CALENDLY = "calendly"
    NOTION = "notion"


class IncomingEvent(Base):
    """Model for storing incoming webhook events."""
    
    __tablename__ = "incoming_events"
    
    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    
    # Provider that sent the webhook
    provider: Mapped[WebhookProvider] = mapped_column(
        SqlEnum(WebhookProvider),
        nullable=False
    )
    
    # Unique event ID from the provider (for idempotency)
    event_id: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    
    # When we received the event
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    
    # Whether the webhook signature was valid
    signature_valid: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )
    
    # Raw webhook payload
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False
    )
    
    # Whether we've processed this event
    processed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )
    
    # Ensure unique events per provider
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_incoming_events_provider_event_id"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<IncomingEvent(id={self.id}, provider={self.provider.value}, "
            f"event_id={self.event_id}, processed={self.processed})>"
        )