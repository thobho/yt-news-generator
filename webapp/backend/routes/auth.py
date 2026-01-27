"""
Authentication routes - login, logout, and session check.
"""

from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel

from ..services import auth as auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Cookie settings
COOKIE_NAME = "session"
COOKIE_MAX_AGE = 60 * 60 * 24  # 24 hours in seconds


class LoginRequest(BaseModel):
    password: str


class AuthStatus(BaseModel):
    authenticated: bool
    auth_enabled: bool


@router.get("/status", response_model=AuthStatus)
async def get_auth_status(request: Request):
    """Check if user is authenticated."""
    auth_enabled = auth_service.is_auth_enabled()

    if not auth_enabled:
        # Auth disabled, everyone is authenticated
        return AuthStatus(authenticated=True, auth_enabled=False)

    token = request.cookies.get(COOKIE_NAME)
    authenticated = auth_service.validate_session(token)

    return AuthStatus(authenticated=authenticated, auth_enabled=True)


@router.post("/login")
async def login(request: LoginRequest, response: Response):
    """Login with password."""
    if not auth_service.is_auth_enabled():
        return {"message": "Authentication is disabled"}

    if not auth_service.verify_password(request.password):
        raise HTTPException(
            status_code=401,
            detail="Invalid password"
        )

    # Create session
    token = auth_service.create_session()

    # Set secure cookie
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,  # Prevent JavaScript access
        samesite="strict",  # CSRF protection
        secure=False,  # Set to True in production with HTTPS
    )

    return {"message": "Login successful"}


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Logout and invalidate session."""
    token = request.cookies.get(COOKIE_NAME)
    auth_service.invalidate_session(token)

    # Delete cookie
    response.delete_cookie(key=COOKIE_NAME)

    return {"message": "Logout successful"}
