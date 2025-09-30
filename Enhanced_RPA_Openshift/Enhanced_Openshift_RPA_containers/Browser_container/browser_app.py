"""
Browser Service - FastAPI Application
-------------------------------------
Main FastAPI application for browser automation service.
"""
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from config import Config
from managers.browser_manager import BrowserManager
from middleware.auth import verify_service_token, auth_service
from models.requests import (
    CreateSessionRequest, NavigateRequest, ClickRequest, FillRequest,
    TOTPRequest, GetTextRequest, GetAttributeRequest, WaitForSelectorRequest,
    ScreenshotRequest, EvaluateRequest, SessionResponse, OperationResponse,
    TextResponse, AttributeResponse, SessionInfoResponse, HealthResponse,
    ErrorResponse
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format=Config.LOG_FORMAT
)
logger = logging.getLogger(__name__)

# Global state
start_time = time.time()
browser_manager: BrowserManager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    global browser_manager
    
    # Startup
    logger.info("=" * 60)
    logger.info(f"Starting {Config.SERVICE_NAME}")
    logger.info("=" * 60)
    
    # Validate configuration
    try:
        Config.validate()
        logger.info("Configuration validated successfully")
    except ValueError as e:
        logger.error(f"Configuration validation failed: {e}")
        raise
    
    # Initialize browser manager
    try:
        browser_manager = BrowserManager()
        await browser_manager.initialize(
            browser_type='firefox',  # Fixed: Only Firefox is used
            **Config.get_browser_launch_options()
        )
        logger.info("Browser manager initialized with Firefox (incognito mode)")
    except Exception as e:
        logger.error(f"Failed to initialize browser manager: {e}")
        raise
    
    logger.info(f"{Config.SERVICE_NAME} started successfully on {Config.HOST}:{Config.PORT}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down browser service...")
    
    if browser_manager:
        await browser_manager.cleanup()
        logger.info("Browser manager cleaned up")
    
    logger.info("Browser service shutdown complete")


# Initialize FastAPI app
app = FastAPI(
    title="RPA Browser Service",
    description="Browser automation service using Playwright with Factory pattern",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal server error",
            detail=str(exc),
            error_type=type(exc).__name__
        ).dict()
    )


# Health Check Endpoints (No Auth Required - For OpenShift Probes)
@app.get("/health/ready", response_model=HealthResponse)
async def health_ready():
    """
    Readiness probe endpoint for OpenShift.
    Returns 200 when service is ready to accept requests.
    """
    if not browser_manager or not browser_manager.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Browser service not ready"
        )
    
    session_info = await browser_manager.get_session_info()
    
    return HealthResponse(
        status="ready",
        browser_ready=True,
        active_sessions=session_info['active_sessions'],
        uptime_seconds=time.time() - start_time
    )


@app.get("/health/live", response_model=HealthResponse)
async def health_live():
    """
    Liveness probe endpoint for OpenShift.
    Returns 200 if service is alive (even if not ready).
    """
    return HealthResponse(
        status="alive",
        browser_ready=browser_manager.is_ready() if browser_manager else False,
        active_sessions=0,
        uptime_seconds=time.time() - start_time
    )


@app.get("/health/browser", response_model=HealthResponse)
async def health_browser(token: dict = Depends(verify_service_token)):
    """
    Business logic health check.
    Tests actual browser functionality.
    """
    if not browser_manager or not browser_manager.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Browser not initialized"
        )
    
    try:
        # Test browser functionality
        session_info = await browser_manager.get_session_info()
        
        return HealthResponse(
            status="healthy",
            browser_ready=True,
            active_sessions=session_info['active_sessions'],
            uptime_seconds=time.time() - start_time
        )
    except Exception as e:
        logger.error(f"Browser health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Browser health check failed: {str(e)}"
        )


# Session Management Endpoints
@app.post("/browser/session/create", response_model=SessionResponse)
async def create_session(
    request: CreateSessionRequest,
    token: dict = Depends(verify_service_token)
):
    """
    Create a new browser session.
    Note: This service only uses Firefox in incognito mode.
    """
    try:
        # Always use incognito session type (privacy/isolation)
        session_id = await browser_manager.create_session(
            session_type='incognito',  # Fixed: Always incognito for privacy
            viewport={'width': request.viewport_width, 'height': request.viewport_height}
        )
        
        logger.info(f"Created incognito session {session_id} for {token.get('sub')}")
        
        return SessionResponse(
            session_id=session_id,
            session_type='incognito',  # Always incognito
            status="created",
            message="Browser session created successfully (Firefox incognito)"
        )
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}"
        )


@app.delete("/browser/session/close", response_model=OperationResponse)
async def close_session(token: dict = Depends(verify_service_token)):
    """
    Close the current browser session.
    """
    try:
        await browser_manager.close_session()
        
        logger.info(f"Closed session for {token.get('sub')}")
        
        return OperationResponse(
            status="success",
            message="Session closed successfully"
        )
    except Exception as e:
        logger.error(f"Failed to close session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to close session: {str(e)}"
        )


@app.get("/browser/session/info", response_model=SessionInfoResponse)
async def get_session_info(token: dict = Depends(verify_service_token)):
    """
    Get information about active sessions.
    """
    session_info = await browser_manager.get_session_info()
    return SessionInfoResponse(**session_info)


