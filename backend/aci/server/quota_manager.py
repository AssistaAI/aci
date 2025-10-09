"""
Quota and resource limitation control.

All quota enforcement is disabled; the functions remain as no-ops to keep call sites intact.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from aci.common.db import crud
from aci.common.exceptions import ProjectNotFound
from aci.common.logging_setup import get_logger

logger = get_logger(__name__)


def enforce_project_creation_quota(db_session: Session, org_id: UUID) -> None:
    logger.debug("Project quota enforcement disabled", extra={"org_id": org_id})


def enforce_agent_creation_quota(db_session: Session, project_id: UUID) -> None:
    logger.debug("Agent quota enforcement disabled", extra={"project_id": project_id})


def enforce_linked_accounts_creation_quota(
    db_session: Session, org_id: UUID, linked_account_owner_id: str
) -> None:
    logger.debug(
        "Linked account quota enforcement disabled",
        extra={"org_id": org_id, "linked_account_owner_id": linked_account_owner_id},
    )


def enforce_agent_secrets_quota(db_session: Session, project_id: UUID) -> None:
    project = crud.projects.get_project(db_session, project_id)
    if not project:
        logger.error(
            f"Project not found during agent secrets quota enforcement project_id={project_id}"
        )
        raise ProjectNotFound(f"Project {project_id} not found")

    logger.debug(
        "Agent secret quota enforcement disabled",
        extra={"project_id": project_id, "org_id": project.org_id},
    )
