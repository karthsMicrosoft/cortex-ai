import builtins
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services.notify import NotifyResult
from app.services.reminders import (
    GRACE_WINDOW,
    _advance_due,
    _send_for_note,
    claim_reminders,
    dispatch,
    find_due_reminders,
    rollover_recurring,
)


def _same_datetime(actual: datetime | None, expected: datetime) -> bool:
    return actual == expected or actual == expected.replace(tzinfo=None)


async def _clear_tables(db: AsyncSession) -> None:
    await db.execute(delete(PushSubscription))
    await db.execute(delete(Note))
    await db.execute(delete(User))
    await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def clean_reminder_tables(db_session: AsyncSession):
    await _clear_tables(db_session)
    yield
    await _clear_tables(db_session)


async def _user(db: AsyncSession, email: str | None = None) -> User:
    user = User(
        email=email or f"user-{uuid.uuid4().hex}@example.com",
        password_hash="hashed-password",
        display_name="Reminder User",
    )
    db.add(user)
    await db.flush()
    return user


async def _note(
    db: AsyncSession,
    user: User,
    *,
    due_at: datetime | None,
    title: str = "Reminder note",
    content: str = "Remember this\nSecond line",
    done_at: datetime | None = None,
    reminder_sent_at: datetime | None = None,
    recurring: str | None = None,
) -> Note:
    note = Note(
        user_id=user.id,
        title=title,
        content=content,
        source_type="text",
        category="Ideas",
        due_at=due_at,
        done_at=done_at,
        reminder_sent_at=reminder_sent_at,
        recurring=recurring,
    )
    db.add(note)
    await db.flush()
    return note


async def _subscription(db: AsyncSession, user: User, endpoint: str | None = None) -> PushSubscription:
    sub = PushSubscription(
        user_id=user.id,
        endpoint=endpoint or f"https://push.example.test/{uuid.uuid4()}",
        auth="auth-secret",
        p256dh="p256dh-key",
        user_agent="pytest",
    )
    db.add(sub)
    await db.flush()
    return sub


@pytest.mark.asyncio
async def test_find_due_reminders_filters_due_unsent_undone_recent(db_session: AsyncSession):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    user = await _user(db_session)
    included = await _note(db_session, user, due_at=now - timedelta(minutes=5))
    await _note(db_session, user, due_at=now + timedelta(minutes=5))
    await _note(db_session, user, due_at=now - timedelta(minutes=1), reminder_sent_at=now)
    await _note(db_session, user, due_at=now - timedelta(minutes=1), done_at=now)
    await _note(db_session, user, due_at=now - GRACE_WINDOW - timedelta(seconds=1))
    await _note(db_session, user, due_at=None)
    await db_session.commit()

    due = await find_due_reminders(db_session, now=now)

    assert [note.id for note in due] == [included.id]


@pytest.mark.asyncio
async def test_claim_reminders_only_claims_each_note_once(db_session: AsyncSession):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    user = await _user(db_session)
    first = await _note(db_session, user, due_at=now)
    second = await _note(db_session, user, due_at=now)
    await db_session.commit()

    claimed = await claim_reminders(db_session, [first.id, second.id], now=now)
    claimed_again = await claim_reminders(db_session, [first.id, second.id], now=now)

    assert claimed == {first.id, second.id}
    assert claimed_again == set()
    await db_session.refresh(first)
    assert _same_datetime(first.reminder_sent_at, now)


@pytest.mark.asyncio
async def test_send_for_note_without_subscriptions_falls_back_to_email(db_session: AsyncSession):
    user = await _user(db_session, "email-fallback@example.com")
    note = await _note(db_session, user, due_at=datetime.now(timezone.utc))
    await db_session.commit()

    with (
        patch("app.services.reminders.send_push", new=AsyncMock()) as mock_push,
        patch(
            "app.services.reminders.send_email",
            new=AsyncMock(return_value=NotifyResult(success=True, channel="email")),
        ) as mock_email,
    ):
        result = await _send_for_note(db_session, note)

    assert result == NotifyResult(success=True, channel="email")
    mock_push.assert_not_called()
    mock_email.assert_awaited_once()
    assert mock_email.call_args.args[0] == "email-fallback@example.com"


@pytest.mark.asyncio
async def test_send_for_note_returns_webpush_success_without_email(db_session: AsyncSession):
    user = await _user(db_session)
    note = await _note(db_session, user, due_at=datetime.now(timezone.utc))
    await _subscription(db_session, user)
    await db_session.commit()

    with (
        patch(
            "app.services.reminders.send_push",
            new=AsyncMock(return_value=NotifyResult(success=True, channel="webpush")),
        ) as mock_push,
        patch("app.services.reminders.send_email", new=AsyncMock()) as mock_email,
    ):
        result = await _send_for_note(db_session, note)

    assert result == NotifyResult(success=True, channel="webpush")
    mock_push.assert_awaited_once()
    mock_email.assert_not_called()


