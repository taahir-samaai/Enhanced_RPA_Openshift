# RPA Orchestrator - Developer Cheat Sheet

Quick reference for common commands and tasks.

## 🚀 Quick Start

```bash
# Start local development
docker-compose up -d

# View logs
docker-compose logs -f orchestrator

# Stop everything
docker-compose down
```

## 🔨 Makefile Commands

```bash
make help              # Show all commands
make dev-up           # Start dev environment
make dev-down         # Stop dev environment
make test             # Run tests
make build            # Build container
make deploy           # Deploy to OpenShift
make oc-logs          # View OpenShift logs
```

## 📝 Environment Variables (Key Ones)

```bash
# Minimum required
DATABASE_URL=sqlite:///rpa.db
JWT_SECRET_KEY=<generate-with-openssl>
VALKEY_HOST=localhost
VALKEY_PASSWORD=<your-password>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<secure-password>

# FNO Providers
METROFIBER_EMAIL=bot@example.com
METROFIBER_PASSWORD=<password>
OCTOTEL_USERNAME=bot@example.com
OCTOTEL_PASSWORD=<password>
OCTOTEL_TOTP_SECRET=<base32-secret>
```

## 🔑 API Endpoints Quick Reference

```bash
# Base URL
BASE_URL=http://localhost:8620

# Get token
curl -X POST $BASE_URL/auth/token \
  -d "username=admin&password=admin123"

# Health check
curl $BASE_URL/health

# Create job
curl -X POST $BASE_URL/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider":"metrofiber","action":"validation","parameters":{"ref":"TEST123"}}'

# Get job
curl $BASE_URL/jobs/1 -H "Authorization: Bearer $TOKEN"

# List jobs
curl $BASE_URL/jobs -H "Authorization: Bearer $TOKEN"

# System status
curl $BASE_URL/status

# Browser services
curl $BASE_URL/browser-services -H "Authorization: Bearer $TOKEN"
```

## 🐳 Docker Commands

```bash
# Build
docker build -t rpa-orchestrator:v2.0 .

# Run standalone
docker run -p 8620:8620 \
  -e DATABASE_URL=sqlite:///rpa.db \
  -e JWT_SECRET_KEY=test \
  rpa-orchestrator:v2.0

# View logs
docker logs -f <container-id>

# Execute shell
docker exec -it <container-id> /bin/bash

# Remove all
docker-compose down -v
docker rmi rpa-orchestrator:v2.0
```

## ☸️ OpenShift Commands

```bash
# Status
oc get pods -l app=rpa-orchestrator -n rpa-system

# Logs (live)
POD=$(oc get pod -l app=rpa-orchestrator -n rpa-system -o jsonpath='{.items[0].metadata.name}')
oc logs -f $POD -n rpa-system

# Logs (last 100 lines)
oc logs $POD -n rpa-system --tail=100

# Execute command in pod
oc exec -it $POD -n rpa-system -- curl http://localhost:8620/health

# Shell access
oc exec -it $POD -n rpa-system -- /bin/bash

# Restart
oc rollout restart deployment/rpa-orchestrator -n rpa-system

# Scale
oc scale deployment/rpa-orchestrator --replicas=3 -n rpa-system

# Update image
oc set image deployment/rpa-orchestrator \
  orchestrator=your-registry/rpa-orchestrator:v2.1 \
  -n rpa-system

# Rollback
oc rollout undo deployment/rpa-orchestrator -n rpa-system

# View events
oc get events -n rpa-system --sort-by='.lastTimestamp'

# Describe deployment
oc describe deployment rpa-orchestrator -n rpa-system

# Port forward (for local access)
oc port-forward svc/rpa-orchestrator-service 8620:8620 -n rpa-system
```

## 🔍 Debugging

```bash
# Check Valkey connection
docker-compose exec valkey valkey-cli -a testpass ping

# View Valkey data
docker-compose exec valkey valkey-cli -a testpass
> KEYS *
> GET totp:used:octotel:123456

# Check database (SQLite)
docker-compose exec orchestrator sqlite3 /var/data/rpa_orchestrator.db
> SELECT * FROM job_queue;
> .quit

# Test TOTP generation
python -c "
from services.totp_manager import TOTPManager
from services.config_manager import ConfigManager
config = ConfigManager()
totp = TOTPManager(config)
totp.initialize()
print(totp.get_fresh_totp_code('octotel', 999))
"

# View all environment variables in pod
oc exec $POD -n rpa-system -- env | sort
```

## 📊 Monitoring

```bash
# System status
curl http://localhost:8620/status | jq

# Metrics
curl http://localhost:8620/metrics | jq

# Active browser services
curl http://localhost:8620/browser-services \
  -H "Authorization: Bearer $TOKEN" | jq

# Job statistics
curl http://localhost:8620/jobs | jq 'group_by(.status) | map({status: .[0].status, count: length})'
```

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest --cov=. tests/

# Run specific test
pytest tests/test_services.py::TestConfigManager -v

