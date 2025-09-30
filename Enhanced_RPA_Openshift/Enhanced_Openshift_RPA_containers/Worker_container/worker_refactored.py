"""
RPA Worker Service - Three-Layer Architecture
==============================================
Business logic execution layer that receives jobs from orchestrator
and delegates browser automation to browser services.

Architecture:
    Orchestrator → Worker (this) → Browser Service
    
The worker:
- Receives job requests from orchestrator via REST API
- Loads provider-specific automation modules via factory pattern
- Communicates with browser service for all browser operations
- Returns results back to orchestrator
"""

import os
import sys
import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from enum import Enum

# Import configuration
from config import Config

# Import browser service client
from browser_client import BrowserServiceClient

# Import provider factory
from provider_factory import ProviderFactory, AutomationError

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global statistics
ACTIVE_JOBS = 0
TOTAL_JOBS = 0
SUCCESSFUL_JOBS = 0
FAILED_JOBS = 0
START_TIME = datetime.now(timezone.utc)

# Initialize browser service client
browser_client = BrowserServiceClient(
    base_url=os.getenv("BROWSER_SERVICE_URL", "http://rpa-browser-service:8080")
)

# Initialize provider factory
provider_factory = ProviderFactory(browser_client)


# ============================================================================
# Pydantic Models
# ============================================================================

class JobRequest(BaseModel):
    """Job request from orchestrator"""
    job_id: int = Field(..., ge=1, description="Unique job identifier")
    provider: str = Field(..., description="Service provider (mfn, osn, octotel, evotel)")
    action: str = Field(..., description="Action to perform (validation, cancellation)")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Job parameters including TOTP")
    
    @field_validator('provider')
    @classmethod
    def validate_provider(cls, v):
        valid = ["mfn", "osn", "octotel", "evotel"]
        if v.lower() not in valid:
            raise ValueError(f"Provider must be one of {valid}")
        return v.lower()
    
    @field_validator('action')
    @classmethod
    def validate_action(cls, v):
        valid = ["validation", "cancellation"]
        if v.lower() not in valid:
            raise ValueError(f"Action must be one of {valid}")
        return v.lower()


class JobResponse(BaseModel):
    """Job execution response"""
    status: str
    job_id: int
    result: Dict[str, Any]
    execution_time: Optional[float] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    active_jobs: int
    total_jobs: int
    successful_jobs: int
    failed_jobs: int
    uptime_seconds: float
    browser_service_available: bool


# ============================================================================
# FastAPI Application
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("=" * 80)
    logger.info("RPA Worker Service Starting")
    logger.info("=" * 80)
    logger.info(f"Browser Service URL: {browser_client.base_url}")
    logger.info(f"Log Level: {Config.LOG_LEVEL}")
    
    # Check browser service health
    if await browser_client.health_check():
        logger.info("✓ Browser service is available")
    else:
        logger.warning("✗ Browser service is not available")
    
    yield
    
    logger.info("RPA Worker Service Shutting Down")


