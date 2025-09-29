# RPA Platform - Enhanced OpenShift Deployment

Complete OpenShift configuration for the enhanced RPA platform with three-layer architecture, centralized TOTP management, and production-grade reliability features.

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Orchestrator  │───▶│    Workers      │───▶│  Browser        │
│                 │    │                 │    │  Services       │
│ • Job Mgmt      │    │ • Business Logic│    │ • Firefox +     │
│ • TOTP Gen      │    │ • Job Execution │    │   Playwright    │
│ • Lifecycle     │    │ • Browser Comms │    │ • Privileged    │
│ • OpenShift     │    │ • Results       │    │   Container     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                      │
         └──────────┬───────────┘
                    ▼
            ┌──────────────┐
            │    Valkey    │
            │   Cluster    │
            │  (HA Mode)   │
            └──────────────┘
```

## 📋 What's Included

### Core Components (22 Files)

1. **01-namespace.yaml** - Namespace definition
2. **02-secrets.yaml** - FNO credentials, DB, JWT, Valkey
3. **03-configmaps.yaml** - System and Valkey configuration
4. **04-persistent-volumes.yaml** - Storage claims
5. **05-services.yaml** - All service definitions
6. **06-valkey-statefulset.yaml** - Valkey HA cluster
7. **07-valkey-sentinel.yaml** - Automatic failover
8. **08-orchestrator-deployment.yaml** - Control plane
9. **09-worker-deployment.yaml** - Business logic layer
10. **10-browser-service-deployment.yaml** - Automation layer
11. **11-rbac.yaml** - Service accounts and permissions
12. **12-security-context-constraints.yaml** - OpenShift SCCs
13. **13-network-policies.yaml** - Network isolation
14. **14-horizontal-pod-autoscalers.yaml** - Auto-scaling
15. **15-pod-disruption-budgets.yaml** - HA guarantees
16. **16-service-monitors.yaml** - Prometheus integration
17. **17-resource-quotas.yaml** - Namespace limits
18. **18-routes.yaml** - External access
19. **19-priority-classes.yaml** - Pod scheduling priority
20. **20-backup-cronjobs.yaml** - Automated backups
21. **21-initialization-jobs.yaml** - Setup jobs
22. **22-grafana-dashboards.yaml** - Monitoring dashboards

### Additional Files

- **00-DEPLOYMENT-GUIDE.md** - Step-by-step deployment instructions
- **kustomization.yaml** - Base Kustomize configuration
- **overlays/dev/** - Development environment
- **overlays/staging/** - Staging environment
- **overlays/production/** - Production environment
- **Makefile** - Deployment automation

## 🚀 Quick Start

### Prerequisites

```bash
# Required tools
- oc CLI (OpenShift)
- kubectl
- kustomize (optional, built into kubectl)

# Access requirements
- OpenShift cluster admin access (for SCCs)
- Container registry access
- Database credentials
- FNO provider credentials
```

### 1. Update Secrets

**CRITICAL**: Edit `02-secrets.yaml` and replace all `REPLACE_WITH_ACTUAL_*` placeholders:

```bash
# Generate JWT signing key
openssl rand -base64 32

# Generate Valkey password
openssl rand -base64 24

# Update all secrets in 02-secrets.yaml
vi 02-secrets.yaml
```

### 2. Deploy Using Kustomize

```bash
# Development
kubectl apply -k overlays/dev/

# Staging
kubectl apply -k overlays/staging/

# Production
kubectl apply -k overlays/production/
```

### 3. Or Deploy Manually

```bash
# Follow the deployment guide
cat 00-DEPLOYMENT-GUIDE.md

# Apply files in order
oc apply -f 01-namespace.yaml
oc apply -f 02-secrets.yaml
# ... etc
```

### 4. Or Use Makefile

```bash
# Deploy to development
make deploy-dev

# Deploy to production
make deploy-prod

# Run health checks
make health-check

