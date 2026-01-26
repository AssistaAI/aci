from abc import ABC, abstractmethod
from threading import Thread
from typing import Generic, TypeVar

import jsonschema

from aci.common import processor
from aci.common.db.sql_models import Function, LinkedAccount
from aci.common.exceptions import InvalidFunctionInput
from aci.common.logging_setup import get_logger
from aci.common.schema_fix_detector import SchemaFixCandidate, SchemaFixDetector
from aci.common.schemas.function import FunctionExecutionResult

logger = get_logger(__name__)

TCred = TypeVar("TCred")
TScheme = TypeVar("TScheme")


class FunctionExecutor(ABC, Generic[TScheme, TCred]):
    """
    Base class for function executors.
    """

    def __init__(self, linked_account: LinkedAccount):
        self.linked_account = linked_account

    # TODO: allow local code execution override by using AppBase.execute() e.g.,:
    # app_factory = AppFactory()
    # app_instance: AppBase = app_factory.get_app_instance(function_name)
    # app_instance.validate_input(function.parameters, function_execution_params.function_input)
    # return app_instance.execute(function_name, function_execution_params.function_input)
    def execute(
        self,
        function: Function,
        function_input: dict,
        security_scheme: TScheme,
        security_credentials: TCred,
    ) -> FunctionExecutionResult:
        """
        Execute the function based on end-user input and security credentials.
        Input validation, default values injection, and security credentials injection are done here.
        """
        logger.info(
            f"Executing function, function_name={function.name}, function_input={function_input}"
        )
        function_input = self._preprocess_function_input(function, function_input)

        return self._execute(function, function_input, security_scheme, security_credentials)

    def _preprocess_function_input(self, function: Function, function_input: dict) -> dict:
        # validate user input against the "visible" parameters
        try:
            jsonschema.validate(
                instance=function_input,
                schema=processor.filter_visible_properties(function.parameters),
            )
        except jsonschema.ValidationError as e:
            logger.exception(
                f"Failed to validate function input, function_name={function.name}, error={e}"
            )
            # Detect potential schema fix (fire-and-forget, non-blocking)
            self._queue_schema_fix_candidate(function, function_input, e)
            raise InvalidFunctionInput(
                f"Invalid function input for function={function.name}, error={e.message}"
            ) from e

        logger.debug(
            f"Function input before injecting defaults, function_name={function.name}, "
            f"function_input={function_input}"
        )

        # inject non-visible defaults, note that should pass the original parameters schema not just visible ones
        function_input = processor.inject_required_but_invisible_defaults(
            function.parameters, function_input
        )
        logger.debug(
            f"Function_input after injecting defaults, function_name={function.name}, "
            f"function_input={function_input}"
        )

        # remove None values from the input
        # TODO: better way to remove None values? and if it's ok to remove all of them?
        function_input = processor.remove_none_values(function_input)

        return function_input

    def _queue_schema_fix_candidate(
        self,
        function: Function,
        function_input: dict,
        error: jsonschema.ValidationError,
    ) -> None:
        """
        Detect and queue a schema fix candidate from a validation error.

        This runs in a background thread to avoid blocking the request.
        """
        try:
            candidate = SchemaFixDetector.detect_from_validation_error(
                error, function.name, function_input
            )

            if candidate:
                logger.info(
                    f"Detected schema fix candidate, function={function.name}, "
                    f"property={candidate.property_name}, path={candidate.property_path}"
                )
                # Queue the fix in a background thread
                thread = Thread(
                    target=self._save_schema_fix_candidate,
                    args=(function, candidate),
                    daemon=True,
                )
                thread.start()
            else:
                logger.debug(
                    f"No fixable schema issue detected, function={function.name}, "
                    f"error={error.message}"
                )
        except Exception as ex:
            # Don't let fix detection errors affect the main flow
            logger.warning(f"Error detecting schema fix candidate: {ex}")

    def _save_schema_fix_candidate(
        self, function: Function, candidate: SchemaFixCandidate
    ) -> None:
        """
        Save a schema fix candidate to the database.

        This runs in a background thread.
        """
        try:
            from aci.common import utils
            from aci.common.db import crud
            from aci.server import config

            # Create a new database session for this background task
            with utils.create_db_session(config.DB_FULL_URL) as db_session:
                crud.schema_fixes.create_or_increment_fix(
                    db_session, candidate, function.id
                )
                db_session.commit()
                logger.info(
                    f"Saved schema fix candidate, function={function.name}, "
                    f"property={candidate.property_name}"
                )
        except Exception as e:
            logger.warning(f"Failed to save schema fix candidate: {e}")

    @abstractmethod
    def _execute(
        self,
        function: Function,
        function_input: dict,
        security_scheme: TScheme,
        security_credentials: TCred,
    ) -> FunctionExecutionResult:
        pass
