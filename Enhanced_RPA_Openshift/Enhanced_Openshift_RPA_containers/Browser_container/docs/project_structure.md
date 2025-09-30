# Browser Service - Complete Project Structure

## 📁 Directory Layout

```
browser_service/
│
├── 📄 app.py                          # Main FastAPI application entry point
├── 📄 config.py                       # Configuration management
├── 📄 requirements.txt                # Python dependencies
├── 📄 Dockerfile                      # Container build definition
├── 📄 .dockerignore                   # Docker build exclusions
├── 📄 Makefile                        # Build and deployment automation
├── 📄 README.md                       # Service documentation
├── 📄 DEPLOYMENT.md                   # Deployment guide
├── 📄 PROJECT_STRUCTURE.md            # This file
├── 📄 test_api.sh                     # API testing script
│
├── 📁 factories/                      # Factory Pattern Implementations
│   ├── 📄 __init__.py
│   ├── 📄 browser_factory.py         # Browser creation factory
│   └── 📄 session_factory.py         # Session/context creation factory
│
├── 📁 managers/                       # Core Management Classes
│   ├── 📄 __init__.py
│   └── 📄 browser_manager.py         # Browser lifecycle management
│
├── 📁 models/                         # Pydantic Models
│   ├── 📄 __init__.py
│   └── 📄 requests.py                # Request/response models
│
├── 📁 middleware/                     # Middleware Components
│   ├── 📄 __init__.py
│   └── 📄 auth.py                    # JWT authentication
│
├── 📁 utils/                          # Utility Functions
│   ├── 📄 __init__.py
│   └── 📄 helpers.py                 # Common utilities, decorators
│
├── 📁 client/                         # Client Library (for Workers)
│   ├── 📄 __init__.py
│   └── 📄 browser_client.py          # Python client for workers
│
├── 📁 examples/                       # Integration Examples
│   ├── 📄 __init__.py
│   └── 📄 worker_integration.py      # Worker integration examples
│
└── 📁 tests/                          # Unit and Integration Tests
    ├── 📄 __init__.py
    ├── 📄 test_factories.py
    ├── 📄 test_browser_manager.py
    ├── 📄 test_auth.py
    └── 📄 test_api.py
```

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Application                     │
│                         (app.py)                            │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌──────────────┐  ┌────────────┐  ┌──────────────┐
│ Auth         │  │ Browser    │  │ API Routes   │
│ Middleware   │  │ Manager    │  │ & Models     │
└──────────────┘  └─────┬──────┘  └──────────────┘
                        │
            ┌───────────┼───────────┐
            │                       │
            ▼                       ▼
    ┌──────────────┐        ┌──────────────┐
    │ Browser      │        │ Session      │
    │ Factory      │        │ Factory      │
    └──────┬───────┘        └──────┬───────┘
           │                       │
           └───────────┬───────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │  Playwright         │
            │  + Firefox          │
            └─────────────────────┘
