"""Bulk test all functions in an app with auto-healing capabilities."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import click
import httpx
from openai import OpenAI
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from aci.cli import config
from aci.cli.commands.fuzzy_test_function_execution import (
    fuzzy_test_function_execution_helper,
)
from aci.common.enums import FunctionDefinitionFormat

console = Console()


@click.command()
@click.option(
    "--app-name",
    "app_name",
    required=True,
    type=str,
    help="Name of the app to test (e.g., BRAVE_SEARCH)",
)
@click.option(
    "--aci-api-key",
    "aci_api_key",
    required=True,
    type=str,
    help="ACI API key to use for authentication",
)
@click.option(
    "--linked-account-owner-id",
    "linked_account_owner_id",
    required=True,
    type=str,
    help="ID of the linked account owner to use for authentication",
)
@click.option(
    "--auto-fix",
    "auto_fix",
    is_flag=True,
    default=False,
    help="Automatically fix detected issues in function schemas",
)
@click.option(
    "--model",
    "model",
    type=str,
    required=False,
    default="gpt-4o",
    help="LLM model to use for function call arguments generation",
)
@click.option(
    "--report-dir",
    "report_dir",
    type=click.Path(),
    default="./test_reports",
    help="Directory to save test reports",
)
@click.option(
    "--max-retries",
    "max_retries",
    type=int,
    default=2,
    help="Maximum number of retry attempts after auto-fix",
)
def test_app_functions(
    app_name: str,
    aci_api_key: str,
    linked_account_owner_id: str,
    auto_fix: bool,
    model: str,
    report_dir: str,
    max_retries: int,
) -> None:
    """Test all functions in an app with optional auto-healing."""
    console.rule(f"[bold blue]Testing App: {app_name}[/bold blue]")

    # Get all functions for this app
    functions = get_app_functions(app_name, aci_api_key)
    if not functions:
        console.print(f"[yellow]No functions found for app: {app_name}[/yellow]")
        return

    console.print(f"[green]Found {len(functions)} functions to test[/green]\n")

    # Sort functions intelligently: LIST/GET functions first to gather context
    sorted_functions = sort_functions_by_priority(functions)
    console.print(f"[cyan]Optimized test order (list/get functions first)[/cyan]\n")

    # Shared context for storing discovered data between tests
    test_context = {}

    results = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Testing functions...", total=len(sorted_functions))

        for function in sorted_functions:
            function_name = function["name"]
            progress.update(task, description=f"[cyan]Testing {function_name}...")

            result = test_function_with_retry(
                function_name=function_name,
                aci_api_key=aci_api_key,
                linked_account_owner_id=linked_account_owner_id,
                model=model,
                auto_fix=auto_fix,
                max_retries=max_retries,
                test_context=test_context,
            )

            # Store successful responses in context for future tests (extract only useful IDs)
            if result["status"] == "passed" and result.get("response"):
                extracted_data = extract_useful_data(function_name, result["response"])
                if extracted_data:
                    test_context[function_name] = extracted_data

            results.append(result)
            progress.advance(task)

    # Generate and save report
    report_path = generate_report(app_name, results, report_dir)

    # Display summary
    display_summary(results, report_path)


def extract_useful_data(function_name: str, response: dict) -> dict | None:
    """
    Extract only the useful identifiers from a response, not the entire payload.

    This prevents token limit issues when passing context to the LLM.
    """
    if not isinstance(response, dict):
        return None

    extracted = {}

    # Handle success responses with data
    if response.get("success") and response.get("data"):
        data = response["data"]

        # Handle nested data
        if isinstance(data, dict) and "data" in data:
            data = data["data"]

        # Extract from lists (voices, avatars, etc.)
        if isinstance(data, dict) and "list" in data:
            items = data["list"]
            if items and len(items) > 0:
                # Only extract IDs from first 5 items to keep context small
                ids = []
                for item in items[:5]:
                    if isinstance(item, dict):
                        # Extract all ID-like fields
                        for key, value in item.items():
                            if isinstance(value, str) and ("id" in key.lower() or key.lower().endswith("_id")):
                                ids.append({key: value})

                if ids:
                    extracted["example_ids"] = ids
                    extracted["total_count"] = len(items)

    return extracted if extracted else None


def sort_functions_by_priority(functions: list[dict]) -> list[dict]:
    """
    Sort functions to optimize test data gathering.

    Priority order:
    1. LIST functions (gather collections of data)
    2. GET functions (retrieve individual items)
    3. CREATE/UPDATE/DELETE functions (use data from LIST/GET)
    """
    def get_priority(func: dict) -> tuple[int, str]:
        name = func.get("name", "").upper()

        # Extract function action (part after __)
        parts = name.split("__")
        action = parts[1] if len(parts) > 1 else name

        # Priority 0: LIST functions (highest priority)
        if action.startswith("LIST") or action.startswith("GET_ALL"):
            return (0, name)

        # Priority 1: GET/RETRIEVE single item functions
        if action.startswith("GET") or action.startswith("RETRIEVE") or action.startswith("FETCH"):
            return (1, name)

        # Priority 2: STATUS/CHECK functions (usually safe, read-only)
        if "STATUS" in action or "CHECK" in action or "SEARCH" in action:
            return (2, name)

        # Priority 3: CREATE functions (need context but don't modify existing)
        if action.startswith("CREATE") or action.startswith("ADD") or action.startswith("GENERATE"):
            return (3, name)

        # Priority 4: UPDATE functions
        if action.startswith("UPDATE") or action.startswith("MODIFY") or action.startswith("EDIT"):
            return (4, name)

        # Priority 5: DELETE functions (lowest priority, most destructive)
        if action.startswith("DELETE") or action.startswith("REMOVE"):
            return (5, name)

        # Default: priority 3 (middle ground)
        return (3, name)

    return sorted(functions, key=get_priority)


def get_app_functions(app_name: str, aci_api_key: str) -> list[dict]:
    """Get all functions for a given app."""
    try:
        response = httpx.get(
            f"{config.SERVER_URL}/v1/functions",
            params={"app_name": app_name, "limit": 1000},
            headers={"x-api-key": aci_api_key},
            timeout=30.0,
        )
        if response.status_code != 200:
            console.print(
                f"[red]Failed to get functions: {response.status_code}[/red]"
            )
            return []

        data = response.json()
        # API returns a list directly
        if isinstance(data, list):
            functions = data
        else:
            # Or it might be wrapped in a dict
            functions = data.get("functions", [])

        # Filter by app_name on client side (in case API doesn't filter properly)
        filtered = [f for f in functions if f.get("app_name") == app_name or f.get("name", "").startswith(f"{app_name}__")]
        return filtered
    except Exception as e:
        console.print(f"[red]Error fetching functions: {e}[/red]")
        return []


def test_function_with_retry(
    function_name: str,
    aci_api_key: str,
    linked_account_owner_id: str,
    model: str,
    auto_fix: bool,
    max_retries: int,
    test_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Test a function with retry logic and auto-healing."""
    result = {
        "function_name": function_name,
        "status": "unknown",
        "error": None,
        "response": None,
        "fixes_applied": [],
        "attempts": 0,
    }

    for attempt in range(max_retries + 1):
        result["attempts"] = attempt + 1

        try:
            # Generate a smart test prompt based on function name and context
            prompt = generate_test_prompt(function_name, test_context or {})

            # Run the fuzzy test and capture response
            response_data = fuzzy_test_function_execution_helper(
                aci_api_key=aci_api_key,
                function_name=function_name,
                model=model,
                linked_account_owner_id=linked_account_owner_id,
                prompt=prompt,
                test_context=test_context or {},
            )

            result["status"] = "passed"
            result["error"] = None
            result["response"] = response_data
            return result

        except Exception as e:
            error_message = str(e)
            result["error"] = error_message
            result["status"] = "failed"

            # If auto-fix is enabled and we have retries left, try to fix
            if auto_fix and attempt < max_retries:
                fixes = detect_and_fix_issues(function_name, error_message)
                if fixes:
                    result["fixes_applied"].extend(fixes)
                    console.print(
                        f"[yellow]Applied {len(fixes)} fix(es) to {function_name}, retrying...[/yellow]"
                    )
                    continue
                else:
                    console.print(
                        f"[red]No automatic fixes available for error: {error_message[:100]}[/red]"
                    )
                    break
            else:
                break

    return result


