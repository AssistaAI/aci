import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from openai import OpenAI
from sqlalchemy.orm import Session

from aci.common import processor
from aci.common.db import crud
from aci.common.db.sql_models import Agent, Function, Project
from aci.common.embeddings import generate_embedding
from aci.common.enums import FunctionDefinitionFormat, Visibility
from aci.common.exceptions import (
    AppConfigurationDisabled,
    AppConfigurationNotFound,
    AppNotAllowedForThisAgent,
    FunctionNotFound,
    InvalidFunctionDefinitionFormat,
    LinkedAccountDisabled,
    LinkedAccountNotFound,
)
from aci.common.logging_setup import get_logger
from aci.common.schemas.feedback import (
    FunctionSearchFeedbackCreate,
    FunctionSearchFeedbackResponse,
)
from aci.common.schemas.function import (
    AnthropicFunctionDefinition,
    BasicFunctionDefinition,
    FunctionDetails,
    FunctionExecute,
    FunctionExecutionResult,
    FunctionsList,
    FunctionsSearch,
    OpenAIFunction,
    OpenAIFunctionDefinition,
    OpenAIResponsesFunctionDefinition,
)
from aci.server import config, custom_instructions, utils
from aci.server import dependencies as deps
from aci.server import security_credentials_manager as scm
from aci.server.function_executors import get_executor
from aci.server.reranker import rerank_with_context
from aci.server.security_credentials_manager import SecurityCredentialsResponse

router = APIRouter()
logger = get_logger(__name__)
# TODO: will this be a bottleneck and problem if high concurrent requests from users?
# TODO: should probably be a singleton and inject into routes, shared access with Apps route
openai_client = OpenAI(api_key=config.OPENAI_API_KEY)


@router.get("", response_model=list[FunctionDetails])
async def list_functions(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    query_params: Annotated[FunctionsList, Query()],
) -> list[Function]:
    """Get a list of functions and their details. Sorted by function name."""
    return crud.functions.get_functions(
        context.db_session,
        context.project.visibility_access == Visibility.PUBLIC,
        True,
        query_params.app_names,
        query_params.limit,
        query_params.offset,
    )


@router.get("/search", response_model_exclude_none=True)
async def search_functions(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    query_params: Annotated[FunctionsSearch, Query()],
) -> list[
    BasicFunctionDefinition
    | OpenAIFunctionDefinition
    | OpenAIResponsesFunctionDefinition
    | AnthropicFunctionDefinition
]:
    """
    Returns the basic information of a list of functions.
    """
    # TODO: currently the search is done across all apps, we might want to add flags to account for below scenarios:
    # - when clients search for functions, if the app of the functions is configured but disabled by client, should the functions be discoverable?

    intent_embedding = (
        generate_embedding(
            openai_client,
            config.OPENAI_EMBEDDING_MODEL,
            config.OPENAI_EMBEDDING_DIMENSION,
            query_params.intent,
        )
        if query_params.intent
        else None
    )
    # Generated intent embedding for search

    # Determine apps to filter based on query params
    apps_to_filter = _determine_apps_to_filter(
        query_params.allowed_apps_only,
        query_params.app_names,
        context.agent.allowed_apps if hasattr(context.agent, "allowed_apps") else [],
    )

    # Determine if we need reranking
    needs_reranking = query_params.intent and len(query_params.intent.strip()) > 5

    # Only fetch extra results if we're actually going to rerank
    fetch_limit = min(query_params.limit * 2, 200) if needs_reranking else query_params.limit

    functions = crud.functions.search_functions(
        context.db_session,
        context.project.visibility_access == Visibility.PUBLIC,
        True,
        apps_to_filter,
        intent_embedding,
        fetch_limit,
        query_params.offset,
        intent_text=query_params.intent,
    )

    # Apply LLM reranking only for substantial queries
    if needs_reranking and functions and len(functions) > 1:
        functions = rerank_with_context(
            functions,
            query_params.intent,
            openai_client,
            agent_context={
                "allowed_apps": context.agent.allowed_apps if hasattr(context.agent, "allowed_apps") else None,
            },
        )
        # Apply the original limit after reranking
        functions = functions[: query_params.limit]

    # Store search results in context for potential implicit feedback
    # This will be used to track which function was actually executed
    if query_params.intent:
        context.db_session.info["last_search_intent"] = query_params.intent
        context.db_session.info["last_search_results"] = [f.name for f in functions]

    logger.info(
        "Search functions result",
        extra={
            "search_functions": {
                "query_params_json": query_params.model_dump_json(),
                "function_names": [function.name for function in functions],
                "reranked": bool(query_params.intent),
            }
        },
    )
    function_definitions = [
        format_function_definition(function, query_params.format) for function in functions
    ]

    return function_definitions


