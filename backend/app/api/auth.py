"""
Auth routes: register, login, refresh, me.

Endpoints:
  POST /api/auth/register  → 201 UserOut (no tokens)
  POST /api/auth/login     → 200 TokenPair + refresh httpOnly cookie
  POST /api/auth/refresh   → 200 new access_token (reads cookie or body)
  GET  /api/auth/me        → 200 UserOut
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import (
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
    _bearer_scheme,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    is_jti_revoked,
    revoke_jti,
    verify_password,
)
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    LogoutRequest,
    PasswordChangeRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenPair,
    UserOut,
)

from app.limiter import limiter  # SEC-03 — per-route rate limiting on auth endpoints

logger = logging.getLogger(__name__)

router = APIRouter()

_REFRESH_COOKIE_NAME = "refresh_token"


# ---------------------------------------------------------------------------
# POST /api/auth/register
# ---------------------------------------------------------------------------

@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")  # SEC-03 — brute-force / account-enumeration protection
async def register(request: Request, payload: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)) -> RegisterResponse:
    """Register a new user. Returns RegisterResponse (user + tokens).
    Also plants a refresh httpOnly cookie (defense-in-depth).
    Raises 409 on duplicate email.
    Round-7: access_token + refresh_token now included in the JSON body so
    the frontend can authenticate without a separate /login call even when
    Edge tracking-prevention blocks the cookie.
    """
    # Check for existing user
    result = await db.execute(select(User).where(User.email == payload.email))
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    # Plant the refresh cookie (defense-in-depth for browsers that allow
    # third-party cookies).
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="none",  # SameSite=None+Secure required for cross-origin SWA→backend cookie.
        max_age=30 * 24 * 3600,  # 30 days
        path="/api/auth",
    )

    return RegisterResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        shadow_reader_enabled=user.shadow_reader_enabled,
        shadow_reader_disabled_categories=user.shadow_reader_disabled_categories,
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,
    )


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenPair)
# SEC-03 with bumped limit: 5/min was tripping legitimate flows where the user
# refreshes between tabs or e2e suites perform several login attempts in
# sequence. 30/min is comfortable for users; bcrypt's CPU cost (~100ms per
# verify) still bounds attacker throughput even at this higher rate.
@limiter.limit("30/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """
    Authenticate user. Returns TokenPair in body.
    Also sets refresh token as httpOnly+secure+sameSite=lax cookie.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    # Set refresh token as httpOnly cookie
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="none",  # SameSite=None+Secure required for cross-origin SWA→backend refresh; otherwise the browser refuses to send the cookie on fetch from gentle-river-*.azurestaticapps.net to cortexks-*.azurecontainerapps.io and refresh always 401s.
        max_age=30 * 24 * 3600,  # 30 days
        path="/api/auth",
    )

    # Round-7: refresh_token now also in the JSON body for localStorage fallback.
    # Cookie path preserved as defense-in-depth for browsers that accept it.
    return TokenPair(
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,
    )


# ---------------------------------------------------------------------------
# POST /api/auth/refresh
# ---------------------------------------------------------------------------

