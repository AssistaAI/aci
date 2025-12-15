from typing import Annotated
from uuid import UUID

from authlib.jose import jwt
from fastapi import APIRouter, Body, Depends, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from aci.common.db import crud
from aci.common.db.sql_models import LinkedAccount
from aci.common.enums import SecurityScheme
from aci.common.exceptions import (
    AppConfigurationNotFound,
    AppNotFound,
    AuthenticationError,
    LinkedAccountAlreadyExists,
    LinkedAccountNotFound,
    NoImplementationFound,
    OAuth1Error,
    OAuth2Error,
    ProjectNotFound,
)
from aci.common.logging_setup import get_logger
from aci.common.schemas.linked_accounts import (
    LinkedAccountAPIKeyCreate,
    LinkedAccountDefaultCreate,
    LinkedAccountNoAuthCreate,
    LinkedAccountOAuth1Create,
    LinkedAccountOAuth1CreateState,
    LinkedAccountOAuth2Create,
    LinkedAccountOAuth2CreateState,
    LinkedAccountPublic,
    LinkedAccountsList,
    LinkedAccountUpdate,
    LinkedAccountWithCredentials,
)
from aci.common.schemas.security_scheme import (
    APIKeySchemeCredentials,
    NoAuthSchemeCredentials,
)
from aci.server import config, quota_manager
from aci.server import dependencies as deps
from aci.server import security_credentials_manager as scm
from aci.server.oauth1_manager import OAuth1Manager
from aci.server.oauth2_manager import OAuth2Manager
from aci.server.trello_auth_manager import TrelloAuthManager

router = APIRouter()
logger = get_logger(__name__)

LINKED_ACCOUNTS_OAUTH2_CALLBACK_ROUTE_NAME = "linked_accounts_oauth2_callback"
LINKED_ACCOUNTS_OAUTH1_CALLBACK_ROUTE_NAME = "linked_accounts_oauth1_callback"

"""
IMPORTANT NOTE:
The api endpoints (both URL design and implementation) for linked accounts are currently a bit hacky, especially for OAuth2 account type.
Will revisit and potentially refactor later once we have more time and more clarity on the requirements.
There are a few tricky parts:
- There are different types of linked accounts (OAuth2, API key, etc.) And the OAuth2 type linking flow
  is very different from the other types.
- For OAuth2 account linking, we want to support quite a few scenarios that might require different
  flows or setups. But for simplicity, we currently hack together an implementation that works for all,
  with some compromises on the security. (well, I'd say it's still secure enough for this stage but need to
  revisit and improve later.). These OAuth2 scenarios include:
  - Scenario 1: allow (our direct) client to link an OAuth2 account on developer portal.
  - Scenario 2: allow (client's) end user to link an OAuth2 account with the redirect url.
    - Scenario 2.1: Client generates the redirect url and sends it to the end user.
    - Scenario 2.2: Amid end user's conversation with the client's AI agent, the AI agent generates the
      redirect url for OAuth2 account linking. (If the App the end user needs access too is not yet authenticated)
  - Scenario 3: allow (our direct) client to generate a link to a webpage that we host for OAuth2 account linking.
    Different from Scenario 2.1, the link is not a redirect url but a link to a webpage that we host. And potentially
    can work for other types of accounting linking, e.g., allowend user to input API key.

- Also see: https://www.notion.so/Replace-authlib-to-support-both-browser-and-cli-authentication-16f8378d6a4780eda593ef149a205198
"""


@router.post("/default", response_model=LinkedAccountPublic, include_in_schema=False)
async def link_account_with_aci_default_credentials(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    body: Annotated[LinkedAccountDefaultCreate, Body()],
) -> LinkedAccount:
    """
    Create a linked account under an App using default credentials (e.g., API key, OAuth2, etc.)
    provided by ACI.
    If there is no default credentials provided by ACI for the specific App, the linked account will not be created,
    and an error will be returned.
    """
    logger.info(
        f"Linking account with ACI default credentials, "
        f"app_name={body.app_name}, "
        f"linked_account_owner_id={body.linked_account_owner_id}"
    )
    # TODO: some duplicate code with other linked account creation routes
    app_configuration = crud.app_configurations.get_app_configuration(
        context.db_session, context.project.id, body.app_name
    )
    if not app_configuration:
        logger.error(
            f"Failed to link account with ACI default credentials, app configuration not found, "
            f"app_name={body.app_name}"
        )
        raise AppConfigurationNotFound(
            f"configuration for app={body.app_name} not found, please configure the app first {config.DEV_PORTAL_URL}/apps/{body.app_name}"
        )

    # need to make sure the App actully has default credentials provided by ACI
    app_default_credentials = app_configuration.app.default_security_credentials_by_scheme.get(
        app_configuration.security_scheme
    )
    if not app_default_credentials:
        logger.error(
            f"Failed to link account with ACI default credentials, no default credentials provided by ACI, "
            f"app_name={body.app_name} "
            f"security_scheme={app_configuration.security_scheme}"
        )
        # TODO: consider choosing a different exception type?
        raise NoImplementationFound(
            f"No default credentials provided by ACI for app={body.app_name}, "
            f"security_scheme={app_configuration.security_scheme}"
        )

    linked_account = crud.linked_accounts.get_linked_account(
        context.db_session,
        context.project.id,
        body.app_name,
        body.linked_account_owner_id,
    )
    # TODO: same as OAuth2 linked account creation, we might want to separate the logic for updating and creating a linked account
    # or give warning to clients if the linked account already exists to avoid accidental overwriting the account
    if linked_account:
        # TODO: support updating any type of linked account to use ACI default credentials
        logger.error(
            f"Failed to link account with ACI default credentials, linked account already exists, "
            f"linked_account_owner_id={body.linked_account_owner_id} "
            f"app_name={body.app_name}"
        )
        raise LinkedAccountAlreadyExists(
            f"linked account with linked_account_owner_id={body.linked_account_owner_id} already exists for app={body.app_name}"
        )
    else:
        # Enforce linked accounts quota before creating new account
        quota_manager.enforce_linked_accounts_creation_quota(
            context.db_session, context.project.org_id, body.linked_account_owner_id
        )

        logger.info(
            f"Creating linked account with ACI default credentials, "
            f"linked_account_owner_id={body.linked_account_owner_id}, "
            f"app_name={body.app_name}"
        )
        linked_account = crud.linked_accounts.create_linked_account(
            context.db_session,
            context.project.id,
            body.app_name,
            body.linked_account_owner_id,
            app_configuration.security_scheme,
            enabled=True,
        )
    context.db_session.commit()

    return linked_account


