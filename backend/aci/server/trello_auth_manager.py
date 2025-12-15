"""
Trello-specific authorization manager.

Trello uses a simplified authorization flow (not full OAuth1 with signatures):
1. Redirect user to: https://trello.com/1/authorize?key=API_KEY&name=AppName&expiration=never&scope=read,write&response_type=token&callback_method=fragment&return_url=CALLBACK
2. User authorizes
3. Trello redirects to return_url with token in URL fragment (#token=xxx)
4. Frontend page captures the token and sends it to backend
"""

import urllib.parse

from aci.common.logging_setup import get_logger

logger = get_logger(__name__)


class TrelloAuthManager:
    """Manager for Trello's simplified token authorization flow."""

    AUTHORIZE_URL = "https://trello.com/1/authorize"

    def __init__(
        self,
        api_key: str,
        app_name: str = "ACI",
    ):
        self.api_key = api_key
        self.app_name = app_name

    def create_authorization_url(
        self,
        return_url: str,
        scope: str = "read,write",
        expiration: str = "never",
    ) -> str:
        """
        Create a Trello authorization URL.

        Args:
            return_url: URL to redirect after authorization (token will be in fragment)
            scope: Trello scope (read, write, or read,write)
            expiration: Token expiration (1hour, 1day, 30days, never)

        Returns:
            The authorization URL
        """
        params = {
            "key": self.api_key,
            "name": self.app_name,
            "expiration": expiration,
            "scope": scope,
            "response_type": "token",
            "callback_method": "fragment",  # Token will be in URL fragment
            "return_url": return_url,
        }

        query_string = urllib.parse.urlencode(params)
        authorization_url = f"{self.AUTHORIZE_URL}?{query_string}"

        logger.info(f"Created Trello authorization URL: {authorization_url}")
        return authorization_url
