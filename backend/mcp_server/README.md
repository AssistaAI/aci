# ACI DevOps MCP Server

MCP server for managing ACI function definitions with a local-first workflow.

## Workflow

```
1. validate_functions  →  Check for issues locally
2. fix_function        →  Auto-fix problems locally
3. seed_local          →  Test with local Docker DB
4. deploy_to_prod      →  Push to main (triggers CI/CD)
5. seed_prod           →  Update production database
```

## Tools

### Local Development

| Tool | Description |
|------|-------------|
| `validate_functions` | Check functions.json files for schema/description issues |
| `fix_function` | Auto-fix common issues (third-person verbs, etc.) |
| `seed_local` | Seed local Docker database via `docker compose exec` |

### Production Deployment

| Tool | Description |
|------|-------------|
| `deploy_to_prod` | Commit and push to main, triggers GitHub Actions |
| `seed_prod` | Seed production DB on DigitalOcean Kubernetes |
| `fetch_prod_logs` | Get error logs from production cluster |

### Browse

| Tool | Description |
|------|-------------|
| `list_apps` | List all apps with function counts |
| `get_function_details` | View function details/parameters |

## Setup

### Prerequisites

- Python 3.12+ with ACI backend dependencies
- Docker (for local seeding)
- kubectl + doctl (for production operations)

### Enable in Claude Code

The MCP server is configured in `.mcp.json` at the project root. Restart Claude Code to load it.

### Local Docker Setup

```bash
cd backend
docker compose up --build
```

### Production Access (kubectl)

```bash
brew install doctl
doctl auth init
doctl kubernetes cluster kubeconfig save assista-kube-prod-nyc1
```

## Usage Examples

### Validate all functions
```
validate_functions()
```

### Fix a specific app
```
fix_function(app_name="slack", dry_run=false)
```

### Test locally before deploying
```
seed_local(app_name="slack", dry_run=false)
```

### Deploy to production
```
deploy_to_prod(commit_message="Fix Slack functions", dry_run=false)
```

### Seed production after deployment
```
seed_prod(app_name="slack", dry_run=false)
```

## Validation Rules

### Description Validation
- Minimum 6 words
- Must start with imperative verb (not third-person like "Creates")
- No redundant app name prefix
- Short descriptions must include app context

### Schema Validation
- Must have `properties`, `required`, `visible`, `additionalProperties` fields
- All required/visible properties must exist
- Non-visible required properties must have defaults
- REST protocol allows only: `path`, `query`, `header`, `cookie`, `body`
