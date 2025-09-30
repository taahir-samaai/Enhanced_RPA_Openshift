# RPA Orchestrator - Quick Start Guide

Get the enhanced orchestrator running in under 10 minutes.

## 🚀 Quick Local Development

### Option 1: Docker Compose (Recommended for Testing)

```bash
# 1. Clone or navigate to orchestrator directory
cd orchestrator/

# 2. Copy environment template
cp .env.example .env

# 3. Edit .env with your credentials (at minimum, update passwords)
nano .env

# 4. Start all services
docker-compose up -d

# 5. Check status
docker-compose ps

# 6. View logs
docker-compose logs -f orchestrator

# 7. Test the API
curl http://localhost:8620/health

# 8. Access Valkey UI (optional)
open http://localhost:8081
```

Your orchestrator is now running at `http://localhost:8620`

### Option 2: Local Python Development

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment
export DATABASE_URL="sqlite:///rpa.db"
export JWT_SECRET_KEY="dev-secret"
export VALKEY_HOST="localhost"
export VALKEY_PASSWORD="testpass"
export ADMIN_USERNAME="admin"
export ADMIN_PASSWORD="admin123"

# 3. Start Valkey (in another terminal)
docker run -d -p 6379:6379 valkey/valkey:7.2 \
  valkey-server --requirepass testpass

# 4. Run orchestrator
python orchestrator.py
```

## 🔧 OpenShift Deployment (5 Minutes)

### Prerequisites
- OpenShift cluster access
- `oc` CLI installed
- Container registry access

### Quick Deploy

```bash
# 1. Login to OpenShift
oc login --server=https://your-openshift-cluster.com

# 2. Navigate to deployment configs
cd ../Enhanced_RPA_Openshift/

# 3. Update secrets (CRITICAL!)
cp 02-secrets.yaml 02-secrets-prod.yaml
nano 02-secrets-prod.yaml
# Replace all REPLACE_WITH_ACTUAL_* values

# 4. Build and push orchestrator image
cd ../orchestrator/
./build-deploy.sh build
./build-deploy.sh push

# 5. Deploy to OpenShift
./build-deploy.sh deploy
```

### Verify Deployment

```bash
# Check pod status
oc get pods -n rpa-system -l app=rpa-orchestrator

# View logs
oc logs -f deployment/rpa-orchestrator -n rpa-system

# Test health endpoint
POD=$(oc get pod -l app=rpa-orchestrator -n rpa-system -o jsonpath='{.items[0].metadata.name}')
oc exec $POD -- curl http://localhost:8620/health
```

## 📝 First API Call

### Get Authentication Token

```bash
curl -X POST http://localhost:8620/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
```

Response:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer"
}
```

### Create a Test Job

```bash
TOKEN="<your-token-here>"

curl -X POST http://localhost:8620/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "metrofiber",
    "action": "validation",
    "parameters": {
      "reference_number": "TEST123",
      "external_job_id": "ORACLE_001"
    }
  }'
```

### Check Job Status

```bash
curl http://localhost:8620/jobs/1 \
  -H "Authorization: Bearer $TOKEN"
```

### List All Jobs

```bash
curl http://localhost:8620/jobs \
  -H "Authorization: Bearer $TOKEN"
```

## 🔍 Monitoring & Debugging

### View System Status

```bash
curl http://localhost:8620/status
```

### Check Browser Services

```bash
curl http://localhost:8620/browser-services \
  -H "Authorization: Bearer $TOKEN"
```

### View Metrics

```bash
curl http://localhost:8620/metrics
```

### Check Logs

**Docker Compose:**
```bash
docker-compose logs -f orchestrator
docker-compose logs -f valkey
```

**OpenShift:**
```bash
oc logs -f deployment/rpa-orchestrator -n rpa-system
oc logs -f statefulset/valkey -n rpa-system
```

## 🛠️ Common Tasks

### Restart Services

**Docker Compose:**
```bash
docker-compose restart orchestrator
```

**OpenShift:**
```bash
oc rollout restart deployment/rpa-orchestrator -n rpa-system
```

### Update Configuration

**Docker Compose:**
```bash
# Edit .env file
nano .env

# Restart to apply
docker-compose restart orchestrator
```

**OpenShift:**
```bash
# Update ConfigMap
oc edit configmap rpa-system-config -n rpa-system

# Update Secret
oc edit secret fno-credentials -n rpa-system

# Restart to apply
oc rollout restart deployment/rpa-orchestrator -n rpa-system
```

