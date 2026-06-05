"""
Pydantic schemas for Web Push subscription endpoints.
"""
import uuid

from pydantic import BaseModel


class PushKeys(BaseModel):
    auth: str
    p256dh: str


class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: PushKeys
    user_agent: str | None = None


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


class PushSubscribeResponse(BaseModel):
    id: uuid.UUID
    created: bool


class VapidPublicKeyResponse(BaseModel):
    public_key: str | None
