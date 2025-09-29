# RPA Enhanced Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying the enhanced RPA platform with three-layer architecture (Orchestrator → Workers → Browser Services) and centralized TOTP management via Valkey.

## Prerequisites

- OpenShift cluster with admin access
- `oc` CLI tool installed and configured
- Cluster admin privileges (required for Security Context Constraints)
- Container images built and pushed to registry:
  - `rpa-orchestrator:v2.0-enhanced`
  - `rpa-worker:v2.0-enhanced`
  - `rpa-browser:v2.0-enhanced`

## Architecture Summary

```
Oracle Dashboard → ORDS → Database → Orchestrator
                                          ↓
                                    (manages)
                                          ↓
                     Workers ←→ Browser Services
                        ↓              ↓
                    Business      Firefox +
                     Logic       Playwright
```

## Deployment Steps

### Step 1: Prepare Secrets

**CRITICAL**: Before deploying, update all placeholder values in `02-secrets.yaml`:

```bash
# Edit the secrets file
vi 02-secrets.yaml

# Replace all REPLACE_WITH_ACTUAL_* values with real credentials
# Generate JWT signing key:
openssl rand -base64 32

# Generate Valkey password:
openssl rand -base64 24
```

### Step 2: Apply Security Context Constraints (Cluster Admin Required)

```bash
# Login as cluster admin
oc login -u system:admin

# Apply SCCs (MUST be done first)
oc apply -f 12-security-context-constraints.yaml

# Verify SCCs
oc get scc rpa-browser-privileged-scc
oc get scc rpa-standard-scc
```

### Step 3: Create Namespace and Core Resources

```bash
# Create namespace
oc apply -f 01-namespace.yaml

# Switch to namespace
oc project rpa-system

# Apply secrets
oc apply -f 02-secrets.yaml

# Verify secrets created
oc get secrets -n rpa-system

# Apply ConfigMaps
oc apply -f 03-configmaps.yaml

# Verify ConfigMaps
oc get configmaps -n rpa-system
```

### Step 4: Create Persistent Storage

```bash
# Apply PVCs
oc apply -f 04-persistent-volumes.yaml

# Wait for PVCs to be bound
oc get pvc -n rpa-system -w

# Expected output:
# NAME                STATUS   VOLUME    CAPACITY
# valkey-data-0       Bound    pvc-xxx   10Gi
# valkey-data-1       Bound    pvc-xxx   10Gi
# valkey-data-2       Bound    pvc-xxx   10Gi
# evidence-storage    Bound    pvc-xxx   50Gi
# log-storage         Bound    pvc-xxx   20Gi
```

### Step 5: Create Services and RBAC

```bash
# Apply services
oc apply -f 05-services.yaml

# Verify services
oc get svc -n rpa-system

# Apply RBAC
oc apply -f 11-rbac.yaml

# Verify service accounts
oc get sa -n rpa-system
```

### Step 6: Deploy Valkey Cluster (High Availability)

```bash
# Deploy Valkey StatefulSet
oc apply -f 06-valkey-statefulset.yaml

# Wait for all Valkey pods to be ready
oc get pods -l app=valkey -n rpa-system -w

# Expected: 3 pods running (valkey-0, valkey-1, valkey-2)

# Deploy Valkey Sentinel
oc apply -f 07-valkey-sentinel.yaml

# Wait for Sentinel pods
oc get pods -l app=valkey-sentinel -n rpa-system -w

# Expected: 3 sentinel pods running

# Verify Valkey cluster health
oc exec -it valkey-0 -n rpa-system -- valkey-cli -a <VALKEY_PASSWORD> INFO replication

# Verify Sentinel status
oc exec -it valkey-sentinel-<pod> -n rpa-system -- valkey-cli -p 26379 SENTINEL master valkey-master
```

### Step 7: Deploy Orchestrator

