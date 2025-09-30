"""
Browser Factory - Factory Pattern for Browser Creation
-------------------------------------------------------
Creates different browser instances based on configuration.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from playwright.async_api import async_playwright, Browser, BrowserType
import logging

logger = logging.getLogger(__name__)


class BrowserInterface(ABC):
    """Abstract base class for browser implementations"""
    
    @abstractmethod
    async def launch(self, **kwargs) -> Browser:
        """Launch browser instance"""
        pass
    
    @abstractmethod
    def get_browser_type(self) -> str:
        """Get browser type name"""
        pass


class FirefoxBrowser(BrowserInterface):
    """Firefox browser implementation"""
    
    def __init__(self, playwright_instance):
        self.playwright = playwright_instance
        self.browser_type: BrowserType = self.playwright.firefox
    
    async def launch(self, **kwargs) -> Browser:
        """Launch Firefox browser"""
        default_args = {
            'headless': True,
            'args': [
                '--no-sandbox',
                '--disable-dev-shm-usage'
            ]
        }
        default_args.update(kwargs)
        
        logger.info(f"Launching Firefox with args: {default_args}")
        browser = await self.browser_type.launch(**default_args)
        logger.info("Firefox browser launched successfully")
        return browser
    
    def get_browser_type(self) -> str:
        return "firefox"


class ChromiumBrowser(BrowserInterface):
    """Chromium browser implementation (for future use)"""
    
    def __init__(self, playwright_instance):
        self.playwright = playwright_instance
        self.browser_type: BrowserType = self.playwright.chromium
    
    async def launch(self, **kwargs) -> Browser:
        """Launch Chromium browser"""
        default_args = {
            'headless': True,
            'args': [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu'
            ]
        }
        default_args.update(kwargs)
        
        logger.info(f"Launching Chromium with args: {default_args}")
        browser = await self.browser_type.launch(**default_args)
        logger.info("Chromium browser launched successfully")
        return browser
    
    def get_browser_type(self) -> str:
        return "chromium"


class BrowserFactory:
    """Factory for creating browser instances"""
    
    _browsers = {
        'firefox': FirefoxBrowser,
        'chromium': ChromiumBrowser,
    }
    
    def __init__(self):
        self.playwright = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize Playwright"""
        if not self._initialized:
            self.playwright = await async_playwright().start()
            self._initialized = True
            logger.info("Playwright initialized")
    
    async def create_browser(
        self, 
        browser_type: str = 'firefox',
        **launch_options
    ) -> tuple[BrowserInterface, Browser]:
        """
        Create a browser instance using factory pattern
        
        Args:
            browser_type: Type of browser ('firefox', 'chromium')
            **launch_options: Additional browser launch options
            
        Returns:
            Tuple of (BrowserInterface, Browser instance)
        """
        if not self._initialized:
            await self.initialize()
        
        browser_type = browser_type.lower()
        
        if browser_type not in self._browsers:
            raise ValueError(
                f"Unsupported browser type: {browser_type}. "
                f"Available: {list(self._browsers.keys())}"
            )
        
        browser_class = self._browsers[browser_type]
        browser_interface = browser_class(self.playwright)
        browser_instance = await browser_interface.launch(**launch_options)
        
        logger.info(f"Created {browser_type} browser via factory")
        return browser_interface, browser_instance
    
    @classmethod
    def register_browser(cls, name: str, browser_class: type):
        """Register a new browser type (for extensibility)"""
        cls._browsers[name] = browser_class
        logger.info(f"Registered new browser type: {name}")
    
    async def cleanup(self):
        """Cleanup Playwright resources"""
        if self.playwright:
            await self.playwright.stop()
            self._initialized = False
            logger.info("Playwright cleaned up")
