# Browser Service - Complete Deployment Checklist

## 📦 What We Built

### Browser Service Container
- ✅ **FastAPI application** with complete REST API
- ✅ **Factory Design Pattern** for clean architecture
- ✅ **Firefox + Incognito** as production configuration
- ✅ **JWT Authentication** reusing existing system
- ✅ **Playwright automation** replacing Selenium
- ✅ **Worker client library** for easy integration
- ✅ **OpenShift ready** with health checks and security contexts

---

## 🎯 Pre-Deployment Checklist

### 1. Files Ready
- [ ] All 28 artifacts collected
- [ ] Directory structure created: `browser_service/`
- [ ] All Python files in place
- [ ] Dockerfile ready
- [ ] Documentation available

### 2. Environment Prepared
- [ ] Python 3.11+ installed
- [ ] Docker installed (for building)
- [ ] OpenShift CLI (`oc`) configured
- [ ] Access to OpenShift cluster
- [ ] Registry access for image storage

### 3. Secrets Generated
- [ ] JWT secret generated: `openssl rand -base64 32`
- [ ] Secret matches orchestrator JWT_SECRET
- [ ] OpenShift secret created: `browser-service-jwt`

### 4. Dependencies Verified
- [ ] `pip install -r requirements.txt` works
- [ ] `playwright install firefox` successful
- [ ] `playwright install-deps firefox` successful
- [ ] Firefox installed: `firefox --version`

---

## 🚀 Deployment Steps

### Step 1: Local Testing (Required)

```bash
# Navigate to directory
cd browser_service

# Install dependencies
make install
make install-pw

# Configure environment
export JWT_SECRET="your-test-secret"
export HEADLESS="true"
export LOG_LEVEL="DEBUG"

# Run locally
make dev

# Test in another terminal
curl http://localhost:8080/health/live
```

**Verification:**
- [ ] Service starts without errors
- [ ] Health endpoint returns 200
- [ ] No import errors in logs
- [ ] Firefox initializes successfully

---

### Step 2: Docker Build (Recommended)

```bash
# Build image
make build

# Test container locally
docker run -d \
  --name browser-service-test \
  -p 8080:8080 \
  -e JWT_SECRET="test-secret" \
  -e HEADLESS="true" \
  browser-service:latest

# Verify
docker logs browser-service-test
curl http://localhost:8080/health/live

# Cleanup
docker stop browser-service-test
docker rm browser-service-test
```

**Verification:**
- [ ] Image builds successfully
- [ ] Container starts without errors
- [ ] Health checks pass
- [ ] No permission errors
- [ ] Firefox works in container

---

### Step 3: OpenShift Preparation

```bash
# Switch to namespace
oc project rpa-system

# Create JWT secret
JWT_SECRET=$(openssl rand -base64 32)
oc create secret generic browser-service-jwt \
  --from-literal=JWT_SECRET="$JWT_SECRET" \
  -n rpa-system

# Verify secret
oc get secret browser-service-jwt -n rpa-system -o yaml

# IMPORTANT: Save this JWT_SECRET - you'll need it for orchestrator/worker
echo $JWT_SECRET > jwt_secret.txt
```

**Verification:**
- [ ] Namespace exists and accessible
- [ ] Secret created successfully
- [ ] JWT_SECRET saved for later use
- [ ] Have admin access for SCCs if needed

---

### Step 4: Build Image in OpenShift

```bash
# Create BuildConfig
oc new-build --name=browser-service \
  --binary \
  --strategy=docker \
  -n rpa-system

# Start build from local directory
cd browser_service
oc start-build browser-service \
  --from-dir=. \
  --follow \
  -n rpa-system

# Verify build
oc get builds -n rpa-system
oc logs -f build/browser-service-1
```

**Verification:**
- [ ] Build completes successfully
- [ ] Image pushed to registry
- [ ] No build errors
- [ ] Image tagged correctly

---

### Step 5: Deploy to OpenShift

```bash
# Deploy using existing configuration
oc apply -f ../Enhanced_RPA_Openshift/10-browser-service-deployment.yaml

# Wait for deployment
oc rollout status deployment/browser-service -n rpa-system

# Check pods
oc get pods -l app=browser-service -n rpa-system

# Check logs
oc logs -f deployment/browser-service -n rpa-system
```

**Verification:**
- [ ] Deployment created
- [ ] Pods running (1/1 Ready)
- [ ] No CrashLoopBackOff
- [ ] Logs show "Browser manager initialized"
- [ ] Health checks passing

---

### Step 6: Service Verification

