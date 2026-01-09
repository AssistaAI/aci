#!/usr/bin/env python3
"""
ACI DevOps MCP Server

Workflow:
1. validate_functions - Check functions.json files locally
2. fix_function - Auto-fix common issues locally
3. seed_local - Seed local Docker database to test changes
4. deploy_to_prod - Push to main when everything is good
5. seed_prod - Seed production database after deployment

Also provides:
- fetch_prod_logs - Get error logs from production
- list_apps / get_function_details - Browse apps and functions
"""

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from aci.common.validators.description import (
    fix_third_person_verb,
    validate_function_description,
)
from aci.common.validator import (
    validate_function_parameters_schema_common,
    validate_function_parameters_schema_rest_protocol,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MCP server
server = Server("aci-devops")

# Constants
BACKEND_DIR = Path(__file__).parent.parent
APPS_DIR = BACKEND_DIR / "apps"
ALLOWED_TOP_LEVEL_KEYS = ["path", "query", "header", "cookie", "body"]


def run_command(cmd: list[str], cwd: str | None = None, timeout: int = 60) -> tuple[int, str, str]:
    """Run a shell command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def validate_single_function(func: dict, app_name: str) -> dict[str, Any]:
    """Validate a single function definition and return issues found."""
    issues = []
    func_name = func.get("name", "unknown")

    # Validate description
    description = func.get("description", "")
    desc_issues = validate_function_description(func_name, description)
    for issue in desc_issues:
        issues.append({
            "type": issue.issue_type,
            "field": "description",
            "message": issue.message,
            "suggestion": issue.suggestion,
        })

    # Validate parameters schema
    parameters = func.get("parameters", {})
    if parameters:
        try:
            validate_function_parameters_schema_common(parameters, f"{func_name}.parameters")
            # Check if it's REST protocol
            protocol = func.get("protocol", "rest")
            if protocol == "rest":
                validate_function_parameters_schema_rest_protocol(
                    parameters, f"{func_name}.parameters", ALLOWED_TOP_LEVEL_KEYS
                )
        except ValueError as e:
            issues.append({
                "type": "SCHEMA_ERROR",
                "field": "parameters",
                "message": str(e),
                "suggestion": None,
            })

    return {
        "function": func_name,
        "valid": len(issues) == 0,
        "issues": issues,
    }


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        # === LOCAL DEVELOPMENT TOOLS ===
        Tool(
            name="validate_functions",
            description="[LOCAL] Validate functions.json files for one or all apps. Run this first to check for issues before seeding.",
            inputSchema={
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "App name to validate (e.g., 'gmail'). Leave empty to validate all apps.",
                    },
                    "verbose": {
                        "type": "boolean",
                        "description": "Include detailed issue information (default: true)",
                        "default": True,
                    },
                },
            },
        ),
        Tool(
            name="fix_function",
            description="[LOCAL] Auto-fix common issues in a function definition (e.g., third-person verbs). Changes are made to local files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "App name (e.g., 'gmail')",
                    },
                    "function_name": {
                        "type": "string",
                        "description": "Function name to fix. Leave empty to fix all functions in the app.",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, show what would be changed without making changes (default: true)",
                        "default": True,
                    },
                },
                "required": ["app_name"],
            },
        ),
        Tool(
            name="seed_local",
            description="[LOCAL] Seed the local Docker database with app/function data. Use this to test changes before deploying to production.",
            inputSchema={
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Specific app to seed. Leave empty to seed all apps.",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, show what would be executed without running (default: true)",
                        "default": True,
                    },
                },
            },
        ),
        # === PRODUCTION DEPLOYMENT TOOLS ===
        Tool(
            name="deploy_to_prod",
            description="[PROD] Commit and push changes to main branch to trigger CI/CD deployment. Only use after local validation and testing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "commit_message": {
                        "type": "string",
                        "description": "Git commit message",
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of files to commit. If empty, commits all changed files in backend/apps/",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, show what would be committed without actually committing (default: true)",
                        "default": True,
                    },
                },
                "required": ["commit_message"],
            },
        ),
        Tool(
            name="seed_prod",
            description="[PROD] Seed the production database on DigitalOcean Kubernetes. Only use after deployment is complete.",
            inputSchema={
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Specific app to seed. Leave empty to seed all apps.",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, show what would be executed without running (default: true)",
                        "default": True,
                    },
                },
            },
        ),
        Tool(
            name="fetch_prod_logs",
            description="[PROD] Fetch error logs from production DigitalOcean Kubernetes cluster to identify issues.",
            inputSchema={
                "type": "object",
                "properties": {
                    "lines": {
                        "type": "integer",
                        "description": "Number of log lines to fetch (default: 100)",
                        "default": 100,
                    },
                    "filter": {
                        "type": "string",
                        "description": "Filter logs by keyword (e.g., 'error', 'ValidationError')",
                    },
                },
            },
        ),
        # === BROWSE TOOLS ===
        Tool(
            name="list_apps",
            description="List all available apps in backend/apps/ with their function counts and status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Filter app names (case-insensitive)",
                    },
                },
            },
        ),
        Tool(
            name="get_function_details",
            description="Get detailed information about a specific function or list all functions in an app.",
            inputSchema={
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "App name (e.g., 'gmail')",
                    },
                    "function_name": {
                        "type": "string",
                        "description": "Specific function name. Leave empty to list all functions.",
                    },
                },
                "required": ["app_name"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    if name == "validate_functions":
        return await validate_functions(arguments)
    elif name == "fix_function":
        return await fix_function(arguments)
    elif name == "seed_local":
        return await seed_local(arguments)
    elif name == "deploy_to_prod":
        return await deploy_to_prod(arguments)
    elif name == "seed_prod":
        return await seed_prod(arguments)
    elif name == "fetch_prod_logs":
        return await fetch_prod_logs(arguments)
    elif name == "list_apps":
        return await list_apps(arguments)
    elif name == "get_function_details":
        return await get_function_details(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


# =============================================================================
# LOCAL DEVELOPMENT TOOLS
# =============================================================================

async def validate_functions(args: dict) -> list[TextContent]:
    """Validate functions.json files locally."""
    app_name = args.get("app_name", "")
    verbose = args.get("verbose", True)

    apps_to_validate = []
    if app_name:
        app_dir = APPS_DIR / app_name
        if not app_dir.exists():
            return [TextContent(type="text", text=f"App '{app_name}' not found in {APPS_DIR}")]
        apps_to_validate = [app_name]
    else:
        apps_to_validate = [d.name for d in APPS_DIR.iterdir() if d.is_dir() and (d / "functions.json").exists()]

    results = {
        "total_apps": len(apps_to_validate),
        "total_functions": 0,
        "valid_functions": 0,
        "invalid_functions": 0,
        "issues_by_type": {},
        "apps_with_issues": [],
    }

    for app in sorted(apps_to_validate):
        functions_file = APPS_DIR / app / "functions.json"
        if not functions_file.exists():
            continue

        try:
            with open(functions_file) as f:
                functions = json.load(f)
        except json.JSONDecodeError as e:
            results["apps_with_issues"].append({
                "app": app,
                "error": f"Invalid JSON: {e}",
            })
            continue

        app_issues = []
        for func in functions:
            results["total_functions"] += 1
            validation = validate_single_function(func, app)

            if validation["valid"]:
                results["valid_functions"] += 1
            else:
                results["invalid_functions"] += 1
                for issue in validation["issues"]:
                    issue_type = issue["type"]
                    results["issues_by_type"][issue_type] = results["issues_by_type"].get(issue_type, 0) + 1

                if verbose:
                    app_issues.append(validation)

        if app_issues:
            results["apps_with_issues"].append({
                "app": app,
                "functions": app_issues,
            })

    # Format output
    output = [
        "# Local Validation Results\n",
        f"- **Apps scanned:** {results['total_apps']}",
        f"- **Total functions:** {results['total_functions']}",
        f"- **Valid:** {results['valid_functions']}",
        f"- **Invalid:** {results['invalid_functions']}",
        "",
        "## Issues by Type",
    ]

    for issue_type, count in sorted(results["issues_by_type"].items(), key=lambda x: -x[1]):
        output.append(f"- {issue_type}: {count}")

    if verbose and results["apps_with_issues"]:
        output.append("\n## Detailed Issues (first 20 apps)")
        for app_data in results["apps_with_issues"][:20]:
            if "error" in app_data:
                output.append(f"\n### {app_data['app']}\n- Error: {app_data['error']}")
            else:
                output.append(f"\n### {app_data['app']}")
                for func_data in app_data.get("functions", [])[:5]:
                    output.append(f"\n**{func_data['function']}**")
                    for issue in func_data["issues"]:
                        output.append(f"  - [{issue['type']}] {issue['message']}")
                        if issue.get("suggestion"):
                            output.append(f"    → Suggestion: {issue['suggestion']}")

    if results["invalid_functions"] == 0:
        output.append("\n✅ All functions are valid! Ready to seed locally.")
    else:
        output.append(f"\n⚠️ Fix {results['invalid_functions']} issues before seeding.")

    return [TextContent(type="text", text="\n".join(output))]


async def fix_function(args: dict) -> list[TextContent]:
    """Auto-fix common issues in function definitions locally."""
    app_name = args.get("app_name")
    function_name = args.get("function_name", "")
    dry_run = args.get("dry_run", True)

    if not app_name:
        return [TextContent(type="text", text="Error: app_name is required")]

    functions_file = APPS_DIR / app_name / "functions.json"
    if not functions_file.exists():
        return [TextContent(type="text", text=f"Functions file not found: {functions_file}")]

    try:
        with open(functions_file) as f:
            functions = json.load(f)
    except json.JSONDecodeError as e:
        return [TextContent(type="text", text=f"Invalid JSON in {functions_file}: {e}")]

    changes = []
    modified = False

    for func in functions:
        name = func.get("name", "")
        if function_name and name != function_name:
            continue

        # Fix third-person verbs
        description = func.get("description", "")
        fixed_description = fix_third_person_verb(description)

        if fixed_description != description:
            changes.append({
                "function": name,
                "field": "description",
                "old": description,
                "new": fixed_description,
            })
            if not dry_run:
                func["description"] = fixed_description
                modified = True

    if not changes:
        return [TextContent(type="text", text=f"No auto-fixable issues found in {app_name}")]

    output = [f"# Auto-fix Results for {app_name}\n"]
    output.append(f"**Mode:** {'DRY RUN' if dry_run else 'APPLIED'}\n")
    output.append(f"**Changes:** {len(changes)}\n")

    for change in changes:
        output.append(f"\n## {change['function']}")
        output.append(f"- **Field:** {change['field']}")
        output.append(f"- **Old:** {change['old'][:100]}...")
        output.append(f"- **New:** {change['new'][:100]}...")

    if not dry_run and modified:
        with open(functions_file, "w") as f:
            json.dump(functions, f, indent=2)
        output.append(f"\n✅ Changes written to {functions_file}")
        output.append("Next: Run validate_functions to verify, then seed_local to test.")
    elif dry_run:
        output.append(f"\n⚠️ Dry run - no changes made. Run with dry_run=false to apply.")

    return [TextContent(type="text", text="\n".join(output))]


async def seed_local(args: dict) -> list[TextContent]:
    """Seed the local Docker database."""
    app_name = args.get("app_name", "")
    dry_run = args.get("dry_run", True)

    # Check if Docker is running
    code, _, stderr = run_command(["docker", "compose", "ps", "-q", "runner"], cwd=str(BACKEND_DIR))
    if code != 0:
        return [TextContent(type="text", text=f"Error: Docker compose not running. Start with: docker compose up --build\n\n{stderr}")]

    # Build the seed command
    if app_name:
        app_dir = APPS_DIR / app_name
        if not app_dir.exists():
            return [TextContent(type="text", text=f"App '{app_name}' not found")]

        has_app_json = (app_dir / "app.json").exists()
        has_functions_json = (app_dir / "functions.json").exists()

        if has_app_json and has_functions_json:
            seed_cmd = f"python -m aci.cli upsert-app --app-file ./apps/{app_name}/app.json --skip-dry-run && python -m aci.cli upsert-functions --functions-file ./apps/{app_name}/functions.json --skip-dry-run"
        elif has_functions_json:
            seed_cmd = f"python -m aci.cli upsert-functions --functions-file ./apps/{app_name}/functions.json --skip-dry-run"
        else:
            return [TextContent(type="text", text=f"App '{app_name}' has no app.json or functions.json")]
    else:
        seed_cmd = "./scripts/seed_db.sh --all --mock"

    output = [
        "# Local Database Seeding\n",
        f"**Mode:** {'DRY RUN' if dry_run else 'EXECUTING'}\n",
        f"**Target:** Local Docker (runner container)",
        f"**App:** {app_name or 'ALL'}",
        f"**Command:** {seed_cmd}",
    ]

    if dry_run:
        output.append("\n⚠️ Dry run - no seeding performed. Run with dry_run=false to execute.")
        output.append("\nWorkflow reminder:")
        output.append("1. validate_functions → Fix issues")
        output.append("2. seed_local(dry_run=false) → Test locally")
        output.append("3. deploy_to_prod → Push to main")
        output.append("4. seed_prod → Update production DB")
    else:
        # Execute via docker compose exec
        code, stdout, stderr = run_command(
            ["docker", "compose", "exec", "runner", "bash", "-c", seed_cmd],
            cwd=str(BACKEND_DIR),
            timeout=300
        )

        if code != 0:
            output.append(f"\n❌ Seeding failed:\n{stderr}")
        else:
            output.append(f"\n✅ Local seeding completed successfully!")
            # Show last 50 lines of output
            lines = stdout.strip().split("\n")
            output.append(f"\n```\n{chr(10).join(lines[-50:])}\n```")
            output.append("\nNext: If everything looks good, use deploy_to_prod to push to production.")

    return [TextContent(type="text", text="\n".join(output))]


# =============================================================================
# PRODUCTION DEPLOYMENT TOOLS
# =============================================================================

async def deploy_to_prod(args: dict) -> list[TextContent]:
    """Commit and push changes to main to trigger production deployment."""
    commit_message = args.get("commit_message", "")
    files = args.get("files", [])
    dry_run = args.get("dry_run", True)

    if not commit_message:
        return [TextContent(type="text", text="Error: commit_message is required")]

    # Get current git status
    code, stdout, stderr = run_command(["git", "status", "--porcelain"], cwd=str(BACKEND_DIR))
    if code != 0:
        return [TextContent(type="text", text=f"Git error: {stderr}")]

    changed_files = [line.strip() for line in stdout.strip().split("\n") if line.strip()]

    # Filter to only app files if no specific files provided
    if not files:
        files = [f.split()[-1] for f in changed_files if "apps/" in f and f.endswith(".json")]

    if not files:
        return [TextContent(type="text", text="No changed files to commit. Make sure you've made changes to app/function files.")]

    output = [
        "# Deploy to Production\n",
        f"**Mode:** {'DRY RUN' if dry_run else 'EXECUTING'}\n",
        f"**Commit message:** {commit_message}\n",
        "**Files to commit:**",
    ]
    for f in files:
        output.append(f"  - {f}")

    if dry_run:
        output.append("\n⚠️ Dry run - no changes made. Run with dry_run=false to commit and push.")
        output.append("\n**Checklist before deploying:**")
        output.append("- [ ] Ran validate_functions - all valid?")
        output.append("- [ ] Ran seed_local - tested locally?")
        output.append("- [ ] Ready to push to production?")
    else:
        # Check current branch
        code, branch, _ = run_command(["git", "branch", "--show-current"], cwd=str(BACKEND_DIR))
        current_branch = branch.strip()

        # Add files
        code, _, stderr = run_command(["git", "add"] + files, cwd=str(BACKEND_DIR))
        if code != 0:
            return [TextContent(type="text", text=f"Git add error: {stderr}")]

        # Commit
        full_message = f"{commit_message}\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
        code, _, stderr = run_command(["git", "commit", "-m", full_message], cwd=str(BACKEND_DIR))
        if code != 0:
            return [TextContent(type="text", text=f"Git commit error: {stderr}")]

        # Push to current branch first
        if current_branch != "main":
            code, _, stderr = run_command(["git", "push", "origin", current_branch], cwd=str(BACKEND_DIR))
            if code != 0:
                return [TextContent(type="text", text=f"Git push to {current_branch} error: {stderr}")]
            output.append(f"\n✅ Pushed to {current_branch}")

            # Cherry-pick to main
            code, commit_hash, _ = run_command(["git", "rev-parse", "HEAD"], cwd=str(BACKEND_DIR))
            commit_hash = commit_hash.strip()

            run_command(["git", "checkout", "main"], cwd=str(BACKEND_DIR))
            run_command(["git", "pull", "origin", "main"], cwd=str(BACKEND_DIR))
            code, _, stderr = run_command(["git", "cherry-pick", commit_hash], cwd=str(BACKEND_DIR))
            if code != 0:
                run_command(["git", "checkout", current_branch], cwd=str(BACKEND_DIR))
                return [TextContent(type="text", text=f"Cherry-pick to main error: {stderr}")]

            code, _, stderr = run_command(["git", "push", "origin", "main"], cwd=str(BACKEND_DIR))
            run_command(["git", "checkout", current_branch], cwd=str(BACKEND_DIR))

            if code != 0:
                return [TextContent(type="text", text=f"Git push to main error: {stderr}")]
        else:
            code, _, stderr = run_command(["git", "push", "origin", "main"], cwd=str(BACKEND_DIR))
            if code != 0:
                return [TextContent(type="text", text=f"Git push error: {stderr}")]

        output.append("\n✅ Changes committed and pushed to main")
        output.append("CI/CD pipeline will automatically deploy to DigitalOcean.")
        output.append("\nNext: Wait for deployment to complete, then run seed_prod to update the database.")

    return [TextContent(type="text", text="\n".join(output))]


async def seed_prod(args: dict) -> list[TextContent]:
    """Seed the production database on DigitalOcean Kubernetes."""
    app_name = args.get("app_name", "")
    dry_run = args.get("dry_run", True)
    namespace = "aci-prod"

    # Check kubectl availability
    code, _, _ = run_command(["which", "kubectl"])
    if code != 0:
        return [TextContent(type="text", text="Error: kubectl not found. Install kubectl and configure for DO cluster.")]

    # Check cluster access
    code, _, stderr = run_command(["kubectl", "get", "pods", "-n", namespace, "--no-headers"])
    if code != 0:
        return [TextContent(type="text", text=f"Error accessing cluster: {stderr}\n\nRun: doctl kubernetes cluster kubeconfig save assista-kube-prod-nyc1")]

    # Build the seed command
    if app_name:
        seed_cmd = f"python -m aci.cli upsert-app --app-file ./apps/{app_name}/app.json --skip-dry-run && python -m aci.cli upsert-functions --functions-file ./apps/{app_name}/functions.json --skip-dry-run"
    else:
        seed_cmd = "./scripts/seed_db.sh --all --mock"

    output = [
        "# Production Database Seeding\n",
        f"**Mode:** {'DRY RUN' if dry_run else 'EXECUTING'}\n",
        f"**Target:** DigitalOcean Kubernetes ({namespace})",
        f"**App:** {app_name or 'ALL'}",
        f"**Command:** {seed_cmd}",
    ]

    if dry_run:
        output.append("\n⚠️ Dry run - no seeding performed. Run with dry_run=false to execute.")
        output.append("\n**Checklist before seeding prod:**")
        output.append("- [ ] Deployment completed successfully?")
        output.append("- [ ] Checked GitHub Actions status?")
    else:
        # Get a backend pod
        code, stdout, stderr = run_command([
            "kubectl", "get", "pods", "-n", namespace,
            "-l", "app=aci-backend",
            "-o", "jsonpath={.items[0].metadata.name}"
        ])

        if code != 0 or not stdout.strip():
            return [TextContent(type="text", text=f"Error finding pod: {stderr}")]

        pod_name = stdout.strip()
        output.append(f"**Pod:** {pod_name}")

        # Execute seed command
        code, stdout, stderr = run_command([
            "kubectl", "exec", "-n", namespace, pod_name,
            "--", "bash", "-c", seed_cmd
        ], timeout=600)

        if code != 0:
            output.append(f"\n❌ Seeding failed:\n{stderr}")
        else:
            output.append(f"\n✅ Production seeding completed successfully!")
            lines = stdout.strip().split("\n")
            output.append(f"\n```\n{chr(10).join(lines[-50:])}\n```")

    return [TextContent(type="text", text="\n".join(output))]


async def fetch_prod_logs(args: dict) -> list[TextContent]:
    """Fetch error logs from production."""
    lines = args.get("lines", 100)
    log_filter = args.get("filter", "")
    namespace = "aci-prod"

    # Check kubectl availability
    code, _, _ = run_command(["which", "kubectl"])
    if code != 0:
        return [TextContent(type="text", text="Error: kubectl not found")]

    # Get pod names
    code, stdout, stderr = run_command([
        "kubectl", "get", "pods", "-n", namespace,
        "-l", "app=aci-backend",
        "-o", "jsonpath={.items[*].metadata.name}"
    ])

    if code != 0:
        return [TextContent(type="text", text=f"Error getting pods: {stderr}")]

    pods = stdout.strip().split()
    if not pods:
        return [TextContent(type="text", text=f"No pods found in {namespace}")]

    # Fetch logs from first pod
    pod = pods[0]
    code, stdout, stderr = run_command([
        "kubectl", "logs", "-n", namespace, pod,
        f"--tail={lines}", "--timestamps"
    ], timeout=30)

    if code != 0:
        return [TextContent(type="text", text=f"Error getting logs: {stderr}")]

    log_lines = stdout.strip().split("\n")
    if log_filter:
        log_lines = [l for l in log_lines if log_filter.lower() in l.lower()]

    output = [
        f"# Production Logs ({namespace})\n",
        f"**Pod:** {pod}",
        f"**Filter:** {log_filter or 'none'}",
        f"**Lines:** {len(log_lines)}",
        "",
        "```",
    ]
    output.extend(log_lines[-100:])  # Last 100 matching lines
    output.append("```")

    return [TextContent(type="text", text="\n".join(output))]


# =============================================================================
# BROWSE TOOLS
# =============================================================================

async def list_apps(args: dict) -> list[TextContent]:
    """List all available apps."""
    filter_text = args.get("filter", "").lower()

    apps = []
    for app_dir in sorted(APPS_DIR.iterdir()):
        if not app_dir.is_dir():
            continue

        app_name = app_dir.name
        if filter_text and filter_text not in app_name.lower():
            continue

        has_app_json = (app_dir / "app.json").exists()
        has_functions_json = (app_dir / "functions.json").exists()

        func_count = 0
        if has_functions_json:
            try:
                with open(app_dir / "functions.json") as f:
                    funcs = json.load(f)
                    func_count = len(funcs)
            except:
                pass

        apps.append({
            "name": app_name,
            "has_app_json": has_app_json,
            "has_functions_json": has_functions_json,
            "function_count": func_count,
        })

    output = [f"# Apps ({len(apps)} found)\n"]
    output.append("| App | Functions | Status |")
    output.append("|-----|-----------|--------|")

    for app in apps:
        status = "✅" if app["has_app_json"] and app["has_functions_json"] else "⚠️"
        output.append(f"| {app['name']} | {app['function_count']} | {status} |")

    return [TextContent(type="text", text="\n".join(output))]


async def get_function_details(args: dict) -> list[TextContent]:
    """Get detailed information about functions."""
    app_name = args.get("app_name")
    function_name = args.get("function_name", "")

    if not app_name:
        return [TextContent(type="text", text="Error: app_name is required")]

    functions_file = APPS_DIR / app_name / "functions.json"
    if not functions_file.exists():
        return [TextContent(type="text", text=f"Functions file not found for app '{app_name}'")]

    try:
        with open(functions_file) as f:
            functions = json.load(f)
    except json.JSONDecodeError as e:
        return [TextContent(type="text", text=f"Invalid JSON: {e}")]

    if function_name:
        func = next((f for f in functions if f.get("name") == function_name), None)
        if not func:
            return [TextContent(type="text", text=f"Function '{function_name}' not found in {app_name}")]

        output = [f"# {function_name}\n"]
        output.append(f"**Description:** {func.get('description', 'N/A')}")
        output.append(f"**Protocol:** {func.get('protocol', 'N/A')}")
        output.append(f"**Tags:** {', '.join(func.get('tags', []))}")
        output.append(f"**Visibility:** {func.get('visibility', 'N/A')}")
        output.append(f"**Active:** {func.get('active', 'N/A')}")

        protocol_data = func.get("protocol_data", {})
        if protocol_data:
            output.append(f"**Method:** {protocol_data.get('method', 'N/A')}")
            output.append(f"**Path:** {protocol_data.get('path', 'N/A')}")

        output.append(f"\n**Parameters:**\n```json\n{json.dumps(func.get('parameters', {}), indent=2)[:2000]}\n```")
    else:
        output = [f"# Functions in {app_name} ({len(functions)} total)\n"]
        for func in functions:
            name = func.get("name", "unknown")
            desc = func.get("description", "No description")[:80]
            output.append(f"- **{name}**: {desc}...")

    return [TextContent(type="text", text="\n".join(output))]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
