"""
JWT token creation and verification, plus bcrypt password hashing.

Dependency resolutions (B2):
- python-jose[cryptography]>=3.5,<4  — CVE-2024-33663/33664 fixed, same API.
- passlib[bcrypt]>=1.7,<2 + bcrypt>=4.0,<4.1  — avoids __about__ AttributeError.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

# ---------------------------------------------------------------------------
# SEC-07: Refresh token revocation — in-memory JTI deny set (MVP)
#
# On rotation (/api/auth/refresh) the old JTI is added here so it can never
# be replayed.  The deny set lives for the lifetime of the process; a restart
# clears it.  For production hardening, replace with a Redis / DB-backed store
# with TTL equal to REFRESH_TOKEN_EXPIRE_DAYS (30 days).
# ---------------------------------------------------------------------------
_revoked_jtis: set[str] = set()


def revoke_jti(jti: str) -> None:
    """Add *jti* to the in-memory revocation set."""
    _revoked_jtis.add(jti)


def is_jti_revoked(jti: str) -> bool:
    """Return True if *jti* has been revoked."""
    return jti in _revoked_jtis

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Return bcrypt hash of *password*."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*."""
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------

ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30
ALGORITHM = "HS256"
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def _make_token(user_id: uuid.UUID, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": token_type,
        "jti": str(uuid.uuid4()),  # SEC-07: unique token ID for revocation tracking
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: uuid.UUID) -> str:
    """Return a signed HS256 access JWT valid for 30 minutes."""
    return _make_token(
        user_id,
        TOKEN_TYPE_ACCESS,
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    """Return a signed HS256 refresh JWT valid for 30 days."""
    return _make_token(
        user_id,
        TOKEN_TYPE_REFRESH,
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT; raise HTTPException 401 on failure."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ---------------------------------------------------------------------------
# FastAPI dependency — get_current_user
# ---------------------------------------------------------------------------

# Use auto_error=False so missing/invalid scheme raises HTTP 401 (not 403).
# The 403 from auto_error=True is misleading — missing auth should be 401.
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """
    Decode the Bearer token and return the authenticated user's UUID.
    Raises HTTP 401 if the token is missing, invalid, or the user does not exist.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)

    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user id in token",
        ) from exc

    # Verify user still exists in DB
    from app.models.user import User  # noqa: PLC0415 — avoid circular import at module level

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id


# ---------------------------------------------------------------------------
# WebSocket token validation — US-9
# ---------------------------------------------------------------------------

def validate_ws_token(token: str) -> uuid.UUID:
    """Decode a JWT passed as a query parameter for WebSocket authentication.

    This is a synchronous helper that validates the JWT signature, expiry, and
    type. It does NOT check the DB — the WebSocket route is responsible for any
    DB-level checks (e.g. user still exists).

    Raises:
        WebSocketException (code 4001) if the token is invalid, expired, or
        has the wrong type (e.g. refresh token).

    Args:
        token: Raw JWT string from the ?token= query parameter.

    Returns:
        The authenticated user's UUID.
    """
    from fastapi import WebSocketException  # noqa: PLC0415 — avoid top-level import

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise WebSocketException(code=4001, reason="Invalid token") from exc

    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise WebSocketException(code=4001, reason="Invalid token type")

    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise WebSocketException(code=4001, reason="Token subject missing")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError as exc:
        raise WebSocketException(code=4001, reason="Invalid user id in token") from exc

    return user_id
