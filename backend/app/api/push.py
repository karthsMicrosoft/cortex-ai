"""
Web Push subscription endpoints.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.config import settings
from app.database import get_db
from app.models.push_subscription import PushSubscription
from app.schemas.push import (
    PushSubscribeRequest,
    PushSubscribeResponse,
    PushUnsubscribeRequest,
    VapidPublicKeyResponse,
)

router = APIRouter()


@router.post(
    "/subscribe",
    response_model=PushSubscribeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def subscribe(
    payload: PushSubscribeRequest,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PushSubscribeResponse:
    """Create or refresh the caller's browser push subscription."""
    dialect_name = db.bind.dialect.name if db.bind is not None else ""
    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(PushSubscription).values(
            user_id=current_user_id,
            endpoint=payload.endpoint,
            auth=payload.keys.auth,
            p256dh=payload.keys.p256dh,
            user_agent=payload.user_agent,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[PushSubscription.user_id, PushSubscription.endpoint],
            set_={
                "auth": payload.keys.auth,
                "p256dh": payload.keys.p256dh,
                "user_agent": payload.user_agent,
                "last_seen_at": func.now(),
            },
        ).returning(
            PushSubscription.id,
            literal_column("xmax = 0").label("created"),
        )
        result = await db.execute(stmt)
        row = result.one()
        await db.commit()
        return PushSubscribeResponse(id=row.id, created=bool(row.created))

    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == current_user_id,
            PushSubscription.endpoint == payload.endpoint,
        )
    )
    subscription = result.scalar_one_or_none()
    if subscription is not None:
        subscription.auth = payload.keys.auth
        subscription.p256dh = payload.keys.p256dh
        subscription.user_agent = payload.user_agent
        subscription.last_seen_at = datetime.now(tz=timezone.utc)
        await db.commit()
        await db.refresh(subscription)
        return PushSubscribeResponse(id=subscription.id, created=False)

    subscription = PushSubscription(
        user_id=current_user_id,
        endpoint=payload.endpoint,
        auth=payload.keys.auth,
        p256dh=payload.keys.p256dh,
        user_agent=payload.user_agent,
        last_seen_at=datetime.now(tz=timezone.utc),
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)
    return PushSubscribeResponse(id=subscription.id, created=True)


@router.delete("/subscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(
    payload: PushUnsubscribeRequest,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete the caller's subscription for the given endpoint."""
    result = await db.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == current_user_id,
            PushSubscription.endpoint == payload.endpoint,
        )
    )
    if (result.rowcount or 0) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Push subscription not found",
        )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/vapid-public-key", response_model=VapidPublicKeyResponse)
async def get_vapid_public_key() -> VapidPublicKeyResponse:
    """Return the VAPID public key, or null when Web Push is not configured."""
    return VapidPublicKeyResponse(public_key=settings.vapid_public_key)
