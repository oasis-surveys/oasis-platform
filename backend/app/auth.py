"""
SURVEYOR — Simple JWT-based authentication.

Provides a basic security layer that can be toggled via environment variables:
  AUTH_ENABLED=true
  AUTH_USERNAME=admin
  AUTH_PASSWORD=your-password

When AUTH_ENABLED is false (default), all routes are accessible without login.
"""

import time
from datetime import datetime, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger

from app.config import settings

# JWT settings
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_HOURS = 24

_security = HTTPBearer(auto_error=False)


def create_token(username: str) -> str:
    """Create a signed JWT token for the given username."""
    payload = {
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + (_JWT_EXPIRY_HOURS * 3600),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_JWT_ALGORITHM)


def verify_token(token: str) -> dict | None:
    """Verify and decode a JWT token. Returns the payload or None."""
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[_JWT_ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> dict | None:
    """
    FastAPI dependency that enforces authentication when AUTH_ENABLED is true.

    When auth is disabled, returns None (all requests pass).
    When auth is enabled, validates the JWT Bearer token.
    """
    if not settings.auth_enabled:
        return None  # Auth disabled — allow all

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload
