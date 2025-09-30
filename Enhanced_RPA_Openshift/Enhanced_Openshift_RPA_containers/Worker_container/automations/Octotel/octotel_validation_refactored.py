"""
Octotel Validation Module - Browser Service Version
===================================================
Refactored to use browser service with tab management.
Opens new tab, performs validation, closes tab, returns to original state.
"""

import os
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
    totp_code: Optional[str] = Field(None, description="Pre-generated TOTP code from orchestrator")

class ScreenshotData(BaseModel):
    """Screenshot metadata and data container"""
    name: str
    timestamp: datetime
    data: str  # Base64 encoded image
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

class ServiceData(BaseModel):
    """Service information container"""
    bitstream_reference: str
    status: ServiceStatus
    customer_name: Optional[str] = None
    service_type: Optional[str] = None
    change_request_available: bool = False
    pending_requests_detected: bool = False
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
    
    async def take_screenshot(self, browser_client: BrowserServiceClient, 
                             session_id: str, name: str) -> Optional[ScreenshotData]:
        """Capture screenshot via browser service"""
        try:
            timestamp = datetime.now()
            
            # Get screenshot from browser service
            screenshot_b64 = await browser_client.screenshot(session_id, full_page=True)
            
            # Save to file
            filename = f"{name}_{timestamp.strftime('%Y%m%d_%H%M%S')}.png"
            filepath = self.evidence_dir / filename
            
            # Decode and save
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
        """Get all screenshots taken"""
        return self.screenshots

# ==================== DATA PROCESSOR ====================

