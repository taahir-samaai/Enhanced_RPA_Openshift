"""
Openserve Cancellation Automation - Browser Service Version
===========================================================
Refactored from OSN with strategy pattern, Forcepoint bypass, and validation followup.
"""

import os
import time
import logging
import traceback
import json
import base64
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from config import Config
from browser_client import BrowserServiceClient, BrowserServiceError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== ENUMERATIONS ====================

class CancellationStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"
    ALREADY_CANCELLED = "already_cancelled"

class CancellationResultType(str, Enum):
    SUBMITTED = "submitted"
    ALREADY_DEACTIVATED = "already_deactivated"
    NOT_FOUND = "not_found"
    ERROR = "error"

# ==================== DATA MODELS ====================

class CancellationRequest(BaseModel):
    job_id: str
    circuit_number: str
    solution_id: str
    requested_date: Optional[str] = None

class ScreenshotData(BaseModel):
    name: str
    timestamp: datetime
    data: str
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

class CancellationDetails(BaseModel):
    order_number: Optional[str] = None
    external_reference: str
    requested_date: Optional[str] = None
    submission_date: datetime
    status: str
    confirmation_received: bool = False

class CancellationResult(BaseModel):
    job_id: str
    circuit_number: str
    status: CancellationStatus
    message: str
    result_type: CancellationResultType
    cancellation_details: Optional[CancellationDetails] = None
    execution_time: Optional[float] = None
    screenshots: List[ScreenshotData] = []
    error_details: Optional[Dict[str, Any]] = None

# ==================== SCREENSHOT SERVICE ====================

class ScreenshotService:
    """Screenshot service"""
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.screenshot_dir = Path(Config.get_job_screenshot_dir(job_id))
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots: List[ScreenshotData] = []
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def take_screenshot(self, browser_client: BrowserServiceClient,
                             session_id: str, name: str) -> Optional[ScreenshotData]:
        """Take screenshot"""
        try:
            timestamp = datetime.now()
            screenshot_b64 = await browser_client.screenshot(session_id, full_page=True)
            
            filename = f"{name}_{timestamp.strftime('%Y%m%d_%H%M%S')}.png"
            filepath = self.screenshot_dir / filename
            screenshot_bytes = base64.b64decode(screenshot_b64)
            with open(filepath, 'wb') as f:
                f.write(screenshot_bytes)
            
            screenshot = ScreenshotData(name=name, timestamp=timestamp, data=screenshot_b64)
            self.screenshots.append(screenshot)
            return screenshot
        except Exception as e:
            self.logger.error(f"Screenshot failed: {str(e)}")
            return None
    
    def get_all_screenshots(self) -> List[ScreenshotData]:
        return self.screenshots

# ==================== STRATEGY INTERFACES ====================

class IErrorDetectionStrategy(ABC):
    """Error detection strategy"""
    @abstractmethod
    async def has_error(self, browser: BrowserServiceClient, session_id: str) -> bool:
        pass

class IAccessDeniedDetectionStrategy(ABC):
    """Access denied detection strategy"""
    @abstractmethod
    async def is_access_denied(self, browser: BrowserServiceClient, session_id: str) -> bool:
        pass

class IFormInteractionStrategy(ABC):
    """Form interaction strategy"""
    @abstractmethod
    async def fill_external_reference(self, browser: BrowserServiceClient, session_id: str, ref: str) -> bool:
        pass
    
    @abstractmethod
    async def fill_cancellation_date(self, browser: BrowserServiceClient, session_id: str, date: str) -> bool:
        pass
    
    @abstractmethod
    async def submit_cancellation(self, browser: BrowserServiceClient, session_id: str) -> bool:
        pass

class IConfirmationStrategy(ABC):
    """Confirmation strategy"""
    @abstractmethod
    async def handle_confirmation_dialog(self, browser: BrowserServiceClient, session_id: str) -> bool:
        pass
    
    @abstractmethod
    async def extract_order_number(self, browser: BrowserServiceClient, session_id: str) -> Optional[str]:
        pass

