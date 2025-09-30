# Browser Service - RPA Automation

FastAPI-based browser automation service using Playwright with Factory Design Pattern.

## 🏗️ Architecture

### Factory Pattern Implementation

The service uses the **Factory Design Pattern** for:

1. **Browser Factory** - Creates different browser types (Firefox, Chromium)
2. **Session Factory** - Creates different session configurations (Standard, Mobile, Incognito)

```
┌─────────────────────────────────────────┐
│         FastAPI Application             │
│  (app.py)                               │
└──────────────┬──────────────────────────┘
               │
       ┌───────▼────────┐
       │ Browser Manager │
       │ (Singleton)     │
       └───────┬────────┘
               │
       ┌───────▼──────────┐
       │  Factory Layer   │
       ├──────────────────┤
       │ Browser Factory  │◄─── Creates browsers (Firefox, Chromium)
       │ Session Factory  │◄─── Creates sessions (Standard, Mobile, etc.)
       └──────────────────┘
```

### Directory Structure

```
browser_service/
├── app.py                          # FastAPI application
├── config.py                       # Configuration management
├── requirements.txt                # Python dependencies
├── Dockerfile                      # Container definition
├── factories/
│   ├── __init__.py
│   ├── browser_factory.py          # Browser creation factory
│   └── session_factory.py          # Session creation factory
├── managers/
│   ├── __init__.py
│   └── browser_manager.py          # Browser lifecycle management
├── models/
│   ├── __init__.py
│   └── requests.py                 # Pydantic request/response models
├── middleware/
│   ├── __init__.py
│   └── auth.py                     # JWT authentication
└── utils/
    └── __init__.py
```

## 🚀 Quick Start

### Local Development

1. **Install dependencies:**
```bash
pip install -r requirements.txt
playwright install firefox
playwright install-deps firefox
```

2. **Set environment variables:**
```bash
export JWT_SECRET="your-secret-key"
export BROWSER_TYPE="firefox"
export HEADLESS="true"
export LOG_LEVEL="INFO"
```

3. **Run the service:**
```bash
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

### Docker Build

```bash
# Build image
docker build -t browser-service:latest .

# Run container
docker run -d \
  -p 8080:8080 \
  -e JWT_SECRET="your-secret-key" \
  -e BROWSER_TYPE="firefox" \
  browser-service:latest
```

### OpenShift Deployment

```bash
# Build in OpenShift
oc new-build --name=browser-service --binary --strategy=docker
oc start-build browser-service --from-dir=. --follow

# Deploy
oc new-app browser-service:latest \
  -e JWT_SECRET=<secret> \
  -e BROWSER_TYPE=firefox \
  -e HEADLESS=true

# Expose service (internal only)
oc expose svc/browser-service
```

## 📚 API Documentation

### Authentication

All endpoints (except health checks) require JWT authentication:

```bash
Authorization: Bearer <jwt-token>
```

### Health Endpoints (No Auth)

#### Readiness Probe
```bash
GET /health/ready
```
Returns 200 when service is ready to accept requests.

#### Liveness Probe
```bash
GET /health/live
```
Returns 200 if service process is alive.

#### Browser Health Check (Auth Required)
```bash
GET /health/browser
```
Tests actual browser functionality.

### Session Management

#### Create Session
```bash
POST /browser/session/create
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_type": "standard",
  "viewport_width": 1920,
  "viewport_height": 1080
}
```

**Session Types:**
- `standard` - Desktop browser (1920x1080)
- `mobile` - Mobile browser (390x844)
- `incognito` - Private browsing mode

#### Close Session
```bash
DELETE /browser/session/close
Authorization: Bearer <token>
```

#### Get Session Info
```bash
GET /browser/session/info
Authorization: Bearer <token>
```

### Navigation

#### Navigate to URL
```bash
POST /browser/navigate
Authorization: Bearer <token>
Content-Type: application/json

{
  "url": "https://example.com",
  "wait_until": "networkidle",
  "timeout": 30000
}
```

**Wait Conditions:**
- `load` - Wait for load event
- `domcontentloaded` - Wait for DOMContentLoaded
- `networkidle` - Wait for network to be idle

### Interactions

#### Click Element
```bash
POST /browser/click
Authorization: Bearer <token>
Content-Type: application/json

{
  "selector": "#submit-button",
  "timeout": 30000,
  "force": false
}
```

#### Fill Input
```bash
POST /browser/fill
Authorization: Bearer <token>
Content-Type: application/json

{
  "selector": "#username",
  "value": "user@example.com",
  "timeout": 30000
}
```

#### Submit TOTP Code
```bash
POST /browser/submit_totp
Authorization: Bearer <token>
Content-Type: application/json