# View logs
make logs-orchestrator
```

## 🔧 Configuration

### Environment-Specific Settings

Each environment (dev/staging/prod) has different:

- **Replica counts**
- **Resource limits**
- **Log levels**
- **Backup schedules**
- **Autoscaling thresholds**

Customize in `overlays/{environment}/kustomization.yaml`

### Key Configuration Files

| File | Purpose |
|------|---------|
| `02-secrets.yaml` | All credentials |
| `03-configmaps.yaml` | System settings |
| `08-orchestrator-deployment.yaml` | Orchestrator config |
| `09-worker-deployment.yaml` | Worker config |
| `10-browser-service-deployment.yaml` | Browser config |

## 📊 Monitoring

### Grafana Dashboards

Four pre-configured dashboards:

1. **RPA System Overview** - Job execution, success rates, active services
2. **Valkey Cluster Monitoring** - Cache performance, replication status
3. **Browser Service Performance** - Cold start times, resource usage
4. **Resource Utilization** - CPU, memory, network, storage

### Prometheus Metrics

ServiceMonitors configured for:
- Orchestrator (port 9090)
- Workers (port 9091)
- Browser Services (port 9092)
- Valkey (port 6379)

### Alerts

Pre-configured alerts for:
- Component downtime
- High resource usage
- Browser service failures
- Valkey replication issues
- Circuit breaker trips

## 🔒 Security

### Multi-Layer Security

1. **Network Policies** - Zero-trust network segmentation
2. **RBAC** - Least-privilege service accounts
3. **SCCs** - Security context constraints
4. **Secrets** - Encrypted credential storage
5. **TLS** - Encrypted routes

### Security Contexts

- **Orchestrator & Workers**: Non-root, restricted
- **Browser Services**: Privileged (required for automation)
- **Valkey**: Non-root with volume permissions

## 🎯 Resource Requirements

### Minimum (Development)

- **CPU**: 5 cores
- **Memory**: 10 GB
- **Storage**: 50 GB

### Recommended (Production)

- **CPU**: 20+ cores
- **Memory**: 40+ GB
- **Storage**: 200+ GB

### Per Component

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| Orchestrator | 500m | 2000m | 1Gi | 2Gi |
| Worker | 500m | 1500m | 512Mi | 1Gi |
| Browser Service | 1000m | 2000m | 2Gi | 4Gi |
| Valkey | 500m | 1000m | 512Mi | 1Gi |

## 🔄 Scaling

### Horizontal Pod Autoscaling

Configured for:
- **Orchestrator**: 2-4 replicas based on CPU/memory
- **Workers**: 4-20 replicas based on load
- **Browser Services**: Dynamically managed by orchestrator

### Manual Scaling

```bash
# Scale workers
oc scale deployment rpa-worker --replicas=10 -n rpa-system

# Scale orchestrator
oc scale deployment rpa-orchestrator --replicas=3 -n rpa-system
```

## 🛠️ Maintenance

### Automated Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| Valkey Backup | Daily 2 AM | Full backup of all nodes |
| Evidence Cleanup | Daily 3 AM | Delete old screenshots/logs |
| Log Rotation | Weekly Sunday 4 AM | Compress and archive logs |

### Manual Maintenance

```bash
# Restart orchestrator
oc rollout restart deployment/rpa-orchestrator -n rpa-system

# View backup status
oc get cronjob -n rpa-system

# Force backup
oc create job --from=cronjob/valkey-backup manual-backup-1 -n rpa-system

# Check storage usage
oc exec -it <pod> -n rpa-system -- df -h
```

## 🐛 Troubleshooting

### Common Issues

**Browser Service Won't Start**
```bash
# Check SCC permissions
oc get scc rpa-browser-privileged-scc
oc describe pod <browser-pod> -n rpa-system
```

**Valkey Connection Failed**
```bash
# Test connectivity
oc exec -it <orchestrator-pod> -n rpa-system -- nc -zv valkey-service 6379
oc logs valkey-0 -n rpa-system
```

**Worker Not Picking Up Jobs**
```bash
# Check worker logs
oc logs -f deployment/rpa-worker -n rpa-system
# Check orchestrator connectivity
oc exec -it <worker-pod> -n rpa-system -- curl http://rpa-orchestrator-service:8620/health
```

### Health Checks

```bash
# All pod status
oc get pods -n rpa-system

