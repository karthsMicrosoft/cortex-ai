import asyncio
import json

from app.config import settings
from app.services.notify import NotifyResult

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover - exercised via monkeypatch in tests
    WebPushException = None
    webpush = None


async def send_push(subscription, payload: dict) -> NotifyResult:
    if settings.vapid_private_key is None or webpush is None or WebPushException is None:
        return NotifyResult(
            success=False,
            channel="none",
            error="vapid not configured",
        )

    subscription_info = {
        "endpoint": subscription.endpoint,
        "keys": {
            "p256dh": subscription.p256dh,
            "auth": subscription.auth,
        },
    }

    try:
        await asyncio.to_thread(
            webpush,
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
        )
    except WebPushException as e:
        status_code = getattr(getattr(e, "response", None), "status_code", None)
        if status_code == 410:
            return NotifyResult(
                success=False,
                channel="webpush",
                error="gone",
                expired=True,
            )
        return NotifyResult(success=False, channel="webpush", error=str(e))

    return NotifyResult(success=True, channel="webpush")