```bash
# Deploy orchestrator
oc apply -f 08-orchestrator-deployment.yaml

# Watch rollout
oc rollout status deployment/rpa-orchestrator -n rpa-system

# Verify pods are running
oc get pods -l app=rpa-orchestrator -n rpa-system

# Check logs
oc logs -f deployment/rpa-orchestrator -n rpa-system

# Test orchestrator health
oc exec -it <orchestrator-pod> -n rpa-system -- curl http://localhost:8620/health/ready
```

### Step 8: Deploy Workers

```bash
# Deploy workers
oc apply -f 09-worker-deployment.yaml

# Watch rollout
oc rollout status deployment/rpa-worker -n rpa-system

# Verify pods
oc get pods -l app=rpa-worker -n rpa-system

# Check logs
oc logs -f deployment/rpa-worker -n rpa-system --tail=50
```

### Step 9: Deploy Browser Service Template

```bash
# Deploy browser service (starts at 0 replicas)
oc apply -f 10-browser-service-deployment.yaml

# Verify deployment created (0 pods is expected)
oc get deployment rpa-browser -n rpa-system

# Browser services will be scaled dynamically by orchestrator
```

### Step 10: Apply Network Policies

```bash
# Apply network policies for security isolation
oc apply -f 13-network-policies.yaml

# Verify network policies
oc get networkpolicy -n rpa-system
```

### Step 11: Configure Autoscaling

```bash
# Apply HPAs
oc apply -f 14-horizontal-pod-autoscalers.yaml

# Verify HPAs
oc get hpa -n rpa-system

# Apply PDBs
oc apply -f 15-pod-disruption-budgets.yaml

# Verify PDBs
oc get pdb -n rpa-system
```

### Step 12: Enable Monitoring (Optional)

```bash
# Apply ServiceMonitors (requires Prometheus Operator)
oc apply -f 16-service-monitors.yaml

# Verify ServiceMonitors
oc get servicemonitor -n rpa-system

# Verify PrometheusRules
oc get prometheusrule -n rpa-system
```

## Validation

### Health Checks

```bash
# Check all pods
oc get pods -n rpa-system

# Expected output:
# NAME                                READY   STATUS    RESTARTS
# rpa-orchestrator-xxx                1/1     Running   0
# rpa-orchestrator-yyy                1/1     Running   0
# rpa-worker-xxx                      1/1     Running   0
# rpa-worker-yyy                      1/1     Running   0
# rpa-worker-zzz                      1/1     Running   0
# rpa-worker-aaa                      1/1     Running   0
# valkey-0                            1/1     Running   0
# valkey-1                            1/1     Running   0
# valkey-2                            1/1     Running   0
# valkey-sentinel-xxx                 1/1     Running   0
# valkey-sentinel-yyy                 1/1     Running   0
# valkey-sentinel-zzz                 1/1     Running   0

# Check services
oc get svc -n rpa-system

# Test orchestrator API
ORCH_POD=$(oc get pod -l app=rpa-orchestrator -n rpa-system -o jsonpath='{.items[0].metadata.name}')
oc exec -it $ORCH_POD -n rpa-system -- curl http://localhost:8620/health/ready
```

### Test Browser Service Provisioning

```bash
# Manually scale browser service to test
oc scale deployment rpa-browser --replicas=1 -n rpa-system

# Wait for pod to start
oc get pods -l app=rpa-browser -n rpa-system -w

# Check browser service logs
BROWSER_POD=$(oc get pod -l app=rpa-browser -n rpa-system -o jsonpath='{.items[0].metadata.name}')
oc logs -f $BROWSER_POD -n rpa-system

# Test browser service health
oc exec -it $BROWSER_POD -n rpa-system -- curl http://localhost:8080/health/ready

# Scale back to 0 (orchestrator will manage)
oc scale deployment rpa-browser --replicas=0 -n rpa-system
```

### Validate Valkey Cluster

```bash
# Check replication status
oc exec -it valkey-0 -n rpa-system -- valkey-cli -a <PASSWORD> INFO replication

# Should show:
# role:master
# connected_slaves:2

# Test failover
oc delete pod valkey-0 -n rpa-system

# Wait for Sentinel to promote new master
sleep 10

# Verify new master
oc exec -it valkey-sentinel-<pod> -n rpa-system -- \
  valkey-cli -p 26379 SENTINEL get-master-addr-by-name valkey-master
```

