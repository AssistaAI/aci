"""
CLI command to validate function descriptions across all apps.
"""

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from aci.cli import config
from aci.common.validators.description import (
    DescriptionIssue,
    validate_function_description,
)

console = Console()


@click.command()
@click.option(
    "--apps-dir",
    "apps_dir",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to apps directory (defaults to backend/apps)",
)
@click.option(
    "--app",
    "app_name",
    type=str,
    default=None,
    help="Validate only a specific app",
)
@click.option(
    "--fail-on-issues",
    is_flag=True,
    help="Exit with error code if any issues are found",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed issues for each function",
)
def validate_descriptions(
    apps_dir: Path | None,
    app_name: str | None,
    fail_on_issues: bool,
    verbose: bool,
) -> None:
    """
    Validate function descriptions for LLM agent optimization.

    Checks all function descriptions across apps for:
    - Minimum length (at least 6 words)
    - Imperative verb form (not third person like "Creates" -> "Create")
    - App context in short descriptions
    - No redundant app name prefixes
    """
    # Determine apps directory
    if apps_dir is None:
        # Default to backend/apps relative to this file
        apps_dir = Path(__file__).parent.parent.parent.parent / "apps"

    if not apps_dir.exists():
        console.print(f"[bold red]Apps directory not found: {apps_dir}[/bold red]")
        raise SystemExit(1)

    # Collect results
    total_functions = 0
    functions_with_issues = 0
    issue_counts: dict[str, int] = {}
    all_issues: list[tuple[str, str, list[DescriptionIssue]]] = []

    # Determine which apps to validate
    if app_name:
        app_dirs = [apps_dir / app_name]
        if not app_dirs[0].exists():
            console.print(f"[bold red]App not found: {app_name}[/bold red]")
            raise SystemExit(1)
    else:
        app_dirs = sorted([d for d in apps_dir.iterdir() if d.is_dir()])

    for app_dir in app_dirs:
        functions_file = app_dir / "functions.json"
        if not functions_file.exists():
            continue

        try:
            with open(functions_file) as f:
                functions = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            console.print(f"[yellow]Warning: Could not read {functions_file}: {e}[/yellow]")
            continue

        for func in functions:
            name = func.get("name", "")
            description = func.get("description", "")

            if not name:
                continue

            total_functions += 1
            issues = validate_function_description(name, description)

            if issues:
                functions_with_issues += 1
                all_issues.append((name, description, issues))

                for issue in issues:
                    issue_counts[issue.issue_type] = issue_counts.get(issue.issue_type, 0) + 1

    # Print summary
    console.print()
    console.rule("Description Validation Results")
    console.print()

    console.print(f"Total functions analyzed: [bold]{total_functions}[/bold]")
    console.print(f"Functions with issues: [bold red]{functions_with_issues}[/bold red]")
    console.print(
        f"Functions passing: [bold green]{total_functions - functions_with_issues}[/bold green]"
    )
    console.print()

    if issue_counts:
        # Issue summary table
        table = Table(title="Issues by Type")
        table.add_column("Issue Type", style="cyan")
        table.add_column("Count", justify="right", style="magenta")

        for issue_type, count in sorted(issue_counts.items(), key=lambda x: -x[1]):
            table.add_row(issue_type, str(count))

        console.print(table)
        console.print()

    if verbose and all_issues:
        # Detailed issues
        console.rule("Detailed Issues")
        console.print()

        for name, description, issues in all_issues[:50]:  # Limit to first 50
            console.print(f"[bold]{name}[/bold]")
            console.print(f"  Current: {description[:80]}{'...' if len(description) > 80 else ''}")
            for issue in issues:
                suggestion = f" -> {issue.suggestion}" if issue.suggestion else ""
                console.print(f"  [red]- {issue.issue_type}[/red]: {issue.message}{suggestion}")
            console.print()

        if len(all_issues) > 50:
            console.print(f"[dim]... and {len(all_issues) - 50} more functions with issues[/dim]")

    # Exit with error if requested and issues found
    if fail_on_issues and functions_with_issues > 0:
        console.print()
        console.print("[bold red]Validation failed: description issues found[/bold red]")
        raise SystemExit(1)

    if functions_with_issues == 0:
        console.print("[bold green]All descriptions pass validation![/bold green]")