@router.post("/no-auth", response_model=LinkedAccountPublic)
async def link_account_with_no_auth(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    body: LinkedAccountNoAuthCreate,
) -> LinkedAccount:
    """
    Create a linked account under an App that requires no authentication.
    """
    logger.info(
        f"Linking no_auth account, app_name={body.app_name}, "
        f"linked_account_owner_id={body.linked_account_owner_id}"
    )
    # TODO: duplicate code with other linked account creation routes, refactor later
    app_configuration = crud.app_configurations.get_app_configuration(
        context.db_session, context.project.id, body.app_name
    )
    if not app_configuration:
        logger.error(
            f"Failed to link no_auth account, app configuration not found, app_name={body.app_name}"
        )
        raise AppConfigurationNotFound(
            f"configuration for app={body.app_name} not found, please configure the app first {config.DEV_PORTAL_URL}/apps/{body.app_name}"
        )
    if app_configuration.security_scheme != SecurityScheme.NO_AUTH:
        logger.error(
            f"Failed to link no_auth account, app configuration security scheme is not no_auth, "
            f"app_name={body.app_name} security_scheme={app_configuration.security_scheme}"
        )
        raise NoImplementationFound(
            f"the security_scheme configured for app={body.app_name} is "
            f"{app_configuration.security_scheme}, not no_auth"
        )
    linked_account = crud.linked_accounts.get_linked_account(
        context.db_session,
        context.project.id,
        body.app_name,
        body.linked_account_owner_id,
    )
    if linked_account:
        logger.error(
            f"Failed to link no_auth account, linked account already exists, "
            f"linked_account_owner_id={body.linked_account_owner_id} app_name={body.app_name}"
        )
        raise LinkedAccountAlreadyExists(
            f"linked account with linked_account_owner_id={body.linked_account_owner_id} already exists for app={body.app_name}"
        )
    else:
        # Enforce linked accounts quota before creating new account
        quota_manager.enforce_linked_accounts_creation_quota(
            context.db_session, context.project.org_id, body.linked_account_owner_id
        )

        logger.info(
            f"Creating no_auth linked account, "
            f"linked_account_owner_id={body.linked_account_owner_id}, "
            f"app_name={body.app_name}"
        )
        linked_account = crud.linked_accounts.create_linked_account(
            context.db_session,
            context.project.id,
            body.app_name,
            body.linked_account_owner_id,
            SecurityScheme.NO_AUTH,
            NoAuthSchemeCredentials(),
            enabled=True,
        )

    context.db_session.commit()

    return linked_account


@router.post("/api-key", response_model=LinkedAccountPublic)
async def link_account_with_api_key(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    body: LinkedAccountAPIKeyCreate,
) -> LinkedAccount:
    """
    Create a linked account under an API key based App.
    """
    logger.info(
        f"Linking api_key account, app_name={body.app_name}, "
        f"linked_account_owner_id={body.linked_account_owner_id}"
    )
    app_configuration = crud.app_configurations.get_app_configuration(
        context.db_session, context.project.id, body.app_name
    )
    if not app_configuration:
        logger.error(
            f"Failed to link api_key account, app configuration not found, app_name={body.app_name}"
        )
        raise AppConfigurationNotFound(
            f"configuration for app={body.app_name} not found, please configure the app first {config.DEV_PORTAL_URL}/apps/{body.app_name}"
        )
    # TODO: for now we require the security_schema used for accounts under an App must be the same as the security_schema configured in the app
    # configuration. But in the future, we might lift this restriction and allow any security_schema as long as the App supports it.
    if app_configuration.security_scheme != SecurityScheme.API_KEY:
        logger.error(
            f"Failed to link api_key account, app configuration security scheme is, "
            f"{app_configuration.security_scheme} instead of api_key "
            f"app_name={body.app_name} security_scheme={app_configuration.security_scheme}"
        )
        # TODO: consider choosing a different exception type?
        raise NoImplementationFound(
            f"the security_scheme configured for app={body.app_name} is "
            f"{app_configuration.security_scheme}, not api_key"
        )
    linked_account = crud.linked_accounts.get_linked_account(
        context.db_session,
        context.project.id,
        body.app_name,
        body.linked_account_owner_id,
    )
    security_credentials = APIKeySchemeCredentials(
        secret_key=body.api_key,
    )
    # TODO: same as other linked account creation, we might want to separate the logic for updating and creating a linked account
    # or give warning to clients if the linked account already exists to avoid accidental overwriting the account
    if linked_account:
        # TODO: support updating api_key linked account
        logger.error(
            f"Failed to link api_key account, linked account already exists, "
            f"linked_account_owner_id={body.linked_account_owner_id} app_name={body.app_name}"
        )
        raise LinkedAccountAlreadyExists(
            f"linked account with linked_account_owner_id={body.linked_account_owner_id} already exists for app={body.app_name}"
        )
    else:
        # Enforce linked accounts quota before creating new account
        quota_manager.enforce_linked_accounts_creation_quota(
            context.db_session, context.project.org_id, body.linked_account_owner_id
        )

        logger.info(
            f"Creating api_key linked account, "
            f"linked_account_owner_id={body.linked_account_owner_id}, "
            f"app_name={body.app_name}"
        )
        linked_account = crud.linked_accounts.create_linked_account(
            context.db_session,
            context.project.id,
            body.app_name,
            body.linked_account_owner_id,
            SecurityScheme.API_KEY,
            security_credentials,
            enabled=True,
        )

    context.db_session.commit()

    return linked_account