```bash
# Get service info
oc get svc browser-service -n rpa-system

# Test internally (from another pod)
oc run test-pod --image=alpine/curl --rm -it -- sh
# Inside pod:
curl http://browser-service:8080/health/live
exit

# If exposed externally, test route
SERVICE_URL=$(oc get route browser-service -n rpa-system -o jsonpath='{.spec.host}' 2>/dev/null)
if [ ! -z "$SERVICE_URL" ]; then
  curl http://$SERVICE_URL/health/live
fi
```

**Verification:**
- [ ] Service created and accessible
- [ ] Health endpoint responds
- [ ] Returns: `{"status":"alive","browser_ready":true,...}`
- [ ] Network policy allows traffic

---

### Step 7: Full Integration Test

```bash
# Generate test JWT token (use the JWT_SECRET from Step 3)
# Create generate_token.py:
cat > generate_token.py << 'EOF'
import jwt
from datetime import datetime, timedelta

JWT_SECRET = "YOUR_JWT_SECRET_HERE"  # From jwt_secret.txt

token = jwt.encode(
    {
        'sub': 'test-worker',
        'service': 'worker',
        'exp': datetime.utcnow() + timedelta(hours=1)
    },
    JWT_SECRET,
    algorithm='HS256'
)
print(token)
EOF

python generate_token.py > test_token.txt
export JWT_TOKEN=$(cat test_token.txt)

# Run full test suite
cd browser_service
JWT_TOKEN=$JWT_TOKEN BASE_URL=http://browser-service:8080 ./test_api.sh

# Or test individual endpoints
curl -X POST http://browser-service:8080/browser/session/create \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_type":"incognito","viewport_width":1920,"viewport_height":1080}'
```

**Verification:**
- [ ] Authentication works (no 401/403 errors)
- [ ] Can create session
- [ ] Can navigate to websites
- [ ] Can interact with elements
- [ ] Can capture screenshots
- [ ] Session closes cleanly

---

## 🔍 Post-Deployment Verification

### Health Checks
```bash
# Readiness
curl http://browser-service:8080/health/ready

# Liveness
curl http://browser-service:8080/health/live

# Browser health (requires auth)
curl -H "Authorization: Bearer $JWT_TOKEN" \
  http://browser-service:8080/health/browser
```

**Expected Responses:**
- [ ] All return 200 status
- [ ] `browser_ready: true`
- [ ] No errors in response

### Resource Usage
```bash
# Check pod resource usage
oc adm top pods -l app=browser-service -n rpa-system

# Check pod details
oc describe pod -l app=browser-service -n rpa-system | grep -A 10 "Limits\|Requests"
```

**Verification:**
- [ ] Memory usage < 1.5GB
- [ ] CPU usage reasonable
- [ ] No OOMKilled events
- [ ] Resources within limits

### Logs Review
```bash
# Check for errors
oc logs deployment/browser-service -n rpa-system | grep -i error

# Check initialization
oc logs deployment/browser-service -n rpa-system | grep -i "initialized\|ready"

# Follow logs
oc logs -f deployment/browser-service -n rpa-system
```

**Verification:**
- [ ] No ERROR level logs
- [ ] "Playwright initialized" message present
- [ ] "Browser manager initialized" message present
- [ ] No Firefox errors

---

## 🔐 Security Verification

### Security Context
```bash
# Check pod security context
oc get pod -l app=browser-service -n rpa-system -o yaml | grep -A 10 securityContext
```

**Verification:**
- [ ] runAsNonRoot: true
- [ ] runAsUser: 1001
- [ ] No privileged containers
- [ ] Appropriate capabilities

### Network Policies
```bash
# Check network policies
oc get networkpolicies -n rpa-system
oc describe networkpolicy browser-service-policy -n rpa-system
```

**Verification:**
- [ ] Network policy exists
- [ ] Only allows traffic from orchestrator/worker
- [ ] Denies external traffic

### Secrets
```bash
# Verify secrets mounted correctly
oc get pod -l app=browser-service -n rpa-system -o yaml | grep -A 5 "secretKeyRef"
```

**Verification:**
- [ ] JWT_SECRET mounted from secret
- [ ] No secrets in logs
- [ ] Environment variables set correctly

---

## 🧪 Integration Testing

### Test with Worker (Manual)

Create test worker script:

```python
# test_worker_integration.py
from client.browser_client import PlaywrightBrowserClient

def test_integration():
    client = PlaywrightBrowserClient(
        base_url="http://browser-service:8080",
        auth_token="YOUR_JWT_TOKEN"
    )
    
    try:
        # Create session
        session_id = client.create_session()
        print(f"✅ Session created: {session_id}")
        
        # Navigate
        client.navigate("https://example.com")
        print("✅ Navigation successful")
        
        # Extract data
        title = client.get_text("h1")
        print(f"✅ Extracted title: {title}")
        
        # Screenshot
        client.screenshot(save_path="test.png")
        print("✅ Screenshot captured")
        
        print("\n🎉 Integration test passed!")
        
    finally:
        client.close_session()
        print("✅ Session closed")

if __name__ == "__main__":
    test_integration()
```

