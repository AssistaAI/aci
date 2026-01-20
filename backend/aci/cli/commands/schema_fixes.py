"""
CLI commands for managing schema fixes.

These commands allow viewing, processing, and managing schema fixes
detected from function execution validation errors.
"""

import click
from openai import OpenAI
from rich.console import Console
from rich.table import Table

from aci.cli import config
from aci.common import utils
from aci.common.db import crud
from aci.common.enums import SchemaFixStatus
from aci.common.schema_fix_applier import SchemaFixApplier
from aci.common.schema_fix_validator import SchemaFixValidator

console = Console()


@click.command()
@click.option(
    "--status",
    type=click.Choice(
        ["pending", "approved", "rejected", "manual_review", "applied", "all"],
        case_sensitive=False,
    ),
    default="all",
    help="Filter fixes by status",
)
@click.option(
    "--limit",
    type=int,
    default=50,
    help="Maximum number of fixes to display",
)
@click.option(
    "--function-name",
    type=str,
    default=None,
    help="Filter fixes by function name",
)
def list_schema_fixes(status: str, limit: int, function_name: str | None) -> None:
    """
    List schema fixes with optional filtering.

    Shows detected schema fixes and their current status.
    """
    with utils.create_db_session(config.DB_FULL_URL) as db_session:
        if function_name:
            status_enum = SchemaFixStatus(status) if status != "all" else None
            fixes = crud.schema_fixes.get_fixes_by_function_name(
                db_session, function_name, status_enum
            )[:limit]
        elif status == "all":
            # Get fixes across all statuses
            fixes = []
            for s in SchemaFixStatus:
                fixes.extend(crud.schema_fixes.get_fixes_by_status(db_session, s, limit=limit))
            fixes = fixes[:limit]
        else:
            status_enum = SchemaFixStatus(status)
            fixes = crud.schema_fixes.get_fixes_by_status(db_session, status_enum, limit=limit)

        if not fixes:
            console.print("[yellow]No schema fixes found matching criteria.[/yellow]")
            return

        table = Table(title=f"Schema Fixes (showing {len(fixes)} results)")
        table.add_column("ID", style="dim", max_width=8)
        table.add_column("Function", style="cyan")
        table.add_column("Property", style="green")
        table.add_column("Path", style="dim", max_width=30)
        table.add_column("Status", style="magenta")
        table.add_column("Occurrences", justify="right")
        table.add_column("Confidence", justify="right")

        for fix in fixes:
            # Get function name
            function = crud.functions.get_function_by_id(db_session, fix.function_id)
            func_name = function.name if function else "Unknown"

            confidence_str = f"{fix.llm_confidence:.2f}" if fix.llm_confidence is not None else "-"

            table.add_row(
                str(fix.id)[:8],
                func_name,
                fix.property_name,
                fix.property_path[:30] if fix.property_path else "-",
                fix.status.value,
                str(fix.occurrence_count),
                confidence_str,
            )

        console.print(table)


