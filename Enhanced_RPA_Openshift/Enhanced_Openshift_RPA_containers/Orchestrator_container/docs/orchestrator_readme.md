# RPA Orchestrator - Enhanced for OpenShift

Enhanced orchestrator container for the three-layer RPA architecture with browser service management, centralized TOTP generation, and OpenShift-native configuration.

## 🏗️ Architecture

```
Oracle Dashboard → ORDS → Database → Orchestrator
                                          ↓
                                    (provisions)
                                          ↓
                     Browser Services (Firefox + Playwright)
                                          ↓
                                    (assigns to)
                                          ↓
                                      Workers
                                          ↓
                                  (execute business logic)
```

## ✨ Key Features

- **Browser Service Management**: Provisions and manages on-demand browser service pods via Kubernetes API
- **Centralized TOTP**: Generates and tracks TOTP codes using Valkey to prevent conflicts
- **OpenShift-Native Config**: Reads from Secrets and ConfigMaps instead of config.py
- **High Availability**: Integrates with Valkey cluster for distributed TOTP tracking
- **Pod Lifecycle Management**: Automatic cleanup of idle browser services
- **Health Monitoring**: Kubernetes-ready health checks for orchestration

## 📦 Components

### Core Files

- `orchestrator.py` - Main FastAPI application with enhanced features
- `services/browser_service_manager.py` - Kubernetes-based browser service lifecycle
- `services/totp_manager.py` - Centralized TOTP with Valkey tracking
- `services/config_manager.py` - OpenShift Secrets/ConfigMaps integration

### Supporting Files

- `models.py` - Pydantic models for API
- `db.py` - Database operations
- `auth.py` - JWT authentication
- `rate_limiter.py` - API rate limiting
- `health_reporter.py` - Health reporting to Oracle
- `monitor.py` - Monitoring dashboard
- `errors.py` - Error handling

## 🚀 Building the Container

### Prerequisites

- Docker or Podman
- Access to container registry
- OpenShift cluster with admin access

### Build Command

```bash
# Build the image
docker build -t rpa-orchestrator:v2.0-enhanced .

# Tag for registry
docker tag rpa-orchestrator:v2.0-enhanced your-registry/rpa-orchestrator:v2.0-enhanced

# Push to registry
docker push your-registry/rpa-orchestrator:v2.0-enhanced
```

### Multi-arch Build (Optional)

```bash
# Build for multiple architectures
docker buildx build --platform linux/amd64,linux/arm64 \
    -t your-registry/rpa-orchestrator:v2.0-enhanced \
    --push .
```

## ⚙️ Configuration

### Required Secrets

The orchestrator requires these secrets to be configured in OpenShift:

```yaml
# Database
DATABASE_URL: postgresql://user:pass@host:5432/rpa

# JWT Authentication
JWT_SECRET_KEY: <generate with: openssl rand -base64 32>
ADMIN_USERNAME: admin
ADMIN_PASSWORD: <secure password>

# Valkey
VALKEY_HOST: valkey-service
VALKEY_PORT: "6379"
VALKEY_PASSWORD: <valkey password>

# FNO Provider Credentials
METROFIBER_URL: https://portal.metrofiber.co.za
METROFIBER_EMAIL: bot@example.com
METROFIBER_PASSWORD: <password>

OCTOTEL_USERNAME: bot@example.com
OCTOTEL_PASSWORD: <password>
OCTOTEL_TOTP_SECRET: <base32 TOTP secret>

OPENSERVE_EMAIL: bot@example.com
OPENSERVE_PASSWORD: <password>

EVOTEL_EMAIL: bot@example.com
EVOTEL_PASSWORD: <password>
```

### ConfigMap Settings

```yaml
# Orchestrator
ORCHESTRATOR_HOST: "0.0.0.0"
ORCHESTRATOR_PORT: "8620"
ORCHESTRATOR_URL: http://rpa-orchestrator-service:8620
MAX_WORKERS: "10"
POLL_INTERVAL: "5"
WORKER_TIMEOUT: "30"

# Browser Service
BROWSER_SERVICE_IMAGE: rpa-browser:v2.0-enhanced
NAMESPACE: rpa-system
BROWSER_CPU_REQUEST: "500m"
BROWSER_CPU_LIMIT: "2"
BROWSER_MEMORY_REQUEST: "1Gi"
BROWSER_MEMORY_LIMIT: "4Gi"
BROWSER_IDLE_TIMEOUT: "10"

# Logging
LOG_LEVEL: INFO
LOG_PATH: /var/logs/orchestrator.log

# Callback
CALLBACK_ENDPOINT: <ORDS callback URL>
CALLBACK_AUTH_TOKEN: <auth token>
CALLBACK_TIMEOUT: "10"
```

## 🎯 OpenShift Deployment

### Step 1: Update Secrets

```bash
# Edit the secrets file with real values
vi ../Enhanced_RPA_Openshift/02-secrets.yaml

# Apply secrets
oc apply -f ../Enhanced_RPA_Openshift/02-secrets.yaml
```

### Step 2: Deploy Orchestrator

```bash
# Apply orchestrator deployment
oc apply -f ../Enhanced_RPA_Openshift/08-orchestrator-deployment.yaml

# Watch deployment
oc get pods -n rpa-system -w
```

### Step 3: Verify Deployment

```bash
# Check pod status
oc get pods -n rpa-system -l app=rpa-orchestrator

# Check logs
oc logs -f deployment/rpa-orchestrator -n rpa-system

# Test health endpoint
ORCH_POD=$(oc get pod -l app=rpa-orchestrator -n rpa-system -o jsonpath='{.items[0].metadata.name}')
oc exec -it $ORCH_POD -n rpa-system -- curl http://localhost:8620/health
```

