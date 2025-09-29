# Disaster Recovery Plan - RPA Platform

## Overview

This document outlines procedures for recovering from various disaster scenarios affecting the RPA platform.

**Recovery Time Objective (RTO)**: 2 hours  
**Recovery Point Objective (RPO)**: 24 hours

## Disaster Scenarios

### Scenario 1: Complete Namespace Deletion

**Impact**: Total loss of all resources  
**Recovery Time**: 45-60 minutes

#### Detection
```bash
# Namespace missing
oc get namespace rpa-system
# Error: namespace "rpa-system" not found
```

#### Recovery Steps

1. **Verify Backup Availability**
```bash
# Check if backups exist
ls -la backup/
# Should have: manifests, valkey-data, evidence
```

2. **Restore from Configuration**
```bash
# Recreate namespace and all resources
oc apply -k overlays/production/

# Wait for pods
kubectl wait --for=condition=ready pod --all -n rpa-system --timeout=10m
```

3. **Restore Valkey Data**
```bash
# If Valkey backup exists
kubectl cp backup/valkey-latest.rdb rpa-system/valkey-0:/data/dump.rdb

# Restart Valkey
oc rollout restart statefulset/valkey -n rpa-system
```

4. **Restore Evidence Files**
```bash
# Extract evidence backup
ORCH_POD=$(oc get pod -l app=rpa-orchestrator -n rpa-system -o jsonpath='{.items[0].metadata.name}')
oc cp backup/evidence-backup.tar.gz rpa-system/$ORCH_POD:/tmp/
oc exec $ORCH_POD -n rpa-system -- tar xzf /tmp/evidence-backup.tar.gz -C /var/evidence
```

5. **Verify Recovery**
```bash
make health-check-prod
```

---

### Scenario 2: Valkey Cluster Complete Failure

**Impact**: TOTP generation unavailable, jobs blocked  
**Recovery Time**: 15-20 minutes

#### Detection
```bash
# All Valkey pods down
oc get pods -l app=valkey -n rpa-system
# All showing Error or CrashLoopBackOff
```

#### Recovery Steps

1. **Delete StatefulSet** (preserves PVCs)
```bash
oc delete statefulset valkey -n rpa-system --cascade=orphan
```

2. **Check PVC Integrity**
```bash
oc get pvc -l app=valkey -n rpa-system
# All should be Bound
```

3. **Recreate StatefulSet**
```bash
oc apply -f 06-valkey-statefulset.yaml
```

4. **Restart Sentinel**
```bash
oc rollout restart deployment/valkey-sentinel -n rpa-system
```

5. **Verify Cluster**
```bash
oc exec -it valkey-0 -n rpa-system -- valkey-cli -a <PASSWORD> INFO replication
oc exec -it valkey-sentinel-<pod> -n rpa-system -- valkey-cli -p 26379 SENTINEL master valkey-master
```

6. **If Data Corrupted, Restore from Backup**
```bash
for i in 0 1 2; do
  oc cp backup/valkey-${i}.rdb rpa-system/valkey-${i}:/data/dump.rdb
done

oc rollout restart statefulset/valkey -n rpa-system
```

---

### Scenario 3: Orchestrator Complete Failure

**Impact**: No job assignment, system coordination lost  
**Recovery Time**: 10-15 minutes

#### Detection
```bash
# All orchestrator pods failing
oc get pods -l app=rpa-orchestrator -n rpa-system
# Both pods in Error/CrashLoopBackOff
```

#### Recovery Steps

1. **Check Recent Changes**
```bash
oc rollout history deployment/rpa-orchestrator -n rpa-system
```

2. **Rollback if Recent Deployment**
```bash
oc rollout undo deployment/rpa-orchestrator -n rpa-system
oc rollout status deployment/rpa-orchestrator -n rpa-system
```

3. **If Rollback Doesn't Work, Redeploy**
```bash
oc delete deployment rpa-orchestrator -n rpa-system
oc apply -f 08-orchestrator-deployment.yaml
```

4. **Check Dependencies**
```bash
# Verify Valkey accessible
ORCH_POD=$(oc get pod -l app=rpa-orchestrator -n rpa-system -o jsonpath='{.items[0].metadata.name}')
oc exec $ORCH_POD -n rpa-system -- nc -zv valkey-service 6379

# Verify database accessible
oc exec $ORCH_POD -n rpa-system -- python -c "from orchestrator.database import test_connection; test_connection()"
```