# Component health
oc exec -it <orchestrator-pod> -n rpa-system -- curl http://localhost:8620/health/ready
oc exec -it <worker-pod> -n rpa-system -- curl http://localhost:8621/health/ready
oc exec -it <browser-pod> -n rpa-system -- curl http://localhost:8080/health/ready

# Valkey cluster status
oc exec -it valkey-0 -n rpa-system -- valkey-cli -a <PASSWORD> INFO replication
```

### Logs

```bash
# Tail orchestrator logs
oc logs -f deployment/rpa-orchestrator -n rpa-system

# Tail worker logs
oc logs -f deployment/rpa-worker -n rpa-system --tail=100

# View events
oc get events -n rpa-system --sort-by='.lastTimestamp'
```

## 🔄 Updates & Rollbacks

### Rolling Updates

```bash
# Update orchestrator image
oc set image deployment/rpa-orchestrator orchestrator=rpa-orchestrator:v2.1 -n rpa-system

# Watch rollout
oc rollout status deployment/rpa-orchestrator -n rpa-system
```

### Rollbacks

```bash
# Rollback orchestrator
oc rollout undo deployment/rpa-orchestrator -n rpa-system

# Rollback to specific revision
oc rollout undo deployment/rpa-orchestrator --to-revision=2 -n rpa-system

# View rollout history
oc rollout history deployment/rpa-orchestrator -n rpa-system
```

## 📚 Documentation

- **00-DEPLOYMENT-GUIDE.md** - Detailed deployment steps
- **Architectural Plan** - In project knowledge
- **OpenShift Docs** - https://docs.openshift.com
- **Valkey Docs** - https://valkey.io

## 🎓 Training & Resources

### Key Concepts

1. **Three-Layer Architecture** - Separation of concerns
2. **Centralized TOTP** - Single source of truth
3. **High Availability** - Valkey clustering with Sentinel
4. **Security Context Constraints** - OpenShift security model
5. **Network Policies** - Zero-trust networking

### Common Commands

```bash
# Check cluster info
oc cluster-info

# View all resources
oc get all -n rpa-system

# Describe any resource
oc describe <resource-type> <resource-name> -n rpa-system

# Execute commands in pods
oc exec -it <pod-name> -n rpa-system -- <command>

# Port forward for local testing
oc port-forward svc/rpa-orchestrator-service 8620:8620 -n rpa-system
```

## 🚨 Support

### Before Seeking Help

1. ✅ Check pod status: `oc get pods -n rpa-system`
2. ✅ Review logs: `oc logs <pod-name> -n rpa-system`
3. ✅ Check events: `oc get events -n rpa-system`
4. ✅ Verify configuration: `oc get configmap,secret -n rpa-system`

### Getting Help

- Review deployment guide: `00-DEPLOYMENT-GUIDE.md`
- Check troubleshooting section above
- Review architectural plan in project knowledge
- Examine component-specific logs

## ✅ Success Criteria

After deployment, verify:

- [ ] All pods running and ready
- [ ] Valkey cluster operational (3 nodes, 3 sentinels)
- [ ] Orchestrator API responding
- [ ] Workers registered and ready
- [ ] Browser service can be provisioned
- [ ] TOTP generation working
- [ ] Evidence storage accessible
- [ ] Network policies enforced
- [ ] Monitoring metrics flowing
- [ ] Backups running successfully

## 📝 License

This configuration is part of the RPA Platform project.

## 🙏 Acknowledgments

Built following cloud-native best practices and OpenShift recommended patterns.

---

**Deployment Version**: v2.0-enhanced  
**Last Updated**: 2025-09-29  
**Status**: Ready for Container Development
