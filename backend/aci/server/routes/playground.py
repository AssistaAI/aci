"""
Optimized endpoints for playground UI to minimize data transfer and improve performance.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from aci.common.db import crud
from aci.common.logging_setup import get_logger
from aci.server import dependencies as deps

logger = get_logger(__name__)
router = APIRouter()


class PlaygroundAppSummary(BaseModel):
    """Lightweight app summary for playground - no functions included"""

    name: str
    display_name: str
    logo: str | None


class PlaygroundLinkedAccountOwner(BaseModel):
    """Unique linked account owner ID with count of linked apps"""

    linked_account_owner_id: str
    app_count: int


class PlaygroundInitResponse(BaseModel):
    """Optimized response for playground initialization"""

    apps: list[PlaygroundAppSummary]
    linked_account_owners: list[PlaygroundLinkedAccountOwner]
    total_function_count: int


@router.get("/init", response_model=PlaygroundInitResponse)
def initialize_playground(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    linked_account_owner_id: str | None = None,
) -> PlaygroundInitResponse:
    """
    Optimized endpoint for playground initialization.

    Returns lightweight data without function definitions (which can be loaded separately when needed).
    - Apps: Only name, display_name, and logo (no functions)
    - Linked account owners: Deduplicated list with app counts
    - Function count: Total number of functions available

    If linked_account_owner_id is provided, only return apps for that owner.

    Security: Only returns public apps and functions to prevent exposure of private integrations.
    """
    # Get linked accounts (with app relationship loaded efficiently)
    linked_accounts = crud.linked_accounts.get_linked_accounts(
        context.db_session,
        context.project.id,
        app_name=None,
        linked_account_owner_id=linked_account_owner_id,
        limit=None,  # Load all for aggregation
        offset=None,
        load_app=True,  # Efficiently join app data
    )

    # Build unique linked account owners with counts
    owner_app_counts: dict[str, int] = {}
    app_names: set[str] = set()

    for la in linked_accounts:
        owner_id = la.linked_account_owner_id
        owner_app_counts[owner_id] = owner_app_counts.get(owner_id, 0) + 1
        app_names.add(la.app.name)

    linked_account_owners = [
        PlaygroundLinkedAccountOwner(linked_account_owner_id=owner_id, app_count=count)
        for owner_id, count in sorted(owner_app_counts.items())
    ]

    # Get apps (without functions to reduce payload size)
    # Security: Only return public apps to prevent exposure of private integrations
    apps_data = crud.apps.get_apps(
        context.db_session,
        public_only=True,
        active_only=True,
        app_names=list(app_names) if app_names else None,
        limit=None,
        offset=None,
        load_functions=False,  # Don't load functions - they're not needed yet
    )

    apps = sorted(
        [
            PlaygroundAppSummary(
                name=app.name,
                display_name=app.display_name,
                logo=app.logo,
            )
            for app in apps_data
        ],
        key=lambda x: x.display_name,
    )

    # Get total function count for selected apps (lightweight query)
    # Security: Only count public functions
    total_function_count = crud.functions.count_functions(
        context.db_session,
        public_only=True,
        active_only=True,
        app_names=list(app_names) if app_names else None,
    )

    logger.info(
        f"Playground init: {len(apps)} apps, {len(linked_account_owners)} owners, {total_function_count} functions"
    )

    return PlaygroundInitResponse(
        apps=apps,
        linked_account_owners=linked_account_owners,
        total_function_count=total_function_count,
    )
