"""
Schema Fix Detector

Detects potential schema fixes from JSON Schema validation errors.
When AI agents send valid API parameters that are missing from our function schemas,
this module identifies the missing properties and their inferred types.
"""

from dataclasses import dataclass
from typing import Any

import jsonschema

from aci.common.enums import SchemaFixErrorType
from aci.common.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass
class SchemaFixCandidate:
    """A candidate for a schema fix detected from a validation error."""

    function_name: str
    property_path: str
    property_name: str
    property_schema: dict[str, Any]
    error_type: SchemaFixErrorType
    original_value: Any


class SchemaFixDetector:
    """
    Detects fixable schema errors from JSON Schema validation failures.

    Currently supports detection of:
    - Additional properties violations (additionalProperties: false)
    """

    @staticmethod
    def detect_from_validation_error(
        error: jsonschema.ValidationError,
        function_name: str,
        function_input: dict[str, Any],
    ) -> SchemaFixCandidate | None:
        """
        Analyze a validation error and detect if it's a fixable schema issue.

        Args:
            error: The JSON Schema validation error
            function_name: The name of the function being executed
            function_input: The input that was passed to the function

        Returns:
            A SchemaFixCandidate if the error is fixable, None otherwise
        """
        error_type = SchemaFixDetector._classify_error(error)

        if error_type == SchemaFixErrorType.ADDITIONAL_PROPERTY:
            return SchemaFixDetector._detect_additional_property_fix(
                error, function_name, function_input
            )

        # Other error types (WRONG_TYPE, MISSING_REQUIRED) are not auto-fixable
        # They typically indicate AI hallucination or incorrect usage
        logger.debug(
            f"Validation error is not fixable, error_type={error_type}, message={error.message}"
        )
        return None

    @staticmethod
    def _classify_error(error: jsonschema.ValidationError) -> SchemaFixErrorType:
        """
        Classify a validation error into one of our error types.

        Args:
            error: The JSON Schema validation error

        Returns:
            The classified error type
        """
        # Check if it's an additionalProperties violation
        validator = str(error.validator) if error.validator else ""
        if validator == "additionalProperties":
            return SchemaFixErrorType.ADDITIONAL_PROPERTY

        # Check if it's a type error
        if validator == "type":
            return SchemaFixErrorType.WRONG_TYPE

        # Check if it's a required field error
        if validator == "required":
            return SchemaFixErrorType.MISSING_REQUIRED

        # Default to additional property for unknown errors that mention "additional"
        if "additional" in error.message.lower():
            return SchemaFixErrorType.ADDITIONAL_PROPERTY

        # Default classification based on message patterns
        if "type" in error.message.lower():
            return SchemaFixErrorType.WRONG_TYPE

        # Fallback - treat unknown as API error (will be skipped)
        return SchemaFixErrorType.API_ERROR

    @staticmethod
    def _detect_additional_property_fix(
        error: jsonschema.ValidationError,
        function_name: str,
        function_input: dict[str, Any],
    ) -> SchemaFixCandidate | None:
        """
        Detect a fix for an additional property violation.

        Args:
            error: The validation error for additionalProperties
            function_name: The name of the function
            function_input: The function input dict

        Returns:
            A SchemaFixCandidate if we can extract the property info
        """
        # Extract the property name from the error message
        # Typical message: "Additional properties are not allowed ('stateId' was unexpected)"
        property_name = SchemaFixDetector._extract_property_name_from_error(error)

        if not property_name:
            logger.warning(f"Could not extract property name from error, message={error.message}")
            return None

        # Build the property path from the error path
        # error.absolute_path gives us the path to where the error occurred
        property_path = SchemaFixDetector._build_property_path(error.absolute_path)

        # Get the value that was passed for this property
        original_value = SchemaFixDetector._get_value_at_path(
            function_input, [*list(error.absolute_path), property_name]
        )

        if original_value is None:
            logger.warning(f"Could not find value for property={property_name} in function_input")
            return None

        # Infer the JSON schema for this property based on its value
        property_schema = SchemaFixDetector._infer_property_schema(original_value)

        return SchemaFixCandidate(
            function_name=function_name,
            property_path=property_path,
            property_name=property_name,
            property_schema=property_schema,
            error_type=SchemaFixErrorType.ADDITIONAL_PROPERTY,
            original_value=original_value,
        )

    @staticmethod
    def _extract_property_name_from_error(
        error: jsonschema.ValidationError,
    ) -> str | None:
        """
        Extract the property name from an additionalProperties error.

        The error message typically looks like:
        "Additional properties are not allowed ('stateId' was unexpected)"
        "Additional properties are not allowed ('priority', 'state' were unexpected)"
        """
        message = error.message

        # Try to extract from the standard jsonschema message format
        if "'" in message and "was unexpected" in message:
            # Extract the first quoted property name
            start = message.find("'") + 1
            end = message.find("'", start)
            if start > 0 and end > start:
                return message[start:end]

        if "'" in message and "were unexpected" in message:
            # Multiple properties - extract the first one
            start = message.find("'") + 1
            end = message.find("'", start)
            if start > 0 and end > start:
                return message[start:end]

        # Fallback: try to parse from context if available
        if hasattr(error, "context") and error.context:
            for suberror in error.context:
                if hasattr(suberror, "path") and suberror.path:
                    return str(list(suberror.path)[-1])

        return None

    @staticmethod
    def _build_property_path(absolute_path: Any) -> str:
        """
        Build a property path string from the jsonschema absolute_path.

        Args:
            absolute_path: The deque from jsonschema error (e.g., ['body', 'variables', 'filter'])

        Returns:
            A dot-separated path string (e.g., "properties.body.properties.variables.properties.filter")
        """
        path_parts = []
        for part in absolute_path:
            path_parts.append("properties")
            path_parts.append(str(part))

        return ".".join(path_parts) if path_parts else "properties"

    @staticmethod
    def _get_value_at_path(data: dict[str, Any], path: list) -> Any:
        """
        Get a value from a nested dict using a path list.

        Args:
            data: The nested dictionary
            path: List of keys to traverse

        Returns:
            The value at the path, or None if not found
        """
        current = data
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    @staticmethod
    def _infer_property_schema(value: Any) -> dict[str, Any]:
        """
        Infer a JSON Schema for a property based on its value.

        Args:
            value: The value to infer schema from

        Returns:
            A JSON Schema dict describing the value's type
        """
        if value is None:
            return {"type": "null"}

        if isinstance(value, bool):
            # Must check bool before int since bool is subclass of int in Python
            return {"type": "boolean"}

        if isinstance(value, int):
            return {"type": "integer"}

        if isinstance(value, float):
            return {"type": "number"}

        if isinstance(value, str):
            return {"type": "string"}

        if isinstance(value, list):
            if not value:
                return {"type": "array"}
            # Infer item type from first element
            item_schema = SchemaFixDetector._infer_property_schema(value[0])
            return {"type": "array", "items": item_schema}

        if isinstance(value, dict):
            # For objects, create a schema with the properties we see
            properties = {}
            for key, val in value.items():
                properties[key] = SchemaFixDetector._infer_property_schema(val)
            return {
                "type": "object",
                "properties": properties,
                "additionalProperties": True,  # Allow flexibility
            }

        # Fallback for unknown types
        return {}
