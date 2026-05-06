"""
Pydantic schemas for auth endpoints.
"""
import uuid
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    # SEC-04: min 8 chars enforced at schema level so weak passwords are rejected
    # with a 422 before reaching the hashing layer.
    password: str = Field(..., min_length=8, max_length=128)
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    """Response for /api/auth/login and /api/auth/refresh.

    SEC-02 NOTE: refresh_token is also delivered via httpOnly cookie (defense
    in depth for browsers that honour SameSite=None+Secure).  The JSON body
    field is added for Round-7 localStorage fallback because Edge's "Balanced"
    tracking-prevention blocks third-party cookies on the Free-tier SWA →
    Container Apps cross-origin path.  Trade-off accepted: localStorage is
    XSS-readable; acceptable for single-user MVP without CSP.  Migrate to
    first-party cookies (custom domain / SWA Standard) as P1.
    """
    access_token: str
    token_type: str = "bearer"
    refresh_token: str = ""


class AccessTokenResponse(BaseModel):
    """Kept for backward-compat imports; /refresh now returns TokenPair."""
    access_token: str
    token_type: str = "bearer"
    refresh_token: str = ""


class RegisterResponse(BaseModel):
    """Response for /api/auth/register — flat UserOut fields + tokens.

    Round-7: access_token + refresh_token added so the frontend can authenticate
    without a separate /login call even when cookies are blocked.
    Fields are deliberately kept flat (not nested under 'user') so existing
    tests checking for top-level 'id'/'email'/'display_name' continue to work.
    """
    # UserOut-equivalent fields (flat)
    id: uuid.UUID
    email: str
    display_name: Optional[str] = None
    shadow_reader_enabled: bool = True
    shadow_reader_disabled_categories: list[str] = []
    # Tokens (Round-7 addition)
    access_token: str
    token_type: str = "bearer"
    refresh_token: str = ""

    model_config = {"from_attributes": True}


class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: Optional[str] = None
    # Phase 2 — Shadow Reader settings (exposed so the frontend can pre-populate settings UI)
    shadow_reader_enabled: bool = True
    shadow_reader_disabled_categories: list[str] = []

    model_config = {"from_attributes": True}


class ProfileUpdateRequest(BaseModel):
    """Body for PUT /api/auth/me — partial update of display_name."""
    display_name: Optional[str] = Field(default=None, max_length=100)


class PasswordChangeRequest(BaseModel):
    """Body for POST /api/auth/password — current_password verifies the
    caller's identity even if their access token is still valid; new_password
    follows the same min_length=8 / max_length=128 SEC-04 rule as register."""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)
