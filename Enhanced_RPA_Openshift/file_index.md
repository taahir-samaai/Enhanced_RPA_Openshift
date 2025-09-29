# RPA Platform - Complete File Index

## 📦 Package Contents

This package contains 35+ files for deploying the enhanced RPA platform to OpenShift.

---

## 🏗️ Core OpenShift Configurations (22 files)

### Foundation (Files 01-05)

| File | Purpose | Size | Priority |
|------|---------|------|----------|
| **01-namespace.yaml** | Namespace definition | Small | P0 |
| **02-secrets.yaml** | All credentials (FNO, DB, JWT, Valkey) | Medium | P0 |
| **03-configmaps.yaml** | System & Valkey configuration | Medium | P0 |
| **04-persistent-volumes.yaml** | Storage claims (Valkey, Evidence, Logs) | Small | P0 |
| **05-services.yaml** | All service definitions | Medium | P0 |

**Deploy Order**: Must be applied in sequence (01 → 05)

### Data Layer (Files 06-07)

| File | Purpose | Size | Priority |
|------|---------|------|----------|
| **06-valkey-statefulset.yaml** | Valkey HA cluster (3 nodes) | Large | P0 |
| **07-valkey-sentinel.yaml** | Automatic failover | Medium | P0 |

**Note**: Valkey must be running before application layer

### Application Layer (Files 08-10)

| File | Purpose | Size | Priority |
|------|---------|------|----------|
| **08-orchestrator-deployment.yaml** | Control plane (2 replicas) | Large | P0 |
| **09-worker-deployment.yaml** | Business logic layer (4 replicas) | Large | P0 |
| **10-browser-service-deployment.yaml** | Automation layer (dynamic) | Large | P0 |

**Note**: 10-browser-service starts with 0 replicas (managed by orchestrator)

### Security & Access Control (Files 11-13)

| File | Purpose | Size | Priority |
|------|---------|------|----------|
| **11-rbac.yaml** | ServiceAccounts, Roles, RoleBindings | Medium | P0 |
| **12-security-context-constraints.yaml** | OpenShift SCCs | Medium | P0 |
| **13-network-policies.yaml** | Network isolation rules | Large | P1 |

**Critical**: File 12 requires cluster admin permissions

### Reliability & Scaling (Files 14-15)

| File | Purpose | Size | Priority |
|------|---------|------|----------|
| **14-horizontal-pod-autoscalers.yaml** | Auto-scaling rules | Small | P1 |
| **15-pod-disruption-budgets.yaml** | HA guarantees | Small | P1 |

### Observability (Files 16-17)

| File | Purpose | Size | Priority |
|------|---------|------|----------|
| **16-service-monitors.yaml** | Prometheus integration | Medium | P1 |
| **17-resource-quotas.yaml** | Namespace limits | Small | P2 |

### External Access & Priority (Files 18-19)

| File | Purpose | Size | Priority |
|------|---------|------|----------|
| **18-routes.yaml** | External routes | Small | P2 |
| **19-priority-classes.yaml** | Pod scheduling priority | Small | P2 |

### Maintenance (Files 20-21)

| File | Purpose | Size | Priority |
|------|---------|------|----------|
| **20-backup-cronjobs.yaml** | Automated backups & cleanup | Large | P1 |
| **21-initialization-jobs.yaml** | One-time setup jobs | Large | P2 |

### Monitoring Dashboards (File 22)

| File | Purpose | Size | Priority |
|------|---------|------|----------|
| **22-grafana-dashboards.yaml** | Pre-configured dashboards | Large | P2 |

---

## 📚 Documentation (7 files)

| File | Purpose | When to Use |
|------|---------|-------------|
| **README.md** | Package overview, quick start | Start here |
| **00-DEPLOYMENT-GUIDE.md** | Step-by-step deployment | During deployment |
| **QUICK-REFERENCE.md** | Command reference card | Daily operations |
| **MIGRATION-GUIDE.md** | Migration from current setup | One-time migration |
| **DISASTER-RECOVERY.md** | Recovery procedures | Emergency situations |
| **FILE-INDEX.md** | This file | Finding files |

---

## 🎛️ Configuration Management (4 files)

| File | Purpose | When to Use |
|------|---------|-------------|
| **kustomization.yaml** | Base Kustomize config | All deployments |
| **overlays/dev/kustomization.yaml** | Development overrides | Dev environment |
| **overlays/staging/kustomization.yaml** | Staging overrides | Staging environment |
| **overlays/production/kustomization.yaml** | Production overrides | Production environment |

---

## 🔧 Automation & Tools (4 files)

| File | Purpose | When to Use |
|------|---------|-------------|
| **Makefile** | Deployment automation | Daily operations |
| **.gitignore** | Git exclusions | Version control setup |
| **.gitlab-ci.yml** | GitLab CI/CD pipeline | Automated deployments (GitLab) |
| **.github/workflows/deploy.yml** | GitHub Actions workflow | Automated deployments (GitHub) |

---

## 📊 File Categories by Function

### Must Edit Before Deployment
```
02-secrets.yaml         ⚠️  CRITICAL - Replace all placeholders
03-configmaps.yaml      ⚙️  Review and adjust settings
overlays/*/             🎯  Configure per environment
```

### Deploy As-Is (After Secrets)
```
01-namespace.yaml
04-persistent-volumes.yaml
05-services.yaml
06-valkey-statefulset.yaml
07-valkey-sentinel.yaml
08-orchestrator-deployment.yaml
09-worker-deployment.yaml
10-browser-service-deployment.yaml
11-rbac.yaml
13-network-policies.yaml
14-horizontal-pod-autoscalers.yaml
15-pod-disruption-budgets.yaml
```