```

## 📦 Core Components

### 1. Application Layer (`app.py`)

**Purpose:** FastAPI application with all endpoints

**Key Features:**
- Health check endpoints (ready, live, browser)
- Session management endpoints
- Browser automation endpoints
- JWT authentication integration
- Global exception handling
- CORS middleware

**Dependencies:**
- FastAPI, Uvicorn
- BrowserManager
- AuthService
- Pydantic models

---

### 2. Configuration (`config.py`)

**Purpose:** Centralized configuration management

**Key Settings:**
- Service configuration (host, port, name)
- Browser settings (type, headless mode)
- Security settings (JWT, allowed IPs)
- Resource limits
- Logging configuration

**Environment Variables:**
- `JWT_SECRET` (required)
- `BROWSER_TYPE` (firefox/chromium)
- `HEADLESS` (true/false)
- `DEFAULT_TIMEOUT`
- `LOG_LEVEL`

---

### 3. Factory Layer (`factories/`)

#### Browser Factory (`browser_factory.py`)

**Purpose:** Create different browser types using Factory pattern

**Classes:**
- `BrowserInterface` - Abstract base class
- `FirefoxBrowser` - Firefox implementation
- `ChromiumBrowser` - Chromium implementation
- `BrowserFactory` - Factory for creating browsers

**Extensibility:**
```python
# Add new browser type
BrowserFactory.register_browser('edge', EdgeBrowser)
```

#### Session Factory (`session_factory.py`)

**Purpose:** Create different session configurations

**Classes:**
- `SessionConfig` - Abstract base class
- `StandardSession` - Desktop configuration
- `MobileSession` - Mobile device configuration
- `IncognitoSession` - Private browsing
- `SessionFactory` - Factory for creating sessions

**Extensibility:**
```python
# Add new session type
SessionFactory.register_session_type('tablet', TabletSession)
```

---

### 4. Browser Manager (`managers/browser_manager.py`)

**Purpose:** Core browser lifecycle and operations management

**Design Pattern:** Singleton

**Key Methods:**
- `initialize()` - Initialize browser via factory
- `create_session()` - Create browser session
- `navigate()` - Navigate to URL
- `click()`, `fill()` - Element interactions
- `get_text()`, `get_attribute()` - Data extraction
- `screenshot()` - Capture screenshots
- `wait_for_selector()` - Wait operations
- `close_session()` - Cleanup

**State Management:**
- Tracks current session
- Manages active contexts
- Handles cleanup

---

### 5. Models (`models/requests.py`)

**Purpose:** Pydantic models for validation

**Request Models:**
- `CreateSessionRequest`
- `NavigateRequest`
- `ClickRequest`
- `FillRequest`
- `TOTPRequest`
- `GetTextRequest`
- `GetAttributeRequest`
- `WaitForSelectorRequest`
- `ScreenshotRequest`
- `EvaluateRequest`

**Response Models:**
- `SessionResponse`
- `OperationResponse`
- `TextResponse`
- `AttributeResponse`
- `SessionInfoResponse`
- `HealthResponse`
- `ErrorResponse`

**Enums:**
- `WaitUntilEnum`
- `SessionTypeEnum`
- `ElementStateEnum`

---

### 6. Middleware (`middleware/auth.py`)

**Purpose:** JWT authentication for service-to-service communication

**Components:**
- `AuthService` - Token validation
- `verify_service_token()` - FastAPI dependency
- `require_service()` - Service-specific decorator
- `IPWhitelistMiddleware` - IP-based access control

**Usage:**
```python
@app.get("/protected")
async def protected_route(token: dict = Depends(verify_service_token)):
    # Token validated, proceed
    pass
```

---

### 7. Utilities (`utils/helpers.py`)

**Purpose:** Common patterns and utilities

**Components:**
- `CircuitBreaker` - Prevent cascading failures
- `@retry_on_exception` - Retry with exponential backoff
- `@timeout_handler` - Function timeout
- `RateLimiter` - API rate limiting
- `@measure_execution_time` - Performance tracking
- `@log_function_call` - Function call logging
- `PerformanceMonitor` - Metrics tracking
- Helper functions (sanitize_filename, format_bytes, etc.)

**Usage:**
```python
@retry_on_exception(max_attempts=3, delay=2)
@track_performance('navigation_time')
def navigate_to_page():
    # Operation with retry and tracking
    pass
```

---

### 8. Client Library (`client/browser_client.py`)

**Purpose:** Python client for workers to use

**Key Features:**
- Mirrors browser service API
- Built-in retry logic
- Context manager support
- Comprehensive error handling
- Type hints and documentation

**Usage in Workers:**
```python
from client.browser_client import PlaywrightBrowserClient

client = PlaywrightBrowserClient(
    base_url=job_params['browser_service_url'],
    auth_token=job_params['browser_service_token']
)

with client:
    client.navigate("https://example.com")
    text = client.get_text("h1")