5. **Verify Recovery**
```bash
oc exec $ORCH_POD -n rpa-system -- curl http://localhost:8620/health/ready
```

---

### Scenario 4: Persistent Storage Failure

**Impact**: Evidence data loss, Valkey data loss  
**Recovery Time**: 30-45 minutes

#### Detection
```bash
# PVC in Lost or Pending state
oc get pvc -n rpa-system
# evidence-storage shows Lost
```

#### Recovery Steps

1. **Immediate Actions**
```bash
# Stop writes to corrupted PVC
oc scale deployment/rpa-orchestrator --replicas=0 -n rpa-system
oc scale deployment/rpa-worker --replicas=0 -n rpa-system
```

2. **Create New PVC**
```bash
oc delete pvc evidence-storage -n rpa-system
oc apply -f 04-persistent-volumes.yaml
```

3. **Restore from Backup**
```bash
# Wait for new PVC to be bound
oc get pvc evidence-storage -n rpa-system -w

# Create temporary pod for restore
cat <<EOF | oc apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: restore-pod
  namespace: rpa-system
spec:
  containers:
  - name: restore
    image: busybox
    command: ["sleep", "3600"]
    volumeMounts:
    - name: evidence
      mountPath: /var/evidence
  volumes:
  - name: evidence
    persistentVolumeClaim:
      claimName: evidence-storage
EOF

# Copy backup
oc cp backup/evidence-backup.tar.gz rpa-system/restore-pod:/tmp/
oc exec restore-pod -n rpa-system -- tar xzf /tmp/evidence-backup.tar.gz -C /var/evidence

# Clean up
oc delete pod restore-pod -n rpa-system
```

4. **Restart Services**
```bash
oc scale deployment/rpa-orchestrator --replicas=2 -n rpa-system
oc scale deployment/rpa-worker --replicas=4 -n rpa-system
```

---

### Scenario 5: Network Policy Misconfiguration

**Impact**: Components can't communicate  
**Recovery Time**: 5-10 minutes

#### Detection
```bash
# Connection timeouts in logs
oc logs -l app=rpa-worker -n rpa-system | grep "connection refused"
```

#### Recovery Steps

1. **Delete All Network Policies**
```bash
oc delete networkpolicy --all -n rpa-system
```

2. **Test Connectivity**
```bash
make test-connectivity
```

3. **Reapply Policies One by One**
```bash
oc apply -f 13-network-policies.yaml

# Test after each policy
make test-connectivity
```

---

### Scenario 6: Certificate Expiration

**Impact**: TLS routes fail, service communication broken  
**Recovery Time**: 15-20 minutes

#### Detection
```bash
# TLS errors in logs
oc logs -l app=rpa-orchestrator -n rpa-system | grep "certificate"
```

#### Recovery Steps

1. **Check Certificate Expiration**
```bash
oc get secret jwt-signing-key -n rpa-system -o jsonpath='{.data.signing-key}' | base64 -d | openssl x509 -text -noout
```

2. **Generate New Certificate**
```bash
openssl rand -base64 32 > new-jwt-key.txt
```

3. **Update Secret**
```bash
oc create secret generic jwt-signing-key \
  --from-file=signing-key=new-jwt-key.txt \
  --dry-run=client -o yaml | oc apply -f -
```

4. **Restart Affected Components**
```bash
oc rollout restart deployment/rpa-orchestrator -n rpa-system
oc rollout restart deployment/rpa-worker -n rpa-system
oc rollout restart deployment/rpa-browser -n rpa-system
```

---

### Scenario 7: Database Connection Loss

**Impact**: Can't read/write job data  
**Recovery Time**: Depends on database recovery

#### Detection
```bash
# Database errors in logs
oc logs -l app=rpa-orchestrator -n rpa-system | grep "database"
```

#### Recovery Steps

1. **Verify Database Status**
```bash
# Connect to database (outside OpenShift)
sqlplus username/password@database
```

2. **If Database Down, Wait for Recovery**
```bash
# Continue monitoring
ORCH_POD=$(oc get pod -l app=rpa-orchestrator -n rpa-system -o jsonpath='{.items[0].metadata.name}')
watch oc exec $ORCH_POD -n rpa-system -- nc -zv database-host 1521
```