app = FastAPI(
    title="RPA Worker Service",
    description="Business logic execution layer for RPA platform",
    version="2.0.0",
    lifespan=lifespan
)


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for orchestrator"""
    global ACTIVE_JOBS, TOTAL_JOBS, SUCCESSFUL_JOBS, FAILED_JOBS, START_TIME
    
    uptime = (datetime.now(timezone.utc) - START_TIME).total_seconds()
    browser_available = await browser_client.health_check()
    
    return HealthResponse(
        status="healthy" if browser_available else "degraded",
        active_jobs=ACTIVE_JOBS,
        total_jobs=TOTAL_JOBS,
        successful_jobs=SUCCESSFUL_JOBS,
        failed_jobs=FAILED_JOBS,
        uptime_seconds=uptime,
        browser_service_available=browser_available
    )


@app.get("/status")
async def get_status():
    """Detailed worker status"""
    global ACTIVE_JOBS, TOTAL_JOBS, SUCCESSFUL_JOBS, FAILED_JOBS, START_TIME
    
    uptime = (datetime.now(timezone.utc) - START_TIME).total_seconds()
    browser_available = await browser_client.health_check()
    
    # Get available providers and actions
    capabilities = provider_factory.get_capabilities()
    
    return {
        "status": "operational",
        "worker_info": {
            "active_jobs": ACTIVE_JOBS,
            "total_jobs": TOTAL_JOBS,
            "successful_jobs": SUCCESSFUL_JOBS,
            "failed_jobs": FAILED_JOBS,
            "uptime_seconds": uptime,
            "start_time": START_TIME.isoformat()
        },
        "browser_service": {
            "available": browser_available,
            "url": browser_client.base_url
        },
        "capabilities": capabilities
    }


@app.post("/execute", response_model=JobResponse)
async def execute_job(job_request: JobRequest):
    """
    Execute automation job
    
    Flow:
    1. Receive job from orchestrator with TOTP pre-generated
    2. Load appropriate provider module via factory
    3. Execute job (module handles browser service communication)
    4. Return results
    """
    global ACTIVE_JOBS, TOTAL_JOBS, SUCCESSFUL_JOBS, FAILED_JOBS
    
    job_id = job_request.job_id
    provider = job_request.provider
    action = job_request.action
    parameters = job_request.parameters
    
    logger.info("=" * 80)
    logger.info(f"Executing Job {job_id}: {provider}.{action}")
    logger.info("=" * 80)
    logger.info(f"Parameters: {json.dumps({k: v for k, v in parameters.items() if k != 'totp_code'}, indent=2)}")
    if 'totp_code' in parameters:
        logger.info(f"TOTP: [REDACTED - provided by orchestrator]")
    
    ACTIVE_JOBS += 1
    TOTAL_JOBS += 1
    start_time = datetime.now(timezone.utc)
    
    try:
        # Get automation module from factory
        automation_module = provider_factory.get_automation(provider, action)
        
        if not automation_module:
            raise AutomationError(f"No automation found for {provider}.{action}")
        
        # Execute the automation
        logger.info(f"Job {job_id}: Executing {provider}.{action} automation")
        result = await automation_module.execute(job_id, parameters)
        
        # Ensure result is a dictionary
        if not isinstance(result, dict):
            logger.warning(f"Job {job_id}: Module returned non-dict result, wrapping")
            result = {
                "status": "completed",
                "message": "Job completed",
                "data": result
            }
        
        # Calculate execution time
        end_time = datetime.now(timezone.utc)
        execution_time = (end_time - start_time).total_seconds()
        
        SUCCESSFUL_JOBS += 1
        logger.info(f"Job {job_id}: Completed successfully in {execution_time:.2f}s")
        
        return JobResponse(
            status="success",
            job_id=job_id,
            result=result,
            execution_time=execution_time
        )
        
    except AutomationError as e:
        FAILED_JOBS += 1
        logger.error(f"Job {job_id}: Automation error - {str(e)}")
        logger.error(traceback.format_exc())
        
        return JobResponse(
            status="error",
            job_id=job_id,
            result={
                "error": str(e),
                "error_type": "AutomationError"
            }
        )
        
    except Exception as e:
        FAILED_JOBS += 1
        logger.error(f"Job {job_id}: Unexpected error - {str(e)}")
        logger.error(traceback.format_exc())
        
        return JobResponse(
            status="error",
            job_id=job_id,
            result={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        
    finally:
        ACTIVE_JOBS = max(0, ACTIVE_JOBS - 1)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "RPA Worker",
        "version": "2.0.0",
        "architecture": "three-layer",
        "endpoints": {
            "health": "/health",
            "status": "/status",
            "execute": "/execute"
        }
    }


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {str(exc)}")
    logger.error(traceback.format_exc())
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc)
        }
    )


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("WORKER_PORT", "8621"))
    host = os.getenv("WORKER_HOST", "0.0.0.0")
    
    logger.info(f"Starting RPA Worker on {host}:{port}")
    
    uvicorn.run(
        "worker:app",
        host=host,
        port=port,
        log_level=Config.LOG_LEVEL.lower(),
        access_log=True
    )
