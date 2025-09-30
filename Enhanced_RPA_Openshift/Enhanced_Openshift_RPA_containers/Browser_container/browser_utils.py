"""
Utility Functions and Helpers
------------------------------
Common utilities for browser service operations.
"""
import time
import logging
from typing import Callable, Any, Optional
from functools import wraps
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 5
    timeout: int = 60
    expected_exception: type = Exception


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.
    Prevents cascading failures by stopping requests after threshold.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 60,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = 'closed'  # closed, open, half_open
    
    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if self.state == 'open':
                if time.time() - self.last_failure_time > self.timeout:
                    logger.info("Circuit breaker: Attempting half-open state")
                    self.state = 'half_open'
                else:
                    raise Exception("Circuit breaker is OPEN")
            
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
                
            except self.expected_exception as e:
                self._on_failure()
                raise
        
        return wrapper
    
    def _on_success(self):
        """Handle successful call"""
        self.failure_count = 0
        if self.state == 'half_open':
            logger.info("Circuit breaker: Closing after successful call")
            self.state = 'closed'
    
    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            logger.warning(
                f"Circuit breaker: OPENING after {self.failure_count} failures"
            )
            self.state = 'open'
    
    def reset(self):
        """Manually reset circuit breaker"""
        self.failure_count = 0
        self.state = 'closed'
        logger.info("Circuit breaker: Manually reset")


def retry_on_exception(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_attempts: Maximum retry attempts
        delay: Initial delay between retries
        backoff: Backoff multiplier
        exceptions: Tuple of exceptions to catch
        
    Usage:
        @retry_on_exception(max_attempts=3, delay=2, backoff=2)
        def flaky_operation():
            # operation that might fail
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 1
            current_delay = delay
            
            while attempt <= max_attempts:
                try:
                    return func(*args, **kwargs)
                    
                except exceptions as e:
                    if attempt == max_attempts:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise
                    
                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {current_delay}s..."
                    )
                    
                    time.sleep(current_delay)
                    current_delay *= backoff
                    attempt += 1
        
        return wrapper
    return decorator


def timeout_handler(timeout_seconds: int):
    """
    Decorator to add timeout to functions.
    
    Args:
        timeout_seconds: Timeout in seconds
        
    Usage:
        @timeout_handler(30)
        def slow_operation():
            # operation that might take too long
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            import signal
            
            def timeout_error(signum, frame):
                raise TimeoutError(f"{func.__name__} exceeded timeout of {timeout_seconds}s")
            
            # Set alarm
            signal.signal(signal.SIGALRM, timeout_error)
            signal.alarm(timeout_seconds)
            
            try:
                result = func(*args, **kwargs)
            finally:
                # Cancel alarm
                signal.alarm(0)
            
            return result
        return wrapper
    return decorator


class RateLimiter:
    """
    Rate limiter for API calls.
    Prevents exceeding rate limits.
    """
    
    def __init__(self, max_calls: int, time_window: int):
        """
        Initialize rate limiter
        
        Args:
            max_calls: Maximum calls allowed
            time_window: Time window in seconds
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
    
    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_time = time.time()
            
            # Remove old calls outside time window
            self.calls = [
                call_time for call_time in self.calls
                if current_time - call_time < self.time_window
            ]
            
            # Check if we can make another call
            if len(self.calls) >= self.max_calls:
                wait_time = self.time_window - (current_time - self.calls[0])
                logger.warning(
                    f"Rate limit reached. Waiting {wait_time:.2f}s"
                )
                time.sleep(wait_time)
                self.calls.pop(0)
            
            # Record this call
            self.calls.append(current_time)
            
            return func(*args, **kwargs)
        
        return wrapper


def measure_execution_time(func: Callable) -> Callable:
    """
    Decorator to measure function execution time.
    
    Usage:
        @measure_execution_time
        def my_function():
            # do something
            pass
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        execution_time = time.time() - start_time
        
        logger.info(
            f"{func.__name__} executed in {execution_time:.2f}s"
        )
        
        return result
    return wrapper


def log_function_call(func: Callable) -> Callable:
    """
    Decorator to log function calls with arguments.
    
    Usage:
        @log_function_call
        def my_function(arg1, arg2):
            # do something
            pass
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        args_repr = [repr(a) for a in args]
        kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
        signature = ", ".join(args_repr + kwargs_repr)
        
        logger.debug(f"Calling {func.__name__}({signature})")
        
        try:
            result = func(*args, **kwargs)
            logger.debug(f"{func.__name__} returned {result!r}")
            return result
        except Exception as e:
            logger.error(f"{func.__name__} raised {type(e).__name__}: {e}")
            raise
    
    return wrapper


class PerformanceMonitor:
    """
    Monitor and track performance metrics.
    """
    
    def __init__(self):
        self.metrics = {}
    
    def record_metric(self, name: str, value: float):
        """Record a performance metric"""
        if name not in self.metrics:
            self.metrics[name] = []
        self.metrics[name].append(value)
    
    def get_average(self, name: str) -> Optional[float]:
        """Get average value for a metric"""
        if name not in self.metrics or not self.metrics[name]:
            return None
        return sum(self.metrics[name]) / len(self.metrics[name])
    
    def get_min(self, name: str) -> Optional[float]:
        """Get minimum value for a metric"""
        if name not in self.metrics or not self.metrics[name]:
            return None
        return min(self.metrics[name])
    
    def get_max(self, name: str) -> Optional[float]:
        """Get maximum value for a metric"""
        if name not in self.metrics or not self.metrics[name]:
            return None
        return max(self.metrics[name])
    
    def get_summary(self) -> dict:
        """Get summary of all metrics"""
        summary = {}
        for name in self.metrics:
            summary[name] = {
                'count': len(self.metrics[name]),
                'average': self.get_average(name),
                'min': self.get_min(name),
                'max': self.get_max(name)
            }
        return summary
    
    def reset(self):
        """Reset all metrics"""
        self.metrics.clear()


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


def track_performance(metric_name: str):
    """
    Decorator to track function execution time as a metric.
    
    Usage:
        @track_performance('navigation_time')
        def navigate():
            # navigate somewhere
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            performance_monitor.record_metric(metric_name, execution_time)
            logger.debug(f"{metric_name}: {execution_time:.2f}s")
            
            return result
        return wrapper
    return decorator


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing invalid characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    import re
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    return filename


def format_bytes(bytes_value: int) -> str:
    """
    Format bytes into human-readable string.
    
    Args:
        bytes_value: Number of bytes
        
    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"


def validate_url(url: str) -> bool:
    """
    Validate URL format.
    
    Args:
        url: URL to validate
        
    Returns:
        True if valid, False otherwise
    """
    import re
    pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or IP
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return pattern.match(url) is not None