class StreamlinedDataProcessor:
    """Process extracted data into structured format"""
    
    def __init__(self, logger):
        self.logger = logger
    
    def create_streamlined_service_data(self, raw_table_data: Dict, raw_sidebar_data: Dict) -> Dict:
        """Create clean structured service data"""
        try:
            service_id = self._get_best_value(raw_table_data, ["service_id", "column_0"])
            line_reference = self._get_best_value(raw_table_data, ["line_reference", "column_1"])
            
            structured_service = {
                "service_identifiers": {
                    "primary_id": service_id,
                    "line_reference": line_reference,
                    "service_uuid": self._extract_uuids(raw_sidebar_data, "service_uuid"),
                    "line_uuid": self._extract_uuids(raw_sidebar_data, "line_uuid")
                },
                "customer_information": self._extract_customer_info(raw_table_data, raw_sidebar_data),
                "service_details": self._extract_service_details(raw_table_data, raw_sidebar_data),
                "technical_details": self._extract_technical_details(raw_table_data, raw_sidebar_data),
                "location_information": self._extract_location_info(raw_table_data, raw_sidebar_data),
                "status_information": self._extract_status_info(raw_table_data, raw_sidebar_data),
                "change_requests": self.extract_change_requests_info(raw_sidebar_data),
                "data_completeness": {
                    "has_table_data": bool(raw_table_data.get("full_row_text")),
                    "has_sidebar_data": bool(raw_sidebar_data.get("raw_sidebar_text")),
                    "has_customer_contact": bool(raw_sidebar_data.get("customer_email")),
                    "has_technical_uuids": bool(raw_sidebar_data.get("service_uuid")),
                    "has_change_requests": bool(raw_sidebar_data.get("change_requests_data", {}).get("table_rows"))
                }
            }
            
            completeness_fields = structured_service["data_completeness"]
            structured_service["data_completeness"]["overall_score"] = sum(completeness_fields.values()) / len(completeness_fields)
            
            return structured_service
            
        except Exception as e:
            self.logger.error(f"Error creating streamlined service data: {str(e)}")
            return {"processing_error": str(e)}
    
    def _extract_customer_info(self, table_data: Dict, sidebar_data: Dict) -> Dict:
        """Extract customer information"""
        customer_info = {}
        customer_name = self._get_best_value(table_data, ["column_6", "customer_name"])
        if customer_name and not customer_name.startswith("S2"):
            customer_info["name"] = customer_name
        if sidebar_data.get("customer_email"):
            customer_info["email"] = sidebar_data["customer_email"]
        if sidebar_data.get("customer_phone"):
            customer_info["phone"] = sidebar_data["customer_phone"]
        return customer_info
    
    def _extract_service_details(self, table_data: Dict, sidebar_data: Dict) -> Dict:
        """Extract service details"""
        service_details = {}
        field_mapping = {
            "type": ["column_2", "service_type"],
            "speed_profile": ["column_8", "speed_profile"],
            "start_date": ["column_4", "start_date"],
            "isp_order_number": ["column_5", "isp_order_number"]
        }
        for field_name, candidates in field_mapping.items():
            value = self._get_best_value(table_data, candidates)
            if value:
                service_details[field_name] = value
        return service_details
    
    def _extract_technical_details(self, table_data: Dict, sidebar_data: Dict) -> Dict:
        """Extract technical details"""
        technical_details = {}
        network_node = self._get_best_value(table_data, ["column_9", "network_node"])
        ont_device = self._get_best_value(table_data, ["column_10", "ont_device"])
        if network_node:
            technical_details["network_node"] = network_node
        if ont_device:
            technical_details["ont_device"] = ont_device
        service_uuids = self._extract_uuids(sidebar_data, "service_uuid")
        line_uuids = self._extract_uuids(sidebar_data, "line_uuid")
        if service_uuids:
            technical_details["service_uuid"] = service_uuids
        if line_uuids:
            technical_details["line_uuid"] = line_uuids
        return technical_details
    
    def _extract_location_info(self, table_data: Dict, sidebar_data: Dict) -> Dict:
        """Extract location information"""
        location_info = {}
        address = self._get_best_value(table_data, ["column_7", "service_address"])
        if address:
            location_info["address"] = address
        return location_info
    
    def _extract_status_info(self, table_data: Dict, sidebar_data: Dict) -> Dict:
        """Extract status information"""
        status_info = {}
        table_status = self._get_best_value(table_data, ["column_11", "table_status", "status"])
        if table_status:
            status_info["current_status"] = table_status
        sidebar_text = sidebar_data.get("raw_sidebar_text", "").lower()
        status_info["has_pending_cancellation"] = "pending cancellation" in sidebar_text
        status_info["has_change_requests"] = "change request" in sidebar_text
        return status_info
    
    def _extract_uuids(self, sidebar_data: Dict, uuid_type: str) -> List[str]:
        """Extract UUIDs"""
        uuids = sidebar_data.get(uuid_type, [])
        if isinstance(uuids, str):
            return [uuids]
        elif isinstance(uuids, list):
            return list(set(uuids))
        return []
    
    def _get_best_value(self, data: Dict, candidates: List[str]) -> str:
        """Get first non-empty value"""
        for candidate in candidates:
            value = data.get(candidate, "")
            if value and str(value).strip():
                return str(value).strip()
        return ""
    
    def extract_change_requests_info(self, service_details: Dict) -> Dict:
        """Extract change request information"""
        change_requests_data = service_details.get("change_requests_data", {})
        if not change_requests_data or change_requests_data.get("extraction_error"):
            return {
                "change_requests_found": False,
                "total_change_requests": 0,
                "first_change_request": {},
                "extraction_successful": False
            }
        
        table_rows = change_requests_data.get("table_rows", [])
        change_request_info = {
            "change_requests_found": len(table_rows) > 0,
            "total_change_requests": len(table_rows),
            "table_headers": change_requests_data.get("table_headers", []),
            "extraction_successful": True,
            "extraction_timestamp": change_requests_data.get("extraction_timestamp"),
            "raw_table_text": change_requests_data.get("raw_table_text", "")
        }
        
        if table_rows:
            first_row = table_rows[0]
            change_request_info["first_change_request"] = {
                "id": first_row.get("change_request_id", ""),
                "type": first_row.get("change_request_type", ""),
                "status": first_row.get("change_request_status", ""),
                "due_date": first_row.get("change_request_due_date", ""),
                "requested_by": first_row.get("change_request_requested_by", ""),
                "full_row_text": first_row.get("full_row_text", "")
            }
            
            change_request_info["all_change_requests"] = []
            for row in table_rows:
                clean_row = {
                    "id": row.get("change_request_id", ""),
                    "type": row.get("change_request_type", ""),
                    "status": row.get("change_request_status", ""),
                    "due_date": row.get("change_request_due_date", ""),
                    "requested_by": row.get("change_request_requested_by", ""),
                    "full_row_text": row.get("full_row_text", ""),
                    "row_index": row.get("row_index", 0)
                }
                change_request_info["all_change_requests"].append(clean_row)
        
        return change_request_info

