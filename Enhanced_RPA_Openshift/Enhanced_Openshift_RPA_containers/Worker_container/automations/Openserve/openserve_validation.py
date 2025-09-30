"""
Openserve Validation Automation - Browser Service Version
=========================================================
Refactored from OSN to Openserve with browser service support.
Includes Forcepoint certificate bypass handling.
"""

import base64
import traceback
from pathlib import Path
from datetime import datetime
import time
import logging
import json
from typing import Optional, List, Dict, Any
from enum import Enum
import re

from pydantic import BaseModel, Field

from config import Config
from browser_client import BrowserServiceClient, BrowserServiceError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== ENUMERATIONS ====================

class ValidationStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"

class SearchResult(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    ERROR = "error"

class OrderType(str, Enum):
    NEW_INSTALLATION = "new_installation"
    CEASE_ACTIVE_SERVICE = "cease_active_service"
    MODIFICATION = "modification"
    UNKNOWN = "unknown"

# ==================== DATA MODELS ====================

class ValidationRequest(BaseModel):
    job_id: str = Field(..., description="Unique job identifier")
    circuit_number: str = Field(..., description="Circuit number to validate")

class ScreenshotData(BaseModel):
    name: str
    timestamp: datetime
    data: str
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

class OrderData(BaseModel):
    orderNumber: str
    type: OrderType
    orderStatus: str
    dateImplemented: Optional[str] = None
    is_new_installation: bool = False
    is_cancellation: bool = False
    is_implemented_cease: bool = False
    is_pending_cease: bool = False
    serviceNumber: Optional[str] = None
    externalRef: Optional[str] = ""
    productName: Optional[str] = ""
    createdOn: Optional[str] = ""

class CustomerDetails(BaseModel):
    name: str = ""
    surname: str = ""
    contact_number: str = ""
    email: str = ""
    order_number: str = ""
    domicile_type: str = ""
    address: str = ""

class CeaseOrderDetails(BaseModel):
    order_number: str
    placed_by: str = ""
    date_submitted: str = ""
    requested_cease_date: str = ""
    product: str = ""
    order_type: str = ""
    service_circuit_no: str = ""
    external_ref: str = ""

class ServiceInfo(BaseModel):
    circuit_number: str
    address: Optional[str] = None
    is_active: bool = False

class ValidationResult(BaseModel):
    job_id: str
    circuit_number: str
    status: ValidationStatus
    message: str
    found: bool
    orders: List[OrderData] = []
    customer_details: Optional[CustomerDetails] = None
    cease_order_details: List[CeaseOrderDetails] = []
    service_info: Optional[ServiceInfo] = None
    search_result: SearchResult
    execution_time: Optional[float] = None
    screenshots: List[ScreenshotData] = []

# ==================== SCREENSHOT SERVICE ====================

class ScreenshotService:
    """Screenshot service for evidence"""
    
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

# ==================== MAIN AUTOMATION CLASS ====================

class OpenserveValidationAutomation:
    """Openserve validation with browser service"""
    
    def __init__(self, browser_client: BrowserServiceClient):
        self.browser = browser_client
        self.logger = logging.getLogger(self.__class__.__name__)
        self.screenshot_service: Optional[ScreenshotService] = None
        self.session_id: Optional[str] = None
    
    async def validate_circuit(self, request: ValidationRequest) -> ValidationResult:
        """Main validation method"""
        start_time = time.time()
        
        try:
            logger.info(f"Starting validation for {request.circuit_number}")
            
            # Setup
            self.screenshot_service = ScreenshotService(request.job_id)
            self.session_id = await self.browser.create_session(int(request.job_id), headless=True)
            
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "initial")
            
            # Login with Forcepoint handling
            await self._login_with_bypass()
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "after_login")
            
            # Get orders
            await self._navigate_to_orders(request.circuit_number)
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "orders_page")
            
            orders = await self._extract_orders()
            
            # Get address
            await self._navigate_to_active_services(request.circuit_number)
            await self.screenshot_service.take_screenshot(self.browser, self.session_id, "active_services")
            
            address = await self._extract_address()
            
            # Check if exists
            circuit_exists = len(orders) > 0 or address is not None
            if not circuit_exists:
                return self._create_not_found_result(request)
            
            # Extract customer details
            customer_details = CustomerDetails()
            new_orders = [o for o in orders if o.is_new_installation]
            if new_orders:
                for order in new_orders:
                    try:
                        await self._navigate_to_order_details(order.orderNumber, "new_installation")
                        await self.screenshot_service.take_screenshot(self.browser, self.session_id, f"customer_{order.orderNumber}")
                        customer_details = await self._extract_customer_details(order.orderNumber)
                        if customer_details and any(getattr(customer_details, f) for f in ['name', 'surname', 'contact_number']):
                            break
                    except:
                        continue
            
            # Extract cease details
            cease_details = []
            cease_orders = [o for o in orders if o.is_cancellation and o.is_pending_cease]
            if cease_orders:
                for order in cease_orders:
                    try:
                        await self._navigate_to_order_details(order.orderNumber, "cease")
                        await self.screenshot_service.take_screenshot(self.browser, self.session_id, f"cease_{order.orderNumber}")
                        cease = await self._extract_cease_details(order.orderNumber)
                        if cease:
                            cease_details.append(cease)
                    except:
                        continue
            
            # Service info
            service_info = ServiceInfo(
                circuit_number=request.circuit_number,
                address=address,
                is_active=address is not None and not any(o.is_implemented_cease for o in orders if o.is_cancellation)
            )
            
            execution_time = time.time() - start_time
            
            result = ValidationResult(
                job_id=request.job_id,
                circuit_number=request.circuit_number,
                status=ValidationStatus.SUCCESS,
                message=f"Validation completed for {request.circuit_number}",
                found=True,
                orders=orders,
                customer_details=customer_details,
                cease_order_details=cease_details,
                service_info=service_info,
                search_result=SearchResult.FOUND,
                execution_time=execution_time,
                screenshots=self.screenshot_service.get_all_screenshots()
            )
            
            logger.info(f"Validation completed in {execution_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"Validation failed: {str(e)}")
            if self.screenshot_service and self.session_id:
                await self.screenshot_service.take_screenshot(self.browser, self.session_id, "error")
            
            return ValidationResult(
                job_id=request.job_id,
                circuit_number=request.circuit_number,
                status=ValidationStatus.ERROR,
                message=str(e),
                found=False,
                cease_order_details=[],
                search_result=SearchResult.ERROR,
                screenshots=self.screenshot_service.get_all_screenshots() if self.screenshot_service else []
            )
        finally:
            if self.session_id:
                await self.browser.close_session(self.session_id)
    
    async def _login_with_bypass(self):
        """Login with Forcepoint certificate bypass"""
        try:
            logger.info("Navigating to Openserve with Forcepoint bypass")
            await self.browser.navigate(self.session_id, "https://partners.openserve.co.za/login")
            await self.browser.wait_for_timeout(self.session_id, 3000)
            
            # Handle Forcepoint bypass
            page_source = await self.browser.get_page_content(self.session_id)
            if "Certificate verification error" in page_source:
                logger.info("Detected Forcepoint - attempting bypass")
                try:
                    await self.browser.click(self.session_id, "//input[@value='   Visit Site anyway   ']")
                    await self.browser.wait_for_timeout(self.session_id, 3000)
                except:
                    # Fallback: submit form
                    await self.browser.execute_script(self.session_id, "document.forms['ask'].submit();")
                    await self.browser.wait_for_timeout(self.session_id, 3000)
            
            # Wait for login page
            await self.browser.wait_for_timeout(self.session_id, 5000)
            await self.browser.wait_for_selector(self.session_id, "#email", timeout=30)
            
            # Enter credentials
            await self.browser.type_text(self.session_id, "#email", Config.OSEMAIL, clear=True)
            await self.browser.type_text(self.session_id, "#password", Config.OSPASSWORD, clear=True)
            
            # Submit
            await self.browser.click(self.session_id, "#next")
            
            # Wait for dashboard
            await self.browser.wait_for_selector(self.session_id, "#navOrders", timeout=30)
            logger.info("Login successful")
            
        except Exception as e:
            raise BrowserServiceError(f"Login failed: {str(e)}")
    
    async def _navigate_to_orders(self, circuit_number: str):
        """Navigate to orders page"""
        url = f"https://partners.openserve.co.za/orders?tabIndex=2&isps=628&serviceNumber={circuit_number}"
        await self.browser.navigate(self.session_id, url)
        await self.browser.wait_for_timeout(self.session_id, 5000)
    
    async def _extract_orders(self) -> List[OrderData]:
        """Extract orders from table"""
        orders = []
        try:
            await self.browser.wait_for_selector(self.session_id, "//table//tbody//tr", timeout=30)
            
            # Extract via JavaScript
            order_data = await self.browser.execute_script(
                self.session_id,
                """
                const rows = document.querySelectorAll('table tbody tr[td]');
                const orders = [];
                
                rows.forEach(row => {
                    const cells = row.querySelectorAll('td');
                    if (cells.length >= 3) {
                        const orderInfo = {
                            orderNumber: cells[0]?.textContent.trim() || '',
                            type: cells[1]?.textContent.trim() || '',
                            externalRef: cells[2]?.textContent.trim() || '',
                            serviceNumber: cells[3]?.textContent.trim() || '',
                            productName: cells[4]?.textContent.trim() || '',
                            createdOn: cells[5]?.textContent.trim() || '',
                            dateImplemented: cells[6]?.textContent.trim() || '',
                            orderStatus: cells[7]?.textContent.trim() || ''
                        };
                        orders.push(orderInfo);
                    }
                });
                
                return orders;
                """
            )
            
            # Process orders
            for info in order_data:
                type_text = info.get("type", "").lower()
                status = info.get("orderStatus", "")
                date_impl = info.get("dateImplemented", "")
                
                if "new" in type_text or "installation" in type_text:
                    order_type = OrderType.NEW_INSTALLATION
                    is_new = True
                    is_cancel = False
                elif "cease" in type_text:
                    order_type = OrderType.CEASE_ACTIVE_SERVICE
                    is_new = False
                    is_cancel = True
                else:
                    order_type = OrderType.MODIFICATION if "modif" in type_text else OrderType.UNKNOWN
                    is_new = False
                    is_cancel = False
                
                order = OrderData(
                    orderNumber=info.get("orderNumber", ""),
                    type=order_type,
                    orderStatus=status,
                    dateImplemented=date_impl,
                    is_new_installation=is_new,
                    is_cancellation=is_cancel,
                    serviceNumber=info.get("serviceNumber", ""),
                    externalRef=info.get("externalRef", ""),
                    productName=info.get("productName", ""),
                    createdOn=info.get("createdOn", "")
                )
                
                if is_cancel:
                    if date_impl and status.lower() == "accepted":
                        order.is_implemented_cease = True
                        order.is_pending_cease = False
                    else:
                        order.is_implemented_cease = False
                        order.is_pending_cease = True
                
                orders.append(order)
            
            logger.info(f"Extracted {len(orders)} orders")
        except Exception as e:
            logger.error(f"Failed to extract orders: {str(e)}")
        
        return orders
    
    async def _navigate_to_active_services(self, circuit_number: str):
        """Navigate to active services"""
        url = f"https://partners.openserve.co.za/active-services/{circuit_number}"
        await self.browser.navigate(self.session_id, url)
        await self.browser.wait_for_timeout(self.session_id, 10000)
    
    async def _extract_address(self) -> Optional[str]:
        """Extract address from active services"""
        try:
            # Click Service Information button
            clicked = await self.browser.execute_script(
                self.session_id,
                """
                var heading = document.evaluate(
                    "//h2[contains(text(), 'Service Information')]",
                    document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
                ).singleNodeValue;
                
                if (heading) {
                    var card = heading.closest('div.card, div.col, div');
                    if (card) {
                        var btn = card.querySelector('button');
                        if (btn) {
                            btn.click();
                            return true;
                        }
                    }
                }
                return false;
                """
            )
            
            if clicked:
                await self.browser.wait_for_timeout(self.session_id, 5000)
                
                # Click Service end points tab
                await self.browser.execute_script(
                    self.session_id,
                    """
                    var tabs = Array.from(document.querySelectorAll('span.p-tabview-title'))
                        .filter(s => s.textContent.includes('Service end points'));
                    if (tabs.length > 0) {
                        var link = tabs[0].closest('a');
                        if (link) link.click();
                    }
                    """
                )
                
                await self.browser.wait_for_timeout(self.session_id, 3000)
                
                # Extract address
                address = await self.browser.execute_script(
                    self.session_id,
                    """
                    var aside = document.evaluate(
                        "//p[contains(text(), 'A-Side')]",
                        document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
                    ).singleNodeValue;
                    
                    if (aside) {
                        var container = aside.closest('div.col, div');
                        if (container) {
                            var rows = container.querySelectorAll('.row');
                            for (var row of rows) {
                                var label = row.querySelector('p.fw-bold');
                                if (label && label.textContent.includes('Site Address')) {
                                    var cols = row.querySelectorAll('div');
                                    if (cols[1]) return cols[1].textContent.trim();
                                }
                            }
                        }
                    }
                    return null;
                    """
                )
                
                if address:
                    logger.info(f"Extracted address: {address}")
                    return address
            
            return None
        except Exception as e:
            logger.error(f"Address extraction failed: {str(e)}")
            return None
    
    async def _navigate_to_order_details(self, order_number: str, order_type: str):
        """Navigate to order details"""
        if order_type == "new_installation":
            url = f"https://partners.openserve.co.za/orders/orders-complete/{order_number}/New%20Installation"
        else:
            url = f"https://partners.openserve.co.za/orders/orders-pending/{order_number}/Cease%20Active%20Service"
        
        await self.browser.navigate(self.session_id, url)
        await self.browser.wait_for_timeout(self.session_id, 5000)
    
    async def _extract_customer_details(self, order_number: str) -> Optional[CustomerDetails]:
        """Extract customer details with JavaScript"""
        try:
            current_url = await self.browser.get_current_url(self.session_id)
            if "orders-complete" not in current_url:
                return None
            
            details = CustomerDetails(order_number=order_number)
            
            customer_data = await self.browser.execute_script(
                self.session_id,
                """
                var text = document.body.textContent;
                var result = {};
                
                var start = text.indexOf("Customer Details");
                var section = "";
                if (start !== -1) {
                    var end = text.indexOf("Appointment", start);
                    section = end !== -1 ? text.substring(start, end) : text.substring(start, start + 500);
                }
                
                var patterns = {
                    name: /Name\\s*:\\s*([^:]*?)(?=Surname\\s*:|$)/i,
                    surname: /Surname\\s*:\\s*([^:]*?)(?=Mobile Number\\s*:|$)/i,
                    mobile_number: /Mobile Number\\s*:\\s*([^:]*?)(?=Domicile|Email|$)/i,
                    domicile_type: /Domicile type\\s*:\\s*([^:]*?)(?=Address\\s*:|$)/i,
                    address: /Address\\s*:\\s*([^:]*?)(?=Appointment|Email|$)/i,
                    email: /Email\\s*:\\s*([\\w.-]+@[\\w.-]+\\.[a-zA-Z]{2,})/i
                };
                
                for (var field in patterns) {
                    var match = section.match(patterns[field]);
                    if (match && match[1]) {
                        var value = match[1].trim().replace(/\\s+/g, ' ').replace(/^[,\\s]+|[,\\s]+$/g, '');
                        if (value.length > 0) result[field] = value;
                    }
                }
                
                if (result.mobile_number) {
                    var digits = result.mobile_number.replace(/\\D/g, '');
                    if (digits.length >= 10) result.mobile_number = digits.substring(0, 10);
                }
                
                return result;
                """
            )
            
            if customer_data:
                details.name = customer_data.get('name', "").strip()
                details.surname = customer_data.get('surname', "").strip()
                details.contact_number = customer_data.get('mobile_number', "").strip()
                details.email = customer_data.get('email', "").strip()
                details.domicile_type = customer_data.get('domicile_type', "").strip()
                details.address = customer_data.get('address', "").strip()
            
            logger.info(f"Extracted customer: {details.name} {details.surname}")
            return details
            
        except Exception as e:
            logger.error(f"Customer extraction failed: {str(e)}")
            return None
    
    async def _extract_cease_details(self, order_number: str) -> Optional[CeaseOrderDetails]:
        """Extract cease order details"""
        try:
            current_url = await self.browser.get_current_url(self.session_id)
            if "orders-pending" not in current_url:
                return None
            
            details = CeaseOrderDetails(order_number=order_number)
            
            order_data = await self.browser.execute_script(
                self.session_id,
                """
                var text = document.body.textContent;
                var result = {};
                
                var start = text.indexOf("Order Details");
                var section = "";
                if (start !== -1) {
                    var end = text.indexOf("Notifications", start);
                    section = end !== -1 ? text.substring(start, end) : text.substring(start, start + 800);
                }
                
                var patterns = {
                    placed_by: /Placed by\\s*:\\s*([^:]*?)(?=Date Submitted\\s*:|$)/i,
                    date_submitted: /Date Submitted\\s*:\\s*([^:]*?)(?=Requested Cease Date\\s*:|$)/i,
                    requested_cease_date: /Requested Cease Date\\s*:\\s*([^:]*?)(?=Product\\s*:|$)/i,
                    product: /Product\\s*:\\s*([^:]*?)(?=Service speed\\s*:|Order type\\s*:|$)/i,
                    order_type: /Order type\\s*:\\s*([^:]*?)(?=Contract term\\s*:|Service\\s*:|$)/i,
                    service_circuit_no: /Service\\/Circuit no\\.\\s*:\\s*([^:]*?)(?=External Ref\\s*:|$)/i,
                    external_ref: /External Ref\\.\\s*:\\s*([^:]*?)(?=Remark\\s*:|$)/i
                };
                
                for (var field in patterns) {
                    var match = section.match(patterns[field]);
                    if (match && match[1]) {
                        var value = match[1].trim().replace(/\\s+/g, ' ').replace(/^[,\\s]+|[,\\s]+$/g, '');
                        if (value.length > 0) result[field] = value;
                    }
                }
                
                return result;
                """
            )
            
            if order_data:
                details.placed_by = order_data.get('placed_by', "").strip()
                details.date_submitted = order_data.get('date_submitted', "").strip()
                details.requested_cease_date = order_data.get('requested_cease_date', "").strip()
                details.product = order_data.get('product', "").strip()
                details.order_type = order_data.get('order_type', "").strip()
                details.service_circuit_no = order_data.get('service_circuit_no', "").strip()
                details.external_ref = order_data.get('external_ref', "").strip()
            
            logger.info(f"Extracted cease details for {order_number}")
            return details
            
        except Exception as e:
            logger.error(f"Cease extraction failed: {str(e)}")
            return None
    
    def _create_not_found_result(self, request: ValidationRequest) -> ValidationResult:
        """Create not found result"""
        return ValidationResult(
            job_id=request.job_id,
            circuit_number=request.circuit_number,
            status=ValidationStatus.SUCCESS,
            message=f"Circuit {request.circuit_number} not found",
            found=False,
            cease_order_details=[],
            search_result=SearchResult.NOT_FOUND,
            screenshots=self.screenshot_service.get_all_screenshots() if self.screenshot_service else []
        )

# ==================== EXECUTE FUNCTION ====================

async def execute(parameters: Dict[str, Any], browser_client: BrowserServiceClient) -> Dict[str, Any]:
    """Execute Openserve validation"""
    try:
        request = ValidationRequest(
            job_id=parameters.get("job_id"),
            circuit_number=parameters.get("circuit_number")
        )
        
        automation = OpenserveValidationAutomation(browser_client)
        result = await automation.validate_circuit(request)
        
        # Format result
        result_dict = {
            "status": result.status.value,
            "message": result.message,
            "details": {
                "found": result.found,
                "circuit_number": result.circuit_number,
                "search_result": result.search_result.value,
                "order_data": [order.dict() for order in result.orders],
                "service_info": result.service_info.dict() if result.service_info else None,
                "order_count": len(result.orders),
                "has_new_installation": any(o.is_new_installation for o in result.orders),
                "has_cancellation": any(o.is_cancellation for o in result.orders),
                "has_pending_cease": any(o.is_cancellation and not o.is_implemented_cease for o in result.orders),
                "customer_details": result.customer_details.dict() if result.customer_details else {},
                "cease_order_details": [c.dict() for c in result.cease_order_details],
            },
            "screenshot_data": [
                {"name": s.name, "timestamp": s.timestamp.isoformat(), "base64_data": s.data}
                for s in result.screenshots
            ],
            "execution_time": result.execution_time
        }
        
        return result_dict
        
    except Exception as e:
        logger.error(f"Execute failed: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "details": {"error": str(e), "found": False},
            "screenshot_data": []
        }