### Test End-to-End Job Execution

```bash
# Submit a test job through Oracle dashboard
# Monitor orchestrator logs
oc logs -f deployment/rpa-orchestrator -n rpa-system

# Expected flow:
# 1. Job received from database
# 2. Browser service provisioned
# 3. TOTP code generated
# 4. Job assigned to worker
# 5. Worker executes via browser service
# 6. Results returned
# 7. Browser service terminated

# Check worker logs
oc logs -f deployment/rpa-worker -n rpa-system

# Verify evidence collection
oc exec -it <orchestrator-pod> -n rpa-system -- ls -la /var/evidence
```

## Troubleshooting

### Browser Service Won't Start

```bash
# Check SCC permissions
oc describe pod <browser-pod> -n rpa-system | grep -A 5 "Security Context"

# Verify privileged container allowed
oc get scc rpa-browser-privileged-scc -o yaml

# Check logs for initialization errors
oc logs <browser-pod> -n rpa-system
```

### Valkey Connection Issues

```bash
# Test Valkey connectivity from orchestrator
ORCH_POD=$(oc get pod -l app=rpa-orchestrator -n rpa-system -o jsonpath='{.items[0].metadata.name}')
oc exec -it $ORCH_POD -n rpa-system -- nc -zv valkey-service 6379

# Check Valkey logs
oc logs valkey-0 -n rpa-system

# Verify Sentinel
oc logs <valkey-sentinel-pod> -n rpa-system
```

### Worker Can't Reach Browser Service

```bash
# Check network policies
oc get networkpolicy -n rpa-system

# Test connectivity
WORKER_POD=$(oc get pod -l app=rpa-worker -n rpa-system -o jsonpath='{.items[0].metadata.name}')
oc exec -it $WORKER_POD -n rpa-system -- nc -zv rpa-browser-service 8080
```

### Configuration Issues

```bash
# Verify secrets mounted
oc describe pod <orchestrator-pod> -n rpa-system | grep -A 10 "Mounts"

# Check environment variables
oc exec -it <orchestrator-pod> -n rpa-system -- env | grep -E "(METROFIBER|OCTOTEL|VALKEY)"
```

## Rollback Procedure

```bash
# Rollback orchestrator
oc rollout undo deployment/rpa-orchestrator -n rpa-system

# Rollback workers
oc rollout undo deployment/rpa-worker -n rpa-system

# Rollback browser services
oc rollout undo deployment/rpa-browser -n rpa-system

# Check rollout history
oc rollout history deployment/rpa-orchestrator -n rpa-system
```

## Cleanup (Complete Removal)

```bash
# Delete all resources
oc delete namespace rpa-system

# Remove SCCs (cluster admin)
oc delete scc rpa-browser-privileged-scc
oc delete scc rpa-standard-scc
```

## Next Steps

After successful deployment:

1. **Container Development**: Build the actual container images with application code
2. **Database Integration**: Configure ORDS and database triggers
3. **Evidence Management**: Set up S3-compatible storage for evidence
4. **Monitoring Dashboard**: Configure Grafana dashboards for metrics
5. **Load Testing**: Validate performance under expected load
6. **Security Audit**: Conduct security review of privileged containers
7. **Documentation**: Update operational runbooks

## Support

For issues or questions:
- Check logs: `oc logs -f <pod-name> -n rpa-system`
- Describe resources: `oc describe pod <pod-name> -n rpa-system`
- Check events: `oc get events -n rpa-system --sort-by='.lastTimestamp'`
- Review architectural plan in project knowledge

## Success Criteria

✅ All pods running and healthy  
✅ Valkey cluster operational with HA  
✅ Orchestrator managing browser services  
✅ Workers executing jobs successfully  
✅ TOTP generation working  
✅ Evidence collection functional  
✅ Network policies enforced  
✅ Monitoring alerts configured  

**Deployment Status**: READY FOR CONTAINER DEVELOPMENT
