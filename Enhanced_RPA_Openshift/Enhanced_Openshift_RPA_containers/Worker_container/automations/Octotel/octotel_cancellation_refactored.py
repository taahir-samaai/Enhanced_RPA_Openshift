"""
Octotel Cancellation Module - Browser Service Version
=====================================================
Refactored to use browser service instead of Selenium.
Follows validation execution pattern at the end.
"""

import os
import time
import logging
import traceback
import json
import base64
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field

from config import Config
from browser_client import BrowserServiceClient, BrowserServiceError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ==================== ENUMERATIONS ====================

class CancellationStatus(str, Enum):
    """Cancellation status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"

class SearchResult(str, Enum):
    """Search result"""
    FOUND = "found"
    NOT_FOUND = "not_found"
    ERROR = "error"

class ServiceStatus(str, Enum):
    """Service status"""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    PENDING = "pending"
    UNKNOWN = "unknown"

# ==================== DATA MODELS ====================

class CancellationRequest(BaseModel):
    """Cancellation request model"""
    job_id: str = Field(..., description="Unique job identifier")
    circuit_number: str = Field(..., description="Circuit number to cancel")
    solution_id: str = Field(..., description="Solution ID for reference")
    requested_date: Optional[str] = Field(None, description="Requested cancellation date")
    totp_code: Optional[str] = Field(None, description="Pre-generated TOTP from orchestrator")

class ScreenshotData(BaseModel):
    """Screenshot data model"""
    name: str
    timestamp: datetime
    data: str
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

class ServiceData(BaseModel):
    """Service data model"""
    bitstream_reference: str
    status: ServiceStatus
    customer_name: Optional[str] = None
    address: Optional[str] = None
    service_type: Optional[str] = None
    change_request_available: bool = False
    pending_requests_detected: bool = False

class CancellationResult(BaseModel):
    """Cancellation result model"""
    job_id: str
    circuit_number: str
    status: CancellationStatus
    message: str
    cancellation_submitted: bool = False
    release_reference: Optional[str] = None
    cancellation_timestamp: Optional[str] = None
    service_data: Optional[ServiceData] = None
    validation_results: Optional[Dict] = None
    execution_time: Optional[float] = None
    screenshots: List[ScreenshotData] = []
    details: Optional[Dict] = None

# ==================== SCREENSHOT SERVICE ====================

class ScreenshotService:
    """Screenshot service for evidence"""
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.evidence_dir = Path(Config.get_job_screenshot_dir(job_id))
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots: List[ScreenshotData] = []
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def take_screenshot(self, browser_client: BrowserServiceClient,
                             session_id: str, name: str) -> Optional[ScreenshotData]:
        """Take screenshot via browser service"""
        try:
            timestamp = datetime.now()
            screenshot_b64 = await browser_client.screenshot(session_id, full_page=True)
            
            # Save to file
            filename = f"{name}_{timestamp.strftime('%Y%m%d_%H%M%S')}.png"
            filepath = self.evidence_dir / filename
            screenshot_bytes = base64.b64decode(screenshot_b64)
            with open(filepath, 'wb') as f:
                f.write(screenshot_bytes)
            
            screenshot = ScreenshotData(
                name=name,
                timestamp=timestamp,
                data=screenshot_b64
            )
            
            self.screenshots.append(screenshot)
            self.logger.info(f"Screenshot saved: {filepath}")
            return screenshot
            
        except Exception as e:
            self.logger.error(f"Failed to take screenshot: {str(e)}")
            return None
    
    def get_all_screenshots(self) -> List[ScreenshotData]:
        """Get all screenshots"""
        return self.screenshots

# ==================== MAIN AUTOMATION CLASS ====================

class OctotelCancellationAutomation:
    """Octotel cancellation using browser service"""
    
    # Fixed values per requirements
    CANCELLATION_REASON = "Customer Service ISP"
    CANCELLATION_COMMENT = "Bot cancellation"
    
    def __init__(self, browser_client: BrowserServiceClient):
        self.browser = browser_client
        self.logger = logging.getLogger(self.__class__.__name__)
        self.screenshot_service: Optional[ScreenshotService] = None
        self.session_id: Optional[str] = None
    
    async def cancel_service(self, request: CancellationRequest) -> CancellationResult:
        """Main cancellation method"""
        start_time = time.time()
        
        try:
            logger.info(f"Starting cancellation for job {request.job_id}, circuit {request.circuit_number}")
            
            # Setup
            self.screenshot_service = ScreenshotService(request.job_id)
            self.session_id = await self.browser.create_session(int(request.job_id), headless=True)
            
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "initial_state")
            
            # Login
            await self._login(request.totp_code)
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "after_login")
            
            # Navigate to services
            await self._navigate_to_services()
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "services_page")
            
            # Search and verify
            search_result, service_data = await self._search_and_verify_service(request.circuit_number)
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "service_search")
            
            if search_result == SearchResult.ERROR:
                return self._create_error_result(request, "Service search failed")
            
            if search_result == SearchResult.NOT_FOUND:
                return self._create_not_found_result(request)
            
            # Check pending requests
            if service_data and service_data.pending_requests_detected:
                return self._create_pending_requests_result(request, service_data)
            
            # Submit cancellation
            success, release_reference = await self._submit_cancellation(request)
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "cancellation_submitted")
            
            if not success:
                return self._create_error_result(request, "Cancellation submission failed")
            
            # Validate
            validation_results = await self._validate_cancellation(request.circuit_number)
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "validation_complete")
            
            execution_time = time.time() - start_time
            
            result = CancellationResult(
                job_id=request.job_id,
                circuit_number=request.circuit_number,
                status=CancellationStatus.SUCCESS,
                message=f"Successfully submitted cancellation for {request.circuit_number}",
                cancellation_submitted=True,
                release_reference=release_reference,
                cancellation_timestamp=datetime.now().isoformat(),
                service_data=service_data,
                validation_results=validation_results,
                execution_time=execution_time,
                screenshots=self.screenshot_service.get_all_screenshots(),
                details=self._create_details_dict(True, service_data, validation_results, release_reference)
            )
            
            logger.info(f"Cancellation completed in {execution_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"Cancellation failed: {str(e)}")
            if self.screenshot_service and self.session_id:
                await self.screenshot_service.take_screenshot(self.browser, self.session_id, "error_state")
            return self._create_error_result(request, str(e))
            
        finally:
            if self.session_id:
                await self.browser.close_session(self.session_id)
    
    async def _login(self, totp_code: Optional[str]):
        """Login to Octotel"""
        try:
            logger.info("Starting Octotel login")
            await self.browser.navigate(self.session_id, Config.OCTOTEL_URL, wait_until="networkidle")
            
            # Click login
            login_selectors = ["//a[contains(text(), 'Login')]", "#loginButton"]
            for selector in login_selectors:
                try:
                    await self.browser.wait_for_selector(self.session_id, selector, timeout=10)
                    await self.browser.click(self.session_id, selector)
                    break
                except:
                    continue
            
            # Wait for form
            await self.browser.wait_for_selector(self.session_id, "#signInFormUsername", timeout=10)
            
            # Enter credentials
            await self.browser.type_text(self.session_id, "#signInFormUsername", Config.OCTOTEL_USERNAME)
            await self.browser.type_text(self.session_id, "#signInFormPassword", Config.OCTOTEL_PASSWORD)
            
            # Submit
            await self.browser.click(self.session_id, "button[name='signInSubmitButton']")
            
            # TOTP
            await self._handle_totp(totp_code)
            
            # Wait for dashboard
            await self.browser.wait_for_selector(self.session_id, "div.navbar", timeout=20)
            logger.info("Login successful")
            
        except Exception as e:
            raise BrowserServiceError(f"Login failed: {str(e)}")
    
    async def _handle_totp(self, totp_code: Optional[str]):
        """Handle TOTP authentication"""
        try:
            if not totp_code:
                import pyotp
                totp = pyotp.TOTP(Config.OCTOTEL_TOTP_SECRET)
                totp_code = totp.now()
                logger.warning("Generated TOTP locally")
            
            await self.browser.wait_for_selector(self.session_id, "#totpCodeInput", timeout=12)
            await self.browser.type_text(self.session_id, "#totpCodeInput", totp_code)
            await self.browser.click(self.session_id, "#signInButton")
            await self.browser.wait_for_timeout(self.session_id, 3000)
            
        except Exception as e:
            raise BrowserServiceError(f"TOTP failed: {str(e)}")
    
    async def _navigate_to_services(self):
        """Navigate to services page"""
        try:
            await self.browser.click(self.session_id, "div.navbar li:nth-of-type(2) > a")
            await self.browser.wait_for_timeout(self.session_id, 3000)
        except Exception as e:
            raise BrowserServiceError(f"Navigation failed: {str(e)}")
    
    async def _search_and_verify_service(self, circuit_number: str) -> tuple[SearchResult, Optional[ServiceData]]:
        """Search and verify service"""
        try:
            # Configure filters
            await self._configure_filters()
            
            # Search
            await self.browser.type_text(self.session_id, "#search", circuit_number, clear=True)
            
            # Click search button
            search_button_selectors = [
                "//div[@class='app-body']//a[contains(text(), 'Search')]",
                "//button[contains(text(), 'Search')]"
            ]
            for selector in search_button_selectors:
                try:
                    await self.browser.click(self.session_id, selector)
                    break
                except:
                    continue
            
            await self.browser.wait_for_timeout(self.session_id, 5000)
            
            # Check if found
            page_text = await self.browser.get_page_content(self.session_id)
            if circuit_number.lower() not in page_text.lower():
                return SearchResult.NOT_FOUND, None
            
            # Click service row
            await self.browser.click(self.session_id, f"//tr[contains(., '{circuit_number}')]")
            await self.browser.wait_for_timeout(self.session_id, 3000)
            
            # Check change request availability
            change_request_available = await self._check_change_request_button()
            
            service_data = ServiceData(
                bitstream_reference=circuit_number,
                status=ServiceStatus.ACTIVE if change_request_available else ServiceStatus.PENDING,
                change_request_available=change_request_available,
                pending_requests_detected=not change_request_available
            )
            
            return SearchResult.FOUND, service_data
            
        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
            return SearchResult.ERROR, None
    
    async def _configure_filters(self):
        """Configure status filters"""
        try:
            await self.browser.execute_script(
                self.session_id,
                """
                let selects = document.querySelectorAll('select');
                if (selects[0]) selects[0].value = '';
                if (selects[2]) selects[2].value = '1';
                """
            )
            await self.browser.wait_for_timeout(self.session_id, 1000)
        except:
            pass
    
    async def _check_change_request_button(self) -> bool:
        """Check if change request button available"""
        try:
            return await self.browser.is_visible(self.session_id, "createchangerequest > a", timeout=3)
        except:
            return False
    
    async def _submit_cancellation(self, request: CancellationRequest) -> tuple[bool, Optional[str]]:
        """Submit cancellation"""
        try:
            # Click change request
            if not await self._click_change_request():
                return False, None
            
            await self.browser.wait_for_timeout(self.session_id, 3000)
            
            # Set type to cancellation
            await self._set_cancellation_type()
            
            # Set reason
            await self._set_cancellation_reason()
            
            # Set date
            await self._set_cancellation_date(request.requested_date)
            
            # Set comments
            await self._set_comments(request.solution_id)
            
            # Submit
            if not await self._submit_form():
                return False, None
            
            await self.browser.wait_for_timeout(self.session_id, 5000)
            
            # Extract reference
            release_reference = await self._extract_release_reference()
            if not release_reference:
                release_reference = f"AUTO_CR_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            return True, release_reference
            
        except Exception as e:
            logger.error(f"Cancellation submission failed: {str(e)}")
            return False, None
    
    async def _click_change_request(self) -> bool:
        """Click change request button"""
        try:
            await self.browser.click(self.session_id, "createchangerequest > a")
            return True
        except:
            return False
    
    async def _set_cancellation_type(self):
        """Set type to cancellation"""
        try:
            await self.browser.execute_script(
                self.session_id,
                "document.querySelector('form > div:nth-of-type(1) select').value = '1';"
            )
            await self.browser.wait_for_timeout(self.session_id, 1000)
        except Exception as e:
            logger.warning(f"Could not set type: {str(e)}")
    
    async def _set_cancellation_reason(self):
        """Set cancellation reason"""
        try:
            await self.browser.execute_script(
                self.session_id,
                "document.getElementById('reason_ddl').value = '2';"
            )
            await self.browser.wait_for_timeout(self.session_id, 1000)
        except Exception as e:
            logger.warning(f"Could not set reason: {str(e)}")
    
    async def _set_cancellation_date(self, requested_date: Optional[str]):
        """Set cancellation date"""
        try:
            if requested_date:
                date_str = requested_date
            else:
                future_date = datetime.now() + timedelta(days=30)
                date_str = future_date.strftime("%d/%m/%Y")
            
            # Find date input
            date_inputs = await self.browser.query_all(self.session_id, "input[type='text']")
            if date_inputs:
                # Use first visible text input
                await self.browser.type_text(self.session_id, "input[type='text']", date_str, clear=True)
                logger.info(f"Set date: {date_str}")
        except Exception as e:
            logger.warning(f"Could not set date: {str(e)}")
    
    async def _set_comments(self, solution_id: str):
        """Set comments"""
        try:
            comment = f"{self.CANCELLATION_COMMENT}. Reference: {solution_id}"
            await self.browser.type_text(self.session_id, "textarea", comment, clear=True)
        except Exception as e:
            logger.warning(f"Could not set comments: {str(e)}")
    
    async def _submit_form(self) -> bool:
        """Submit form"""
        try:
            submit_selectors = [
                "div.modal-footer > button",
                "//button[contains(text(), 'Submit')]",
                "button[type='submit']"
            ]
            
            for selector in submit_selectors:
                try:
                    await self.browser.click(self.session_id, selector)
                    return True
                except:
                    continue
            
            return False
        except:
            return False
    
    async def _extract_release_reference(self) -> Optional[str]:
        """Extract release reference"""
        try:
            page_source = await self.browser.get_page_content(self.session_id)
            patterns = [r'(CR[\-_]?\d{6,})', r'(CHG[\-_]?\d{6,})', r'([A-Z]{2,3}\d{6,})']
            for pattern in patterns:
                matches = re.findall(pattern, page_source, re.IGNORECASE)
                if matches:
                    return matches[0].strip()
            return None
        except:
            return None
    
    async def _validate_cancellation(self, circuit_number: str) -> Dict[str, Any]:
        """Validate cancellation submission"""
        try:
            await self.browser.wait_for_timeout(self.session_id, 3000)
            page_source = await self.browser.get_page_content(self.session_id)
            
            success_indicators = ["request submitted", "cancellation submitted", "successfully submitted"]
            
            for indicator in success_indicators:
                if indicator in page_source.lower():
                    return {
                        "validation_timestamp": datetime.now().isoformat(),
                        "validation_status": "complete",
                        "cancellation_confirmed": True,
                        "success_indicator": indicator
                    }
            
            return {
                "validation_timestamp": datetime.now().isoformat(),
                "validation_status": "complete",
                "cancellation_confirmed": False
            }
        except Exception as e:
            return {"error": str(e), "cancellation_confirmed": False}
    
    def _create_details_dict(self, submitted: bool, service_data: Optional[ServiceData],
                            validation: Dict, reference: Optional[str]) -> Dict:
        """Create details dictionary"""
        details = {
            "cancellation_submitted": submitted,
            "release_reference": reference,
            "found": service_data is not None,
            "cancellation_reason": self.CANCELLATION_REASON,
            "cancellation_comment": self.CANCELLATION_COMMENT
        }
        
        if service_data:
            details.update({
                "circuit_number": service_data.bitstream_reference,
                "service_status": service_data.status.value,
                "change_request_available": service_data.change_request_available,
                "pending_requests_detected": service_data.pending_requests_detected
            })
        
        if validation:
            details.update(validation)
        
        return details
    
    def _create_error_result(self, request: CancellationRequest, message: str) -> CancellationResult:
        """Create error result"""
        return CancellationResult(
            job_id=request.job_id,
            circuit_number=request.circuit_number,
            status=CancellationStatus.ERROR,
            message=message,
            cancellation_submitted=False,
            screenshots=self.screenshot_service.get_all_screenshots() if self.screenshot_service else [],
            details={"found": False, "error": message}
        )
    
    def _create_not_found_result(self, request: CancellationRequest) -> CancellationResult:
        """Create not found result"""
        return CancellationResult(
            job_id=request.job_id,
            circuit_number=request.circuit_number,
            status=CancellationStatus.SUCCESS,
            message=f"Service {request.circuit_number} not found",
            cancellation_submitted=False,
            screenshots=self.screenshot_service.get_all_screenshots() if self.screenshot_service else [],
            details={"found": False}
        )
    
    def _create_pending_requests_result(self, request: CancellationRequest,
                                       service_data: ServiceData) -> CancellationResult:
        """Create pending requests result"""
        return CancellationResult(
            job_id=request.job_id,
            circuit_number=request.circuit_number,
            status=CancellationStatus.FAILURE,
            message=f"Cannot cancel {request.circuit_number} - pending requests detected",
            cancellation_submitted=False,
            service_data=service_data,
            screenshots=self.screenshot_service.get_all_screenshots() if self.screenshot_service else [],
            details={"found": True, "pending_requests_detected": True}
        )

# ==================== EXECUTE FUNCTION ====================

async def execute(parameters: Dict[str, Any], browser_client: BrowserServiceClient) -> Dict[str, Any]:
    """
    Execute Octotel cancellation with post-validation
    """
    job_id = parameters.get("job_id")
    circuit_number = parameters.get("circuit_number")
    solution_id = parameters.get("solution_id")
    
    results = {
        "status": "failure",
        "message": "",
        "screenshot_data": [],
        "details": {}
    }
    
    try:
        if not all([job_id, circuit_number, solution_id]):
            return {
                "status": "error",
                "message": "Missing required parameters",
                "details": {"error": "job_id, circuit_number, and solution_id required"},
                "screenshot_data": []
            }
        
        request = CancellationRequest(
            job_id=job_id,
            circuit_number=circuit_number,
            solution_id=solution_id,
            requested_date=parameters.get("requested_date"),
            totp_code=parameters.get("totp_code")
        )
        
        automation = OctotelCancellationAutomation(browser_client)
        result = await automation.cancel_service(request)
        
        results = {
            "status": "success" if result.status == CancellationStatus.SUCCESS else "failure",
            "message": result.message,
            "details": {
                "found": result.status == CancellationStatus.SUCCESS,
                "cancellation_submitted": result.cancellation_submitted,
                "release_reference": result.release_reference,
                "service_found": result.service_data is not None,
                "is_active": result.service_data.status != ServiceStatus.CANCELLED if result.service_data else False,
                **(result.details or {})
            },
            "screenshot_data": [
                {"name": s.name, "timestamp": s.timestamp.isoformat(), "base64_data": s.data}
                for s in result.screenshots
            ]
        }
        
    except Exception as e:
        logger.error(f"Execute failed: {str(e)}")
        results = {
            "status": "error",
            "message": str(e),
            "details": {"error": str(e)},
            "screenshot_data": []
        }
    
    finally:
        # Execute validation for complete data
        await _execute_validation_followup(job_id, circuit_number, browser_client, results)
    
    return results


async def _execute_validation_followup(job_id: str, circuit_number: str,
                                       browser_client: BrowserServiceClient,
                                       results: Dict):
    """Execute validation after cancellation"""
    try:
        logger.info(f"Job {job_id}: Fetching updated data via validation")
        
        from providers.octotel.validation import execute as validation_execute
        
        validation_result = await validation_execute(
            {"job_id": job_id, "circuit_number": circuit_number, "totp_code": None},
            browser_client
        )
        
        if "details" in validation_result and validation_result["details"]:
            results["details"] = validation_result["details"]
            logger.info(f"Job {job_id}: Replaced with validation data")
            
            if "screenshot_data" in validation_result:
                existing = results.get("screenshot_data", [])
                results["screenshot_data"] = existing + validation_result["screenshot_data"]
                
    except Exception as e:
        logger.error(f"Validation followup failed: {str(e)}")
        results["details"]["validation_error"] = str(e)
