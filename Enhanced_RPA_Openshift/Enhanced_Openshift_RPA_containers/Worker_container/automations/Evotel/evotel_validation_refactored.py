"""
Evotel Validation Module - Browser Service Version
=====================================================================
Refactored to use browser service with tab management
Updated to use circuit_number for uniformity across all FNO providers
"""

import asyncio
import time
import logging
import traceback
import json
import base64
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field

# Import browser client
from browser_client import BrowserServiceClient

# Import configuration
from config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ==================== ENUMERATIONS ====================

class ValidationStatus(str, Enum):
    """Job execution status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"

class SearchResult(str, Enum):
    """Service search result"""
    FOUND = "found"
    NOT_FOUND = "not_found"
    ERROR = "error"

class ServiceStatus(str, Enum):
    """Service operational status"""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    PENDING = "pending"
    UNKNOWN = "unknown"

# ==================== DATA MODELS ====================

class ValidationRequest(BaseModel):
    """Input model for validation requests"""
    job_id: str = Field(..., description="Unique job identifier")
    circuit_number: str = Field(..., description="Circuit number to validate")

class ScreenshotData(BaseModel):
    """Screenshot metadata and data container"""
    name: str
    timestamp: datetime
    data: str  # Base64 encoded image
    path: str
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

class ServiceData(BaseModel):
    """Service information container"""
    service_id: str
    service_type: Optional[str] = None
    customer_name: Optional[str] = None
    status: ServiceStatus
    work_orders: List[Dict] = []
    service_details: Optional[Dict] = None
    extraction_timestamp: Optional[str] = None

class ValidationResult(BaseModel):
    """Complete validation result container"""
    job_id: str
    circuit_number: str
    status: ValidationStatus
    message: str
    found: bool
    service_data: Optional[ServiceData] = None
    search_result: SearchResult
    execution_time: Optional[float] = None
    screenshots: List[ScreenshotData] = []
    evidence_dir: Optional[str] = None
    details: Optional[Dict] = None

# ==================== SCREENSHOT SERVICE ====================

class ScreenshotService:
    """Screenshot service for evidence collection"""
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.evidence_dir = Path(Config.get_job_screenshot_dir(job_id))
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots: List[ScreenshotData] = []
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def take_screenshot(self, browser: BrowserServiceClient, 
                            session_id: str, name: str) -> Optional[ScreenshotData]:
        """Capture and encode screenshot for evidence"""
        try:
            timestamp = datetime.now()
            filename = f"{name}_{timestamp.strftime('%Y%m%d_%H%M%S')}.png"
            filepath = self.evidence_dir / filename

            # Get screenshot from browser service (already base64)
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
            self.logger.info(f"Screenshot saved: {filename}")
            return screenshot
            
        except Exception as e:
            self.logger.error(f"Failed to take screenshot: {str(e)}")
            return None
    
    def get_all_screenshots(self) -> List[ScreenshotData]:
        """Get all screenshots taken"""
        return self.screenshots

# ==================== UTILITY FUNCTIONS ====================

async def robust_click(browser: BrowserServiceClient, session_id: str, 
                      selector: str, description: str = "element") -> bool:
    """Multi-method element clicking with fallback strategies"""
    try:
        # First try standard click
        await browser.click(session_id, selector)
        logger.info(f"Successfully clicked {description}")
        return True
    except Exception as e:
        logger.debug(f"Standard click failed for {description}: {str(e)}")
        
        # Fallback: JavaScript click
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
    """
    Filter service links to only return active (non-greyed) links
    Returns list of dicts with selector and text
    """
    try:
        # Get all service link elements
        script = """
        const links = Array.from(document.querySelectorAll('#WebGrid tbody tr td:nth-child(3) a'));
        return links.map((link, index) => ({
            index: index,
            text: link.textContent.trim(),
            href: link.href || '',
            style: link.getAttribute('style') || '',
            classes: link.className || '',
            enabled: link.disabled === false,
            opacity: window.getComputedStyle(link).opacity,
            color: window.getComputedStyle(link).color
        }));
        """
        
        all_links = await browser.execute_script(session_id, script)
        
        if not all_links:
            logger.warning("No service links found")
            return []
        
        active_links = []
        
        for link_info in all_links:
            is_active = True
            
            # Check href validity
            href = link_info.get('href', '')
            if not href or href in ["#", "javascript:void(0)", "javascript:;"]:
                logger.info(f"Link {link_info['index']+1}: Skipping - invalid href")
                continue
            
            # Check for disabled classes
            classes = link_info.get('classes', '').lower()
            if any(cls in classes for cls in ['disabled', 'inactive', 'text-muted', 'greyed-out']):
                logger.info(f"Link {link_info['index']+1}: Skipping - has disabled class")
                continue
            
            # Check inline style for gray colors
            style = link_info.get('style', '').lower()
            gray_colors = ['#c0c0c0', '#cccccc', '#999999', '#666666', '#808080']
            if any(gray in style for gray in gray_colors):
                logger.info(f"Link {link_info['index']+1}: Skipping - has gray inline style")
                continue
            
            # Check computed color (RGB check)
            color = link_info.get('color', '')
            if color:
                rgb_match = re.search(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', color)
                if rgb_match:
                    r, g, b = map(int, rgb_match.groups())
                    if abs(r - g) < 50 and abs(g - b) < 50 and max(r, g, b) < 150:
                        logger.info(f"Link {link_info['index']+1}: Skipping - greyed out color")
                        continue
            
            # Check opacity
            opacity = float(link_info.get('opacity', 1))
            if opacity < 0.6:
                logger.info(f"Link {link_info['index']+1}: Skipping - low opacity")
                continue
            
            # Link is active
            logger.info(f"Link {link_info['index']+1}: Active - '{link_info['text']}'")
            active_links.append({
                'selector': f"#WebGrid tbody tr td:nth-child(3) a:nth-of-type({link_info['index']+1})",
                'text': link_info['text'],
                'href': href
            })
        
        logger.info(f"Found {len(active_links)} active links out of {len(all_links)} total")
        return active_links
        
    except Exception as e:
        logger.error(f"Error filtering active service links: {e}")
        return []

async def select_newest_inactive_service(browser: BrowserServiceClient,
                                        session_id: str, logger) -> Optional[str]:
    """
    Select the newest inactive service based on Effective Date
    Returns selector for the service link
    """
    try:
        script = """
        const rows = Array.from(document.querySelectorAll('#WebGrid tbody tr'));
        return rows.map((row, index) => {
            const linkCell = row.querySelector('td:nth-child(3) a');
            const dateCell = row.querySelector('td:nth-child(7)');
            return {
                index: index,
                text: linkCell ? linkCell.textContent.trim() : '',
                date: dateCell ? dateCell.textContent.trim() : '',
                selector: `#WebGrid tbody tr:nth-of-type(${index+1}) td:nth-child(3) a`
            };
        }).filter(row => row.text && row.date);
        """
        
        rows = await browser.execute_script(session_id, script)
        
        if not rows:
            logger.error("No service rows found")
            return None
        
        # Parse dates and find newest
        newest_service = None
        newest_date = None
        
        for row in rows:
            try:
                date_text = row['date']
                effective_date = datetime.strptime(date_text, "%d/%m/%Y")
                
                if newest_date is None or effective_date > newest_date:
                    newest_date = effective_date
                    newest_service = row['selector']
                    logger.debug(f"Service: {row['text'][:50]}... - Date: {date_text}")
            except ValueError as ve:
                logger.warning(f"Could not parse date '{date_text}': {ve}")
                continue
        
        if newest_service:
            logger.info(f"Selected newest inactive service (Date: {newest_date.strftime('%d/%m/%Y')})")
        
        return newest_service
        
    except Exception as e:
        logger.error(f"Error selecting newest inactive service: {e}")
        return None

# ==================== LOGIN HANDLER ====================

class EvotelLogin:
    """Email/password authentication handler for Evotel portal"""
    
    def __init__(self, browser: BrowserServiceClient, session_id: str):
        self.browser = browser
        self.session_id = session_id
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def login(self) -> bool:
        """Execute complete login flow"""
        try:
            self.logger.info("Starting Evotel login process")
            
            # Navigate to login page
            await self.browser.navigate(
                self.session_id,
                Config.EVOTEL_URL,
                wait_until="networkidle"
            )
            
            self.logger.info("Login page loaded successfully")
            
            # Fill email field
            await self.browser.wait_for_selector(self.session_id, "#Email", timeout=15)
            await self.browser.type_text(
                self.session_id,
                "#Email",
                Config.EVOTEL_EMAIL,
                clear=True
            )
            self.logger.info("Email entered successfully")
            
            # Fill password field
            await self.browser.type_text(
                self.session_id,
                "#Password",
                Config.EVOTEL_PASSWORD,
                clear=True
            )
            self.logger.info("Password entered successfully")
            
            # Click login button
            await self.browser.click(
                self.session_id,
                "#loginForm form div:nth-child(4) div button"
            )
            self.logger.info("Login form submitted")
            
            # Wait for successful login
            await asyncio.sleep(3)
            current_url = await self.browser.get_current_url(self.session_id)
            
            if "/Manage/Index" in current_url or "/Manage" in current_url:
                self.logger.info("Login successful")
                return True
            else:
                self.logger.error(f"Login failed - current URL: {current_url}")
                return False
                    
        except Exception as e:
            self.logger.error(f"Login failed: {str(e)}")
            raise

# ==================== DATA EXTRACTOR ====================

class EvotelDataExtractor:
    """Extract data from Evotel portal"""
    
    def __init__(self, browser: BrowserServiceClient, session_id: str, logger):
        self.browser = browser
        self.session_id = session_id
        self.logger = logger
    
    async def search_circuit_number(self, circuit_number: str) -> SearchResult:
        """Search for circuit number in Evotel portal"""
        try:
            self.logger.info(f"Searching for circuit number: {circuit_number}")
            
            # Wait for search field
            await self.browser.wait_for_selector(self.session_id, "#SearchString", timeout=15)
            
            # Enter circuit number
            await self.browser.type_text(
                self.session_id,
                "#SearchString",
                circuit_number,
                clear=True
            )
            await asyncio.sleep(0.5)
            
            self.logger.info(f"Circuit number entered: {circuit_number}")
            
            # Click search button
            await self.browser.click(self.session_id, "#btnSearch")
            self.logger.info("Search button clicked")
            
            # Wait for results
            await asyncio.sleep(3)
            
            return await self._check_search_results()
            
        except Exception as e:
            self.logger.error(f"Circuit number search failed: {str(e)}")
            return SearchResult.ERROR
    
    async def _check_search_results(self) -> SearchResult:
        """Check if search returned results"""
        try:
            # Check for service links
            script = """
            const links = document.querySelectorAll('#WebGrid tbody tr td:nth-child(3) a');
            return links.length;
            """
            
            link_count = await self.browser.execute_script(self.session_id, script)
            
            if link_count and link_count > 0:
                self.logger.info(f"Found {link_count} service results")
                return SearchResult.FOUND
            else:
                # Check for "no results" indicators
                page_text = await self.browser.get_text(self.session_id, "body")
                if "no results" in page_text.lower() or "not found" in page_text.lower():
                    self.logger.info("No search results found")
                    return SearchResult.NOT_FOUND
                else:
                    self.logger.warning("Unknown search result state")
                    return SearchResult.ERROR
                    
        except Exception as e:
            self.logger.error(f"Error checking search results: {str(e)}")
            return SearchResult.ERROR
    
    async def extract_service_info(self) -> Dict[str, Any]:
        """Extract service information from search results"""
        try:
            self.logger.info("Extracting active service information")
            
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
            
            if active_links:
                # Use last active service
                service_link = active_links[-1]
                self.logger.info(f"Using active service: {service_link['text']}")
                selector = service_link['selector']
            else:
                # Fallback to newest inactive
                self.logger.info("No active services, selecting newest inactive")
                selector = await select_newest_inactive_service(
                    self.browser, self.session_id, self.logger
                )
                if not selector:
                    return {"error": "No services found"}
            
            # Click service
            if not await robust_click(self.browser, self.session_id, selector, "service link"):
                return {"error": "Failed to click service link"}
            
            await asyncio.sleep(3)
            
            # Extract service UUID from URL
            current_url = await self.browser.get_current_url(self.session_id)
            service_uuid = None
            if "/Service/Info/" in current_url:
                service_uuid = current_url.split("/Service/Info/")[-1].split("?")[0]
            
            return {"service_uuid": service_uuid, "status": "success"}
            
        except Exception as e:
            self.logger.error(f"Error extracting service info: {str(e)}")
            return {"error": str(e)}
    
    async def extract_work_orders(self) -> List[Dict[str, Any]]:
        """Extract work orders - first (most recent) only"""
        try:
            self.logger.info("Extracting first work order")
            
            # Click work orders menu
            await self.browser.click(self.session_id, "#work-orders > span")
            await asyncio.sleep(2)
            
            # Get work order links (filter out email links)
            script = """
            const links = Array.from(document.querySelectorAll('dl.dl-horizontal.dl-horizontal-service dd a'));
            return links.map((link, index) => ({
                index: index,
                text: link.textContent.trim(),
                href: link.href || '',
                selector: `dl.dl-horizontal.dl-horizontal-service dd a:nth-of-type(${index+1})`
            })).filter(link => !link.href.includes('mailto:') && link.text);
            """
            
            work_order_links = await self.browser.execute_script(self.session_id, script)
            
            if not work_order_links:
                self.logger.error("No work order links found")
                return []
            
            # Click first work order
            first_wo = work_order_links[0]
            self.logger.info(f"Processing first work order: {first_wo['text']}")
            
            await self.browser.click(self.session_id, first_wo['selector'])
            await asyncio.sleep(3)
            
            # Extract comprehensive data
            comprehensive_details = await self._extract_comprehensive_work_order_details()
            
            return [{
                "work_order_index": 1,
                "work_order_text": first_wo['text'],
                "work_order_url": first_wo['href'],
                "comprehensive_details": comprehensive_details,
                "extraction_timestamp": datetime.now().isoformat(),
                "is_most_recent": True
            }]
            
        except Exception as e:
            self.logger.error(f"Error extracting work orders: {str(e)}")
            return []
    
    async def _extract_comprehensive_work_order_details(self) -> Dict[str, Any]:
        """Extract comprehensive work order details"""
        try:
            # Get full page text
            page_text = await self.browser.get_text(self.session_id, "body")
            
            # Extract using JavaScript
            script = """
            const extractField = (labels) => {
                for (const label of labels) {
                    const elements = document.evaluate(
                        `//*[contains(text(), '${label}')]/following-sibling::*[1]`,
                        document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
                    );
                    if (elements.singleNodeValue) {
                        return elements.singleNodeValue.textContent.trim();
                    }
                }
                return '';
            };
            
            return {
                client_details: {
                    client_name: extractField(['Client']),
                    area: extractField(['Area']),
                    address: extractField(['Address']),
                    email: extractField(['E-Mail', 'Email']),
                    mobile: extractField(['Mobile'])
                },
                service_details: {
                    service_provider: extractField(['Service Provider']),
                    product: extractField(['Product']),
                    service_status: extractField(['Service Status', 'Status'])
                },
                work_order_details: {
                    reference: extractField(['Reference']),
                    status: extractField(['Status'])
                }
            };
            """
            
            extracted_data = await self.browser.execute_script(self.session_id, script)
            
            return {
                "extraction_metadata": {
                    "extraction_timestamp": datetime.now().isoformat(),
                    "page_url": await self.browser.get_current_url(self.session_id),
                    "full_page_text": page_text
                },
                **extracted_data
            }
            
        except Exception as e:
            self.logger.error(f"Comprehensive extraction failed: {str(e)}")
            return {"extraction_error": str(e)}

# ==================== MAIN AUTOMATION CLASS ====================

class EvotelValidationAutomation:
    """Main automation class for Evotel validation"""
    
    def __init__(self, browser_client: BrowserServiceClient):
        self.browser = browser_client
        self.session_id = None
        self.screenshot_service = None
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def validate_circuit_number(self, request: ValidationRequest) -> ValidationResult:
        """Main validation method"""
        start_time = time.time()
        
        try:
            self.logger.info(f"Starting validation for {request.job_id}, circuit {request.circuit_number}")
            
            # Create browser session
            self.session_id = await self.browser.create_session(
                int(request.job_id),
                headless=True
            )
            
            # Setup screenshot service
            self.screenshot_service = ScreenshotService(request.job_id)
            await self.screenshot_service.take_screenshot(
                self.browser, self.session_id, "initial_state"
            )
            
            # Login
            login_handler = EvotelLogin(self.browser, self.session_id)
            await login_handler.login()
            await self.screenshot_service.take_screenshot(
                self.browser, self.session_id, "after_login"
            )
            
            # Search
            data_extractor = EvotelDataExtractor(self.browser, self.session_id, self.logger)
            search_result = await data_extractor.search_circuit_number(request.circuit_number)
            await self.screenshot_service.take_screenshot(
                self.browser, self.session_id, "search_completed"
            )
            
            if search_result == SearchResult.ERROR:
                return self._create_error_result(request, "Search operation failed")
            
            if search_result == SearchResult.NOT_FOUND:
                return self._create_not_found_result(request, time.time() - start_time)
            
            # Extract service info
            service_info = await data_extractor.extract_service_info()
            await self.screenshot_service.take_screenshot(
                self.browser, self.session_id, "service_info_extracted"
            )
            
            if service_info.get("error"):
                return self._create_error_result(
                    request, f"Service extraction failed: {service_info['error']}"
                )
            
            # Extract work orders
            work_orders = await data_extractor.extract_work_orders()
            await self.screenshot_service.take_screenshot(
                self.browser, self.session_id, "work_orders_extracted"
            )
            
            # Create success result
            execution_time = time.time() - start_time
            return self._create_comprehensive_success_result(
                request, service_info, work_orders, execution_time
            )
            
        except Exception as e:
            self.logger.error(f"Validation failed: {str(e)}")
            
            if self.screenshot_service and self.session_id:
                try:
                    await self.screenshot_service.take_screenshot(
                        self.browser, self.session_id, "error_state"
                    )
                except:
                    pass
            
            return ValidationResult(
                job_id=request.job_id,
                circuit_number=request.circuit_number,
                status=ValidationStatus.ERROR,
                message=str(e),
                found=False,
                search_result=SearchResult.ERROR,
                screenshots=self.screenshot_service.get_all_screenshots() if self.screenshot_service else [],
                evidence_dir=str(self.screenshot_service.evidence_dir) if self.screenshot_service else None
            )
            
        finally:
            if self.session_id:
                await self.browser.close_session(self.session_id)
    
    def _create_comprehensive_success_result(self, request: ValidationRequest,
                                           service_info: Dict, work_orders: List[Dict],
                                           execution_time: float) -> ValidationResult:
        """Create comprehensive success result"""
        primary_wo = work_orders[0] if work_orders else {}
        comprehensive_data = primary_wo.get("comprehensive_details", {})
        
        service_data = ServiceData(
            service_id=service_info.get("service_uuid", ""),
            service_type=service_info.get("service_name", ""),
            customer_name=comprehensive_data.get("client_details", {}).get("client_name", ""),
            status=ServiceStatus.ACTIVE,
            work_orders=work_orders,
            service_details=service_info,
            extraction_timestamp=datetime.now().isoformat()
        )
        
        details = {
            "found": True,
            "circuit_number": request.circuit_number,
            "service_summary": {
                "customer": comprehensive_data.get("client_details", {}).get("client_name", ""),
                "product": comprehensive_data.get("service_details", {}).get("product", ""),
                "status": comprehensive_data.get("service_details", {}).get("service_status", "")
            },
            "work_order_summary": {
                "total_work_orders": len(work_orders),
                "all_work_orders": work_orders
            },
            "raw_extraction": {
                "comprehensive_extraction": comprehensive_data,
                "service_info": service_info
            }
        }
        
        return ValidationResult(
            job_id=request.job_id,
            circuit_number=request.circuit_number,
            status=ValidationStatus.SUCCESS,
            message=f"Successfully validated circuit {request.circuit_number}",
            found=True,
            service_data=service_data,
            search_result=SearchResult.FOUND,
            execution_time=execution_time,
            screenshots=self.screenshot_service.get_all_screenshots(),
            evidence_dir=str(self.screenshot_service.evidence_dir),
            details=details
        )
    
    def _create_error_result(self, request: ValidationRequest, message: str) -> ValidationResult:
        """Create error result"""
        return ValidationResult(
            job_id=request.job_id,
            circuit_number=request.circuit_number,
            status=ValidationStatus.ERROR,
            message=message,
            found=False,
            search_result=SearchResult.ERROR,
            screenshots=self.screenshot_service.get_all_screenshots() if self.screenshot_service else [],
            evidence_dir=str(self.screenshot_service.evidence_dir) if self.screenshot_service else None
        )
    
    def _create_not_found_result(self, request: ValidationRequest, execution_time: float) -> ValidationResult:
        """Create not found result"""
        return ValidationResult(
            job_id=request.job_id,
            circuit_number=request.circuit_number,
            status=ValidationStatus.SUCCESS,
            message=f"Circuit {request.circuit_number} not found",
            found=False,
            search_result=SearchResult.NOT_FOUND,
            execution_time=execution_time,
            screenshots=self.screenshot_service.get_all_screenshots() if self.screenshot_service else [],
            evidence_dir=str(self.screenshot_service.evidence_dir) if self.screenshot_service else None,
            details={"found": False, "search_term": request.circuit_number}
        )

# ==================== MAIN EXECUTION ====================

async def execute(parameters: Dict[str, Any], 
                 browser_client: BrowserServiceClient) -> Dict[str, Any]:
    """Main execution function for external API calls"""
    try:
        # Validate configuration
        if not all([Config.EVOTEL_URL, Config.EVOTEL_EMAIL, Config.EVOTEL_PASSWORD]):
            logger.error("Missing required Evotel configuration")
            return {
                "status": "error",
                "message": "Missing required Evotel configuration",
                "details": {"error": "configuration_missing"},
                "screenshot_data": []
            }
        
        # Create validation request
        request = ValidationRequest(
            job_id=parameters.get("job_id"),
            circuit_number=parameters.get("circuit_number")
        )
        
        logger.info(f"Starting validation for circuit: {request.circuit_number}")
        
        # Execute validation
        automation = EvotelValidationAutomation(browser_client)
        result = await automation.validate_circuit_number(request)
        
        # Convert result to dictionary
        result_dict = {
            "status": result.status.value,
            "message": result.message,
            "details": result.details or {"found": result.found},
            "evidence_dir": result.evidence_dir,
            "screenshot_data": [
                {
                    "name": screenshot.name,
                    "timestamp": screenshot.timestamp.isoformat(),
                    "base64_data": screenshot.data,
                    "path": screenshot.path
                }
                for screenshot in result.screenshots
            ],
            "execution_time": result.execution_time
        }
        
        return result_dict
        
    except Exception as e:
        logger.error(f"Execute function failed: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "message": f"Execution error: {str(e)}",
            "details": {"error": str(e)},
            "screenshot_data": []
        }
