"""
Configuration - Browser Service Configuration
---------------------------------------------
Configuration management using environment variables.
"""
import os
from typing import List


class Config:
    """Browser service configuration"""
    
    # Service Configuration
    SERVICE_NAME = os.getenv('SERVICE_NAME', 'browser-service')
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 8080))
    
    # Browser Configuration
    BROWSER_TYPE = 'firefox'  # Fixed: Only Firefox is used
    HEADLESS = os.getenv('HEADLESS', 'true').lower() == 'true'
    
    # Session Configuration
    DEFAULT_SESSION_TYPE = 'incognito'  # Fixed: Always use incognito mode
    DEFAULT_TIMEOUT = int(os.getenv('DEFAULT_TIMEOUT', 30000))  # milliseconds
    MAX_SESSIONS = int(os.getenv('MAX_SESSIONS', 5))
    SESSION_IDLE_TIMEOUT = int(os.getenv('SESSION_IDLE_TIMEOUT', 300))  # seconds
    
    # Security Configuration
    JWT_SECRET = os.getenv('JWT_SECRET')
    JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
    ALLOWED_IPS = os.getenv('ALLOWED_IPS', '').split(',') if os.getenv('ALLOWED_IPS') else []
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    
    # Resource Limits
    MEMORY_LIMIT_MB = int(os.getenv('MEMORY_LIMIT_MB', 2048))
    CPU_LIMIT = float(os.getenv('CPU_LIMIT', 2.0))
    
    # Screenshot Configuration
    SCREENSHOT_ENABLED = os.getenv('SCREENSHOT_ENABLED', 'true').lower() == 'true'
    SCREENSHOT_MAX_SIZE = int(os.getenv('SCREENSHOT_MAX_SIZE', 5242880))  # 5MB
    
    # Health Check Configuration
    HEALTH_CHECK_INTERVAL = int(os.getenv('HEALTH_CHECK_INTERVAL', 30))  # seconds
    
    # OpenShift Configuration
    OPENSHIFT_NAMESPACE = os.getenv('OPENSHIFT_NAMESPACE', 'rpa-system')
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        errors = []
        
        if not cls.JWT_SECRET:
            errors.append("JWT_SECRET is required")
        
        if cls.BROWSER_TYPE not in ['firefox', 'chromium']:
            errors.append(f"Invalid BROWSER_TYPE: {cls.BROWSER_TYPE}")
        
        if cls.DEFAULT_TIMEOUT < 1000:
            errors.append("DEFAULT_TIMEOUT must be at least 1000ms")
        
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
    
    @classmethod
    def get_browser_launch_options(cls) -> dict:
        """Get browser launch options"""
        return {
            'headless': cls.HEADLESS,
            'args': [
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ] + cls._get_additional_browser_args()
        }
    
    @classmethod
    def _get_additional_browser_args(cls) -> List[str]:
        """Get additional browser arguments from environment"""
        args_str = os.getenv('BROWSER_ARGS', '')
        return [arg.strip() for arg in args_str.split(',') if arg.strip()]
    
    @classmethod
    def to_dict(cls) -> dict:
        """Convert configuration to dictionary"""
        return {
            'service_name': cls.SERVICE_NAME,
            'host': cls.HOST,
            'port': cls.PORT,
            'browser_type': cls.BROWSER_TYPE,
            'headless': cls.HEADLESS,
            'default_timeout': cls.DEFAULT_TIMEOUT,
            'max_sessions': cls.MAX_SESSIONS,
            'log_level': cls.LOG_LEVEL,
            'screenshot_enabled': cls.SCREENSHOT_ENABLED,
        }
