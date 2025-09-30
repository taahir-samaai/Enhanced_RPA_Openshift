"""
Config Manager
-------------
Manages configuration from OpenShift Secrets and ConfigMaps.
Replaces traditional config.py with OpenShift-native configuration.
"""
import os
import logging
import json
from typing import Any, Optional, List, Dict

logger = logging.getLogger(__name__)


class ConfigManager:
    """
    OpenShift-native configuration manager.
    
    Configuration sources (in order of precedence):
    1. Environment variables (from Secrets/ConfigMaps)
    2. Default values
    
    Usage:
        config = ConfigManager()
        db_url = config.get("DATABASE_URL")
        debug = config.get_bool("DEBUG_MODE")
        workers = config.get_int("MAX_WORKERS", default=4)
    """
    
    def __init__(self):
        """Initialize configuration manager."""
        self._config_cache = {}
        self._load_configuration()
        logger.info("ConfigManager initialized with OpenShift configuration")
    
    def _load_configuration(self):
        """Load configuration from environment variables."""
        # In OpenShift, Secrets and ConfigMaps are mounted as environment variables
        # or as files in /etc/config and /etc/secrets
        
        # Load from environment (primary method)
        logger.info("Loading configuration from environment variables")
        
        # Also check for mounted config files
        self._load_from_mounted_files()
    
    def _load_from_mounted_files(self):
        """Load configuration from mounted Secret/ConfigMap files."""
        # Secrets mounted at /etc/secrets
        secrets_path = "/etc/secrets"
        if os.path.exists(secrets_path):
            logger.info(f"Loading secrets from {secrets_path}")
            for filename in os.listdir(secrets_path):
                filepath = os.path.join(secrets_path, filename)
                if os.path.isfile(filepath):
                    try:
                        with open(filepath, 'r') as f:
                            content = f.read().strip()
                            # Store with uppercase key
                            key = filename.upper().replace('-', '_')
                            self._config_cache[key] = content
                            logger.debug(f"Loaded secret: {key}")
                    except Exception as e:
                        logger.error(f"Error reading secret file {filename}: {e}")
        
        # ConfigMaps mounted at /etc/config
        config_path = "/etc/config"
        if os.path.exists(config_path):
            logger.info(f"Loading config from {config_path}")
            for filename in os.listdir(config_path):
                filepath = os.path.join(config_path, filename)
                if os.path.isfile(filepath):
                    try:
                        with open(filepath, 'r') as f:
                            content = f.read().strip()
                            key = filename.upper().replace('-', '_')
                            self._config_cache[key] = content
                            logger.debug(f"Loaded config: {key}")
                    except Exception as e:
                        logger.error(f"Error reading config file {filename}: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value.
        
        Args:
            key: Configuration key (case-insensitive)
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        key = key.upper()
        
        # Check environment variables first
        value = os.getenv(key)
        if value is not None:
            return value
        
        # Check cache (from mounted files)
        value = self._config_cache.get(key)
        if value is not None:
            return value
        
        # Return default
        return default
    
    def get_int(self, key: str, default: int = 0) -> int:
        """
        Get configuration value as integer.
        
        Args:
            key: Configuration key
            default: Default value if key not found or conversion fails
            
        Returns:
            Integer value
        """
        value = self.get(key)
        if value is None:
            return default
        
        try:
            return int(value)
        except (ValueError, TypeError):
            logger.warning(f"Could not convert {key}={value} to int, using default {default}")
            return default
    
    def get_float(self, key: str, default: float = 0.0) -> float:
        """
        Get configuration value as float.
        
        Args:
            key: Configuration key
            default: Default value if key not found or conversion fails
            
        Returns:
            Float value
        """
        value = self.get(key)
        if value is None:
            return default
        
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning(f"Could not convert {key}={value} to float, using default {default}")
            return default
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """
        Get configuration value as boolean.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Boolean value
        """
        value = self.get(key)
        if value is None:
            return default
        
        # Convert string to boolean
        if isinstance(value, bool):
            return value
        
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', '1', 'on', 'enabled')
        
        return bool(value)
    
    def get_list(self, key: str, default: Optional[List] = None, separator: str = ',') -> List:
        """
        Get configuration value as list.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            separator: Separator for splitting string values
            
        Returns:
            List value
        """
        if default is None:
            default = []
        
        value = self.get(key)
        if value is None:
            return default
        
        # If already a list
        if isinstance(value, list):
            return value
        
        # Try to parse as JSON array
        if isinstance(value, str):
            # Check if it's JSON
            if value.strip().startswith('['):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    pass
            
            # Split by separator
            return [item.strip() for item in value.split(separator) if item.strip()]
        
        return default
    
    def get_dict(self, key: str, default: Optional[Dict] = None) -> Dict:
        """
        Get configuration value as dictionary.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Dictionary value
        """
        if default is None:
            default = {}
        
        value = self.get(key)
        if value is None:
            return default
        
        # If already a dict
        if isinstance(value, dict):
            return value
        
        # Try to parse as JSON
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.warning(f"Could not parse {key} as JSON, using default")
        
        return default
    
    def get_secret(self, key: str, required: bool = False) -> Optional[str]:
        """
        Get a secret value with additional security considerations.
        
        Args:
            key: Secret key
            required: Whether the secret is required
            
        Returns:
            Secret value or None
            
        Raises:
            ValueError: If required secret is missing
        """
        value = self.get(key)
        
        if value is None and required:
            raise ValueError(f"Required secret '{key}' is not configured")
        
        return value
    
    def reload(self):
        """Reload configuration (useful for config updates without restart)."""
        logger.info("Reloading configuration")
        self._config_cache.clear()
        self._load_configuration()
    
    def get_all_keys(self) -> List[str]:
        """
        Get all configuration keys (for debugging).
        
        Returns:
            List of configuration keys
        """
        env_keys = list(os.environ.keys())
        cache_keys = list(self._config_cache.keys())
        return sorted(set(env_keys + cache_keys))
    
    def validate_required_config(self, required_keys: List[str]) -> bool:
        """
        Validate that all required configuration keys are present.
        
        Args:
            required_keys: List of required configuration keys
            
        Returns:
            bool: True if all required keys present
        """
        missing_keys = []
        
        for key in required_keys:
            if self.get(key) is None:
                missing_keys.append(key)
        
        if missing_keys:
            logger.error(f"Missing required configuration keys: {', '.join(missing_keys)}")
            return False
        
        logger.info("All required configuration keys present")
        return True
    
    def get_database_config(self) -> Dict[str, str]:
        """Get database configuration."""
        return {
            "url": self.get("DATABASE_URL", "sqlite:///rpa_orchestrator.db"),
            "pool_size": self.get_int("DB_POOL_SIZE", 10),
            "max_overflow": self.get_int("DB_MAX_OVERFLOW", 20),
            "pool_timeout": self.get_int("DB_POOL_TIMEOUT", 30),
            "pool_recycle": self.get_int("DB_POOL_RECYCLE", 3600),
        }
    
    def get_orchestrator_config(self) -> Dict[str, Any]:
        """Get orchestrator-specific configuration."""
        return {
            "host": self.get("ORCHESTRATOR_HOST", "0.0.0.0"),
            "port": self.get_int("ORCHESTRATOR_PORT", 8620),
            "url": self.get("ORCHESTRATOR_URL", "http://rpa-orchestrator-service:8620"),
            "max_workers": self.get_int("MAX_WORKERS", 10),
            "poll_interval": self.get_int("POLL_INTERVAL", 5),
            "worker_timeout": self.get_int("WORKER_TIMEOUT", 30),
        }
    
    def get_browser_service_config(self) -> Dict[str, Any]:
        """Get browser service configuration."""
        return {
            "image": self.get("BROWSER_SERVICE_IMAGE", "rpa-browser:v2.0-enhanced"),
            "namespace": self.get("NAMESPACE", "rpa-system"),
            "cpu_request": self.get("BROWSER_CPU_REQUEST", "500m"),
            "cpu_limit": self.get("BROWSER_CPU_LIMIT", "2"),
            "memory_request": self.get("BROWSER_MEMORY_REQUEST", "1Gi"),
            "memory_limit": self.get("BROWSER_MEMORY_LIMIT", "4Gi"),
            "idle_timeout": self.get_int("BROWSER_IDLE_TIMEOUT", 10),
        }
    
    def get_valkey_config(self) -> Dict[str, Any]:
        """Get Valkey configuration."""
        return {
            "host": self.get("VALKEY_HOST", "valkey-service"),
            "port": self.get_int("VALKEY_PORT", 6379),
            "password": self.get_secret("VALKEY_PASSWORD"),
            "db": self.get_int("VALKEY_DB", 0),
            "socket_timeout": self.get_int("VALKEY_SOCKET_TIMEOUT", 5),
        }
    
    def get_provider_credentials(self, provider: str) -> Dict[str, str]:
        """
        Get credentials for a specific provider.
        
        Args:
            provider: Provider name (e.g., 'metrofiber', 'octotel')
            
        Returns:
            Dictionary of credentials
        """
        provider = provider.upper()
        
        credentials = {
            "url": self.get(f"{provider}_URL"),
            "email": self.get(f"{provider}_EMAIL"),
            "username": self.get(f"{provider}_USERNAME"),
            "password": self.get_secret(f"{provider}_PASSWORD"),
            "totp_secret": self.get_secret(f"{provider}_TOTP_SECRET"),
        }
        
        # Remove None values
        return {k: v for k, v in credentials.items() if v is not None}
    
    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging configuration."""
        return {
            "level": self.get("LOG_LEVEL", "INFO"),
            "path": self.get("LOG_PATH", "/var/logs/orchestrator.log"),
            "format": self.get("LOG_FORMAT", "%(asctime)s [%(levelname)s] %(name)s: %(message)s"),
        }
    
    def __repr__(self) -> str:
        """String representation (for debugging)."""
        return f"ConfigManager(keys={len(self.get_all_keys())})"
