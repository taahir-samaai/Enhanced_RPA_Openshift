# RPA Platform - Quick Reference Card

## 🚀 Deployment Commands

```bash
# Deploy to development
make deploy-dev

# Deploy to staging
make deploy-staging

# Deploy to production (requires confirmation)
make deploy-prod

# Deploy using Kustomize directly
kubectl apply -k overlays/production/
```

## 🔍 Health Checks

```bash
# All pods status
oc get pods -n rpa-system

# Component health endpoints
oc exec -it <orchestrator-pod> -- curl http://localhost:8620/health/ready
oc exec -it <worker-pod> -- curl http://localhost:8621/health/ready
oc exec -it <browser-pod> -- curl http://localhost:8080/health/ready

# Quick health check (Makefile)
make health-check-prod

# Valkey cluster status
oc exec -it valkey-0 -n rpa-system -- valkey-cli -a <PASSWORD> INFO replication
```

## 📊 Monitoring

```bash
# View all services
oc get svc -n rpa-system

# Check HPA status
oc get hpa -n rpa-system

# View metrics
oc top pods -n rpa-system
oc top nodes

# Recent events
oc get events -n rpa-system --sort-by='.lastTimestamp' | tail -20
```

## 📝 Logs

```bash
# Orchestrator logs
make logs-orchestrator-prod
# or
oc logs -f deployment/rpa-orchestrator -n rpa-system --tail=50

# Worker logs
make logs-worker-prod
# or
oc logs -f deployment/rpa-worker -n rpa-system --tail=100

# Browser service logs
oc logs -f <browser-pod> -n rpa-system

# Valkey logs
oc logs -f valkey-0 -n rpa-system

# All pod logs
oc logs -f -l app=rpa-orchestrator -n rpa-system --max-log-requests=10
```

## 🔄 Scaling

```bash
# Manual scaling
oc scale deployment/rpa-worker --replicas=10 -n rpa-system
oc scale deployment/rpa-orchestrator --replicas=3 -n rpa-system

# Using Makefile
make scale-workers REPLICAS=10

# Check current scale
oc get deployment -n rpa-system
```

## 🔧 Restart Components

```bash
# Restart orchestrator
make restart-orchestrator
# or
oc rollout restart deployment/rpa-orchestrator -n rpa-system

# Restart workers
make restart-workers
# or
oc rollout restart deployment/rpa-worker -n rpa-system

# Restart browser services
oc rollout restart deployment/rpa-browser -n rpa-system

# Restart Valkey (StatefulSet)
oc rollout restart statefulset/valkey -n rpa-system
```

## ⏮️ Rollback

```bash
# Rollback orchestrator
make rollback-orchestrator
# or
oc rollout undo deployment/rpa-orchestrator -n rpa-system

# Rollback to specific revision
oc rollout undo deployment/rpa-orchestrator --to-revision=2 -n rpa-system

# View rollout history
oc rollout history deployment/rpa-orchestrator -n rpa-system

# Check rollout status
oc rollout status deployment/rpa-orchestrator -n rpa-system
```

## 🛠️ Maintenance

```bash
# Manual Valkey backup
make backup
# or
oc create job --from=cronjob/valkey-backup manual-backup-$(date +%Y%m%d) -n rpa-system

# Evidence cleanup
make cleanup-evidence
# or
oc create job --from=cronjob/evidence-cleanup manual-cleanup-$(date +%Y%m%d) -n rpa-system

# Check CronJob status
oc get cronjobs -n rpa-system
oc get jobs -n rpa-system

# View backup logs
oc logs job/manual-backup-<timestamp> -n rpa-system
```

## 🔒 Secrets Management

```bash
# View secrets (not values)
oc get secrets -n rpa-system

# Edit secret
oc edit secret metrofiber-credentials -n rpa-system

# Create/update secret from file
oc create secret generic new-secret --from-file=key=value.txt -n rpa-system

# Get secret value (decode base64)
oc get secret valkey-credentials -n rpa-system -o jsonpath='{.data.password}' | base64 -d
```

## 🌐 Network

```bash
# View services
oc get svc -n rpa-system

# View network policies
oc get networkpolicy -n rpa-system

# Port forward for local access
oc port-forward svc/rpa-orchestrator-service 8620:8620 -n rpa-system
# or
make port-forward

# Test connectivity
make test-connectivity
```

## 💾 Storage

```bash
# View PVCs
oc get pvc -n rpa-system

# Check storage usage
oc exec -it <pod> -n rpa-system -- df -h

# List evidence files
oc exec -it <orchestrator-pod> -n rpa-system -- ls -lh /var/evidence

# View PVC details
oc describe pvc evidence-storage -n rpa-system
```

## 🐛 Troubleshooting

```bash
# Describe pod (detailed info)
oc describe pod <pod-name> -n rpa-system

# Debug orchestrator
make debug-orchestrator

# Debug worker
make debug-worker

# Debug Valkey
make debug-valkey

# Shell into pod
oc exec -it <pod-name> -n rpa-system -- /bin/bash

# Check resource usage
oc top pod <pod-name> -n rpa-system

# View pod YAML
oc get pod <pod-name> -n rpa-system -o yaml
```

## 🔐 Security

