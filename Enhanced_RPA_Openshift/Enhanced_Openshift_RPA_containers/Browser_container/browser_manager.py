"""
Browser Manager - Core Browser Management Using Factory Pattern
---------------------------------------------------------------
Manages browser lifecycle and operations using factories.
"""
import uuid
import logging
from typing import Optional, Dict, Any
from playwright.async_api import Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeout

from factories.browser_factory import BrowserFactory, BrowserInterface
from factories.session_factory import SessionFactory

logger = logging.getLogger(__name__)


class BrowserManager:
    """
    Manages browser instances and sessions using factory pattern.
    Singleton pattern to ensure only one browser instance per container.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BrowserManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.browser_factory = BrowserFactory()
        self.browser_interface: Optional[BrowserInterface] = None
        self.browser: Optional[Browser] = None
        self.session_factory: Optional[SessionFactory] = None
        self.current_session_id: Optional[str] = None
        self._initialized = True
        self._ready = False
    
    async def initialize(self, browser_type: str = 'firefox', **launch_options):
        """
        Initialize browser using factory
        
        Args:
            browser_type: Type of browser to create
            **launch_options: Browser launch options
        """
        try:
            # Create browser via factory
            self.browser_interface, self.browser = await self.browser_factory.create_browser(
                browser_type=browser_type,
                **launch_options
            )
            
            # Create session factory
            self.session_factory = SessionFactory(self.browser)
            
            self._ready = True
            logger.info(f"BrowserManager initialized with {browser_type}")
            
        except Exception as e:
            logger.error(f"Failed to initialize BrowserManager: {e}")
            self._ready = False
            raise
    
    def is_ready(self) -> bool:
        """Check if browser is ready"""
        return self._ready and self.browser is not None
    
    async def create_session(
        self,
        session_type: str = 'standard',
        **config_kwargs
    ) -> str:
        """
        Create a new browser session
        
        Args:
            session_type: Type of session to create
            **config_kwargs: Session configuration options
            
        Returns:
            Session ID
        """
        if not self.is_ready():
            raise RuntimeError("Browser not initialized")
        
        # Generate unique session ID
        session_id = str(uuid.uuid4())
        
        # Create session via factory
        context, page = await self.session_factory.create_session(
            session_id=session_id,
            session_type=session_type,
            **config_kwargs
        )
        
        self.current_session_id = session_id
        logger.info(f"Created session: {session_id}")
        
        return session_id
    
    async def get_current_page(self) -> Page:
        """Get the current active page"""
        if not self.current_session_id:
            raise RuntimeError("No active session")
        
        session = await self.session_factory.get_session(self.current_session_id)
        if not session:
            raise RuntimeError(f"Session {self.current_session_id} not found")
        
        _, page = session
        return page
    
    async def navigate(
        self,
        url: str,
        wait_until: str = 'networkidle',
        timeout: int = 30000
    ):
        """
        Navigate to URL
        
        Args:
            url: URL to navigate to
            wait_until: Wait condition ('load', 'domcontentloaded', 'networkidle')
            timeout: Navigation timeout in milliseconds
        """
        page = await self.get_current_page()
        
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout)
            logger.info(f"Navigated to {url}")
        except PlaywrightTimeout:
            logger.error(f"Navigation timeout for {url}")
            raise
    
    async def click(
        self,
        selector: str,
        timeout: int = 30000,
        force: bool = False
    ):
        """
        Click element
        
        Args:
            selector: Element selector
            timeout: Timeout in milliseconds
            force: Force click even if element is not actionable
        """
        page = await self.get_current_page()
        
        try:
            await page.click(selector, timeout=timeout, force=force)
            logger.info(f"Clicked element: {selector}")
        except PlaywrightTimeout:
            logger.error(f"Click timeout for selector: {selector}")
            raise
    
    async def fill(
        self,
        selector: str,
        value: str,
        timeout: int = 30000
    ):
        """
        Fill input field
        
        Args:
            selector: Element selector
            value: Value to fill
            timeout: Timeout in milliseconds
        """
        page = await self.get_current_page()
        
        try:
            await page.fill(selector, value, timeout=timeout)
            logger.info(f"Filled element {selector} with value")
        except PlaywrightTimeout:
            logger.error(f"Fill timeout for selector: {selector}")
            raise
    
    async def press_key(self, key: str):
        """Press keyboard key"""
        page = await self.get_current_page()
        await page.keyboard.press(key)
        logger.info(f"Pressed key: {key}")
    
    async def get_text(
        self,
        selector: str,
        timeout: int = 30000
    ) -> str:
        """
        Get text content of element
        
        Args:
            selector: Element selector
            timeout: Timeout in milliseconds
            
        Returns:
            Text content
        """
        page = await self.get_current_page()
        
        try:
            element = await page.wait_for_selector(selector, timeout=timeout)
            text = await element.inner_text()
            logger.info(f"Retrieved text from {selector}")
            return text
        except PlaywrightTimeout:
            logger.error(f"Timeout getting text for selector: {selector}")
            raise
    
    async def get_attribute(
        self,
        selector: str,
        attribute: str,
        timeout: int = 30000
    ) -> Optional[str]:
        """Get element attribute value"""
        page = await self.get_current_page()
        
        try:
            element = await page.wait_for_selector(selector, timeout=timeout)
            value = await element.get_attribute(attribute)
            logger.info(f"Retrieved attribute {attribute} from {selector}")
            return value
        except PlaywrightTimeout:
            logger.error(f"Timeout getting attribute for selector: {selector}")
            raise
    
    async def screenshot(
        self,
        full_page: bool = False,
        path: Optional[str] = None
    ) -> bytes:
        """
        Capture screenshot
        
        Args:
            full_page: Capture full scrollable page
            path: Optional path to save screenshot
            
        Returns:
            Screenshot bytes
        """
        page = await self.get_current_page()
        screenshot_bytes = await page.screenshot(full_page=full_page, path=path)
        logger.info("Captured screenshot")
        return screenshot_bytes
    
    async def wait_for_selector(
        self,
        selector: str,
        state: str = 'visible',
        timeout: int = 30000
    ):
        """
        Wait for element to reach specific state
        
        Args:
            selector: Element selector
            state: Target state ('attached', 'detached', 'visible', 'hidden')
            timeout: Timeout in milliseconds
        """
        page = await self.get_current_page()
        
        try:
            await page.wait_for_selector(selector, state=state, timeout=timeout)
            logger.info(f"Element {selector} reached state: {state}")
        except PlaywrightTimeout:
            logger.error(f"Timeout waiting for {selector} to be {state}")
            raise
    
    async def evaluate(self, expression: str) -> Any:
        """Execute JavaScript in page context"""
        page = await self.get_current_page()
        result = await page.evaluate(expression)
        logger.info(f"Evaluated JavaScript expression")
        return result
    
    async def close_session(self, session_id: Optional[str] = None):
        """Close a session"""
        if session_id is None:
            session_id = self.current_session_id
        
        if session_id:
            await self.session_factory.close_session(session_id)
            if session_id == self.current_session_id:
                self.current_session_id = None
            logger.info(f"Closed session: {session_id}")
    
    async def get_session_info(self) -> Dict[str, Any]:
        """Get information about active sessions"""
        return {
            'active_sessions': self.session_factory.get_active_session_count(),
            'current_session': self.current_session_id,
            'browser_type': self.browser_interface.get_browser_type() if self.browser_interface else None,
            'ready': self._ready
        }
    
    async def cleanup(self):
        """Cleanup all resources"""
        if self.session_factory:
            await self.session_factory.close_all_sessions()
        
        if self.browser:
            await self.browser.close()
            logger.info("Browser closed")
        
        if self.browser_factory:
            await self.browser_factory.cleanup()
        
        self._ready = False
        logger.info("BrowserManager cleanup complete")
