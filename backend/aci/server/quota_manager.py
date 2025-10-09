"""
Quota and resource limitation control.

This module contains functions for enforcing various resource limits and quotas
across the platform, such as maximum projects per user, API rate limits, storage
quotas, and other resource constraints.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from aci.common.db import crud
from aci.common.exceptions import MaxAgentsReached, ProjectNotFound
from aci.common.logging_setup import get_logger
from aci.server import config

logger = get_logger(__name__)


def enforce_project_creation_quota(db_session: Session, org_id: UUID) -> None:
    """
    Skip plan-based project quota enforcement for local development.

    Args:
        db_session: Database session
        org_id: ID of the organization to check
    """
    logger.debug("Skipping project quota enforcement", extra={"org_id": org_id})


def enforce_agent_creation_quota(db_session: Session, project_id: UUID) -> None:
    """
    Check and enforce that the project hasn't exceeded its agent creation quota.

    Args:
        db_session: Database session
        project_id: ID of the project to check

    Raises:
        MaxAgentsReached: If the project has reached its maximum allowed agents
    """
    agents = crud.projects.get_agents_by_project(db_session, project_id)
    if len(agents) >= config.MAX_AGENTS_PER_PROJECT:
        logger.error(
            f"Project has reached maximum agents quota, project_id={project_id}, "
            f"max_agents={config.MAX_AGENTS_PER_PROJECT} num_agents={len(agents)}"
        )
        raise MaxAgentsReached()


def enforce_linked_accounts_creation_quota(
    db_session: Session, org_id: UUID, linked_account_owner_id: str
) -> None:
    """
    Skip plan-based linked account quota enforcement for local development.

    Args:
        db_session: Database session
        org_id: ID of the organization to check
        linked_account_owner_id: ID of the linked account owner to check
    """
    if crud.linked_accounts.linked_account_owner_id_exists_in_org(
        db_session, org_id, linked_account_owner_id
    ):
        # If the linked account owner id already exists in the organization, linking this account
        # will not increase the total number of unique linked account owner ids or exceed the quota.
        return

    logger.debug("Skipping linked account quota enforcement", extra={"org_id": org_id})


def enforce_agent_secrets_quota(db_session: Session, project_id: UUID) -> None:
    """
    Skip plan-based agent secret quota enforcement for local development.

    Args:
        db_session: Database session
        project_id: ID of the project to check
    """
    # Get the project
    project = crud.projects.get_project(db_session, project_id)
    if not project:
        logger.error(
            f"Project not found during agent secrets quota enforcement project_id={project_id}"
        )
        raise ProjectNotFound(f"Project {project_id} not found")

    logger.debug(
        "Skipping agent secrets quota enforcement",
        extra={"project_id": project_id, "org_id": project.org_id},
    )
