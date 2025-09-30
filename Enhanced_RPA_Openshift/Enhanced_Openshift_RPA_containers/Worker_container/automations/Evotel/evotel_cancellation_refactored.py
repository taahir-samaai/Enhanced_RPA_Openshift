"""
Evotel Cancellation Automation - Browser Service Version
=============================================================================
Refactored to use browser service with tab management and enhanced service selection
"""

import asyncio
import time
import logging
import traceback
import json
import base64
import re
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field

# Import browser client
from browser_client import BrowserServiceClient

# Import existing config
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== UTILITY FUNCTIONS ====================

async def robust_click(browser: BrowserServiceClient, session_id: str,
                      selector: str, description: str = "element") -> bool:
    """Multi-method element clicking with fallback strategies"""
    try:
        await browser.click(session_id, selector)
        logger.info(f"Successfully clicked {description}")
        return True
    except Exception as e:
        logger.debug(f"Standard click failed for {description}: {str(e)}")
        
        try:
            script = f"""
            const element = document.querySelector('{selector}');
            if (element) {{ element.click(); return true; }}
            return false;
            """
            result = await browser.execute_script(session_id, script)
            if result:
                logger.info(f"Successfully clicked {description} using JavaScript")
                return True
        except Exception as js_error:
            logger.error(f"All click methods failed for {description}: {str(js_error)}")
            return False
    
    return False

