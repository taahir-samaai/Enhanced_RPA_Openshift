"""
Session Factory - Factory Pattern for Browser Session/Context Creation
----------------------------------------------------------------------
Creates different browser contexts with various configurations.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from playwright.async_api import Browser, BrowserContext, Page
import logging

logger = logging.getLogger(__name__)


class SessionConfig(ABC):
    """Abstract base class for session configurations"""
    
    @abstractmethod
    def get_context_options(self) -> Dict[str, Any]:
        """Get browser context options"""
        pass
    
    @abstractmethod
    def get_session_type(self) -> str:
        """Get session type name"""
        pass


class StandardSession(SessionConfig):
    """Standard browser session configuration"""
    
    def __init__(self, viewport: Optional[Dict[str, int]] = None):
        self.viewport = viewport or {'width': 1920, 'height': 1080}
    
    def get_context_options(self) -> Dict[str, Any]:
        return {
            'viewport': self.viewport,
            'user_agent': 'Mozilla/5.0 (X11; Linux x86_64) Firefox/120.0',
            'locale': 'en-US',
            'timezone_id': 'Africa/Johannesburg',
            'permissions': [],
            'ignore_https_errors': False,
        }
    
    def get_session_type(self) -> str:
        return "standard"


class MobileSession(SessionConfig):
    """Mobile browser session configuration"""
    
    def __init__(self, device: str = 'iPhone 12'):
        self.device = device
    
    def get_context_options(self) -> Dict[str, Any]:
        # Playwright device descriptors
        devices = {
            'iPhone 12': {
                'viewport': {'width': 390, 'height': 844},
                'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)',
                'device_scale_factor': 3,
                'is_mobile': True,
                'has_touch': True,
            }
        }
        
        return devices.get(self.device, devices['iPhone 12'])
    
    def get_session_type(self) -> str:
        return "mobile"


class IncognitoSession(SessionConfig):
    """Incognito/private browsing session"""
    
    def get_context_options(self) -> Dict[str, Any]:
        return {
            'viewport': {'width': 1920, 'height': 1080},
            'user_agent': 'Mozilla/5.0 (X11; Linux x86_64) Firefox/120.0',
            'locale': 'en-US',
            'accept_downloads': False,
            'ignore_https_errors': False,
            'java_script_enabled': True,
        }
    
    def get_session_type(self) -> str:
        return "incognito"


class SessionFactory:
    """Factory for creating browser sessions/contexts"""
    
    _session_configs = {
        'standard': StandardSession,
        'mobile': MobileSession,
        'incognito': IncognitoSession,
    }
    
    def __init__(self, browser: Browser):
        self.browser = browser
        self.active_contexts: Dict[str, BrowserContext] = {}
        self.active_pages: Dict[str, Page] = {}
    
    async def create_session(
        self,
        session_id: str,
        session_type: str = 'standard',
        **config_kwargs
    ) -> tuple[BrowserContext, Page]:
        """
        Create a browser session with specific configuration
        
        Args:
            session_id: Unique session identifier
            session_type: Type of session ('standard', 'mobile', 'incognito')
            **config_kwargs: Additional configuration options
            
        Returns:
            Tuple of (BrowserContext, Page)
        """
        if session_id in self.active_contexts:
            logger.warning(f"Session {session_id} already exists, returning existing")
            return self.active_contexts[session_id], self.active_pages[session_id]
        
        session_type = session_type.lower()
        
        if session_type not in self._session_configs:
            raise ValueError(
                f"Unsupported session type: {session_type}. "
                f"Available: {list(self._session_configs.keys())}"
            )
        
        # Create session configuration
        config_class = self._session_configs[session_type]
        session_config = config_class(**config_kwargs)
        context_options = session_config.get_context_options()
        
        # Create browser context
        context = await self.browser.new_context(**context_options)
        logger.info(
            f"Created {session_type} context for session {session_id} "
            f"with options: {context_options}"
        )
        
        # Create page
        page = await context.new_page()
        logger.info(f"Created page for session {session_id}")
        
        # Store active session
        self.active_contexts[session_id] = context
        self.active_pages[session_id] = page
        
        return context, page
    
    async def get_session(self, session_id: str) -> Optional[tuple[BrowserContext, Page]]:
        """Get an existing session"""
        if session_id not in self.active_contexts:
            return None
        return self.active_contexts[session_id], self.active_pages[session_id]
    
    async def close_session(self, session_id: str):
        """Close a specific session"""
        if session_id in self.active_contexts:
            context = self.active_contexts[session_id]
            page = self.active_pages[session_id]
            
            await page.close()
            await context.close()
            
            del self.active_contexts[session_id]
            del self.active_pages[session_id]
            
            logger.info(f"Closed session {session_id}")
    
    async def close_all_sessions(self):
        """Close all active sessions"""
        session_ids = list(self.active_contexts.keys())
        for session_id in session_ids:
            await self.close_session(session_id)
        logger.info("All sessions closed")
    
    def get_active_session_count(self) -> int:
        """Get count of active sessions"""
        return len(self.active_contexts)
    
    @classmethod
    def register_session_type(cls, name: str, config_class: type):
        """Register a new session type (for extensibility)"""
        cls._session_configs[name] = config_class
        logger.info(f"Registered new session type: {name}")