@click.command()
@click.option(
    "--auto-apply",
    is_flag=True,
    help="Automatically apply high-confidence fixes (>= 0.9)",
)
@click.option(
    "--limit",
    type=int,
    default=10,
    help="Maximum number of fixes to process",
)
@click.option(
    "--min-occurrences",
    type=int,
    default=1,
    help="Minimum occurrence count to process a fix",
)
def process_pending_fixes(auto_apply: bool, limit: int, min_occurrences: int) -> None:
    """
    Process pending schema fixes with LLM validation.

    Validates pending fixes using GPT and updates their status based on confidence.
    High-confidence fixes (>= 0.9) can be auto-applied with --auto-apply flag.
    """
    openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
    validator = SchemaFixValidator(openai_client)

    with utils.create_db_session(config.DB_FULL_URL) as db_session:
        pending_fixes = crud.schema_fixes.get_pending_fixes(
            db_session, limit=limit, min_occurrences=min_occurrences
        )

        if not pending_fixes:
            console.print("[yellow]No pending fixes to process.[/yellow]")
            return

        console.print(f"[cyan]Processing {len(pending_fixes)} pending fixes...[/cyan]")

        results_table = Table(title="Validation Results")
        results_table.add_column("Function")
        results_table.add_column("Property")
        results_table.add_column("Decision")
        results_table.add_column("Confidence")
        results_table.add_column("Applied")

        for fix in pending_fixes:
            function = crud.functions.get_function_by_id(db_session, fix.function_id)
            if not function:
                console.print(f"[red]Function not found for fix {fix.id}[/red]")
                continue

            console.print(f"Validating: {function.name} -> {fix.property_name}...", end=" ")

            result = validator.validate_fix(function, fix)

            # Update fix status with LLM results
            crud.schema_fixes.update_fix_status(
                db_session,
                fix.id,
                result.decision,
                llm_reasoning=result.reasoning,
                llm_confidence=result.confidence,
            )

            applied = "No"
            if auto_apply and result.decision == SchemaFixStatus.APPROVED:
                # Apply the fix directly to the function
                if SchemaFixApplier.apply_fix_to_function(db_session, function, fix):
                    applied = "Yes"

            decision_color = {
                SchemaFixStatus.APPROVED: "green",
                SchemaFixStatus.REJECTED: "red",
                SchemaFixStatus.MANUAL_REVIEW: "yellow",
            }.get(result.decision, "white")

            console.print(f"[{decision_color}]{result.decision.value}[/{decision_color}]")

            results_table.add_row(
                function.name,
                fix.property_name,
                result.decision.value,
                f"{result.confidence:.2f}",
                applied,
            )

        db_session.commit()
        console.print(results_table)


@click.command()
@click.argument("fix_id", type=str)
@click.option(
    "--action",
    type=click.Choice(["approve", "reject"], case_sensitive=False),
    required=True,
    help="Action to take on the fix",
)
@click.option(
    "--reason",
    type=str,
    default=None,
    help="Reason for the decision",
)
def review_schema_fix(fix_id: str, action: str, reason: str | None) -> None:
    """
    Manually review and approve/reject a schema fix.

    FIX_ID is the UUID of the schema fix to review.
    """
    from uuid import UUID

    try:
        fix_uuid = UUID(fix_id)
    except ValueError:
        console.print(f"[red]Invalid UUID: {fix_id}[/red]")
        return

    with utils.create_db_session(config.DB_FULL_URL) as db_session:
        fix = crud.schema_fixes.get_fix_by_id(db_session, fix_uuid)
        if not fix:
            console.print(f"[red]Fix not found: {fix_id}[/red]")
            return

        function = crud.functions.get_function_by_id(db_session, fix.function_id)
        func_name = function.name if function else "Unknown"

        new_status = SchemaFixStatus.APPROVED if action == "approve" else SchemaFixStatus.REJECTED

        crud.schema_fixes.update_fix_status(
            db_session,
            fix_uuid,
            new_status,
            llm_reasoning=reason or f"Manually {action}d",
        )

        db_session.commit()

        status_color = "green" if action == "approve" else "red"
        console.print(
            f"[{status_color}]Fix for {func_name}.{fix.property_name} has been {action}d.[/{status_color}]"
        )


