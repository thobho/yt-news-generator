"""
Authentication service - simple session-based auth with password.
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

# Session storage (in-memory, cleared on restart)
_sessions: dict[str, datetime] = {}

# Session duration
SESSION_DURATION_HOURS = 24


def get_password() -> str:
    """Get the authentication password from environment."""
    password = os.environ.get("AUTH_PASSWORD", "").strip()
    if not password:
        raise RuntimeError(
            "AUTH_PASSWORD environment variable is not set. "
            "Set it to enable authentication."
        )
    return password


def is_auth_enabled() -> bool:
    """Check if authentication is enabled (password is set)."""
    password = os.environ.get("AUTH_PASSWORD", "").strip()
    return bool(password)


def verify_password(password: str) -> bool:
    """Verify the provided password against the configured one."""
    try:
        correct_password = get_password()
        # Use constant-time comparison to prevent timing attacks
        return secrets.compare_digest(password, correct_password)
    except RuntimeError:
        return False


def create_session() -> str:
    """Create a new session and return the session token."""
    # Generate secure random token
    token = secrets.token_urlsafe(32)

    # Store session with expiration time
    expiration = datetime.utcnow() + timedelta(hours=SESSION_DURATION_HOURS)
    _sessions[token] = expiration

    # Clean up expired sessions periodically
    _cleanup_expired_sessions()

    return token


def validate_session(token: Optional[str]) -> bool:
    """Validate a session token."""
    if not token:
        return False

    expiration = _sessions.get(token)
    if not expiration:
        return False

    if datetime.utcnow() > expiration:
        # Session expired, remove it
        _sessions.pop(token, None)
        return False

    return True


def invalidate_session(token: Optional[str]) -> None:
    """Invalidate (logout) a session."""
    if token:
        _sessions.pop(token, None)


def _cleanup_expired_sessions() -> None:
    """Remove expired sessions from storage."""
    now = datetime.utcnow()
    expired = [token for token, exp in _sessions.items() if now > exp]
    for token in expired:
        _sessions.pop(token, None)
