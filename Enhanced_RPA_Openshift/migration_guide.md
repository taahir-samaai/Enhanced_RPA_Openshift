# Migration Guide: Current RPA to Enhanced Deployment

This guide walks through migrating from the current RPA setup to the enhanced three-layer architecture with Valkey-based TOTP management.

## Overview

### What's Changing

| Component | Current | Enhanced |
|-----------|---------|----------|
| **Architecture** | 2-Layer (Orchestrator + Workers) | 3-Layer (Orchestrator + Workers + Browser Services) |
| **Browser Execution** | Workers run Chrome directly | Dedicated browser service pods |
| **TOTP Management** | Each worker generates codes | Centralized in orchestrator via Valkey |
| **Configuration** | config.py file | OpenShift Secrets + ConfigMaps |
| **Security** | Standard containers | Least-privilege + privileged browser isolation |
| **High Availability** | None | Valkey clustering with Sentinel |
| **Scaling** | Manual | Automatic with HPA |

### Migration Timeline

**Total Estimated Time: 2-4 hours** (excluding testing)

- Pre-migration prep: 30 minutes
- Backup & safety: 15 minutes
- Deploy new infrastructure: 45 minutes
- Data migration: 30 minutes
- Testing & validation: 1-2 hours
- Cutover: 15 minutes

## Pre-Migration Checklist

### 1. Document Current State

```bash
# Capture current deployment
oc get all -n rpa-system -o yaml > backup/current-deployment.yaml

# Export current configuration
oc get configmap -n rpa-system -o yaml > backup/current-configmaps.yaml
oc get secret -n rpa-system -o yaml > backup/current-secrets.yaml

# Document current resource usage
oc top pods -n rpa-system > backup/current-resource-usage.txt

# Save current logs
for pod in $(oc get pods -n rpa-system -o name); do
  oc logs $pod -n rpa-system > backup/logs/$(basename $pod).log
done
```

### 2. Extract Configuration Values

Create a mapping of current config.py values to new secrets:

```python
# Current config.py structure → New location
METROFIBER_URL → Secret: metrofiber-credentials.url
METROFIBER_EMAIL → Secret: metrofiber-credentials.email
METROFIBER_PASSWORD → Secret: metrofiber-credentials.password

OCTOTEL_USERNAME → Secret: octotel-credentials.username
OCTOTEL_PASSWORD → Secret: octotel-credentials.password
OCTOTEL_TOTP_SECRET → Secret: octotel-credentials.totp-secret

# ... etc
```

### 3. Test Environment First

**CRITICAL**: Never migrate production first!

1. Deploy to dev environment
2. Test all functionality
3. Deploy to staging
4. Run load tests
5. Only then migrate production

## Migration Steps

### Phase 1: Prepare New Environment

#### Step 1.1: Update Secrets File

```bash
# Copy template
cp 02-secrets.yaml 02-secrets-production.yaml

# Extract values from current config.py
cd ../current-deployment
grep -E "^[A-Z_]+\s*=" config.py > config-values.txt

# Update secrets file with real values
vi 02-secrets-production.yaml
# Replace all REPLACE_WITH_ACTUAL_* placeholders
```

#### Step 1.2: Generate New Credentials

```bash
# Generate JWT signing key
openssl rand -base64 32

# Generate Valkey password
openssl rand -base64 24

# Add to secrets file
```

#### Step 1.3: Validate Configuration

```bash
# Validate all YAML
make validate

# Check secrets are configured
make check-secrets

# Dry run deployment
kubectl apply -k overlays/production/ --dry-run=server
```

### Phase 2: Deploy Parallel Environment

#### Step 2.1: Deploy to New Namespace

```bash
# Create separate namespace for migration testing
oc create namespace rpa-system-v2

# Deploy enhanced version
kubectl apply -k overlays/production/
# Update namespace to rpa-system-v2 in kustomization

# Wait for all components
kubectl wait --for=condition=ready pod --all -n rpa-system-v2 --timeout=10m
```

#### Step 2.2: Initialize Valkey with Current TOTP State

```bash
# Get current TOTP usage from logs/database
# Initialize Valkey with this state

VALKEY_POD=$(oc get pod -l app=valkey -n rpa-system-v2 -o jsonpath='{.items[0].metadata.name}')

oc exec -it $VALKEY_POD -n rpa-system-v2 -- valkey-cli -a <PASSWORD> <<EOF
# Initialize TOTP tracking based on current state
SET totp:octotel:counter 0
SET totp:metrofiber:counter 0
# ... etc
EOF
```

#### Step 2.3: Validate New Deployment

```bash
# Run health checks
make health-check

# Test orchestrator API
ORCH_POD=$(oc get pod -l app=rpa-orchestrator -n rpa-system-v2 -o jsonpath='{.items[0].metadata.name}')
oc exec -it $ORCH_POD -n rpa-system-v2 -- curl http://localhost:8620/health/ready

# Test browser service provisioning
oc scale deployment/rpa-browser --replicas=1 -n rpa-system-v2
oc get pods -l app=rpa-browser -n rpa-system-v2 -w
```

### Phase 3: Data Migration