# TODO: have "structured_outputs" flag ("structured_outputs_if_possible") to support openai's structured outputs function calling?
# which need "strict: true" and only support a subset of json schema and a bunch of other restrictions like "All fields must be required"
# If you turn on Structured Outputs by supplying strict: true and call the API with an unsupported JSON Schema, you will receive an error.
# TODO: client sdk can use pydantic to validate model output for parameters used for function execution
# TODO: "flatten" flag to make sure nested parameters are flattened?
@router.get(
    "/{function_name}/definition",
    response_model_exclude_none=True,  # having this to exclude "strict" field in openai's function definition if not set
)
async def get_function_definition(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    function_name: str,
    format: FunctionDefinitionFormat = Query(  # noqa: B008 # TODO: need to fix this later
        default=FunctionDefinitionFormat.OPENAI,
        description="The format to use for the function definition (e.g., 'openai' or 'anthropic'). "
        "There is also a 'basic' format that only returns name and description.",
    ),
) -> (
    BasicFunctionDefinition
    | OpenAIFunctionDefinition
    | OpenAIResponsesFunctionDefinition
    | AnthropicFunctionDefinition
):
    """
    Return the function definition that can be used directly by LLM.
    The actual content depends on the FunctionDefinitionFormat and the function itself.
    """
    function: Function | None = crud.functions.get_function(
        context.db_session,
        function_name,
        context.project.visibility_access == Visibility.PUBLIC,
        True,
    )
    if not function:
        logger.error(
            f"Failed to get function definition, function not found, function_name={function_name}"
        )
        raise FunctionNotFound(f"function={function_name} not found")

    function_definition = format_function_definition(function, format)

    logger.info(
        "function definition to return",
        extra={
            "get_function_definition": {
                "format": format,
                "function_name": function_name,
            },
        },
    )
    return function_definition


# TODO: is there any way to abstract and generalize the checks and validations
# (enabled, configured, accessible, etc.)?
@router.post(
    "/{function_name}/execute",
    response_model=FunctionExecutionResult,
    response_model_exclude_none=True,
)
async def execute(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    function_name: str,
    body: FunctionExecute,
) -> FunctionExecutionResult:
    start_time = datetime.now(UTC)

    result = await execute_function(
        db_session=context.db_session,
        project=context.project,
        agent=context.agent,
        function_name=function_name,
        function_input=body.function_input,
        linked_account_owner_id=body.linked_account_owner_id,
        openai_client=openai_client,
    )

    end_time = datetime.now(UTC)

    # TODO: reconsider the implementation handling large log fields
    try:
        execute_result_data = utils.truncate_if_too_large(
            json.dumps(result.data, default=str), config.MAX_LOG_FIELD_SIZE
        )
    except Exception:
        logger.exception("Failed to dump execute_result_data")
        execute_result_data = "failed to dump execute_result_data"

    try:
        function_input_data = utils.truncate_if_too_large(
            json.dumps(body.function_input, default=str), config.MAX_LOG_FIELD_SIZE
        )
    except Exception:
        logger.exception("Failed to dump function_input_data")
        function_input_data = "failed to dump function_input_data"

    logger.info(
        "function execution result",
        extra={
            "function_execution": {
                "app_name": function_name.split("__")[0] if "__" in function_name else "unknown",
                "function_name": function_name,
                "linked_account_owner_id": body.linked_account_owner_id,
                "function_execution_start_time": start_time,
                "function_execution_end_time": end_time,
                "function_execution_duration": (end_time - start_time).total_seconds(),
                "function_input": function_input_data,
                "function_execution_result_success": result.success,
                "function_execution_result_error": result.error,
                "function_execution_result_data": execute_result_data,
                "function_execution_result_data_size": len(execute_result_data),
            }
        },
    )
    return result


