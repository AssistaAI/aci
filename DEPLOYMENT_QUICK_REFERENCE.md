# Quick Deployment Reference - Pagination Updates

## 🚀 To Deploy

### Automatic (Recommended)
```bash
git add .
git commit -m "Add pagination and performance indexes"
git push origin dev    # Test on staging first
# ✅ Watch GitHub Actions
git push origin main   # Deploy to production
```

### Manual Safety Check (Optional)
```bash
export KUBECONFIG=/path/to/kubeconfig

# Check current state
kubectl exec -n aci-prod deployment/aci-backend -- alembic current

# Run migration manually
kubectl exec -n aci-prod deployment/aci-backend -- alembic upgrade head

# Then deploy code
git push origin main
```

---

## 📋 New Files Created

**K8s Manifests:**
- ✨ `backend/k8s/migration-job.yaml` - Runs migrations before deployment
- ✨ `backend/k8s/migration-check-job.yaml` - Verifies migration status

**Migration:**
- ✨ `backend/aci/alembic/versions/2025_11_20_1257-add_performance_indexes.py`

**Frontend:**
- ✨ `frontend/src/hooks/use-pagination.tsx` - Reusable pagination hook

**CI/CD:**
- ✏️ `.github/workflows/backend-deployment.yml` - Now runs migrations automatically

---

## 🔍 What Happens on Deploy

```
1. Build Docker Image
2. Check Migration Status (Pre) ⚠️
3. Run Migrations 🔒 BLOCKS IF FAILS
4. Deploy to K8s (only if migrations succeed)
5. Wait for Rollout
6. Verify Migration Status (Post) ⚠️
```

**Key Point**: Deployment **STOPS** if migrations fail. Old version keeps running.

---

## ✅ Verify Deployment Success

```bash
# 1. Check GitHub Actions
# Go to Actions tab → "Build and Deploy backend"
# Look for ✅ "Run Database Migrations" step

# 2. Check indexes exist
kubectl exec -n aci-prod deployment/aci-backend -- \
  psql $DATABASE_URL -c "\di" | grep "ix_"

# Should show 16 new indexes

# 3. Check migration applied
kubectl exec -n aci-prod deployment/aci-backend -- alembic current
# Should show: add_perf_indexes (head)

# 4. Test frontend
# Visit /linked-accounts - should show pagination
# Visit /appconfigs - should show pagination
```

---

## 🔧 Troubleshooting

### Migration Failed
```bash
# Check logs
kubectl logs job/aci-migrate-<BUILD_NUMBER> -n aci-prod

# Access database
kubectl exec -it -n aci-prod deployment/aci-backend -- bash
alembic current
alembic history
```

### Rollback Migration
```bash
kubectl exec -it -n aci-prod deployment/aci-backend -- bash
alembic downgrade -1
```

### Check What's Running
```bash
# Check jobs
kubectl get jobs -n aci-prod | grep migrate

# Check pods
kubectl get pods -n aci-prod | grep backend

# Check logs
kubectl logs -n aci-prod deployment/aci-backend --tail=100
```

---

## 📊 What Changed

**Backend:**
- 16 new database indexes (performance)
- Pagination for linked accounts (was: ALL records, now: 15/page)
- Pagination for projects (was: ALL, now: 100/page default)

**Frontend:**
- Server-side pagination on `/linked-accounts`
- Server-side pagination on `/appconfigs`
- Reusable `usePagination` hook

**CI/CD:**
- Automated migration before deployment
- Pre/post migration verification
- Deployment blocks if migration fails

---

## 🎯 Success Criteria

- ✅ GitHub Actions workflow succeeds
- ✅ Migration logs show "completed successfully"
- ✅ 16 indexes exist in database
- ✅ Pagination controls visible in UI
- ✅ API uses `?limit=15&offset=0` params
- ✅ No errors in logs

---

## 📈 Expected Improvements

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Network transfer | 500KB+ | 20-50KB | 95% ↓ |
| Query time | 1000ms+ | 10-50ms | 95% ↓ |
| Memory usage | All records | 15 records | 90% ↓ |

---

## 🆘 Emergency Contacts

**Rollback Command:**
```bash
kubectl exec -it deployment/aci-backend -n aci-prod -- alembic downgrade -1
```

**Check Deployment:**
```bash
kubectl get pods -n aci-prod
kubectl describe deployment/aci-backend -n aci-prod
kubectl logs -n aci-prod deployment/aci-backend
```

---

## 📝 Testing Checklist

Before pushing to production:

- [ ] Test on `dev` environment first
- [ ] Verify migration logs in GitHub Actions
- [ ] Check linked accounts page pagination
- [ ] Check app configs page pagination
- [ ] Verify API responses have limit/offset params
- [ ] Monitor application logs for errors
- [ ] Check database query performance

---

## 🔐 Safety Features

1. ✅ **Non-destructive** - Only adds indexes, no data changes
2. ✅ **Reversible** - Full downgrade support
3. ✅ **Gated deployment** - Won't deploy if migration fails
4. ✅ **Zero downtime** - Old version runs during migration
5. ✅ **Auto-retry** - Up to 3 attempts on failure
6. ✅ **Auto-cleanup** - Jobs deleted after 1 hour

---

For full details, see [DEPLOYMENT_MIGRATION_GUIDE.md](DEPLOYMENT_MIGRATION_GUIDE.md)
