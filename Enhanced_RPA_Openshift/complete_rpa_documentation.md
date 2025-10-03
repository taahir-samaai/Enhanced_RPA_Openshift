# RPA Solution Documentation - Batch-First Architecture

## 📋 Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Container Structure](#container-structure)
4. [Data Flow](#data-flow)
5. [Integration Points](#integration-points)
6. [Deployment](#deployment)
7. [Monitoring](#monitoring)
8. [Troubleshooting](#troubleshooting)

---

## 1. System Overview

### Purpose
Automated RPA system for processing FNO (Fiber Network Operator) jobs including validations and cancellations across multiple providers.

### Key Features
- **Batch-First Processing**: Orchestrator groups jobs into batches for optimal efficiency
- **TOTP Management**: Centralized TOTP generation with Valkey tracking
- **Session Reuse**: One browser session per batch (10x efficiency gain)
- **True Parallelization**: All workers can process all FNO types
- **Distributed Coordination**: Valkey-based state management

### Supported Providers
- **Octotel** (TOTP required)
- **Openserve** (formerly OSN)
- **MetroFiber (MFN)**
- **Evotel**
- Future providers (easily extensible)

### Performance Metrics
- **50 jobs without batching**: ~50 logins, ~50 minutes
- **50 jobs with batching**: ~1 login, ~5 minutes
- **Efficiency gain**: 10x faster, 98% fewer logins

---

## 2. Architecture

### 2.1 Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Layer 1: Orchestration                        │
│                                                                  │
│  ┌──────────────┐  ┌─────────────┐  ┌────────────────────────┐ │
│  │ Orchestrator │  │ TOTP Manager│  │ Batch Manager          │ │
│  │ Container    │  │ (Valkey)    │  │ (creates batches)      │ │
│  └──────────────┘  └─────────────┘  └────────────────────────┘ │
│                                                                  │
│  Responsibilities:                                              │
│  • Receive jobs from Oracle/ORDS                               │
│  • Create batches (group jobs by provider)                     │
│  • Generate ONE TOTP per batch                                 │
│  • Assign batches to workers                                   │
│  • Track batch progress                                        │
│  • Store batch metadata in Valkey                              │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           │ Dispatch batches
                           │
┌──────────────────────────┴───────────────────────────────────────┐
│                    Layer 2: Execution                            │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Worker 1     │  │ Worker 2     │  │ Worker N     │         │
│  │ Container    │  │ Container    │  │ Container    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│                                                                  │
│  Responsibilities:                                              │
│  • Receive jobs with batch_id                                  │
│  • Check Valkey for batch info                                 │
│  • Create/reuse browser session                                │
│  • Execute automation logic                                    │
│  • Update batch progress                                       │
│  • Finalize batch when complete                                │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           │ Browser operations
                           │
┌──────────────────────────┴───────────────────────────────────────┐
│                    Layer 3: Browser Automation                   │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Browser      │  │ Browser      │  │ Browser      │         │
│  │ Service 1    │  │ Service 2    │  │ Service N    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│                                                                  │
│  Responsibilities:                                              │
│  • Manage Firefox browser instances                            │
│  • Provide REST API for browser operations                     │
│  • Handle session management                                   │
│  • Execute JavaScript                                          │
│  • Capture screenshots                                         │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Supporting Infrastructure

```
┌─────────────────────────────────────────────────────────────────┐
│                    Valkey Cluster (State Store)                  │
│                                                                  │
│  Stores:                                                        │
│  • Batch metadata (batch:provider:batch_id)                    │
│  • TOTP usage tracking (totp:used:provider:code)               │
│  • Batch locks (batch_lock:provider)                           │
│  • Session information (batch session_id)                      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    Database (Job Queue)                          │
│                                                                  │
│  Stores:                                                        │
│  • Job definitions                                             │
│  • Job status                                                  │
│  • Job results                                                 │
│  • Evidence/screenshots                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Container Structure

### 3.1 Orchestrator Container

#### Purpose
Coordinates job processing, creates batches, manages TOTP, tracks state.

#### File Structure
```
Enhanced_Openshift_RPA_containers/Orchestrator_container/
│
├── orchestrator.py                 # Main FastAPI application
├── enhanced_orchestrator.py        # Enhanced with batch management
│
├── services/
│   ├── __init__.py
│   ├── batch_manager.py           # NEW: Batch creation and management
│   ├── totp_manager.py            # TOTP generation with Valkey
│   ├── config_manager.py          # Configuration management
│   └── browser_service_manager.py # Browser service lifecycle
│
├── models/
│   ├── __init__.py
│   ├── batch.py                   # NEW: Batch data models
│   ├── job.py                     # Job data models
│   └── requests.py                # API request models
│
├── db/
│   ├── __init__.py
│   ├── database.py                # Database connection
│   ├── models.py                  # SQLAlchemy models
│   └── migrations/                # Database migrations
│
├── auth/
│   ├── __init__.py
│   └── jwt_handler.py             # JWT authentication
│
├── utils/
│   ├── __init__.py
│   ├── logger.py                  # Logging configuration
│   └── validators.py              # Input validation
│
├── tests/
│   ├── test_batch_manager.py      # NEW: Batch manager tests
│   ├── test_totp_manager.py       # TOTP manager tests
│   └── test_orchestrator.py       # Integration tests
│
├── config.py                       # Configuration settings
├── requirements.txt                # Python dependencies
├── Dockerfile                      # Container image definition
├── .env.example                    # Environment variables template
└── README.md                       # Orchestrator documentation
```

#### Key Files Explained

**orchestrator.py**
```python
# Main application with FastAPI
# Endpoints:
#   POST /jobs          - Submit job
#   POST /jobs/bulk     - Submit multiple jobs
#   GET  /jobs/{id}     - Get job status
#   GET  /batches       - Get active batches
#   GET  /health        - Health check
#   GET  /metrics       - Prometheus metrics
```

**services/batch_manager.py** (NEW)
```python
# BatchManager class
# - Creates batches from pending jobs
# - Generates ONE TOTP per batch
# - Assigns batches to workers
# - Stores batch metadata in Valkey
# - Monitors batch progress
```

**services/totp_manager.py**
```python
# TOTPManager class
# - Generates TOTP codes
# - Tracks usage in Valkey
# - Prevents code reuse
# - Provides metrics
```

#### Dependencies
```txt
# requirements.txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
valkey==5.0.1
pyotp==2.9.0
pydantic==2.5.0
python-jose[cryptography]==3.3.0
apscheduler==3.10.4
requests==2.31.0
prometheus-client==0.19.0
```

#### Environment Variables
```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/rpa_db

# Valkey
VALKEY_HOST=valkey-service
VALKEY_PORT=6379
VALKEY_PASSWORD=your_password

# Batch Configuration
BATCH_SIZE=50
BATCH_MODE=true
TOTP_PROVIDERS=octotel

# Worker Endpoints
WORKER_ENDPOINTS=http://worker-1:8621,http://worker-2:8621

# TOTP Secrets (from OpenShift secrets)
OCTOTEL_TOTP_SECRET=base32_secret
```

---

### 3.2 Worker Container

#### Purpose
Executes automation jobs, manages browser sessions, processes batches.

#### File Structure
```
Enhanced_Openshift_RPA_containers/Worker_container/
│
├── worker_refactored.py           # Main FastAPI application
│
├── services/
│   ├── __init__.py
│   ├── batch_processor.py         # NEW: Batch-aware processing
│   ├── browser_client.py          # Browser service REST client
│   └── screenshot_service.py      # Evidence collection
│
├── providers/                      # FNO-specific automation
│   │
│   ├── octotel/
│   │   ├── __init__.py
│   │   ├── validation.py          # Octotel validation automation
│   │   └── cancellation.py        # Octotel cancellation automation
│   │
│   ├── openserve/
│   │   ├── __init__.py
│   │   ├── validation.py          # Openserve validation
│   │   └── cancellation.py        # Openserve cancellation
│   │
│   ├── mfn/                        # MetroFiber
│   │   ├── __init__.py
│   │   ├── validation.py
│   │   └── cancellation.py
│   │
│   └── evotel/
│       ├── __init__.py
│       ├── validation.py
│       └── cancellation.py
│
├── models/
│   ├── __init__.py
│   ├── requests.py                # Request models
│   ├── responses.py               # Response models
│   └── validation_result.py       # Result models
│
├── factories/
│   ├── __init__.py
│   └── provider_factory.py        # Provider loading
│
├── tests/
│   ├── test_batch_processor.py    # NEW: Batch tests
│   ├── test_providers/            # Provider tests
│   │   ├── test_octotel.py
│   │   ├── test_openserve.py
│   │   └── test_mfn.py
│   └── test_integration.py
│
├── config.py                       # Configuration
├── requirements.txt                # Dependencies
├── Dockerfile                      # Container image
├── .env.example                    # Environment template
└── README.md                       # Worker documentation
```

#### Key Files Explained

**worker_refactored.py**
```python
# Main FastAPI application
# Endpoints:
#   POST /execute       - Execute job
#   GET  /batch/status  - Current batch status
#   POST /batch/flush   - Flush current batch
#   GET  /health        - Health check
#   GET  /stats         - Worker statistics
```

**services/batch_processor.py** (NEW)
```python
# BatchAwareProcessor class
# - Detects batch jobs (has batch_id)
# - Gets batch info from Valkey
# - Creates/reuses browser sessions
# - Updates batch progress
# - Finalizes batch when complete
```

**providers/octotel/validation.py**
```python
# OctotelValidationAutomation class
# - Accepts optional session_id parameter
# - Supports session reuse (batch mode)
# - Detects session expiration
# - Performs validation logic
```

**factories/provider_factory.py**
```python
# ProviderFactory class
# - Dynamically loads provider modules
# - Routes jobs to correct automation
# - Manages automation instances
```

#### Dependencies
```txt
# requirements.txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
aiohttp==3.9.1
valkey==5.0.1
pydantic==2.5.0
pillow==10.1.0
python-dateutil==2.8.2
```

#### Environment Variables
```bash
# Browser Service
BROWSER_SERVICE_URL=http://browser-service:8080

# Valkey
VALKEY_HOST=valkey-service
VALKEY_PORT=6379
VALKEY_PASSWORD=your_password

# Batch Configuration
BATCH_SIZE=50
BATCH_TIMEOUT=30

# Provider Configuration
TOTP_PROVIDERS=octotel
```

---

### 3.3 Browser Service Container

#### Purpose
Provides browser automation capabilities via REST API using Playwright and Firefox.

#### File Structure
```
Enhanced_Openshift_RPA_containers/Browser_container/
│
├── app.py                          # Main FastAPI application
│
├── services/
│   ├── __init__.py
│   ├── browser_manager.py         # Browser lifecycle management
│   └── auth_service.py            # JWT authentication
│
├── factories/
│   ├── __init__.py
│   ├── browser_factory.py         # Browser type factory
│   └── session_factory.py         # Session/context factory
│
├── models/
│   ├── __init__.py
│   ├── requests.py                # API request models
│   └── responses.py               # API response models
│
├── client/
│   ├── __init__.py
│   └── browser_client_lib.py      # Python client library
│
├── tests/
│   ├── test_browser_manager.py
│   ├── test_session_factory.py
│   └── test_integration.py
│
├── config.py                       # Configuration
├── requirements.txt                # Dependencies
├── Dockerfile                      # Container image
├── .env.example                    # Environment template
└── README.md                       # Browser service docs
```

#### Key Files Explained

**app.py**
```python
# Main FastAPI application
# Endpoints:
#   POST   /browser/session/create    - Create session
#   POST   /browser/navigate           - Navigate to URL
#   POST   /browser/click              - Click element
#   POST   /browser/fill               - Fill input
#   POST   /browser/screenshot         - Take screenshot
#   GET    /browser/text               - Get element text
#   DELETE /browser/session/close      - Close session
#   GET    /health                     - Health check
```

**services/browser_manager.py**
```python
# BrowserManager class
# - Manages Playwright browser instances
# - Creates/closes sessions
# - Executes browser commands
# - Handles timeouts and errors
```

**factories/session_factory.py**
```python
# SessionFactory class
# - Creates browser contexts (sessions)
# - Configures viewport, user agent
# - Manages session lifecycle
```

#### Dependencies
```txt
# requirements.txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
playwright==1.40.0
pydantic==2.5.0
python-jose[cryptography]==3.3.0
```

#### Environment Variables
```bash
# Browser Configuration
BROWSER_TYPE=firefox
HEADLESS=true

# Authentication
JWT_SECRET=your_secret_key

# Resource Limits
MAX_SESSIONS=10
SESSION_TIMEOUT=600
```

---

### 3.4 Valkey Cluster

#### Purpose
Distributed state store for batch metadata, TOTP tracking, and coordination.

#### Data Structures

**Batch Metadata**
```redis
Key:   batch:octotel:batch_001
Value: {
  "batch_id": "batch_001",
  "provider": "octotel",
  "worker_id": "worker-1",
  "totp_code": "123456",
  "session_id": "abc123",
  "job_ids": [1,2,3,...,50],
  "status": "in_progress",
  "created_at": "2025-10-01T10:00:00Z",
  "started_at": "2025-10-01T10:00:05Z",
  "completed_at": null,
  "batch_size": 50,
  "jobs_completed": 15,
  "jobs_failed": 0
}
TTL:   3600 seconds
```

**TOTP Usage Tracking**
```redis
Key:   totp:used:octotel:123456
Value: {
  "job_id": 1,
  "reserved_at": "2025-10-01T10:00:00Z",
  "provider": "octotel"
}
TTL:   60 seconds
```

**TOTP Metrics**
```redis
Key:   totp:metrics:octotel:success
Value: 145  # Count of successful authentications
TTL:   None (persistent)
```

#### Configuration
```yaml
# valkey-configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: valkey-config
data:
  valkey.conf: |
    bind 0.0.0.0
    port 6379
    maxmemory 2gb
    maxmemory-policy allkeys-lru
    save 900 1
    save 300 10
```

---

## 4. Data Flow

### 4.1 Batch Creation Flow

```
1. Oracle Dashboard → ORDS → Orchestrator
   POST /jobs/bulk
   {
     "provider": "octotel",
     "action": "validation",
     "jobs": [
       {"circuit_number": "CIRC001"},
       {"circuit_number": "CIRC002"},
       ... 200 jobs
     ]
   }

2. Orchestrator → Database
   INSERT INTO job_queue (provider, action, parameters, status)
   VALUES ('octotel', 'validation', {...}, 'pending')
   ... (200 inserts)

3. Orchestrator (poll_job_queue)
   SELECT * FROM job_queue WHERE status = 'pending' LIMIT 200

4. Orchestrator (BatchManager.create_batches)
   Group 200 jobs into 4 batches of 50

5. For each batch:
   a. Orchestrator → TOTPManager
      totp_code = get_fresh_totp_code('octotel', batch_id)
   
   b. TOTPManager → Valkey
      SET totp:used:octotel:123456 {...} EX 60
   
   c. Orchestrator → Valkey
      SET batch:octotel:batch_001 {...} EX 3600
   
   d. Orchestrator → Worker
      POST /execute
      {
        "job_id": 1,
        "provider": "octotel",
        "action": "validation",
        "parameters": {
          "circuit_number": "CIRC001",
          "batch_id": "batch_001",
          "totp_code": "123456"
        }
      }
```

### 4.2 Job Execution Flow

```
1. Worker receives job with batch_id

2. Worker → Valkey
   GET batch:octotel:batch_001
   
   Response: {
     "session_id": null,  # No session yet
     "totp_code": "123456",
     ...
   }

3. Worker (first job) → Browser Service
   POST /browser/session/create
   
   Response: {
     "session_id": "abc123"
   }

4. Worker → Browser Service (Login)
   POST /browser/navigate
   POST /browser/fill (username, password)
   POST /browser/fill (TOTP "123456")
   POST /browser/click (login button)

5. Worker → Valkey (Update batch)
   SET batch:octotel:batch_001 {
     "session_id": "abc123",
     "status": "in_progress",
     ...
   }

6. Worker → Provider Automation
   Execute validation logic using session_id

7. Worker → Valkey (Update progress)
   Increment jobs_completed counter

8. Worker → Orchestrator
   POST /jobs/{id}/complete
   {
     "status": "success",
     "result": {...}
   }

9. Orchestrator → Database
   UPDATE job_queue SET status = 'completed' WHERE id = 1

--- Next job in batch ---

10. Worker receives job 2 (same batch_id)

11. Worker → Valkey
    GET batch:octotel:batch_001
    
    Response: {
      "session_id": "abc123",  # Session exists!
      ...
    }

12. Worker → Provider Automation
    Execute validation using existing session_id
    (Skip login - already logged in!)

13. Repeat steps 7-9

--- Last job in batch ---

14. Worker detects batch complete
    (jobs_completed == batch_size)

15. Worker → Browser Service
    DELETE /browser/session/close
    
16. Worker → Valkey
    SET batch:octotel:batch_001 {
      "status": "completed",
      "completed_at": "...",
      ...
    }
```

### 4.3 Parallel Processing

```
Time    Worker 1          Worker 2          Worker 3
─────────────────────────────────────────────────────────
T=0     batch_001 (1-50)  batch_002 (51-100) batch_003 (101-150)
        Octotel           Octotel            Octotel
        
T=5     Create session    Create session     Create session
        Login TOTP 1      Login TOTP 2       Login TOTP 3
        
T=10    Job 1 ✓          Job 51 ✓           Job 101 ✓
T=15    Job 2 ✓          Job 52 ✓           Job 102 ✓
T=20    Job 3 ✓          Job 53 ✓           Job 103 ✓
...     
T=120   Job 50 ✓         Job 100 ✓          Job 150 ✓
        Close session     Close session      Close session
        
Result: 150 jobs processed in ~2 minutes with 3 logins
```

---

## 5. Integration Points

### 5.1 External Integrations

#### Oracle ORDS (Job Submission)
```http
POST https://oracle-ords.example.com/rpa/jobs
Content-Type: application/json

{
  "provider": "octotel",
  "action": "validation",
  "circuit_number": "CIRC12345",
  "callback_url": "https://ords.example.com/rpa/callback"
}

Response:
{
  "job_id": 123,
  "status": "accepted"
}
```

#### Oracle ORDS (Callback)
```http
POST https://oracle-ords.example.com/rpa/callback
Content-Type: application/json

{
  "job_id": 123,
  "status": "completed",
  "result": {
    "found": true,
    "status": "active",
    "customer": "ABC Corp"
  },
  "screenshots": ["base64..."]
}
```

### 5.2 Internal Integrations

#### Orchestrator ↔ Worker
```http
POST http://worker-1:8621/execute
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "job_id": 1,
  "provider": "octotel",
  "action": "validation",
  "parameters": {
    "circuit_number": "CIRC001",
    "batch_id": "batch_001",
    "totp_code": "123456"
  }
}
```

#### Worker ↔ Browser Service
```http
POST http://browser-service:8080/browser/session/create
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "job_id": 1,
  "headless": true
}

Response:
{
  "session_id": "abc123",
  "status": "created"
}
```

#### Worker/Orchestrator ↔ Valkey
```python
# Python client
import valkey

client = valkey.Valkey(
    host='valkey-service',
    port=6379,
    password='xxx',
    decode_responses=True
)

# Store batch
client.set(
    'batch:octotel:batch_001',
    json.dumps(batch_data),
    ex=3600
)

# Get batch
batch_data = json.loads(
    client.get('batch:octotel:batch_001')
)

# Update batch
batch_data['jobs_completed'] += 1
client.set(
    'batch:octotel:batch_001',
    json.dumps(batch_data),
    ex=3600
)
```

---

## 6. Deployment

### 6.1 OpenShift Deployment Order

```bash
# 1. Create namespace
oc new-project rpa-system

# 2. Deploy Valkey cluster
oc apply -f 01-valkey-statefulset.yaml
oc wait --for=condition=ready pod -l app=valkey --timeout=300s

# 3. Create secrets
oc apply -f 02-secrets.yaml

# 4. Create config maps
oc apply -f 03-configmaps.yaml

# 5. Deploy Database
oc apply -f 04-database.yaml
oc wait --for=condition=ready pod -l app=postgres --timeout=300s

# 6. Deploy Browser Service
oc apply -f 05-browser-service.yaml
oc wait --for=condition=ready pod -l app=browser-service --timeout=300s

# 7. Deploy Orchestrator
oc apply -f 06-orchestrator.yaml
oc wait --for=condition=ready pod -l app=orchestrator --timeout=300s

# 8. Deploy Workers
oc apply -f 07-worker.yaml
oc scale deployment/rpa-worker --replicas=5
oc wait --for=condition=ready pod -l app=worker --timeout=300s

# 9. Verify deployment
oc get pods
oc logs deployment/orchestrator
oc logs deployment/rpa-worker
```

### 6.2 Resource Requirements

```yaml
# Orchestrator
resources:
  requests:
    cpu: 500m
    memory: 1Gi
  limits:
    cpu: 2000m
    memory: 4Gi

# Worker
resources:
  requests:
    cpu: 1000m
    memory: 2Gi
  limits:
    cpu: 4000m
    memory: 8Gi

# Browser Service
resources:
  requests:
    cpu: 1000m
    memory: 2Gi
  limits:
    cpu: 2000m
    memory: 4Gi

# Valkey
resources:
  requests:
    cpu: 500m
    memory: 2Gi
  limits:
    cpu: 2000m
    memory: 4Gi
```

### 6.3 Scaling

```bash
# Scale workers (horizontal)
oc scale deployment/rpa-worker --replicas=10

# Scale browser services (on-demand)
# Browser services are created dynamically as needed

# Scale Valkey (vertical)
# Edit valkey statefulset to increase memory
oc edit statefulset valkey
```

---

## 7. Monitoring

### 7.1 Health Checks

```bash
# Orchestrator
curl http://orchestrator:8620/health

# Worker
curl http://worker-1:8621/health

# Browser Service
curl http://browser-service:8080/health

# Valkey
oc exec valkey-0 -- valkey-cli -a xxx ping
```

### 7.2 Metrics

```bash
# Orchestrator metrics
curl http://orchestrator:8620/metrics

# Example output:
jobs_total 1250
jobs_completed 1180
jobs_failed 15
jobs_active 5
batches_created 45
batches_completed 42
totp_codes_generated 45
totp_success_rate 0.98

# Worker metrics
curl http://worker-1:8621/stats

# Example output:
{
  "active_batches": 1,
  "batches_processed": 15,
  "jobs_processed": 750,
  "session_reuses": 735,
  "efficiency": "98.0%"
}
```

### 7.3 Batch Monitoring

```bash
# Get active batches
curl http://orchestrator:8620/batches/active

{
  "active_batches": 3,
  "batches": [
    {
      "batch_id": "batch_001",
      "provider": "octotel",
      "worker": "worker-1",
      "progress": "25/50",
      "status": "in_progress",
      "session_id": "abc123"
    }
  ]
}

# Check specific batch in Valkey
oc exec valkey-0 -- valkey-cli -a xxx \
  GET "batch:octotel:batch_001"
```

### 7.4 Logging

```bash
# View orchestrator logs
oc logs -f deployment/orchestrator

# View worker logs
oc logs -f deployment/rpa-worker

# View browser service logs
oc logs -f deployment/browser-service

# Filter by batch_id
oc logs deployment/orchestrator | grep "batch_001"

# Filter by job_id
oc logs deployment/rpa-worker | grep "job_id: 123"
```

---

## 8. Troubleshooting

### 8.1 Common Issues

#### Issue: Batch stuck in "assigned" status

**Symptoms:**
- Batch created but never moves to "in_progress"
- Jobs not executing

**Diagnosis:**
```bash
# Check batch in Valkey
oc exec valkey-0 -- valkey-cli -a xxx \
  GET "batch:octotel:batch_001"

# Check worker logs
oc logs deployment/rpa-worker | grep "batch_001"

# Check if jobs were dispatched
curl http://orchestrator:8620/jobs?batch_id=batch_001
```

**Solutions:**
1. Check worker connectivity
2. Verify batch_id is being sent to worker
3. Check Valkey connectivity from worker
4. Restart worker if needed

---

#### Issue: Session expired mid-batch

**Symptoms:**
- First 10 jobs succeed, rest fail
- Error: "Session not found" or "Context closed"

**Diagnosis:**
```bash
# Check batch progress
curl http://worker-1:8621/batch/status

# Check session_id in Valkey
oc exec valkey-0 -- valkey-cli -a xxx \
  GET "batch:octotel:batch_001"
```

**Solutions:**
1. Reduce BATCH_SIZE to ensure completion within session timeout
2. Implement session refresh logic
3. Increase FNO portal session timeout if possible

---

#### Issue: TOTP authentication fails

**Symptoms:**
- All jobs in batch fail at login
- Error: "Invalid TOTP code"

**Diagnosis:**
```bash
# Check TOTP in batch
oc exec valkey-0 -- valkey-cli -a xxx \
  GET "batch:octotel:batch_001"

# Check TOTP generation logs
oc logs deployment/orchestrator | grep "TOTP"

# Verify time sync
oc exec orchestrator-pod -- date
oc exec worker-1-pod -- date
```

**Solutions:**
1. Verify TOTP secret is correct
2. Check system time synchronization (NTP)
3. Verify TOTP window settings (30s standard)

---

#### Issue: Multiple workers processing same batch

**Symptoms:**
- Duplicate job executions
- Concurrent session creation errors

**Diagnosis:**
```bash
# Check which workers have the batch
oc logs deployment/rpa-worker | grep "batch_001"

# Check batch owner in Valkey
oc exec valkey-0 -- valkey-cli -a xxx \
  GET "batch:octotel:batch_001"
```

**Solutions:**
This shouldn't happen with batch-first architecture since orchestrator assigns batch to ONE worker. If it does:
1. Check orchestrator dispatch logic
2. Verify worker_id is being set correctly
3. Check for race conditions in batch assignment

---

### 8.2 Debugging Commands

```bash
# Check Valkey keys
oc exec valkey-0 -- valkey-cli -a xxx KEYS "batch:*"
oc exec valkey-0 -- valkey-cli -a xxx KEYS "totp:*"

# Monitor Valkey in real-time
oc exec valkey-0 -- valkey-cli -a xxx MONITOR

# Check database
oc exec database-pod -- psql -U rpa -d rpa_db \
  -c "SELECT * FROM job_queue WHERE status = 'dispatched';"

# Check network connectivity
oc exec worker-1-pod -- curl http://browser-service:8080/health
oc exec worker-1-pod -- curl http://valkey-service:6379

# View all container logs
oc logs -f --all-containers -l app=rpa-system

# Check resource usage
oc adm top pods
oc describe pod worker-1-pod
```

---

## 9. Development Workflow

### 9.1 Local Development

```bash
# 1. Start Valkey locally
docker-compose up -d valkey

# 2. Set environment variables
export VALKEY_HOST=localhost
export VALKEY_PORT=6379
export DATABASE_URL=sqlite:///local.db

# 3. Run orchestrator
cd Orchestrator_container
python orchestrator.py

# 4. Run worker (different terminal)
cd Worker_container
python worker_refactored.py

# 5. Run browser service (different terminal)
cd Browser_container
python app.py

# 6. Submit test job
curl -X POST http://localhost:8620/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "octotel",
    "action": "validation",
    "parameters": {"circuit_number": "TEST123"}
  }'
```

### 9.2 Testing

```bash
# Unit tests
pytest tests/test_batch_manager.py -v
pytest tests/test_batch_processor.py -v

# Integration tests
pytest tests/test_integration.py -v

# Load tests
locust -f tests/load_test.py --host=http://localhost:8620
```

### 9.3 Building Containers

```bash
# Build orchestrator
docker build -t rpa-orchestrator:v2.0 \
  -f Orchestrator_container/Dockerfile \
  Orchestrator_container/

# Build worker
docker build -t rpa-worker:v2.0 \
  -f Worker_container/Dockerfile \
  Worker_container/

# Build browser service
docker build -t rpa-browser:v2.0 \
  -f Browser_container/Dockerfile \
  Browser_container/

# Push to registry
docker tag rpa-orchestrator:v2.0 registry.io/rpa-orchestrator:v2.0
docker push registry.io/rpa-orchestrator:v2.0
```

---

## 10. Configuration Reference

### 10.1 Environment Variables

#### Orchestrator
```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/db
DB_POOL_SIZE=20

# Valkey
VALKEY_HOST=valkey-service
VALKEY_PORT=6379
VALKEY_PASSWORD=xxx

# Batch Configuration
BATCH_SIZE=50                    # Jobs per batch
BATCH_MODE=true                  # Enable batching
TOTP_PROVIDERS=octotel           # Comma-separated

# Worker Configuration
WORKER_ENDPOINTS=http://worker-1:8621,http://worker-2:8621
MAX_WORKERS=5

# TOTP Secrets
OCTOTEL_TOTP_SECRET=base32_secret

# Scheduling
POLL_INTERVAL=5                  # Seconds between polls
BATCH_MONITOR_INTERVAL=30        # Seconds

# Logging
LOG_LEVEL=INFO
```

#### Worker
```bash
# Browser Service
BROWSER_SERVICE_URL=http://browser-service:8080

# Valkey
VALKEY_HOST=valkey-service
VALKEY_PORT=6379
VALKEY_PASSWORD=xxx

# Batch Configuration
BATCH_SIZE=50
BATCH_TIMEOUT=30                 # Seconds

# Provider Configuration
TOTP_PROVIDERS=octotel

# Logging
LOG_LEVEL=INFO
```

#### Browser Service
```bash
# Browser
BROWSER_TYPE=firefox
HEADLESS=true

# Resources
MAX_SESSIONS=10
SESSION_TIMEOUT=600              # Seconds

# Security
JWT_SECRET=your_secret

# Logging
LOG_LEVEL=INFO
```

---

## Appendix A: Batch State Machine

```
Created → Assigned → In Progress → Completed
   │          │           │            
   │          │           └─→ Failed
   │          └─→ Failed
   └─→ Failed

States:
- created:      Batch created, not yet assigned
- assigned:     Assigned to worker, not yet started
- in_progress:  Worker processing jobs
- completed:    All jobs done successfully
- failed:       Batch failed (reassign or abort)
```

---

## Appendix B: Quick Reference

### Common Commands
```bash
# View active batches
curl http://orchestrator:8620/batches/active

# Check worker stats
curl http://worker-1:8621/stats

# Flush worker batch
curl -X POST http://worker-1:8621/batch/flush

# Check Valkey batch
oc exec valkey-0 -- valkey-cli -a xxx GET "batch:octotel:batch_001"

# View orchestrator logs
oc logs -f deployment/orchestrator

# Scale workers
oc scale deployment/rpa-worker --replicas=10
```

### Emergency Procedures
```bash
# Kill stuck batch
oc exec valkey-0 -- valkey-cli -a xxx DEL "batch:octotel:batch_001"

# Reset job to pending
oc exec database-pod -- psql -U rpa -d rpa_db \
  -c "UPDATE job_queue SET status = 'pending' WHERE id = 123;"

# Restart all workers
oc rollout restart deployment/rpa-worker

# Clear all Valkey batches
oc exec valkey-0 -- valkey-cli -a xxx FLUSHDB
```

---

**End of Documentation**

*Version: 2.0*  
*Last Updated: 2025-10-01*  
*Architecture: Batch-First with Orchestrator Coordination*
