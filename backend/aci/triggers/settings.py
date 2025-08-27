from pydantic import Field
from pydantic_settings import BaseSettings


class TriggersSettings(BaseSettings):
    """Triggers module configuration using environment variables."""
    
    # Slack configuration
    slack_signing_secret: str = Field(
        description="Slack signing secret for webhook verification"
    )
    
    # HubSpot configuration
    hubspot_app_secret: str = Field(
        description="HubSpot app secret for webhook verification"
    )
    
    # Google Pub/Sub configuration
    pubsub_oidc_audience: str = Field(
        description="Expected audience for Google Pub/Sub OIDC token verification"
    )
    google_issuer: str = Field(
        default="https://accounts.google.com",
        description="Expected issuer for Google OIDC tokens"
    )
    
    # GitHub configuration
    github_webhook_secret: str = Field(
        description="GitHub webhook secret for webhook verification"
    )
    
    # Stripe configuration
    stripe_webhook_secret: str = Field(
        description="Stripe webhook secret for webhook verification"
    )
    
    # Linear configuration
    linear_webhook_secret: str = Field(
        description="Linear webhook secret for webhook verification"
    )
    
    # Discord configuration
    discord_public_key: str = Field(
        description="Discord application public key for webhook verification"
    )
    
    # Shopify configuration
    shopify_webhook_secret: str = Field(
        description="Shopify webhook secret for webhook verification"
    )
    
    # Twilio configuration
    twilio_auth_token: str = Field(
        description="Twilio auth token for webhook verification"
    )
    
    # Redis configuration
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for background job queue"
    )
    
    # Database configuration
    database_url: str = Field(
        description="PostgreSQL database URL for storing events"
    )
    
    # Replay protection
    max_timestamp_age_seconds: int = Field(
        default=300,  # 5 minutes
        description="Maximum allowed age for webhook timestamps"
    )
    
    model_config = {
        "env_prefix": "TRIGGERS_",
        "case_sensitive": False
    }


# Global settings instance
settings = TriggersSettings()