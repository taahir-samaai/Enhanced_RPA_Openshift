# Worker Build & Test Guide

Quick guide for building and testing the refactored worker locally.

---

## Prerequisites

- Python 3.11+
- Docker (for containerization)
- Browser service running (or mock for testing)

---

## Local Development Setup

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```bash
# Worker Configuration
WORKER_PORT=8621
WORKER_HOST=0.0.0.0
LOG_LEVEL=INFO

# Browser Service
BROWSER_SERVICE_URL=http://localhost:8080

# MFN Credentials
METROFIBER_URL=https://ftth.metrofibre.co.za/
EMAIL=your-email@example.com
PASSWORD=your-password

# OSN Credentials
OPENSERVE_URL=https://openserve.co.za/
OSEMAIL=your-email@example.com
OSPASSWORD=your-password

# Octotel Credentials
OCTOTEL_URL=https://periscope.octotel.co.za
OCTOTEL_USERNAME=your-username
OCTOTEL_PASSWORD=your-password
OCTOTEL_TOTP_SECRET=your-totp-secret

# Evotel Credentials
EVOTEL_URL=https://portal.evotel.co.za
EVOTEL_USERNAME=your-username
EVOTEL_PASSWORD=your-password
```

### 3. Project Structure

Ensure your directory structure looks like this:

```
worker/
├── worker.py
├── browser_client.py
├── provider_factory.py
├── config.py
├── requirements.txt
├── Dockerfile
├── .env
└── providers/
    ├── __init__.py
    └── mfn/
        ├── __init__.py
        ├── validation.py
        └── cancellation.py
```

### 4. Run Worker Locally

```bash
# Start worker
python worker.py

# Or with uvicorn directly
uvicorn worker:app --host 0.0.0.0 --port 8621 --reload
```

---

## Testing

### 1. Health Check

```bash
curl http://localhost:8621/health
```

Expected response:
```json
{
  "status": "healthy",
  "active_jobs": 0,
  "total_jobs": 0,
  "successful_jobs": 0,
  "failed_jobs": 0,
  "uptime_seconds": 120.5,
  "browser_service_available": true
}
```

### 2. Check Worker Status

```bash
curl http://localhost:8621/status
```

Expected response:
```json
{
  "status": "operational",
  "worker_info": {
    "active_jobs": 0,
    "total_jobs": 0,
    "successful_jobs": 0,
    "failed_jobs": 0,
    "uptime_seconds": 125.3,
    "start_time": "2024-01-15T10:30:00Z"
  },
  "browser_service": {
    "available": true,
    "url": "http://localhost:8080"
  },
  "capabilities": {
    "mfn": ["validation", "cancellation"],
    "osn": ["validation", "cancellation"],
    "octotel": ["validation", "cancellation"],
    "evotel": ["validation", "cancellation"]
  }
}
```

### 3. Execute Test Job

Create `test_job.json`:
```json
{
  "job_id": 12345,
  "provider": "mfn",
  "action": "validation",
  "parameters": {
    "circuit_number": "TEST123456",
    "customer_name": "Test Customer"
  }
}
```

Submit job:
```bash
curl -X POST http://localhost:8621/execute \
  -H "Content-Type: application/json" \
  -d @test_job.json
```

---

## Docker Build

### 1. Build Image

```bash
# Build worker image
docker build -t rpa-worker:v2.0-enhanced .

# Tag for registry
docker tag rpa-worker:v2.0-enhanced your-registry/rpa-worker:v2.0-enhanced
```

### 2. Run Container Locally

```bash
docker run -d \
  --name rpa-worker \
  -p 8621:8621 \
  --env-file .env \
  -e BROWSER_SERVICE_URL=http://host.docker.internal:8080 \
  rpa-worker:v2.0-enhanced
```

### 3. Check Container Logs

```bash
docker logs -f rpa-worker
```

### 4. Test Container

```bash
# Health check
curl http://localhost:8621/health

# Status
curl http://localhost:8621/status
```

---

## Mock Browser Service (for testing)

If you don't have the browser service running yet, create a mock:

Create `mock_browser_service.py`:

