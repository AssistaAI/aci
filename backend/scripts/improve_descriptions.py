#!/usr/bin/env python3
"""
Script to analyze and improve function descriptions for LLM agent tool selection.

This script:
1. Analyzes all functions.json files across apps
2. Identifies description quality issues
3. Generates suggested improvements
4. Outputs a review file for human approval
5. Applies approved changes back to functions.json files

Usage:
    # Analyze all apps and generate suggestions
    python scripts/improve_descriptions.py analyze --output improvements.json

    # Generate a markdown report for review
    python scripts/improve_descriptions.py report --input improvements.json --output improvements.md

    # Apply approved changes
    python scripts/improve_descriptions.py apply --input reviewed_improvements.json

    # Validate descriptions (useful for CI)
    python scripts/improve_descriptions.py validate --fail-on-issues
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent
APPS_DIR = BACKEND_DIR / "apps"


# ============================================================================
# Validation logic (standalone copy to avoid external dependencies)
# ============================================================================

@dataclass
class DescriptionIssue:
    """Represents an issue found in a description."""
    issue_type: str
    message: str
    suggestion: str | None = None


THIRD_PERSON_TO_IMPERATIVE = {
    "retrieves": "Retrieve",
    "creates": "Create",
    "updates": "Update",
    "deletes": "Delete",
    "lists": "List",
    "sends": "Send",
    "gets": "Get",
    "returns": "Return",
    "provides": "Provide",
    "fetches": "Fetch",
    "searches": "Search",
    "generates": "Generate",
    "adds": "Add",
    "removes": "Remove",
    "moves": "Move",
    "copies": "Copy",
    "enables": "Enable",
    "disables": "Disable",
    "starts": "Start",
    "stops": "Stop",
    "syncs": "Sync",
    "exports": "Export",
    "imports": "Import",
    "uploads": "Upload",
    "downloads": "Download",
    "cancels": "Cancel",
    "schedules": "Schedule",
    "archives": "Archive",
    "restores": "Restore",
    "publishes": "Publish",
    "subscribes": "Subscribe",
    "unsubscribes": "Unsubscribe",
    "invites": "Invite",
    "revokes": "Revoke",
    "grants": "Grant",
    "checks": "Check",
    "verifies": "Verify",
    "validates": "Validate",
    "finds": "Find",
    "queries": "Query",
    "filters": "Filter",
    "sorts": "Sort",
    "groups": "Group",
    "assigns": "Assign",
    "unassigns": "Unassign",
    "completes": "Complete",
    "marks": "Mark",
    "sets": "Set",
    "clears": "Clear",
    "synthesizes": "Synthesize",
    "connects": "Connect",
    "disconnects": "Disconnect",
    "links": "Link",
    "unlinks": "Unlink",
    "attaches": "Attach",
    "detaches": "Detach",
}

MIN_WORD_COUNT = 6
APP_CONTEXT_THRESHOLD = 12


def validate_function_description(name: str, description: str) -> list[DescriptionIssue]:
    """Validate a function description and return a list of issues found."""
    issues: list[DescriptionIssue] = []

    if not description or not description.strip():
        issues.append(DescriptionIssue(
            issue_type="EMPTY_DESCRIPTION",
            message="Description is empty or contains only whitespace",
            suggestion=None,
        ))
        return issues

    words = description.split()
    word_count = len(words)
    app_name = name.split("__")[0].lower() if "__" in name else ""

    # Rule 1: Minimum length check
    if word_count < MIN_WORD_COUNT:
        issues.append(DescriptionIssue(
            issue_type="TOO_SHORT",
            message=f"Description has only {word_count} words (minimum {MIN_WORD_COUNT})",
            suggestion="Add more context about what the function does",
        ))

    # Rule 2: Imperative verb form check
    first_word = words[0].lower() if words else ""
    if first_word in THIRD_PERSON_TO_IMPERATIVE:
        imperative = THIRD_PERSON_TO_IMPERATIVE[first_word]
        issues.append(DescriptionIssue(
            issue_type="THIRD_PERSON_VERB",
            message=f"Use imperative verb form instead of third person '{words[0]}'",
            suggestion=imperative,
        ))

    # Rule 3: No redundant app name prefix
    if app_name and first_word == app_name:
        issues.append(DescriptionIssue(
            issue_type="REDUNDANT_APP_PREFIX",
            message="Don't start description with app name (already in function name)",
            suggestion="Remove the app name prefix and start with an action verb",
        ))

    # Rule 4: App context required for short descriptions
    if word_count < APP_CONTEXT_THRESHOLD and app_name:
        description_lower = description.lower()
        app_variants = [app_name, app_name.replace("_", " "), app_name.replace("_", "")]
        has_app_context = any(variant in description_lower for variant in app_variants)
        context_words = ["api", "workspace", "account", "platform", "service", "crm", "database"]
        has_generic_context = any(word in description_lower for word in context_words)

        if not has_app_context and not has_generic_context:
            issues.append(DescriptionIssue(
                issue_type="MISSING_APP_CONTEXT",
                message="Short descriptions should mention the app/platform for disambiguation",
                suggestion=f"Include '{app_name.replace('_', ' ').title()}' in the description",
            ))

    return issues


def fix_third_person_verb(description: str) -> str:
    """Fix third-person verb at the start of a description to imperative form."""
    if not description:
        return description
    words = description.split()
    if not words:
        return description
    first_word_lower = words[0].lower()
    if first_word_lower in THIRD_PERSON_TO_IMPERATIVE:
        words[0] = THIRD_PERSON_TO_IMPERATIVE[first_word_lower]
        return " ".join(words)
    return description


# ============================================================================
# Main script logic
# ============================================================================


@dataclass
class FunctionAnalysis:
    """Analysis result for a single function."""

    name: str
    app_name: str
    current_description: str
    issues: list[dict]
    suggested_description: str | None
    status: str  # "pending_review", "approved", "rejected", "no_issues"


def analyze_function(name: str, description: str) -> FunctionAnalysis:
    """
    Analyze a single function's description and generate improvement suggestions.

    Args:
        name: Function name (e.g., GMAIL__SEND_EMAIL)
        description: Current description

    Returns:
        FunctionAnalysis with issues and suggested improvements
    """
    app_name = name.split("__")[0] if "__" in name else "unknown"
    issues = validate_function_description(name, description)

    if not issues:
        return FunctionAnalysis(
            name=name,
            app_name=app_name,
            current_description=description,
            issues=[],
            suggested_description=None,
            status="no_issues",
        )

    # Generate suggested description
    suggested = generate_suggested_description(name, description, issues)

    return FunctionAnalysis(
        name=name,
        app_name=app_name,
        current_description=description,
        issues=[asdict(issue) for issue in issues],
        suggested_description=suggested,
        status="pending_review",
    )


def generate_suggested_description(
    name: str, description: str, issues: list[DescriptionIssue]
) -> str:
    """
    Generate a suggested improved description based on identified issues.

    Args:
        name: Function name
        description: Current description
        issues: List of issues found

    Returns:
        Suggested improved description
    """
    suggested = description
    app_name = name.split("__")[0] if "__" in name else ""
    app_display = app_name.replace("_", " ").title()

    # Fix third-person verb
    issue_types = {i.issue_type for i in issues}

    if "THIRD_PERSON_VERB" in issue_types:
        suggested = fix_third_person_verb(suggested)

    # Remove redundant app prefix
    if "REDUNDANT_APP_PREFIX" in issue_types:
        words = suggested.split()
        if words and words[0].lower() == app_name.lower():
            # Remove app name and any following "API" word
            words = words[1:]
            if words and words[0].lower() == "api":
                words = words[1:]
            suggested = " ".join(words)
            # Ensure it starts with capital letter
            if suggested:
                suggested = suggested[0].upper() + suggested[1:]

    # Add app context for short descriptions
    if "MISSING_APP_CONTEXT" in issue_types and app_display:
        words = suggested.split()
        # Try to insert app name naturally
        if len(words) >= 2:
            # Pattern: "Verb the/a/an resource" -> "Verb the/a/an resource in/from/via AppName"
            if words[-1].endswith("."):
                words[-1] = words[-1][:-1]

            # Determine preposition based on verb
            first_word_lower = words[0].lower()
            if first_word_lower in ["retrieve", "get", "list", "fetch", "search", "find", "query"]:
                preposition = "from"
            elif first_word_lower in ["create", "add", "upload", "send", "schedule"]:
                preposition = "in"
            elif first_word_lower in ["update", "modify", "edit", "change"]:
                preposition = "in"
            elif first_word_lower in ["delete", "remove"]:
                preposition = "from"
            else:
                preposition = "via"

            suggested = f"{suggested} {preposition} {app_display}."

    # For too short descriptions, add a note
    if "TOO_SHORT" in issue_types:
        # Mark for manual review - can't automatically expand
        if not suggested.endswith("[NEEDS EXPANSION]"):
            suggested = f"{suggested} [NEEDS EXPANSION]"

    return suggested


def analyze_all_apps() -> dict[str, FunctionAnalysis]:
    """
    Analyze all function descriptions across all apps.

    Returns:
        Dictionary mapping function names to their analysis results
    """
    results: dict[str, FunctionAnalysis] = {}

    for app_dir in sorted(APPS_DIR.iterdir()):
        if not app_dir.is_dir():
            continue

        functions_file = app_dir / "functions.json"
        if not functions_file.exists():
            continue

        try:
            with open(functions_file) as f:
                functions = json.load(f)

            for func in functions:
                name = func.get("name", "")
                description = func.get("description", "")

                if not name:
                    continue

                analysis = analyze_function(name, description)
                results[name] = analysis

        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Could not process {functions_file}: {e}", file=sys.stderr)

    return results


def save_analysis(results: dict[str, FunctionAnalysis], output_path: Path) -> None:
    """Save analysis results to JSON file."""
    data = {
        name: {
            "name": a.name,
            "app_name": a.app_name,
            "current_description": a.current_description,
            "issues": a.issues,
            "suggested_description": a.suggested_description,
            "status": a.status,
        }
        for name, a in results.items()
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


def load_analysis(input_path: Path) -> dict[str, dict]:
    """Load analysis results from JSON file."""
    with open(input_path) as f:
        return json.load(f)


def generate_report(results: dict[str, dict], output_path: Path) -> None:
    """Generate a markdown report for human review."""
    # Group by app
    by_app: dict[str, list[dict]] = {}
    for name, data in results.items():
        if data["status"] == "no_issues":
            continue
        app = data["app_name"]
        if app not in by_app:
            by_app[app] = []
        by_app[app].append(data)

    # Generate report
    lines = [
        "# Function Description Improvement Report",
        "",
        "Review each suggestion below. Mark as 'approved' or 'rejected' in the JSON file.",
        "",
        "## Summary",
        "",
        f"- **Total functions with issues**: {len([r for r in results.values() if r['status'] != 'no_issues'])}",
        f"- **Apps affected**: {len(by_app)}",
        "",
    ]

    # Issue type summary
    issue_counts: dict[str, int] = {}
    for data in results.values():
        for issue in data.get("issues", []):
            itype = issue["issue_type"]
            issue_counts[itype] = issue_counts.get(itype, 0) + 1

    lines.append("### Issues by Type")
    lines.append("")
    for itype, count in sorted(issue_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- **{itype}**: {count}")
    lines.append("")

    # Per-app breakdown
    lines.append("---")
    lines.append("")

    for app in sorted(by_app.keys()):
        funcs = by_app[app]
        lines.append(f"## {app.upper()}")
        lines.append("")

        for func in funcs:
            lines.append(f"### `{func['name']}`")
            lines.append("")
            lines.append("**Current:**")
            lines.append(f"> {func['current_description']}")
            lines.append("")
            lines.append("**Issues:**")
            for issue in func["issues"]:
                lines.append(f"- {issue['issue_type']}: {issue['message']}")
            lines.append("")
            if func["suggested_description"]:
                lines.append("**Suggested:**")
                lines.append(f"> {func['suggested_description']}")
            lines.append("")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))


def apply_changes(input_path: Path, dry_run: bool = False) -> int:
    """
    Apply approved description changes to functions.json files.

    Args:
        input_path: Path to the reviewed improvements JSON
        dry_run: If True, only report what would change

    Returns:
        Number of changes applied
    """
    data = load_analysis(input_path)

    # Group approved changes by app
    changes_by_app: dict[str, dict[str, str]] = {}
    for name, info in data.items():
        if info.get("status") != "approved":
            continue
        if not info.get("suggested_description"):
            continue

        app = info["app_name"]
        if app not in changes_by_app:
            changes_by_app[app] = {}
        changes_by_app[app][name] = info["suggested_description"]

    changes_applied = 0

    for app, changes in changes_by_app.items():
        functions_file = APPS_DIR / app / "functions.json"
        if not functions_file.exists():
            print(f"Warning: {functions_file} not found", file=sys.stderr)
            continue

        with open(functions_file) as f:
            functions = json.load(f)

        modified = False
        for func in functions:
            name = func.get("name", "")
            if name in changes:
                old_desc = func.get("description", "")
                new_desc = changes[name]

                # Remove [NEEDS EXPANSION] marker if present
                if new_desc.endswith("[NEEDS EXPANSION]"):
                    new_desc = new_desc.replace(" [NEEDS EXPANSION]", "")

                if old_desc != new_desc:
                    if dry_run:
                        print(f"Would update {name}:")
                        print(f"  FROM: {old_desc}")
                        print(f"  TO:   {new_desc}")
                        print()
                    else:
                        func["description"] = new_desc
                        modified = True
                        changes_applied += 1

        if modified and not dry_run:
            with open(functions_file, "w") as f:
                json.dump(functions, f, indent=4)
            print(f"Updated {functions_file}")

    return changes_applied


def validate_all(fail_on_issues: bool = False) -> int:
    """
    Validate all function descriptions and report issues.

    Args:
        fail_on_issues: If True, exit with error code if issues found

    Returns:
        Number of functions with issues
    """
    results = analyze_all_apps()

    with_issues = [r for r in results.values() if r.status != "no_issues"]

    print(f"Analyzed {len(results)} functions")
    print(f"Functions with issues: {len(with_issues)}")

    if with_issues:
        print("\nIssue summary:")
        issue_counts: dict[str, int] = {}
        for analysis in with_issues:
            for issue in analysis.issues:
                itype = issue["issue_type"]
                issue_counts[itype] = issue_counts.get(itype, 0) + 1

        for itype, count in sorted(issue_counts.items(), key=lambda x: -x[1]):
            print(f"  {itype}: {count}")

        if fail_on_issues:
            print("\nValidation failed: description issues found")
            return len(with_issues)

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Analyze and improve function descriptions for LLM agents"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze all function descriptions")
    analyze_parser.add_argument(
        "--output", "-o", type=Path, default=Path("improvements.json"), help="Output JSON file"
    )

    # Report command
    report_parser = subparsers.add_parser("report", help="Generate markdown report")
    report_parser.add_argument(
        "--input", "-i", type=Path, default=Path("improvements.json"), help="Input JSON file"
    )
    report_parser.add_argument(
        "--output", "-o", type=Path, default=Path("improvements.md"), help="Output markdown file"
    )

    # Apply command
    apply_parser = subparsers.add_parser("apply", help="Apply approved changes")
    apply_parser.add_argument(
        "--input", "-i", type=Path, required=True, help="Input JSON file with reviewed changes"
    )
    apply_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would change without applying"
    )

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate all descriptions")
    validate_parser.add_argument(
        "--fail-on-issues", action="store_true", help="Exit with error if issues found"
    )

    args = parser.parse_args()

    if args.command == "analyze":
        print("Analyzing all function descriptions...")
        results = analyze_all_apps()

        with_issues = len([r for r in results.values() if r.status != "no_issues"])
        print(f"Found {with_issues} functions with issues out of {len(results)} total")

        save_analysis(results, args.output)
        print(f"Saved analysis to {args.output}")

    elif args.command == "report":
        print(f"Generating report from {args.input}...")
        data = load_analysis(args.input)
        generate_report(data, args.output)
        print(f"Saved report to {args.output}")

    elif args.command == "apply":
        changes = apply_changes(args.input, dry_run=args.dry_run)
        if args.dry_run:
            print(f"Would apply {changes} changes")
        else:
            print(f"Applied {changes} changes")

    elif args.command == "validate":
        issues = validate_all(fail_on_issues=args.fail_on_issues)
        if args.fail_on_issues and issues > 0:
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