@router.get("/oauth2")
async def link_oauth2_account(
    request: Request,
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    query_params: Annotated[LinkedAccountOAuth2Create, Query()],
) -> dict:
    """
    Start an OAuth2 account linking process.
    It will return a redirect url (as a string, instead of RedirectResponse) to the OAuth2 provider's authorization endpoint.
    """
    app_configuration = crud.app_configurations.get_app_configuration(
        context.db_session, context.project.id, query_params.app_name
    )
    if not app_configuration:
        logger.error(
            f"Failed to link OAuth2 account, app configuration not found, "
            f"app_name={query_params.app_name}"
        )
        raise AppConfigurationNotFound(
            f"configuration for app={query_params.app_name} not found, please configure the app first {config.DEV_PORTAL_URL}/apps/{query_params.app_name}"
        )
    # TODO: for now we require the security_schema used for accounts under an App must be the same as the security_schema configured in the app
    # configuration. But in the future, we might lift this restriction and allow any security_schema as long the App supports it.
    if app_configuration.security_scheme != SecurityScheme.OAUTH2:
        logger.error(
            f"Failed to link OAuth2 account, app configuration security scheme is not OAuth2, "
            f"app_name={query_params.app_name} security_scheme={app_configuration.security_scheme}"
        )
        raise NoImplementationFound(
            f"The security_scheme configured in app={query_params.app_name} is "
            f"{app_configuration.security_scheme}, not OAuth2"
        )

    # Enforce linked accounts quota before creating new account
    quota_manager.enforce_linked_accounts_creation_quota(
        context.db_session, context.project.org_id, query_params.linked_account_owner_id
    )

    oauth2_scheme = scm.get_app_configuration_oauth2_scheme(
        app_configuration.app, app_configuration
    )

    oauth2_manager = OAuth2Manager(
        app_name=query_params.app_name,
        client_id=oauth2_scheme.client_id,
        client_secret=oauth2_scheme.client_secret,
        scope=oauth2_scheme.scope,
        authorize_url=oauth2_scheme.authorize_url,
        access_token_url=oauth2_scheme.access_token_url,
        refresh_token_url=oauth2_scheme.refresh_token_url,
        token_endpoint_auth_method=oauth2_scheme.token_endpoint_auth_method,
    )

    # create and encode the state payload.
    # NOTE: the state payload is jwt encoded (signed), but it's not encrypted, anyone can decode it
    # TODO: add expiration check to the state payload for extra security
    # LinkedIn doesn't support PKCE, so don't generate code_verifier for it
    code_verifier = (
        None if query_params.app_name == "LINKEDIN" else OAuth2Manager.generate_code_verifier()
    )

    oauth2_state = LinkedAccountOAuth2CreateState(
        app_name=query_params.app_name,
        project_id=context.project.id,
        linked_account_owner_id=query_params.linked_account_owner_id,
        client_id=oauth2_scheme.client_id,
        code_verifier=code_verifier,
        after_oauth2_link_redirect_url=query_params.after_oauth2_link_redirect_url,
    )

    oauth2_state_jwt = jwt.encode(
        {"alg": config.JWT_ALGORITHM},
        oauth2_state.model_dump(mode="json", exclude_none=True),
        config.SIGNING_KEY,
    ).decode()  # decode() is needed to convert the bytes to a string (not decoding the jwt payload) for this jwt library.

    path = request.url_for(LINKED_ACCOUNTS_OAUTH2_CALLBACK_ROUTE_NAME).path
    redirect_uri = oauth2_scheme.redirect_url or f"{config.REDIRECT_URI_BASE}{path}"
    authorization_url = await oauth2_manager.create_authorization_url(
        redirect_uri=redirect_uri,
        state=oauth2_state_jwt,
        code_verifier=code_verifier or "",  # Pass empty string if None to avoid issues
    )

    # rewrite the authorization url for some apps that need special handling
    # TODO: this is hacky and need to refactor this in the future
    authorization_url = OAuth2Manager.rewrite_oauth2_authorization_url(
        query_params.app_name, authorization_url
    )

    logger.info(f"Linking oauth2 account with authorization_url={authorization_url}")
    return {"url": authorization_url}


