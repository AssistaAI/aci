"""
Validation utilities for function and app descriptions.

Ensures descriptions are optimized for LLM agent tool selection by checking:
- Minimum length for sufficient context
- Imperative verb form (not third person)
- App context in short descriptions
- No redundant app name prefixes
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DescriptionIssue:
    """Represents an issue found in a description."""

    issue_type: str
    message: str
    suggestion: str | None = None


# Mapping from third-person verbs to imperative form
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

# Minimum word count for descriptions
MIN_WORD_COUNT = 6

# Word count threshold below which app context is required
APP_CONTEXT_THRESHOLD = 12


def validate_function_description(name: str, description: str) -> list[DescriptionIssue]:
    """
    Validate a function description and return a list of issues found.

    Args:
        name: Function name in format APP_NAME__FUNCTION_NAME
        description: The function description to validate

    Returns:
        List of DescriptionIssue objects describing problems found
    """
    issues: list[DescriptionIssue] = []

    if not description or not description.strip():
        issues.append(
            DescriptionIssue(
                issue_type="EMPTY_DESCRIPTION",
                message="Description is empty or contains only whitespace",
                suggestion=None,
            )
        )
        return issues

    words = description.split()
    word_count = len(words)

    # Extract app name from function name (e.g., GMAIL from GMAIL__SEND_EMAIL)
    app_name = name.split("__")[0].lower() if "__" in name else ""

    # Rule 1: Minimum length check
    if word_count < MIN_WORD_COUNT:
        issues.append(
            DescriptionIssue(
                issue_type="TOO_SHORT",
                message=f"Description has only {word_count} words (minimum {MIN_WORD_COUNT})",
                suggestion="Add more context about what the function does, what parameters it accepts, or what it returns",
            )
        )

    # Rule 2: Imperative verb form check
    first_word = words[0].lower() if words else ""
    if first_word in THIRD_PERSON_TO_IMPERATIVE:
        imperative = THIRD_PERSON_TO_IMPERATIVE[first_word]
        issues.append(
            DescriptionIssue(
                issue_type="THIRD_PERSON_VERB",
                message=f"Use imperative verb form instead of third person '{words[0]}'",
                suggestion=imperative,
            )
        )

    # Rule 3: No redundant app name prefix
    if app_name and first_word == app_name:
        issues.append(
            DescriptionIssue(
                issue_type="REDUNDANT_APP_PREFIX",
                message="Don't start description with app name (already in function name)",
                suggestion="Remove the app name prefix and start with an action verb",
            )
        )

    # Rule 4: App context required for short descriptions
    if word_count < APP_CONTEXT_THRESHOLD and app_name:
        # Check if description mentions the app or related context
        description_lower = description.lower()
        app_variants = [
            app_name,
            app_name.replace("_", " "),
            app_name.replace("_", ""),
        ]
        has_app_context = any(variant in description_lower for variant in app_variants)

        # Also accept generic context words
        context_words = ["api", "workspace", "account", "platform", "service", "crm", "database"]
        has_generic_context = any(word in description_lower for word in context_words)

        if not has_app_context and not has_generic_context:
            issues.append(
                DescriptionIssue(
                    issue_type="MISSING_APP_CONTEXT",
                    message="Short descriptions should mention the app/platform for disambiguation",
                    suggestion=f"Include '{app_name.replace('_', ' ').title()}' or relevant context in the description",
                )
            )

    return issues


def fix_third_person_verb(description: str) -> str:
    """
    Fix third-person verb at the start of a description to imperative form.

    Args:
        description: The description to fix

    Returns:
        The description with the first word converted to imperative form if applicable
    """
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


def get_issue_summary(issues: list[DescriptionIssue]) -> dict[str, int]:
    """
    Get a summary count of issues by type.

    Args:
        issues: List of DescriptionIssue objects

    Returns:
        Dictionary mapping issue types to counts
    """
    summary: dict[str, int] = {}
    for issue in issues:
        summary[issue.issue_type] = summary.get(issue.issue_type, 0) + 1
    return summary
