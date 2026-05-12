"""
Limited-scope clip token endpoint — Phase 5 / PR 5.5.

POST /api/auth/clip-token mints a 30-day JWT with ``scope: "clip"`` for use
by the Chrome MV3 extension. The user authenticates with their full session
cookie/token (e.g. on the Settings page in the web app), copies the returned
token, and pastes it into the extension popup, which stores it in
``chrome.storage.local``.

Security rationale: extension storage is reachable from any compromised
content-script context, so we never put the full session JWT there. A
clip-scoped token can ONLY hit ``POST /api/import/url`` and
``POST /api/notes`` — every other route uses ``get_current_user`` which
rejects scoped tokens with 403 (see ``app/auth/jwt.py``).
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from app.auth.jwt import create_access_token, get_current_user
from app.limiter import limiter

router = APIRouter()

CLIP_TOKEN_SCOPE = "clip"
CLIP_TOKEN_EXPIRE_DAYS = 30
CLIP_TOKEN_EXPIRE_SECONDS = CLIP_TOKEN_EXPIRE_DAYS * 24 * 3600


class ClipTokenResponse(BaseModel):
    clip_token: str
    expires_in: int
    scope: str


@router.post(
    "/clip-token",
    response_model=ClipTokenResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("5/hour")
async def create_clip_token(
    request: Request,
    response: Response,
    current_user_id: uuid.UUID = Depends(get_current_user),
) -> ClipTokenResponse:
    """Mint a 30-day clip-scoped JWT for the calling user.

    Per-user (per-IP under slowapi MVP) rate limit: 5/hour. Rotating tokens
    is a deliberate, low-frequency action.
    """
    token = create_access_token(
        current_user_id,
        scope=CLIP_TOKEN_SCOPE,
        expires_delta=timedelta(days=CLIP_TOKEN_EXPIRE_DAYS),
    )
    return ClipTokenResponse(
        clip_token=token,
        expires_in=CLIP_TOKEN_EXPIRE_SECONDS,
        scope=CLIP_TOKEN_SCOPE,
    )