```python
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/browser/session")
def create_session(request: dict):
    return {"session_id": "mock-session-123"}

@app.delete("/browser/session/{session_id}")
def close_session(session_id: str):
    return {"success": True}

@app.post("/browser/{session_id}/navigate")
def navigate(session_id: str, request: dict):
    return {"success": True, "url": request.get("url")}

@app.post("/browser/{session_id}/click")
def click(session_id: str, request: dict):
    return {"success": True}

@app.post("/browser/{session_id}/type")
def type_text(session_id: str, request: dict):
    return {"success": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

Run mock:
```bash
python mock_browser_service.py
```

---

## Integration Testing

### 1. Create Test Suite

Create `tests/test_worker.py`:

```python
import pytest
from httpx import AsyncClient
from worker import app

@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

@pytest.mark.asyncio
async def test_status():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert "capabilities" in data

@pytest.mark.asyncio
async def test_execute_job():
    async with AsyncClient(app=app, base_url="http://test") as client:
        job_request = {
            "job_id": 1,
            "provider": "mfn",
            "action": "validation",
            "parameters": {"circuit_number": "TEST123"}
        }
        response = await client.post("/execute", json=job_request)
        assert response.status_code == 200
```

### 2. Run Tests

```bash
pytest tests/ -v
```

---

## Deployment to OpenShift

### 1. Push Image to Registry

```bash
# Login to registry
docker login your-registry.com

# Push image
docker push your-registry/rpa-worker:v2.0-enhanced
```

### 2. Update Deployment YAML

In `09-worker-deployment.yaml`, update image:

```yaml
containers:
  - name: worker
    image: your-registry/rpa-worker:v2.0-enhanced
    imagePullPolicy: Always
```

### 3. Apply to OpenShift

```bash
oc apply -f 09-worker-deployment.yaml -n rpa-system
```

### 4. Verify Deployment

```bash
# Check pods
oc get pods -n rpa-system -l app=rpa-worker

# Check logs
oc logs -f deployment/rpa-worker -n rpa-system

# Test health endpoint
oc port-forward deployment/rpa-worker 8621:8621 -n rpa-system
curl http://localhost:8621/health
```

---

## Troubleshooting

### Worker Won't Start

```bash
# Check logs
docker logs rpa-worker

# Common issues:
# 1. Missing environment variables
# 2. Can't connect to browser service
# 3. Port already in use
```

### Can't Connect to Browser Service

```bash
# Check browser service is running
curl http://browser-service-url:8080/health

# Check network connectivity
docker run --rm --network=host appropriate/curl \
  curl http://rpa-browser-service:8080/health
```

### Job Execution Fails

```bash
# Check detailed logs
oc logs deployment/rpa-worker -n rpa-system --tail=100

# Check browser service logs
oc logs deployment/rpa-browser -n rpa-system --tail=100

# Verify credentials in secrets
oc get secret metrofiber-credentials -n rpa-system -o yaml
```

---

## Performance Testing

### Load Test with Apache Bench

```bash
# Create job payload
cat > job.json << EOF
{
  "job_id": 1,
  "provider": "mfn",
  "action": "validation",
  "parameters": {"circuit_number": "TEST123"}
}
EOF

# Run load test
ab -n 100 -c 10 -p job.json -T application/json \
  http://localhost:8621/execute
```

---

## Next Steps

1. ✅ Worker is running locally
2. ✅ Tests are passing
3. 🔄 Build browser service
4. 🔄 Deploy to OpenShift dev environment
5. 🔄 Run integration tests
6. 🔄 Deploy to production

---

## Quick Commands Reference

```bash
# Development
python worker.py                          # Run worker
uvicorn worker:app --reload               # Run with auto-reload
pytest tests/ -v                          # Run tests

# Docker
docker build -t rpa-worker:v2.0 .        # Build image
docker run -p 8621:8621 rpa-worker:v2.0  # Run container
docker logs -f rpa-worker                 # View logs

# OpenShift
oc apply -f 09-worker-deployment.yaml     # Deploy
oc get pods -l app=rpa-worker            # Check pods
oc logs -f deployment/rpa-worker         # View logs
oc port-forward deployment/rpa-worker 8621:8621  # Port forward

# Testing
curl http://localhost:8621/health         # Health check
curl http://localhost:8621/status         # Status check
curl -X POST http://localhost:8621/execute -d @job.json  # Execute job
```
