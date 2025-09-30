"""
MFN (MetroFiber) Validation Module
===================================
Service validation automation for MetroFiber portal using Playwright via browser service.

Architecture:
    Worker → Browser Service → Firefox (Playwright)
    
This module:
- Uses browser service client for all browser operations
- Receives pre-generated TOTP from orchestrator
- Implements validation business logic
- Returns standardized results
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
import asyncio
import os

from provider_factory import BaseAutomation, AutomationError
from config import Config

logger = logging.getLogger(__name__)


class MFNValidation(BaseAutomation):
    """MetroFiber service validation automation"""
    
    # Portal configuration
    PORTAL_URL = os.getenv("METROFIBER_URL", "https://ftth.metrofibre.co.za/")
    EMAIL = os.getenv("EMAIL", "vcappont2.bot@vcontractor.co.za")
    PASSWORD = os.getenv("PASSWORD", "")
    
    # Timeouts
    WAIT_TIMEOUT = 15
    NAVIGATION_TIMEOUT = 30
    
    def __init__(self, browser_client):
        super().__init__(browser_client)
        self.job_id = None
        self.screenshots = []
        self.service_location = None
        
        if not all([self.PORTAL_URL, self.EMAIL, self.PASSWORD]):
            raise ValueError("Missing MFN portal configuration")
    
    async def execute(self, job_id: int, parameters: Dict) -> Dict:
        """
        Execute MFN validation
        
        Parameters:
            - circuit_number: Service circuit number (required)
            - customer_name: Customer name (optional)
            - customer_id: Customer ID (optional)
            - fsan: FSAN (optional)
        """
        self.job_id = job_id
        logger.info(f"Job {job_id}: Starting MFN validation")
        
        # Extract parameters
        circuit_number = parameters.get("circuit_number") or parameters.get("order_id")
        customer_name = parameters.get("customer_name", "")
        customer_id = parameters.get("customer_id", "")
        fsan = parameters.get("fsan", "")
        
        if not circuit_number:
            raise AutomationError("circuit_number or order_id is required")
        
        try:
            # Create browser session
            await self.create_session(job_id)
            
            # Execute validation workflow
            logger.info(f"Job {job_id}: Logging into MFN portal")
            await self._login()
            
            logger.info(f"Job {job_id}: Searching for circuit {circuit_number}")
            service_found = await self._search_service(
                circuit_number, customer_name, customer_id, fsan
            )
            
            if not service_found:
                logger.info(f"Job {job_id}: Service not found")
                return self._build_not_found_result()
            
            logger.info(f"Job {job_id}: Extracting service details")
            service_data = await self._extract_service_details(circuit_number)
            
            logger.info(f"Job {job_id}: Checking service history")
            history_data = await self._check_service_history()
            
            # Build result
            result = self._build_success_result(service_data, history_data)
            
            logger.info(f"Job {job_id}: MFN validation completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"Job {job_id}: MFN validation failed - {str(e)}")
            screenshot = await self.take_screenshot("error")
            raise AutomationError(f"MFN validation failed: {str(e)}")
        
        finally:
            await self.cleanup()
    
    async def _login(self):
        """Login to MFN portal"""
        try:
            # Navigate to portal
            await self.browser.navigate(
                self.session_id,
                self.PORTAL_URL,
                wait_until="networkidle"
            )
            
            # Wait for login form
            await self.browser.wait_for_selector(
                self.session_id,
                "input[name='email']",
                timeout=self.WAIT_TIMEOUT
            )
            
            # Fill login form
            await self.browser.type_text(
                self.session_id,
                "input[name='email']",
                self.EMAIL
            )
            
            await self.browser.type_text(
                self.session_id,
                "input[name='password']",
                self.PASSWORD
            )
            
            # Submit form
            await self.browser.click(self.session_id, "button[type='submit']")
            
            # Wait for navigation to main page
            await asyncio.sleep(2)
            
            # Verify login success
            current_url = await self.browser.get_current_url(self.session_id)
            if "main.php" not in current_url.lower():
                screenshot = await self.take_screenshot("login_failed")
                raise AutomationError("Login failed - did not reach main page")
            
            logger.info(f"Job {self.job_id}: Login successful")
            
        except Exception as e:
            raise AutomationError(f"Login failed: {str(e)}")
    
    async def _search_service(self, circuit_number: str, customer_name: str = "", 
                             customer_id: str = "", fsan: str = "") -> bool:
        """
        Search for service in MFN portal
        
        Returns:
            True if service found, False otherwise
        """
        try:
            # Navigate to search page
            search_url = f"{self.PORTAL_URL}customerSearch.php"
            await self.browser.navigate(self.session_id, search_url, wait_until="networkidle")
            
            # Wait for search form
            await self.browser.wait_for_selector(
                self.session_id,
                "input[name='circuit_number']",
                timeout=self.WAIT_TIMEOUT
            )
            
            # Try circuit number search first
            if circuit_number:
                logger.info(f"Job {self.job_id}: Searching by circuit number: {circuit_number}")
                await self.browser.type_text(
                    self.session_id,
                    "input[name='circuit_number']",
                    circuit_number
                )
                
                await self.browser.click(self.session_id, "button[name='search']")
                await asyncio.sleep(2)
                
                # Check if service found
                service_found = await self._check_search_results()
                if service_found:
                    self.service_location = "circuit_search"
                    return True
            
            # Try customer name search
            if customer_name:
                logger.info(f"Job {self.job_id}: Searching by customer name: {customer_name}")
                await self.browser.navigate(self.session_id, search_url)
                await self.browser.type_text(
                    self.session_id,
                    "input[name='customer_name']",
                    customer_name
                )
                await self.browser.click(self.session_id, "button[name='search']")
                await asyncio.sleep(2)
                
                service_found = await self._check_search_results()
                if service_found:
                    self.service_location = "customer_search"
                    return True
            
            # Try FSAN search
            if fsan:
                logger.info(f"Job {self.job_id}: Searching by FSAN: {fsan}")
                await self.browser.navigate(self.session_id, search_url)
                await self.browser.type_text(
                    self.session_id,
                    "input[name='fsan']",
                    fsan
                )
                await self.browser.click(self.session_id, "button[name='search']")
                await asyncio.sleep(2)
                
                service_found = await self._check_search_results()
                if service_found:
                    self.service_location = "fsan_search"
                    return True
            
            logger.info(f"Job {self.job_id}: Service not found in any search")
            return False
            
        except Exception as e:
            raise AutomationError(f"Search failed: {str(e)}")
    
    async def _check_search_results(self) -> bool:
        """Check if search returned results"""
        try:
            # Check for "no results" message
            no_results_visible = await self.browser.is_visible(
                self.session_id,
                "text='No results found'",
                timeout=3
            )
            
            if no_results_visible:
                return False
            
            # Check for results table
            results_table_visible = await self.browser.is_visible(
                self.session_id,
                "table.results",
                timeout=3
            )
            
            return results_table_visible
            
        except:
            return False
    
    async def _extract_service_details(self, circuit_number: str) -> Dict[str, Any]:
        """Extract service details from detail page"""
        try:
            # Click on service to open details
            await self.browser.click(
                self.session_id,
                f"a[data-circuit='{circuit_number}']"
            )
            await asyncio.sleep(2)
            
            # Wait for detail page
            await self.browser.wait_for_selector(
                self.session_id,
                "#service-details",
                timeout=self.WAIT_TIMEOUT
            )
            
            # Extract fields
            details = {}
            
            # List of fields to extract
            fields = {
                "customer_name": "#customer",
                "customer_id": "#customer_id_number",
                "email": "#mail",
                "mobile": "#mobile_number",
                "address": "#ad1",
                "fsan": "#fsan",
                "activation_date": "#activation",
                "package": "#package_upgrade_mrc",
                "status": "#systemDate",
                "circuit_number": "#id"
            }
            
            for field_name, selector in fields.items():
                try:
                    value = await self.browser.get_text(
                        self.session_id,
                        selector,
                        timeout=5
                    )
                    details[field_name] = value.strip()
                except:
                    details[field_name] = ""
                    logger.warning(f"Could not extract field: {field_name}")
            
            # Take screenshot of details
            screenshot = await self.take_screenshot("service_details")
            self.screenshots.append({
                "name": "service_details",
                "data": screenshot,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            return details
            
        except Exception as e:
            raise AutomationError(f"Failed to extract service details: {str(e)}")
    
    async def _check_service_history(self) -> Dict[str, Any]:
        """Check service history for cancellations"""
        try:
            # Click history button
            await self.browser.click(self.session_id, "button#history")
            await asyncio.sleep(2)
            
            # Wait for history table
            await self.browser.wait_for_selector(
                self.session_id,
                "table#history-table",
                timeout=self.WAIT_TIMEOUT
            )
            
            # Extract history records
            history_rows = await self.browser.query_all(
                self.session_id,
                "table#history-table tbody tr"
            )
            
            cancellation_found = False
            cancellation_captured = False
            
            for row in history_rows:
                # Check if row contains cancellation
                row_text = row.get("text", "").lower()
                if "cancellation" in row_text or "cancel" in row_text:
                    cancellation_found = True
                    if "captured" in row_text:
                        cancellation_captured = True
                        break
            
            # Take screenshot
            screenshot = await self.take_screenshot("service_history")
            self.screenshots.append({
                "name": "service_history",
                "data": screenshot,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            return {
                "cancellation_found": cancellation_found,
                "cancellation_captured": cancellation_captured,
                "total_records": len(history_rows)
            }
            
        except Exception as e:
            logger.warning(f"Failed to check history: {str(e)}")
            return {
                "cancellation_found": False,
                "cancellation_captured": False,
                "total_records": 0
            }
    
    def _build_success_result(self, service_data: Dict, history_data: Dict) -> Dict:
        """Build successful validation result"""
        return {
            "status": "success",
            "message": "Service validation completed successfully",
            "found": True,
            "is_active": True,
            "service_location": self.service_location,
            "service_data": service_data,
            "history": history_data,
            "pending_cease_order": history_data.get("cancellation_captured", False),
            "evidence": {
                "screenshots": self.screenshots
            }
        }
    
    def _build_not_found_result(self) -> Dict:
        """Build not found result"""
        return {
            "status": "success",
            "message": "Service not found",
            "found": False,
            "is_active": False,
            "service_location": None,
            "evidence": {
                "screenshots": self.screenshots
            }
        }