## 🔍 Testing Locally

### Using Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  valkey:
    image: valkey/valkey:7.2
    ports:
      - "6379:6379"
    command: valkey-server --requirepass testpassword
  
  orchestrator:
    build: .
    ports:
      - "8620:8620"
    environment:
      DATABASE_URL: sqlite:////var/data/rpa.db
      JWT_SECRET_KEY: test-secret-key-change-in-production
      ADMIN_USERNAME: admin
      ADMIN_PASSWORD: admin123
      VALKEY_HOST: valkey
      VALKEY_PASSWORD: testpassword
      LOG_LEVEL: DEBUG
    volumes:
      - ./data:/var/data
      - ./logs:/var/logs
    depends_on:
      - valkey
```

Run locally:

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f orchestrator

# Test API
curl http://localhost:8620/health

# Stop services
docker-compose down
```

## 📊 API Endpoints

### Health & Status

- `GET /` - Service information
- `GET /health` - Health check
- `GET /health/ready` - Readiness probe
- `GET /health/live` - Liveness probe
- `GET /status` - Detailed system status
- `GET /metrics` - System metrics

### Authentication

- `POST /auth/token` - Get JWT token

### Job Management

- `POST /jobs` - Create new job
- `GET /jobs` - List jobs (with filtering)
- `GET /jobs/{job_id}` - Get job details
- `PATCH /jobs/{job_id}` - Update job status
- `DELETE /jobs/{job_id}` - Cancel job

### Browser Services

- `GET /browser-services` - List active browser services

### Callbacks

- `POST /callbacks/job-complete` - Worker completion callback (internal)

## 🔐 Security Features

1. **Non-root Container**: Runs as user `rpa` (UID 1000)
2. **Secrets Management**: Uses OpenShift Secrets for sensitive data
3. **JWT Authentication**: Secure API access
4. **Rate Limiting**: Prevents API abuse
5. **RBAC**: OpenShift service accounts with minimal permissions

## 📈 Monitoring

### Health Checks

```bash
# Liveness - is the service alive?
curl http://localhost:8620/health/live

# Readiness - can it accept traffic?
curl http://localhost:8620/health/ready

# Full health check
curl http://localhost:8620/health
```

### Metrics

```bash
# Get system metrics
curl http://localhost:8620/metrics

# Get browser service status
curl http://localhost:8620/browser-services
```

### Logs

```bash
# Tail orchestrator logs
oc logs -f deployment/rpa-orchestrator -n rpa-system

# Get last 100 lines
oc logs deployment/rpa-orchestrator -n rpa-system --tail=100

# View specific pod
oc logs rpa-orchestrator-xxxxx -n rpa-system
```

## 🐛 Troubleshooting

### Orchestrator Won't Start

```bash
# Check pod events
oc describe pod <pod-name> -n rpa-system

# Check logs
oc logs <pod-name> -n rpa-system

# Common issues:
# - Secrets not configured
# - Valkey connection failed
# - Database connection failed
```

### Browser Service Provisioning Fails

```bash
# Check RBAC permissions
oc get sa rpa-orchestrator-sa -n rpa-system
oc describe role rpa-orchestrator-role -n rpa-system

# Check browser service image
oc get deployment rpa-browser -n rpa-system

# View browser service logs
oc logs <browser-pod> -n rpa-system
```

### TOTP Generation Issues

```bash
# Test Valkey connection
ORCH_POD=$(oc get pod -l app=rpa-orchestrator -n rpa-system -o jsonpath='{.items[0].metadata.name}')
oc exec -it $ORCH_POD -n rpa-system -- python -c "
import valkey
client = valkey.Valkey(host='valkey-service', port=6379, password='<password>')
print(client.ping())
"

# Check TOTP secrets configured
oc get secret fno-credentials -n rpa-system -o yaml
```

## 🔄 Updates & Rollbacks

### Rolling Update

```bash
# Update image
oc set image deployment/rpa-orchestrator \
    orchestrator=your-registry/rpa-orchestrator:v2.1-enhanced \
    -n rpa-system

# Watch rollout
oc rollout status deployment/rpa-orchestrator -n rpa-system
```

### Rollback

```bash
# Rollback to previous version
oc rollout undo deployment/rpa-orchestrator -n rpa-system

# Rollback to specific revision
oc rollout undo deployment/rpa-orchestrator --to-revision=2 -n rpa-system
```

## 📝 Development

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="sqlite:///rpa.db"
export JWT_SECRET_KEY="dev-secret"
export VALKEY_HOST="localhost"
export VALKEY_PASSWORD="testpass"

# Run orchestrator
python orchestrator.py
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest tests/

# Run with coverage
pytest --cov=. tests/
```

## 📚 Additional Documentation

- **Architecture Plan**: See `../Enhanced_RPA_Openshift/rpa_architectural_plan(2).md`
- **Deployment Guide**: See `../Enhanced_RPA_Openshift/00-DEPLOYMENT-GUIDE.md`
- **Migration Guide**: See `../Enhanced_RPA_Openshift/migration_guide.md`

## 🤝 Contributing

When making changes:

1. Update relevant documentation
2. Test locally with docker-compose
3. Test in dev environment before production
4. Follow semantic versioning for releases

## 📄 License

Internal use only - RPA Platform Project

## ✅ Checklist Before Deployment

- [ ] All secrets configured in `02-secrets.yaml`
- [ ] ConfigMaps updated with correct values
- [ ] Container image built and pushed to registry
- [ ] Valkey cluster deployed and healthy
- [ ] Database accessible
- [ ] RBAC permissions configured
- [ ] Browser service image available
- [ ] Health checks passing
- [ ] Tested in dev environment

---

**Version**: 2.0.0-enhanced  
**Last Updated**: 2025-09-29
