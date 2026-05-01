"""
Auth routes: register, login, refresh, me.

Endpoints:
  POST /api/auth/register  → 201 UserOut (no tokens)
  POST /api/auth/login     → 200 TokenPair + refresh httpOnly cookie
  POST /api/auth/refresh   → 200 new access_token (reads cookie or body)
  GET  /api/auth/me        → 200 UserOut
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import (
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
    PasswordChangeRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
)

from app.limiter import limiter  # SEC-03 — per-route rate limiting on auth endpoints

router = APIRouter()

_REFRESH_COOKIE_NAME = "refresh_token"


# ---------------------------------------------------------------------------
# POST /api/auth/register
# ---------------------------------------------------------------------------

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")  # SEC-03 — brute-force / account-enumeration protection
async def register(request: Request, payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> UserOut:
    """Register a new user. Returns UserOut (no tokens). Raises 409 on duplicate email."""
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
    return UserOut.model_validate(user)


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenPair)
@limiter.limit("5/minute")  # SEC-03 — credential brute-force protection
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

    # SEC-02: refresh token is delivered via httpOnly cookie only — not in the JSON body.
    return TokenPair(
        access_token=access_token,
        token_type="bearer",
    )


# ---------------------------------------------------------------------------
# POST /api/auth/refresh
# ---------------------------------------------------------------------------

@router.post("/refresh", response_model=AccessTokenResponse)
@limiter.limit("5/minute")  # SEC-03 — token-replay / brute-force protection
async def refresh_token(
    request: Request,
    response: Response,
    refresh_body: Optional[RefreshRequest] = None,
    refresh_cookie: Optional[str] = Cookie(default=None, alias=_REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> AccessTokenResponse:
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
    if incoming_jti and is_jti_revoked(incoming_jti):
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
        revoke_jti(incoming_jti)

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

    return AccessTokenResponse(access_token=new_access, token_type="bearer")


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
# POST /api/auth/logout — clear refresh cookie + revoke its JTI
# ---------------------------------------------------------------------------

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    refresh_cookie: Optional[str] = Cookie(default=None, alias=_REFRESH_COOKIE_NAME),
) -> Response:
    """Revoke the current refresh token (if any) and clear the cookie.
    Idempotent — silently succeeds if no cookie is present or the token is
    already invalid (so a button click never exposes information to attackers)."""
    if refresh_cookie:
        try:
            payload = decode_token(refresh_cookie)
            jti = payload.get("jti")
            if jti:
                revoke_jti(jti)
        except HTTPException:
            pass  # already invalid — idempotent

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
