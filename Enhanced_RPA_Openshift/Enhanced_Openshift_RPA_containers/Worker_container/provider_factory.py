"""
Provider Factory
================
Factory pattern implementation for loading provider-specific automation modules.
Supports dynamic registration and discovery of automation providers.
"""

import logging
from typing import Dict, Optional, Type
from abc import ABC, abstractmethod

from browser_client import BrowserServiceClient

logger = logging.getLogger(__name__)


# ============================================================================
# Exceptions
# ============================================================================

class AutomationError(Exception):
    """Base exception for automation errors"""
    pass


class ProviderNotFoundError(AutomationError):
    """Raised when provider is not registered"""
    pass


class ActionNotFoundError(AutomationError):
    """Raised when action is not available for provider"""
    pass


# ============================================================================
# Base Automation Class
# ============================================================================

class BaseAutomation(ABC):
    """
    Base class for all provider automation modules
    
    All provider-specific automations must inherit from this class
    and implement the execute method.
    """
    
    def __init__(self, browser_client: BrowserServiceClient):
        """
        Initialize automation
        
        Args:
            browser_client: Browser service client for automation
        """
        self.browser = browser_client
        self.session_id: Optional[str] = None
    
    @abstractmethod
    async def execute(self, job_id: int, parameters: Dict) -> Dict:
        """
        Execute automation
        
        Args:
            job_id: Job identifier
            parameters: Job parameters including:
                - circuit_number / order_id
                - customer_name (optional)
                - totp_code (for providers requiring TOTP)
                - Other provider-specific parameters
        
        Returns:
            Result dictionary with:
                - status: success/error
                - message: Human-readable message
                - data: Provider-specific result data
                - evidence: Screenshots, logs, etc.
        """
        pass
    
    async def create_session(self, job_id: int) -> str:
        """Create browser session for this job"""
        if self.session_id:
            logger.warning(f"Session already exists for job {job_id}")
            return self.session_id
        
        self.session_id = await self.browser.create_session(job_id, headless=True)
        return self.session_id
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.session_id:
            await self.browser.close_session(self.session_id)
            self.session_id = None
    
    async def take_screenshot(self, name: str = "screenshot") -> str:
        """Take screenshot and return base64 data"""
        if not self.session_id:
            raise AutomationError("No active session for screenshot")
        return await self.browser.screenshot(self.session_id, full_page=True)


# ============================================================================
# Provider Factory
# ============================================================================

class ProviderFactory:
    """
    Factory for creating provider automation instances
    
    Uses registration pattern to support dynamic provider loading.
    """
    
    def __init__(self, browser_client: BrowserServiceClient):
        """
        Initialize provider factory
        
        Args:
            browser_client: Browser service client to pass to automations
        """
        self.browser_client = browser_client
        self._providers: Dict[str, Dict[str, Type[BaseAutomation]]] = {}
        
        # Auto-register built-in providers
        self._register_builtin_providers()
    
    def _register_builtin_providers(self):
        """Register built-in provider modules"""
        try:
            # Import and register MFN
            from providers.mfn.validation import MFNValidation
            from providers.mfn.cancellation import MFNCancellation
            self.register_provider("mfn", "validation", MFNValidation)
            self.register_provider("mfn", "cancellation", MFNCancellation)
            logger.info("Registered MFN provider")
        except ImportError as e:
            logger.warning(f"Failed to register MFN provider: {e}")
        
        try:
            # Import and register OSN
            from providers.osn.validation import OSNValidation
            from providers.osn.cancellation import OSNCancellation
            self.register_provider("osn", "validation", OSNValidation)
            self.register_provider("osn", "cancellation", OSNCancellation)
            logger.info("Registered OSN provider")
        except ImportError as e:
            logger.warning(f"Failed to register OSN provider: {e}")
        
        try:
            # Import and register Octotel
            from providers.octotel.validation import OctotelValidation
            from providers.octotel.cancellation import OctotelCancellation
            self.register_provider("octotel", "validation", OctotelValidation)
            self.register_provider("octotel", "cancellation", OctotelCancellation)
            logger.info("Registered Octotel provider")
        except ImportError as e:
            logger.warning(f"Failed to register Octotel provider: {e}")
        
        try:
            # Import and register Evotel
            from providers.evotel.validation import EvotelValidation
            from providers.evotel.cancellation import EvotelCancellation
            self.register_provider("evotel", "validation", EvotelValidation)
            self.register_provider("evotel", "cancellation", EvotelCancellation)
            logger.info("Registered Evotel provider")
        except ImportError as e:
            logger.warning(f"Failed to register Evotel provider: {e}")
    
    def register_provider(self, provider: str, action: str, automation_class: Type[BaseAutomation]):
        """
        Register a provider automation
        
        Args:
            provider: Provider name (e.g., 'mfn')
            action: Action name (e.g., 'validation')
            automation_class: Automation class (must inherit from BaseAutomation)
        """
        if not issubclass(automation_class, BaseAutomation):
            raise ValueError(f"{automation_class.__name__} must inherit from BaseAutomation")
        
        provider = provider.lower()
        action = action.lower()
        
        if provider not in self._providers:
            self._providers[provider] = {}
        
        self._providers[provider][action] = automation_class
        logger.debug(f"Registered {provider}.{action} -> {automation_class.__name__}")
    
    def get_automation(self, provider: str, action: str) -> BaseAutomation:
        """
        Get automation instance for provider and action
        
        Args:
            provider: Provider name
            action: Action name
            
        Returns:
            Automation instance ready to execute
            
        Raises:
            ProviderNotFoundError: If provider not registered
            ActionNotFoundError: If action not available for provider
        """
        provider = provider.lower()
        action = action.lower()
        
        if provider not in self._providers:
            raise ProviderNotFoundError(f"Provider '{provider}' not registered")
        
        if action not in self._providers[provider]:
            available = list(self._providers[provider].keys())
            raise ActionNotFoundError(
                f"Action '{action}' not available for provider '{provider}'. "
                f"Available actions: {available}"
            )
        
        automation_class = self._providers[provider][action]
        return automation_class(self.browser_client)
    
    def get_capabilities(self) -> Dict[str, list]:
        """
        Get available providers and their actions
        
        Returns:
            Dictionary of {provider: [actions]}
        """
        return {
            provider: list(actions.keys())
            for provider, actions in self._providers.items()
        }
    
    def is_available(self, provider: str, action: str) -> bool:
        """Check if provider and action are available"""
        provider = provider.lower()
        action = action.lower()
        return provider in self._providers and action in self._providers[provider]