# ==================== STRATEGY IMPLEMENTATIONS ====================

class StandardErrorDetectionStrategy(IErrorDetectionStrategy):
    """Standard error detection"""
    
    async def has_error(self, browser: BrowserServiceClient, session_id: str) -> bool:
        try:
            selectors = [
                "//div[contains(@class, 'error')]",
                "//div[contains(@class, 'alert-danger')]",
                "//div[contains(@class, 'p-message-error')]"
            ]
            for selector in selectors:
                if await browser.is_visible(session_id, selector, timeout=2):
                    return True
            return False
        except:
            return False

class OpenserveAccessDeniedDetectionStrategy(IAccessDeniedDetectionStrategy):
    """Openserve access denied detection"""
    
    async def is_access_denied(self, browser: BrowserServiceClient, session_id: str) -> bool:
        try:
            url = await browser.get_current_url(session_id)
            if "error/access-denied" in url:
                return True
            
            selectors = [
                "//h1[contains(text(), 'Access Denied')]",
                "//div[contains(text(), 'Access denied')]"
            ]
            for selector in selectors:
                if await browser.is_visible(session_id, selector, timeout=2):
                    return True
            return False
        except:
            return False

class RobustFormInteractionStrategy(IFormInteractionStrategy):
    """Robust form interaction"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def fill_external_reference(self, browser: BrowserServiceClient, session_id: str, ref: str) -> bool:
        """Fill external reference"""
        selectors = [
            "//input[@formcontrolname='reference']",
            "input[formcontrolname='reference']",
            "#externalReference"
        ]
        
        for selector in selectors:
            try:
                await browser.type_text(session_id, selector, ref, clear=True)
                self.logger.info(f"Filled external reference: {ref}")
                return True
            except:
                continue
        
        return False
    
    async def fill_cancellation_date(self, browser: BrowserServiceClient, session_id: str, date_str: str) -> bool:
        """Fill cancellation date"""
        if not date_str:
            return True
        
        selectors = [
            "p-calendar input",
            "input[formcontrolname='ceaseDate']",
            ".p-calendar input"
        ]
        
        for selector in selectors:
            try:
                # Format date
                formatted = self._format_date(date_str)
                await browser.type_text(session_id, selector, formatted, clear=True)
                await browser.press_key(session_id, "Tab")
                await browser.wait_for_timeout(session_id, 1000)
                self.logger.info(f"Filled date: {formatted}")
                return True
            except:
                continue
        
        return True  # Not critical
    
    async def submit_cancellation(self, browser: BrowserServiceClient, session_id: str) -> bool:
        """Submit form"""
        selectors = [
            "//button[contains(@class, 'p-button') and .//span[text()='Submit']]",
            "//button[contains(text(), 'Submit')]",
            "button[type='submit']"
        ]
        
        for selector in selectors:
            try:
                await browser.click(session_id, selector)
                self.logger.info("Submitted form")
                return True
            except:
                continue
        
        return False
    
    def _format_date(self, date_str: str) -> str:
        """Format date for input"""
        if "/" in date_str:
            parts = date_str.split("/")
            if len(parts) == 3:
                day, month, year = parts
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        return date_str

class OpenserveConfirmationStrategy(IConfirmationStrategy):
    """Openserve confirmation handling"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def handle_confirmation_dialog(self, browser: BrowserServiceClient, session_id: str) -> bool:
        """Handle confirmation dialog"""
        try:
            # Wait for dialog
            await browser.wait_for_selector(session_id, "//div[contains(@class, 'p-dialog')]", timeout=10)
            self.logger.info("Dialog appeared")
            
            # Click continue
            selectors = [
                "//button[@id='ceaseActiveServiceOrderSubmit']",
                "//button[.//span[text()='Continue']]",
                "//button[contains(text(), 'Continue')]"
            ]
            
            for selector in selectors:
                try:
                    await browser.click(session_id, selector)
                    self.logger.info("Clicked Continue")
                    return True
                except:
                    continue
            
            return False
        except Exception as e:
            self.logger.error(f"Dialog handling failed: {str(e)}")
            return False
    
    async def extract_order_number(self, browser: BrowserServiceClient, session_id: str) -> Optional[str]:
        """Extract order number"""
        try:
            await browser.wait_for_selector(
                session_id,
                "//h1[contains(text(), 'submitted successfully')]",
                timeout=10
            )
            
            # Extract order number
            page_text = await browser.get_page_content(session_id)
            
            import re
            match = re.search(r'Order number[:\s]+#?(\d+)', page_text)
            if match:
                order_number = match.group(1)
                self.logger.info(f"Extracted order: {order_number}")
                return order_number
            
            return None
        except:
            return None

