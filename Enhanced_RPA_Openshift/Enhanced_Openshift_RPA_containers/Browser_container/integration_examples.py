"""
Worker Integration Examples
----------------------------
Examples showing how workers integrate with browser service.
"""
import logging
from pathlib import Path
from typing import Dict, Any

# Import the browser client (this would be in worker container)
import sys
sys.path.append('../client')
from browser_client import (
    PlaywrightBrowserClient,
    SessionType,
    WaitUntil,
    ElementState,
    BrowserServiceError
)

logger = logging.getLogger(__name__)


# ============================================================================
# EXAMPLE 1: Basic Octotel Validation (Converted from Selenium)
# ============================================================================

class OctotelValidation:
    """
    Octotel order validation using browser service.
    This replaces the old Selenium-based automation.
    """
    
    def __init__(self, job_id: str, job_params: Dict[str, Any]):
        """
        Initialize automation
        
        Args:
            job_id: Job identifier
            job_params: Job parameters from orchestrator including:
                - browser_service_url: Browser service endpoint
                - browser_service_token: JWT token for auth
                - totp_code: Pre-generated TOTP code
                - username: Octotel username
                - password: Octotel password
                - order_id: Order to validate
        """
        self.job_id = job_id
        self.job_params = job_params
        
        # Create browser client
        self.browser = PlaywrightBrowserClient(
            base_url=job_params['browser_service_url'],
            auth_token=job_params['browser_service_token'],
            timeout=60
        )
        
        self.screenshot_dir = Path(f"screenshots/{job_id}")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
    
    def execute(self) -> Dict[str, Any]:
        """
        Execute validation workflow
        
        Returns:
            Validation results
        """
        try:
            # Create browser session
            self.browser.create_session(session_type=SessionType.STANDARD)
            logger.info(f"Job {self.job_id}: Browser session created")
            
            # Login to Octotel portal
            self._login()
            
            # Navigate to order
            order_data = self._validate_order()
            
            # Capture evidence
            self._capture_evidence()
            
            return {
                'status': 'success',
                'order_data': order_data,
                'job_id': self.job_id
            }
            
        except Exception as e:
            logger.error(f"Job {self.job_id}: Validation failed: {str(e)}")
            # Capture error screenshot
            self._capture_error_screenshot()
            raise
            
        finally:
            # Always cleanup session
            try:
                self.browser.close_session()
            except Exception as e:
                logger.warning(f"Error closing session: {e}")
    
    def _login(self):
        """Login to Octotel portal"""
        logger.info(f"Job {self.job_id}: Logging in to Octotel")
        
        # Navigate to login page
        self.browser.navigate(
            url="https://octotel-portal.co.za/login",
            wait_until=WaitUntil.NETWORKIDLE
        )
        
        # Fill credentials
        self.browser.fill('#username', self.job_params['username'])
        self.browser.fill('#password', self.job_params['password'])
        self.browser.click('#login-button')
        
        # Wait for TOTP prompt
        self.browser.wait_for_selector(
            '#totp-input',
            state=ElementState.VISIBLE,
            timeout=10000
        )
        
        # Submit pre-generated TOTP code from orchestrator
        self.browser.submit_totp(
            selector='#totp-input',
            code=self.job_params['totp_code'],  # Pre-generated!
            submit=True
        )
        
        # Wait for dashboard
        self.browser.wait_for_selector(
            '#dashboard',
            state=ElementState.VISIBLE,
            timeout=30000
        )
        
        logger.info(f"Job {self.job_id}: Login successful")
    
    def _validate_order(self) -> Dict[str, str]:
        """Validate order details"""
        logger.info(f"Job {self.job_id}: Validating order")
        
        order_id = self.job_params['order_id']
        
        # Navigate to order page
        self.browser.navigate(
            url=f"https://octotel-portal.co.za/orders/{order_id}",
            wait_until=WaitUntil.NETWORKIDLE
        )
        
        # Extract order data
        order_data = {
            'status': self.browser.get_text('#order-status'),
            'customer_name': self.browser.get_text('#customer-name'),
            'service_address': self.browser.get_text('#service-address'),
            'installation_date': self.browser.get_text('#installation-date'),
        }
        
        logger.info(f"Job {self.job_id}: Order data extracted: {order_data}")
        return order_data
    
    def _capture_evidence(self):
        """Capture screenshot evidence"""
        screenshot_path = self.screenshot_dir / "validation_complete.png"
        self.browser.screenshot(
            full_page=True,
            save_path=str(screenshot_path)
        )
        logger.info(f"Job {self.job_id}: Evidence captured")
    
    def _capture_error_screenshot(self):
        """Capture screenshot on error"""
        try:
            screenshot_path = self.screenshot_dir / "error.png"
            self.browser.screenshot(
                full_page=True,
                save_path=str(screenshot_path)
            )
        except Exception as e:
            logger.warning(f"Failed to capture error screenshot: {e}")


