from aci.common.enums import HttpLocation
from aci.common.exceptions import NoImplementationFound
from aci.common.logging_setup import get_logger
from aci.common.schemas.security_scheme import OAuth2Scheme, OAuth2SchemeCredentials
from aci.server.function_executors.rest_function_executor import RestFunctionExecutor

logger = get_logger(__name__)


class RestOAuth2FunctionExecutor(RestFunctionExecutor[OAuth2Scheme, OAuth2SchemeCredentials]):
    """
    Function executor for REST OAuth2 functions.
    """

    def _inject_credentials(
        self,
        security_scheme: OAuth2Scheme,
        security_credentials: OAuth2SchemeCredentials,
        headers: dict,
        query: dict,
        body: dict,
        cookies: dict,
    ) -> None:
        """Injects oauth2 access token into the request"""
        logger.debug(
            f"Injecting oauth2 access token into the request, "
            f"security_scheme={security_scheme}, security_credentials={security_credentials}"
        )
        access_token = (
            security_credentials.access_token
            if not security_scheme.prefix
            else f"{security_scheme.prefix} {security_credentials.access_token}"
        )

        match security_scheme.location:
            case HttpLocation.HEADER:
                headers[security_scheme.name] = access_token
            case HttpLocation.QUERY:
                query[security_scheme.name] = access_token
            case HttpLocation.BODY:
                body[security_scheme.name] = access_token
            case HttpLocation.COOKIE:
                cookies[security_scheme.name] = access_token
            case _:
                # should never happen
                logger.error(
                    f"Unsupported OAuth2 location, location={security_scheme.location}, "
                    f"security_scheme={security_scheme}"
                )
                raise NoImplementationFound(
                    f"Unsupported OAuth2 location, location={security_scheme.location}"
                )

        # Inject additional headers if specified
        if security_scheme.additional_headers:
            metadata = security_credentials.metadata or {}
            for header_name, header_value_template in security_scheme.additional_headers.items():
                # Resolve template variables from metadata
                # e.g., "{{orgId}}" -> "2389290"
                header_value = header_value_template
                for key, value in metadata.items():
                    header_value = header_value.replace(f"{{{{{key}}}}}", value)

                headers[header_name] = header_value
                logger.debug(
                    f"Injected additional header, header_name={header_name}, "
                    f"template={header_value_template}, resolved_value={header_value}"
                )