{
  "selector": "#totp-input",
  "code": "123456",
  "submit": true
}
```

### Data Extraction

#### Get Text
```bash
GET /browser/text?selector=#result&timeout=30000
Authorization: Bearer <token>
```

#### Get Attribute
```bash
GET /browser/attribute?selector=#link&attribute=href&timeout=30000
Authorization: Bearer <token>
```

#### Screenshot
```bash
POST /browser/screenshot
Authorization: Bearer <token>
Content-Type: application/json

{
  "full_page": false
}
```

Returns PNG image bytes.

### Wait Operations

#### Wait for Selector
```bash
POST /browser/wait_for_selector
Authorization: Bearer <token>
Content-Type: application/json

{
  "selector": "#loading-spinner",
  "state": "hidden",
  "timeout": 30000
}
```

**States:**
- `attached` - Element is in DOM
- `detached` - Element is not in DOM
- `visible` - Element is visible
- `hidden` - Element is hidden

### JavaScript Execution

#### Evaluate JavaScript
```bash
POST /browser/evaluate
Authorization: Bearer <token>
Content-Type: application/json

{
  "expression": "document.title"
}
```

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET` | *Required* | JWT secret for authentication |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `BROWSER_TYPE` | `firefox` | Browser type (firefox, chromium) |
| `HEADLESS` | `true` | Run browser in headless mode |
| `DEFAULT_TIMEOUT` | `30000` | Default timeout in milliseconds |
| `MAX_SESSIONS` | `5` | Maximum concurrent sessions |
| `LOG_LEVEL` | `INFO` | Logging level |
| `HOST` | `0.0.0.0` | Service host |
| `PORT` | `8080` | Service port |

### OpenShift Secrets

Create secret for JWT:
```bash
oc create secret generic browser-service-jwt \
  --from-literal=JWT_SECRET=<your-secret>
```

Mount in deployment:
```yaml
env:
  - name: JWT_SECRET
    valueFrom:
      secretKeyRef:
        name: browser-service-jwt
        key: JWT_SECRET
```

## 🔒 Security

### JWT Authentication

The service validates JWT tokens from orchestrator/worker services:

```python
# Token payload structure:
{
  "sub": "worker-id",
  "service": "worker",
  "exp": 1234567890
}
```

### OpenShift Security Context

Run with minimal privileges:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1001
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
```

## 📊 Monitoring

### Metrics Endpoints

- `/health/ready` - Readiness probe
- `/health/live` - Liveness probe
- `/health/browser` - Business logic health
- `/browser/session/info` - Session statistics

### Logging

Structured logging with levels:
- `DEBUG` - Detailed debugging
- `INFO` - General information
- `WARNING` - Warning messages
- `ERROR` - Error messages

## 🧪 Testing

### Manual Testing

```bash
# Get JWT token from orchestrator
TOKEN="your-jwt-token"

# Create session
curl -X POST http://localhost:8080/browser/session/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_type": "standard"}'

# Navigate
curl -X POST http://localhost:8080/browser/navigate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Screenshot
curl -X POST http://localhost:8080/browser/screenshot \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"full_page": true}' \
  --output screenshot.png
```

## 🐛 Troubleshooting

### Browser Fails to Start

Check Firefox installation:
```bash
firefox --version
playwright install firefox
playwright install-deps firefox
```

### Permission Errors

Ensure proper ownership:
```bash
chown -R 1001:1001 /app
chmod -R 755 /app
```

### Memory Issues

Increase memory limits in OpenShift:
```yaml
resources:
  limits:
    memory: "2Gi"
  requests:
    memory: "512Mi"
```

## 📖 Design Patterns

### Factory Pattern Benefits

1. **Extensibility**: Easy to add new browser types
2. **Maintainability**: Centralized browser creation logic
3. **Testability**: Mock factories for unit tests
4. **Flexibility**: Runtime browser selection

### Adding New Browser Type

```python
# 1. Create browser implementation
class EdgeBrowser(BrowserInterface):
    async def launch(self, **kwargs):
        # Implementation
        pass

# 2. Register with factory
BrowserFactory.register_browser('edge', EdgeBrowser)
```

### Adding New Session Type

```python
# 1. Create session config
class TabletSession(SessionConfig):
    def get_context_options(self):
        return {'viewport': {'width': 768, 'height': 1024}}

# 2. Register with factory
SessionFactory.register_session_type('tablet', TabletSession)
```

## 📝 License

Internal RPA Platform - Proprietary