#### Step 3.1: Migrate Evidence Files

```bash
# Copy evidence from old to new storage
OLD_POD=$(oc get pod -l app=rpa-orchestrator -n rpa-system -o jsonpath='{.items[0].metadata.name}')
NEW_POD=$(oc get pod -l app=rpa-orchestrator -n rpa-system-v2 -o jsonpath='{.items[0].metadata.name}')

# Create temporary archive
oc exec $OLD_POD -n rpa-system -- tar czf /tmp/evidence-backup.tar.gz -C /var/evidence .

# Copy via local machine
oc cp rpa-system/$OLD_POD:/tmp/evidence-backup.tar.gz ./evidence-backup.tar.gz
oc cp ./evidence-backup.tar.gz rpa-system-v2/$NEW_POD:/tmp/evidence-backup.tar.gz

# Extract in new environment
oc exec $NEW_POD -n rpa-system-v2 -- tar xzf /tmp/evidence-backup.tar.gz -C /var/evidence
```

#### Step 3.2: Migrate Database State (if needed)

```bash
# If you track state in database, update connection strings
# The new deployment will use the same database, so no migration needed
# Just verify connectivity

oc exec $NEW_POD -n rpa-system-v2 -- python -c "
from orchestrator.database import test_connection
test_connection()
"
```

### Phase 4: Testing & Validation

#### Step 4.1: Smoke Tests

```bash
# Submit test job through Oracle dashboard
# Point to new orchestrator service temporarily

# Monitor execution
oc logs -f deployment/rpa-orchestrator -n rpa-system-v2
oc logs -f deployment/rpa-worker -n rpa-system-v2

# Verify:
# - Job received ✓
# - Browser service provisioned ✓
# - TOTP generated ✓
# - Job executed ✓
# - Evidence collected ✓
# - Results returned ✓
```

#### Step 4.2: Load Testing

```bash
# Submit multiple concurrent jobs
# Monitor resource usage
oc top pods -n rpa-system-v2

# Verify HPA scaling
watch oc get hpa -n rpa-system-v2

# Check Valkey under load
VALKEY_POD=$(oc get pod -l app=valkey -n rpa-system-v2 -o jsonpath='{.items[0].metadata.name}')
oc exec -it $VALKEY_POD -n rpa-system-v2 -- valkey-cli -a <PASSWORD> INFO stats
```

#### Step 4.3: Failover Testing

```bash
# Test Valkey failover
oc delete pod valkey-0 -n rpa-system-v2
# Wait for Sentinel to promote new master
sleep 30
# Verify new master
oc exec -it valkey-sentinel-<pod> -n rpa-system-v2 -- \
  valkey-cli -p 26379 SENTINEL get-master-addr-by-name valkey-master

# Test orchestrator failover
oc delete pod <orchestrator-pod> -n rpa-system-v2
# Verify new pod takes over
oc get pods -l app=rpa-orchestrator -n rpa-system-v2
```

### Phase 5: Production Cutover

#### Step 5.1: Prepare for Cutover

```bash
# Schedule maintenance window
# Notify users
# Prepare rollback plan

# Final backup of old environment
oc get all -n rpa-system -o yaml > backup/pre-cutover-backup.yaml
```

#### Step 5.2: Cutover Plan

```bash
# Option A: Blue-Green Deployment (Recommended)
# 1. Run both environments in parallel
# 2. Gradually shift traffic to new environment
# 3. Monitor for issues
# 4. Complete switch
# 5. Decommission old environment

# Option B: Direct Cutover (Faster but riskier)
# 1. Stop old orchestrator
# 2. Update routes/services
# 3. Start new orchestrator
# 4. Monitor closely
```

#### Step 5.3: Execute Blue-Green Cutover

```bash
# 1. Scale down old workers (but keep orchestrator for monitoring)
oc scale deployment/rpa-worker --replicas=0 -n rpa-system

# 2. Update ORDS/database to point to new orchestrator
# Update connection strings in Oracle APEX or ORDS configuration

# 3. Monitor new environment for 1 hour
watch oc get pods -n rpa-system-v2

# 4. If successful, rename namespaces
oc label namespace rpa-system old-version=true
oc label namespace rpa-system-v2 old-version=false
# Update DNS/routes if needed

# 5. After 24 hours of stable operation, decommission old
oc delete namespace rpa-system
oc label namespace rpa-system-v2 name=rpa-system
```

### Phase 6: Post-Migration Validation

#### Step 6.1: Comprehensive Testing

```bash
# Run full test suite
# - All FNO providers (MetroFiber, Octotel, OpenServe, Evotel)
# - TOTP authentication for all providers
# - Evidence collection
# - Error handling
# - Concurrent job execution
# - Browser service cold start
# - Valkey failover

# Document results
```

#### Step 6.2: Performance Verification

```bash
# Compare metrics
# Old environment baseline vs new environment

# Key metrics:
# - Job completion time
# - TOTP success rate
# - Resource utilization
# - Error rates
# - Cost per job
```

#### Step 6.3: Enable Full Monitoring

