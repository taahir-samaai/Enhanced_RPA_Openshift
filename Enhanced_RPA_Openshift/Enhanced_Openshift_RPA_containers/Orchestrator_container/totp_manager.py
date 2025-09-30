"""
TOTP Manager
-----------
Centralized TOTP generation and usage tracking with Valkey.
Prevents concurrent jobs from using the same TOTP code.
"""
import logging
import time
import pyotp
from typing import Optional, Dict
from datetime import datetime, timedelta
import valkey

logger = logging.getLogger(__name__)


class TOTPManager:
    """
    Centralized TOTP management with Valkey-based usage tracking.
    
    Features:
    - Generate fresh TOTP codes
    - Track code usage to prevent conflicts
    - Monitor TOTP metrics per provider
    - Handle timing windows appropriately
    """
    
    def __init__(self, config_manager):
        """
        Initialize TOTP manager.
        
        Args:
            config_manager: ConfigManager instance for settings
        """
        self.config_manager = config_manager
        self.valkey_client = None
        self.totp_secrets = {}
        
        # TOTP configuration
        self.totp_window = 30  # TOTP codes valid for 30 seconds
        self.used_codes_ttl = 60  # Track used codes for 60 seconds
        
        # Providers requiring TOTP
        self.totp_providers = ["octotel"]
        
        logger.info("TOTP Manager initialized")
    
    def initialize(self) -> bool:
        """
        Initialize Valkey connection and load TOTP secrets.
        
        Returns:
            bool: True if initialization successful
        """
        try:
            # Initialize Valkey connection
            valkey_host = self.config_manager.get("VALKEY_HOST", "valkey-service")
            valkey_port = int(self.config_manager.get("VALKEY_PORT", "6379"))
            valkey_password = self.config_manager.get("VALKEY_PASSWORD")
            
            self.valkey_client = valkey.Valkey(
                host=valkey_host,
                port=valkey_port,
                password=valkey_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            
            # Test connection
            self.valkey_client.ping()
            logger.info(f"Connected to Valkey at {valkey_host}:{valkey_port}")
            
            # Load TOTP secrets from config
            self._load_totp_secrets()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize TOTP manager: {e}")
            return False
    
    def _load_totp_secrets(self):
        """Load TOTP secrets from configuration."""
        # Load secrets for providers that require TOTP
        for provider in self.totp_providers:
            secret_key = f"{provider.upper()}_TOTP_SECRET"
            secret = self.config_manager.get(secret_key)
            
            if secret:
                self.totp_secrets[provider] = secret
                logger.info(f"Loaded TOTP secret for {provider}")
            else:
                logger.warning(f"No TOTP secret found for {provider}")
    
    def provider_requires_totp(self, provider: str) -> bool:
        """
        Check if a provider requires TOTP authentication.
        
        Args:
            provider: Provider name
            
        Returns:
            bool: True if provider requires TOTP
        """
        return provider.lower() in self.totp_providers
    
    def get_fresh_totp_code(self, provider: str, job_id: int, max_retries: int = 3) -> Optional[str]:
        """
        Generate a fresh TOTP code that hasn't been used recently.
        
        Args:
            provider: Provider name (e.g., 'octotel')
            job_id: Job identifier for tracking
            max_retries: Maximum retries if code is in use
            
        Returns:
            str: Fresh TOTP code, or None if generation failed
        """
        provider = provider.lower()
        
        if provider not in self.totp_secrets:
            logger.error(f"No TOTP secret configured for provider: {provider}")
            return None
        
        try:
            secret = self.totp_secrets[provider]
            totp = pyotp.TOTP(secret)
            
            for attempt in range(max_retries):
                # Generate current TOTP code
                code = totp.now()
                
                # Check if this code has been used recently
                if not self._is_code_used(provider, code):
                    # Reserve the code for this job
                    if self._reserve_code(provider, code, job_id):
                        logger.info(f"Generated fresh TOTP code for {provider}, job {job_id}")
                        
                        # Track generation metrics
                        self._record_totp_generation(provider, job_id)
                        
                        return code
                
                # If code is in use, wait for next time window
                logger.info(f"TOTP code for {provider} in use, waiting for next window...")
                self._wait_for_next_window()
            
            logger.error(f"Failed to generate fresh TOTP for {provider} after {max_retries} attempts")
            return None
            
        except Exception as e:
            logger.error(f"Error generating TOTP for {provider}: {e}")
            return None
    
    def _is_code_used(self, provider: str, code: str) -> bool:
        """
        Check if a TOTP code has been used recently.
        
        Args:
            provider: Provider name
            code: TOTP code to check
            
        Returns:
            bool: True if code is in use
        """
        try:
            key = f"totp:used:{provider}:{code}"
            return self.valkey_client.exists(key) > 0
        except Exception as e:
            logger.error(f"Error checking TOTP code usage: {e}")
            # Err on the side of caution - assume code is used
            return True
    
    def _reserve_code(self, provider: str, code: str, job_id: int) -> bool:
        """
        Reserve a TOTP code for a specific job.
        
        Args:
            provider: Provider name
            code: TOTP code to reserve
            job_id: Job identifier
            
        Returns:
            bool: True if reservation successful
        """
        try:
            key = f"totp:used:{provider}:{code}"
            
            # Use SET with NX (only set if not exists) and EX (expiry)
            result = self.valkey_client.set(
                key,
                json.dumps({
                    "job_id": job_id,
                    "reserved_at": datetime.utcnow().isoformat(),
                    "provider": provider
                }),
                nx=True,  # Only set if key doesn't exist
                ex=self.used_codes_ttl  # Expire after TTL
            )
            
            return result is not None
            
        except Exception as e:
            logger.error(f"Error reserving TOTP code: {e}")
            return False
    
    def mark_totp_consumed(self, provider: str, job_id: int, success: bool):
        """
        Mark a TOTP code as consumed and record the outcome.
        
        Args:
            provider: Provider name
            job_id: Job identifier
            success: Whether authentication was successful
        """
        try:
            # Record consumption metrics
            key = f"totp:consumed:{provider}:{job_id}"
            self.valkey_client.set(
                key,
                json.dumps({
                    "consumed_at": datetime.utcnow().isoformat(),
                    "success": success
                }),
                ex=3600  # Keep for 1 hour for metrics
            )
            
            # Update success rate metrics
            if success:
                self.valkey_client.incr(f"totp:metrics:{provider}:success")
            else:
                self.valkey_client.incr(f"totp:metrics:{provider}:failure")
            
            logger.info(f"Marked TOTP for job {job_id} as consumed (success={success})")
            
        except Exception as e:
            logger.error(f"Error marking TOTP as consumed: {e}")
    
    def _wait_for_next_window(self):
        """Wait for the next TOTP time window."""
        # Calculate time until next window
        current_time = int(time.time())
        seconds_in_window = current_time % self.totp_window
        wait_time = self.totp_window - seconds_in_window + 1  # +1 for safety
        
        logger.info(f"Waiting {wait_time} seconds for next TOTP window")
        time.sleep(wait_time)
    
    def _record_totp_generation(self, provider: str, job_id: int):
        """Record TOTP generation for metrics."""
        try:
            key = f"totp:generated:{provider}"
            self.valkey_client.incr(key)
            
            # Also record in a sorted set with timestamp
            timestamp = datetime.utcnow().timestamp()
            self.valkey_client.zadd(
                f"totp:timeline:{provider}",
                {str(job_id): timestamp}
            )
            
            # Keep only last 1000 entries
            self.valkey_client.zremrangebyrank(f"totp:timeline:{provider}", 0, -1001)
            
        except Exception as e:
            logger.error(f"Error recording TOTP generation: {e}")
    
    def get_totp_metrics(self, provider: str) -> Dict[str, any]:
        """
        Get TOTP usage metrics for a provider.
        
        Args:
            provider: Provider name
            
        Returns:
            dict: Metrics including success rate, generations, etc.
        """
        try:
            generated = int(self.valkey_client.get(f"totp:generated:{provider}") or 0)
            successes = int(self.valkey_client.get(f"totp:metrics:{provider}:success") or 0)
            failures = int(self.valkey_client.get(f"totp:metrics:{provider}:failure") or 0)
            
            total_consumed = successes + failures
            success_rate = (successes / total_consumed * 100) if total_consumed > 0 else 0
            
            # Get recent activity
            recent_jobs = self.valkey_client.zrevrange(
                f"totp:timeline:{provider}",
                0, 9,  # Last 10 jobs
                withscores=True
            )
            
            return {
                "provider": provider,
                "generated": generated,
                "consumed": total_consumed,
                "successes": successes,
                "failures": failures,
                "success_rate": round(success_rate, 2),
                "recent_jobs": [
                    {
                        "job_id": int(job_id),
                        "timestamp": datetime.fromtimestamp(timestamp).isoformat()
                    }
                    for job_id, timestamp in recent_jobs
                ]
            }
            
        except Exception as e:
            logger.error(f"Error getting TOTP metrics for {provider}: {e}")
            return {}
    
    def health_check(self) -> bool:
        """
        Check if TOTP manager is healthy.
        
        Returns:
            bool: True if healthy
        """
        try:
            if not self.valkey_client:
                return False
            
            # Test Valkey connection
            self.valkey_client.ping()
            
            # Check if we have TOTP secrets loaded
            if not self.totp_secrets:
                logger.warning("No TOTP secrets loaded")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"TOTP manager health check failed: {e}")
            return False
    
    def reset_metrics(self, provider: str):
        """Reset metrics for a provider (admin function)."""
        try:
            keys_to_delete = [
                f"totp:generated:{provider}",
                f"totp:metrics:{provider}:success",
                f"totp:metrics:{provider}:failure",
                f"totp:timeline:{provider}"
            ]
            
            for key in keys_to_delete:
                self.valkey_client.delete(key)
            
            logger.info(f"Reset TOTP metrics for {provider}")
            
        except Exception as e:
            logger.error(f"Error resetting metrics: {e}")


# Add json import
import json