# TODO: move to agent/tools.py or a util function
def format_function_definition(
    function: Function, format: FunctionDefinitionFormat
) -> (
    BasicFunctionDefinition
    | OpenAIFunctionDefinition
    | OpenAIResponsesFunctionDefinition
    | AnthropicFunctionDefinition
):
    match format:
        case FunctionDefinitionFormat.BASIC:
            return BasicFunctionDefinition(
                name=function.name,
                description=function.description,
            )
        case FunctionDefinitionFormat.OPENAI:
            return OpenAIFunctionDefinition(
                function=OpenAIFunction(
                    name=function.name,
                    description=function.description,
                    parameters=processor.filter_visible_properties(function.parameters),
                )
            )
        case FunctionDefinitionFormat.OPENAI_RESPONSES:
            # Create a properly formatted OpenAIResponsesFunctionDefinition
            # This format is used by the OpenAI chat completions API
            return OpenAIResponsesFunctionDefinition(
                type="function",
                name=function.name,
                description=function.description,
                parameters=processor.filter_visible_properties(function.parameters),
            )
        case FunctionDefinitionFormat.ANTHROPIC:
            return AnthropicFunctionDefinition(
                name=function.name,
                description=function.description,
                input_schema=processor.filter_visible_properties(function.parameters),
            )
        case _:
            raise InvalidFunctionDefinitionFormat(f"Invalid format: {format}")


