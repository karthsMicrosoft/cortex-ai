"""Email notification delivery via Azure Communication Services."""
import asyncio

from app.config import settings
from app.services.notify import NotifyResult

try:
    from azure.communication.email import EmailClient
except ImportError:  # pragma: no cover - exercised by patching EmailClient to None
    EmailClient = None


async def send_email(
    to: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
) -> NotifyResult:
    """Send an email notification, or safely no-op when ACS Email is unavailable."""
    if not settings.acs_email_connection or EmailClient is None:
        return NotifyResult(success=False, channel="none", error="acs not configured")

    message = {
        "content": {
            "subject": subject,
            "html": body_html,
            "plainText": body_text or "",
        },
        "recipients": {
            "to": [{"address": to}],
        },
        "senderAddress": settings.acs_email_sender,
    }

    def _send() -> None:
        client = EmailClient.from_connection_string(settings.acs_email_connection)
        client.begin_send(message).result()

    try:
        await asyncio.to_thread(_send)
    except Exception as e:
        return NotifyResult(success=False, channel="email", error=str(e))

    return NotifyResult(success=True, channel="email")
