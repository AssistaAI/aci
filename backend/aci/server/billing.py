from copy import deepcopy
from uuid import UUID

from sqlalchemy.orm import Session

from aci.common.db import crud
from aci.common.db.sql_models import Plan, Project
from aci.common.logging_setup import get_logger
from aci.common.schemas.plans import PlanFeatures

logger = get_logger(__name__)

_UNLIMITED_PLAN_FEATURES = PlanFeatures(
    linked_accounts=1_000_000,
    api_calls_monthly=1_000_000_000,
    agent_credentials=1_000_000,
    developer_seats=1_000_000,
    custom_oauth=True,
    log_retention_days=3650,
    projects=1_000_000,
).model_dump()


def _build_unlimited_plan(name: str = "unlimited") -> Plan:
    """Return a Plan-like object with effectively no limits."""
    return Plan(
        name=name,
        stripe_product_id=f"local-{name}-product",
        stripe_monthly_price_id=f"local-{name}-monthly",
        stripe_yearly_price_id=f"local-{name}-yearly",
        features=deepcopy(_UNLIMITED_PLAN_FEATURES),
        is_public=False,
    )


def get_active_plan_by_org_id(db_session: Session, org_id: UUID) -> Plan:
    """
    Always serve an unlimited local plan so development environments are never blocked.
    """
    subscription = crud.subscriptions.get_subscription_by_org_id(db_session, org_id)
    plan_name = "unlimited"
    if subscription:
        existing_plan = crud.plans.get_by_id(db_session, subscription.plan_id)
        if existing_plan:
            plan_name = existing_plan.name

    return _build_unlimited_plan(plan_name)


def increment_quota(
    db_session: Session, project: Project, monthly_quota_limit: int | None = None
) -> None:
    """
    Quota usage tracking is disabled for local unlimited mode.
    """
    logger.debug(
        "Skipping monthly quota increment",
        extra={"project_id": project.id, "org_id": project.org_id},
    )
