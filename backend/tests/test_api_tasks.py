import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _iso(value: datetime) -> str:
    return value.isoformat()


async def _create_task_note(
    client: AsyncClient,
    headers: dict,
    content: str,
    due_at: datetime | None = None,
    priority: int | None = None,
    recurring: str | None = None,
) -> dict:
    payload = {"content": content, "source_type": "text", "category": "Ideas"}
    if due_at is not None:
        payload["due_at_hint"] = _iso(due_at)
    if priority is not None:
        payload["priority_hint"] = priority
    if recurring is not None:
        payload["recurring_hint"] = recurring
    resp = await client.post("/api/notes", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_list_open_tasks_returns_due_not_done_and_truncates_content(
    client: AsyncClient,
    auth_headers: dict,
):
    due_at = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    long_content = "x" * 250
    task = await _create_task_note(client, auth_headers, long_content, due_at=due_at)
    done = await _create_task_note(
        client,
        auth_headers,
        "done task",
        due_at=due_at + timedelta(days=1),
    )
    await client.put(
        f"/api/notes/{done['id']}",
        json={"done_at": _iso(due_at)},
        headers=auth_headers,
    )

    resp = await client.get("/api/tasks?status=open", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = [item["id"] for item in body["items"]]
    assert task["id"] in ids
    assert done["id"] not in ids
    listed = next(item for item in body["items"] if item["id"] == task["id"])
    assert listed["done_at"] is None
    assert listed["due_at"] is not None
    assert len(listed["content"]) == 200


@pytest.mark.asyncio
async def test_list_overdue_tasks_filters_to_past_due(
    client: AsyncClient,
    auth_headers: dict,
):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    future = datetime.now(timezone.utc) + timedelta(days=1)
    overdue = await _create_task_note(client, auth_headers, "overdue task", due_at=past)
    upcoming = await _create_task_note(client, auth_headers, "future task", due_at=future)

    resp = await client.get("/api/tasks?status=overdue", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    ids = [item["id"] for item in resp.json()["items"]]
    assert overdue["id"] in ids
    assert upcoming["id"] not in ids


@pytest.mark.asyncio
async def test_list_done_tasks_filters_done_at(
    client: AsyncClient,
    auth_headers: dict,
):
    due_at = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    open_task = await _create_task_note(client, auth_headers, "open task", due_at=due_at)
    done_task = await _create_task_note(client, auth_headers, "done task", due_at=due_at)
    await client.put(
        f"/api/notes/{done_task['id']}",
        json={"done_at": _iso(due_at)},
        headers=auth_headers,
    )

    resp = await client.get("/api/tasks?status=done", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    ids = [item["id"] for item in resp.json()["items"]]
    assert done_task["id"] in ids
    assert open_task["id"] not in ids


@pytest.mark.asyncio
async def test_list_tasks_priority_filter(client: AsyncClient, auth_headers: dict):
    due_at = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    high = await _create_task_note(client, auth_headers, "high priority", due_at, priority=1)
    await _create_task_note(client, auth_headers, "low priority", due_at, priority=3)

    resp = await client.get("/api/tasks?status=open&priority=1", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [item["id"] for item in items] == [high["id"]]
    assert items[0]["priority"] == 1


@pytest.mark.asyncio
async def test_list_tasks_enforces_ownership_isolation(
    client: AsyncClient,
    auth_headers: dict,
    second_user_headers: dict,
):
    due_at = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    own = await _create_task_note(client, auth_headers, "owned task", due_at)
    other = await _create_task_note(client, second_user_headers, "other task", due_at)

    resp = await client.get("/api/tasks?status=open", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    ids = [item["id"] for item in resp.json()["items"]]
    assert own["id"] in ids
    assert other["id"] not in ids


@pytest.mark.asyncio
async def test_list_tasks_pagination(client: AsyncClient, auth_headers: dict):
    base = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    created = []
    for index in range(3):
        created.append(
            await _create_task_note(
                client,
                auth_headers,
                f"paged task {index}",
                base + timedelta(days=index),
            )
        )

    resp = await client.get("/api/tasks?status=open&limit=2&offset=1", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert [item["id"] for item in body["items"]] == [created[1]["id"], created[2]["id"]]


@pytest.mark.asyncio
async def test_done_endpoint_toggles_done_at(client: AsyncClient, auth_headers: dict):
    due_at = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    task = await _create_task_note(client, auth_headers, "toggle task", due_at)

    done_resp = await client.post(f"/api/notes/{task['id']}/done", headers=auth_headers)
    undone_resp = await client.post(f"/api/notes/{task['id']}/done", headers=auth_headers)

    assert done_resp.status_code == 200, done_resp.text
    assert done_resp.json()["done_at"] is not None
    assert undone_resp.status_code == 200, undone_resp.text
    assert undone_resp.json()["done_at"] is None


@pytest.mark.asyncio
async def test_recurring_done_rollover_advances_due_and_clears_reminder(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    due_at = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    task = await _create_task_note(
        client,
        auth_headers,
        "daily recurring task",
        due_at,
        recurring="daily",
    )
    note_id = uuid.UUID(task["id"])
    result = await db_session.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one()
    note.reminder_sent_at = datetime.now(timezone.utc)
    await db_session.commit()

    resp = await client.post(f"/api/notes/{task['id']}/done", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["done_at"] is None
    assert _parse_dt(body["due_at"]) == due_at + timedelta(days=1)
    assert body["reminder_sent_at"] is None