# ==================== PAGE OBJECTS ====================

class LoginPage:
    """Login page with Forcepoint bypass"""
    
    def __init__(self, browser: BrowserServiceClient, session_id: str):
        self.browser = browser
        self.session_id = session_id
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def login(self, email: str, password: str):
        """Login with bypass"""
        try:
            # Navigate with bypass
            await self.browser.navigate(self.session_id, "https://partners.openserve.co.za/login")
            await self.browser.wait_for_timeout(self.session_id, 3000)
            
            # Handle Forcepoint
            page_source = await self.browser.get_page_content(self.session_id)
            if "Certificate verification error" in page_source:
                self.logger.info("Handling Forcepoint bypass")
                try:
                    await self.browser.click(self.session_id, "//input[@value='   Visit Site anyway   ']")
                except:
                    await self.browser.execute_script(self.session_id, "document.forms['ask'].submit();")
                await self.browser.wait_for_timeout(self.session_id, 3000)
            
            # Wait for login page
            await self.browser.wait_for_timeout(self.session_id, 5000)
            await self.browser.wait_for_selector(self.session_id, "#email", timeout=30)
            
            # Enter credentials
            await self.browser.type_text(self.session_id, "#email", email, clear=True)
            await self.browser.type_text(self.session_id, "#password", password, clear=True)
            
            # Submit
            await self.browser.click(self.session_id, "#next")
            
            # Wait for dashboard
            await self.browser.wait_for_selector(self.session_id, "#navOrders", timeout=30)
            self.logger.info("Login successful")
            
        except Exception as e:
            raise BrowserServiceError(f"Login failed: {str(e)}")

class CancellationPage:
    """Cancellation page object"""
    
    def __init__(self, browser: BrowserServiceClient, session_id: str,
                 form_strategy: IFormInteractionStrategy,
                 confirmation_strategy: IConfirmationStrategy):
        self.browser = browser
        self.session_id = session_id
        self.form_strategy = form_strategy
        self.confirmation_strategy = confirmation_strategy
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def navigate_to_cancellation(self, circuit_number: str) -> bool:
        """Navigate to cancellation page"""
        try:
            url = f"https://partners.openserve.co.za/active-services/{circuit_number}/cease-service"
            await self.browser.navigate(self.session_id, url)
            await self.browser.wait_for_timeout(self.session_id, 3000)
            
            # Check for heading
            try:
                await self.browser.wait_for_selector(
                    self.session_id,
                    "//h2[contains(text(), 'Cease active service')]",
                    timeout=10
                )
                self.logger.info("Cancellation page loaded")
                return True
            except:
                return False
        except Exception as e:
            self.logger.error(f"Navigation failed: {str(e)}")
            return False
    
    async def submit_cancellation_request(self, solution_id: str,
                                         requested_date: Optional[str] = None) -> tuple[bool, Optional[str]]:
        """Submit cancellation request"""
        try:
            await self.browser.wait_for_timeout(self.session_id, 2000)
            
            # Fill reference
            if not await self.form_strategy.fill_external_reference(self.browser, self.session_id, solution_id):
                raise Exception("Failed to fill reference")
            
            # Fill date if provided
            if requested_date:
                await self.form_strategy.fill_cancellation_date(self.browser, self.session_id, requested_date)
            
            await self.browser.wait_for_timeout(self.session_id, 2000)
            
            # Submit
            if not await self.form_strategy.submit_cancellation(self.browser, self.session_id):
                raise Exception("Failed to submit")
            
            # Handle confirmation
            if not await self.confirmation_strategy.handle_confirmation_dialog(self.browser, self.session_id):
                raise Exception("Failed to confirm")
            
            # Extract order number
            order_number = await self.confirmation_strategy.extract_order_number(self.browser, self.session_id)
            
            self.logger.info("Cancellation submitted")
            return True, order_number
            
        except Exception as e:
            self.logger.error(f"Submission failed: {str(e)}")
            return False, None