3. **If Credentials Invalid, Update**
```bash
oc edit secret database-credentials -n rpa-system
# Update password (base64 encoded)

# Restart orchestrator
oc rollout restart deployment/rpa-orchestrator -n rpa-system
```

---

### Scenario 8: Complete Cluster Failure

**Impact**: Total system unavailable  
**Recovery Time**: 2-4 hours

#### Recovery Steps

1. **New Cluster Prerequisites**
```bash
# Ensure you have:
# - Backups of all manifests
# - Valkey data backups
# - Evidence file backups
# - Secret values documented
```

2. **Deploy to New Cluster**
```bash
# Configure kubectl for new cluster
export KUBECONFIG=/path/to/new-cluster-config

# Apply SCCs (cluster admin)
oc apply -f 12-security-context-constraints.yaml

# Deploy everything
kubectl apply -k overlays/production/
```

3. **Restore Data**
```bash
# Follow steps from Scenario 1 for data restoration
```

4. **Update DNS/Routes**
```bash
# Point traffic to new cluster
# Update Route53/CloudDNS records
```

5. **Comprehensive Testing**
```bash
# Full smoke test
# Load testing
# Failover testing
```

---

## Backup Strategy

### Automated Backups

```bash
# Daily Valkey backup (automated via CronJob)
# Retention: 30 days

# Weekly full backup (manual)
./scripts/full-backup.sh

# Monthly archive (manual)
./scripts/archive-backup.sh
```

### Manual Backup Now

```bash
# Create backup directory
mkdir -p backup/$(date +%Y%m%d)

# Backup all manifests
oc get all -n rpa-system -o yaml > backup/$(date +%Y%m%d)/manifests.yaml
oc get secrets -n rpa-system -o yaml > backup/$(date +%Y%m%d)/secrets.yaml
oc get configmaps -n rpa-system -o yaml > backup/$(date +%Y%m%d)/configmaps.yaml

# Backup Valkey data
for i in 0 1 2; do
  oc exec valkey-${i} -n rpa-system -- valkey-cli -a <PASSWORD> BGSAVE
  sleep 5
  oc cp rpa-system/valkey-${i}:/data/dump.rdb backup/$(date +%Y%m%d)/valkey-${i}.rdb
done

# Backup evidence files
ORCH_POD=$(oc get pod -l app=rpa-orchestrator -n rpa-system -o jsonpath='{.items[0].metadata.name}')
oc exec $ORCH_POD -n rpa-system -- tar czf /tmp/evidence.tar.gz -C /var/evidence .
oc cp rpa-system/$ORCH_POD:/tmp/evidence.tar.gz backup/$(date +%Y%m%d)/evidence.tar.gz

echo "Backup complete: backup/$(date +%Y%m%d)/"
```

### Backup Verification

```bash
# Test restore in dev environment
oc create namespace rpa-system-restore-test
kubectl apply -k overlays/dev/
# ... restore process ...
# ... test functionality ...
oc delete namespace rpa-system-restore-test
```

---

## Emergency Contacts

### Escalation Path

1. **Level 1**: On-call engineer
2. **Level 2**: Platform team lead
3. **Level 3**: Infrastructure team
4. **Level 4**: Vendor support (OpenShift, etc.)

### Contact Information

```
On-Call Engineer: [Phone/Slack]
Platform Lead: [Phone/Email/Slack]
Infrastructure: [Email/Slack]
Database Team: [Email/Slack]
```

### Communication Channels

- **Incident Channel**: #rpa-incidents
- **Status Page**: status.example.com
- **War Room**: Zoom/Teams link

---

## Post-Incident Review

After any disaster recovery:

1. **Document Timeline**
   - When was issue detected?
   - What was the impact?
   - How long did recovery take?
   - What was the root cause?

2. **Update Runbooks**
   - What worked well?
   - What could be improved?
   - New procedures needed?

3. **Preventive Measures**
   - How can we prevent this?
   - What monitoring is needed?
   - Infrastructure changes?

4. **Test Recovery Procedures**
   - Schedule disaster recovery drills
   - Verify backups regularly
   - Update documentation

---

## Disaster Recovery Testing Schedule

- **Monthly**: Test Valkey restoration
- **Quarterly**: Test full namespace recreation
- **Bi-annually**: Test cluster failover
- **Annually**: Full disaster recovery drill

---

**Version**: v2.0-enhanced  
**Last Updated**: 2025-09-29  
**Review Date**: 2026-03-29
