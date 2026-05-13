"""
JWT token creation and verification, plus bcrypt password hashing.

Dependency resolutions (B2):
- python-jose[cryptography]>=3.5,<4  — CVE-2024-33663/33664 fixed, same API.
- passlib[bcrypt]>=1.7,<2 + bcrypt>=4.0,<4.1  — avoids __about__ AttributeError.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SEC-07 / Round 19: Persistent JWT revocation
#
# A two-tier denylist:
#   * `_revoked_jtis` is an in-memory cache (per-process) consulted first so
#     hot-path requests don't hit the DB.  It is populated on every revoke
#     and on every successful DB-hit lookup.
#   * `revoked_jtis` table (Alembic 011) is the durable store.  Survives
#     Container App restarts so explicit logout and refresh-rotation
#     revocations can't be bypassed by waiting for a process recycle.
#
# Pruning: rows past their `expires_at` are safe to delete because the JWT
# signature/expiry check would already reject those tokens.  Call
# :func:`prune_expired_revoked_jtis` from a scheduled job (future).
# ---------------------------------------------------------------------------
_revoked_jtis: set[str] = set()


async def revoke_jti(db: AsyncSession, jti: str, expires_at: datetime) -> None:
    """Persist *jti* in the revocation table and the in-memory cache.

    Idempotent — a duplicate revoke for the same JTI is a no-op (we tolerate
    the IntegrityError raised by the PRIMARY KEY constraint on a race).

    Args:
        db: Async SQLAlchemy session — typically request-scoped.
        jti: The token's `jti` claim (uuid4 string).
        expires_at: The token's `exp` claim (timezone-aware datetime).  Used
            by the prune job to GC entries whose underlying JWT can no
            longer be presented.
    """
    _revoked_jtis.add(jti)

    from app.models.revoked_jti import RevokedJTI  # noqa: PLC0415

    # Cheap existence check first — avoids needlessly raising IntegrityError
    # in the common (idempotent) case.
    existing = await db.get(RevokedJTI, jti)
    if existing is not None:
        return

    db.add(RevokedJTI(jti=jti, expires_at=expires_at))
    try:
        await db.flush()
    except IntegrityError:
        # Concurrent revoke for the same JTI from another worker — fine,
        # the cache already reflects the revocation.
        await db.rollback()


async def is_jti_revoked(db: AsyncSession, jti: str) -> bool:
    """Return True if *jti* has been revoked.

    Fast-path: the in-memory `_revoked_jtis` cache is consulted first.  Only
    on a cache miss do we hit the DB; a positive DB result is then promoted
    into the cache so subsequent requests in this process avoid the round
    trip.
    """
    if jti in _revoked_jtis:
        return True

    from app.models.revoked_jti import RevokedJTI  # noqa: PLC0415

    result = await db.execute(select(RevokedJTI).where(RevokedJTI.jti == jti))
    row = result.scalar_one_or_none()
    if row is not None:
        _revoked_jtis.add(jti)
        return True
    return False


async def prune_expired_revoked_jtis(db: AsyncSession) -> int:
    """Delete revoked-JTI rows whose `expires_at` has already passed.

    Returns the number of rows deleted. Safe to run repeatedly — the JWT
    signature+expiry check already rejects expired tokens, so removing the
    revocation row does not re-enable replay.
    """
    from app.models.revoked_jti import RevokedJTI  # noqa: PLC0415

    now = datetime.now(tz=timezone.utc)
    result = await db.execute(
        delete(RevokedJTI).where(RevokedJTI.expires_at < now)
    )
    await db.flush()
    return result.rowcount or 0

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


def _make_token(
    user_id: uuid.UUID,
    token_type: str,
    expires_delta: timedelta,
    scope: str | None = None,
) -> str:
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": token_type,
        "jti": str(uuid.uuid4()),  # SEC-07: unique token ID for revocation tracking
        "iat": now,
        "exp": now + expires_delta,
    }
    # PR 5.5: only include the scope claim when explicitly set, so existing
    # full-session tokens stay byte-identical to before.
    if scope is not None:
        payload["scope"] = scope
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(
    user_id: uuid.UUID,
    *,
    scope: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Return a signed HS256 access JWT.

    By default the token is valid for ``ACCESS_TOKEN_EXPIRE_MINUTES`` (30 min)
    and carries no scope claim — i.e. it is a full-session token.

    PR 5.5: pass ``scope="clip"`` (and a custom ``expires_delta``) to mint a
    limited-capability token for the browser extension. Routes guarded by
    :func:`require_scope` will accept it; routes guarded by the default
    :func:`get_current_user` will reject it with 403.
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return _make_token(
        user_id,
        TOKEN_TYPE_ACCESS,
        expires_delta,
        scope=scope,
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


def verify_scope(token_payload: dict, required_scope: str | None) -> None:
    """Raise HTTP 403 if *token_payload*'s scope does not satisfy *required_scope*.

    Semantics (PR 5.5):
      * A token with no ``scope`` claim is a full-session token and may call
        ANY endpoint, regardless of ``required_scope``.
      * A token with ``scope == required_scope`` passes.
      * A token with ``scope`` set to anything else is rejected with 403.
      * ``required_scope=None`` means "no scope required" — any token passes.
    """
    token_scope = token_payload.get("scope")
    if token_scope is None:
        return  # full session — always allowed
    if required_scope is None:
        return  # caller doesn't care about scope
    if token_scope != required_scope:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Token scope '{token_scope}' is not permitted on this endpoint "
                f"(required: '{required_scope}')"
            ),
        )


async def _resolve_user_from_credentials(
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
    allowed_scopes: set[str | None] | None,
) -> uuid.UUID:
    """Shared decode + DB-existence check used by both ``get_current_user``
    and ``require_scope``.

    *allowed_scopes* is a set whose members may include ``None`` (full
    session) and/or string scope names (e.g. ``"clip"``). When ``None`` is
    passed for the whole argument, only no-scope tokens are accepted (default
    ``get_current_user`` behaviour — protects sensitive routes).
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

    # SEC-07 / Round 19: reject revoked access tokens (explicit logout, etc.).
    access_jti = payload.get("jti")
    if access_jti and await is_jti_revoked(db, access_jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # PR 5.5: scope check. Default get_current_user ⇒ allowed_scopes={None}.
    effective_allowed: set[str | None] = (
        {None} if allowed_scopes is None else allowed_scopes
    )
    token_scope = payload.get("scope")
    if token_scope not in effective_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Token scope '{token_scope}' is not permitted on this endpoint"
            ),
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

    # Round 20 / PR alpha — enrich the current trace span with a hashed user
    # id so authenticated requests are correlatable in App Insights without
    # leaking raw UUIDs. Best-effort; swallows all exceptions.
    try:
        from app.observability.tracing import add_user_id_hash_to_span  # noqa: PLC0415

        add_user_id_hash_to_span(user_id)
    except Exception:  # noqa: BLE001
        pass

    return user_id


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """
    Decode the Bearer token and return the authenticated user's UUID.

    Raises HTTP 401 if the token is missing, invalid, or the user does not
    exist; raises HTTP 403 (PR 5.5) if the token carries a ``scope`` claim
    (i.e. it is a limited-capability extension/clip token, which must not be
    accepted on full-session-only endpoints).
    """
    return await _resolve_user_from_credentials(credentials, db, allowed_scopes=None)


def require_scope(allowed_scopes: set[str | None]):
    """Build a FastAPI dependency that accepts tokens whose ``scope`` claim
    is in *allowed_scopes* (use ``None`` in the set to also accept full-session
    tokens).

    Example::

        @router.post("/url")
        async def import_url(
            user_id: uuid.UUID = Depends(require_scope({None, "clip"})),
            ...
        ): ...
    """

    async def _dep(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
        db: AsyncSession = Depends(get_db),
    ) -> uuid.UUID:
        return await _resolve_user_from_credentials(
            credentials, db, allowed_scopes=allowed_scopes
        )

    return _dep


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
