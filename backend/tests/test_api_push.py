"""
Tests for Web Push subscription API endpoints.
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.push_subscription import PushSubscription


def _payload(
    endpoint: str,
    auth: str = "auth-1",
    p256dh: str = "p256dh-1",
    user_agent: str | None = "pytest-agent",
) -> dict:
    return {
        "endpoint": endpoint,
        "keys": {"auth": auth, "p256dh": p256dh},
        "user_agent": user_agent,
    }


async def _subscriptions_for_user(
    db_session: AsyncSession,
    user_id: uuid.UUID,
) -> list[PushSubscription]:
    result = await db_session.execute(
        select(PushSubscription).where(PushSubscription.user_id == user_id)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_subscribe_then_resubscribe_updates_existing(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    endpoint = f"https://push.example.test/{uuid.uuid4()}"

    first = await client.post(
        "/api/push/subscribe",
        json=_payload(endpoint),
        headers=auth_headers,
    )
    assert first.status_code == 201, first.text
    first_body = first.json()
    assert first_body["created"] is True

    second = await client.post(
        "/api/push/subscribe",
        json=_payload(
            endpoint,
            auth="auth-2",
            p256dh="p256dh-2",
            user_agent="updated-agent",
        ),
        headers=auth_headers,
    )
    assert second.status_code == 201, second.text
    second_body = second.json()
    assert second_body == {"id": first_body["id"], "created": False}

    result = await db_session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    )
    subscription = result.scalar_one()
    assert subscription.auth == "auth-2"
    assert subscription.p256dh == "p256dh-2"
    assert subscription.user_agent == "updated-agent"


@pytest.mark.asyncio
async def test_subscribe_two_endpoints_same_user(
    client: AsyncClient,
    auth_headers: dict,
    registered_user: dict,
    db_session: AsyncSession,
):
    user_id = uuid.UUID(registered_user["user"]["id"])
    endpoint_a = f"https://push.example.test/{uuid.uuid4()}"
    endpoint_b = f"https://push.example.test/{uuid.uuid4()}"

    for endpoint in (endpoint_a, endpoint_b):
        resp = await client.post(
            "/api/push/subscribe",
            json=_payload(endpoint),
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text

    subscriptions = await _subscriptions_for_user(db_session, user_id)
    endpoints = {sub.endpoint for sub in subscriptions}
    assert {endpoint_a, endpoint_b}.issubset(endpoints)


@pytest.mark.asyncio
async def test_same_endpoint_different_users_allowed(
    client: AsyncClient,
    auth_headers: dict,
    second_user_headers: dict,
    db_session: AsyncSession,
):
    endpoint = f"https://push.example.test/{uuid.uuid4()}"

    first = await client.post(
        "/api/push/subscribe",
        json=_payload(endpoint),
        headers=auth_headers,
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/api/push/subscribe",
        json=_payload(endpoint, auth="other-auth", p256dh="other-p256dh"),
        headers=second_user_headers,
    )
    assert second.status_code == 201, second.text

    result = await db_session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    )
    assert len(result.scalars().all()) == 2


@pytest.mark.asyncio
async def test_unsubscribe_deletes_then_404(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    endpoint = f"https://push.example.test/{uuid.uuid4()}"
    sub = await client.post(
        "/api/push/subscribe",
        json=_payload(endpoint),
        headers=auth_headers,
    )
    assert sub.status_code == 201, sub.text

    resp = await client.request(
        "DELETE",
        "/api/push/subscribe",
        json={"endpoint": endpoint},
        headers=auth_headers,
    )
    assert resp.status_code == 204, resp.text

    result = await db_session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    )
    assert result.scalar_one_or_none() is None

    again = await client.request(
        "DELETE",
        "/api/push/subscribe",
        json={"endpoint": endpoint},
        headers=auth_headers,
    )
    assert again.status_code == 404


@pytest.mark.asyncio
async def test_vapid_public_key_configured(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "vapid_public_key", "test-public-key")

    resp = await client.get("/api/push/vapid-public-key")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"public_key": "test-public-key"}


@pytest.mark.asyncio
async def test_vapid_public_key_unset(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "vapid_public_key", None)

    resp = await client.get("/api/push/vapid-public-key")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"public_key": None}


@pytest.mark.asyncio
async def test_unsubscribe_cannot_delete_other_users_subscription(
    client: AsyncClient,
    auth_headers: dict,
    second_user_headers: dict,
    db_session: AsyncSession,
):
    endpoint = f"https://push.example.test/{uuid.uuid4()}"
    sub = await client.post(
        "/api/push/subscribe",
        json=_payload(endpoint),
        headers=auth_headers,
    )
    assert sub.status_code == 201, sub.text

    other_delete = await client.request(
        "DELETE",
        "/api/push/subscribe",
        json={"endpoint": endpoint},
        headers=second_user_headers,
    )
    assert other_delete.status_code == 404

    result = await db_session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    )
    assert result.scalar_one_or_none() is not None