@router.get(
    "/oauth2/callback",
    name=LINKED_ACCOUNTS_OAUTH2_CALLBACK_ROUTE_NAME,
    response_model=LinkedAccountWithCredentials,
    response_model_exclude_none=True,
)
async def linked_accounts_oauth2_callback(
    request: Request,
    db_session: Annotated[Session, Depends(deps.yield_db_session)],
) -> LinkedAccount | RedirectResponse:
    """
    Callback endpoint for OAuth2 account linking.
    - A linked account (with necessary credentials from the OAuth2 provider) will be created in the database.
    """
    # check for errors
    error = request.query_params.get("error")
    error_description = request.query_params.get("error_description")
    if error:
        logger.error(
            f"OAuth2 account linking callback received, error={error}, "
            f"error_description={error_description}"
        )
        raise OAuth2Error(
            f"oauth2 account linking callback error: {error}, error_description: {error_description}"
        )

    # check for code
    code = request.query_params.get("code")
    if not code:
        logger.error("OAuth2 account linking callback received, missing code")
        raise OAuth2Error("missing code parameter during account linking")

    # check for state
    state_jwt = request.query_params.get("state")
    if not state_jwt:
        logger.error(
            "OAuth2 account linking callback received, missing state",
        )
        raise OAuth2Error("missing state parameter during account linking")

    # decode the state payload
    try:
        state = LinkedAccountOAuth2CreateState.model_validate(
            jwt.decode(state_jwt, config.SIGNING_KEY)
        )
        logger.info(
            f"OAuth2 account linking callback received, decoded state={state.model_dump(exclude_none=True)}",
        )
    except Exception as e:
        logger.exception(f"Failed to decode OAuth2 state, error={e}")
        raise AuthenticationError("invalid state parameter during account linking") from e

    # check if the app exists
    app = crud.apps.get_app(db_session, state.app_name, False, False)
    if not app:
        logger.error(
            f"Unable to continue with account linking, app not found app_name={state.app_name}"
        )
        raise AppNotFound(f"app={state.app_name} not found")

    # check app configuration
    # - exists
    # - configuration is OAuth2
    # - client_id matches the one used at the start of the OAuth2 flow
    app_configuration = crud.app_configurations.get_app_configuration(
        db_session, state.project_id, state.app_name
    )
    if not app_configuration:
        logger.error(
            f"Unable to continue with account linking, app configuration not found "
            f"app_name={state.app_name}"
        )
        raise AppConfigurationNotFound(f"app configuration for app={state.app_name} not found")
    if app_configuration.security_scheme != SecurityScheme.OAUTH2:
        logger.error(
            f"Unable to continue with account linking, app configuration is not OAuth2 "
            f"app_name={state.app_name}"
        )
        raise NoImplementationFound(f"app configuration for app={state.app_name} is not OAuth2")

    # create oauth2 manager
    oauth2_scheme = scm.get_app_configuration_oauth2_scheme(
        app_configuration.app, app_configuration
    )
    if oauth2_scheme.client_id != state.client_id:
        logger.error(
            f"Unable to continue with account linking, client_id of state doesn't match client_id of app configuration "
            f"app_name={state.app_name} "
            f"client_id={oauth2_scheme.client_id} "
            f"state_client_id={state.client_id}"
        )
        raise OAuth2Error("client_id mismatch during account linking")

    logger.info(
        f"Creating OAuth2Manager for callback, "
        f"app_name={state.app_name}, "
        f"client_id={oauth2_scheme.client_id[:10]}..., "
        f"client_secret_length={len(oauth2_scheme.client_secret)}, "
        f"token_endpoint_auth_method={oauth2_scheme.token_endpoint_auth_method}, "
        f"access_token_url={oauth2_scheme.access_token_url}"
    )

    oauth2_manager = OAuth2Manager(
        app_name=state.app_name,
        client_id=oauth2_scheme.client_id,
        client_secret=oauth2_scheme.client_secret,
        scope=oauth2_scheme.scope,
        authorize_url=oauth2_scheme.authorize_url,
        access_token_url=oauth2_scheme.access_token_url,
        refresh_token_url=oauth2_scheme.refresh_token_url,
        token_endpoint_auth_method=oauth2_scheme.token_endpoint_auth_method,
    )

    path = request.url_for(LINKED_ACCOUNTS_OAUTH2_CALLBACK_ROUTE_NAME).path
    redirect_uri = oauth2_scheme.redirect_url or f"{config.REDIRECT_URI_BASE}{path}"

    logger.info(
        f"About to fetch token for {state.app_name}, "
        f"redirect_uri={redirect_uri}, "
        f"code_verifier={'<none>' if not state.code_verifier else '<present>'}"
    )

    token_response = await oauth2_manager.fetch_token(
        redirect_uri=redirect_uri,
        code=code,
        code_verifier=state.code_verifier
        or "",  # Pass empty string if None for apps that don't support PKCE
    )
    security_credentials = await oauth2_manager.parse_fetch_token_response(token_response)

    # if the linked account already exists, update it, otherwise create a new one
    # TODO: consider separating the logic for updating and creating a linked account or give warning to clients
    # if the linked account already exists to avoid accidental overwriting the account
    # TODO: try/except, retry?
    linked_account = crud.linked_accounts.get_linked_account(
        db_session,
        state.project_id,
        state.app_name,
        state.linked_account_owner_id,
    )
    if linked_account:
        logger.info(
            f"Updating oauth2 credentials for linked account, linked_account_id={linked_account.id}"
        )
        linked_account = crud.linked_accounts.update_linked_account_credentials(
            db_session, linked_account, security_credentials
        )
    else:
        # Get the organization ID from the project
        project = crud.projects.get_project(db_session, state.project_id)
        if not project:
            logger.error(
                f"project not found when creating linked account project_id={state.project_id}"
            )
            raise ProjectNotFound(f"Project with ID {state.project_id} not found")
        org_id = project.org_id
        # Enforce linked accounts quota before creating new account
        quota_manager.enforce_linked_accounts_creation_quota(
            db_session, org_id, state.linked_account_owner_id
        )

        logger.info(
            f"Creating oauth2 linked account, "
            f"app_name={state.app_name}, "
            f"linked_account_owner_id={state.linked_account_owner_id}"
        )
        linked_account = crud.linked_accounts.create_linked_account(
            db_session,
            project_id=state.project_id,
            app_name=state.app_name,
            linked_account_owner_id=state.linked_account_owner_id,
            security_scheme=SecurityScheme.OAUTH2,
            security_credentials=security_credentials,
            enabled=True,
        )
    db_session.commit()

    if state.after_oauth2_link_redirect_url:
        return RedirectResponse(
            url=state.after_oauth2_link_redirect_url, status_code=status.HTTP_302_FOUND
        )

    return linked_account


