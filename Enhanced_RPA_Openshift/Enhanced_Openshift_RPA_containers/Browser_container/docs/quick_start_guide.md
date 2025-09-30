# Browser Service - Quick Start Guide

Get the browser service running in 5 minutes!

## ⚡ Prerequisites

- Python 3.11+
- Docker (optional, for containerization)
- OpenShift CLI (`oc`) for deployment

## 🚀 Option 1: Local Development (Fastest)

### Step 1: Clone and Setup

```bash
# Navigate to browser service directory
cd browser_service

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install firefox
playwright install-deps firefox
```

### Step 2: Configure Environment

```bash
# Create .env file
cat > .env << EOF
JWT_SECRET=dev-secret-key-change-in-production
BROWSER_TYPE=firefox
HEADLESS=true
DEFAULT_TIMEOUT=30000
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8080
EOF

# Export environment variables
export $(cat .env | xargs)
```

### Step 3: Run Service

```bash
# Start development server
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

**Service is now running!**
- API: http://localhost:8080
- Docs: http://localhost:8080/docs
- Health: http://localhost:8080/health/live

### Step 4: Test It

```bash
# Test health endpoint (no auth required)
curl http://localhost:8080/health/live

# Expected response:
# {"status":"alive","browser_ready":true,"active_sessions":0,...}
```

## 🐳 Option 2: Docker (Production-like)

### Step 1: Build Image

```bash
# Build Docker image
docker build -t browser-service:latest .

# Or use Makefile
make build
```

### Step 2: Run Container

```bash
# Run container
docker run -d \
  --name browser-service \
  -p 8080:8080 \
  -e JWT_SECRET="your-secret-key" \
  -e BROWSER_TYPE="firefox" \
  -e HEADLESS="true" \
  browser-service:latest

# Check logs
docker logs -f browser-service

# Test
curl http://localhost:8080/health/live
```

## ☁️ Option 3: OpenShift Deployment

### Step 1: Create Namespace

```bash
# Create/switch to namespace
oc new-project rpa-system || oc project rpa-system
```

### Step 2: Create Secrets

```bash
# Generate JWT secret
JWT_SECRET=$(openssl rand -base64 32)

# Create secret
oc create secret generic browser-service-jwt \
  --from-literal=JWT_SECRET="$JWT_SECRET" \
  -n rpa-system
```

### Step 3: Build Image in OpenShift

```bash
# Create BuildConfig
oc new-build --name=browser-service \
  --binary \
  --strategy=docker \
  -n rpa-system

# Start build
oc start-build browser-service \
  --from-dir=. \
  --follow \
  -n rpa-system
```

### Step 4: Deploy

```bash
# Apply deployment (already created in Enhanced_RPA_Openshift/)
oc apply -f ../Enhanced_RPA_Openshift/10-browser-service-deployment.yaml

# Check status
oc get pods -l app=browser-service -n rpa-system

# View logs
oc logs -f deployment/browser-service -n rpa-system
```

### Step 5: Test in OpenShift

```bash
# Get service URL
SERVICE_URL=$(oc get route browser-service -n rpa-system -o jsonpath='{.spec.host}')

# Test (no auth needed for health)
curl http://$SERVICE_URL/health/live
```

## 🧪 Testing the API

### Generate Test JWT Token

For testing, you'll need a JWT token. Here's a quick Python script:

```python
# generate_token.py
import jwt
from datetime import datetime, timedelta

JWT_SECRET = "your-secret-key"  # Must match your JWT_SECRET

token = jwt.encode(
    {
        'sub': 'test-worker',
        'service': 'worker',
        'exp': datetime.utcnow() + timedelta(hours=24)
    },
    JWT_SECRET,
    algorithm='HS256'
)

print(f"JWT Token: {token}")
```

Run it:
```bash
python generate_token.py
```

### Test Complete Workflow

```bash
# Set your token
export JWT_TOKEN="your-generated-token"

# 1. Create session
curl -X POST http://localhost:8080/browser/session/create \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_type": "standard",
    "viewport_width": 1920,
    "viewport_height": 1080
  }'

# Response: {"session_id":"...","status":"created",...}

# 2. Navigate
curl -X POST http://localhost:8080/browser/navigate \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "wait_until": "networkidle",
    "timeout": 30000
  }'

# 3. Get text
curl -X GET "http://localhost:8080/browser/text?selector=h1&timeout=30000" \
  -H "Authorization: Bearer $JWT_TOKEN"

# Response: {"text":"Example Domain","selector":"h1"}