```bash
# Verify all ServiceMonitors working
oc get servicemonitor -n rpa-system

# Import Grafana dashboards
oc apply -f 22-grafana-dashboards.yaml

# Configure alerting
# Update Slack/PagerDuty webhooks in production overlay
```

## Rollback Procedure

If issues are encountered during migration:

### Quick Rollback (During Cutover)

```bash
# 1. Stop new environment
oc scale deployment/rpa-orchestrator --replicas=0 -n rpa-system-v2
oc scale deployment/rpa-worker --replicas=0 -n rpa-system-v2

# 2. Restart old environment
oc scale deployment/rpa-orchestrator --replicas=1 -n rpa-system
oc scale deployment/rpa-worker --replicas=4 -n rpa-system

# 3. Verify old environment operational
oc get pods -n rpa-system
make health-check

# 4. Revert database/ORDS connections

# 5. Resume operations on old platform
```

### Complete Rollback (After Cutover)

```bash
# 1. Restore from backup
oc apply -f backup/pre-cutover-backup.yaml

# 2. Verify restoration
oc get pods -n rpa-system

# 3. Test functionality
# Submit test job

# 4. Resume normal operations

# 5. Investigate issues with new deployment
# Review logs, metrics, and errors
# Fix issues before retry
```

## Troubleshooting Migration Issues

### Issue: Browser Service Won't Start

```bash
# Verify SCC applied
oc get scc rpa-browser-privileged-scc

# Check pod events
oc describe pod <browser-pod> -n rpa-system-v2

# Verify service account has SCC
oc describe scc rpa-browser-privileged-scc | grep rpa-browser-sa
```

### Issue: Valkey Connection Failures

```bash
# Test connectivity from orchestrator
ORCH_POD=$(oc get pod -l app=rpa-orchestrator -n rpa-system-v2 -o jsonpath='{.items[0].metadata.name}')
oc exec $ORCH_POD -n rpa-system-v2 -- nc -zv valkey-service 6379

# Check Valkey logs
oc logs valkey-0 -n rpa-system-v2

# Verify password
oc get secret valkey-credentials -n rpa-system-v2 -o jsonpath='{.data.password}' | base64 -d
```

### Issue: Workers Can't Reach Browser Services

```bash
# Check network policies
oc get networkpolicy -n rpa-system-v2

# Test connectivity
WORKER_POD=$(oc get pod -l app=rpa-worker -n rpa-system-v2 -o jsonpath='{.items[0].metadata.name}')
oc exec $WORKER_POD -n rpa-system-v2 -- nc -zv rpa-browser-service 8080

# Verify DNS
oc exec $WORKER_POD -n rpa-system-v2 -- nslookup rpa-browser-service
```

### Issue: Evidence Not Migrated

```bash
# Verify PVC mounted
oc describe pod <orchestrator-pod> -n rpa-system-v2 | grep evidence-storage

# Check permissions
oc exec <orchestrator-pod> -n rpa-system-v2 -- ls -la /var/evidence

# Re-run migration if needed
# Follow Phase 3, Step 3.1 again
```

## Post-Migration Optimization

### Week 1: Monitor Closely

- Check dashboards daily
- Review error rates
- Verify TOTP success rates
- Monitor resource usage
- Adjust HPA thresholds if needed

### Week 2-4: Optimize

- Fine-tune resource requests/limits
- Adjust warm pool size
- Optimize cold start times
- Review and adjust backup schedules
- Update documentation with lessons learned

### Month 2+: Long-term

- Implement cost optimization
- Scale infrastructure based on usage patterns
- Add additional monitoring/alerting
- Plan for future enhancements

## Validation Checklist

After migration, verify:

- [ ] All pods running and healthy
- [ ] Valkey cluster operational (3 nodes, 3 sentinels)
- [ ] Orchestrator API responding
- [ ] Workers registered and ready
- [ ] Browser services can be provisioned
- [ ] TOTP generation working for all providers
- [ ] Evidence storage accessible and populated
- [ ] Network policies enforced
- [ ] Monitoring metrics flowing to Prometheus
- [ ] Grafana dashboards populated
- [ ] Alerts firing appropriately
- [ ] Backups running successfully
- [ ] All FNO providers tested
- [ ] Performance meets or exceeds old platform
- [ ] No increase in error rates
- [ ] Database connectivity stable
- [ ] Oracle dashboard integration working

## Success Criteria

Migration is successful when:

1. **Functionality**: All RPA jobs execute successfully
2. **Performance**: Job completion time ≤ old platform
3. **Reliability**: TOTP success rate > 98%
4. **Availability**: System uptime > 99.9%
5. **Scalability**: HPA working correctly under load
6. **Security**: All security controls in place
7. **Monitoring**: Full observability operational
8. **Cost**: Resource usage within expected ranges

## Support

If you encounter issues during migration:

1. Check this guide's troubleshooting section
2. Review deployment guide: `00-DEPLOYMENT-GUIDE.md`
3. Check architectural plan in project knowledge
4. Review component logs
5. Consult quick reference: `QUICK-REFERENCE.md`

---

**Migration Version**: v2.0-enhanced  
**Last Updated**: 2025-09-29  
**Estimated Duration**: 2-4 hours (plus testing)