# ============================================================================
# Trello-specific authorization endpoints
# Trello uses a simplified token flow (not full OAuth1/2) where the token
# is returned in the URL fragment. Frontend captures it and sends to backend.
# ============================================================================


class TrelloAuthCreate(BaseModel):
    """Request model for initiating Trello auth"""

    linked_account_owner_id: str
    api_key: str  # User-provided API key
    after_trello_link_redirect_url: str | None = None


class TrelloAuthState(BaseModel):
    """State for Trello auth callback"""

    project_id: UUID
    linked_account_owner_id: str
    api_key: str
    after_trello_link_redirect_url: str | None = None


class TrelloTokenSubmit(BaseModel):
    """Request model for submitting Trello token from frontend"""

    token: str
    state: str  # JWT-encoded TrelloAuthState


TRELLO_CALLBACK_ROUTE_NAME = "trello_auth_callback"


@router.get("/trello/auth")
async def initiate_trello_auth(
    request: Request,
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    query_params: Annotated[TrelloAuthCreate, Query()],
) -> dict:
    """
    Start Trello account linking process.
    Returns a URL to redirect the user to Trello for authorization.
    After authorization, Trello redirects to our frontend callback page with the token in the URL fragment.
    """
    app_configuration = crud.app_configurations.get_app_configuration(
        context.db_session, context.project.id, "TRELLO"
    )
    if not app_configuration:
        logger.error("Failed to initiate Trello auth, app configuration not found")
        raise AppConfigurationNotFound(
            f"configuration for app=TRELLO not found, please configure the app first {config.DEV_PORTAL_URL}/apps/TRELLO"
        )

    if app_configuration.security_scheme != SecurityScheme.API_KEY:
        logger.error(
            f"Failed to initiate Trello auth, app configuration security scheme is not API_KEY, "
            f"security_scheme={app_configuration.security_scheme}"
        )
        raise NoImplementationFound(
            f"The security_scheme configured for TRELLO is {app_configuration.security_scheme}, "
            "but Trello auth requires api_key scheme"
        )

    # Enforce linked accounts quota
    quota_manager.enforce_linked_accounts_creation_quota(
        context.db_session, context.project.org_id, query_params.linked_account_owner_id
    )

    # Validate user-provided API key
    if not query_params.api_key or not query_params.api_key.strip():
        logger.error("Trello API key not provided by user")
        raise ValueError("Trello API key is required")

    # Create state for the callback
    state = TrelloAuthState(
        project_id=context.project.id,
        linked_account_owner_id=query_params.linked_account_owner_id,
        api_key=query_params.api_key,  # Use user-provided API key
        after_trello_link_redirect_url=query_params.after_trello_link_redirect_url,
    )

    state_jwt = jwt.encode(
        {"alg": config.JWT_ALGORITHM},
        state.model_dump(mode="json", exclude_none=True),
        config.SIGNING_KEY,
    ).decode()

    # Create the frontend callback URL (this page will capture the token from fragment)
    # The frontend page will then POST the token to our /trello/token endpoint
    callback_path = request.url_for(TRELLO_CALLBACK_ROUTE_NAME).path
    frontend_callback_url = f"{config.REDIRECT_URI_BASE}{callback_path}?state={state_jwt}"

    # Create Trello authorization URL
    trello_auth_manager = TrelloAuthManager(api_key=query_params.api_key, app_name="ACI")
    authorization_url = trello_auth_manager.create_authorization_url(
        return_url=frontend_callback_url,
        scope="read,write",
        expiration="never",
    )

    logger.info(f"Initiating Trello auth, authorization_url={authorization_url}")
    return {"url": authorization_url}


