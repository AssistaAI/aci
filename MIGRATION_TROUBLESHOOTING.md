# Migration Troubleshooting Guide

The migration job is failing repeatedly. Here's how to diagnose and fix it.

## Quick Diagnosis

Run the debug script to see what's happening:

```bash
cd backend
./scripts/debug-migration.sh aci-prod
```

This will show:
- Current migration status
- Any pending migrations
- Failed pod logs
- Database connection status
- Existing indexes

## Most Likely Issues

### Issue 1: Database Connection Problem

**Symptoms:**
- Pods failing immediately
- No logs visible
- "BackoffLimitExceeded" after 4 retries

**Check:**
```bash
kubectl exec -n aci-prod deployment/aci-backend -- \
  psql $DATABASE_URL -c 'SELECT version();'
```

**Fixes:**
- Database might be restarting
- Check database pods: `kubectl get pods -n aci-prod | grep postgres`
- Check database logs: `kubectl logs -n aci-prod aci-postgres-rw-1`

### Issue 2: Missing Environment Variables

**Symptoms:**
- Pod starts but crashes immediately
- Error about connection string

**Check:**
```bash
kubectl describe job aci-migrate-95 -n aci-prod
# Look at Environment section
```

**Fixes:**
- Verify secrets exist: `kubectl get secrets -n aci-prod | grep postgres`
- Check secret contents: `kubectl get secret aci-postgres-app -n aci-prod -o yaml`

### Issue 3: Alembic Can't Find Migration Files

**Symptoms:**
- Error: "Can't locate revision identified by 'add_perf_indexes'"
- Error: "Migration file not found"

**Check:**
```bash
kubectl exec -n aci-prod deployment/aci-backend -- ls -la aci/alembic/versions/
```

**Fixes:**
- Migration file might not be in Docker image
- Check Dockerfile.server.prod includes: `COPY ./aci /workdir/aci`
- Rebuild image: Force push to trigger new build

### Issue 4: Migration Conflicts

**Symptoms:**
- Error: "Target database is not up to date"
- Error: "Can't apply migration from X to Y"

**Check:**
```bash
kubectl exec -n aci-prod deployment/aci-backend -- alembic current
kubectl exec -n aci-prod deployment/aci-backend -- alembic heads
```

**Fixes:**
```bash
# See what's pending
kubectl exec -it -n aci-prod deployment/aci-backend -- bash
alembic history
alembic current
alembic heads

# If stuck, stamp to current head
alembic stamp head
```

### Issue 5: Indexes Already Exist (Should be fixed now)

**Symptoms:**
- Error: "relation 'ix_apps_visibility' already exists"
- DuplicateTable error

**Check:**
```bash
kubectl exec -n aci-prod deployment/aci-backend -- \
  psql $DATABASE_URL -c "\di" | grep ix_
```

**Fix:**
This should be handled by `if_not_exists=True` in the migration. If not:
```bash
# Manually drop conflicting indexes
kubectl exec -it -n aci-prod deployment/aci-backend -- \
  psql $DATABASE_URL -c "DROP INDEX IF EXISTS ix_apps_visibility;"
# ... repeat for all failing indexes
```

## Manual Migration Execution

If the job keeps failing, run migration manually:

```bash
# 1. Get shell access
kubectl exec -it -n aci-prod deployment/aci-backend -- bash

# 2. Check current state
alembic current
alembic history | head -20

# 3. Try to upgrade
alembic upgrade head

# 4. If it fails, check the error
# Common fixes:

# - Missing table: Check if you need earlier migrations
alembic history

# - Wrong revision: Stamp to correct version
alembic stamp 48bf142a794c  # Previous migration
alembic upgrade head

# - Database locked: Wait and retry
# - Connection timeout: Check database is running
```

## Get Detailed Logs

### From Failed Job
```bash
# List all migration jobs
kubectl get jobs -n aci-prod | grep migrate

# Get pods for a specific job
kubectl get pods -n aci-prod -l job-name=aci-migrate-95

# Get logs from specific pod
kubectl logs -n aci-prod aci-migrate-95-jkpqw

# Get pod details
kubectl describe pod -n aci-prod aci-migrate-95-jkpqw
```

### From Current Deployment
```bash
# Try migration from running backend pod
kubectl exec -n aci-prod deployment/aci-backend -- alembic upgrade head

# Check backend logs
kubectl logs -n aci-prod deployment/aci-backend --tail=100
```

## Common Error Messages

### "FATAL: password authentication failed"
- **Issue**: Wrong database credentials
- **Fix**: Check secrets, verify database user

### "could not connect to server: Connection refused"
- **Issue**: Database not accessible
- **Fix**: Check database is running, check network policies

### "relation does not exist"
- **Issue**: Missing table, wrong schema
- **Fix**: Check migration history, may need to run earlier migrations

### "Target database is not up to date"
- **Issue**: Database schema doesn't match migration expectations
- **Fix**: Check `alembic current`, may need to stamp

### "Can't locate revision"
- **Issue**: Migration file missing or wrong revision ID
- **Fix**: Check Docker image includes migration files

## Nuclear Option: Reset Migration State

⚠️ **DANGER**: Only do this if you understand the implications!

```bash
kubectl exec -it -n aci-prod deployment/aci-backend -- bash

# 1. Check what the actual database schema is
psql $DATABASE_URL -c "\d apps" | head -30

# 2. If indexes already exist, stamp to new migration
alembic stamp add_perf_indexes

# 3. Verify
alembic current
# Should show: add_perf_indexes (head)

# 4. Exit and deploy
exit
```

## Verify Fix

After fixing, verify:

```bash
# 1. Check migration status
kubectl exec -n aci-prod deployment/aci-backend -- alembic current
# Should show: add_perf_indexes (head)

# 2. Check indexes exist
kubectl exec -n aci-prod deployment/aci-backend -- \
  psql $DATABASE_URL -c "SELECT indexname FROM pg_indexes WHERE indexname LIKE 'ix_%' ORDER BY indexname;"
# Should show 16 indexes

# 3. Test application
curl https://aci-api.assista.dev/v1/apps?limit=10

# 4. Check logs for errors
kubectl logs -n aci-prod deployment/aci-backend --tail=50
```

## Push Updated Code

After updating workflow for better logging:

```bash
git add .
git commit -m "Improve migration error logging in CI/CD"
git push origin main
```

The next deployment will show much more detailed error information!

## Getting Help

If still stuck, gather this info:

```bash
# Run debug script and save output
./scripts/debug-migration.sh aci-prod > migration-debug.txt

# Get job description
kubectl describe job aci-migrate-95 -n aci-prod >> migration-debug.txt

# Get pod logs
kubectl logs aci-migrate-95-jkpqw -n aci-prod >> migration-debug.txt 2>&1

# Share migration-debug.txt
```

## Quick Fixes Reference

| Problem | Quick Fix |
|---------|-----------|
| Job fails immediately | Check database connection |
| "Index exists" error | Already fixed with `if_not_exists=True` |
| "Can't locate revision" | Migration file missing from image, rebuild |
| "Connection refused" | Database pod might be down |
| "Password auth failed" | Check secrets |
| Wrong migration state | Stamp to correct version |
| Timeout after 5min | Database slow, increase timeout |

## Contact & Escalation

If migration keeps failing:
1. Check database health first
2. Try manual migration
3. Review actual error logs (not just job status)
4. Consider stamping if indexes already exist
5. As last resort: Create indexes manually, then stamp