@click.command()
@click.option(
    "--function-name",
    type=str,
    default=None,
    help="Apply fixes only for a specific function",
)
@click.option(
    "--skip-dry-run",
    is_flag=True,
    help="Actually apply the changes (default is dry run)",
)
def apply_approved_fixes(function_name: str | None, skip_dry_run: bool) -> None:
    """
    Apply approved schema fixes to function parameters.

    This applies fixes that have been approved but not yet applied to the database.
    """
    with utils.create_db_session(config.DB_FULL_URL) as db_session:
        if function_name:
            # Get fixes for specific function
            function = crud.functions.get_function(
                db_session, function_name, public_only=False, active_only=False
            )
            if not function:
                console.print(f"[red]Function not found: {function_name}[/red]")
                return

            fixes = crud.schema_fixes.get_approved_fixes_for_function(db_session, function.id)
            functions_to_update = [(function, fixes)] if fixes else []
        else:
            # Get all approved fixes grouped by function
            approved_fixes = crud.schema_fixes.get_fixes_by_status(
                db_session, SchemaFixStatus.APPROVED, limit=1000
            )

            # Group by function
            functions_fixes: dict = {}
            for fix in approved_fixes:
                if fix.function_id not in functions_fixes:
                    function = crud.functions.get_function_by_id(db_session, fix.function_id)
                    functions_fixes[fix.function_id] = (function, [])
                functions_fixes[fix.function_id][1].append(fix)

            functions_to_update = list(functions_fixes.values())

        if not functions_to_update:
            console.print("[yellow]No approved fixes to apply.[/yellow]")
            return

        table = Table(title="Fixes to Apply" + (" (DRY RUN)" if not skip_dry_run else ""))
        table.add_column("Function")
        table.add_column("Property")
        table.add_column("Path")
        table.add_column("Status")

        for function, fixes in functions_to_update:
            if not function:
                continue

            for fix in fixes:
                if skip_dry_run:
                    success = SchemaFixApplier.apply_fix_to_function(db_session, function, fix)
                    status = "[green]Applied[/green]" if success else "[red]Failed[/red]"
                else:
                    status = "[yellow]Would Apply[/yellow]"

                table.add_row(
                    function.name,
                    fix.property_name,
                    fix.property_path[:30] if fix.property_path else "-",
                    status,
                )

        if skip_dry_run:
            db_session.commit()

        console.print(table)

        if not skip_dry_run:
            console.print(
                "\n[bold yellow]This was a dry run. "
                "Use --skip-dry-run to apply changes.[/bold yellow]"
            )


@click.command()
@click.argument("fix_id", type=str)
def rollback_schema_fix(fix_id: str) -> None:
    """
    Rollback a previously applied schema fix.

    FIX_ID is the UUID of the schema fix to rollback.
    """
    from uuid import UUID

    try:
        fix_uuid = UUID(fix_id)
    except ValueError:
        console.print(f"[red]Invalid UUID: {fix_id}[/red]")
        return

    with utils.create_db_session(config.DB_FULL_URL) as db_session:
        fix = crud.schema_fixes.get_fix_by_id(db_session, fix_uuid)
        if not fix:
            console.print(f"[red]Fix not found: {fix_id}[/red]")
            return

        if fix.status != SchemaFixStatus.APPLIED:
            console.print(f"[red]Fix is not in APPLIED status (current: {fix.status.value})[/red]")
            return

        function = crud.functions.get_function_by_id(db_session, fix.function_id)
        if not function:
            console.print(f"[red]Function not found for fix {fix_id}[/red]")
            return

        success = SchemaFixApplier.rollback_fix(db_session, function, fix)

        if success:
            db_session.commit()
            console.print(f"[green]Rolled back fix for {function.name}.{fix.property_name}[/green]")
        else:
            console.print("[red]Failed to rollback fix[/red]")


@click.command()
def schema_fix_stats() -> None:
    """
    Show statistics about schema fixes.
    """
    with utils.create_db_session(config.DB_FULL_URL) as db_session:
        stats = crud.schema_fixes.get_fix_statistics(db_session)

        console.print("[bold cyan]Schema Fix Statistics[/bold cyan]\n")

        table = Table(title="By Status")
        table.add_column("Status")
        table.add_column("Count", justify="right")

        for status, count in stats["by_status"].items():
            table.add_row(status, str(count))

        console.print(table)

        console.print()

        table2 = Table(title="By Error Type")
        table2.add_column("Error Type")
        table2.add_column("Count", justify="right")

        for error_type, count in stats["by_error_type"].items():
            table2.add_row(error_type, str(count))

        console.print(table2)

        console.print(f"\n[bold]Total fixes: {stats['total']}[/bold]")
