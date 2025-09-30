# Browser Service Deployment Guide

Complete guide for deploying the browser service to OpenShift.

## 📋 Prerequisites

- OpenShift cluster access with admin privileges
- `oc` CLI tool installed and configured
- Docker (for local testing)
- Python 3.11+

## 🚀 Quick Start

### 1. Local Development Setup

```bash
# Clone repository and navigate to browser service
cd browser_service

# Install dependencies
make install
make install-pw

# Set environment variables
export JWT_SECRET="your-development-secret"
export BROWSER_TYPE="firefox"
export HEADLESS="true"

# Run locally
make dev
```

Access API documentation: http://localhost:8080/docs

### 2. Build Container Image

#### Option A: Local Docker Build

```bash
# Build image
make build

# Test locally
docker run -d -p 8080:8080 \
  -e JWT_SECRET="test-secret" \
  -e BROWSER_TYPE="firefox" \
  browser-service:latest

# Test endpoints
curl http://localhost:8080/health/live
```

#### Option B: OpenShift Build

```bash
# Create BuildConfig
oc new-build --name=browser-service \
  --binary \
  --strategy=docker \
  -n rpa-system

# Start build from source
oc start-build browser-service \
  --from-dir=. \
  --follow \
  -n rpa-system
```

### 3. Create OpenShift Secrets

```bash
# Generate JWT secret
JWT_SECRET=$(openssl rand -base64 32)

# Create secret
oc create secret generic browser-service-jwt \
  --from-literal=JWT_SECRET="$JWT_SECRET" \
  -n rpa-system

# Verify secret
oc get secret browser-service-jwt -n rpa-system
```

### 4. Deploy to OpenShift

The deployment configuration is already created in:
`../Enhanced_RPA_Openshift/10-browser-service-deployment.yaml`

```bash
# Apply deployment
oc apply -f ../Enhanced_RPA_Openshift/10-browser-service-deployment.yaml

# Verify deployment
oc get pods -l app=browser-service -n rpa-system
oc get svc browser-service -n rpa-system

# Check logs
oc logs -f deployment/browser-service -n rpa-system
```

## 🔧 Configuration

### Environment Variables

Create a ConfigMap for non-sensitive configuration:

```bash
oc create configmap browser-service-config \
  --from-literal=BROWSER_TYPE=firefox \
  --from-literal=HEADLESS=true \
  --from-literal=DEFAULT_TIMEOUT=30000 \
  --from-literal=MAX_SESSIONS=5 \
  --from-literal=LOG_LEVEL=INFO \
  -n rpa-system
```

### Resource Limits

Adjust resources based on your workload:

```yaml
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "2000m"
```

### Security Context

The service runs with minimal privileges:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1001
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
```

## 🔍 Verification

### Health Checks

```bash
# Get service URL
SERVICE_URL=$(oc get route browser-service -n rpa-system -o jsonpath='{.spec.host}')

# Test liveness
curl http://$SERVICE_URL/health/live

# Test readiness
curl http://$SERVICE_URL/health/ready

# Test with authentication (requires JWT)
curl -H "Authorization: Bearer $JWT_TOKEN" \
  http://$SERVICE_URL/health/browser
```

### Create Test Session

```bash
# Get JWT token from orchestrator
TOKEN=$(oc exec -it deployment/orchestrator -n rpa-system -- \
  python -c "from auth import create_access_token; print(create_access_token({'sub': 'test'}))")

# Create browser session
curl -X POST http://$SERVICE_URL/browser/session/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_type": "standard",
    "viewport_width": 1920,
    "viewport_height": 1080
  }'
```

## 📊 Monitoring

### View Logs

```bash
# Real-time logs
oc logs -f deployment/browser-service -n rpa-system

# Logs from specific pod
POD=$(oc get pods -l app=browser-service -o jsonpath='{.items[0].metadata.name}')
oc logs $POD -n rpa-system

# Previous pod logs (if crashed)
oc logs $POD --previous -n rpa-system
```

### Check Pod Status

```bash
# Pod status
oc get pods -l app=browser-service -n rpa-system

# Detailed pod info
oc describe pod -l app=browser-service -n rpa-system

# Pod events
oc get events --field-selector involvedObject.name=$POD -n rpa-system
```

### Resource Usage

```bash
# CPU and memory usage
oc adm top pods -l app=browser-service -n rpa-system

# Detailed metrics
oc describe pod -l app=browser-service -n rpa-system | grep -A 5 "Limits"
```

## 🐛 Troubleshooting

### Pod Not Starting

```bash
# Check pod events
oc describe pod -l app=browser-service -n rpa-system