# ==================== MAIN AUTOMATION CLASS ====================

class OctotelValidationAutomation:
    """Main automation class using browser service"""
    
    def __init__(self, browser_client: BrowserServiceClient):
        self.browser = browser_client
        self.logger = logging.getLogger(self.__class__.__name__)
        self.screenshot_service: Optional[ScreenshotService] = None
        self.session_id: Optional[str] = None
        self.original_url: Optional[str] = None
    
    async def validate_circuit(self, request: ValidationRequest) -> ValidationResult:
        """Main validation method with tab management"""
        start_time = time.time()
        
        try:
            logger.info(f"Starting validation for circuit {request.circuit_number}")
            
            # Setup services
            self.screenshot_service = ScreenshotService(request.job_id)
            
            # Create browser session
            self.session_id = await self.browser.create_session(int(request.job_id), headless=True)
            logger.info(f"Created browser session: {self.session_id}")
            
            # Save original URL (about:blank initially)
            self.original_url = await self.browser.get_current_url(self.session_id)
            
            # Take initial screenshot
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "initial_state")
            
            # Perform login with TOTP
            await self._login(request.totp_code)
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "after_login")
            
            # Navigate to services
            await self._navigate_to_services()
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "services_page")
            
            # Search for circuit
            search_result = await self._search_for_circuit(request.circuit_number)
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "search_completed")
            
            if search_result == SearchResult.ERROR:
                return self._create_error_result(request, "Search operation failed")
            
            # Get search results
            search_data = getattr(self, '_search_results', {})
            all_services = search_data.get('all_services', [])
            matching_services = search_data.get('matching_services', [])
            
            if search_result == SearchResult.NOT_FOUND:
                return self._create_not_found_result(request, all_services, time.time() - start_time)
            
            # Extract detailed info
            service_details = {}
            if matching_services:
                primary_service = matching_services[0]
                service_id = primary_service.get('service_id', '')
                
                if await self._click_service_row(service_id):
                    service_details = await self._extract_service_details(service_id)
                    await self.screenshot_service.take_screenshot(self.browser, self.session_id, "service_details")
            
            execution_time = time.time() - start_time
            result = self._create_streamlined_success_result(
                request, all_services, matching_services, service_details, execution_time
            )
            
            logger.info(f"Validation completed successfully in {execution_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"Validation failed: {str(e)}")
            if self.screenshot_service and self.session_id:
                await self.screenshot_service.take_screenshot(self.browser, self.session_id, "error_state")
            
            return ValidationResult(
                job_id=request.job_id,
                circuit_number=request.circuit_number,
                status=ValidationStatus.ERROR,
                message=str(e),
                found=False,
                search_result=SearchResult.ERROR,
                screenshots=self.screenshot_service.get_all_screenshots() if self.screenshot_service else []
            )
            
        finally:
            # Cleanup: close session
            if self.session_id:
                try:
                    await self.browser.close_session(self.session_id)
                    logger.info("Browser session closed")
                except Exception as e:
                    logger.error(f"Error closing session: {str(e)}")
    
    async def _login(self, totp_code: Optional[str]):
        """Login to Octotel portal"""
        try:
            logger.info("Starting Octotel login")
            
            # Navigate to portal
            await self.browser.navigate(self.session_id, Config.OCTOTEL_URL, wait_until="networkidle")
            
            # Find and click login button
            login_selectors = [
                "//a[contains(text(), 'Login')]",
                "#loginButton"
            ]
            
            for selector in login_selectors:
                try:
                    await self.browser.wait_for_selector(self.session_id, selector, timeout=10)
                    await self.browser.click(self.session_id, selector)
                    logger.info("Clicked login button")
                    break
                except:
                    continue
            
            # Wait for login form
            await self.browser.wait_for_selector(self.session_id, "#signInFormUsername", timeout=10)
            
            # Enter credentials
            await self.browser.type_text(self.session_id, "#signInFormUsername", Config.OCTOTEL_USERNAME)
            await self.browser.type_text(self.session_id, "#signInFormPassword", Config.OCTOTEL_PASSWORD)
            
            # Submit
            await self.browser.click(self.session_id, "button[name='signInSubmitButton']")
            
            # Handle TOTP
            await self._handle_totp(totp_code)
            
            # Wait for dashboard
            await self.browser.wait_for_selector(
                self.session_id,
                "div.navbar li:nth-of-type(2) > a",
                timeout=20
            )
            
            logger.info("Login successful")
            
        except Exception as e:
            raise BrowserServiceError(f"Login failed: {str(e)}")
    
    async def _handle_totp(self, totp_code: Optional[str]):
        """Handle TOTP authentication"""
        try:
            if not totp_code:
                # Generate TOTP if not provided
                import pyotp
                totp = pyotp.TOTP(Config.OCTOTEL_TOTP_SECRET)
                totp_code = totp.now()
                logger.info("Generated TOTP code locally")
            else:
                logger.info("Using TOTP code from orchestrator")
            
            # Wait for TOTP input
            await self.browser.wait_for_selector(self.session_id, "#totpCodeInput", timeout=12)
            
            # Enter TOTP
            await self.browser.type_text(self.session_id, "#totpCodeInput", totp_code)
            
            # Submit
            await self.browser.click(self.session_id, "#signInButton")
            await self.browser.wait_for_timeout(self.session_id, 3000)
            
        except Exception as e:
            raise BrowserServiceError(f"TOTP authentication failed: {str(e)}")
    
    async def _navigate_to_services(self):
        """Navigate to Services page"""
        try:
            logger.info("Navigating to Services page")
            await self.browser.click(self.session_id, "div.navbar li:nth-of-type(2) > a")
            await self.browser.wait_for_timeout(self.session_id, 3000)
            logger.info("Navigated to Services")
        except Exception as e:
            raise BrowserServiceError(f"Failed to navigate to services: {str(e)}")
    
    async def _search_for_circuit(self, circuit_number: str) -> SearchResult:
        """Search for circuit"""
        try:
            logger.info(f"Searching for circuit: {circuit_number}")
            
            # Configure filters
            await self._configure_status_filters()
            
            # Enter search term
            await self.browser.type_text(self.session_id, "#search", circuit_number, clear=True)
            await self.browser.press_key(self.session_id, "Enter")
            
            await self.browser.wait_for_timeout(self.session_id, 5000)
            
            # Extract services
            all_services = await self._extract_all_services()
            
            # Filter matching
            matching_services = []
            search_term_lower = circuit_number.lower()
            for service in all_services:
                fields_to_check = [
                    service.get("full_row_text", ""),
                    service.get("service_id", ""),
                    service.get("line_reference", "")
                ]
                for field_value in fields_to_check:
                    if field_value and search_term_lower in str(field_value).lower():
                        matching_services.append(service)
                        break
            
            self._search_results = {
                'all_services': all_services,
                'matching_services': matching_services,
                'search_term': circuit_number
            }
            
            logger.info(f"Found {len(matching_services)} matching services")
            
            return SearchResult.FOUND if matching_services else SearchResult.NOT_FOUND
            
        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
            return SearchResult.ERROR
    
    async def _configure_status_filters(self):
        """Configure status filters"""
        try:
            # Set filters using execute_script
            await self.browser.execute_script(
                self.session_id,
                """
                let selects = document.querySelectorAll('select');
                if (selects[0]) selects[0].value = '';
                if (selects[2]) selects[2].value = '1';
                """
            )
            await self.browser.wait_for_timeout(self.session_id, 1000)
        except Exception as e:
            logger.warning(f"Could not set filters: {str(e)}")
    
    async def _extract_all_services(self) -> List[Dict]:
        """Extract all services from table"""
        try:
            # Get table HTML
            table_html = await self.browser.execute_script(
                self.session_id,
                """
                let table = document.querySelector('table');
                return table ? table.outerHTML : '';
                """
            )
            
            # Parse table (simplified - you'd need proper HTML parsing)
            services = []
            # This is a simplified version - implement proper table parsing
            return services
            
        except Exception:
            return []
    
    async def _click_service_row(self, service_id: str) -> bool:
        """Click service row"""
        try:
            await self.browser.click(self.session_id, f"//tr[contains(., '{service_id}')]")
            await self.browser.wait_for_timeout(self.session_id, 2000)
            return True
        except:
            return False
    
    async def _extract_service_details(self, service_id: str) -> Dict:
        """Extract service details"""
        try:
            await self.browser.wait_for_timeout(self.session_id, 2000)
            
            # Get sidebar text
            sidebar_text = await self.browser.get_text(self.session_id, ".sidebar")
            
            service_details = {
                "extraction_timestamp": datetime.now().isoformat(),
                "raw_sidebar_text": sidebar_text,
                "service_id": service_id
            }
            
            # Extract patterns
            patterns = {
                "customer_email": r"[\w\.-]+@[\w\.-]+\.\w+",
                "customer_phone": r"[\+]?[1-9]?[0-9]{7,14}",
                "service_uuid": r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
            }
            
            for field_name, pattern in patterns.items():
                matches = re.findall(pattern, sidebar_text, re.IGNORECASE)
                if matches:
                    service_details[field_name] = matches[0] if len(matches) == 1 else matches
            
            return service_details
            
        except Exception as e:
            return {"error": str(e)}
    
    def _create_streamlined_success_result(self, request: ValidationRequest, all_services: List[Dict],
                                          matching_services: List[Dict], service_details: Dict,
                                          execution_time: float) -> ValidationResult:
        """Create success result"""
        processor = StreamlinedDataProcessor(self.logger)
        
        structured_services = []
        for raw_service in matching_services:
            structured_service = processor.create_streamlined_service_data(raw_service, service_details)
            structured_services.append(structured_service)
        
        details = {
            "services": structured_services,
            "extraction_metadata": {
                "total_services_found": len(matching_services),
                "search_term": request.circuit_number,
                "extraction_timestamp": datetime.now().isoformat()
            }
        }
        
        return ValidationResult(
            job_id=request.job_id,
            circuit_number=request.circuit_number,
            status=ValidationStatus.SUCCESS,
            message=f"Successfully extracted {len(matching_services)} services",
            found=True,
            search_result=SearchResult.FOUND,
            execution_time=execution_time,
            screenshots=self.screenshot_service.get_all_screenshots(),
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
            screenshots=self.screenshot_service.get_all_screenshots() if self.screenshot_service else []
        )
    
    def _create_not_found_result(self, request: ValidationRequest, all_services: List[Dict],
                                 execution_time: float) -> ValidationResult:
        """Create not found result"""
        return ValidationResult(
            job_id=request.job_id,
            circuit_number=request.circuit_number,
            status=ValidationStatus.SUCCESS,
            message=f"Circuit {request.circuit_number} not found",
            found=False,
            search_result=SearchResult.NOT_FOUND,
            execution_time=execution_time,
            screenshots=self.screenshot_service.get_all_screenshots(),
            details={"total_services_searched": len(all_services)}
        )

# ==================== EXECUTE FUNCTION ====================

async def execute(parameters: Dict[str, Any], browser_client: BrowserServiceClient) -> Dict[str, Any]:
    """Main execution function for worker"""
    try:
        # Validate configuration
        if not all([Config.OCTOTEL_USERNAME, Config.OCTOTEL_PASSWORD, Config.OCTOTEL_TOTP_SECRET]):
            return {
                "status": "error",
                "message": "Missing required Octotel configuration",
                "details": {"error": "configuration_missing"},
                "screenshot_data": []
            }
        
        # Create validation request
        request = ValidationRequest(
            job_id=parameters.get("job_id"),
            circuit_number=parameters.get("circuit_number"),
            totp_code=parameters.get("totp_code")  # From orchestrator
        )
        
        logger.info(f"Starting validation for circuit: {request.circuit_number}")
        
        # Execute validation
        automation = OctotelValidationAutomation(browser_client)
        result = await automation.validate_circuit(request)
        
        # Convert to dictionary
        result_dict = {
            "status": result.status.value,
            "message": result.message,
            "details": result.details or {"found": result.found},
            "screenshot_data": [
                {
                    "name": screenshot.name,
                    "timestamp": screenshot.timestamp.isoformat(),
                    "base64_data": screenshot.data
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
