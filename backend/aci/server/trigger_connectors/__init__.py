"""
Trigger Connectors - Base classes and utilities for webhook management.

Each trigger connector handles webhook registration, verification, and event parsing
for a specific third-party service.
"""

from .base import TriggerConnectorBase
from .github import GitHubTriggerConnector
from .hubspot import HubSpotTriggerConnector
from .notion import NotionTriggerConnector
from .shopify import ShopifyTriggerConnector
from .slack import SlackTriggerConnector

__all__ = [
    "TriggerConnectorBase",
    "GitHubTriggerConnector",
    "HubSpotTriggerConnector",
    "NotionTriggerConnector",
    "ShopifyTriggerConnector",
    "SlackTriggerConnector",
]