# Common issues:
# 1. Image pull errors
oc get pods -l app=browser-service -n rpa-system -o jsonpath='{.items[0].status.containerStatuses[0].state}'

# 2. Configuration errors
oc logs -l app=browser-service -n rpa-system

# 3. Resource constraints
oc get events -n rpa-system | grep browser-service
```

### Browser Initialization Fails

```bash
# Check logs for Playwright errors
oc logs -l app=browser-service -n rpa-system | grep -i "playwright\|firefox"

# Verify Firefox installation
oc exec deployment/browser-service -n rpa-system -- firefox --version

# Check Playwright installation
oc exec deployment/browser-service -n rpa-system -- playwright --version
```

### Authentication Errors

```bash
# Verify JWT secret
oc get secret browser-service-jwt -n rpa-system -o jsonpath='{.data.JWT_SECRET}' | base64 -d

# Test token validation
curl -H "Authorization: Bearer invalid-token" \
  http://$SERVICE_URL/health/browser
# Should return 401 or 403
```

### Memory Issues

```bash
# Check memory usage
oc adm top pod -l app=browser-service -n rpa-system

# Increase memory limits
oc set resources deployment/browser-service \
  --limits=memory=4Gi \
  --requests=memory=1Gi \
  -n rpa-system
```

### Session Cleanup Issues

```bash
# Get session info
curl -H "Authorization: Bearer $TOKEN" \
  http://$SERVICE_URL/browser/session/info

# Force close sessions (restart pod)
oc delete pod -l app=browser-service -n rpa-system
```

## 🔄 Updates and Rollbacks

### Update Deployment

```bash
# Update image
oc set image deployment/browser-service \
  browser-service=browser-service:new-tag \
  -n rpa-system

# Watch rollout
oc rollout status deployment/browser-service -n rpa-system
```

### Rollback

```bash
# View rollout history
oc rollout history deployment/browser-service -n rpa-system

# Rollback to previous version
oc rollout undo deployment/browser-service -n rpa-system

# Rollback to specific revision
oc rollout undo deployment/browser-service --to-revision=2 -n rpa-system
```

## 🔒 Security Hardening

### Network Policies

Create network policy to restrict access:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: browser-service-policy
  namespace: rpa-system
spec:
  podSelector:
    matchLabels:
      app: browser-service
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: worker
    - podSelector:
        matchLabels:
          app: orchestrator
    ports:
    - protocol: TCP
      port: 8080
```

Apply:
```bash
oc apply -f network-policy.yaml
```

### Secret Rotation

```bash
# Generate new JWT secret
NEW_SECRET=$(openssl rand -base64 32)

# Update secret
oc create secret generic browser-service-jwt-new \
  --from-literal=JWT_SECRET="$NEW_SECRET" \
  -n rpa-system

# Update deployment to use new secret
oc set env deployment/browser-service \
  --from=secret/browser-service-jwt-new \
  -n rpa-system

# Delete old secret
oc delete secret browser-service-jwt -n rpa-system
```

## 📈 Scaling

### Manual Scaling

```bash
# Scale to 3 replicas
oc scale deployment/browser-service --replicas=3 -n rpa-system

# Verify scaling
oc get pods -l app=browser-service -n rpa-system
```

### Horizontal Pod Autoscaler

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: browser-service-hpa
  namespace: rpa-system
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: browser-service
  minReplicas: 1
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

## 🧪 Testing in Production

### Smoke Test

```bash
# Run test script
JWT_TOKEN=$PRODUCTION_TOKEN \
BASE_URL=https://browser-service-rpa-system.apps.cluster.com \
./test_api.sh
```

### Load Testing

```bash
# Using Apache Bench
ab -n 100 -c 10 \
  -H "Authorization: Bearer $TOKEN" \
  http://$SERVICE_URL/health/browser

# Using hey
hey -n 1000 -c 50 \
  -H "Authorization: Bearer $TOKEN" \
  http://$SERVICE_URL/health/browser
```

## 📞 Support

For issues or questions:
1. Check logs: `make logs`
2. Review pod status: `make status`
3. Open shell in pod: `make shell`
4. Contact RPA platform team

## 🎓 Additional Resources

- [Playwright Documentation](https://playwright.dev/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [OpenShift Documentation](https://docs.openshift.com/)
- Project Architecture: `../Enhanced_RPA_Openshift/rpa_architectural_plan(2).md`