### Requires Cluster Admin
```
12-security-context-constraints.yaml    👑  Cluster admin only
```

### Optional/Enhancement
```
16-service-monitors.yaml
17-resource-quotas.yaml
18-routes.yaml
19-priority-classes.yaml
20-backup-cronjobs.yaml
21-initialization-jobs.yaml
22-grafana-dashboards.yaml
```

---

## 🎯 Deployment Paths

### Quick Start (Minimum Viable)
1. Edit `02-secrets.yaml`
2. Apply files 01-11 in order
3. Verify with `make health-check`

### Recommended (Production)
1. Edit `02-secrets.yaml`
2. Edit `overlays/production/kustomization.yaml`
3. Run `make deploy-prod`
4. Apply optional files 16-22
5. Configure monitoring

### CI/CD (Automated)
1. Configure GitLab CI or GitHub Actions
2. Set up secrets in CI/CD platform
3. Push to repository
4. Automated deployment triggers

---

## 📏 File Size Reference

| Size Category | Approx Lines | Files |
|---------------|--------------|-------|
| **Small** | < 50 lines | 01, 04, 14, 15, 17, 18, 19 |
| **Medium** | 50-150 lines | 02, 03, 05, 07, 11, 13, 16 |
| **Large** | 150+ lines | 06, 08, 09, 10, 20, 21, 22, Docs, Makefile |

**Total Lines**: ~4,500 lines of YAML configuration

---

## 🔍 Finding What You Need

### "I want to..."

**...deploy for the first time**
→ Start with `README.md`, then `00-DEPLOYMENT-GUIDE.md`

**...update secrets**
→ `02-secrets.yaml`

**...change configuration**
→ `03-configmaps.yaml` or `overlays/*/kustomization.yaml`

**...add more workers**
→ `09-worker-deployment.yaml` or use `make scale-workers REPLICAS=10`

**...check system health**
→ `QUICK-REFERENCE.md` or `make health-check`

**...migrate from old system**
→ `MIGRATION-GUIDE.md`

**...recover from failure**
→ `DISASTER-RECOVERY.md`

**...understand a command**
→ `QUICK-REFERENCE.md`

**...set up monitoring**
→ `16-service-monitors.yaml` and `22-grafana-dashboards.yaml`

**...configure backups**
→ `20-backup-cronjobs.yaml`

**...troubleshoot issues**
→ `00-DEPLOYMENT-GUIDE.md` (Troubleshooting section) or `QUICK-REFERENCE.md`

**...customize for my environment**
→ Create new overlay in `overlays/my-env/kustomization.yaml`

---

## 📋 Checklists

### Pre-Deployment Checklist
- [ ] Read `README.md`
- [ ] Review `00-DEPLOYMENT-GUIDE.md`
- [ ] Edit `02-secrets.yaml` (all placeholders replaced)
- [ ] Review `03-configmaps.yaml` (settings appropriate)
- [ ] Choose deployment method (manual/Kustomize/CI-CD)
- [ ] Test in dev environment first
- [ ] Have rollback plan ready

### Post-Deployment Checklist
- [ ] All pods running (`make health-check`)
- [ ] Valkey cluster operational
- [ ] Orchestrator API responding
- [ ] Workers registered
- [ ] Browser service can provision
- [ ] TOTP working
- [ ] Evidence storage accessible
- [ ] Monitoring configured
- [ ] Backups scheduled
- [ ] Documentation updated

---

## 🗺️ Navigation Map

```
RPA Platform Configuration
├── README.md                        ← Start here
├── 00-DEPLOYMENT-GUIDE.md          ← Deploy guide
│
├── Core Configs (01-22)            ← OpenShift resources
│   ├── Foundation (01-05)
│   ├── Data Layer (06-07)
│   ├── Application (08-10)
│   ├── Security (11-13)
│   ├── Scaling (14-15)
│   ├── Monitoring (16-17)
│   ├── Access (18-19)
│   └── Maintenance (20-22)
│
├── Kustomize Configs
│   ├── kustomization.yaml          ← Base
│   └── overlays/
│       ├── dev/
│       ├── staging/
│       └── production/
│
├── Operations
│   ├── Makefile                    ← Automation
│   ├── QUICK-REFERENCE.md          ← Commands
│   └── DISASTER-RECOVERY.md        ← Emergency
│
├── Migration
│   └── MIGRATION-GUIDE.md          ← One-time
│
└── CI/CD
    ├── .gitlab-ci.yml
    └── .github/workflows/deploy.yml
```

---

## 💡 Tips

### First Time Users
1. Start with README.md
2. Use dev environment
3. Follow deployment guide exactly
4. Don't skip secrets configuration
5. Test thoroughly before production

### Experienced Users
- Use Makefile for quick operations
- Leverage Kustomize overlays
- Set up CI/CD early
- Keep quick reference handy
- Regularly test disaster recovery

### Troubleshooting
1. Check QUICK-REFERENCE.md first
2. Review component logs
3. Verify connectivity
4. Check recent changes
5. Consult disaster recovery guide if severe

---

## 📞 Support Resources

1. **Quick issues**: QUICK-REFERENCE.md
2. **Deployment problems**: 00-DEPLOYMENT-GUIDE.md (Troubleshooting)
3. **Migration questions**: MIGRATION-GUIDE.md
4. **Disasters**: DISASTER-RECOVERY.md
5. **Architecture questions**: Project knowledge (architectural plan)

---

**Version**: v2.0-enhanced  
**Last Updated**: 2025-09-29  
**Total Files**: 35+  
**Total Documentation**: 15,000+ words
