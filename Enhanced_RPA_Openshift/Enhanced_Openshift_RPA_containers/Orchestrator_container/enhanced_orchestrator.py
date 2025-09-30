"""
RPA Orchestration System - Enhanced Orchestrator
------------------------------------------------
Enhanced orchestrator for three-layer architecture with browser service management,
centralized TOTP generation, and OpenShift-native configuration.

Key Features:
- Browser service lifecycle management via Kubernetes API
- Centralized TOTP generation with Valkey tracking
- OpenShift Secrets and ConfigMaps integration
- Worker-to-browser service job coordination
"""
import time
import os
import json
import logging
import datetime
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import traceback

# FastAPI imports
from fastapi import FastAPI, Depends, HTTPException, status, APIRouter, BackgroundTasks, Query, Path as FastAPIPath, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, validator
from contextlib import asynccontextmanager

# APScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Import local modules
from auth import check_permission
import auth
from rate_limiter import rate_limit_middleware
import models
import db

# Import new enhanced services
from services.browser_service_manager import BrowserServiceManager
from services.totp_manager import TOTPManager
from services.config_manager import ConfigManager
from health_reporter import HealthReporter
from monitor import generate_monitoring_html
from errors import (
    global_exception_handler,
    http_exception_handler,
    validation_error_handler
)

# Initialize configuration from OpenShift
config_manager = ConfigManager()