### Scale Workers

**OpenShift:**
```bash
# Scale up
oc scale deployment/rpa-worker --replicas=6 -n rpa-system

# Scale down
oc scale deployment/rpa-worker --replicas=2 -n rpa-system
```

### View Database

**Docker Compose (SQLite):**
```bash
docker-compose exec orchestrator sqlite3 /var/data/rpa_orchestrator.db
# Then: SELECT * FROM job_queue;
```

**Docker Compose (PostgreSQL):**
```bash
docker-compose exec postgres psql -U rpa_user -d rpa_db
# Then: SELECT * FROM job_queue;
```

## 🧪 Testing

### Run Unit Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run all tests
pytest tests/

# Run with coverage
pytest --cov=. tests/

# Run specific test file
pytest tests/test_services.py -v
```

### Test TOTP Generation

```bash
# Test TOTP manager
python -c "
from services.totp_manager import TOTPManager
from services.config_manager import ConfigManager

config = ConfigManager()
totp = TOTPManager(config)
totp.initialize()

code = totp.get_fresh_totp_code('octotel', job_id=999)
print(f'TOTP Code: {code}')

metrics = totp.get_totp_metrics('octotel')
print(f'Metrics: {metrics}')
"
```

### Test Browser Service Management

```bash
# This requires OpenShift/Kubernetes access
# Test in a real cluster environment
oc exec -it <orchestrator-pod> -- python -c "
from services.browser_service_manager import BrowserServiceManager
from services.config_manager import ConfigManager

config = ConfigManager()
manager = BrowserServiceManager(config)

# Provision a test browser service
service_info = manager.provision_browser_service(job_id=999)
print(f'Service Info: {service_info}')
"
```

## 🐛 Troubleshooting

### Issue: "Valkey connection failed"

**Solution:**
```bash
# Check Valkey is running
docker-compose ps valkey
# or
oc get pods -l app=valkey -n rpa-system

# Test connection
docker-compose exec valkey valkey-cli -a testpass ping
# or
oc exec valkey-0 -- valkey-cli -a <password> ping
```

### Issue: "Database connection failed"

**Solution:**
```bash
# Check database is accessible
docker-compose ps postgres
# or check DATABASE_URL is correct

# For SQLite, check file permissions
ls -la ./data/
```

### Issue: "Browser service provisioning failed"

**Solution:**
```bash
# Check RBAC permissions
oc get sa rpa-orchestrator-sa -n rpa-system
oc describe role rpa-orchestrator-role -n rpa-system

# Check if browser image is available
oc get deployment rpa-browser -n rpa-system
```

### Issue: "Authentication failed"

**Solution:**
```bash
# Reset admin password
docker-compose exec orchestrator python -c "
from auth import hash_password
print(hash_password('new_password'))
"

# Then update in database or recreate admin user
```

## 📚 Next Steps

1. **Configure Real Credentials**: Update `.env` or OpenShift secrets with real FNO credentials
2. **Deploy Workers**: Set up worker containers (see worker documentation)
3. **Deploy Browser Services**: Configure browser service deployment
4. **Set Up Monitoring**: Configure Prometheus/Grafana (see monitoring docs)
5. **Configure Callbacks**: Set up Oracle ORDS callbacks for job completion
6. **Scale Up**: Adjust replica counts based on workload

## 🔗 Additional Resources

- **Full Documentation**: See `README.md`
- **Architecture Details**: `../Enhanced_RPA_Openshift/rpa_architectural_plan(2).md`
- **Deployment Guide**: `../Enhanced_RPA_Openshift/00-DEPLOYMENT-GUIDE.md`
- **Migration Guide**: `../Enhanced_RPA_Openshift/migration_guide.md`
- **API Documentation**: Access `/docs` endpoint when orchestrator is running

## 💡 Pro Tips

1. **Use Docker Compose for local development** - It's the fastest way to test
2. **Always test in dev environment first** - Never deploy directly to production
3. **Monitor Valkey metrics** - Use the Valkey Commander UI to debug TOTP issues
4. **Check logs frequently** - They contain detailed error information
5. **Use the health endpoints** - They provide quick status checks

## 🆘 Getting Help

If you encounter issues:

1. ✅ Check the logs first
2. ✅ Verify all secrets/configs are set
3. ✅ Test health endpoints
4. ✅ Review the troubleshooting section
5. ✅ Check the full documentation

---

**Happy Orchestrating! 🎉**
