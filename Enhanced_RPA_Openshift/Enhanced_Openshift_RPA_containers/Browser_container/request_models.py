"""
Request/Response Models
-----------------------
Pydantic models for API request and response validation.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from enum import Enum


class WaitUntilEnum(str, Enum):
    """Page load wait conditions"""
    LOAD = 'load'
    DOMCONTENTLOADED = 'domcontentloaded'
    NETWORKIDLE = 'networkidle'


class SessionTypeEnum(str, Enum):
    """Session types"""
    STANDARD = 'standard'
    MOBILE = 'mobile'
    INCOGNITO = 'incognito'


class ElementStateEnum(str, Enum):
    """Element states"""
    ATTACHED = 'attached'
    DETACHED = 'detached'
    VISIBLE = 'visible'
    HIDDEN = 'hidden'


# Request Models
class CreateSessionRequest(BaseModel):
    """Request to create browser session"""
    session_type: SessionTypeEnum = Field(
        default=SessionTypeEnum.STANDARD,
        description="Type of browser session to create"
    )
    viewport_width: Optional[int] = Field(default=1920, ge=320, le=3840)
    viewport_height: Optional[int] = Field(default=1080, ge=240, le=2160)
    
    class Config:
        schema_extra = {
            "example": {
                "session_type": "standard",
                "viewport_width": 1920,
                "viewport_height": 1080
            }
        }


class NavigateRequest(BaseModel):
    """Request to navigate to URL"""
    url: str = Field(..., description="URL to navigate to")
    wait_until: WaitUntilEnum = Field(
        default=WaitUntilEnum.NETWORKIDLE,
        description="Wait condition after navigation"
    )
    timeout: int = Field(default=30000, ge=1000, le=120000, description="Timeout in milliseconds")
    
    @validator('url')
    def validate_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "url": "https://example.com",
                "wait_until": "networkidle",
                "timeout": 30000
            }
        }


class ClickRequest(BaseModel):
    """Request to click element"""
    selector: str = Field(..., description="CSS selector for element to click")
    timeout: int = Field(default=30000, ge=1000, le=120000)
    force: bool = Field(default=False, description="Force click even if element not actionable")
    
    class Config:
        schema_extra = {
            "example": {
                "selector": "#submit-button",
                "timeout": 30000,
                "force": False
            }
        }


class FillRequest(BaseModel):
    """Request to fill input field"""
    selector: str = Field(..., description="CSS selector for input element")
    value: str = Field(..., description="Value to fill")
    timeout: int = Field(default=30000, ge=1000, le=120000)
    
    class Config:
        schema_extra = {
            "example": {
                "selector": "#username",
                "value": "user@example.com",
                "timeout": 30000
            }
        }


class TOTPRequest(BaseModel):
    """Request to submit TOTP code"""
    selector: str = Field(..., description="CSS selector for TOTP input")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit TOTP code")
    submit: bool = Field(default=True, description="Auto-submit after entering code")
    
    @validator('code')
    def validate_totp_code(cls, v):
        if not v.isdigit():
            raise ValueError('TOTP code must contain only digits')
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "selector": "#totp-code",
                "code": "123456",
                "submit": True
            }
        }


class GetTextRequest(BaseModel):
    """Request to get text from element"""
    selector: str = Field(..., description="CSS selector for element")
    timeout: int = Field(default=30000, ge=1000, le=120000)
    
    class Config:
        schema_extra = {
            "example": {
                "selector": "#result-message",
                "timeout": 30000
            }
        }


class GetAttributeRequest(BaseModel):
    """Request to get element attribute"""
    selector: str = Field(..., description="CSS selector for element")
    attribute: str = Field(..., description="Attribute name to retrieve")
    timeout: int = Field(default=30000, ge=1000, le=120000)
    
    class Config:
        schema_extra = {
            "example": {
                "selector": "#download-link",
                "attribute": "href",
                "timeout": 30000
            }
        }


class WaitForSelectorRequest(BaseModel):
    """Request to wait for element"""
    selector: str = Field(..., description="CSS selector for element")
    state: ElementStateEnum = Field(
        default=ElementStateEnum.VISIBLE,
        description="Target state to wait for"
    )
    timeout: int = Field(default=30000, ge=1000, le=120000)
    
    class Config:
        schema_extra = {
            "example": {
                "selector": "#loading-spinner",
                "state": "hidden",
                "timeout": 30000
            }
        }


class ScreenshotRequest(BaseModel):
    """Request to capture screenshot"""
    full_page: bool = Field(default=False, description="Capture full scrollable page")
    
    class Config:
        schema_extra = {
            "example": {
                "full_page": True
            }
        }


class EvaluateRequest(BaseModel):
    """Request to evaluate JavaScript"""
    expression: str = Field(..., description="JavaScript expression to evaluate")
    
    class Config:
        schema_extra = {
            "example": {
                "expression": "document.title"
            }
        }


# Response Models
class SessionResponse(BaseModel):
    """Response after creating session"""
    session_id: str
    session_type: str
    status: str
    message: str


class OperationResponse(BaseModel):
    """Generic operation response"""
    status: str
    message: str
    details: Optional[Dict[str, Any]] = None


class TextResponse(BaseModel):
    """Response containing text content"""
    text: str
    selector: str


class AttributeResponse(BaseModel):
    """Response containing attribute value"""
    attribute: str
    value: Optional[str]
    selector: str


class SessionInfoResponse(BaseModel):
    """Response with session information"""
    active_sessions: int
    current_session: Optional[str]
    browser_type: Optional[str]
    ready: bool


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    browser_ready: bool
    active_sessions: int
    uptime_seconds: Optional[float] = None


class ErrorResponse(BaseModel):
    """Error response"""
    error: str
    detail: str
    error_type: str