@router.get("/trello/callback", name=TRELLO_CALLBACK_ROUTE_NAME)
async def trello_auth_callback(
    request: Request,
    state: str = Query(..., description="JWT-encoded state"),
) -> RedirectResponse:
    """
    Trello auth callback page.
    This endpoint serves an HTML page that:
    1. Captures the token from the URL fragment (not accessible server-side)
    2. Sends it to our /trello/token endpoint
    """
    # Return an HTML page that captures the token and submits it
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Connecting Trello...</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }}
            .container {{
                text-align: center;
                background: white;
                padding: 40px 60px;
                border-radius: 16px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            }}
            .spinner {{
                width: 50px;
                height: 50px;
                border: 4px solid #f3f3f3;
                border-top: 4px solid #667eea;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin: 0 auto 20px;
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            h2 {{ color: #333; margin-bottom: 10px; }}
            p {{ color: #666; }}
            .error {{ color: #e74c3c; display: none; }}
            .success {{ color: #27ae60; display: none; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="spinner" id="spinner"></div>
            <h2 id="title">Connecting your Trello account...</h2>
            <p id="message">Please wait while we complete the authorization.</p>
            <p class="error" id="error"></p>
            <p class="success" id="success"></p>
        </div>
        <script>
            (function() {{
                const state = "{state}";

                // Get token from URL fragment
                const hash = window.location.hash;
                const tokenMatch = hash.match(/token=([^&]+)/);

                if (!tokenMatch) {{
                    document.getElementById('spinner').style.display = 'none';
                    document.getElementById('title').textContent = 'Authorization Failed';
                    document.getElementById('message').style.display = 'none';
                    document.getElementById('error').style.display = 'block';
                    document.getElementById('error').textContent = 'No token received from Trello. Please try again.';
                    return;
                }}

                const token = tokenMatch[1];

                // Submit token to backend
                fetch('/v1/linked-accounts/trello/token', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{
                        token: token,
                        state: state
                    }})
                }})
                .then(response => response.json())
                .then(data => {{
                    document.getElementById('spinner').style.display = 'none';
                    if (data.success) {{
                        document.getElementById('title').textContent = 'Success!';
                        document.getElementById('message').style.display = 'none';
                        document.getElementById('success').style.display = 'block';
                        document.getElementById('success').textContent = 'Your Trello account has been connected.';

                        // Redirect if there's a redirect URL
                        if (data.redirect_url) {{
                            setTimeout(() => {{
                                window.location.href = data.redirect_url;
                            }}, 1500);
                        }}
                    }} else {{
                        document.getElementById('title').textContent = 'Error';
                        document.getElementById('message').style.display = 'none';
                        document.getElementById('error').style.display = 'block';
                        document.getElementById('error').textContent = data.error || 'Failed to connect Trello account.';
                    }}
                }})
                .catch(error => {{
                    document.getElementById('spinner').style.display = 'none';
                    document.getElementById('title').textContent = 'Error';
                    document.getElementById('message').style.display = 'none';
                    document.getElementById('error').style.display = 'block';
                    document.getElementById('error').textContent = 'Network error. Please try again.';
                    console.error('Error:', error);
                }});
            }})();
        </script>
    </body>
    </html>
    """
    from starlette.responses import HTMLResponse

    return HTMLResponse(content=html_content)


@router.post("/trello/token")
async def submit_trello_token(
    body: TrelloTokenSubmit,
    db_session: Annotated[Session, Depends(deps.yield_db_session)],
) -> dict:
    """
    Receive the Trello token from the frontend callback page and create/update the linked account.
    """
    # Decode state
    try:
        state = TrelloAuthState.model_validate(jwt.decode(body.state, config.SIGNING_KEY))
        logger.info(f"Trello token submission, project_id={state.project_id}")
    except Exception as e:
        logger.exception(f"Failed to decode Trello auth state: {e}")
        return {"success": False, "error": "Invalid or expired authorization state"}

    # Get app configuration
    app_configuration = crud.app_configurations.get_app_configuration(
        db_session, state.project_id, "TRELLO"
    )
    if not app_configuration:
        logger.error("App configuration not found during Trello token submission")
        return {"success": False, "error": "Trello app configuration not found"}

    # Create credentials with API_KEY:TOKEN format for the existing api_key flow
    combined_credential = f"{state.api_key}:{body.token}"
    security_credentials = APIKeySchemeCredentials(secret_key=combined_credential)

    # Create or update linked account
    linked_account = crud.linked_accounts.get_linked_account(
        db_session,
        state.project_id,
        "TRELLO",
        state.linked_account_owner_id,
    )

    if linked_account:
        logger.info(f"Updating Trello credentials for linked account, id={linked_account.id}")
        linked_account = crud.linked_accounts.update_linked_account_credentials(
            db_session, linked_account, security_credentials
        )
    else:
        # Get org_id from project for quota enforcement
        project = crud.projects.get_project(db_session, state.project_id)
        if not project:
            return {"success": False, "error": "Project not found"}

        quota_manager.enforce_linked_accounts_creation_quota(
            db_session, project.org_id, state.linked_account_owner_id
        )

        logger.info(
            f"Creating Trello linked account, "
            f"linked_account_owner_id={state.linked_account_owner_id}"
        )
        linked_account = crud.linked_accounts.create_linked_account(
            db_session,
            project_id=state.project_id,
            app_name="TRELLO",
            linked_account_owner_id=state.linked_account_owner_id,
            security_scheme=SecurityScheme.API_KEY,
            security_credentials=security_credentials,
            enabled=True,
        )

    db_session.commit()

    response = {"success": True, "linked_account_id": str(linked_account.id)}
    if state.after_trello_link_redirect_url:
        response["redirect_url"] = state.after_trello_link_redirect_url

    return response


# ============================================================================
# OAuth1 endpoints (for apps that use full OAuth1.0a with signatures)
# ============================================================================


@router.get("/oauth1")
async def link_oauth1_account(
    request: Request,
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    query_params: Annotated[LinkedAccountOAuth1Create, Query()],
) -> dict:
    """
    Start an OAuth1 account linking process.
    It will return a redirect url (as a string) to the OAuth1 provider's authorization endpoint.
    """
    app_configuration = crud.app_configurations.get_app_configuration(
        context.db_session, context.project.id, query_params.app_name
    )
    if not app_configuration:
        logger.error(
            f"Failed to link OAuth1 account, app configuration not found, "
            f"app_name={query_params.app_name}"
        )
        raise AppConfigurationNotFound(
            f"configuration for app={query_params.app_name} not found, please configure the app first {config.DEV_PORTAL_URL}/apps/{query_params.app_name}"
        )

    if app_configuration.security_scheme != SecurityScheme.OAUTH1:
        logger.error(
            f"Failed to link OAuth1 account, app configuration security scheme is not OAuth1, "
            f"app_name={query_params.app_name} security_scheme={app_configuration.security_scheme}"
        )
        raise NoImplementationFound(
            f"The security_scheme configured in app={query_params.app_name} is "
            f"{app_configuration.security_scheme}, not OAuth1"
        )

    # Enforce linked accounts quota before creating new account
    quota_manager.enforce_linked_accounts_creation_quota(
        context.db_session, context.project.org_id, query_params.linked_account_owner_id
    )

    oauth1_scheme = scm.get_app_configuration_oauth1_scheme(
        app_configuration.app, app_configuration
    )

    oauth1_manager = OAuth1Manager(
        app_name=query_params.app_name,
        consumer_key=oauth1_scheme.consumer_key,
        consumer_secret=oauth1_scheme.consumer_secret,
        request_token_url=oauth1_scheme.request_token_url,
        authorize_url=oauth1_scheme.authorize_url,
        access_token_url=oauth1_scheme.access_token_url,
        scope=oauth1_scheme.scope,
    )

    # Get the callback URL
    path = request.url_for(LINKED_ACCOUNTS_OAUTH1_CALLBACK_ROUTE_NAME).path
    callback_url = f"{config.REDIRECT_URI_BASE}{path}"

    # Get request token
    request_token_response = await oauth1_manager.get_request_token(callback_url)
    oauth_token = request_token_response["oauth_token"]
    oauth_token_secret = request_token_response["oauth_token_secret"]

    # Create state payload
    oauth1_state = LinkedAccountOAuth1CreateState(
        app_name=query_params.app_name,
        project_id=context.project.id,
        linked_account_owner_id=query_params.linked_account_owner_id,
        consumer_key=oauth1_scheme.consumer_key,
        oauth_token_secret=oauth_token_secret,
        after_oauth1_link_redirect_url=query_params.after_oauth1_link_redirect_url,
    )

    oauth1_state_jwt = jwt.encode(
        {"alg": config.JWT_ALGORITHM},
        oauth1_state.model_dump(mode="json", exclude_none=True),
        config.SIGNING_KEY,
    ).decode()

    # Create authorization URL with state encoded in oauth_token
    # Note: OAuth1 doesn't have a standard state parameter, so we'll use it in the callback
    # We store the state JWT in the session or include it in the callback handling
    authorization_url = oauth1_manager.create_authorization_url(
        oauth_token=oauth_token,
        app_name=query_params.app_name,
    )

    # Store state temporarily - we'll need to pass it through somehow
    # For OAuth1, we can store the mapping of oauth_token -> state in the database or cache
    # For simplicity, we'll encode the state in a special way
    # Actually, let's use the oauth_token as a key to store state temporarily
    crud.oauth1_temp_tokens.create_temp_token(
        context.db_session,
        oauth_token=oauth_token,
        state_jwt=oauth1_state_jwt,
    )
    context.db_session.commit()

    logger.info(f"Linking oauth1 account with authorization_url={authorization_url}")
    return {"url": authorization_url}


@router.get(
    "/oauth1/callback",
    name=LINKED_ACCOUNTS_OAUTH1_CALLBACK_ROUTE_NAME,
    response_model=LinkedAccountWithCredentials,
    response_model_exclude_none=True,
)
async def linked_accounts_oauth1_callback(
    request: Request,
    db_session: Annotated[Session, Depends(deps.yield_db_session)],
) -> LinkedAccount | RedirectResponse:
    """
    Callback endpoint for OAuth1 account linking.
    """
    # Check for oauth_token and oauth_verifier
    oauth_token = request.query_params.get("oauth_token")
    oauth_verifier = request.query_params.get("oauth_verifier")

    if not oauth_token:
        logger.error("OAuth1 callback missing oauth_token")
        raise OAuth1Error("missing oauth_token parameter during account linking")

    if not oauth_verifier:
        logger.error("OAuth1 callback missing oauth_verifier")
        raise OAuth1Error("missing oauth_verifier parameter during account linking")

    # Retrieve the stored state using oauth_token
    temp_token = crud.oauth1_temp_tokens.get_temp_token(db_session, oauth_token)
    if not temp_token:
        logger.error(f"OAuth1 temp token not found for oauth_token={oauth_token}")
        raise OAuth1Error("invalid or expired oauth_token during account linking")

    # Decode the state
    try:
        state = LinkedAccountOAuth1CreateState.model_validate(
            jwt.decode(temp_token.state_jwt, config.SIGNING_KEY)
        )
        logger.info(
            f"OAuth1 account linking callback received, decoded state={state.model_dump(exclude_none=True)}"
        )
    except Exception as e:
        logger.exception(f"Failed to decode OAuth1 state, error={e}")
        raise AuthenticationError("invalid state during account linking") from e

    # Clean up temp token
    crud.oauth1_temp_tokens.delete_temp_token(db_session, oauth_token)

    # Check if app exists
    app = crud.apps.get_app(db_session, state.app_name, False, False)
    if not app:
        logger.error(f"App not found during OAuth1 callback, app_name={state.app_name}")
        raise AppNotFound(f"app={state.app_name} not found")

    # Check app configuration
    app_configuration = crud.app_configurations.get_app_configuration(
        db_session, state.project_id, state.app_name
    )
    if not app_configuration:
        logger.error(
            f"App configuration not found during OAuth1 callback, app_name={state.app_name}"
        )
        raise AppConfigurationNotFound(f"app configuration for app={state.app_name} not found")

    if app_configuration.security_scheme != SecurityScheme.OAUTH1:
        logger.error(f"App configuration is not OAuth1, app_name={state.app_name}")
        raise NoImplementationFound(f"app configuration for app={state.app_name} is not OAuth1")

    # Get OAuth1 scheme
    oauth1_scheme = scm.get_app_configuration_oauth1_scheme(
        app_configuration.app, app_configuration
    )

    if oauth1_scheme.consumer_key != state.consumer_key:
        logger.error(
            f"Consumer key mismatch during OAuth1 callback, "
            f"expected={oauth1_scheme.consumer_key}, got={state.consumer_key}"
        )
        raise OAuth1Error("consumer_key mismatch during account linking")

    # Create OAuth1 manager and exchange for access token
    oauth1_manager = OAuth1Manager(
        app_name=state.app_name,
        consumer_key=oauth1_scheme.consumer_key,
        consumer_secret=oauth1_scheme.consumer_secret,
        request_token_url=oauth1_scheme.request_token_url,
        authorize_url=oauth1_scheme.authorize_url,
        access_token_url=oauth1_scheme.access_token_url,
        scope=oauth1_scheme.scope,
    )

    # Exchange request token for access token
    access_token_response = await oauth1_manager.get_access_token(
        oauth_token=oauth_token,
        oauth_token_secret=state.oauth_token_secret,
        oauth_verifier=oauth_verifier,
    )
    security_credentials = oauth1_manager.parse_access_token_response(access_token_response)

    # Create or update linked account
    linked_account = crud.linked_accounts.get_linked_account(
        db_session,
        state.project_id,
        state.app_name,
        state.linked_account_owner_id,
    )

    if linked_account:
        logger.info(
            f"Updating oauth1 credentials for linked account, linked_account_id={linked_account.id}"
        )
        linked_account = crud.linked_accounts.update_linked_account_credentials(
            db_session, linked_account, security_credentials
        )
    else:
        # Get the organization ID from the project
        project = crud.projects.get_project(db_session, state.project_id)
        if not project:
            logger.error(f"Project not found, project_id={state.project_id}")
            raise ProjectNotFound(f"Project with ID {state.project_id} not found")

        # Enforce quota
        quota_manager.enforce_linked_accounts_creation_quota(
            db_session, project.org_id, state.linked_account_owner_id
        )

        logger.info(
            f"Creating oauth1 linked account, "
            f"app_name={state.app_name}, "
            f"linked_account_owner_id={state.linked_account_owner_id}"
        )
        linked_account = crud.linked_accounts.create_linked_account(
            db_session,
            project_id=state.project_id,
            app_name=state.app_name,
            linked_account_owner_id=state.linked_account_owner_id,
            security_scheme=SecurityScheme.OAUTH1,
            security_credentials=security_credentials,
            enabled=True,
        )

    db_session.commit()

    if state.after_oauth1_link_redirect_url:
        return RedirectResponse(
            url=state.after_oauth1_link_redirect_url, status_code=status.HTTP_302_FOUND
        )

    return linked_account


@router.get("", response_model=list[LinkedAccountPublic])
async def list_linked_accounts(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    query_params: Annotated[LinkedAccountsList, Query()],
) -> list[LinkedAccount]:
    """
    List linked accounts with pagination.
    - Optionally filter by app_name and linked_account_owner_id.
    - app_name + linked_account_owner_id can uniquely identify a linked account.
    - This can be an alternatively way to GET /linked-accounts/{linked_account_id} for getting a specific linked account.
    - Results are ordered by created_at descending (newest first).
    """

    linked_accounts = crud.linked_accounts.get_linked_accounts(
        context.db_session,
        context.project.id,
        query_params.app_name,
        query_params.linked_account_owner_id,
        query_params.limit,
        query_params.offset,
    )

    return linked_accounts


@router.get(
    "/{linked_account_id}",
    response_model=LinkedAccountWithCredentials,
    response_model_exclude_none=True,
)
async def get_linked_account(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    linked_account_id: UUID,
) -> LinkedAccount:
    """
    Get a linked account by its id.
    - linked_account_id uniquely identifies a linked account across the platform.
    """
    logger.info(f"Get linked account, linked_account_id={linked_account_id}")
    # validations
    linked_account = crud.linked_accounts.get_linked_account_by_id_under_project(
        context.db_session, linked_account_id, context.project.id
    )
    if not linked_account:
        logger.error(f"Linked account not found, linked_account_id={linked_account_id}")
        raise LinkedAccountNotFound(f"linked account={linked_account_id} not found")

    # Get the app configuration to check and refresh credentials if needed
    app_configuration = crud.app_configurations.get_app_configuration(
        context.db_session, context.project.id, linked_account.app.name
    )
    if not app_configuration:
        logger.error(
            "app configuration not found",
        )
        raise AppConfigurationNotFound(
            f"app configuration for app={linked_account.app.name} not found"
        )

    security_credentials_response = await scm.get_security_credentials(
        linked_account.app, app_configuration, linked_account
    )
    scm.update_security_credentials(
        context.db_session, linked_account.app, linked_account, security_credentials_response
    )
    logger.info(
        f"Fetched security credentials for linked account, linked_account_id={linked_account.id}, "
        f"is_updated={security_credentials_response.is_updated}"
    )
    context.db_session.commit()

    return linked_account


@router.delete("/{linked_account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_linked_account(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    linked_account_id: UUID,
) -> None:
    """
    Delete a linked account by its id.
    """
    logger.info(f"Delete linked account, linked_account_id={linked_account_id}")
    linked_account = crud.linked_accounts.get_linked_account_by_id_under_project(
        context.db_session, linked_account_id, context.project.id
    )
    if not linked_account:
        logger.error(f"Linked account not found, linked_account_id={linked_account_id}")
        raise LinkedAccountNotFound(f"linked account={linked_account_id} not found")

    crud.linked_accounts.delete_linked_account(context.db_session, linked_account)

    context.db_session.commit()


@router.patch("/{linked_account_id}", response_model=LinkedAccountPublic)
async def update_linked_account(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    linked_account_id: UUID,
    body: LinkedAccountUpdate,
) -> LinkedAccount:
    """
    Update a linked account.
    """
    logger.info(f"Update linked account, linked_account_id={linked_account_id}")
    linked_account = crud.linked_accounts.get_linked_account_by_id_under_project(
        context.db_session, linked_account_id, context.project.id
    )
    if not linked_account:
        logger.error(f"Linked account not found, linked_account_id={linked_account_id}")
        raise LinkedAccountNotFound(f"Linked account={linked_account_id} not found")

    linked_account = crud.linked_accounts.update_linked_account(
        context.db_session, linked_account, body
    )
    context.db_session.commit()

    return linked_account