# ============================================================================
# EXAMPLE 2: MetroFiber Cancellation (More Complex Workflow)
# ============================================================================

class MetroFiberCancellation:
    """MetroFiber service cancellation automation"""
    
    def __init__(self, job_id: str, job_params: Dict[str, Any]):
        self.job_id = job_id
        self.job_params = job_params
        
        self.browser = PlaywrightBrowserClient(
            base_url=job_params['browser_service_url'],
            auth_token=job_params['browser_service_token']
        )
    
    def execute(self) -> Dict[str, Any]:
        """Execute cancellation workflow"""
        try:
            # Create session
            self.browser.create_session()
            
            # Login
            self._login()
            
            # Search for service
            service_data = self._search_service()
            
            # Cancel service
            cancellation_id = self._cancel_service(service_data)
            
            # Verify cancellation
            self._verify_cancellation(cancellation_id)
            
            return {
                'status': 'success',
                'cancellation_id': cancellation_id,
                'service_data': service_data
            }
            
        finally:
            self.browser.close_session()
    
    def _login(self):
        """Login to MetroFiber portal"""
        self.browser.navigate("https://metrofiber-portal.co.za/login")
        
        self.browser.fill('#email', self.job_params['email'])
        self.browser.fill('#password', self.job_params['password'])
        self.browser.click('button[type="submit"]')
        
        # Wait for dashboard
        self.browser.wait_for_selector('#dashboard', timeout=20000)
    
    def _search_service(self) -> Dict[str, str]:
        """Search for service to cancel"""
        # Navigate to services
        self.browser.click('a[href="/services"]')
        
        # Search by circuit number
        circuit = self.job_params['circuit_number']
        self.browser.fill('#search-input', circuit)
        self.browser.click('#search-button')
        
        # Wait for results
        self.browser.wait_for_selector('.service-row', timeout=15000)
        
        # Extract service data
        return {
            'circuit_number': self.browser.get_text('.service-row .circuit'),
            'customer_name': self.browser.get_text('.service-row .customer'),
            'status': self.browser.get_text('.service-row .status')
        }
    
    def _cancel_service(self, service_data: Dict) -> str:
        """Cancel the service"""
        # Click cancel button
        self.browser.click('.service-row .cancel-button')
        
        # Wait for modal
        self.browser.wait_for_selector('#cancel-modal', timeout=5000)
        
        # Fill cancellation form
        self.browser.fill('#cancellation-reason', self.job_params.get('reason', 'Customer request'))
        self.browser.click('#confirm-cancel')
        
        # Wait for confirmation
        self.browser.wait_for_selector('.cancellation-success', timeout=10000)
        
        # Extract cancellation ID
        cancellation_id = self.browser.get_text('.cancellation-id')
        logger.info(f"Service cancelled: {cancellation_id}")
        
        return cancellation_id
    
    def _verify_cancellation(self, cancellation_id: str):
        """Verify cancellation was processed"""
        # Navigate to cancellations
        self.browser.navigate("https://metrofiber-portal.co.za/cancellations")
        
        # Search for cancellation
        self.browser.fill('#cancellation-search', cancellation_id)
        
        # Verify status
        status = self.browser.get_text('.cancellation-status')
        assert status in ['Pending', 'Completed'], f"Unexpected status: {status}"


