"""
SURVEYOR — Authentication endpoints.

POST /api/auth/login   — Verify credentials, return JWT
GET  /api/auth/me      — Return current user info (or auth status)
"""

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends, status

from app.config import settings
from app.auth import create_token, require_auth


router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    expires_in: int = 86400  # 24 hours


class AuthStatusResponse(BaseModel):
    auth_enabled: bool
    authenticated: bool
    username: str | None = None


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest):
    """
    Authenticate with username/password and receive a JWT token.

    When AUTH_ENABLED is false, this endpoint still works but isn't required.
    """
    if not settings.auth_enabled:
        # Auth disabled — issue token for any credentials (convenience)
        token = create_token(data.username)
        return LoginResponse(token=token, username=data.username)

    if not settings.auth_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AUTH_ENABLED is true but AUTH_PASSWORD is not set in .env",
        )

    if data.username != settings.auth_username or data.password != settings.auth_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_token(data.username)
    return LoginResponse(token=token, username=data.username)


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(user=Depends(require_auth)):
    """
    Check whether authentication is enabled and if the current request
    is authenticated.
    """
    return AuthStatusResponse(
        auth_enabled=settings.auth_enabled,
        authenticated=user is not None or not settings.auth_enabled,
        username=user.get("sub") if user else None,
    )
