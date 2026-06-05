from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.config import settings
from app.services.notify.webpush import send_push
import app.services.notify.webpush as webpush_module


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class FakeWebPushException(Exception):
    def __init__(self, status_code: int, message: str = "webpush failed"):
        super().__init__(message)
        self.response = FakeResponse(status_code)


@pytest.fixture
def subscription():
    return SimpleNamespace(
        endpoint="https://push.example.test/send/abc",
        p256dh="p256dh-key",
        auth="auth-secret",
    )


@pytest.fixture
def payload():
    return {
        "title": "Reminder",
        "body": "Time to follow up",
        "url": "/tasks/123",
        "tag": "task-123",
    }


@pytest.mark.asyncio
async def test_send_push_noops_when_vapid_private_key_unset(monkeypatch, subscription, payload):
    monkeypatch.setattr(settings, "vapid_private_key", None)
    monkeypatch.setattr(webpush_module, "webpush", lambda **kwargs: None)
    monkeypatch.setattr(webpush_module, "WebPushException", FakeWebPushException)

    result = await send_push(subscription, payload)

    assert result.success is False
    assert result.channel == "none"
    assert "not configured" in result.error


@pytest.mark.asyncio
async def test_send_push_returns_success_when_webpush_succeeds(monkeypatch, subscription, payload):
    monkeypatch.setattr(settings, "vapid_private_key", "private-key")
    monkeypatch.setattr(settings, "vapid_subject", "mailto:admin@cortex.app")
    monkeypatch.setattr(webpush_module, "WebPushException", FakeWebPushException)

    with patch("app.services.notify.webpush.webpush") as mock_webpush:
        result = await send_push(subscription, payload)

    assert result.success is True
    assert result.channel == "webpush"
    mock_webpush.assert_called_once()
    kwargs = mock_webpush.call_args.kwargs
    assert kwargs["subscription_info"]["endpoint"] == subscription.endpoint
    assert kwargs["vapid_private_key"] == "private-key"
    assert kwargs["vapid_claims"] == {"sub": "mailto:admin@cortex.app"}


@pytest.mark.asyncio
async def test_send_push_marks_subscription_expired_on_410(monkeypatch, subscription, payload):
    monkeypatch.setattr(settings, "vapid_private_key", "private-key")
    monkeypatch.setattr(webpush_module, "WebPushException", FakeWebPushException)

    with patch(
        "app.services.notify.webpush.webpush",
        side_effect=FakeWebPushException(410),
    ):
        result = await send_push(subscription, payload)

    assert result.success is False
    assert result.channel == "webpush"
    assert result.error == "gone"
    assert result.expired is True


@pytest.mark.asyncio
async def test_send_push_reports_non_expired_webpush_errors(monkeypatch, subscription, payload):
    monkeypatch.setattr(settings, "vapid_private_key", "private-key")
    monkeypatch.setattr(webpush_module, "WebPushException", FakeWebPushException)

    with patch(
        "app.services.notify.webpush.webpush",
        side_effect=FakeWebPushException(400, "bad request"),
    ):
        result = await send_push(subscription, payload)

    assert result.success is False
    assert result.channel == "webpush"
    assert result.expired is False
    assert "bad request" in result.error


@pytest.mark.asyncio
async def test_send_push_noops_when_pywebpush_missing(monkeypatch, subscription, payload):
    monkeypatch.setattr(settings, "vapid_private_key", "private-key")
    monkeypatch.setattr(webpush_module, "webpush", None)

    result = await send_push(subscription, payload)

    assert result.success is False
    assert result.channel == "none"
    assert "not configured" in result.error