@pytest.mark.asyncio
async def test_send_for_note_falls_back_to_email_when_all_pushes_fail(db_session: AsyncSession):
    user = await _user(db_session, "push-failed@example.com")
    note = await _note(db_session, user, due_at=datetime.now(timezone.utc))
    await _subscription(db_session, user)
    await _subscription(db_session, user)
    await db_session.commit()

    with (
        patch(
            "app.services.reminders.send_push",
            new=AsyncMock(return_value=NotifyResult(success=False, channel="webpush", error="bad request")),
        ) as mock_push,
        patch(
            "app.services.reminders.send_email",
            new=AsyncMock(return_value=NotifyResult(success=True, channel="email")),
        ) as mock_email,
    ):
        result = await _send_for_note(db_session, note)

    assert result == NotifyResult(success=True, channel="email")
    assert mock_push.await_count == 2
    mock_email.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_for_note_deletes_expired_410_subscription(db_session: AsyncSession):
    user = await _user(db_session, "expired@example.com")
    note = await _note(db_session, user, due_at=datetime.now(timezone.utc))
    sub = await _subscription(db_session, user)
    sub_id = sub.id
    await db_session.commit()

    with (
        patch(
            "app.services.reminders.send_push",
            new=AsyncMock(
                return_value=NotifyResult(
                    success=False,
                    channel="webpush",
                    error="gone",
                    expired=True,
                )
            ),
        ),
        patch(
            "app.services.reminders.send_email",
            new=AsyncMock(return_value=NotifyResult(success=True, channel="email")),
        ),
    ):
        result = await _send_for_note(db_session, note)

    remaining = await db_session.execute(
        select(PushSubscription).where(PushSubscription.id == sub_id)
    )
    assert result == NotifyResult(success=True, channel="email")
    assert remaining.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_rollover_recurring_daily_advances_and_clears_markers(db_session: AsyncSession):
    due_at = datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc)
    user = await _user(db_session)
    note = await _note(
        db_session,
        user,
        due_at=due_at,
        recurring="daily",
        reminder_sent_at=due_at,
        done_at=due_at,
    )
    await db_session.commit()

    await rollover_recurring(db_session, note)

    assert note.due_at == due_at + timedelta(days=1)
    assert note.reminder_sent_at is None
    assert note.done_at is None


@pytest.mark.asyncio
async def test_rollover_recurring_weekly_advances_by_seven_days(db_session: AsyncSession):
    due_at = datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc)
    user = await _user(db_session)
    note = await _note(db_session, user, due_at=due_at, recurring="weekly", reminder_sent_at=due_at)
    await db_session.commit()

    await rollover_recurring(db_session, note)

    assert note.due_at == due_at + timedelta(weeks=1)
    assert note.reminder_sent_at is None


@pytest.mark.asyncio
async def test_rollover_recurring_monthly_uses_available_month_logic(db_session: AsyncSession):
    due_at = datetime(2026, 1, 15, 9, 30, tzinfo=timezone.utc)
    user = await _user(db_session)
    note = await _note(db_session, user, due_at=due_at, recurring="monthly", reminder_sent_at=due_at)
    await db_session.commit()

    try:
        from dateutil.relativedelta import relativedelta

        expected = due_at + relativedelta(months=1)
    except ImportError:
        expected = due_at + timedelta(days=30)

    await rollover_recurring(db_session, note)

    assert note.due_at == expected
    assert note.reminder_sent_at is None


def test_advance_due_monthly_falls_back_to_30_days_when_dateutil_missing(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "dateutil.relativedelta":
            raise ImportError("dateutil hidden for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    due_at = datetime(2026, 1, 15, 9, 30, tzinfo=timezone.utc)

    assert _advance_due(due_at, "monthly") == due_at + timedelta(days=30)


@pytest.mark.asyncio
async def test_rollover_recurring_non_recurring_is_noop(db_session: AsyncSession):
    due_at = datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc)
    sent_at = datetime(2026, 1, 1, 9, 31, tzinfo=timezone.utc)
    done_at = datetime(2026, 1, 1, 9, 32, tzinfo=timezone.utc)
    user = await _user(db_session)
    note = await _note(
        db_session,
        user,
        due_at=due_at,
        reminder_sent_at=sent_at,
        done_at=done_at,
    )
    await db_session.commit()

    await rollover_recurring(db_session, note)

    assert note.due_at == due_at
    assert note.reminder_sent_at == sent_at
    assert note.done_at == done_at


@pytest.mark.asyncio
async def test_dispatch_claims_sends_and_rolls_recurring_due_notes(db_session: AsyncSession):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    user = await _user(db_session, "dispatch@example.com")
    recurring = await _note(db_session, user, due_at=now - timedelta(minutes=3), recurring="daily")
    one_shot_a = await _note(db_session, user, due_at=now - timedelta(minutes=2))
    one_shot_b = await _note(db_session, user, due_at=now - timedelta(minutes=1))
    future = await _note(db_session, user, due_at=now + timedelta(minutes=1))
    done = await _note(db_session, user, due_at=now - timedelta(minutes=1), done_at=now)
    await db_session.commit()

    with patch(
        "app.services.reminders.send_email",
        new=AsyncMock(return_value=NotifyResult(success=True, channel="email")),
    ) as mock_email:
        result = await dispatch(db_session, now=now)

    assert result == {
        "found": 3,
        "claimed": 3,
        "sent_push": 0,
        "sent_email": 3,
        "failed": 0,
        "rolled": 1,
    }
    assert mock_email.await_count == 3
    assert recurring.due_at == now - timedelta(minutes=3) + timedelta(days=1)
    assert recurring.reminder_sent_at is None
    assert _same_datetime(one_shot_a.reminder_sent_at, now)
    assert _same_datetime(one_shot_b.reminder_sent_at, now)
    assert future.reminder_sent_at is None
    assert done.reminder_sent_at is None
