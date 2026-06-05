"""Reminder dispatcher (Round 35).

Finds notes whose due_at <= now AND reminder_sent_at IS NULL AND done_at IS NULL,
claims them race-safely (UPDATE ... RETURNING), then dispatches a notification
via webpush first, falling back to email. Recurring notes get their due_at
advanced after firing so the next instance is queued automatically.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services.notify import NotifyResult
from app.services.notify.email import send_email
from app.services.notify.webpush import send_push

logger = logging.getLogger(__name__)

# How long after due_at we still consider firing (in case the job missed a tick).
GRACE_WINDOW = timedelta(hours=24)

# Batch size per dispatcher run. Tune later if needed.
MAX_PER_RUN = 100


async def find_due_reminders(db: AsyncSession, *, now: datetime | None = None) -> list[Note]:
    """Return notes that should fire a reminder now.

    Filter: due_at IS NOT NULL AND due_at <= now AND reminder_sent_at IS NULL
    AND done_at IS NULL AND due_at > now - GRACE_WINDOW (drop ancient overdue
    so the job doesn't spam after a long outage).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - GRACE_WINDOW
    stmt = (
        select(Note)
        .where(Note.due_at.is_not(None))
        .where(Note.due_at <= now)
        .where(Note.due_at > cutoff)
        .where(Note.reminder_sent_at.is_(None))
        .where(Note.done_at.is_(None))
        .order_by(Note.due_at.asc())
        .limit(MAX_PER_RUN)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def claim_reminders(
    db: AsyncSession,
    note_ids: list[uuid.UUID],
    *,
    now: datetime | None = None,
) -> set[uuid.UUID]:
    """Atomically mark the given notes as reminder_sent_at = now.

    Returns the set of IDs that were actually claimed (other rows may have
    been claimed by a parallel dispatcher). Idempotent — re-running with
    already-claimed IDs returns an empty set.
    """
    if not note_ids:
        return set()
    if now is None:
        now = datetime.now(timezone.utc)
    stmt = (
        update(Note)
        .where(Note.id.in_(note_ids))
        .where(Note.reminder_sent_at.is_(None))
        .where(Note.done_at.is_(None))
        .values(reminder_sent_at=now)
        .returning(Note.id)
    )
    result = await db.execute(stmt)
    claimed = {row[0] for row in result.fetchall()}
    await db.commit()
    return claimed


def _build_payload(note: Note) -> dict:
    title = (note.title or "Reminder").strip()[:80] or "Reminder"
    body = (note.content or "").strip().splitlines()[0][:200] if note.content else ""
    return {
        "title": f"⏰ {title}",
        "body": body,
        "url": f"/notes/{note.id}",
        "tag": f"reminder-{note.id}",
    }


async def _send_for_note(db: AsyncSession, note: Note) -> NotifyResult:
    """Try webpush for each subscription; on no success and no active push,
    fall back to email.

    Returns the LAST attempted NotifyResult so callers can log it.
    """
    payload = _build_payload(note)

    subs_stmt = select(PushSubscription).where(PushSubscription.user_id == note.user_id)
    subs = list((await db.execute(subs_stmt)).scalars().all())

    last_result: NotifyResult | None = None
    any_success = False
    expired_subs: list[uuid.UUID] = []

    for sub in subs:
        result = await send_push(sub, payload)
        last_result = result
        if result.success:
            any_success = True
        if result.expired:
            expired_subs.append(sub.id)

    if expired_subs:
        await db.execute(delete(PushSubscription).where(PushSubscription.id.in_(expired_subs)))
        await db.commit()
        logger.info(
            "reminders.expired_subs_deleted note_id=%s count=%d",
            note.id,
            len(expired_subs),
        )

    if any_success:
        return NotifyResult(success=True, channel="webpush")

    user_stmt = select(User).where(User.id == note.user_id)
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if user is None or not user.email:
        return last_result or NotifyResult(success=False, channel="none", error="no recipient")

    subject = payload["title"]
    body_text = f"{payload['body']}\n\nView: {payload['url']}"
    body_html = f"<p>{payload['body']}</p><p><a href='{payload['url']}'>View note</a></p>"
    return await send_email(user.email, subject, body_html, body_text)


def _advance_due(due_at: datetime, recurring: str) -> datetime:
    if recurring == "daily":
        return due_at + timedelta(days=1)
    if recurring == "weekly":
        return due_at + timedelta(weeks=1)
    if recurring == "monthly":
        try:
            from dateutil.relativedelta import relativedelta  # type: ignore[import-not-found]

            return due_at + relativedelta(months=1)
        except ImportError:
            return due_at + timedelta(days=30)
    return due_at


async def rollover_recurring(
    db: AsyncSession,
    note: Note,
    *,
    now: datetime | None = None,
) -> None:
    """Advance due_at on a recurring note and clear reminder_sent_at + done_at.

    Idempotent: if note.recurring is None, no-op.
    """
    if not note.recurring:
        return
    if now is None:
        now = datetime.now(timezone.utc)
    base = note.due_at or now
    note.due_at = _advance_due(base, note.recurring)
    note.reminder_sent_at = None
    note.done_at = None
    await db.commit()


async def dispatch(db: AsyncSession, *, now: datetime | None = None) -> dict:
    """Single-run dispatch pass. Returns counters for the operator."""
    if now is None:
        now = datetime.now(timezone.utc)
    due = await find_due_reminders(db, now=now)
    note_ids = [n.id for n in due]
    claimed = await claim_reminders(db, note_ids, now=now)
    due = [n for n in due if n.id in claimed]

    sent_push = sent_email = failed = rolled = 0
    for note in due:
        result = await _send_for_note(db, note)
        if result.success and result.channel == "webpush":
            sent_push += 1
        elif result.success and result.channel == "email":
            sent_email += 1
        else:
            failed += 1
            logger.warning(
                "reminders.dispatch_failed note_id=%s error=%s",
                note.id,
                result.error,
            )
        if note.recurring:
            await rollover_recurring(db, note, now=now)
            rolled += 1

    return {
        "found": len(note_ids),
        "claimed": len(claimed),
        "sent_push": sent_push,
        "sent_email": sent_email,
        "failed": failed,
        "rolled": rolled,
    }