# Browser Navigation Endpoints
@app.post("/browser/navigate", response_model=OperationResponse)
async def navigate(
    request: NavigateRequest,
    token: dict = Depends(verify_service_token)
):
    """
    Navigate to a URL.
    """
    try:
        await browser_manager.navigate(
            url=request.url,
            wait_until=request.wait_until.value,
            timeout=request.timeout
        )
        
        return OperationResponse(
            status="success",
            message=f"Navigated to {request.url}",
            details={"url": request.url}
        )
    except Exception as e:
        logger.error(f"Navigation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Navigation failed: {str(e)}"
        )


# Browser Interaction Endpoints
@app.post("/browser/click", response_model=OperationResponse)
async def click(
    request: ClickRequest,
    token: dict = Depends(verify_service_token)
):
    """
    Click an element.
    """
    try:
        await browser_manager.click(
            selector=request.selector,
            timeout=request.timeout,
            force=request.force
        )
        
        return OperationResponse(
            status="success",
            message=f"Clicked element: {request.selector}",
            details={"selector": request.selector}
        )
    except Exception as e:
        logger.error(f"Click failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Click failed: {str(e)}"
        )


@app.post("/browser/fill", response_model=OperationResponse)
async def fill(
    request: FillRequest,
    token: dict = Depends(verify_service_token)
):
    """
    Fill an input field.
    """
    try:
        await browser_manager.fill(
            selector=request.selector,
            value=request.value,
            timeout=request.timeout
        )
        
        return OperationResponse(
            status="success",
            message=f"Filled element: {request.selector}",
            details={"selector": request.selector}
        )
    except Exception as e:
        logger.error(f"Fill failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fill failed: {str(e)}"
        )


@app.post("/browser/submit_totp", response_model=OperationResponse)
async def submit_totp(
    request: TOTPRequest,
    token: dict = Depends(verify_service_token)
):
    """
    Submit TOTP code (pre-generated by orchestrator).
    """
    try:
        await browser_manager.fill(
            selector=request.selector,
            value=request.code,
            timeout=30000
        )
        
        if request.submit:
            await browser_manager.press_key("Enter")
        
        logger.info(f"TOTP submitted for {token.get('sub')}")
        
        return OperationResponse(
            status="success",
            message="TOTP code submitted successfully",
            details={"selector": request.selector}
        )
    except Exception as e:
        logger.error(f"TOTP submission failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TOTP submission failed: {str(e)}"
        )


# Data Extraction Endpoints
@app.get("/browser/text", response_model=TextResponse)
async def get_text(
    selector: str,
    timeout: int = 30000,
    token: dict = Depends(verify_service_token)
):
    """
    Get text content from an element.
    """
    try:
        text = await browser_manager.get_text(selector=selector, timeout=timeout)
        
        return TextResponse(
            text=text,
            selector=selector
        )
    except Exception as e:
        logger.error(f"Get text failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get text: {str(e)}"
        )


@app.get("/browser/attribute", response_model=AttributeResponse)
async def get_attribute(
    selector: str,
    attribute: str,
    timeout: int = 30000,
    token: dict = Depends(verify_service_token)
):
    """
    Get attribute value from an element.
    """
    try:
        value = await browser_manager.get_attribute(
            selector=selector,
            attribute=attribute,
            timeout=timeout
        )
        
        return AttributeResponse(
            attribute=attribute,
            value=value,
            selector=selector
        )
    except Exception as e:
        logger.error(f"Get attribute failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get attribute: {str(e)}"
        )


# Screenshot Endpoint
@app.post("/browser/screenshot")
async def screenshot(
    request: ScreenshotRequest,
    token: dict = Depends(verify_service_token)
):
    """
    Capture screenshot.
    Returns PNG image bytes.
    """
    try:
        image_bytes = await browser_manager.screenshot(full_page=request.full_page)
        
        logger.info(f"Screenshot captured for {token.get('sub')}")
        
        return Response(
            content=image_bytes,
            media_type="image/png"
        )
    except Exception as e:
        logger.error(f"Screenshot failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Screenshot failed: {str(e)}"
        )


# Wait Operations
@app.post("/browser/wait_for_selector", response_model=OperationResponse)
async def wait_for_selector(
    request: WaitForSelectorRequest,
    token: dict = Depends(verify_service_token)
):
    """
    Wait for element to reach specific state.
    """
    try:
        await browser_manager.wait_for_selector(
            selector=request.selector,
            state=request.state.value,
            timeout=request.timeout
        )
        
        return OperationResponse(
            status="success",
            message=f"Element {request.selector} reached state: {request.state.value}",
            details={"selector": request.selector, "state": request.state.value}
        )
    except Exception as e:
        logger.error(f"Wait for selector failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Wait for selector failed: {str(e)}"
        )


# JavaScript Evaluation
@app.post("/browser/evaluate", response_model=OperationResponse)
async def evaluate(
    request: EvaluateRequest,
    token: dict = Depends(verify_service_token)
):
    """
    Execute JavaScript in page context.
    """
    try:
        result = await browser_manager.evaluate(request.expression)
        
        return OperationResponse(
            status="success",
            message="JavaScript executed successfully",
            details={"result": result}
        )
    except Exception as e:
        logger.error(f"JavaScript evaluation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"JavaScript evaluation failed: {str(e)}"
        )


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": Config.SERVICE_NAME,
        "version": "1.0.0",
        "status": "running",
        "browser_type": Config.BROWSER_TYPE,
        "uptime_seconds": time.time() - start_time
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host=Config.HOST,
        port=Config.PORT,
        log_level=Config.LOG_LEVEL.lower()
    )
