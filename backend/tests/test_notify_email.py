from unittest.mock import Mock, patch

import pytest

from app.config import settings
from app.services.notify import email


@pytest.mark.asyncio
async def test_send_email_noops_when_acs_connection_unset(monkeypatch):
    monkeypatch.setattr(settings, "acs_email_connection", None)
    monkeypatch.setattr(settings, "acs_email_sender", "donotreply@example.com")

    result = await email.send_email("user@example.com", "Subject", "<p>Hello</p>")

    assert result.success is False
    assert result.channel == "none"
    assert result.error == "acs not configured"


@pytest.mark.asyncio
async def test_send_email_succeeds_with_mocked_email_client(monkeypatch):
    monkeypatch.setattr(settings, "acs_email_connection", "endpoint=https://example.communication.azure.com/;accesskey=fake")
    monkeypatch.setattr(settings, "acs_email_sender", "donotreply@example.com")

    poller = Mock()
    poller.result.return_value = None
    client = Mock()
    client.begin_send.return_value = poller

    with patch("app.services.notify.email.EmailClient") as mock_email_client:
        mock_email_client.from_connection_string.return_value = client

        result = await email.send_email(
            "user@example.com",
            "Subject",
            "<p>Hello</p>",
            "Hello",
        )

    assert result.success is True
    assert result.channel == "email"
    mock_email_client.from_connection_string.assert_called_once_with(settings.acs_email_connection)
    client.begin_send.assert_called_once_with(
        {
            "content": {
                "subject": "Subject",
                "html": "<p>Hello</p>",
                "plainText": "Hello",
            },
            "recipients": {"to": [{"address": "user@example.com"}]},
            "senderAddress": "donotreply@example.com",
        }
    )
    poller.result.assert_called_once_with()


@pytest.mark.asyncio
async def test_send_email_returns_error_when_email_client_raises(monkeypatch):
    monkeypatch.setattr(settings, "acs_email_connection", "endpoint=https://example.communication.azure.com/;accesskey=fake")
    monkeypatch.setattr(settings, "acs_email_sender", "donotreply@example.com")

    client = Mock()
    client.begin_send.side_effect = RuntimeError("send failed")

    with patch("app.services.notify.email.EmailClient") as mock_email_client:
        mock_email_client.from_connection_string.return_value = client

        result = await email.send_email("user@example.com", "Subject", "<p>Hello</p>")

    assert result.success is False
    assert result.channel == "email"
    assert "send failed" in result.error


@pytest.mark.asyncio
async def test_send_email_noops_when_email_client_missing(monkeypatch):
    monkeypatch.setattr(settings, "acs_email_connection", "endpoint=https://example.communication.azure.com/;accesskey=fake")
    monkeypatch.setattr(settings, "acs_email_sender", "donotreply@example.com")

    with patch("app.services.notify.email.EmailClient", None):
        result = await email.send_email("user@example.com", "Subject", "<p>Hello</p>")

    assert result.success is False
    assert result.channel == "none"
    assert result.error == "acs not configured"