async def filter_active_service_links(browser: BrowserServiceClient,
                                     session_id: str, logger) -> List[Dict]:
    """Filter service links to only return active (non-greyed) links"""
    try:
        script = """
        const links = Array.from(document.querySelectorAll('#WebGrid tbody tr td:nth-child(3) a'));
        return links.map((link, index) => ({
            index: index,
            text: link.textContent.trim(),
            href: link.href || '',
            style: link.getAttribute('style') || '',
            color: window.getComputedStyle(link).color,
            opacity: window.getComputedStyle(link).opacity,
            selector: `#WebGrid tbody tr td:nth-child(3) a:nth-of-type(${index+1})`
        }));
        """
        
        all_links = await browser.execute_script(session_id, script)
        
        if not all_links:
            logger.warning("No service links found")
            return []
        
        active_links = []
        
        for link_info in all_links:
            # Check href validity
            href = link_info.get('href', '')
            if not href or href in ["#", "javascript:void(0)", "javascript:;"]:
                continue
            
            # Check for gray colors in style
            style = link_info.get('style', '').lower()
            gray_colors = ['#c0c0c0', '#cccccc', '#999999', '#666666', '#808080']
            if any(gray in style for gray in gray_colors):
                continue
            
            # Check computed color
            color = link_info.get('color', '')
            if color:
                rgb_match = re.search(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', color)
                if rgb_match:
                    r, g, b = map(int, rgb_match.groups())
                    if abs(r - g) < 50 and abs(g - b) < 50 and max(r, g, b) < 150:
                        continue
            
            # Check opacity
            opacity = float(link_info.get('opacity', 1))
            if opacity < 0.6:
                continue
            
            logger.info(f"Link {link_info['index']+1}: Active - '{link_info['text']}'")
            active_links.append(link_info)
        
        logger.info(f"Found {len(active_links)} active links out of {len(all_links)} total")
        return active_links
        
    except Exception as e:
        logger.error(f"Error filtering active service links: {e}")
        return []

# ==================== ENUMERATIONS ====================

class CancellationStatus(str, Enum):
    """Enumeration for cancellation status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"
    ALREADY_CANCELLED = "already_cancelled"

class CancellationResultType(str, Enum):
    """Enumeration for cancellation results"""
    SUBMITTED = "submitted"
    ALREADY_DEACTIVATED = "already_deactivated"
    NOT_FOUND = "not_found"
    ERROR = "error"

# ==================== DATA MODELS ====================

class CancellationRequest(BaseModel):
    """Request model for cancellation"""
    job_id: str
    circuit_number: str
    solution_id: Optional[str] = None
    requested_date: Optional[str] = None

class ScreenshotData(BaseModel):
    """Model for screenshot data"""
    name: str
    timestamp: datetime
    data: str
    path: str
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

class CancellationDetails(BaseModel):
    """Model for cancellation details"""
    work_order_number: Optional[str] = None
    service_uuid: Optional[str] = None
    external_reference: Optional[str] = None
    requested_date: Optional[str] = None
    submission_date: datetime
    status: str
    confirmation_received: bool = False
    work_order_updated: bool = False

class CancellationResult(BaseModel):
    """Result model for cancellation"""
    job_id: str
    circuit_number: str
    status: CancellationStatus
    message: str
    result_type: CancellationResultType
    cancellation_details: Optional[CancellationDetails] = None
    execution_time: Optional[float] = None
    screenshots: List[ScreenshotData] = []
    evidence_dir: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None

# ==================== SERVICES ====================

class ScreenshotService:
    """Service for managing screenshots and evidence"""
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.evidence_dir = Path(Config.get_job_screenshot_dir(job_id))
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots: List[ScreenshotData] = []
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def take_screenshot(self, browser: BrowserServiceClient,
                            session_id: str, name: str) -> Optional[ScreenshotData]:
        """Take screenshot and save with metadata"""
        try:
            timestamp = datetime.now()
            filename = f"{name}_{timestamp.strftime('%Y%m%d_%H%M%S')}.png"
            filepath = self.evidence_dir / filename
            
            # Get screenshot from browser service
            screenshot_b64 = await browser.screenshot(session_id, full_page=True)
            
            # Save to file
            screenshot_bytes = base64.b64decode(screenshot_b64)
            with open(filepath, 'wb') as f:
                f.write(screenshot_bytes)
            
            screenshot = ScreenshotData(
                name=name,
                timestamp=timestamp,
                data=screenshot_b64,
                path=str(filepath)
            )
            
            self.screenshots.append(screenshot)
            self.logger.info(f"Screenshot saved: {filepath}")
            return screenshot
            
        except Exception as e:
            self.logger.error(f"Failed to take screenshot: {str(e)}")
            return None
    
    def get_all_screenshots(self) -> List[ScreenshotData]:
        """Get all screenshots taken"""
        return self.screenshots

# ==================== PAGE OBJECTS ====================

class EvotelLoginPage:
    """Page object for Evotel login functionality"""
    
    def __init__(self, browser: BrowserServiceClient, session_id: str):
        self.browser = browser
        self.session_id = session_id
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def login(self) -> bool:
        """Perform login to Evotel portal"""
        try:
            self.logger.info("Starting Evotel login process")
            
            # Navigate to login page
            await self.browser.navigate(
                self.session_id,
                Config.EVOTEL_URL,
                wait_until="networkidle"
            )
            
            # Fill email
            await self.browser.wait_for_selector(self.session_id, "#Email", timeout=15)
            await self.browser.type_text(
                self.session_id,
                "#Email",
                Config.EVOTEL_EMAIL,
                clear=True
            )
            self.logger.info("Email entered")
            
            # Fill password
            await self.browser.type_text(
                self.session_id,
                "#Password",
                Config.EVOTEL_PASSWORD,
                clear=True
            )
            self.logger.info("Password entered")
            
            # Click login button
            await self.browser.click(
                self.session_id,
                "#loginForm form div:nth-child(4) div button"
            )
            
            # Wait for successful login
            await asyncio.sleep(3)
            current_url = await self.browser.get_current_url(self.session_id)
            
            if "/Manage" in current_url:
                self.logger.info("Login successful")
                return True
            else:
                self.logger.error(f"Login failed - URL: {current_url}")
                return False
                    
        except Exception as e:
            self.logger.error(f"Login failed: {str(e)}")
            raise

# ==================== STRATEGY IMPLEMENTATIONS ====================

class SimplifiedEvotelServiceSearchStrategy:
    """Simplified Evotel service search strategy"""
    
    def __init__(self, browser: BrowserServiceClient, session_id: str):
        self.browser = browser
        self.session_id = session_id
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def search_service(self, circuit_number: str) -> bool:
        """Search for service using circuit number"""
        try:
            self.logger.info(f"Searching for circuit number: {circuit_number}")
            
            # Wait for and fill search field
            await self.browser.wait_for_selector(self.session_id, "#SearchString", timeout=15)
            await self.browser.type_text(
                self.session_id,
                "#SearchString",
                circuit_number,
                clear=True
            )
            await asyncio.sleep(0.5)
            
            # Click search button
            await self.browser.click(self.session_id, "#btnSearch")
            await asyncio.sleep(3)
            
            # Check if results found
            script = """
            const links = document.querySelectorAll('#WebGrid tbody tr td:nth-child(3) a');
            return links.length;
            """
            link_count = await self.browser.execute_script(self.session_id, script)
            
            if link_count and link_count > 0:
                self.logger.info(f"Found {link_count} service results")
                return True
            else:
                self.logger.info("No service results found")
                return False
                
        except Exception as e:
            self.logger.error(f"Service search failed: {str(e)}")
            return False
    
    async def navigate_to_service(self) -> Optional[str]:
        """Navigate to last ACTIVE service and return service UUID"""
        try:
            # Wait for service links
            await self.browser.wait_for_selector(
                self.session_id,
                "#WebGrid tbody tr td:nth-child(3) a",
                timeout=15
            )
            
            # Get active service links
            active_links = await filter_active_service_links(
                self.browser, self.session_id, self.logger
            )
            
            if not active_links:
                raise Exception("No active service links found")
            
            # Click last active service
            last_service = active_links[-1]
            self.logger.info(f"Using active service: {last_service['text']}")
            
            await self.browser.click(self.session_id, last_service['selector'])
            await asyncio.sleep(3)
            
            # Extract service UUID
            current_url = await self.browser.get_current_url(self.session_id)
            if "/Service/Info/" in current_url:
                service_uuid = current_url.split("/Service/Info/")[-1].split("?")[0]
                return service_uuid
            
            return None
        
        except Exception as e:
            self.logger.error(f"Error navigating to service: {str(e)}")
            return None

class EvotelCancellationFormStrategy:
    """Evotel-specific cancellation form strategy"""
    
    def __init__(self, browser: BrowserServiceClient, session_id: str):
        self.browser = browser
        self.session_id = session_id
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def initiate_cancellation(self) -> bool:
        """Click cancel service button"""
        try:
            current_url = await self.browser.get_current_url(self.session_id)
            if "/Service/Info/" not in current_url:
                self.logger.error(f"Not on service info page: {current_url}")
                return False
            
            # Try multiple selectors for cancel button
            selectors = [
                "a:has-text('Cancel Service')",
                "a[href*='/Service/Cancel/']"
            ]
            
            for selector in selectors:
                try:
                    await self.browser.click(self.session_id, selector)
                    await asyncio.sleep(2)
                    
                    # Check if on cancellation page
                    new_url = await self.browser.get_current_url(self.session_id)
                    if "/Service/Cancel/" in new_url:
                        self.logger.info("Successfully navigated to cancellation page")
                        return True
                except:
                    continue
            
            self.logger.error("Cancel Service button not found")
            return False
                
        except Exception as e:
            self.logger.error(f"Failed to initiate cancellation: {str(e)}")
            return False
    
    async def fill_cancellation_form(self, reason: str, comment: str,
                                    cancellation_date: str = None) -> bool:
        """Fill cancellation form"""
        try:
            # Select cancellation reason
            await self.browser.wait_for_selector(
                self.session_id,
                "#CancellationReason",
                timeout=15
            )
            
            script = f"""
            const select = document.querySelector('#CancellationReason');
            const options = Array.from(select.options);
            const option = options.find(opt => opt.text === '{reason}');
            if (option) {{
                select.value = option.value;
                select.dispatchEvent(new Event('change'));
                return true;
            }}
            return false;
            """
            await self.browser.execute_script(self.session_id, script)
            self.logger.info(f"Selected cancellation reason: {reason}")
            
            # Fill comment
            await self.browser.type_text(
                self.session_id,
                "#CancellationComment",
                comment,
                clear=True
            )
            self.logger.info(f"Entered comment: {comment}")
            
            # Set cancellation date
            if not await self._set_cancellation_date(cancellation_date):
                self.logger.warning("Failed to set cancellation date")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to fill cancellation form: {str(e)}")
            return False
    
    async def _set_cancellation_date(self, cancellation_date: str = None) -> bool:
        """Set the cancellation effective date"""
        try:
            if not cancellation_date:
                target_date = date.today() + timedelta(days=30)
                cancellation_date = target_date.strftime("%d/%m/%Y")
            
            self.logger.info(f"Setting cancellation date to: {cancellation_date}")
            
            # Try direct input
            await self.browser.type_text(
                self.session_id,
                "#CancellationEffectiveDate",
                cancellation_date,
                clear=True
            )
            
            # Trigger change event
            script = """
            const field = document.querySelector('#CancellationEffectiveDate');
            field.dispatchEvent(new Event('change'));
            """
            await self.browser.execute_script(self.session_id, script)
            
            self.logger.info(f"Set cancellation date: {cancellation_date}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error setting cancellation date: {str(e)}")
            return False
    
    async def confirm_cancellation(self) -> bool:
        """Confirm cancellation submission"""
        try:
            await self.browser.click(
                self.session_id,
                "input[value='Confirm Cancellation']"
            )
            
            # Wait for redirect
            await asyncio.sleep(3)
            current_url = await self.browser.get_current_url(self.session_id)
            
            if "/Service/Info/" in current_url:
                self.logger.info("Cancellation confirmed successfully")
                return True
            else:
                self.logger.error("Did not redirect to service info page")
                return False
            
        except Exception as e:
            self.logger.error(f"Failed to confirm cancellation: {str(e)}")
            return False

class EvotelWorkOrderStrategy:
    """Evotel-specific work order management strategy"""
    
    def __init__(self, browser: BrowserServiceClient, session_id: str):
        self.browser = browser
        self.session_id = session_id
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def navigate_to_work_orders(self) -> bool:
        """Navigate to work orders section"""
        try:
            current_url = await self.browser.get_current_url(self.session_id)
            if "/Service/Info/" not in current_url:
                self.logger.error(f"Not on service info page: {current_url}")
                return False
            
            # Click work orders menu
            await self.browser.click(self.session_id, "#work-orders > span")
            await asyncio.sleep(2)
            
            # Get work order links (filter out email links)
            script = """
            const links = Array.from(document.querySelectorAll('dl.dl-horizontal.dl-horizontal-service dd a'));
            return links.filter(link => {
                const href = link.href || '';
                const text = link.textContent.trim();
                return !href.includes('mailto:') && text;
            }).map((link, index) => ({
                index: index,
                text: link.textContent.trim(),
                selector: `dl.dl-horizontal.dl-horizontal-service dd a:nth-of-type(${index+1})`
            }));
            """
            
            work_order_links = await self.browser.execute_script(self.session_id, script)
            
            if not work_order_links:
                self.logger.error("No work order links found")
                return False
            
            # Click first work order
            first_wo = work_order_links[0]
            await self.browser.click(self.session_id, first_wo['selector'])
            await asyncio.sleep(3)
            
            self.logger.info("Successfully navigated to work order page")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to navigate to work orders: {str(e)}")
            return False
    
    async def update_work_order_status(self, comment: str) -> Optional[str]:
        """Update work order status to completed"""
        try:
            # Extract work order reference
            page_text = await self.browser.get_text(self.session_id, "body")
            ref_match = re.search(r'Ref:\s*(\d{8}-\d+)', page_text)
            work_order_ref = ref_match.group(1) if ref_match else "unknown"
            
            # Update status dropdown
            script = """
            const select = document.querySelector('#StatusId');
            select.value = 'c14c051e-d259-426f-a2b1-e869e5300bcc';
            select.dispatchEvent(new Event('change'));
            """
            await self.browser.execute_script(self.session_id, script)
            self.logger.info("Updated work order status to completed")
            
            # Fill comments
            await self.browser.type_text(
                self.session_id,
                "#Comments",
                comment,
                clear=True
            )
            
            # Check "No user notification" checkbox
            script = """
            const checkbox = document.querySelector('#NoUserNotification');
            if (!checkbox.checked) {
                checkbox.click();
            }
            """
            await self.browser.execute_script(self.session_id, script)
            
            # Submit
            await self.browser.click(self.session_id, "input[value='Submit']")
            await asyncio.sleep(3)
            
            self.logger.info(f"Work order {work_order_ref} updated successfully")
            return work_order_ref
            
        except Exception as e:
            self.logger.error(f"Failed to update work order: {str(e)}")
            return None

# ==================== MAIN AUTOMATION CLASS ====================

class EvotelCancellationAutomation:
    """Enhanced Evotel cancellation automation"""
    
    def __init__(self, browser_client: BrowserServiceClient):
        self.browser = browser_client
        self.session_id = None
        self.screenshot_service = None
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def cancel_service(self, request: CancellationRequest) -> CancellationResult:
        """Main cancellation method"""
        start_time = time.time()
        
        try:
            self.logger.info(f"=== STARTING EVOTEL CANCELLATION ===")
            self.logger.info(f"Job: {request.job_id}, Circuit: {request.circuit_number}")
            
            # Create browser session
            self.session_id = await self.browser.create_session(
                int(request.job_id),
                headless=True
            )
            
            # Setup services
            self.screenshot_service = ScreenshotService(request.job_id)
            await self.screenshot_service.take_screenshot(
                self.browser, self.session_id, "cancellation_initial"
            )
            
            # STEP 1: Login
            self.logger.info("STEP 1: Login")
            login_page = EvotelLoginPage(self.browser, self.session_id)
            await login_page.login()
            await self.screenshot_service.take_screenshot(
                self.browser, self.session_id, "cancellation_after_login"
            )
            
            # STEP 2: Search
            self.logger.info("STEP 2: Search for service")
            search_strategy = SimplifiedEvotelServiceSearchStrategy(
                self.browser, self.session_id
            )
            
            if not await search_strategy.search_service(request.circuit_number):
                await self.screenshot_service.take_screenshot(
                    self.browser, self.session_id, "cancellation_not_found"
                )
                return self._create_not_found_result(request)
            
            await self.screenshot_service.take_screenshot(
                self.browser, self.session_id, "cancellation_search_results"
            )
            
            # STEP 3: Navigate to service
            self.logger.info("STEP 3: Navigate to service")
            service_uuid = await search_strategy.navigate_to_service()
            if not service_uuid:
                return self._create_error_result(request, "Failed to navigate to service")
            
            await self.screenshot_service.take_screenshot(
                self.browser, self.session_id, "cancellation_service_selected"
            )
            
            # STEP 4: Initiate cancellation
            self.logger.info("STEP 4: Initiate cancellation")
            cancel_form = EvotelCancellationFormStrategy(self.browser, self.session_id)
            
            if not await cancel_form.initiate_cancellation():
                return self._create_error_result(request, "Failed to initiate cancellation")
            
            await self.screenshot_service.take_screenshot(
                self.browser, self.session_id, "cancellation_form_page"
            )
            
            # STEP 5: Fill form
            self.logger.info("STEP 5: Fill cancellation form")
            if not await cancel_form.fill_cancellation_form(
                "USING ANOTHER FNO",
                "Bot cancellation",
                request.requested_date
            ):
                return self._create_error_result(request, "Failed to fill form")
            
            await self.screenshot_service.take_screenshot(
                self.browser, self.session_id, "cancellation_form_filled"
            )
            
            # STEP 6: Confirm
            self.logger.info("STEP 6: Confirm cancellation")
            if not await cancel_form.confirm_cancellation():
                return self._create_error_result(request, "Failed to confirm")
            
            await self.screenshot_service.take_screenshot(
                self.browser, self.session_id, "cancellation_confirmed"
            )
            
            # STEP 7: Navigate to work orders
            self.logger.info("STEP 7: Navigate to work orders")
            wo_strategy = EvotelWorkOrderStrategy(self.browser, self.session_id)
            
            if not await wo_strategy.navigate_to_work_orders():
                return self._create_error_result(request, "Failed to navigate to work orders")
            
            await self.screenshot_service.take_screenshot(
                self.browser, self.session_id, "cancellation_work_order"
            )
            
            # STEP 8: Update work order
            self.logger.info("STEP 8: Update work order")
            work_order_ref = await wo_strategy.update_work_order_status("Bot cancellation")
            
            if not work_order_ref:
                return self._create_error_result(request, "Failed to update work order")
            
            await self.screenshot_service.take_screenshot(
                self.browser, self.session_id, "cancellation_wo_updated"
            )
            
            # Success
            execution_time = time.time() - start_time
            self.logger.info(f"=== CANCELLATION COMPLETED ===")
            return self._create_success_result(
                request, service_uuid, work_order_ref, execution_time
            )
            
        except Exception as e:
            self.logger.error(f"Cancellation failed: {str(e)}")
            
            if self.screenshot_service and self.session_id:
                try:
                    await self.screenshot_service.take_screenshot(
                        self.browser, self.session_id, "error_state"
                    )
                except:
                    pass
            
            return self._create_error_result(request, str(e))
            
        finally:
            if self.session_id:
                await self.browser.close_session(self.session_id)
    
    def _create_success_result(self, request: CancellationRequest,
                             service_uuid: str, work_order_ref: str,
                             execution_time: float) -> CancellationResult:
        """Create success result"""
        cancellation_details = CancellationDetails(
            work_order_number=work_order_ref,
            service_uuid=service_uuid,
            external_reference=request.solution_id,
            requested_date=request.requested_date,
            submission_date=datetime.now(),
            status="completed",
            confirmation_received=True,
            work_order_updated=True
        )
        
        return CancellationResult(
            job_id=request.job_id,
            circuit_number=request.circuit_number,
            status=CancellationStatus.SUCCESS,
            message=f"Successfully cancelled service {request.circuit_number}",
            result_type=CancellationResultType.SUBMITTED,
            cancellation_details=cancellation_details,
            execution_time=execution_time,
            screenshots=self.screenshot_service.get_all_screenshots(),
            evidence_dir=str(self.screenshot_service.evidence_dir)
        )
    
    def _create_not_found_result(self, request: CancellationRequest) -> CancellationResult:
        """Create not found result"""
        return CancellationResult(
            job_id=request.job_id,
            circuit_number=request.circuit_number,
            status=CancellationStatus.FAILURE,
            message=f"Service {request.circuit_number} not found",
            result_type=CancellationResultType.NOT_FOUND,
            screenshots=self.screenshot_service.get_all_screenshots(),
            evidence_dir=str(self.screenshot_service.evidence_dir)
        )
    
    def _create_error_result(self, request: CancellationRequest,
                           error_message: str) -> CancellationResult:
        """Create error result"""
        return CancellationResult(
            job_id=request.job_id,
            circuit_number=request.circuit_number,
            status=CancellationStatus.ERROR,
            message=error_message,
            result_type=CancellationResultType.ERROR,
            screenshots=self.screenshot_service.get_all_screenshots() if self.screenshot_service else [],
            evidence_dir=str(self.screenshot_service.evidence_dir) if self.screenshot_service else None,
            error_details={"error": error_message, "timestamp": datetime.now().isoformat()}
        )

# ==================== MAIN EXECUTION FUNCTION ====================

async def execute(parameters: Dict[str, Any],
                 browser_client: BrowserServiceClient) -> Dict[str, Any]:
    """
    Execution function for Evotel cancellation
    Includes validation execution at the end for comprehensive data collection
    """
    logger.info("=== EVOTEL CANCELLATION EXECUTE FUNCTION STARTED ===")
    
    # Extract parameters
    job_id = parameters.get("job_id")
    circuit_number = parameters.get("circuit_number")
    solution_id = parameters.get("solution_id")
    requested_date = parameters.get("requested_date")
    
    # Initialize results
    results = {
        "status": "failure",
        "message": "",
        "evidence": [],
        "screenshot_data": [],
        "details": {}
    }
    
    try:
        # Validate parameters
        if not job_id or not circuit_number:
            return {
                "status": "error",
                "message": "Missing required parameters",
                "details": {"error": "job_id and circuit_number required"},
                "screenshot_data": []
            }
        
        # Generate solution_id if not provided
        if not solution_id:
            solution_id = f"EVOTEL_{job_id}"
        
        # Calculate date if not provided
        if not requested_date:
            target_date = date.today() + timedelta(days=30)
            requested_date = target_date.strftime("%d/%m/%Y")
        
        # Validate configuration
        if not all([Config.EVOTEL_URL, Config.EVOTEL_EMAIL, Config.EVOTEL_PASSWORD]):
            return {
                "status": "error",
                "message": "Missing Evotel configuration",
                "details": {"error": "Evotel credentials not configured"},
                "screenshot_data": []
            }
        
        # Create request
        request = CancellationRequest(
            job_id=job_id,
            circuit_number=circuit_number,
            solution_id=solution_id,
            requested_date=requested_date
        )
        
        # Execute cancellation
        automation = EvotelCancellationAutomation(browser_client)
        result = await automation.cancel_service(request)
        
        # Convert to dictionary
        results = {
            "status": "success" if result.status == CancellationStatus.SUCCESS else "failure",
            "message": result.message,
            "details": {
                "found": result.status in [CancellationStatus.SUCCESS, CancellationStatus.ALREADY_CANCELLED],
                "circuit_number": result.circuit_number,
                "result_type": result.result_type.value,
                "cancellation_status": result.status.value,
                "execution_time": result.execution_time,
                "cancellation_details": result.cancellation_details.dict() if result.cancellation_details else None,
                "requested_date": requested_date,
                "cancellation_submitted": result.status == CancellationStatus.SUCCESS,
                "cancellation_captured_id": result.cancellation_details.work_order_number if result.cancellation_details else None,
                "service_found": result.result_type != CancellationResultType.NOT_FOUND
            },
            "screenshot_data": [
                {
                    "name": s.name,
                    "timestamp": s.timestamp.isoformat(),
                    "base64_data": s.data,
                    "path": s.path
                }
                for s in result.screenshots
            ]
        }
        
        logger.info("=== CANCELLATION COMPLETED ===")
        
    except Exception as e:
        logger.error(f"=== CANCELLATION FAILED ===")
        logger.error(f"Exception: {str(e)}")
        logger.error(traceback.format_exc())
        
        results = {
            "status": "error",
            "message": f"Execution error: {str(e)}",
            "details": {
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            },
            "screenshot_data": []
        }
    
    finally:
        # Execute post-cancellation validation
        await asyncio.sleep(3)
        logger.info("=== STARTING POST-CANCELLATION VALIDATION ===")
        
        try:
            # Import validation execute function
            from automations.evotel.validation import execute as validation_execute
            
            validation_result = await validation_execute(
                {"job_id": job_id, "circuit_number": circuit_number},
                browser_client
            )
            
            # Merge validation data
            if "details" in validation_result and validation_result["details"]:
                results["details"] = validation_result["details"]
                logger.info("Replaced details with post-cancellation validation data")
                
                # Merge screenshots
                if "screenshot_data" in validation_result:
                    existing = results.get("screenshot_data", [])
                    validation_shots = validation_result["screenshot_data"]
                    results["screenshot_data"] = existing + validation_shots
                    
        except Exception as validation_error:
            logger.error(f"Post-cancellation validation failed: {str(validation_error)}")
            if "details" not in results:
                results["details"] = {}
            results["details"]["validation_error"] = str(validation_error)
    
    logger.info("=== EVOTEL CANCELLATION EXECUTE COMPLETED ===")
    return results
