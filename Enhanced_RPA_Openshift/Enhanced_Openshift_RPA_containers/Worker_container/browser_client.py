"""
Browser Service Client
======================
Client library for communicating with the browser service layer.
Provides high-level methods for browser automation operations.
"""

import aiohttp
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class BrowserServiceError(Exception):
    """Browser service communication error"""
    pass


class BrowserServiceClient:
    """Client for browser service REST API"""
    
    def __init__(self, base_url: str, timeout: int = 300):
        """
        Initialize browser service client
        
        Args:
            base_url: Base URL of browser service (e.g., http://rpa-browser-service:8080)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self.session
    
    async def close(self):
        """Close the session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to browser service"""
        url = f"{self.base_url}{endpoint}"
        session = await self._get_session()
        
        try:
            async with session.request(method, url, **kwargs) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    raise BrowserServiceError(
                        f"Browser service error {response.status}: {error_text}"
                    )
                return await response.json()
        except aiohttp.ClientError as e:
            raise BrowserServiceError(f"Failed to communicate with browser service: {str(e)}")
    
    # ========================================================================
    # Health & Status
    # ========================================================================
    
    async def health_check(self) -> bool:
        """Check if browser service is healthy"""
        try:
            result = await self._request("GET", "/health")
            return result.get("status") == "healthy"
        except Exception as e:
            logger.warning(f"Browser service health check failed: {str(e)}")
            return False
    
    async def get_status(self) -> Dict[str, Any]:
        """Get detailed browser service status"""
        return await self._request("GET", "/status")
    
    # ========================================================================
    # Session Management
    # ========================================================================
    
    async def create_session(self, job_id: int, headless: bool = True) -> str:
        """
        Create a new browser session
        
        Args:
            job_id: Job identifier for tracking
            headless: Run browser in headless mode
            
        Returns:
            session_id: Unique session identifier
        """
        logger.info(f"Creating browser session for job {job_id}")
        result = await self._request(
            "POST",
            "/browser/session",
            json={
                "job_id": job_id,
                "headless": headless,
                "incognito": True  # Always use incognito mode
            }
        )
        session_id = result.get("session_id")
        logger.info(f"Created browser session: {session_id}")
        return session_id
    
    async def close_session(self, session_id: str) -> bool:
        """Close browser session and cleanup"""
        logger.info(f"Closing browser session: {session_id}")
        try:
            await self._request("DELETE", f"/browser/session/{session_id}")
            logger.info(f"Closed browser session: {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to close session {session_id}: {str(e)}")
            return False
    
    # ========================================================================
    # Navigation
    # ========================================================================
    
    async def navigate(self, session_id: str, url: str, wait_until: str = "networkidle") -> Dict[str, Any]:
        """
        Navigate to URL
        
        Args:
            session_id: Browser session ID
            url: Target URL
            wait_until: Wait condition (load, domcontentloaded, networkidle)
        """
        logger.info(f"Navigating to {url}")
        return await self._request(
            "POST",
            f"/browser/{session_id}/navigate",
            json={"url": url, "wait_until": wait_until}
        )
    
    async def get_current_url(self, session_id: str) -> str:
        """Get current page URL"""
        result = await self._request("GET", f"/browser/{session_id}/url")
        return result.get("url", "")
    
    # ========================================================================
    # Element Interaction
    # ========================================================================
    
    async def click(self, session_id: str, selector: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Click element
        
        Args:
            session_id: Browser session ID
            selector: CSS selector or XPath
            timeout: Wait timeout in seconds
        """
        logger.debug(f"Clicking element: {selector}")
        return await self._request(
            "POST",
            f"/browser/{session_id}/click",
            json={"selector": selector, "timeout": timeout}
        )
    
    async def type_text(self, session_id: str, selector: str, text: str, clear: bool = True, timeout: int = 30) -> Dict[str, Any]:
        """
        Type text into input field
        
        Args:
            session_id: Browser session ID
            selector: CSS selector or XPath
            text: Text to type
            clear: Clear existing text first
            timeout: Wait timeout in seconds
        """
        logger.debug(f"Typing into element: {selector}")
        return await self._request(
            "POST",
            f"/browser/{session_id}/type",
            json={
                "selector": selector,
                "text": text,
                "clear": clear,
                "timeout": timeout
            }
        )
    
    async def select_option(self, session_id: str, selector: str, value: str, timeout: int = 30) -> Dict[str, Any]:
        """Select option from dropdown"""
        logger.debug(f"Selecting option {value} in {selector}")
        return await self._request(
            "POST",
            f"/browser/{session_id}/select",
            json={"selector": selector, "value": value, "timeout": timeout}
        )
    
    async def press_key(self, session_id: str, key: str) -> Dict[str, Any]:
        """Press keyboard key (Enter, Tab, Escape, etc.)"""
        return await self._request(
            "POST",
            f"/browser/{session_id}/press",
            json={"key": key}
        )
    
    # ========================================================================
    # Element Queries
    # ========================================================================
    
    async def wait_for_selector(self, session_id: str, selector: str, state: str = "visible", timeout: int = 30) -> Dict[str, Any]:
        """
        Wait for element to reach state
        
        Args:
            session_id: Browser session ID
            selector: CSS selector or XPath
            state: Element state (visible, hidden, attached, detached)
            timeout: Wait timeout in seconds
        """
        return await self._request(
            "POST",
            f"/browser/{session_id}/wait",
            json={"selector": selector, "state": state, "timeout": timeout}
        )
    
    async def get_text(self, session_id: str, selector: str, timeout: int = 30) -> str:
        """Get text content of element"""
        result = await self._request(
            "POST",
            f"/browser/{session_id}/text",
            json={"selector": selector, "timeout": timeout}
        )
        return result.get("text", "")
    
    async def get_attribute(self, session_id: str, selector: str, attribute: str, timeout: int = 30) -> Optional[str]:
        """Get element attribute value"""
        result = await self._request(
            "POST",
            f"/browser/{session_id}/attribute",
            json={"selector": selector, "attribute": attribute, "timeout": timeout}
        )
        return result.get("value")
    
    async def is_visible(self, session_id: str, selector: str, timeout: int = 5) -> bool:
        """Check if element is visible"""
        try:
            result = await self._request(
                "POST",
                f"/browser/{session_id}/visible",
                json={"selector": selector, "timeout": timeout}
            )
            return result.get("visible", False)
        except:
            return False
    
    async def query_all(self, session_id: str, selector: str) -> List[Dict[str, Any]]:
        """Query all matching elements"""
        result = await self._request(
            "POST",
            f"/browser/{session_id}/query_all",
            json={"selector": selector}
        )
        return result.get("elements", [])
    
    # ========================================================================
    # Advanced Operations
    # ========================================================================
    
    async def execute_script(self, session_id: str, script: str, args: List[Any] = None) -> Any:
        """Execute JavaScript in browser context"""
        return await self._request(
            "POST",
            f"/browser/{session_id}/execute",
            json={"script": script, "args": args or []}
        )
    
    async def screenshot(self, session_id: str, full_page: bool = False) -> str:
        """
        Take screenshot
        
        Returns:
            Base64 encoded screenshot
        """
        result = await self._request(
            "POST",
            f"/browser/{session_id}/screenshot",
            json={"full_page": full_page}
        )
        return result.get("screenshot", "")
    
    async def get_page_content(self, session_id: str) -> str:
        """Get page HTML content"""
        result = await self._request("GET", f"/browser/{session_id}/content")
        return result.get("content", "")
    
    # ========================================================================
    # Form Operations
    # ========================================================================
    
    async def fill_form(self, session_id: str, form_data: Dict[str, str]) -> Dict[str, Any]:
        """
        Fill multiple form fields
        
        Args:
            session_id: Browser session ID
            form_data: Dictionary of {selector: value}
        """
        logger.info(f"Filling form with {len(form_data)} fields")
        return await self._request(
            "POST",
            f"/browser/{session_id}/form",
            json={"fields": form_data}
        )
    
    async def submit_form(self, session_id: str, form_selector: str) -> Dict[str, Any]:
        """Submit form"""
        return await self._request(
            "POST",
            f"/browser/{session_id}/submit",
            json={"selector": form_selector}
        )
    
    # ========================================================================
    # Wait Operations
    # ========================================================================
    
    async def wait_for_navigation(self, session_id: str, timeout: int = 30) -> Dict[str, Any]:
        """Wait for page navigation to complete"""
        return await self._request(
            "POST",
            f"/browser/{session_id}/wait_navigation",
            json={"timeout": timeout}
        )
    
    async def wait_for_timeout(self, session_id: str, milliseconds: int) -> Dict[str, Any]:
        """Wait for specified time"""
        return await self._request(
            "POST",
            f"/browser/{session_id}/wait_timeout",
            json={"milliseconds": milliseconds}
        )
