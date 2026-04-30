"""
Pydantic schemas for auth endpoints.
"""
import uuid
from typing import Optional

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
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