Run from worker pod:
```bash
oc cp test_worker_integration.py worker-pod:/tmp/
oc exec worker-pod -- python /tmp/test_worker_integration.py
```

**Verification:**
- [ ] All steps complete without errors
- [ ] Session created and closed
- [ ] Data extracted successfully
- [ ] Screenshot saved

---

## 📊 Monitoring Setup

### Prometheus Metrics
```bash
# Check if metrics endpoint exists
curl http://browser-service:8080/metrics
```

### Grafana Dashboard
- [ ] Import browser service dashboard
- [ ] Verify metrics flowing
- [ ] Set up alerts for failures

### Logging
```bash
# Configure log forwarding
oc set env deployment/browser-service LOG_LEVEL=INFO
```

**Verification:**
- [ ] Logs centralized
- [ ] Log level appropriate
- [ ] Structured logging working

---

## 🔄 Next Steps After Deployment

### 1. Orchestrator Integration
- [ ] Copy JWT_SECRET to orchestrator
- [ ] Create BrowserServiceManager in orchestrator
- [ ] Create TOTPManager in orchestrator
- [ ] Update job assignment logic
- [ ] Test TOTP generation and browser service provisioning

### 2. Worker Integration
- [ ] Copy `client/browser_client.py` to worker container
- [ ] Update Octotel automation to use browser client
- [ ] Update MetroFiber automation to use browser client
- [ ] Update OpenServe automation to use browser client
- [ ] Remove Selenium dependencies
- [ ] Remove pyotp from worker

### 3. Testing
- [ ] End-to-end test: Oracle → Orchestrator → Worker → Browser Service
- [ ] Test TOTP flow
- [ ] Test error handling
- [ ] Performance testing

### 4. Documentation
- [ ] Update team documentation
- [ ] Create runbooks
- [ ] Document troubleshooting procedures

---

## 🐛 Common Issues & Solutions

### Issue: Pod won't start
**Check:**
```bash
oc describe pod -l app=browser-service
oc logs -l app=browser-service
```
**Solutions:**
- Verify image exists
- Check secret is mounted
- Review resource limits

### Issue: Browser initialization fails
**Check:**
```bash
oc logs -l app=browser-service | grep -i firefox
```
**Solutions:**
- Verify Playwright installed in image
- Check Firefox dependencies
- Review security context

### Issue: Authentication fails
**Check:**
```bash
# Verify JWT_SECRET matches
oc get secret browser-service-jwt -o yaml
```
**Solutions:**
- Regenerate and update secret
- Verify token generation uses same secret
- Check token expiration

### Issue: High memory usage
**Check:**
```bash
oc adm top pods -l app=browser-service
```
**Solutions:**
- Increase memory limits
- Reduce MAX_SESSIONS
- Check for memory leaks

---

## ✅ Final Verification Checklist

### Service Health
- [ ] Pods running and ready
- [ ] Health checks passing
- [ ] No errors in logs
- [ ] Firefox initializes correctly

### Integration
- [ ] Authentication working
- [ ] Can create sessions
- [ ] Can perform automations
- [ ] Screenshots working
- [ ] TOTP submission working

### Performance
- [ ] Response times acceptable (<5s for most operations)
- [ ] Memory usage stable
- [ ] CPU usage reasonable
- [ ] No resource exhaustion

### Security
- [ ] Running as non-root
- [ ] Secrets properly mounted
- [ ] Network policies applied
- [ ] No privileged access

### Documentation
- [ ] Deployment documented
- [ ] Runbooks created
- [ ] Team trained
- [ ] Support procedures in place

---

## 🎉 Success Criteria

You're ready for production when:

1. ✅ Browser service pod is running and stable
2. ✅ Health checks all pass
3. ✅ Can authenticate with JWT
4. ✅ Can create sessions and run automations
5. ✅ Integration test passes end-to-end
6. ✅ Resource usage within limits
7. ✅ Logs show no errors
8. ✅ Security verified
9. ✅ Team trained
10. ✅ Ready to integrate orchestrator and workers

---

## 📞 Support

If issues arise:
1. Check logs: `oc logs -f deployment/browser-service`
2. Review pod status: `oc describe pod -l app=browser-service`
3. Test health: `curl http://browser-service:8080/health/live`
4. Review this checklist
5. Check relevant documentation artifacts

**Congratulations! Your Browser Service is deployed! 🚀**