```

---

### 9. Examples (`examples/worker_integration.py`)

**Purpose:** Real-world integration examples

**Includes:**
- Octotel validation example
- MetroFiber cancellation example
- Context manager usage
- Error handling patterns
- Worker execute function template

---

## 🔄 Request Flow

### 1. Worker → Browser Service Flow

```
Worker
  │
  ├─ Initialize Client
  │  └─ PlaywrightBrowserClient(url, token)
  │
  ├─ Create Session
  │  └─ POST /browser/session/create
  │     └─ BrowserManager.create_session()
  │        └─ SessionFactory.create_session()
  │
  ├─ Execute Operations
  │  ├─ POST /browser/navigate
  │  │  └─ BrowserManager.navigate()
  │  │
  │  ├─ POST /browser/fill
  │  │  └─ BrowserManager.fill()
  │  │
  │  └─ GET /browser/text
  │     └─ BrowserManager.get_text()
  │
  └─ Cleanup
     └─ DELETE /browser/session/close
        └─ BrowserManager.close_session()
```

### 2. Authentication Flow

```
Request
  │
  ├─ Extract Authorization header
  │
  ├─ verify_service_token(authorization)
  │  └─ AuthService.extract_token_from_header()
  │     └─ AuthService.verify_token()
  │        └─ jwt.decode(token, JWT_SECRET)
  │
  ├─ Token Valid?
  │  ├─ Yes → Proceed to endpoint
  │  └─ No → HTTPException 401/403
  │
  └─ Execute endpoint logic
```

## 🔧 Extension Points

### Adding New Browser Type

1. Create browser class in `factories/browser_factory.py`:
```python
class EdgeBrowser(BrowserInterface):
    async def launch(self, **kwargs) -> Browser:
        # Implementation
        pass
```

2. Register with factory:
```python
BrowserFactory.register_browser('edge', EdgeBrowser)
```

3. Update config to support new type

### Adding New Session Type

1. Create session config in `factories/session_factory.py`:
```python
class TabletSession(SessionConfig):
    def get_context_options(self) -> Dict:
        # Return tablet configuration
        pass
```

2. Register with factory:
```python
SessionFactory.register_session_type('tablet', TabletSession)
```

### Adding New Endpoint

1. Define request/response models in `models/requests.py`
2. Add endpoint in `app.py`:
```python
@app.post("/browser/new_operation", response_model=OperationResponse)
async def new_operation(
    request: NewOperationRequest,
    token: dict = Depends(verify_service_token)
):
    # Implementation
    pass
```

3. Add method to `BrowserManager` if needed
4. Update client library with new method

## 📊 Performance Considerations

### Resource Usage

**Memory:**
- Base: ~200MB (Python + FastAPI)
- Per Browser: ~300-500MB
- Per Session: ~50-100MB

**CPU:**
- Idle: <5%
- Active automation: 20-80% per session

**Recommended Limits:**
```yaml
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "2000m"
```

### Scaling Considerations

- One browser instance per container (Singleton pattern)
- Multiple sessions supported (up to MAX_SESSIONS)
- Scale horizontally by adding more pods
- Use HPA for automatic scaling

## 🧪 Testing

### Unit Tests
```bash
pytest tests/test_factories.py
pytest tests/test_browser_manager.py
pytest tests/test_auth.py
```

### Integration Tests
```bash
# Start service locally
make dev

# Run API tests
JWT_TOKEN=test-token make test
```

### Manual Testing
```bash
# Use test script
JWT_TOKEN=your-token ./test_api.sh

# Or use curl
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/health/browser
```

## 🚀 Deployment

### Local Development
```bash
make install
make install-pw
make dev
```

### Docker Build
```bash
make build
docker run -p 8080:8080 \
  -e JWT_SECRET=secret \
  browser-service:latest
```

### OpenShift Deployment
```bash
make build-openshift
make deploy
make logs
```

## 📝 Best Practices

1. **Always use context manager** for browser client
2. **Handle errors gracefully** with try/finally
3. **Use appropriate timeouts** for operations
4. **Take screenshots** on errors for debugging
5. **Log important operations** for audit trail
6. **Clean up sessions** after use
7. **Use retry logic** for flaky operations
8. **Monitor resource usage** in production

## 🔗 Related Documentation

- [README.md](README.md) - Overview and API reference
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment guide
- [worker_integration.py](examples/worker_integration.py) - Integration examples
- Architecture Plan: `../Enhanced_RPA_Openshift/rpa_architectural_plan(2).md`