# ==================== MAIN AUTOMATION ====================

class OpenserveCancellationAutomation:
    """Main Openserve cancellation automation"""
    
    def __init__(self, browser_client: BrowserServiceClient, config: Config,
                 error_strategy: IErrorDetectionStrategy,
                 access_strategy: IAccessDeniedDetectionStrategy,
                 form_strategy: IFormInteractionStrategy,
                 confirmation_strategy: IConfirmationStrategy):
        self.browser = browser_client
        self.config = config
        self.error_strategy = error_strategy
        self.access_strategy = access_strategy
        self.form_strategy = form_strategy
        self.confirmation_strategy = confirmation_strategy
        self.logger = logging.getLogger(self.__class__.__name__)
        self.screenshot_service: Optional[ScreenshotService] = None
        self.session_id: Optional[str] = None
    
    async def cancel_service(self, request: CancellationRequest) -> CancellationResult:
        """Main cancellation method"""
        start_time = time.time()
        
        try:
            logger.info(f"Starting cancellation for {request.circuit_number}")
            
            # Setup
            self.screenshot_service = ScreenshotService(request.job_id)
            self.session_id = await self.browser.create_session(int(request.job_id), headless=True)
            
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "initial")
            
            # Login
            login_page = LoginPage(self.browser, self.session_id)
            await login_page.login(Config.OSEMAIL, Config.OSPASSWORD)
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "after_login")
            
            # Navigate to cancellation
            cancellation_page = CancellationPage(
                self.browser,
                self.session_id,
                self.form_strategy,
                self.confirmation_strategy
            )
            
            if not await cancellation_page.navigate_to_cancellation(request.circuit_number):
                # Check if access denied (already cancelled)
                if await self.access_strategy.is_access_denied(self.browser, self.session_id):
                    await self.screenshot_service.take_screenshot(self.browser, self.session_id, "access_denied")
                    return self._create_already_cancelled_result(request)
                else:
                    return self._create_error_result(request, "Failed to navigate to cancellation page")
            
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "cancellation_page")
            
            # Check errors
            if await self.error_strategy.has_error(self.browser, self.session_id):
                await self.screenshot_service.take_screenshot(self.browser, self.session_id, "error_detected")
                return self._create_error_result(request, "Error on cancellation page")
            
            # Submit
            success, order_number = await cancellation_page.submit_cancellation_request(
                request.solution_id,
                request.requested_date
            )
            
            if success:
                await self.screenshot_service.take_screenshot(self.browser, self.session_id, "success")
                return self._create_success_result(request, order_number, start_time)
            else:
                await self.screenshot_service.take_screenshot(self.browser, self.session_id, "failed")
                return self._create_error_result(request, "Submission failed")
            
        except Exception as e:
            logger.error(f"Cancellation failed: {str(e)}")
            if self.screenshot_service and self.session_id:
                await self.screenshot_service.take_screenshot(self.browser, self.session_id, "error")
            return self._create_error_result(request, str(e))
            
        finally:
            if self.session_id:
                await self.browser.close_session(self.session_id)
    
    def _create_success_result(self, request: CancellationRequest, order_number: Optional[str], start_time: float) -> CancellationResult:
        """Create success result"""
        execution_time = time.time() - start_time
        
        details = CancellationDetails(
            order_number=order_number,
            external_reference=request.solution_id,
            requested_date=request.requested_date,
            submission_date=datetime.now(),
            status="submitted",
            confirmation_received=order_number is not None
        )
        
        return CancellationResult(
            job_id=request.job_id,
            circuit_number=request.circuit_number,
            status=CancellationStatus.SUCCESS,
            message=f"Successfully submitted cancellation for {request.circuit_number}",
            result_type=CancellationResultType.SUBMITTED,
            cancellation_details=details,
            execution_time=execution_time,
            screenshots=self.screenshot_service.get_all_screenshots() if self.screenshot_service else []
        )
    
    def _create_already_cancelled_result(self, request: CancellationRequest) -> CancellationResult:
        """Create already cancelled result"""
        return CancellationResult(
            job_id=request.job_id,
            circuit_number=request.circuit_number,
            status=CancellationStatus.ALREADY_CANCELLED,
            message=f"Service {request.circuit_number} already cancelled",
            result_type=CancellationResultType.ALREADY_DEACTIVATED,
            screenshots=self.screenshot_service.get_all_screenshots() if self.screenshot_service else []
        )
    
    def _create_error_result(self, request: CancellationRequest, error_message: str) -> CancellationResult:
        """Create error result"""
        return CancellationResult(
            job_id=request.job_id,
            circuit_number=request.circuit_number,
            status=CancellationStatus.ERROR,
            message=error_message,
            result_type=CancellationResultType.ERROR,
            screenshots=self.screenshot_service.get_all_screenshots() if self.screenshot_service else [],
            error_details={"error": error_message, "timestamp": datetime.now().isoformat()}
        )

