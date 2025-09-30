"""
Browser Service Client Library
-------------------------------
Client library for workers to communicate with browser service.
This file should be copied to the worker container.
"""
import requests
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class WaitUntil(Enum):
    """Page load wait conditions"""
    LOAD = 'load'
    DOMCONTENTLOADED = 'domcontentloaded'
    NETWORKIDLE = 'networkidle'


class ElementState(Enum):
    """Element states"""
    ATTACHED = 'attached'
    DETACHED = 'detached'
    VISIBLE = 'visible'
    HIDDEN = 'hidden'


class SessionType(Enum):
    """Browser session types"""
    STANDARD = 'standard'
    MOBILE = 'mobile'
    INCOGNITO = 'incognito'


@dataclass
class BrowserServiceConfig:
    """Configuration for browser service client"""
    base_url: str
    auth_token: str
    timeout: int = 60
    retry_attempts: int = 3
    verify_ssl: bool = True


class BrowserServiceError(Exception):
    """Base exception for browser service errors"""
    pass


class BrowserServiceConnectionError(BrowserServiceError):
    """Connection to browser service failed"""
    pass


class BrowserServiceAuthError(BrowserServiceError):
    """Authentication with browser service failed"""
    pass


class BrowserServiceTimeoutError(BrowserServiceError):
    """Browser operation timed out"""
    pass