# ============================================================================
# EXAMPLE 3: Using Context Manager (Simplified)
# ============================================================================

def simple_automation_example(job_params: Dict[str, Any]) -> str:
    """
    Simple example using context manager.
    Browser session automatically created and cleaned up.
    """
    
    with PlaywrightBrowserClient(
        base_url=job_params['browser_service_url'],
        auth_token=job_params['browser_service_token']
    ) as browser:
        
        # Navigate
        browser.navigate("https://example.com")
        
        # Extract data
        title = browser.get_text('h1')
        
        # Screenshot
        browser.screenshot(save_path='result.png')
        
        return title


# ============================================================================
# EXAMPLE 4: Error Handling and Retry
# ============================================================================

class RobustAutomation:
    """Example with comprehensive error handling"""
    
    def __init__(self, job_params: Dict[str, Any]):
        self.browser = PlaywrightBrowserClient(
            base_url=job_params['browser_service_url'],
            auth_token=job_params['browser_service_token'],
            retry_attempts=5,  # More retries for flaky operations
            timeout=90
        )
    
    def execute_with_retry(self) -> Dict[str, Any]:
        """Execute with retry logic"""
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                return self._execute_workflow()
            except BrowserServiceError as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                
                # Cleanup and retry
                try:
                    self.browser.close_session()
                except:
                    pass
                
                if attempt < max_attempts - 1:
                    logger.info("Retrying...")
                    continue
        
        # All attempts failed
        raise last_error
    
    def _execute_workflow(self) -> Dict[str, Any]:
        """Main workflow with error handling"""
        try:
            self.browser.create_session()
            
            # Navigate with retry
            self._safe_navigate("https://portal.example.com")
            
            # Login with error handling
            if not self._safe_login():
                raise BrowserServiceError("Login failed")
            
            # Extract data
            data = self._safe_extract_data()
            
            return {'status': 'success', 'data': data}
            
        finally:
            self.browser.close_session()
    
    def _safe_navigate(self, url: str):
        """Navigate with error handling"""
        try:
            self.browser.navigate(url, wait_until=WaitUntil.NETWORKIDLE)
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            # Try with less strict wait condition
            self.browser.navigate(url, wait_until=WaitUntil.LOAD)
    
    def _safe_login(self) -> bool:
        """Login with verification"""
        try:
            self.browser.fill('#username', 'user')
            self.browser.fill('#password', 'pass')
            self.browser.click('#login')
            
            # Verify login success
            self.browser.wait_for_selector('#dashboard', timeout=30000)
            return True
            
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def _safe_extract_data(self) -> Dict[str, str]:
        """Extract data with fallbacks"""
        data = {}
        
        # Try primary selector, fall back to alternatives
        selectors = ['#primary-data', '.data-container', '[data-field="info"]']
        
        for selector in selectors:
            try:
                data['info'] = self.browser.get_text(selector)
                break
            except Exception:
                continue
        
        return data


# ============================================================================
# EXAMPLE 5: Integration with Worker Execute Function
# ============================================================================

def execute(job_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Worker execute function - called by worker.py
    This is how the automation modules are called.
    
    Args:
        job_id: Unique job identifier
        parameters: Job parameters including browser service info
        
    Returns:
        Execution results
    """
    logger.info(f"Executing job {job_id}")
    
    # Determine automation type
    provider = parameters.get('provider')
    action = parameters.get('action')
    
    try:
        if provider == 'octotel' and action == 'validation':
            automation = OctotelValidation(job_id, parameters)
            result = automation.execute()
            
        elif provider == 'metrofiber' and action == 'cancellation':
            automation = MetroFiberCancellation(job_id, parameters)
            result = automation.execute()
            
        else:
            raise ValueError(f"Unknown automation: {provider}/{action}")
        
        logger.info(f"Job {job_id} completed successfully")
        return result
        
    except Exception as e:
        logger.error(f"Job {job_id} failed: {str(e)}")
        return {
            'status': 'failed',
            'error': str(e),
            'job_id': job_id
        }