# Configure logging
logging.basicConfig(
    level=getattr(logging, config_manager.get("LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config_manager.get("LOG_PATH", "/var/logs/orchestrator.log"))
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Orchestrator starting with OpenShift-native configuration")

# Initialize scheduler with SQLAlchemy job store
jobstores = {
    'default': SQLAlchemyJobStore(url=config_manager.get("DATABASE_URL"))
}
scheduler = BackgroundScheduler(jobstores=jobstores, timezone='UTC')

# Thread pool for background tasks
worker_pool = ThreadPoolExecutor(max_workers=int(config_manager.get("MAX_WORKERS", "10")))

# Initialize enhanced services
browser_service_manager = BrowserServiceManager(config_manager)
totp_manager = TOTPManager(config_manager)

def send_health_report():
    """Send health report to OGGIES_LOG via ORDS."""
    if not config_manager.get_bool("HEALTH_REPORT_ENABLED"):
        return
    
    try:
        reporter = HealthReporter(
            endpoint=config_manager.get("HEALTH_REPORT_ENDPOINT"),
            server_type="Orchestrator",
            db_path=config_manager.get("DB_PATH")
        )
        
        if reporter.send():
            logger.info("Health report sent successfully")
    except Exception as e:
        logger.error(f"Error sending health report: {str(e)}")

def initialize_app_components():
    """Initialize application components before FastAPI starts."""
    logger.info("Initializing application components...")
    
    if not db.init_db():
        logger.error("Failed to initialize database")
        return False
    
    if not auth.create_default_admin():
        logger.error("Failed to create default admin user")
        return False
    
    # Initialize TOTP manager with Valkey connection
    if not totp_manager.initialize():
        logger.error("Failed to initialize TOTP manager")
        return False
    
    job_count = reset_and_configure_scheduler()
    logger.info(f"Configured scheduler with {job_count} jobs")
        
    logger.info("Application components initialized successfully")
    return True

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    try:
        app.state.start_time = datetime.datetime.now(datetime.UTC)
        app.state.initialized = initialize_app_components()
        
        if not app.state.initialized:
            logger.error("Application initialization failed")
        
        yield
        
        logger.info("Shutting down RPA Orchestrator...")
        
        if scheduler.running:
            scheduler.shutdown()
            logger.info("Scheduler shutdown complete")
        
        # Cleanup browser services
        browser_service_manager.cleanup_all_services()
        
        worker_pool.shutdown(wait=False)
        db.SessionLocal.remove()
        db.engine.dispose()
        
        logger.info("Graceful shutdown completed")
    except Exception as e:
        logger.error(f"Error during startup/shutdown: {str(e)}")
        traceback.print_exc()
        yield

# Initialize FastAPI app
app = FastAPI(
    title="RPA Orchestration System - Enhanced",
    description="API for managing RPA automation jobs with three-layer architecture",
    version="2.0.0-enhanced",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config_manager.get_list("CORS_ORIGINS", ["*"]),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add exception handlers
app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)

# Add rate limiting middleware
app.middleware("http")(rate_limit_middleware)

def reset_and_configure_scheduler():
    """Reset and configure the scheduler with standard jobs."""
    try:
        scheduler.remove_all_jobs()
        
        # Poll job queue every 5 seconds
        scheduler.add_job(
            poll_job_queue,
            'interval',
            seconds=int(config_manager.get("POLL_INTERVAL", "5")),
            id='poll_job_queue',
            replace_existing=True
        )
        
        # Recover stale jobs every 5 minutes
        scheduler.add_job(
            db.recover_stale_locks,
            'interval',
            minutes=5,
            id='recover_stale_locks',
            replace_existing=True
        )
        
        # Send health reports every 5 minutes
        scheduler.add_job(
            send_health_report,
            'interval',
            minutes=5,
            id='send_health_report',
            replace_existing=True
        )
        
        # Collect metrics every minute
        scheduler.add_job(
            db.record_system_metrics,
            'interval',
            minutes=1,
            id='record_metrics',
            replace_existing=True
        )
        
        # Cleanup browser services every 2 minutes
        scheduler.add_job(
            browser_service_manager.cleanup_idle_services,
            'interval',
            minutes=2,
            id='cleanup_browser_services',
            replace_existing=True
        )
        
        if not scheduler.running:
            scheduler.start()
            logger.info("Scheduler started successfully")
        
        jobs = scheduler.get_jobs()
        return len(jobs)
        
    except Exception as e:
        logger.error(f"Error configuring scheduler: {str(e)}")
        traceback.print_exc()
        return 0

def poll_job_queue():
    """Poll database for pending jobs and dispatch them."""
    try:
        pending_jobs = db.get_jobs_by_status("pending", limit=10)
        
        for job_dict in pending_jobs:
            try:
                dispatch_job(job_dict)
            except Exception as e:
                logger.error(f"Error dispatching job {job_dict['id']}: {str(e)}")
                
    except Exception as e:
        logger.error(f"Error polling job queue: {str(e)}")

def dispatch_job(job_dict: Dict[str, Any]):
    """
    Enhanced job dispatch with browser service management and TOTP generation.
    
    Flow:
    1. Check if job requires browser automation
    2. If yes, provision browser service pod
    3. Generate TOTP if provider requires it
    4. Assign worker and browser service to job
    5. Dispatch to worker with all required info
    """
    job_id = job_dict['id']
    provider = job_dict['provider']
    action = job_dict['action']
    
    try:
        logger.info(f"Dispatching job {job_id}: {provider}/{action}")
        
        # Update job status to dispatching
        db.update_job_status(job_id, "dispatching")
        
        # Check if provider requires TOTP
        totp_code = None
        if totp_manager.provider_requires_totp(provider):
            logger.info(f"Job {job_id} requires TOTP, generating fresh code...")
            totp_code = totp_manager.get_fresh_totp_code(provider, job_id)
            logger.info(f"Generated TOTP for job {job_id}")
        
        # Provision browser service
        logger.info(f"Provisioning browser service for job {job_id}...")
        browser_service_info = browser_service_manager.provision_browser_service(job_id)
        
        if not browser_service_info:
            raise Exception("Failed to provision browser service")
        
        logger.info(f"Browser service provisioned: {browser_service_info['service_url']}")
        
        # Find available worker
        worker_url = find_available_worker()
        if not worker_url:
            raise Exception("No available workers")
        
        # Prepare enhanced job payload
        job_payload = {
            "job_id": job_id,
            "provider": provider,
            "action": action,
            "parameters": job_dict.get("parameters", {}),
            "browser_service_url": browser_service_info['service_url'],
            "browser_service_id": browser_service_info['service_id'],
            "totp_code": totp_code,
            "orchestrator_callback": f"{config_manager.get('ORCHESTRATOR_URL')}/callbacks/job-complete"
        }
        
        # Dispatch to worker
        response = send_job_to_worker(worker_url, job_payload)
        
        if response.get("status") == "accepted":
            db.update_job_status(
                job_id,
                "running",
                result={"worker": worker_url, "browser_service": browser_service_info['service_url']}
            )
            logger.info(f"Job {job_id} dispatched successfully to worker {worker_url}")
        else:
            raise Exception(f"Worker rejected job: {response.get('message')}")
            
    except Exception as e:
        logger.error(f"Error dispatching job {job_id}: {str(e)}")
        traceback.print_exc()
        
        # Cleanup browser service if provisioned
        if 'browser_service_info' in locals():
            browser_service_manager.terminate_browser_service(
                browser_service_info['service_id']
            )
        
        # Update job status to failed
        db.update_job_status(
            job_id,
            "failed",
            result={"error": str(e), "stage": "dispatch"}
        )

def find_available_worker() -> Optional[str]:
    """Find an available worker from registered workers."""
    workers = config_manager.get_list("WORKER_URLS", [])
    
    for worker_url in workers:
        try:
            response = requests.get(f"{worker_url}/status", timeout=2)
            if response.status_code == 200:
                status = response.json()
                if status.get("available", False):
                    return worker_url
        except Exception as e:
            logger.debug(f"Worker {worker_url} not available: {str(e)}")
            continue
    
    return None

def send_job_to_worker(worker_url: str, job_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Send job to worker via REST API."""
    try:
        response = requests.post(
            f"{worker_url}/execute",
            json=job_payload,
            timeout=int(config_manager.get("WORKER_TIMEOUT", "30"))
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error sending job to worker {worker_url}: {str(e)}")
        return {"status": "error", "message": str(e)}

def send_external_report(job_id: int, status: str, result: Dict[str, Any]):
    """Send external job completion report via callback."""
    callback_endpoint = config_manager.get("CALLBACK_ENDPOINT")
    if not callback_endpoint:
        return
    
    try:
        job_dict = db.get_job(job_id)
        external_job_id = job_dict.get("parameters", {}).get("external_job_id")
        
        payload = {
            "job_id": job_id,
            "external_job_id": external_job_id,
            "status": status,
            "result": result,
            "completed_at": datetime.datetime.now(datetime.UTC).isoformat()
        }
        
        response = requests.post(
            callback_endpoint,
            json=payload,
            headers={"Authorization": f"Bearer {config_manager.get('CALLBACK_AUTH_TOKEN')}"},
            timeout=int(config_manager.get("CALLBACK_TIMEOUT", "10"))
        )
        response.raise_for_status()
        logger.info(f"External report sent for job {job_id}")
        
    except Exception as e:
        logger.error(f"Error sending external report for job {job_id}: {str(e)}")

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint with system information."""
    return {
        "service": "RPA Orchestration System - Enhanced",
        "version": "2.0.0-enhanced",
        "architecture": "three-layer",
        "status": "operational",
        "features": [
            "Browser service lifecycle management",
            "Centralized TOTP generation",
            "OpenShift-native configuration",
            "High availability"
        ]
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for OpenShift probes."""
    try:
        # Check database
        with db.db_session() as session:
            session.execute("SELECT 1")
        
        # Check Valkey
        valkey_healthy = totp_manager.health_check()
        
        # Check scheduler
        scheduler_healthy = scheduler.running
        
        if not valkey_healthy:
            raise Exception("Valkey connection failed")
        
        if not scheduler_healthy:
            raise Exception("Scheduler not running")
        
        return {
            "status": "healthy",
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "components": {
                "database": "healthy",
                "valkey": "healthy",
                "scheduler": "healthy"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/health/ready")
async def readiness_check():
    """Readiness check for OpenShift."""
    return await health_check()

@app.get("/health/live")
async def liveness_check():
    """Liveness check for OpenShift."""
    return {"status": "alive", "timestamp": datetime.datetime.now(datetime.UTC).isoformat()}

@app.get("/status")
async def get_system_status():
    """Get detailed system status."""
    try:
        uptime = datetime.datetime.now(datetime.UTC) - app.state.start_time
        
        # Get job counts
        with db.db_session() as session:
            queued = session.query(db.JobQueue).filter_by(status="pending").count()
            running = session.query(db.JobQueue).filter_by(status="running").count()
            completed = session.query(db.JobQueue).filter_by(status="completed").count()
            failed = session.query(db.JobQueue).filter_by(status="failed").count()
        
        # Get browser service status
        browser_services = browser_service_manager.get_active_services()
        
        return {
            "status": "operational",
            "uptime_seconds": int(uptime.total_seconds()),
            "jobs": {
                "queued": queued,
                "running": running,
                "completed": completed,
                "failed": failed
            },
            "browser_services": {
                "active": len(browser_services),
                "services": browser_services
            },
            "scheduler": {
                "running": scheduler.running,
                "jobs": len(scheduler.get_jobs())
            }
        }
    except Exception as e:
        logger.error(f"Error getting system status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/token")
async def login_endpoint(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authentication endpoint."""
    return await auth.login_for_access_token(form_data)

@app.post("/jobs", response_model=models.Job)
async def create_job_endpoint(
    job: models.JobCreate,
    background_tasks: BackgroundTasks,
    api_key_info: Dict = Depends(check_permission("job:create"))
):
    """Create a new job."""
    external_job_id = job.parameters.get("external_job_id")
    
    job_dict = db.create_job(
        provider=job.provider,
        action=job.action,
        parameters=job.parameters,
        external_job_id=external_job_id,
        priority=job.priority,
        retry_count=job.retry_count,
        max_retries=job.max_retries
    )
    
    if job.priority > 5:
        background_tasks.add_task(dispatch_job, job_dict)
    
    return models.Job(**job_dict)

@app.get("/jobs/{job_id}", response_model=models.Job)
async def get_job_endpoint(
    job_id: int = FastAPIPath(..., ge=1, title="The ID of the job to get")
):
    """Get job details."""
    job_dict = db.get_job(job_id)
    if not job_dict:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if 'status' not in job_dict or job_dict['status'] is None:
        job_dict['status'] = "pending"
        
    return models.Job(**job_dict)

@app.get("/jobs", response_model=List[models.Job])
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter jobs by status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """List jobs with optional filtering."""
    if status:
        jobs = db.get_jobs_by_status(status, limit, offset)
    else:
        with db.db_session() as session:
            query = session.query(db.JobQueue)
            query = query.order_by(db.JobQueue.created_at.desc())
            query = query.limit(limit).offset(offset)
            jobs = [db.to_dict(job) for job in query.all()]
    
    return [models.Job(**job) for job in jobs]

@app.patch("/jobs/{job_id}", response_model=models.Job)
async def update_job_status_endpoint(
    job_id: int = FastAPIPath(..., ge=1),
    status_update: models.JobStatusUpdate = None
):
    """Update job status."""
    job_dict = db.get_job(job_id)
    if not job_dict:
        raise HTTPException(status_code=404, detail="Job not found")
    
    updated_job = db.update_job_status(
        job_id,
        status_update.status,
        result=status_update.result,
        evidence=status_update.evidence
    )
    
    if not updated_job:
        raise HTTPException(status_code=500, detail="Failed to update job status")
    
    return models.Job(**updated_job)

@app.post("/callbacks/job-complete")
async def job_complete_callback(request: Request):
    """Callback endpoint for workers to report job completion."""
    try:
        payload = await request.json()
        job_id = payload.get("job_id")
        status = payload.get("status")
        result = payload.get("result", {})
        evidence = payload.get("evidence", {})
        browser_service_id = payload.get("browser_service_id")
        
        logger.info(f"Received completion callback for job {job_id}: {status}")
        
        # Update job status
        db.update_job_status(job_id, status, result=result, evidence=evidence)
        
        # Terminate browser service
        if browser_service_id:
            browser_service_manager.terminate_browser_service(browser_service_id)
        
        # Mark TOTP as consumed if applicable
        if payload.get("totp_used"):
            totp_manager.mark_totp_consumed(
                provider=payload.get("provider"),
                job_id=job_id,
                success=(status == "completed")
            )
        
        # Send external report
        if config_manager.get("CALLBACK_ENDPOINT"):
            send_external_report(job_id, status, result)
        
        return {"status": "acknowledged"}
        
    except Exception as e:
        logger.error(f"Error processing job completion callback: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/browser-services")
async def list_browser_services():
    """List active browser services."""
    services = browser_service_manager.get_active_services()
    return {
        "count": len(services),
        "services": services
    }

@app.get("/metrics")
async def get_metrics():
    """Get system metrics."""
    metrics_data = db.get_recent_metrics(limit=24)
    
    if metrics_data:
        avg_queued = sum(m.get("queued_jobs", 0) for m in metrics_data) / len(metrics_data)
        avg_running = sum(m.get("running_jobs", 0) for m in metrics_data) / len(metrics_data)
        avg_completed = sum(m.get("completed_jobs", 0) for m in metrics_data) / len(metrics_data)
        avg_failed = sum(m.get("failed_jobs", 0) for m in metrics_data) / len(metrics_data)
    else:
        avg_queued = avg_running = avg_completed = avg_failed = 0
    
    current_status = await get_system_status()
    return {
        "metrics": metrics_data,
        "averages": {
            "queued_jobs": avg_queued,
            "running_jobs": avg_running,
            "completed_jobs": avg_completed,
            "failed_jobs": avg_failed
        },
        "current": current_status
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(config_manager.get("ORCHESTRATOR_PORT", "8620")),
        log_level=config_manager.get("LOG_LEVEL", "info").lower()
    )
