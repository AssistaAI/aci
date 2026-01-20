#!/bin/bash
# Run the schema fix scheduler
# This can be called by cron or run as a background process

# For cron, add this to crontab:
# 0 * * * * cd /path/to/backend && ./scripts/run_schema_fix_scheduler.sh >> /var/log/schema_fix_scheduler.log 2>&1

# For Docker:
# docker compose exec runner python -m aci.scheduler.schema_fix_scheduler

set -e

cd "$(dirname "$0")/.."

# Check if running in Docker
if [ -f /.dockerenv ]; then
    python -m aci.scheduler.schema_fix_scheduler
else
    # Run via docker compose
    docker compose exec -T runner python -m aci.scheduler.schema_fix_scheduler
fi