class PlaywrightBrowserClient:
    """
    Client for communicating with Playwright browser service.
    
    Usage:
        client = PlaywrightBrowserClient(
            base_url="http://browser-service:8080",
            auth_token="jwt-token-from-orchestrator"
        )
        
        client.create_session()
        client.navigate("https://example.com")
        text = client.get_text("#heading")
        client.close_session()
    """
    
    def __init__(
        self,
        base_url: str,
        auth_token: str,
        timeout: int = 60,
        retry_attempts: int = 3,
        verify_ssl: bool = True
    ):
        """
        Initialize browser client
        
        Args:
            base_url: Browser service URL
            auth_token: JWT authentication token
            timeout: Request timeout in seconds
            retry_attempts: Number of retry attempts for failed requests
            verify_ssl: Verify SSL certificates
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {auth_token}',
            'Content-Type': 'application/json'
        })
        self.session.verify = verify_ssl
        
        self.session_id: Optional[str] = None
        
        logger.info(f"Initialized browser client for {self.base_url}")
    
    def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        retry: int = 0
    ) -> requests.Response:
        """
        Make HTTP request to browser service with retry logic
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            json_data: JSON request body
            params: Query parameters
            retry: Current retry attempt
            
        Returns:
            Response object
            
        Raises:
            BrowserServiceError: If request fails after retries
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                json=json_data,
                params=params,
                timeout=self.timeout
            )
            
            # Raise for HTTP errors
            if response.status_code == 401:
                raise BrowserServiceAuthError("Authentication failed")
            elif response.status_code == 403:
                raise BrowserServiceAuthError("Access forbidden")
            elif response.status_code >= 500:
                if retry < self.retry_attempts:
                    logger.warning(f"Server error {response.status_code}, retrying... ({retry + 1}/{self.retry_attempts})")
                    return self._request(method, endpoint, json_data, params, retry + 1)
                raise BrowserServiceError(f"Server error: {response.status_code}")
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.Timeout:
            if retry < self.retry_attempts:
                logger.warning(f"Request timeout, retrying... ({retry + 1}/{self.retry_attempts})")
                return self._request(method, endpoint, json_data, params, retry + 1)
            raise BrowserServiceTimeoutError(f"Request timed out after {self.timeout}s")
        
        except requests.exceptions.ConnectionError as e:
            if retry < self.retry_attempts:
                logger.warning(f"Connection error, retrying... ({retry + 1}/{self.retry_attempts})")
                return self._request(method, endpoint, json_data, params, retry + 1)
            raise BrowserServiceConnectionError(f"Failed to connect to browser service: {str(e)}")
    
    # Session Management
    
    def create_session(
        self,
        viewport_width: int = 1920,
        viewport_height: int = 1080
    ) -> str:
        """
        Create browser session (always Firefox incognito mode)
        
        Args:
            viewport_width: Viewport width
            viewport_height: Viewport height
            
        Returns:
            Session ID
        """
        response = self._request(
            'POST',
            '/browser/session/create',
            json_data={
                'session_type': 'incognito',  # Always incognito
                'viewport_width': viewport_width,
                'viewport_height': viewport_height
            }
        )
        
        data = response.json()
        self.session_id = data['session_id']
        logger.info(f"Created browser session: {self.session_id}")
        return self.session_id
    
    def close_session(self):
        """Close browser session"""
        response = self._request('DELETE', '/browser/session/close')
        logger.info("Closed browser session")
        self.session_id = None
    
    def get_session_info(self) -> Dict[str, Any]:
        """Get session information"""
        response = self._request('GET', '/browser/session/info')
        return response.json()
    
    # Navigation
    
    def navigate(
        self,
        url: str,
        wait_until: WaitUntil = WaitUntil.NETWORKIDLE,
        timeout: int = 30000
    ):
        """
        Navigate to URL
        
        Args:
            url: URL to navigate to
            wait_until: Wait condition
            timeout: Navigation timeout in milliseconds
        """
        self._request(
            'POST',
            '/browser/navigate',
            json_data={
                'url': url,
                'wait_until': wait_until.value,
                'timeout': timeout
            }
        )
        logger.info(f"Navigated to {url}")
    
    # Interactions
    
    def click(
        self,
        selector: str,
        timeout: int = 30000,
        force: bool = False
    ):
        """
        Click element
        
        Args:
            selector: CSS selector
            timeout: Timeout in milliseconds
            force: Force click even if not actionable
        """
        self._request(
            'POST',
            '/browser/click',
            json_data={
                'selector': selector,
                'timeout': timeout,
                'force': force
            }
        )
        logger.info(f"Clicked element: {selector}")
    
    def fill(
        self,
        selector: str,
        value: str,
        timeout: int = 30000
    ):
        """
        Fill input field
        
        Args:
            selector: CSS selector
            value: Value to fill
            timeout: Timeout in milliseconds
        """
        self._request(
            'POST',
            '/browser/fill',
            json_data={
                'selector': selector,
                'value': value,
                'timeout': timeout
            }
        )
        logger.info(f"Filled element: {selector}")
    
    def submit_totp(
        self,
        selector: str,
        code: str,
        submit: bool = True
    ):
        """
        Submit TOTP code
        
        Args:
            selector: CSS selector for TOTP input
            code: 6-digit TOTP code (pre-generated by orchestrator)
            submit: Auto-submit after entering code
        """
        self._request(
            'POST',
            '/browser/submit_totp',
            json_data={
                'selector': selector,
                'code': code,
                'submit': submit
            }
        )
        logger.info("TOTP code submitted")
    
    # Data Extraction
    
    def get_text(
        self,
        selector: str,
        timeout: int = 30000
    ) -> str:
        """
        Get text content from element
        
        Args:
            selector: CSS selector
            timeout: Timeout in milliseconds
            
        Returns:
            Text content
        """
        response = self._request(
            'GET',
            '/browser/text',
            params={
                'selector': selector,
                'timeout': timeout
            }
        )
        data = response.json()
        return data['text']
    
    def get_attribute(
        self,
        selector: str,
        attribute: str,
        timeout: int = 30000
    ) -> Optional[str]:
        """
        Get attribute value from element
        
        Args:
            selector: CSS selector
            attribute: Attribute name
            timeout: Timeout in milliseconds
            
        Returns:
            Attribute value or None
        """
        response = self._request(
            'GET',
            '/browser/attribute',
            params={
                'selector': selector,
                'attribute': attribute,
                'timeout': timeout
            }
        )
        data = response.json()
        return data['value']
    
    # Screenshot
    
    def screenshot(
        self,
        full_page: bool = False,
        save_path: Optional[str] = None
    ) -> bytes:
        """
        Capture screenshot
        
        Args:
            full_page: Capture full scrollable page
            save_path: Optional path to save screenshot
            
        Returns:
            Screenshot bytes
        """
        response = self._request(
            'POST',
            '/browser/screenshot',
            json_data={'full_page': full_page}
        )
        
        screenshot_bytes = response.content
        
        if save_path:
            with open(save_path, 'wb') as f:
                f.write(screenshot_bytes)
            logger.info(f"Screenshot saved to {save_path}")
        
        return screenshot_bytes
    
    # Wait Operations
    
    def wait_for_selector(
        self,
        selector: str,
        state: ElementState = ElementState.VISIBLE,
        timeout: int = 30000
    ):
        """
        Wait for element to reach specific state
        
        Args:
            selector: CSS selector
            state: Target state
            timeout: Timeout in milliseconds
        """
        self._request(
            'POST',
            '/browser/wait_for_selector',
            json_data={
                'selector': selector,
                'state': state.value,
                'timeout': timeout
            }
        )
        logger.info(f"Element {selector} reached state: {state.value}")
    
    # JavaScript Execution
    
    def evaluate(self, expression: str) -> Any:
        """
        Execute JavaScript in page context
        
        Args:
            expression: JavaScript expression
            
        Returns:
            Evaluation result
        """
        response = self._request(
            'POST',
            '/browser/evaluate',
            json_data={'expression': expression}
        )
        data = response.json()
        return data.get('details', {}).get('result')
    
    # Context Manager Support
    
    def __enter__(self):
        """Context manager entry"""
        self.create_session()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        try:
            self.close_session()
        except Exception as e:
            logger.warning(f"Error closing session: {e}")
        return False


# Convenience function for quick client creation
def create_browser_client(
    browser_service_url: str,
    auth_token: str,
    **kwargs
) -> PlaywrightBrowserClient:
    """
    Create browser client with default settings
    
    Args:
        browser_service_url: Browser service URL
        auth_token: JWT token
        **kwargs: Additional client options
        
    Returns:
        Configured browser client
    """
    return PlaywrightBrowserClient(
        base_url=browser_service_url,
        auth_token=auth_token,
        **kwargs
    )
