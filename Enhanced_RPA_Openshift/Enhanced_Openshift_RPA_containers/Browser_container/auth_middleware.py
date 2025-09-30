"""
Authentication Middleware
-------------------------
JWT authentication for service-to-service communication.
Reuses the same JWT system as orchestrator/worker.
"""
import os
import jwt
import logging
from typing import Optional
from fastapi import Header, HTTPException, status
from functools import wraps

logger = logging.getLogger(__name__)


class AuthService:
    """Authentication service for JWT validation"""
    
    def __init__(self):
        self.jwt_secret = os.getenv('JWT_SECRET')
        self.jwt_algorithm = os.getenv('JWT_ALGORITHM', 'HS256')
        
        if not self.jwt_secret:
            raise ValueError("JWT_SECRET environment variable is required")
        
        logger.info("AuthService initialized")
    
    def verify_token(self, token: str) -> dict:
        """
        Verify JWT token
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded token payload
            
        Raises:
            HTTPException: If token is invalid
        """
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm]
            )
            
            logger.debug(f"Token verified for subject: {payload.get('sub')}")
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"}
            )
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"}
            )
    
    def extract_token_from_header(self, authorization: Optional[str]) -> str:
        """
        Extract JWT token from Authorization header
        
        Args:
            authorization: Authorization header value
            
        Returns:
            JWT token string
            
        Raises:
            HTTPException: If header is missing or malformed
        """
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization header",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        parts = authorization.split()
        
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header format. Expected 'Bearer <token>'",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        return parts[1]


# Global auth service instance
auth_service = AuthService()


async def verify_service_token(authorization: str = Header(None)) -> dict:
    """
    FastAPI dependency for JWT verification
    
    Usage:
        @app.get("/protected")
        async def protected_route(token: dict = Depends(verify_service_token)):
            # token contains decoded JWT payload
            pass
    
    Args:
        authorization: Authorization header (injected by FastAPI)
        
    Returns:
        Decoded token payload
        
    Raises:
        HTTPException: If authentication fails
    """
    token = auth_service.extract_token_from_header(authorization)
    payload = auth_service.verify_token(token)
    return payload


def require_service(service_name: str):
    """
    Decorator to require specific service authentication
    
    Usage:
        @app.get("/browser-only")
        @require_service("worker")
        async def browser_only_route(token: dict = Depends(verify_service_token)):
            pass
    
    Args:
        service_name: Required service name in token
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, token: dict, **kwargs):
            if token.get('service') != service_name:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied. This endpoint requires '{service_name}' service token"
                )
            return await func(*args, token=token, **kwargs)
        return wrapper
    return decorator


class IPWhitelistMiddleware:
    """
    Middleware for IP-based access control (optional additional security)
    """
    
    def __init__(self, allowed_ips: Optional[list] = None):
        self.allowed_ips = allowed_ips or []
        
        # Add common internal IPs
        self.allowed_ips.extend(['127.0.0.1', '::1', 'localhost'])
        
        logger.info(f"IP whitelist initialized with {len(self.allowed_ips)} entries")
    
    def is_allowed(self, client_ip: str) -> bool:
        """Check if IP is allowed"""
        if not self.allowed_ips:
            return True  # If no whitelist configured, allow all
        
        return client_ip in self.allowed_ips