async def execute_function(
    db_session: Session,
    project: Project,
    agent: Agent,
    function_name: str,
    function_input: dict,
    linked_account_owner_id: str,
    openai_client: OpenAI,
) -> FunctionExecutionResult:
    """
    Execute a function with the given parameters.

    Args:
        db_session: Database session
        project: Project object
        agent: Agent object
        function_name: Name of the function to execute
        function_input: Input parameters for the function
        linked_account_owner_id: ID of the linked account owner
        openai_client: Optional OpenAI client for custom instructions validation

    Returns:
        FunctionExecutionResult: Result of the function execution

    Raises:
        FunctionNotFound: If the function is not found
        AppConfigurationNotFound: If the app configuration is not found
        AppConfigurationDisabled: If the app configuration is disabled
        AppNotAllowedForThisAgent: If the app is not allowed for the agent
        LinkedAccountNotFound: If the linked account is not found
        LinkedAccountDisabled: If the linked account is disabled
    """
    # Get the function
    function = crud.functions.get_function(
        db_session,
        function_name,
        project.visibility_access == Visibility.PUBLIC,
        True,
    )
    if not function:
        logger.error(
            f"Failed to execute function, function not found, function_name={function_name}"
        )
        raise FunctionNotFound(f"function={function_name} not found")

    # Check if the App (that this function belongs to) is configured
    app_configuration = crud.app_configurations.get_app_configuration(
        db_session, project.id, function.app.name
    )
    if not app_configuration:
        logger.error(
            f"Failed to execute function, app configuration not found, "
            f"function_name={function_name} app_name={function.app.name}"
        )
        raise AppConfigurationNotFound(
            f"Configuration for app={function.app.name} not found, please configure the app first {config.DEV_PORTAL_URL}/apps/{function.app.name}"
        )
    # Check if user has disabled the app configuration
    if not app_configuration.enabled:
        logger.error(
            f"Failed to execute function, app configuration is disabled, "
            f"function_name={function_name} app_name={function.app.name} app_configuration_id={app_configuration.id}"
        )
        raise AppConfigurationDisabled(
            f"Configuration for app={function.app.name} is disabled, please enable the app first {config.DEV_PORTAL_URL}/appconfigs/{function.app.name}"
        )

    # Check if the function is allowed to be executed by the agent
    if function.app.name not in agent.allowed_apps:
        logger.error(
            f"Failed to execute function, App not allowed to be used by this agent, "
            f"function_name={function_name} app_name={function.app.name} agent_id={agent.id}"
        )
        raise AppNotAllowedForThisAgent(
            f"App={function.app.name} that this function belongs to is not allowed to be used by agent={agent.name}"
        )

    # Check if the linked account status (configured, enabled, etc.)
    linked_account = crud.linked_accounts.get_linked_account(
        db_session,
        project.id,
        function.app.name,
        linked_account_owner_id,
    )
    if not linked_account:
        logger.error(
            f"Failed to execute function, linked account not found, "
            f"function_name={function_name} app_name={function.app.name} linked_account_owner_id={linked_account_owner_id}"
        )
        raise LinkedAccountNotFound(
            f"Linked account with linked_account_owner_id={linked_account_owner_id} not found for app={function.app.name},"
            f"please link the account for this app here: {config.DEV_PORTAL_URL}/appconfigs/{function.app.name}"
        )

    if not linked_account.enabled:
        logger.error(
            f"Failed to execute function, linked account is disabled, "
            f"function_name={function_name} app_name={function.app.name} linked_account_owner_id={linked_account_owner_id} linked_account_id={linked_account.id}"
        )
        raise LinkedAccountDisabled(
            f"Linked account with linked_account_owner_id={linked_account_owner_id} is disabled for app={function.app.name},"
            f"please enable the account for this app here: {config.DEV_PORTAL_URL}/appconfigs/{function.app.name}"
        )

    security_credentials_response: SecurityCredentialsResponse = await scm.get_security_credentials(
        app_configuration.app, app_configuration, linked_account
    )

    scm.update_security_credentials(
        db_session, function.app, linked_account, security_credentials_response
    )

    logger.info(
        f"Fetched security credentials for function execution, function_name={function_name}, "
        f"app_name={function.app.name}, linked_account_owner_id={linked_account_owner_id}, "
        f"linked_account_id={linked_account.id}, is_updated={security_credentials_response.is_updated}, "
        f"is_app_default_credentials={security_credentials_response.is_app_default_credentials}"
    )
    db_session.commit()

    custom_instructions.check_for_violation(
        openai_client,
        function,
        function_input,
        agent.custom_instructions,
    )

    function_executor = get_executor(function.protocol, linked_account)
    logger.info(
        f"Instantiated function executor, function_executor={type(function_executor)}, "
        f"function={function_name}"
    )

    # Execute the function
    execution_result = function_executor.execute(
        function,
        function_input,
        security_credentials_response.scheme,
        security_credentials_response.credentials,
    )

    last_used_at: datetime = datetime.now(UTC)
    crud.linked_accounts.update_linked_account_last_used_at(
        db_session,
        last_used_at,
        linked_account,
    )
    db_session.commit()

    if not execution_result.success:
        logger.error(
            f"Function execution result error, function_name={function_name}, "
            f"error={execution_result.error}"
        )

    # Record implicit feedback if this function was part of a recent search
    if hasattr(db_session, "info") and "last_search_results" in db_session.info:
        last_results = db_session.info.get("last_search_results", [])
        if function_name in last_results:
            # Import here to avoid circular dependency
            from aci.common.db.crud import feedback as feedback_crud
            from aci.common.schemas.feedback import FunctionSearchFeedbackCreate

            implicit_feedback = FunctionSearchFeedbackCreate(
                intent=db_session.info.get("last_search_intent"),
                returned_function_names=last_results,
                selected_function_name=function_name,
                was_helpful=execution_result.success,  # Assume successful execution means helpful
                feedback_type="implicit_execution",
                search_metadata={
                    "execution_success": execution_result.success,
                    "execution_error": execution_result.error if not execution_result.success else None,
                },
            )

            try:
                # Only record feedback for successful executions to reduce noise
                if execution_result.success:
                    feedback_crud.create_search_feedback(
                        db_session,
                        agent.id,
                        project.id,
                        implicit_feedback,
                    )
                    db_session.commit()
                    # Recorded implicit feedback
            except Exception:
                # Don't fail the execution due to feedback recording failure
                db_session.rollback()

            # Always clear the search context to prevent memory leaks
            db_session.info.pop("last_search_intent", None)
            db_session.info.pop("last_search_results", None)
    else:
        # Clean up session.info even if feedback wasn't recorded
        if hasattr(db_session, "info"):
            db_session.info.pop("last_search_intent", None)
            db_session.info.pop("last_search_results", None)

    return execution_result


