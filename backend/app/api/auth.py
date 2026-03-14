"""
OASIS — Authentication endpoints.

POST /api/auth/login   — Verify credentials, return JWT
GET  /api/auth/status  — Return auth configuration and current auth state
"""

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings
from app.auth import create_token, verify_token, require_auth


router = APIRouter(prefix="/auth", tags=["Authentication"])

_security = HTTPBearer(auto_error=False)


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
async def auth_status(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
):
    """
    Public endpoint — no auth required.

    Returns whether auth is enabled and whether the caller's token (if any) is valid.
    This lets the frontend decide whether to show the login page.
    """
    if not settings.auth_enabled:
        return AuthStatusResponse(
            auth_enabled=False,
            authenticated=True,
            username=None,
        )

    # Auth is enabled — check if a valid token was provided
    if credentials:
        payload = verify_token(credentials.credentials)
        if payload:
            return AuthStatusResponse(
                auth_enabled=True,
                authenticated=True,
                username=payload.get("sub"),
            )

    # No token or invalid token
    return AuthStatusResponse(
        auth_enabled=True,
        authenticated=False,
        username=None,
    )
