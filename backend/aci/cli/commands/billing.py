from datetime import datetime, timedelta
from uuid import UUID, uuid4

import click
from rich.console import Console

from aci.cli import config
from aci.common import utils
from aci.common.db import crud
from aci.common.db.sql_models import Plan, Subscription
from aci.common.enums import StripeSubscriptionInterval, StripeSubscriptionStatus
from aci.common.schemas.plans import PlanFeatures, PlanUpdate

console = Console()

STRIPE_STARTER_PRODUCT_ID = "prod_SB7tlLd8lSxbuO"
STRIPE_STARTER_MONTHLY_PRICE_ID = "price_1RGldu2Nixr9IfKz20SLnp3G"
STRIPE_STARTER_YEARLY_PRICE_ID = "price_1RGlwG2Nixr9IfKz3w2iQu2R"

STRIPE_TEAM_PRODUCT_ID = "prod_SB85QAy6lgGUyZ"
STRIPE_TEAM_MONTHLY_PRICE_ID = "price_1RGlp52Nixr9IfKzHEkpkUno"
STRIPE_TEAM_YEARLY_PRICE_ID = "price_1RGlvI2Nixr9IfKzKf0vNDRq"

PLANS_DATA = [
    Plan(
        name="free",
        stripe_product_id="prod_FREE_placeholder",
        stripe_monthly_price_id="price_FREE_monthly_placeholder",
        stripe_yearly_price_id="price_FREE_yearly_placeholder",
        features=PlanFeatures(
            linked_accounts=3,
            api_calls_monthly=1000,
            agent_credentials=5,
            developer_seats=1,
            custom_oauth=True,
            log_retention_days=7,
            projects=1,
        ).model_dump(),
        is_public=True,
    ),
    Plan(
        name="starter",
        stripe_product_id=STRIPE_STARTER_PRODUCT_ID,
        stripe_monthly_price_id=STRIPE_STARTER_MONTHLY_PRICE_ID,
        stripe_yearly_price_id=STRIPE_STARTER_YEARLY_PRICE_ID,
        features=PlanFeatures(
            linked_accounts=250,
            api_calls_monthly=100000,
            agent_credentials=2500,
            developer_seats=5,
            custom_oauth=True,
            log_retention_days=30,
            projects=5,
        ).model_dump(),
        is_public=True,
    ),
    Plan(
        name="team",
        stripe_product_id=STRIPE_TEAM_PRODUCT_ID,
        stripe_monthly_price_id=STRIPE_TEAM_MONTHLY_PRICE_ID,
        stripe_yearly_price_id=STRIPE_TEAM_YEARLY_PRICE_ID,
        features=PlanFeatures(
            linked_accounts=1000,
            api_calls_monthly=300000,
            agent_credentials=10000,
            developer_seats=10,
            custom_oauth=True,
            log_retention_days=30,
            projects=10,
        ).model_dump(),
        is_public=True,
    ),
]