# 4. Screenshot
curl -X POST http://localhost:8080/browser/screenshot \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"full_page": false}' \
  --output test_screenshot.png

# 5. Close session
curl -X DELETE http://localhost:8080/browser/session/close \
  -H "Authorization: Bearer $JWT_TOKEN"
```

### Use the Test Script

```bash
# Make executable
chmod +x test_api.sh

# Run tests
JWT_TOKEN=$JWT_TOKEN ./test_api.sh
```

## 📚 Using from Worker Code

### Step 1: Copy Client Library to Worker

```bash
# Copy client to worker container
cp client/browser_client.py /path/to/worker/services/
```

### Step 2: Use in Automation

```python
# In your worker automation module
from services.browser_client import PlaywrightBrowserClient

def execute(job_id, parameters):
    """Execute automation job"""
    
    # Initialize client with params from orchestrator
    browser = PlaywrightBrowserClient(
        base_url=parameters['browser_service_url'],
        auth_token=parameters['browser_service_token']
    )
    
    try:
        # Create session
        browser.create_session()
        
        # Perform automation
        browser.navigate("https://portal.example.com")
        browser.fill("#username", parameters['username'])
        browser.fill("#password", parameters['password'])
        browser.click("#login")
        
        # Submit TOTP (pre-generated by orchestrator)
        browser.submit_totp("#totp", parameters['totp_code'])
        
        # Extract data
        result = browser.get_text("#result")
        
        # Screenshot for evidence
        browser.screenshot(save_path=f"screenshots/{job_id}.png")
        
        return {'status': 'success', 'data': result}
        
    finally:
        browser.close_session()
```

Or use context manager:

```python
def execute(job_id, parameters):
    with PlaywrightBrowserClient(
        base_url=parameters['browser_service_url'],
        auth_token=parameters['browser_service_token']
    ) as browser:
        
        browser.navigate("https://example.com")
        data = browser.get_text("h1")
        
        return {'status': 'success', 'data': data}
    
    # Session automatically closed
```

## 🔍 Verify Everything Works

### Checklist

- [ ] Service starts without errors
- [ ] Health endpoints return 200
- [ ] Can create browser session
- [ ] Can navigate to websites
- [ ] Can interact with elements
- [ ] Can extract data
- [ ] Can take screenshots
- [ ] Session closes cleanly
- [ ] Authentication works
- [ ] Logs are readable

### Common Issues

#### Issue: "JWT_SECRET is required"

**Solution:**
```bash
export JWT_SECRET="your-secret-key"
```

#### Issue: "playwright: command not found"

**Solution:**
```bash
pip install playwright
playwright install firefox
playwright install-deps firefox
```

#### Issue: "Browser not ready"

**Solution:**
Wait 10-15 seconds after startup for browser initialization.

#### Issue: "Authentication failed"

**Solution:**
Ensure JWT_SECRET matches between service and token generation.

#### Issue: Container OOM killed

**Solution:**
Increase memory limits:
```bash
docker run -m 2g ...  # 2GB limit
```

## 📖 Next Steps

1. **Explore API Documentation**
   - Visit: http://localhost:8080/docs
   - Try all endpoints interactively

2. **Review Integration Examples**
   - Check: `examples/worker_integration.py`
   - See real automation patterns

3. **Read Full Documentation**
   - README.md - API reference
   - DEPLOYMENT.md - Production deployment
   - PROJECT_STRUCTURE.md - Architecture details

4. **Set Up in Your Environment**
   - Deploy to OpenShift
   - Configure with orchestrator
   - Update worker automation

5. **Monitor and Optimize**
   - Watch logs
   - Track performance metrics
   - Adjust resource limits

## 🆘 Need Help?

- **Logs:** `docker logs browser-service` or `oc logs -f deployment/browser-service`
- **Shell:** `docker exec -it browser-service bash` or `oc rsh deployment/browser-service`
- **Status:** `curl http://localhost:8080/browser/session/info`
- **Docs:** http://localhost:8080/docs

## 🎉 Success!

You now have:
- ✅ Running browser service
- ✅ Factory pattern implementation
- ✅ JWT authentication
- ✅ Working API endpoints
- ✅ Client library for workers
- ✅ Integration examples

**Ready to integrate with orchestrator and workers!**

---

**Pro Tips:**

1. Use Makefile commands: `make dev`, `make build`, `make test`
2. Check API docs at `/docs` for interactive testing
3. Enable DEBUG logging for troubleshooting: `LOG_LEVEL=DEBUG`
4. Use context managers in worker code for automatic cleanup
5. Monitor resource usage: `oc adm top pods -l app=browser-service`