@router.post("/refresh", response_model=TokenPair)
# SEC-03: rate limit, but high enough to allow normal usage. Bumped 5→60/min
# on 2026-05-01 because the original 5/min broke legitimate flows: SessionGate
# calls /refresh on every page reload, opening 2–3 tabs hits the limit, and
# Playwright + browser tests collide. JTI rotation already stops replay attacks
# even at higher rates, and a 256-bit JTI cannot be brute-forced at 60/min.
@limiter.limit("60/minute")
async def refresh_token(
    request: Request,
    response: Response,
    refresh_body: Optional[RefreshRequest] = None,
    refresh_cookie: Optional[str] = Cookie(default=None, alias=_REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """
    Rotate refresh token. Accepts token from:
    1. JSON body field `refresh_token`
    2. httpOnly cookie `refresh_token` (set by /login)
    Returns new access_token.
    """
    token_str: Optional[str] = None
    if refresh_body and refresh_body.refresh_token:
        token_str = refresh_body.refresh_token
    elif refresh_cookie:
        token_str = refresh_cookie

    if not token_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )

    payload = decode_token(token_str)  # raises 401 if invalid/expired
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — expected refresh token",
        )

    # SEC-07: Reject revoked tokens (previous rotation or explicit logout).
    incoming_jti: Optional[str] = payload.get("jti")
    if incoming_jti and await is_jti_revoked(db, incoming_jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
        )

    user_id_str = payload.get("sub")
    try:
        user_id = uuid.UUID(user_id_str)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user id in token",
        ) from exc

    # Verify user exists
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # SEC-07: Revoke the old JTI before issuing the new token (rotation).
    if incoming_jti:
        # The old refresh token's `exp` is what bounds the revocation row's
        # useful lifetime — past that point it's safe to prune.
        incoming_exp_ts = payload.get("exp")
        incoming_exp = (
            datetime.fromtimestamp(incoming_exp_ts, tz=timezone.utc)
            if isinstance(incoming_exp_ts, (int, float))
            else datetime.now(tz=timezone.utc)
        )
        await revoke_jti(db, incoming_jti, incoming_exp)

    new_access = create_access_token(user_id)
    new_refresh = create_refresh_token(user_id)

    # Rotate refresh cookie
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=new_refresh,
        httponly=True,
        secure=True,
        samesite="none",  # SameSite=None+Secure required for cross-origin SWA→backend refresh; otherwise the browser refuses to send the cookie on fetch from gentle-river-*.azurestaticapps.net to cortexks-*.azurecontainerapps.io and refresh always 401s.
        max_age=30 * 24 * 3600,
        path="/api/auth",
    )

    # Round-7: new_refresh also returned in JSON body for localStorage fallback.
    return TokenPair(access_token=new_access, token_type="bearer", refresh_token=new_refresh)


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserOut)
async def get_me(
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Return the currently authenticated user's profile."""
    result = await db.execute(select(User).where(User.id == current_user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserOut.model_validate(user)


# ---------------------------------------------------------------------------
# PUT /api/auth/me — update profile (currently: display_name only)
# ---------------------------------------------------------------------------

@router.put("/me", response_model=UserOut)
async def update_me(
    payload: ProfileUpdateRequest,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Partial profile update. Email is intentionally not editable here —
    changing the auth identity should go through a separate confirm-email flow.
    """
    result = await db.execute(select(User).where(User.id == current_user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.display_name is not None:
        user.display_name = payload.display_name

    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


# ---------------------------------------------------------------------------
# POST /api/auth/password — change password
# ---------------------------------------------------------------------------

@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")  # SEC-03 — slow brute-force on current_password
async def change_password(
    request: Request,
    payload: PasswordChangeRequest,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Change the authenticated user's password. Requires the current
    password as a defense-in-depth check (so a stolen access token alone
    cannot rotate the password without also knowing the existing one)."""
    result = await db.execute(select(User).where(User.id == current_user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    user.password_hash = hash_password(payload.new_password)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# POST /api/auth/logout — revoke access + refresh JTIs and clear the cookie
# ---------------------------------------------------------------------------

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    body: Optional[LogoutRequest] = None,
    refresh_cookie: Optional[str] = Cookie(default=None, alias=_REFRESH_COOKIE_NAME),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Round 19 / SEC-07 follow-up.

    Behaviour:
      * Requires a valid, NON-REVOKED access token in the ``Authorization``
        header (401 otherwise).  We re-decode it here to recover the JTI/exp
        rather than going through ``get_current_user``, so we don't need to
        touch the users table.
      * Revokes the access-token JTI (so a stolen token can't be replayed,
        and a second logout call with the same token returns 401).
      * Revokes the refresh-token JTI if a refresh token is supplied via
        request body OR the ``refresh_token`` cookie.  Malformed refresh
        tokens are silently skipped — logout from the user's perspective
        must always succeed (idempotent on missing/bad refresh).
      * Clears the ``refresh_token`` cookie.
      * Returns 204 No Content.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_payload = decode_token(credentials.credentials)  # 401 on bad sig/expiry
    if access_payload.get("type") != TOKEN_TYPE_ACCESS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_jti = access_payload.get("jti")
    # Reject already-revoked access tokens — calling logout twice with the
    # same token must 401 the second time (otherwise an attacker who's
    # already triggered logout can keep silently confirming the JTI is dead).
    if access_jti and await is_jti_revoked(db, access_jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if access_jti:
        access_exp_ts = access_payload.get("exp")
        access_exp = (
            datetime.fromtimestamp(access_exp_ts, tz=timezone.utc)
            if isinstance(access_exp_ts, (int, float))
            else datetime.now(tz=timezone.utc)
        )
        await revoke_jti(db, access_jti, access_exp)

    # Refresh token: prefer the body field (Round-7 localStorage path), fall
    # back to the httpOnly cookie.  Both delivery paths are best-effort —
    # a logout button click must never expose information to attackers.
    refresh_token_str: Optional[str] = None
    if body and body.refresh_token:
        refresh_token_str = body.refresh_token
    elif refresh_cookie:
        refresh_token_str = refresh_cookie

    if refresh_token_str:
        try:
            refresh_payload = decode_token(refresh_token_str)
        except HTTPException:
            logger.info("logout: ignoring malformed refresh token (idempotent)")
            refresh_payload = None
        if refresh_payload is not None and refresh_payload.get("type") == TOKEN_TYPE_REFRESH:
            r_jti = refresh_payload.get("jti")
            if r_jti:
                r_exp_ts = refresh_payload.get("exp")
                r_exp = (
                    datetime.fromtimestamp(r_exp_ts, tz=timezone.utc)
                    if isinstance(r_exp_ts, (int, float))
                    else datetime.now(tz=timezone.utc)
                )
                await revoke_jti(db, r_jti, r_exp)

    response.delete_cookie(
        key=_REFRESH_COOKIE_NAME,
        path="/api/auth",
        secure=True,
        samesite="none",
        httponly=True,
    )
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers=dict(response.headers),
    )