@click.command("populate-subscription-plans")
@click.option(
    "--skip-dry-run",
    is_flag=True,
    help="provide this flag to run the command and apply changes to the database",
)
def populate_subscription_plans(skip_dry_run: bool) -> None:
    """
    Populates the Plan table with Starter, Team, and Growth plans.
    If plans with the same names exist, they will be updated.
    Uses placeholder Stripe IDs.
    """
    console.rule("[bold blue]Populating Subscription Plans[/bold blue]")

    with utils.create_db_session(config.DB_FULL_URL) as db_session:
        created_count = 0
        updated_count = 0
        for plan_data in PLANS_DATA:
            plan_name = str(plan_data.name)
            existing_plan = crud.plans.get_by_name(db_session, plan_name)

            if existing_plan:
                # Update existing plan
                console.print(f"Updating existing plan: {plan_name}")
                plan_update_schema = PlanUpdate(
                    stripe_product_id=str(plan_data.stripe_product_id),
                    stripe_monthly_price_id=str(plan_data.stripe_monthly_price_id),
                    stripe_yearly_price_id=str(plan_data.stripe_yearly_price_id),
                    features=PlanFeatures(**plan_data.features),
                    is_public=bool(plan_data.is_public),
                )
                updated_plan = crud.plans.update_plan(
                    db=db_session,
                    plan=existing_plan,
                    plan_update=plan_update_schema,
                )
                if updated_plan:
                    updated_count += 1
                console.print(f"  Plan: {updated_plan.name}, ID: {updated_plan.id}")

            else:
                # Create new plan
                console.print(f"Creating new plan: {plan_name}")
                new_plan = crud.plans.create(
                    db=db_session,
                    name=str(plan_data.name),
                    stripe_product_id=str(plan_data.stripe_product_id),
                    stripe_monthly_price_id=str(plan_data.stripe_monthly_price_id),
                    stripe_yearly_price_id=str(plan_data.stripe_yearly_price_id),
                    features=PlanFeatures(**plan_data.features),
                    is_public=bool(plan_data.is_public),
                )
                console.print(f"  Plan: {new_plan.name}, ID: {new_plan.id}")
                created_count += 1

        if not skip_dry_run:
            console.print(
                f"[bold yellow]Dry run complete. Created: {created_count}, Updated: {updated_count}.[/bold yellow]"
            )
            console.print("Rolling back changes. Use --skip-dry-run to apply.")
            db_session.rollback()
        else:
            try:
                db_session.commit()
                console.print(
                    f"[bold green]Successfully populated/updated plans. Created: {created_count}, Updated: {updated_count}.[/bold green]"
                )
            except Exception as e:
                db_session.rollback()
                console.print(f"[bold red]Error during commit: {e}[/bold red]")
                raise click.Abort() from e


@click.command("create-test-subscription")
@click.option("--org-id", required=True, type=str, help="Organization ID (UUID)")
@click.option("--plan-name", default="team", type=str, help="Plan name (free, starter, team)")
@click.option(
    "--skip-dry-run",
    is_flag=True,
    help="provide this flag to run the command and apply changes to the database",
)
def create_test_subscription(org_id: str, plan_name: str, skip_dry_run: bool) -> None:
    """
    Creates a test subscription for local development.
    Uses placeholder Stripe IDs for testing.
    """
    console.rule(f"[bold blue]Creating Test Subscription for Org {org_id}[/bold blue]")

    try:
        org_uuid = UUID(org_id)
    except ValueError as e:
        console.print(f"[bold red]Invalid UUID format for org-id: {org_id}[/bold red]")
        raise click.Abort() from e

    with utils.create_db_session(config.DB_FULL_URL) as db_session:
        # Get the plan
        plan = crud.plans.get_by_name(db_session, plan_name)
        if not plan:
            console.print(f"[bold red]Plan '{plan_name}' not found[/bold red]")
            raise click.Abort()

        console.print(f"Found plan: {plan.name} (ID: {plan.id})")

        # Check if subscription already exists
        existing_subscription = crud.subscriptions.get_subscription_by_org_id(db_session, org_uuid)
        if existing_subscription:
            console.print(
                f"[bold yellow]Subscription already exists for org {org_id}[/bold yellow]"
            )
            return

        # Create test subscription
        subscription = Subscription(
            org_id=org_uuid,
            plan_id=plan.id,
            stripe_customer_id=f"cus_test_{uuid4().hex[:8]}",
            stripe_subscription_id=f"sub_test_{uuid4().hex[:8]}",
            status=StripeSubscriptionStatus.ACTIVE,
            interval=StripeSubscriptionInterval.MONTH,
            current_period_end=datetime.now() + timedelta(days=30),
            cancel_at_period_end=False,
        )

        db_session.add(subscription)

        if not skip_dry_run:
            console.print(
                f"[bold yellow]Dry run complete. Would create subscription for org {org_id} with plan {plan_name}.[/bold yellow]"
            )
            console.print("Rolling back changes. Use --skip-dry-run to apply.")
            db_session.rollback()
        else:
            try:
                db_session.commit()
                console.print(
                    f"[bold green]Successfully created test subscription for org {org_id}[/bold green]"
                )
                console.print(f"  Plan: {plan.name}")
                console.print(f"  Stripe Customer ID: {subscription.stripe_customer_id}")
                console.print(f"  Stripe Subscription ID: {subscription.stripe_subscription_id}")
            except Exception as e:
                db_session.rollback()
                console.print(f"[bold red]Error during commit: {e}[/bold red]")
                raise click.Abort() from e
