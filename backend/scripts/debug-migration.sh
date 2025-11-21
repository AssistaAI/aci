#!/bin/bash

# Debug migration issues in production
# Usage: ./scripts/debug-migration.sh [namespace]

NAMESPACE=${1:-aci-prod}

echo "=== Debugging migration in namespace: $NAMESPACE ==="
echo ""

echo "=== 1. Check current migration status ==="
kubectl exec -n $NAMESPACE deployment/aci-backend -- alembic current || echo "Could not check current migration"
echo ""

echo "=== 2. Check migration history ==="
kubectl exec -n $NAMESPACE deployment/aci-backend -- alembic history --verbose | head -30 || echo "Could not check history"
echo ""

echo "=== 3. Check for pending migrations ==="
kubectl exec -n $NAMESPACE deployment/aci-backend -- sh -c "
  CURRENT=\$(alembic current 2>/dev/null | grep -oP '(?<=^)[a-f0-9]+')
  HEAD=\$(alembic heads 2>/dev/null | grep -oP '(?<=^)[a-f0-9]+')
  if [ \"\$CURRENT\" != \"\$HEAD\" ]; then
    echo 'Pending migrations detected!'
    echo \"Current: \$CURRENT\"
    echo \"Head: \$HEAD\"
  else
    echo 'Database is up to date'
  fi
" || echo "Could not check pending migrations"
echo ""

echo "=== 4. Check recent migration jobs ==="
kubectl get jobs -n $NAMESPACE | grep migrate | head -10
echo ""

echo "=== 5. Check failed migration pods ==="
kubectl get pods -n $NAMESPACE | grep migrate | grep -E "(Error|CrashLoopBackOff|Failed)"
echo ""

echo "=== 6. Get logs from most recent failed migration pod ==="
LATEST_POD=$(kubectl get pods -n $NAMESPACE | grep migrate | grep -E "(Error|CrashLoopBackOff|Failed)" | head -1 | awk '{print $1}')
if [ ! -z "$LATEST_POD" ]; then
  echo "Getting logs from: $LATEST_POD"
  kubectl logs -n $NAMESPACE $LATEST_POD || echo "Could not get logs"
  echo ""
  echo "=== Pod description ==="
  kubectl describe pod -n $NAMESPACE $LATEST_POD | tail -50
else
  echo "No failed migration pods found"
fi
echo ""

echo "=== 7. Check database connection ==="
kubectl exec -n $NAMESPACE deployment/aci-backend -- sh -c "
  echo 'Testing database connection...'
  psql \$DATABASE_URL -c 'SELECT version();' 2>&1 | head -5
" || echo "Could not connect to database"
echo ""

echo "=== 8. Check if indexes already exist ==="
kubectl exec -n $NAMESPACE deployment/aci-backend -- sh -c "
  echo 'Checking for existing performance indexes...'
  psql \$DATABASE_URL -c \"SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND indexname LIKE 'ix_%' ORDER BY indexname;\" 2>&1
" || echo "Could not check indexes"
echo ""

echo "=== 9. Check alembic_version table ==="
kubectl exec -n $NAMESPACE deployment/aci-backend -- sh -c "
  echo 'Current alembic version in database:'
  psql \$DATABASE_URL -c 'SELECT * FROM alembic_version;' 2>&1
" || echo "Could not check alembic_version table"
echo ""

echo "=== 10. Recent namespace events ==="
kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' | tail -20
echo ""

echo "=== Debug complete ==="
echo ""
echo "To manually run migration:"
echo "  kubectl exec -it -n $NAMESPACE deployment/aci-backend -- alembic upgrade head"
echo ""
echo "To rollback last migration:"
echo "  kubectl exec -it -n $NAMESPACE deployment/aci-backend -- alembic downgrade -1"
echo ""
echo "To access database directly:"
echo "  kubectl exec -it -n $NAMESPACE deployment/aci-backend -- psql \$DATABASE_URL"