def generate_test_prompt(function_name: str, test_context: dict[str, Any]) -> str:
    """
    Generate a realistic test prompt based on function name and available context.

    If previous functions have returned useful data (like IDs, names, etc.),
    instruct the LLM to use that real data instead of fake values.
    """
    # Extract the function action from the name
    parts = function_name.split("__")
    action = parts[1].replace("_", " ").lower() if len(parts) > 1 else "test"

    # Build context summary for the LLM
    context_summary = build_context_summary(function_name, test_context)

    if context_summary:
        return f"""Test the {action} functionality with realistic parameters.

IMPORTANT: Use real data from previous API responses when possible:
{context_summary}

Use actual IDs, names, and values from the context above instead of making up fake data."""
    else:
        return f"Test the {action} functionality with realistic parameters"


def build_context_summary(function_name: str, test_context: dict[str, Any]) -> str:
    """
    Build a concise summary of available context data relevant to this function.

    Uses the extracted IDs from previous responses.
    """
    if not test_context:
        return ""

    app_name = function_name.split("__")[0]
    summary_lines = []

    for ctx_func_name, ctx_data in test_context.items():
        # Only include context from the same app
        if not ctx_func_name.startswith(app_name):
            continue

        if isinstance(ctx_data, dict) and ctx_data.get("example_ids"):
            example_ids = ctx_data["example_ids"]
            total_count = ctx_data.get("total_count", len(example_ids))

            # Format the example IDs nicely
            id_strings = []
            for id_obj in example_ids[:3]:  # Show max 3 examples
                for key, value in id_obj.items():
                    id_strings.append(f"{key}='{value}'")

            summary_lines.append(
                f"- From {ctx_func_name}: {total_count} items available. Example IDs: {', '.join(id_strings)}"
            )

    return "\n".join(summary_lines) if summary_lines else ""