@router.post("/search/feedback", response_model=FunctionSearchFeedbackResponse)
async def provide_search_feedback(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    feedback: FunctionSearchFeedbackCreate,
) -> FunctionSearchFeedbackResponse:
    """
    Provide feedback on function search quality.
    This helps improve search relevance over time.

    Rate limited to prevent spam: Max 10 feedback entries per agent per hour.
    """
    # Import here to avoid circular dependency
    from datetime import UTC, datetime, timedelta
    from sqlalchemy import and_, func, select

    from aci.common.db.crud import feedback as feedback_crud
    from aci.common.db.sql_models import FunctionSearchFeedback

    # Simple rate limiting check (proper implementation should be in middleware)
    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    recent_feedback_count = context.db_session.scalar(
        select(func.count(FunctionSearchFeedback.id))
        .where(
            and_(
                FunctionSearchFeedback.agent_id == context.agent.id,
                FunctionSearchFeedback.created_at > one_hour_ago,
            )
        )
    )

    if recent_feedback_count and recent_feedback_count >= 10:
        from fastapi import HTTPException

        raise HTTPException(status_code=429, detail="Rate limit exceeded: Max 10 feedback entries per hour")

    # Create the feedback entry
    db_feedback = feedback_crud.create_search_feedback(
        context.db_session,
        context.agent.id,
        context.project.id,
        feedback,
    )

    context.db_session.commit()

    logger.info(
        "Search feedback recorded",
        extra={
            "feedback": {
                "id": str(db_feedback.id),
                "was_helpful": feedback.was_helpful,
                "feedback_type": feedback.feedback_type,
                "intent": feedback.intent[:50] if feedback.intent else None,
                "selected_function": feedback.selected_function_name,
            }
        },
    )

    return FunctionSearchFeedbackResponse(
        id=db_feedback.id,
        agent_id=db_feedback.agent_id,
        project_id=db_feedback.project_id,
        intent=db_feedback.intent,
        returned_function_names=db_feedback.returned_function_names,
        selected_function_name=db_feedback.selected_function_name,
        was_helpful=db_feedback.was_helpful,
        feedback_type=db_feedback.feedback_type,
        feedback_comment=db_feedback.feedback_comment,
        search_metadata=db_feedback.search_metadata,
        created_at=db_feedback.created_at,
    )


async def get_functions_definitions(
    db_session: Session,
    function_names: list[str],
    format: FunctionDefinitionFormat = FunctionDefinitionFormat.BASIC,
) -> list[
    BasicFunctionDefinition
    | OpenAIFunctionDefinition
    | OpenAIResponsesFunctionDefinition
    | AnthropicFunctionDefinition
]:
    """
    Get function definitions for a list of function names.

    Args:
        db_session: Database session
        function_names: List of function names to get definitions for
        format: Format of the function definition to return

    Returns:
        List of function definitions in the requested format
    """
    # Query functions by name
    functions = db_session.query(Function).filter(Function.name.in_(function_names)).all()

    # Get function definitions
    function_definitions = []
    for function in functions:
        function_definition = format_function_definition(function, format)
        function_definitions.append(function_definition)

    return function_definitions


def _determine_apps_to_filter(
    allowed_apps_only: bool,
    app_names: list[str] | None,
    agent_allowed_apps: list[str],
) -> list[str] | None:
    """Determine which apps to filter based on query parameters and agent permissions."""
    if allowed_apps_only:
        if app_names is None:
            return agent_allowed_apps
        return list(set(app_names) & set(agent_allowed_apps))
    return app_names
