# browser_service/factories/__init__.py
"""
Factories Package
-----------------
Factory pattern implementations for browser and session creation.
"""
from .browser_factory import BrowserFactory, BrowserInterface, FirefoxBrowser, ChromiumBrowser
from .session_factory import SessionFactory, SessionConfig, StandardSession, MobileSession, IncognitoSession

__all__ = [
    'BrowserFactory',
    'BrowserInterface',
    'FirefoxBrowser',
    'ChromiumBrowser',
    'SessionFactory',
    'SessionConfig',
    'StandardSession',
    'MobileSession',
    'IncognitoSession',
]


# browser_service/managers/__init__.py
"""
Managers Package
----------------
Core management classes for browser lifecycle and operations.
"""
from .browser_manager import BrowserManager

__all__ = ['BrowserManager']


# browser_service/models/__init__.py
"""
Models Package
--------------
Pydantic models for request/response validation.
"""
from .requests import (
    CreateSessionRequest,
    NavigateRequest,
    ClickRequest,
    FillRequest,
    TOTPRequest,
    GetTextRequest,
    GetAttributeRequest,
    WaitForSelectorRequest,
    ScreenshotRequest,
    EvaluateRequest,
    SessionResponse,
    OperationResponse,
    TextResponse,
    AttributeResponse,
    SessionInfoResponse,
    HealthResponse,
    ErrorResponse,
    WaitUntilEnum,
    SessionTypeEnum,
    ElementStateEnum,
)

__all__ = [
    'CreateSessionRequest',
    'NavigateRequest',
    'ClickRequest',
    'FillRequest',
    'TOTPRequest',
    'GetTextRequest',
    'GetAttributeRequest',
    'WaitForSelectorRequest',
    'ScreenshotRequest',
    'EvaluateRequest',
    'SessionResponse',
    'OperationResponse',
    'TextResponse',
    'AttributeResponse',
    'SessionInfoResponse',
    'HealthResponse',
    'ErrorResponse',
    'WaitUntilEnum',
    'SessionTypeEnum',
    'ElementStateEnum',
]


# browser_service/middleware/__init__.py
"""
Middleware Package
------------------
Authentication and middleware components.
"""
from .auth import AuthService, verify_service_token, require_service, IPWhitelistMiddleware

__all__ = [
    'AuthService',
    'verify_service_token',
    'require_service',
    'IPWhitelistMiddleware',
]


# browser_service/utils/__init__.py
"""
Utils Package
-------------
Utility functions and helpers.
"""

__all__ = []
