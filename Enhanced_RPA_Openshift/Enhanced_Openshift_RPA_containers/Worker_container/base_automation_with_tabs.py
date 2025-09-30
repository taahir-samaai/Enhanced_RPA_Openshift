"""
Base Automation Pattern with Tab Management
============================================
Shows the proper pattern for provider modules with tab isolation.

Each automation:
1. Creates a browser session
2. Opens a new tab for work
3. Performs automation
4. Closes the tab
5. Returns to original state
6. Closes session
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from abc import ABC, abstractmethod

from browser_client import BrowserServiceClient, BrowserServiceError

logger = logging.getLogger(__name__)


class BaseProviderAutomation(ABC):
    """
    Base class for all provider automations with tab management.
    
    Pattern:
    1. __init__ receives browser_client
    2. execute() is the main entry point
    3. Tab management is handled automatically
    4. Cleanup is guaranteed via try/finally
    """
    
    def __init__(self, browser_client: BrowserServiceClient):
        self.browser = browser_client
        self.logger = logging.getLogger(self.__class__.__name__)
        self.session_id: Optional[str] = None
        self.original_url: Optional[str] = None
        self.work_tab_url: Optional[str] = None
    
    async def execute(self, job_id: int, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main execution method with automatic tab management.
        Override _execute_automation() instead of this method.
        """
        try:
            # Create browser session
            self.session_id = await self.browser.create_session(job_id, headless=True)
            self.logger.info(f"Created browser session: {self.session_id}")
            
            # Save original URL (typically about:blank)
            self.original_url = await self.browser.get_current_url(self.session_id)
            self.logger.info(f"Original URL: {self.original_url}")
            
            # Open new tab for work (Playwright context isolation)
            # Note: In Playwright, we can open a new page in the same context
            await self._open_new_tab()
            
            # Execute the actual automation (subclass implements this)
            result = await self._execute_automation(job_id, parameters)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Automation failed: {str(e)}")
            raise
            
        finally:
            # Cleanup: close tab and session
            await self._cleanup()
    
    async def _open_new_tab(self):
        """Open a new tab for work"""
        try:
            # In Playwright via browser service, we navigate to about:blank first
            # then to our target URL. This ensures tab isolation.
            self.work_tab_url = "about:blank"
            await self.browser.navigate(self.session_id, self.work_tab_url)
            self.logger.info("Opened new tab for work")
        except Exception as e:
            self.logger.error(f"Failed to open new tab: {str(e)}")
            raise
    
    async def _close_work_tab(self):
        """Close the work tab and return to original"""
        try:
            # Navigate back to original URL (effectively closing the work context)
            if self.original_url:
                await self.browser.navigate(self.session_id, self.original_url)
                self.logger.info("Closed work tab, returned to original URL")
        except Exception as e:
            self.logger.warning(f"Could not close work tab: {str(e)}")
    
    async def _cleanup(self):
        """Cleanup resources"""
        try:
            # Close work tab
            await self._close_work_tab()
            
            # Close browser session
            if self.session_id:
                await self.browser.close_session(self.session_id)
                self.logger.info("Browser session closed")
        except Exception as e:
            self.logger.error(f"Cleanup failed: {str(e)}")
    
    @abstractmethod
    async def _execute_automation(self, job_id: int, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the actual automation logic.
        Subclasses must implement this method.
        
        Args:
            job_id: Job identifier
            parameters: Job parameters including credentials, search terms, etc.
            
        Returns:
            Result dictionary with status, message, data, screenshots
        """
        pass
    
    async def take_screenshot(self, name: str) -> str:
        """Take screenshot and return base64 data"""
        if not self.session_id:
            raise BrowserServiceError("No active session for screenshot")
        return await self.browser.screenshot(self.session_id, full_page=True)


# ==================== EXAMPLE IMPLEMENTATION ====================

class ExampleProviderValidation(BaseProviderAutomation):
    """
    Example provider validation showing the pattern.
    Replace with actual provider (Octotel, Openserve, etc.)
    """
    
    PORTAL_URL = "https://example-provider.com"
    
    async def _execute_automation(self, job_id: int, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Implement actual automation logic"""
        
        # Extract parameters
        circuit_number = parameters.get("circuit_number")
        totp_code = parameters.get("totp_code")  # Pre-generated by orchestrator
        
        try:
            # Step 1: Navigate to portal
            self.logger.info(f"Navigating to {self.PORTAL_URL}")
            await self.browser.navigate(self.session_id, self.PORTAL_URL)
            
            # Step 2: Login
            self.logger.info("Performing login")
            await self._login(totp_code)
            
            # Step 3: Search for service
            self.logger.info(f"Searching for circuit: {circuit_number}")
            service_found = await self._search_service(circuit_number)
            
            if not service_found:
                return {
                    "status": "success",
                    "message": f"Service {circuit_number} not found",
                    "found": False,
                    "data": {}
                }
            
            # Step 4: Extract service data
            self.logger.info("Extracting service data")
            service_data = await self._extract_service_data()
            
            # Step 5: Take final screenshot
            screenshot = await self.take_screenshot("final_state")
            
            # Return standardized result
            return {
                "status": "success",
                "message": f"Successfully validated service {circuit_number}",
                "found": True,
                "data": service_data,
                "screenshots": [
                    {
                        "name": "final_state",
                        "timestamp": datetime.now().isoformat(),
                        "data": screenshot
                    }
                ]
            }
            
        except Exception as e:
            self.logger.error(f"Automation failed: {str(e)}")
            raise
    
    async def _login(self, totp_code: Optional[str]):
        """Login implementation"""
        # Wait for login form
        await self.browser.wait_for_selector(self.session_id, "#username", timeout=15)
        
        # Enter credentials
        await self.browser.type_text(self.session_id, "#username", "user@example.com")
        await self.browser.type_text(self.session_id, "#password", "password123")
        
        # Submit
        await self.browser.click(self.session_id, "button[type='submit']")
        
        # Handle TOTP if required
        if totp_code:
            await self.browser.wait_for_selector(self.session_id, "#totp", timeout=10)
            await self.browser.type_text(self.session_id, "#totp", totp_code)
            await self.browser.click(self.session_id, "#totp-submit")
        
        # Wait for dashboard
        await self.browser.wait_for_selector(self.session_id, ".dashboard", timeout=20)
        self.logger.info("Login successful")
    
    async def _search_service(self, circuit_number: str) -> bool:
        """Search for service"""
        # Navigate to services
        await self.browser.click(self.session_id, "a[href='/services']")
        await self.browser.wait_for_selector(self.session_id, "#search-input", timeout=10)
        
        # Enter search term
        await self.browser.type_text(self.session_id, "#search-input", circuit_number, clear=True)
        await self.browser.press_key(self.session_id, "Enter")
        
        # Wait for results
        await self.browser.wait_for_timeout(self.session_id, 3000)
        
        # Check if service found
        results_text = await self.browser.get_text(self.session_id, ".results-container")
        return circuit_number in results_text
    
    async def _extract_service_data(self) -> Dict[str, Any]:
        """Extract service data"""
        # Click on first result
        await self.browser.click(self.session_id, ".service-row:first-child")
        await self.browser.wait_for_selector(self.session_id, ".service-details", timeout=10)
        
        # Extract data
        customer_name = await self.browser.get_text(self.session_id, ".customer-name")
        status = await self.browser.get_text(self.session_id, ".service-status")
        
        return {
            "customer_name": customer_name,
            "status": status,
            "extraction_timestamp": datetime.now().isoformat()
        }


# ==================== EXECUTE FUNCTION PATTERN ====================

async def execute(parameters: Dict[str, Any], browser_client: BrowserServiceClient) -> Dict[str, Any]:
    """
    Standard execute function pattern for all providers.
    
    This is called by the worker's provider factory.
    
    Args:
        parameters: Job parameters from orchestrator
        browser_client: Browser service client instance
        
    Returns:
        Result dictionary
    """
    try:
        # Validate required parameters
        job_id = parameters.get("job_id")
        if not job_id:
            return {
                "status": "error",
                "message": "Missing required parameter: job_id",
                "data": {}
            }
        
        # Create automation instance
        automation = ExampleProviderValidation(browser_client)
        
        # Execute automation (tab management handled automatically)
        result = await automation.execute(job_id, parameters)
        
        return result
        
    except Exception as e:
        logger.error(f"Execute failed: {str(e)}")
        return {
            "status": "error",
            "message": f"Execution error: {str(e)}",
            "data": {}
        }


# ==================== USAGE EXAMPLE ====================

"""
# In the worker factory:

from providers.octotel.validation import execute as octotel_validation_execute
from providers.openserve.validation import execute as openserve_validation_execute

# When job comes in:
if provider == "octotel" and action == "validation":
    result = await octotel_validation_execute(parameters, browser_client)

# The execute function:
# 1. Creates automation instance with browser_client
# 2. Calls automation.execute() which:
#    - Creates session
#    - Opens new tab
#    - Runs _execute_automation()
#    - Closes tab
#    - Closes session
# 3. Returns standardized result

# Tab isolation ensures:
# - Each job starts with clean browser state
# - No cookie/session leakage between jobs
# - Original browser state is preserved
# - Cleanup is guaranteed via try/finally
"""