def detect_and_fix_issues(function_name: str, error_message: str) -> list[str]:
    """
    Detect issues from error messages and apply automatic fixes.

    Returns a list of fixes that were applied.
    """
    fixes_applied = []

    # Pattern 1: Missing visible parameters
    if "missing required" in error_message.lower() or "required property" in error_message.lower():
        fix = fix_missing_visible_parameters(function_name)
        if fix:
            fixes_applied.append("Added missing parameters to visible array")

    # Pattern 2: Schema validation errors
    if "validation error" in error_message.lower() or "invalid type" in error_message.lower():
        fix = fix_schema_validation(function_name)
        if fix:
            fixes_applied.append("Fixed schema validation issues")

    # Pattern 3: Missing defaults for invisible required parameters
    if "default" in error_message.lower():
        fix = add_missing_defaults(function_name)
        if fix:
            fixes_applied.append("Added missing default values")

    return fixes_applied


def fix_missing_visible_parameters(function_name: str) -> bool:
    """
    Fix missing visible parameters by ensuring all required parameters are in visible array.

    This is a placeholder - in production, this would:
    1. Load the functions.json file
    2. Parse the parameters schema
    3. Add missing required params to visible array
    4. Save and upsert the function
    """
    # TODO: Implement actual fix logic
    console.print(
        f"[yellow]Would fix missing visible parameters for {function_name}[/yellow]"
    )
    return False


def fix_schema_validation(function_name: str) -> bool:
    """
    Fix schema validation issues like missing additionalProperties: false.

    This is a placeholder - in production, this would:
    1. Load the functions.json file
    2. Add additionalProperties: false to all object schemas
    3. Add visible arrays at all nested levels
    4. Save and upsert the function
    """
    # TODO: Implement actual fix logic
    console.print(f"[yellow]Would fix schema validation for {function_name}[/yellow]")
    return False


def add_missing_defaults(function_name: str) -> bool:
    """
    Add default values for invisible required parameters.

    This is a placeholder - in production, this would:
    1. Load the functions.json file
    2. Find invisible required parameters without defaults
    3. Add sensible default values
    4. Save and upsert the function
    """
    # TODO: Implement actual fix logic
    console.print(f"[yellow]Would add missing defaults for {function_name}[/yellow]")
    return False


def generate_report(
    app_name: str, results: list[dict], report_dir: str
) -> Path:
    """Generate a markdown report of test results."""
    report_dir_path = Path(report_dir)
    report_dir_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = report_dir_path / f"{app_name}_{timestamp}.md"

    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] == "failed")

    with open(report_file, "w") as f:
        f.write(f"# Test Report: {app_name}\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Summary:** {passed} passed, {failed} failed out of {len(results)} functions\n\n")
        f.write("---\n\n")

        for result in results:
            status_icon = "✅" if result["status"] == "passed" else "❌"
            f.write(f"## {status_icon} {result['function_name']}\n\n")
            f.write(f"**Status:** {result['status']}\n")
            f.write(f"**Attempts:** {result['attempts']}\n\n")

            if result["fixes_applied"]:
                f.write(f"**Fixes Applied:**\n")
                for fix in result["fixes_applied"]:
                    f.write(f"- {fix}\n")
                f.write("\n")

            if result["error"]:
                f.write(f"**Error:**\n```json\n{result['error']}\n```\n\n")

            if result.get("response"):
                import json
                f.write(f"**Response:**\n```json\n{json.dumps(result['response'], indent=2)}\n```\n\n")

            f.write("---\n\n")

    return report_file


def display_summary(results: list[dict], report_path: Path) -> None:
    """Display a summary table of test results."""
    console.rule("[bold green]Test Summary[/bold green]")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Function", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Attempts", justify="center")
    table.add_column("Fixes", justify="center")

    for result in results:
        status = "[green]✅ PASSED[/green]" if result["status"] == "passed" else "[red]❌ FAILED[/red]"
        fixes_count = len(result["fixes_applied"])
        fixes_str = str(fixes_count) if fixes_count > 0 else "-"

        table.add_row(
            result["function_name"],
            status,
            str(result["attempts"]),
            fixes_str,
        )

    console.print(table)

    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] == "failed")
    total = len(results)

    console.print(f"\n[bold]Results: {passed}/{total} passed ({(passed/total*100):.1f}%)[/bold]")
    console.print(f"[dim]Report saved to: {report_path}[/dim]\n")