# ==================== FACTORY ====================

class OpenserveCancellationFactory:
    """Factory for creating Openserve cancellation automation"""
    
    @staticmethod
    def create_standard_automation(browser_client: BrowserServiceClient, config: Config) -> OpenserveCancellationAutomation:
        """Create standard automation"""
        return OpenserveCancellationAutomation(
            browser_client=browser_client,
            config=config,
            error_strategy=StandardErrorDetectionStrategy(),
            access_strategy=OpenserveAccessDeniedDetectionStrategy(),
            form_strategy=RobustFormInteractionStrategy(),
            confirmation_strategy=OpenserveConfirmationStrategy()
        )

# ==================== EXECUTE FUNCTION ====================

async def execute(parameters: Dict[str, Any], browser_client: BrowserServiceClient) -> Dict[str, Any]:
    """Execute Openserve cancellation with validation followup"""
    
    job_id = parameters.get("job_id")
    circuit_number = parameters.get("circuit_number")
    solution_id = parameters.get("solution_id")
    
    results = {"status": "failure", "message": "", "screenshot_data": [], "details": {}}
    
    try:
        if not all([job_id, circuit_number, solution_id]):
            return {
                "status": "error",
                "message": "Missing required parameters",
                "details": {"error": "job_id, circuit_number, solution_id required"},
                "screenshot_data": []
            }
        
        request = CancellationRequest(
            job_id=job_id,
            circuit_number=circuit_number,
            solution_id=solution_id,
            requested_date=parameters.get("requested_date")
        )
        
        # Create automation
        automation = OpenserveCancellationFactory.create_standard_automation(browser_client, Config)
        
        # Execute
        result = await automation.cancel_service(request)
        
        # Convert to dict
        results = {
            "status": "success" if result.status == CancellationStatus.SUCCESS else "failure",
            "message": result.message,
            "details": {
                "found": result.status == CancellationStatus.SUCCESS,
                "circuit_number": result.circuit_number,
                "result_type": result.result_type.value,
                "cancellation_status": result.status.value,
                "execution_time": result.execution_time,
                "cancellation_details": result.cancellation_details.dict() if result.cancellation_details else None,
                "cancellation_submitted": result.status == CancellationStatus.SUCCESS,
                "cancellation_captured_id": result.cancellation_details.order_number if result.cancellation_details else None,
                "service_found": True,
                "is_active": result.status != CancellationStatus.ALREADY_CANCELLED
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
        await asyncio.sleep(3)
        logger.info(f"Job {job_id}: Fetching validation data")
        
        from providers.openserve.validation import execute as validation_execute
        
        validation_result = await validation_execute(
            {"job_id": job_id, "circuit_number": circuit_number},
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