# Run and show print statements
pytest tests/ -v -s
```

## 🔐 Security

```bash
# Generate JWT secret
openssl rand -base64 32

# Generate Valkey password
openssl rand -base64 24

# Hash password for admin user
python -c "from auth import hash_password; print(hash_password('your_password'))"

# View secrets (base64 encoded)
oc get secret fno-credentials -n rpa-system -o yaml

# Decode secret
oc get secret fno-credentials -n rpa-system -o jsonpath='{.data.metrofiber-password}' | base64 -d
```

## 🗄️ Database

```bash
# SQLite shell (local)
sqlite3 data/rpa_orchestrator.db

# Common queries
SELECT * FROM job_queue ORDER BY created_at DESC LIMIT 10;
SELECT status, COUNT(*) FROM job_queue GROUP BY status;
SELECT * FROM job_queue WHERE status = 'failed';
UPDATE job_queue SET status = 'pending' WHERE id = 1;

# Backup database
cp data/rpa_orchestrator.db data/rpa_orchestrator.db.backup

# PostgreSQL (if using)
docker-compose exec postgres psql -U rpa_user -d rpa_db
```

## 📦 Build & Deploy Pipeline

```bash
# Complete deployment flow
make test              # Run tests
make build            # Build image
make push             # Push to registry
make deploy           # Deploy to OpenShift
make oc-logs          # Verify deployment

# Or all at once
make deploy-all
```

## 🔧 Configuration

```bash
# Edit local config
nano .env

# Edit OpenShift ConfigMap
oc edit configmap rpa-system-config -n rpa-system

# Edit OpenShift Secret
oc edit secret fno-credentials -n rpa-system

# Reload config (restart pod)
oc rollout restart deployment/rpa-orchestrator -n rpa-system
```

## 🆘 Troubleshooting Quick Fixes

```bash
# Pod won't start - check events
oc describe pod $POD -n rpa-system

# Valkey connection failed - verify
oc exec valkey-0 -n rpa-system -- valkey-cli -a <pass> ping

# Can't provision browser service - check RBAC
oc get sa rpa-orchestrator-sa -n rpa-system
oc describe role rpa-orchestrator-role -n rpa-system

# Database locked - check for stale locks
oc exec $POD -n rpa-system -- python -c "
import db
count = db.recover_stale_locks()
print(f'Recovered {count} stale locks')
"

# Reset admin password
oc exec $POD -n rpa-system -- python -c "
from auth import hash_password, create_default_admin
create_default_admin()
print('Admin user reset')
"
```

## 📝 Useful Python Snippets

```python
# Test ConfigManager
from services.config_manager import ConfigManager
config = ConfigManager()
print(config.get('DATABASE_URL'))
print(config.get_provider_credentials('metrofiber'))

# Test TOTPManager
from services.totp_manager import TOTPManager
totp = TOTPManager(config)
totp.initialize()
code = totp.get_fresh_totp_code('octotel', 999)
metrics = totp.get_totp_metrics('octotel')

# Test BrowserServiceManager
from services.browser_service_manager import BrowserServiceManager
manager = BrowserServiceManager(config)
services = manager.get_active_services()

# Create test job
import db
job = db.create_job(
    provider='metrofiber',
    action='validation',
    parameters={'ref': 'TEST123'}
)
```

## 🔗 Quick Links

- API Docs: http://localhost:8620/docs
- Health: http://localhost:8620/health
- Status: http://localhost:8620/status
- Valkey UI: http://localhost:8081
- Metrics: http://localhost:8620/metrics

## 💡 Pro Tips

1. **Use `make` commands** - They're faster and remember the syntax for you
2. **Check logs first** - 90% of issues are visible in logs
3. **Test locally first** - Docker Compose is faster than OpenShift
4. **Use port-forward** - Access OpenShift services locally for debugging
5. **Keep .env updated** - Copy from .env.example when new vars are added
6. **Monitor Valkey** - Use Valkey Commander UI for visual debugging
7. **Tag images properly** - Use semantic versioning (v2.0.1, v2.1.0)
8. **Always backup** - Before making changes, backup DB and configs

## 🎯 Common Workflows

### Add New FNO Provider
1. Add credentials to `.env` or OpenShift Secret
2. Update `config_manager.py` if needed
3. Create worker automation module
4. Update TOTP list if provider requires TOTP
5. Test with mock job

### Deploy New Version
1. Update code
2. Run tests: `make test`
3. Build: `make build IMAGE_TAG=v2.1.0`
4. Push: `make push IMAGE_TAG=v2.1.0`
5. Deploy: `make deploy IMAGE_TAG=v2.1.0`
6. Monitor: `make oc-logs`
7. Rollback if needed: `make rollback`

### Debug Failed Job
1. Get job details: `curl $BASE_URL/jobs/$JOB_ID`
2. Check logs: `oc logs $POD | grep "job_id: $JOB_ID"`
3. Check database: `SELECT * FROM job_queue WHERE id = $JOB_ID`
4. Check browser service if applicable
5. Retry job or fix issue

---

**Keep this handy!** Bookmark for quick reference during development.
