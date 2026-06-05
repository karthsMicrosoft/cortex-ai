from datetime import datetime, timezone

import pytest
from httpx import AsyncClient


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@pytest.mark.asyncio
async def test_create_note_persists_browser_task_hints(
    client: AsyncClient,
    auth_headers: dict,
):
    due_at = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    resp = await client.post(
        "/api/notes",
        json={
            "content": "Follow up next week",
            "source_type": "text",
            "category": "Ideas",
            "due_at_hint": due_at.isoformat(),
            "priority_hint": 1,
            "recurring_hint": "weekly",
        },
        headers=auth_headers,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert _parse_dt(body["due_at"]) == due_at
    assert body["priority"] == 1
    assert body["recurring"] == "weekly"


@pytest.mark.asyncio
async def test_patch_note_updates_and_clears_task_fields(
    client: AsyncClient,
    auth_headers: dict,
):
    create_resp = await client.post(
        "/api/notes",
        json={"content": "Task fields", "source_type": "text", "category": "Ideas"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    note_id = create_resp.json()["id"]
    due_at = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)

    update_resp = await client.patch(
        f"/api/notes/{note_id}",
        json={"due_at": due_at.isoformat(), "priority": 2, "recurring": "daily"},
        headers=auth_headers,
    )

    assert update_resp.status_code == 200, update_resp.text
    updated = update_resp.json()
    assert _parse_dt(updated["due_at"]) == due_at
    assert updated["priority"] == 2
    assert updated["recurring"] == "daily"

    clear_resp = await client.patch(
        f"/api/notes/{note_id}",
        json={"due_at": None, "priority": None, "recurring": None},
        headers=auth_headers,
    )

    assert clear_resp.status_code == 200, clear_resp.text
    cleared = clear_resp.json()
    assert cleared["due_at"] is None
    assert cleared["priority"] is None
    assert cleared["recurring"] is None
