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
    """Response for /api/auth/login.

    The refresh token is delivered exclusively via an httpOnly cookie and is
    intentionally omitted from the JSON body to prevent JavaScript access
    (SEC-02 — XSS token-theft mitigation).
    """
    access_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


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
