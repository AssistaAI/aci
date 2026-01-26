"""
Schema Fix Applier

Applies approved schema fixes to function parameters.
Also handles merging fixes during the seeding process.
"""

import copy
from typing import Any

from sqlalchemy.orm import Session

from aci.common.db import crud
from aci.common.db.sql_models import Function, SchemaFix
from aci.common.enums import SchemaFixStatus
from aci.common.logging_setup import get_logger

logger = get_logger(__name__)


class SchemaFixApplier:
    """
    Applies schema fixes to function parameters.

    Can apply fixes directly to the database or merge them into
    seed data during the upsert process.
    """

    @staticmethod
    def apply_fix_to_function(
        db_session: Session,
        function: Function,
        schema_fix: SchemaFix,
    ) -> bool:
        """
        Apply a schema fix directly to a function's parameters in the database.

        Args:
            db_session: Database session
            function: The function to update
            schema_fix: The schema fix to apply

        Returns:
            True if the fix was applied successfully, False otherwise
        """
        if schema_fix.status != SchemaFixStatus.APPROVED:
            logger.warning(
                f"Cannot apply fix with status={schema_fix.status}, "
                f"fix_id={schema_fix.id}, function={function.name}"
            )
            return False

        try:
            # Create a deep copy of the parameters to modify
            new_parameters = copy.deepcopy(function.parameters)

            # Apply the fix
            success = SchemaFixApplier._update_schema_at_path(
                new_parameters,
                schema_fix.property_path,
                schema_fix.property_name,
                schema_fix.property_schema,
            )

            if not success:
                logger.error(
                    f"Failed to apply fix at path={schema_fix.property_path}, "
                    f"property={schema_fix.property_name}"
                )
                return False

            # Update the function parameters
            function.parameters = new_parameters

            # Mark the fix as applied
            crud.schema_fixes.mark_fix_as_applied(db_session, schema_fix.id)

            logger.info(
                f"Applied schema fix, function={function.name}, "
                f"property={schema_fix.property_name}, path={schema_fix.property_path}"
            )
            return True

        except Exception as e:
            logger.exception(f"Error applying schema fix: {e}")
            return False

    @staticmethod
    def merge_fixes_into_parameters(
        parameters: dict[str, Any],
        fixes: list[SchemaFix],
    ) -> dict[str, Any]:
        """
        Merge schema fixes into a parameters dict (for seeding).

        This is used during the upsert process to preserve approved fixes
        that might not be in the seed data.

        Args:
            parameters: The base parameters dict (from seed data)
            fixes: List of approved schema fixes to merge

        Returns:
            New parameters dict with fixes merged in
        """
        if not fixes:
            return parameters

        merged = copy.deepcopy(parameters)

        for fix in fixes:
            # Check if the property already exists in the seed data
            if SchemaFixApplier._property_exists_at_path(
                merged, fix.property_path, fix.property_name
            ):
                logger.debug(
                    f"Property already exists in seed data, skipping fix, "
                    f"property={fix.property_name}, path={fix.property_path}"
                )
                continue

            # Apply the fix
            success = SchemaFixApplier._update_schema_at_path(
                merged,
                fix.property_path,
                fix.property_name,
                fix.property_schema,
            )

            if success:
                logger.debug(
                    f"Merged schema fix, property={fix.property_name}, path={fix.property_path}"
                )
            else:
                logger.warning(
                    f"Failed to merge schema fix, property={fix.property_name}, path={fix.property_path}"
                )

        return merged

    @staticmethod
    def _update_schema_at_path(
        schema: dict[str, Any],
        path: str,
        property_name: str,
        property_schema: dict[str, Any],
    ) -> bool:
        """
        Update a schema by adding a property at the specified path.

        Args:
            schema: The schema dict to modify (in place)
            path: Dot-separated path to the location (e.g., "properties.body.properties")
            property_name: The name of the property to add
            property_schema: The schema for the property

        Returns:
            True if successful, False otherwise
        """
        try:
            # Navigate to the target location
            current = schema
            path_parts = path.split(".") if path else []

            for part in path_parts:
                if part not in current:
                    # Create intermediate objects if they don't exist
                    current[part] = {}
                current = current[part]

            # Ensure we're at a properties dict
            if "properties" not in current:
                current["properties"] = {}

            # Add the property
            current["properties"][property_name] = property_schema

            return True

        except (KeyError, TypeError) as e:
            logger.warning(f"Failed to navigate path={path}: {e}")
            return False

    @staticmethod
    def _property_exists_at_path(
        schema: dict[str, Any],
        path: str,
        property_name: str,
    ) -> bool:
        """
        Check if a property exists at the specified path.

        Args:
            schema: The schema dict to check
            path: Dot-separated path to the location
            property_name: The name of the property to check

        Returns:
            True if the property exists, False otherwise
        """
        try:
            current = schema
            path_parts = path.split(".") if path else []

            for part in path_parts:
                if part not in current:
                    return False
                current = current[part]

            # Check if the property exists in the properties dict
            return property_name in current.get("properties", {})

        except (KeyError, TypeError):
            return False

    @staticmethod
    def rollback_fix(
        db_session: Session,
        function: Function,
        schema_fix: SchemaFix,
    ) -> bool:
        """
        Rollback a previously applied schema fix.

        Args:
            db_session: Database session
            function: The function to update
            schema_fix: The schema fix to rollback

        Returns:
            True if the rollback was successful, False otherwise
        """
        if schema_fix.status != SchemaFixStatus.APPLIED:
            logger.warning(
                f"Cannot rollback fix with status={schema_fix.status}, fix_id={schema_fix.id}"
            )
            return False

        try:
            # Remove the property from the schema
            new_parameters = copy.deepcopy(function.parameters)

            success = SchemaFixApplier._remove_property_at_path(
                new_parameters,
                schema_fix.property_path,
                schema_fix.property_name,
            )

            if not success:
                logger.error(
                    f"Failed to rollback fix at path={schema_fix.property_path}, "
                    f"property={schema_fix.property_name}"
                )
                return False

            # Update the function parameters
            function.parameters = new_parameters

            # Update the fix status back to approved
            crud.schema_fixes.update_fix_status(db_session, schema_fix.id, SchemaFixStatus.APPROVED)

            logger.info(
                f"Rolled back schema fix, function={function.name}, "
                f"property={schema_fix.property_name}"
            )
            return True

        except Exception as e:
            logger.exception(f"Error rolling back schema fix: {e}")
            return False

    @staticmethod
    def _remove_property_at_path(
        schema: dict[str, Any],
        path: str,
        property_name: str,
    ) -> bool:
        """
        Remove a property from a schema at the specified path.

        Args:
            schema: The schema dict to modify (in place)
            path: Dot-separated path to the location
            property_name: The name of the property to remove

        Returns:
            True if successful, False otherwise
        """
        try:
            current = schema
            path_parts = path.split(".") if path else []

            for part in path_parts:
                if part not in current:
                    return False
                current = current[part]

            # Remove the property
            if "properties" in current and property_name in current["properties"]:
                del current["properties"][property_name]
                return True

            return False

        except (KeyError, TypeError) as e:
            logger.warning(f"Failed to remove property at path={path}: {e}")
            return False


def get_fixes_to_merge(
    db_session: Session,
    function_name: str,
) -> list[SchemaFix]:
    """
    Get all fixes that should be merged for a function during seeding.

    This includes both APPROVED and APPLIED fixes to ensure we preserve
    all fixes even after seeding.

    Args:
        db_session: Database session
        function_name: The function name

    Returns:
        List of SchemaFix records to merge
    """
    approved = crud.schema_fixes.get_fixes_by_function_name(
        db_session, function_name, SchemaFixStatus.APPROVED
    )
    applied = crud.schema_fixes.get_fixes_by_function_name(
        db_session, function_name, SchemaFixStatus.APPLIED
    )

    return approved + applied
