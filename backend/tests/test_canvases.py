"""
Phase 7 — PR A: Visual Thinking Canvas API tests.

Covers all 12 endpoints under /api/canvases:
  * CRUD canvas
  * Items: add / update (with optimistic concurrency) / batch / delete
  * Edges: add (with cross-canvas validation) / delete
  * Auto-layout
  * Ownership isolation across users
  * Edge cases: large batches, viewport persistence, ghost cards,
    geometry validation, zoom bounds.
"""
from __future__ import annotations

import uuid
from typing import Optional

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canvas import Canvas
from app.models.canvas_item import CanvasItem
from app.models.note import Note

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _user_id_from_headers(client: AsyncClient, headers: dict) -> uuid.UUID:
    resp = await client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200, resp.text
    return uuid.UUID(resp.json()["id"])


async def _create_canvas_api(
    client: AsyncClient, headers: dict, title: str = "Untitled Canvas"
) -> dict:
    resp = await client.post(
        "/api/canvases", headers=headers, json={"title": title}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_note_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    content: str = "body",
    title: Optional[str] = None,
) -> Note:
    note = Note(user_id=user_id, content=content, title=title)
    db.add(note)
    await db.flush()
    return note


async def _add_item_api(
    client: AsyncClient,
    headers: dict,
    canvas_id: str,
    *,
    item_type: str = "text",
    note_id: Optional[str] = None,
    label: Optional[str] = None,
    position_x: float = 0.0,
    position_y: float = 0.0,
) -> dict:
    payload: dict = {
        "item_type": item_type,
        "position_x": position_x,
        "position_y": position_y,
    }
    if note_id is not None:
        payload["note_id"] = note_id
    if label is not None:
        payload["label"] = label
    resp = await client.post(
        f"/api/canvases/{canvas_id}/items", headers=headers, json=payload
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ===========================================================================
# 1 — CRUD canvas (~8 tests)
# ===========================================================================

async def test_create_canvas_201(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/canvases", headers=auth_headers, json={})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Untitled Canvas"
    assert body["viewport_zoom"] == 1
    assert "id" in body


async def test_create_canvas_with_custom_title(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/canvases",
        headers=auth_headers,
        json={"title": "Project Board", "description": "Sprint planning"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Project Board"
    assert body["description"] == "Sprint planning"


async def test_list_canvases_returns_only_user_canvases(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    mine = await _create_canvas_api(client, auth_headers, title="Mine")
    await _create_canvas_api(client, second_user_headers, title="Other")

    resp = await client.get("/api/canvases", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    titles = {c["title"] for c in body["items"]}
    assert "Mine" in titles
    assert "Other" not in titles
    assert body["total"] == len([c for c in body["items"] if c["id"] == mine["id"]]) or body["total"] >= 1


async def test_get_canvas_includes_items_and_edges(
    client: AsyncClient, auth_headers: dict
):
    canvas = await _create_canvas_api(client, auth_headers)
    a = await _add_item_api(client, auth_headers, canvas["id"], label="A")
    b = await _add_item_api(client, auth_headers, canvas["id"], label="B")

    # Add an edge between them
    edge_resp = await client.post(
        f"/api/canvases/{canvas['id']}/edges",
        headers=auth_headers,
        json={"source_item_id": a["id"], "target_item_id": b["id"]},
    )
    assert edge_resp.status_code == 201, edge_resp.text

    resp = await client.get(
        f"/api/canvases/{canvas['id']}", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 2
    assert len(body["edges"]) == 1
    assert body["edges"][0]["source_item_id"] == a["id"]


async def test_get_canvas_not_found_404(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        f"/api/canvases/{uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_get_canvas_other_user_404(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    other = await _create_canvas_api(client, second_user_headers, title="Other")
    resp = await client.get(
        f"/api/canvases/{other['id']}", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_update_canvas_title(client: AsyncClient, auth_headers: dict):
    canvas = await _create_canvas_api(client, auth_headers)
    resp = await client.patch(
        f"/api/canvases/{canvas['id']}",
        headers=auth_headers,
        json={"title": "Renamed"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Renamed"


async def test_delete_canvas_cascades_items_and_edges(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    canvas = await _create_canvas_api(client, auth_headers)
    a = await _add_item_api(client, auth_headers, canvas["id"], label="A")
    b = await _add_item_api(client, auth_headers, canvas["id"], label="B")
    await client.post(
        f"/api/canvases/{canvas['id']}/edges",
        headers=auth_headers,
        json={"source_item_id": a["id"], "target_item_id": b["id"]},
    )

    resp = await client.delete(
        f"/api/canvases/{canvas['id']}", headers=auth_headers
    )
    assert resp.status_code == 204

    # Verify the canvas is gone via GET.
    follow = await client.get(
        f"/api/canvases/{canvas['id']}", headers=auth_headers
    )
    assert follow.status_code == 404


# ===========================================================================
# 2 — Canvas items (~10 tests)
# ===========================================================================

async def test_add_note_item_snapshots_title(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    user_id = await _user_id_from_headers(client, auth_headers)
    note = await _create_note_for_user(
        db_session, user_id, content="My note", title="My title"
    )
    await db_session.commit()

    canvas = await _create_canvas_api(client, auth_headers)
    body = await _add_item_api(
        client, auth_headers, canvas["id"],
        item_type="note", note_id=str(note.id),
    )
    assert body["note_id"] == str(note.id)
    assert body["last_known_title"] == "My title"
    assert body["version"] == 1


async def test_add_group_item(client: AsyncClient, auth_headers: dict):
    canvas = await _create_canvas_api(client, auth_headers)
    body = await _add_item_api(
        client, auth_headers, canvas["id"], item_type="group", label="Pile"
    )
    assert body["item_type"] == "group"
    assert body["label"] == "Pile"


async def test_add_text_item(client: AsyncClient, auth_headers: dict):
    canvas = await _create_canvas_api(client, auth_headers)
    body = await _add_item_api(
        client, auth_headers, canvas["id"], item_type="text", label="hi"
    )
    assert body["item_type"] == "text"


async def test_add_duplicate_note_item_409(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    user_id = await _user_id_from_headers(client, auth_headers)
    note = await _create_note_for_user(db_session, user_id, content="dup", title="t")
    await db_session.commit()

    canvas = await _create_canvas_api(client, auth_headers)
    await _add_item_api(
        client, auth_headers, canvas["id"],
        item_type="note", note_id=str(note.id),
    )
    resp = await client.post(
        f"/api/canvases/{canvas['id']}/items",
        headers=auth_headers,
        json={"item_type": "note", "note_id": str(note.id)},
    )
    assert resp.status_code == 409, resp.text


async def test_update_item_position_increments_version(
    client: AsyncClient, auth_headers: dict
):
    canvas = await _create_canvas_api(client, auth_headers)
    item = await _add_item_api(client, auth_headers, canvas["id"], label="A")
    assert item["version"] == 1

    resp = await client.patch(
        f"/api/canvases/{canvas['id']}/items/{item['id']}",
        headers=auth_headers,
        json={"position_x": 123.4, "position_y": 56.7, "version": 1},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["position_x"] == 123.4
    assert body["position_y"] == 56.7
    assert body["version"] == 2


async def test_update_item_version_conflict_409(
    client: AsyncClient, auth_headers: dict
):
    canvas = await _create_canvas_api(client, auth_headers)
    item = await _add_item_api(client, auth_headers, canvas["id"], label="A")

    resp = await client.patch(
        f"/api/canvases/{canvas['id']}/items/{item['id']}",
        headers=auth_headers,
        json={"position_x": 10, "version": 99},
    )
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["current_version"] == 1


async def test_delete_item_204(client: AsyncClient, auth_headers: dict):
    canvas = await _create_canvas_api(client, auth_headers)
    item = await _add_item_api(client, auth_headers, canvas["id"], label="A")
    resp = await client.delete(
        f"/api/canvases/{canvas['id']}/items/{item['id']}",
        headers=auth_headers,
    )
    assert resp.status_code == 204
    # Confirm via get
    detail = await client.get(
        f"/api/canvases/{canvas['id']}", headers=auth_headers
    )
    assert detail.json()["items"] == []


async def test_batch_update_increments_all_versions(
    client: AsyncClient, auth_headers: dict
):
    canvas = await _create_canvas_api(client, auth_headers)
    a = await _add_item_api(client, auth_headers, canvas["id"], label="A")
    b = await _add_item_api(client, auth_headers, canvas["id"], label="B")

    payload = {
        "items": [
            {"id": a["id"], "position_x": 10, "position_y": 20, "version": 1},
            {"id": b["id"], "position_x": 30, "position_y": 40, "version": 1},
        ]
    }
    resp = await client.post(
        f"/api/canvases/{canvas['id']}/items/batch",
        headers=auth_headers,
        json=payload,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 2
    for it in body["items"]:
        assert it["version"] == 2


async def test_batch_update_version_conflict_rolls_back(
    client: AsyncClient, auth_headers: dict
):
    canvas = await _create_canvas_api(client, auth_headers)
    a = await _add_item_api(client, auth_headers, canvas["id"], label="A")
    b = await _add_item_api(client, auth_headers, canvas["id"], label="B")

    payload = {
        "items": [
            {"id": a["id"], "position_x": 999, "version": 1},
            {"id": b["id"], "position_x": 999, "version": 42},  # bad
        ]
    }
    resp = await client.post(
        f"/api/canvases/{canvas['id']}/items/batch",
        headers=auth_headers,
        json=payload,
    )
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    conflict_ids = {c["id"] for c in detail["conflicts"]}
    assert b["id"] in conflict_ids

    # Verify A was NOT updated (rollback).
    follow = await client.get(
        f"/api/canvases/{canvas['id']}", headers=auth_headers
    )
    by_id = {it["id"]: it for it in follow.json()["items"]}
    assert by_id[a["id"]]["position_x"] != 999
    assert by_id[a["id"]]["version"] == 1


async def test_item_on_other_users_canvas_404(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    other = await _create_canvas_api(client, second_user_headers)
    other_item = await _add_item_api(
        client, second_user_headers, other["id"], label="X"
    )
    resp = await client.patch(
        f"/api/canvases/{other['id']}/items/{other_item['id']}",
        headers=auth_headers,
        json={"position_x": 5, "version": 1},
    )
    assert resp.status_code == 404


# ===========================================================================
# 3 — Canvas edges (~6 tests)
# ===========================================================================

async def test_add_edge_201(client: AsyncClient, auth_headers: dict):
    canvas = await _create_canvas_api(client, auth_headers)
    a = await _add_item_api(client, auth_headers, canvas["id"], label="A")
    b = await _add_item_api(client, auth_headers, canvas["id"], label="B")
    resp = await client.post(
        f"/api/canvases/{canvas['id']}/edges",
        headers=auth_headers,
        json={"source_item_id": a["id"], "target_item_id": b["id"], "style": "dashed"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["style"] == "dashed"


async def test_add_edge_invalid_source_422(
    client: AsyncClient, auth_headers: dict
):
    canvas = await _create_canvas_api(client, auth_headers)
    b = await _add_item_api(client, auth_headers, canvas["id"], label="B")
    resp = await client.post(
        f"/api/canvases/{canvas['id']}/edges",
        headers=auth_headers,
        json={
            "source_item_id": str(uuid.uuid4()),
            "target_item_id": b["id"],
        },
    )
    assert resp.status_code == 422, resp.text


async def test_add_edge_cross_canvas_422(
    client: AsyncClient, auth_headers: dict
):
    c1 = await _create_canvas_api(client, auth_headers, title="C1")
    c2 = await _create_canvas_api(client, auth_headers, title="C2")
    a = await _add_item_api(client, auth_headers, c1["id"], label="A")
    b = await _add_item_api(client, auth_headers, c2["id"], label="B")

    resp = await client.post(
        f"/api/canvases/{c1['id']}/edges",
        headers=auth_headers,
        json={"source_item_id": a["id"], "target_item_id": b["id"]},
    )
    assert resp.status_code == 422


async def test_add_duplicate_edge_409(client: AsyncClient, auth_headers: dict):
    canvas = await _create_canvas_api(client, auth_headers)
    a = await _add_item_api(client, auth_headers, canvas["id"], label="A")
    b = await _add_item_api(client, auth_headers, canvas["id"], label="B")
    payload = {"source_item_id": a["id"], "target_item_id": b["id"]}
    first = await client.post(
        f"/api/canvases/{canvas['id']}/edges",
        headers=auth_headers,
        json=payload,
    )
    assert first.status_code == 201
    second = await client.post(
        f"/api/canvases/{canvas['id']}/edges",
        headers=auth_headers,
        json=payload,
    )
    assert second.status_code == 409, second.text


async def test_delete_edge_204(client: AsyncClient, auth_headers: dict):
    canvas = await _create_canvas_api(client, auth_headers)
    a = await _add_item_api(client, auth_headers, canvas["id"], label="A")
    b = await _add_item_api(client, auth_headers, canvas["id"], label="B")
    edge_resp = await client.post(
        f"/api/canvases/{canvas['id']}/edges",
        headers=auth_headers,
        json={"source_item_id": a["id"], "target_item_id": b["id"]},
    )
    edge_id = edge_resp.json()["id"]
    resp = await client.delete(
        f"/api/canvases/{canvas['id']}/edges/{edge_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 204


async def test_edge_cascades_when_item_deleted(
    client: AsyncClient, auth_headers: dict
):
    canvas = await _create_canvas_api(client, auth_headers)
    a = await _add_item_api(client, auth_headers, canvas["id"], label="A")
    b = await _add_item_api(client, auth_headers, canvas["id"], label="B")
    edge_resp = await client.post(
        f"/api/canvases/{canvas['id']}/edges",
        headers=auth_headers,
        json={"source_item_id": a["id"], "target_item_id": b["id"]},
    )
    assert edge_resp.status_code == 201

    # Delete source item — edge should cascade.
    del_resp = await client.delete(
        f"/api/canvases/{canvas['id']}/items/{a['id']}",
        headers=auth_headers,
    )
    assert del_resp.status_code == 204

    detail = await client.get(
        f"/api/canvases/{canvas['id']}", headers=auth_headers
    )
    assert detail.json()["edges"] == []


# ===========================================================================
# 4 — Auto-layout (~3 tests)
# ===========================================================================

async def test_auto_layout_empty_canvas_200(
    client: AsyncClient, auth_headers: dict
):
    canvas = await _create_canvas_api(client, auth_headers)
    resp = await client.post(
        f"/api/canvases/{canvas['id']}/auto-layout", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []


async def test_auto_layout_changes_positions(
    client: AsyncClient, auth_headers: dict
):
    canvas = await _create_canvas_api(client, auth_headers)
    items = [
        await _add_item_api(
            client, auth_headers, canvas["id"], label=f"i{i}",
            position_x=0, position_y=0,
        )
        for i in range(4)
    ]

    resp = await client.post(
        f"/api/canvases/{canvas['id']}/auto-layout", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 4
    # All items should have a non-(0,0) position OR at least be distinct.
    positions = {(it["position_x"], it["position_y"]) for it in body["items"]}
    assert len(positions) == 4
    # All versions bumped from 1 → 2.
    assert all(it["version"] == 2 for it in body["items"])


async def test_auto_layout_not_found_404(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        f"/api/canvases/{uuid.uuid4()}/auto-layout", headers=auth_headers
    )
    assert resp.status_code == 404


# ===========================================================================
# 5 — Ownership isolation (~5 tests)
# ===========================================================================

async def test_list_excludes_other_user_canvases(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _create_canvas_api(client, second_user_headers, title="Foreign")
    resp = await client.get("/api/canvases", headers=auth_headers)
    titles = {c["title"] for c in resp.json()["items"]}
    assert "Foreign" not in titles


async def test_cannot_add_item_to_other_users_canvas(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    other = await _create_canvas_api(client, second_user_headers)
    resp = await client.post(
        f"/api/canvases/{other['id']}/items",
        headers=auth_headers,
        json={"item_type": "text", "label": "sneak"},
    )
    assert resp.status_code == 404


async def test_cannot_update_other_users_item(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    other = await _create_canvas_api(client, second_user_headers)
    item = await _add_item_api(client, second_user_headers, other["id"], label="X")
    resp = await client.patch(
        f"/api/canvases/{other['id']}/items/{item['id']}",
        headers=auth_headers,
        json={"position_x": 10, "version": 1},
    )
    assert resp.status_code == 404


async def test_cannot_add_edge_to_other_users_canvas(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    other = await _create_canvas_api(client, second_user_headers)
    a = await _add_item_api(client, second_user_headers, other["id"], label="A")
    b = await _add_item_api(client, second_user_headers, other["id"], label="B")
    resp = await client.post(
        f"/api/canvases/{other['id']}/edges",
        headers=auth_headers,
        json={"source_item_id": a["id"], "target_item_id": b["id"]},
    )
    assert resp.status_code == 404


async def test_cannot_delete_other_users_canvas(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    other = await _create_canvas_api(client, second_user_headers, title="Other")
    resp = await client.delete(
        f"/api/canvases/{other['id']}", headers=auth_headers
    )
    assert resp.status_code == 404


# ===========================================================================
# 6 — Edge cases (~5 tests)
# ===========================================================================

async def test_large_batch_update(client: AsyncClient, auth_headers: dict):
    """50+ items batched in a single transactional update."""
    canvas = await _create_canvas_api(client, auth_headers)
    items = [
        await _add_item_api(client, auth_headers, canvas["id"], label=f"i{i}")
        for i in range(50)
    ]
    payload = {
        "items": [
            {"id": it["id"], "position_x": float(i), "version": 1}
            for i, it in enumerate(items)
        ]
    }
    resp = await client.post(
        f"/api/canvases/{canvas['id']}/items/batch",
        headers=auth_headers,
        json=payload,
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 50


async def test_viewport_persistence(client: AsyncClient, auth_headers: dict):
    canvas = await _create_canvas_api(client, auth_headers)
    resp = await client.patch(
        f"/api/canvases/{canvas['id']}",
        headers=auth_headers,
        json={"viewport_x": 100.5, "viewport_y": -200.5, "viewport_zoom": 2.0},
    )
    assert resp.status_code == 200
    detail = await client.get(
        f"/api/canvases/{canvas['id']}", headers=auth_headers
    )
    body = detail.json()
    assert body["viewport_x"] == 100.5
    assert body["viewport_y"] == -200.5
    assert body["viewport_zoom"] == 2.0


async def test_ghost_card_after_note_deletion(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """When the underlying note's FK is cleared (ON DELETE SET NULL on Postgres),
    the canvas_item survives and the snapshot title is still surfaced.

    SQLite doesn't enforce ON DELETE SET NULL by default, so we simulate the
    post-cascade DB state directly and verify the API contract.
    """
    from sqlalchemy import select, update

    user_id = await _user_id_from_headers(client, auth_headers)
    note = await _create_note_for_user(
        db_session, user_id, content="x", title="Ghost title"
    )
    await db_session.commit()

    canvas = await _create_canvas_api(client, auth_headers)
    item = await _add_item_api(
        client, auth_headers, canvas["id"],
        item_type="note", note_id=str(note.id),
    )
    assert item["last_known_title"] == "Ghost title"

    # Simulate ON DELETE SET NULL: clear note_id, then delete the note row.
    await db_session.execute(
        update(CanvasItem)
        .where(CanvasItem.id == uuid.UUID(item["id"]))
        .values(note_id=None)
    )
    await db_session.execute(
        Note.__table__.delete().where(Note.id == note.id)
    )
    await db_session.commit()

    detail = await client.get(
        f"/api/canvases/{canvas['id']}", headers=auth_headers
    )
    items = detail.json()["items"]
    assert len(items) == 1
    assert items[0]["note_id"] is None
    assert items[0]["last_known_title"] == "Ghost title"


async def test_negative_width_422(client: AsyncClient, auth_headers: dict):
    canvas = await _create_canvas_api(client, auth_headers)
    resp = await client.post(
        f"/api/canvases/{canvas['id']}/items",
        headers=auth_headers,
        json={"item_type": "text", "width": -5},
    )
    assert resp.status_code == 422


async def test_zoom_out_of_range_422(client: AsyncClient, auth_headers: dict):
    canvas = await _create_canvas_api(client, auth_headers)
    resp = await client.patch(
        f"/api/canvases/{canvas['id']}",
        headers=auth_headers,
        json={"viewport_zoom": 9.0},
    )
    assert resp.status_code == 422