```bash
# View Security Context Constraints
oc get scc rpa-browser-privileged-scc
oc get scc rpa-standard-scc

# View service accounts
oc get sa -n rpa-system

# Check RBAC
oc get role,rolebinding -n rpa-system

# View who can perform action
oc auth can-i create pods -n rpa-system --as=system:serviceaccount:rpa-system:rpa-orchestrator-sa
```

## 📈 Metrics & Alerts

```bash
# View ServiceMonitors
oc get servicemonitor -n rpa-system

# View PrometheusRules
oc get prometheusrule -n rpa-system

# Check alert status (if Prometheus deployed)
oc get alertmanager -n openshift-monitoring
```

## 🧪 Testing

```bash
# Test browser service provisioning
oc scale deployment/rpa-browser --replicas=1 -n rpa-system
oc get pods -l app=rpa-browser -n rpa-system -w

# Test orchestrator API
ORCH_POD=$(oc get pod -l app=rpa-orchestrator -n rpa-system -o jsonpath='{.items[0].metadata.name}')
oc exec -it $ORCH_POD -n rpa-system -- curl -v http://localhost:8620/health

# Run health check job
oc create job --from=job/system-health-check manual-health-check -n rpa-system
```

## 🗑️ Cleanup

```bash
# Delete specific deployment
oc delete deployment rpa-worker -n rpa-system

# Delete all resources in namespace
oc delete all --all -n rpa-system

# Delete namespace (complete cleanup)
oc delete namespace rpa-system

# Clean dev environment
make clean-dev
```

## 📦 Configuration Updates

```bash
# Update ConfigMap
oc edit configmap rpa-system-config -n rpa-system

# Restart pods to pick up config changes
oc rollout restart deployment/rpa-orchestrator -n rpa-system

# Apply updated manifests
oc apply -f 03-configmaps.yaml

# View current configuration
oc get configmap rpa-system-config -n rpa-system -o yaml
```

## 🔄 Updates

```bash
# Update image tag
oc set image deployment/rpa-orchestrator orchestrator=rpa-orchestrator:v2.1 -n rpa-system

# Watch update progress
oc rollout status deployment/rpa-orchestrator -n rpa-system

# Pause rollout
oc rollout pause deployment/rpa-orchestrator -n rpa-system

# Resume rollout
oc rollout resume deployment/rpa-orchestrator -n rpa-system
```

## 🎯 Common Scenarios

### Deploy New Version
```bash
# 1. Update image tag
oc set image deployment/rpa-orchestrator orchestrator=rpa-orchestrator:v2.1 -n rpa-system

# 2. Watch rollout
oc rollout status deployment/rpa-orchestrator -n rpa-system

# 3. Verify health
make health-check-prod
```

### Scale for High Load
```bash
# 1. Scale workers
oc scale deployment/rpa-worker --replicas=15 -n rpa-system

# 2. Monitor
watch oc get pods -n rpa-system

# 3. Check HPA
oc get hpa -n rpa-system
```

### Investigate Issues
```bash
# 1. Check pod status
oc get pods -n rpa-system

# 2. View logs
oc logs -f <failing-pod> -n rpa-system

# 3. Describe pod
oc describe pod <failing-pod> -n rpa-system

# 4. Check events
oc get events -n rpa-system --sort-by='.lastTimestamp'
```

### Recover from Failure
```bash
# 1. Check what's failing
oc get pods -n rpa-system | grep -v Running

# 2. Restart failing component
oc rollout restart deployment/<component> -n rpa-system

# 3. If persists, rollback
oc rollout undo deployment/<component> -n rpa-system

# 4. Check Valkey cluster
oc exec -it valkey-0 -n rpa-system -- valkey-cli -a <PASSWORD> INFO
```

## 📱 Useful Aliases

Add to your `.bashrc` or `.zshrc`:

```bash
# OpenShift aliases
alias ocp='oc project rpa-system'
alias ocg='oc get pods -n rpa-system'
alias ocl='oc logs -f -n rpa-system'
alias ocd='oc describe -n rpa-system'
alias oce='oc exec -it -n rpa-system'

# RPA-specific
alias rpa-logs-orch='oc logs -f deployment/rpa-orchestrator -n rpa-system'
alias rpa-logs-worker='oc logs -f deployment/rpa-worker -n rpa-system'
alias rpa-status='oc get pods,svc,hpa -n rpa-system'
alias rpa-restart='oc rollout restart deployment/rpa-orchestrator deployment/rpa-worker -n rpa-system'
```

## 📞 Emergency Contacts

### Critical Issues Checklist
1. ✅ Check pod status: `oc get pods -n rpa-system`
2. ✅ Review recent logs: `oc logs -f <pod> -n rpa-system --tail=100`
3. ✅ Check events: `oc get events -n rpa-system --sort-by='.lastTimestamp'`
4. ✅ Verify Valkey cluster: `make debug-valkey`
5. ✅ Test connectivity: `make test-connectivity`
6. ✅ Check resource usage: `oc top pods -n rpa-system`

### Quick Recovery
```bash
# Nuclear option - restart everything
oc rollout restart deployment/rpa-orchestrator -n rpa-system
oc rollout restart deployment/rpa-worker -n rpa-system
oc rollout restart statefulset/valkey -n rpa-system
oc rollout restart deployment/valkey-sentinel -n rpa-system
```

---

**Version**: v2.0-enhanced  
**Last Updated**: 2025-09-29  
**For detailed documentation**: See `00-DEPLOYMENT-GUIDE.md` and `README.md`
