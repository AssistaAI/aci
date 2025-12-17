"""
Trigger Connectors - Base classes and utilities for webhook management.

Each trigger connector handles webhook registration, verification, and event parsing
for a specific third-party service.
"""

from .base import TriggerConnectorBase
from .github import GitHubTriggerConnector
from .gmail import GmailTriggerConnector
from .google_calendar import GoogleCalendarTriggerConnector
from .hubspot import HubSpotTriggerConnector
from .microsoft_calendar import MicrosoftCalendarTriggerConnector
from .notion import NotionTriggerConnector
from .shopify import ShopifyTriggerConnector
from .slack import SlackTriggerConnector

__all__ = [
    "GitHubTriggerConnector",
    "GmailTriggerConnector",
    "GoogleCalendarTriggerConnector",
    "HubSpotTriggerConnector",
    "MicrosoftCalendarTriggerConnector",
    "NotionTriggerConnector",
    "ShopifyTriggerConnector",
    "SlackTriggerConnector",
    "TriggerConnectorBase",
    "get_trigger_connector",
]

# Mapping of app names to their trigger connector classes
_CONNECTOR_MAP = {
    "GITHUB": GitHubTriggerConnector,
    "GMAIL": GmailTriggerConnector,
    "GOOGLE_CALENDAR": GoogleCalendarTriggerConnector,
    "HUBSPOT": HubSpotTriggerConnector,
    "MICROSOFT_CALENDAR": MicrosoftCalendarTriggerConnector,
    "NOTION": NotionTriggerConnector,
    "SHOPIFY": ShopifyTriggerConnector,
    "SLACK": SlackTriggerConnector,
}


def get_trigger_connector(app_name: str) -> TriggerConnectorBase:
    """
    Get the appropriate trigger connector for the given app.

    Args:
        app_name: Name of the app (e.g., "GOOGLE_CALENDAR", "SLACK")

    Returns:
        Instance of the appropriate TriggerConnectorBase subclass

    Raises:
        ValueError: If app_name is not supported
    """
    connector_class = _CONNECTOR_MAP.get(app_name)
    if not connector_class:
        raise ValueError(
            f"No trigger connector available for app '{app_name}'. "
            f"Supported apps: {', '.join(_CONNECTOR_MAP.keys())}"
        )
    return connector_class()
