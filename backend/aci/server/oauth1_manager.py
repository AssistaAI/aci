"""
OAuth 1.0a Manager for apps like Trello.

OAuth 1.0a flow:
1. Get request token (temporary token)
2. User authorizes the request token
3. Exchange request token for access token
"""

import base64
import hashlib
import hmac
import secrets
import time
import urllib.parse

import httpx

from aci.common.exceptions import OAuth1Error
from aci.common.logging_setup import get_logger
from aci.common.schemas.security_scheme import OAuth1SchemeCredentials

logger = get_logger(__name__)


class OAuth1Manager:
    """Manager for OAuth 1.0a authentication flow"""

    def __init__(
        self,
        app_name: str,
        consumer_key: str,
        consumer_secret: str,
        request_token_url: str,
        authorize_url: str,
        access_token_url: str,
        scope: str | None = None,
    ):
        """
        Initialize the OAuth1Manager

        Args:
            app_name: The name of the ACI.dev App
            consumer_key: The consumer key (API key) for OAuth1
            consumer_secret: The consumer secret for OAuth1
            request_token_url: URL to get request token
            authorize_url: URL for user authorization
            access_token_url: URL to exchange request token for access token
            scope: Optional scope (used by Trello for permissions)
        """
        self.app_name = app_name
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.request_token_url = request_token_url
        self.authorize_url = authorize_url
        self.access_token_url = access_token_url
        self.scope = scope

    def _generate_nonce(self) -> str:
        """Generate a random nonce for OAuth1"""
        return secrets.token_hex(16)

    def _generate_timestamp(self) -> str:
        """Generate timestamp for OAuth1"""
        return str(int(time.time()))

    def _percent_encode(self, value: str) -> str:
        """Percent encode a value according to OAuth1 spec"""
        return urllib.parse.quote(str(value), safe="")

    def _create_signature_base_string(
        self,
        method: str,
        url: str,
        params: dict[str, str],
    ) -> str:
        """Create the signature base string for OAuth1 signing"""
        # Sort parameters and encode them
        sorted_params = sorted(params.items())
        param_string = "&".join(
            f"{self._percent_encode(k)}={self._percent_encode(v)}" for k, v in sorted_params
        )

        # Create base string
        base_string = "&".join(
            [
                method.upper(),
                self._percent_encode(url),
                self._percent_encode(param_string),
            ]
        )
        return base_string

    def _create_signature(
        self,
        base_string: str,
        token_secret: str = "",
    ) -> str:
        """Create HMAC-SHA1 signature"""
        # Signing key is consumer_secret&token_secret
        signing_key = (
            f"{self._percent_encode(self.consumer_secret)}&{self._percent_encode(token_secret)}"
        )

        # Create HMAC-SHA1 signature
        signature = hmac.new(
            signing_key.encode("utf-8"),
            base_string.encode("utf-8"),
            hashlib.sha1,
        ).digest()

        return base64.b64encode(signature).decode("utf-8")

    def _create_oauth_header(
        self,
        oauth_params: dict[str, str],
    ) -> str:
        """Create OAuth Authorization header"""
        header_params = ", ".join(
            f'{self._percent_encode(k)}="{self._percent_encode(v)}"'
            for k, v in sorted(oauth_params.items())
        )
        return f"OAuth {header_params}"

    async def get_request_token(
        self,
        callback_url: str,
    ) -> dict[str, str]:
        """
        Get request token (step 1 of OAuth1 flow)

        Args:
            callback_url: The callback URL for OAuth1

        Returns:
            Dictionary with oauth_token and oauth_token_secret
        """
        nonce = self._generate_nonce()
        timestamp = self._generate_timestamp()

        # OAuth parameters
        oauth_params = {
            "oauth_consumer_key": self.consumer_key,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": timestamp,
            "oauth_nonce": nonce,
            "oauth_version": "1.0",
            "oauth_callback": callback_url,
        }

        # Add scope if provided (Trello uses this)
        request_params = dict(oauth_params)
        if self.scope:
            request_params["scope"] = self.scope

        # Create signature
        base_string = self._create_signature_base_string(
            "POST",
            self.request_token_url,
            request_params,
        )
        signature = self._create_signature(base_string)
        oauth_params["oauth_signature"] = signature

        # Make request
        auth_header = self._create_oauth_header(oauth_params)

        try:
            async with httpx.AsyncClient() as client:
                # Add scope as query param if provided
                url = self.request_token_url
                if self.scope:
                    url = f"{url}?scope={self._percent_encode(self.scope)}"

                response = await client.post(
                    url,
                    headers={"Authorization": auth_header},
                    timeout=30.0,
                )
                response.raise_for_status()

                # Parse response (format: oauth_token=xxx&oauth_token_secret=yyy)
                response_data = dict(urllib.parse.parse_qsl(response.text))

                if "oauth_token" not in response_data:
                    logger.error(f"Missing oauth_token in request token response: {response.text}")
                    raise OAuth1Error("Missing oauth_token in request token response")

                logger.info(
                    f"Successfully got request token for {self.app_name}, "
                    f"oauth_token={response_data['oauth_token'][:10]}..."
                )
                return response_data

        except httpx.HTTPError as e:
            logger.error(f"Failed to get request token for {self.app_name}: {e}")
            raise OAuth1Error(f"Failed to get request token: {e}") from e

    def create_authorization_url(
        self,
        oauth_token: str,
        app_name: str | None = None,
    ) -> str:
        """
        Create authorization URL for user to authorize the app (step 2)

        Args:
            oauth_token: The request token from step 1
            app_name: Optional app name to show in Trello's authorization page

        Returns:
            The authorization URL
        """
        params = {"oauth_token": oauth_token}
        if app_name:
            params["name"] = app_name

        query_string = urllib.parse.urlencode(params)
        return f"{self.authorize_url}?{query_string}"

    async def get_access_token(
        self,
        oauth_token: str,
        oauth_token_secret: str,
        oauth_verifier: str,
    ) -> dict[str, str]:
        """
        Exchange request token for access token (step 3)

        Args:
            oauth_token: The authorized request token
            oauth_token_secret: The request token secret from step 1
            oauth_verifier: The verifier from the callback

        Returns:
            Dictionary with oauth_token (access token) and oauth_token_secret
        """
        nonce = self._generate_nonce()
        timestamp = self._generate_timestamp()

        # OAuth parameters
        oauth_params = {
            "oauth_consumer_key": self.consumer_key,
            "oauth_token": oauth_token,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": timestamp,
            "oauth_nonce": nonce,
            "oauth_version": "1.0",
            "oauth_verifier": oauth_verifier,
        }

        # Create signature
        base_string = self._create_signature_base_string(
            "POST",
            self.access_token_url,
            oauth_params,
        )
        signature = self._create_signature(base_string, oauth_token_secret)
        oauth_params["oauth_signature"] = signature

        # Make request
        auth_header = self._create_oauth_header(oauth_params)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.access_token_url,
                    headers={"Authorization": auth_header},
                    timeout=30.0,
                )
                response.raise_for_status()

                # Parse response
                response_data = dict(urllib.parse.parse_qsl(response.text))

                if "oauth_token" not in response_data:
                    logger.error(f"Missing oauth_token in access token response: {response.text}")
                    raise OAuth1Error("Missing oauth_token in access token response")

                logger.info(
                    f"Successfully got access token for {self.app_name}, "
                    f"oauth_token={response_data['oauth_token'][:10]}..."
                )
                return response_data

        except httpx.HTTPError as e:
            logger.error(f"Failed to get access token for {self.app_name}: {e}")
            raise OAuth1Error(f"Failed to get access token: {e}") from e

    def parse_access_token_response(
        self,
        response: dict[str, str],
    ) -> OAuth1SchemeCredentials:
        """
        Parse access token response into OAuth1SchemeCredentials

        Args:
            response: The access token response from the provider

        Returns:
            OAuth1SchemeCredentials
        """
        return OAuth1SchemeCredentials(
            consumer_key=self.consumer_key,
            consumer_secret=self.consumer_secret,
            oauth_token=response["oauth_token"],
            oauth_token_secret=response["oauth_token_secret"],
        )

    def create_auth_header_for_request(
        self,
        method: str,
        url: str,
        oauth_token: str,
        oauth_token_secret: str,
        additional_params: dict[str, str] | None = None,
    ) -> str:
        """
        Create OAuth1 Authorization header for an API request

        Args:
            method: HTTP method
            url: Request URL (without query string)
            oauth_token: The access token
            oauth_token_secret: The access token secret
            additional_params: Additional parameters to include in signature

        Returns:
            The Authorization header value
        """
        nonce = self._generate_nonce()
        timestamp = self._generate_timestamp()

        # OAuth parameters
        oauth_params = {
            "oauth_consumer_key": self.consumer_key,
            "oauth_token": oauth_token,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": timestamp,
            "oauth_nonce": nonce,
            "oauth_version": "1.0",
        }

        # Combine all params for signature
        all_params = dict(oauth_params)
        if additional_params:
            all_params.update(additional_params)

        # Create signature
        base_string = self._create_signature_base_string(method, url, all_params)
        signature = self._create_signature(base_string, oauth_token_secret)
        oauth_params["oauth_signature"] = signature

        return self._create_oauth_header(oauth_params)
