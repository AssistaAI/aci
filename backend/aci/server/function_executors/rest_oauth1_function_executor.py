"""
Function executor for REST APIs using OAuth 1.0a authentication.
"""

from aci.common.logging_setup import get_logger
from aci.common.schemas.security_scheme import OAuth1Scheme, OAuth1SchemeCredentials
from aci.server.function_executors.rest_function_executor import RestFunctionExecutor
from aci.server.oauth1_manager import OAuth1Manager

logger = get_logger(__name__)


class RestOAuth1FunctionExecutor(RestFunctionExecutor[OAuth1Scheme, OAuth1SchemeCredentials]):
    """
    Function executor for REST OAuth1 functions.

    For OAuth1, we need to include both `key` and `token` as query parameters
    for Trello-style APIs. The OAuth1 signature is typically handled differently,
    but Trello allows simple key+token authentication.
    """

    def _inject_credentials(
        self,
        security_scheme: OAuth1Scheme,
        security_credentials: OAuth1SchemeCredentials,
        headers: dict,
        query: dict,
        body: dict,
        cookies: dict,
    ) -> None:
        """
        Injects OAuth1 credentials into the request.

        For Trello-style APIs, we inject:
        - key: The consumer key (API key)
        - token: The OAuth access token
        """
        logger.debug(
            f"Injecting OAuth1 credentials into the request, "
            f"consumer_key={security_credentials.consumer_key[:10]}..."
        )

        # Trello uses simple key+token query params
        query["key"] = security_credentials.consumer_key
        query["token"] = security_credentials.oauth_token

    def _build_oauth1_header(
        self,
        method: str,
        url: str,
        security_scheme: OAuth1Scheme,
        security_credentials: OAuth1SchemeCredentials,
    ) -> str:
        """
        Build OAuth1 Authorization header for APIs that require signed requests.

        Note: This is not currently used for Trello, which uses simple key+token params,
        but is available for other OAuth1 APIs that require signed headers.
        """
        oauth1_manager = OAuth1Manager(
            app_name="",  # Not needed for header generation
            consumer_key=security_credentials.consumer_key,
            consumer_secret=security_credentials.consumer_secret,
            request_token_url="",
            authorize_url="",
            access_token_url="",
        )

        return oauth1_manager.create_auth_header_for_request(
            method=method,
            url=url,
            oauth_token=security_credentials.oauth_token,
            oauth_token_secret=security_credentials.oauth_token_secret,
        )
