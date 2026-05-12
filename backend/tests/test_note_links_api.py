"""
PR 6.1 — Backlinks API tests (TDD).

Endpoint: GET /api/notes/{note_id}/links

Returns:
{
  "outgoing": [ { note_id, title, summary, link_type, score, category }, ... ],
  "incoming": [ ... ]
}

Sort: link_type priority (manual > wiki > semantic) then score desc.
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note
from app.models.note_link import NoteLink
from app.models.user import User


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_note_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    content: str = "body",
    title: str | None = None,
    summary: str | None = None,
    category: str = "Ideas",
) -> Note:
    note = Note(
        user_id=user_id,
        content=content,
        title=title,
        summary=summary,
        category=category,
    )
    db.add(note)
    await db.flush()
    return note


async def _user_id_from_headers(client: AsyncClient, headers: dict) -> uuid.UUID:
    """Extract the user id by hitting /api/auth/me."""
    resp = await client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200, resp.text
    return uuid.UUID(resp.json()["id"])


# ---------------------------------------------------------------------------
# Auth + 404 cases
# ---------------------------------------------------------------------------

async def test_get_links_requires_auth(client: AsyncClient):
    """No Authorization header → 401."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/notes/{fake_id}/links")
    assert resp.status_code == 401, resp.text


async def test_get_links_404_for_missing_note(client: AsyncClient, auth_headers: dict):
    """Random uuid that doesn't exist → 404."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/notes/{fake_id}/links", headers=auth_headers)
    assert resp.status_code == 404, resp.text


async def test_get_links_404_for_other_users_note(
    client: AsyncClient,
    auth_headers: dict,
    second_user_headers: dict,
    db_session: AsyncSession,
):
    """A note that exists but belongs to another user → 404 (no leak)."""
    other_user_id = await _user_id_from_headers(client, second_user_headers)
    other_note = await _create_note_for_user(db_session, other_user_id, content="other")
    await db_session.commit()

    resp = await client.get(f"/api/notes/{other_note.id}/links", headers=auth_headers)
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

async def test_get_links_empty_for_isolated_note(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """A note with no links should return both arrays empty."""
    user_id = await _user_id_from_headers(client, auth_headers)
    note = await _create_note_for_user(db_session, user_id, content="lonely")
    await db_session.commit()

    resp = await client.get(f"/api/notes/{note.id}/links", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"outgoing": [], "incoming": []}


async def test_get_links_returns_outgoing_and_incoming(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """Both outgoing and incoming directions should be populated."""
    user_id = await _user_id_from_headers(client, auth_headers)
    a = await _create_note_for_user(db_session, user_id, content="A")
    b = await _create_note_for_user(db_session, user_id, content="B", title="Beta")
    c = await _create_note_for_user(db_session, user_id, content="C", title="Gamma")

    db_session.add_all([
        NoteLink(source_note_id=a.id, target_note_id=b.id, similarity_score=0.7, link_type="semantic"),
        NoteLink(source_note_id=c.id, target_note_id=a.id, similarity_score=0.5, link_type="semantic"),
    ])
    await db_session.commit()

    resp = await client.get(f"/api/notes/{a.id}/links", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert len(body["outgoing"]) == 1
    assert body["outgoing"][0]["note_id"] == str(b.id)
    assert len(body["incoming"]) == 1
    assert body["incoming"][0]["note_id"] == str(c.id)


async def test_get_links_includes_note_metadata(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """Each returned link must include title, summary, category, link_type."""
    user_id = await _user_id_from_headers(client, auth_headers)
    a = await _create_note_for_user(db_session, user_id, content="A")
    b = await _create_note_for_user(
        db_session,
        user_id,
        content="B-content",
        title="B-title",
        summary="B-summary",
        category="Learning",
    )
    db_session.add(
        NoteLink(source_note_id=a.id, target_note_id=b.id, similarity_score=0.9, link_type="semantic"),
    )
    await db_session.commit()

    resp = await client.get(f"/api/notes/{a.id}/links", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    item = resp.json()["outgoing"][0]
    assert item["note_id"] == str(b.id)
    assert item["title"] == "B-title"
    assert item["summary"] == "B-summary"
    assert item["category"] == "Learning"
    assert item["link_type"] == "semantic"
    assert item["score"] == pytest.approx(0.9)


async def test_get_links_sorted_by_priority_then_score(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """Manual > wiki > semantic. Within semantic: score desc."""
    user_id = await _user_id_from_headers(client, auth_headers)
    src = await _create_note_for_user(db_session, user_id, content="src")
    t_man = await _create_note_for_user(db_session, user_id, content="man")
    t_wiki = await _create_note_for_user(db_session, user_id, content="wiki")
    t_sem_low = await _create_note_for_user(db_session, user_id, content="sem-low")
    t_sem_high = await _create_note_for_user(db_session, user_id, content="sem-high")

    db_session.add_all([
        NoteLink(source_note_id=src.id, target_note_id=t_sem_low.id,  similarity_score=0.3, link_type="semantic"),
        NoteLink(source_note_id=src.id, target_note_id=t_man.id,      similarity_score=1.0, link_type="manual"),
        NoteLink(source_note_id=src.id, target_note_id=t_sem_high.id, similarity_score=0.9, link_type="semantic"),
        NoteLink(source_note_id=src.id, target_note_id=t_wiki.id,     similarity_score=1.0, link_type="wiki"),
    ])
    await db_session.commit()

    resp = await client.get(f"/api/notes/{src.id}/links", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    outgoing = resp.json()["outgoing"]
    assert [item["link_type"] for item in outgoing] == ["manual", "wiki", "semantic", "semantic"]
    # within semantic: high score first
    sem_items = [i for i in outgoing if i["link_type"] == "semantic"]
    assert sem_items[0]["note_id"] == str(t_sem_high.id)
    assert sem_items[1]["note_id"] == str(t_sem_low.id)


async def test_get_links_filters_to_user_notes_only(
    client: AsyncClient,
    auth_headers: dict,
    second_user_headers: dict,
    db_session: AsyncSession,
):
    """If a linked note on the OTHER end belongs to a different user, omit it (privacy)."""
    user_id = await _user_id_from_headers(client, auth_headers)
    other_user_id = await _user_id_from_headers(client, second_user_headers)

    mine = await _create_note_for_user(db_session, user_id, content="mine")
    mine_friend = await _create_note_for_user(db_session, user_id, content="mine-friend")
    foreign = await _create_note_for_user(db_session, other_user_id, content="foreign")

    db_session.add_all([
        NoteLink(source_note_id=mine.id, target_note_id=mine_friend.id, similarity_score=0.8, link_type="semantic"),
        # cross-user link rows (should never normally exist, but defend against it)
        NoteLink(source_note_id=mine.id, target_note_id=foreign.id, similarity_score=0.9, link_type="semantic"),
        NoteLink(source_note_id=foreign.id, target_note_id=mine.id, similarity_score=0.6, link_type="semantic"),
    ])
    await db_session.commit()

    resp = await client.get(f"/api/notes/{mine.id}/links", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    out_ids = {item["note_id"] for item in body["outgoing"]}
    in_ids = {item["note_id"] for item in body["incoming"]}
    assert str(mine_friend.id) in out_ids
    assert str(foreign.id) not in out_ids
    assert str(foreign.id) not in in_ids


# ---------------------------------------------------------------------------
# PR 6.3 — Manual link creation (POST) + deletion (DELETE)
# ---------------------------------------------------------------------------
#
# Endpoints under test:
#   POST   /api/notes/{note_id}/links
#   DELETE /api/notes/{note_id}/links/{link_id}
#
# Behaviour summary:
#   - Only link_type='manual' is allowed via these endpoints.
#   - POST is idempotent for an existing (source, target, manual) row (200).
#   - POST inserts return 201; the response carries id/source/target/link_type/
#     score/created_at; score is null for manual links.
#   - Self-links rejected with 400.
#   - Other-user notes (source or target) → 404 (no existence leak).
#   - DELETE returns 204 and removes only manual rows; semantic/wiki rows
#     return 403; missing → 404.

async def test_create_manual_link_201(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """Successful manual link creation returns 201 with the new row."""
    user_id = await _user_id_from_headers(client, auth_headers)
    src = await _create_note_for_user(db_session, user_id, content="src")
    tgt = await _create_note_for_user(db_session, user_id, content="tgt")
    await db_session.commit()

    resp = await client.post(
        f"/api/notes/{src.id}/links",
        headers=auth_headers,
        json={"target_note_id": str(tgt.id), "link_type": "manual"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source_note_id"] == str(src.id)
    assert body["target_note_id"] == str(tgt.id)
    assert body["link_type"] == "manual"
    assert body["score"] is None
    assert "id" in body and body["id"]
    assert "created_at" in body


async def test_create_manual_link_idempotent_200(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """A repeated POST with the same triple returns 200 + the existing row."""
    user_id = await _user_id_from_headers(client, auth_headers)
    src = await _create_note_for_user(db_session, user_id, content="src")
    tgt = await _create_note_for_user(db_session, user_id, content="tgt")
    await db_session.commit()

    payload = {"target_note_id": str(tgt.id), "link_type": "manual"}
    first = await client.post(f"/api/notes/{src.id}/links", headers=auth_headers, json=payload)
    assert first.status_code == 201, first.text
    first_id = first.json()["id"]

    second = await client.post(f"/api/notes/{src.id}/links", headers=auth_headers, json=payload)
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first_id


async def test_create_manual_link_self_400(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """Self-links (source == target) are rejected with 400."""
    user_id = await _user_id_from_headers(client, auth_headers)
    note = await _create_note_for_user(db_session, user_id, content="me")
    await db_session.commit()

    resp = await client.post(
        f"/api/notes/{note.id}/links",
        headers=auth_headers,
        json={"target_note_id": str(note.id), "link_type": "manual"},
    )
    assert resp.status_code == 400, resp.text


async def test_create_manual_link_other_user_404(
    client: AsyncClient,
    auth_headers: dict,
    second_user_headers: dict,
    db_session: AsyncSession,
):
    """If source OR target belongs to another user → 404 (no leak)."""
    user_id = await _user_id_from_headers(client, auth_headers)
    other_user_id = await _user_id_from_headers(client, second_user_headers)

    mine = await _create_note_for_user(db_session, user_id, content="mine")
    foreign = await _create_note_for_user(db_session, other_user_id, content="foreign")
    await db_session.commit()

    # Source mine, target foreign → 404.
    resp1 = await client.post(
        f"/api/notes/{mine.id}/links",
        headers=auth_headers,
        json={"target_note_id": str(foreign.id), "link_type": "manual"},
    )
    assert resp1.status_code == 404, resp1.text

    # Source foreign (not mine) → 404.
    resp2 = await client.post(
        f"/api/notes/{foreign.id}/links",
        headers=auth_headers,
        json={"target_note_id": str(mine.id), "link_type": "manual"},
    )
    assert resp2.status_code == 404, resp2.text


async def test_create_manual_link_invalid_type_400(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """link_type must be 'manual' for this endpoint; 'semantic' → 400."""
    user_id = await _user_id_from_headers(client, auth_headers)
    src = await _create_note_for_user(db_session, user_id, content="src")
    tgt = await _create_note_for_user(db_session, user_id, content="tgt")
    await db_session.commit()

    resp = await client.post(
        f"/api/notes/{src.id}/links",
        headers=auth_headers,
        json={"target_note_id": str(tgt.id), "link_type": "semantic"},
    )
    assert resp.status_code == 400, resp.text


async def test_create_manual_link_coexists_with_semantic(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """Pre-existing (A,B,semantic) must not block POST (A,B,manual)."""
    user_id = await _user_id_from_headers(client, auth_headers)
    src = await _create_note_for_user(db_session, user_id, content="src")
    tgt = await _create_note_for_user(db_session, user_id, content="tgt")
    db_session.add(
        NoteLink(
            source_note_id=src.id,
            target_note_id=tgt.id,
            similarity_score=0.42,
            link_type="semantic",
        )
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/notes/{src.id}/links",
        headers=auth_headers,
        json={"target_note_id": str(tgt.id), "link_type": "manual"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["link_type"] == "manual"


async def test_delete_manual_link_204(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """DELETE on a manual link owned by the user returns 204."""
    user_id = await _user_id_from_headers(client, auth_headers)
    src = await _create_note_for_user(db_session, user_id, content="src")
    tgt = await _create_note_for_user(db_session, user_id, content="tgt")
    link = NoteLink(
        source_note_id=src.id,
        target_note_id=tgt.id,
        similarity_score=0.0,
        link_type="manual",
    )
    db_session.add(link)
    await db_session.commit()

    resp = await client.delete(
        f"/api/notes/{src.id}/links/{link.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 204, resp.text

    # Verify the row is gone via the GET endpoint.
    list_resp = await client.get(f"/api/notes/{src.id}/links", headers=auth_headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["outgoing"] == []


async def test_delete_manual_link_404_for_nonexistent(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """DELETE for a link id that doesn't exist (under an owned note) → 404."""
    user_id = await _user_id_from_headers(client, auth_headers)
    src = await _create_note_for_user(db_session, user_id, content="src")
    await db_session.commit()

    resp = await client.delete(
        f"/api/notes/{src.id}/links/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert resp.status_code == 404, resp.text


async def test_delete_link_403_for_non_manual(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """DELETE on a semantic/wiki link returns 403 (only manual is removable here)."""
    user_id = await _user_id_from_headers(client, auth_headers)
    src = await _create_note_for_user(db_session, user_id, content="src")
    tgt = await _create_note_for_user(db_session, user_id, content="tgt")
    link = NoteLink(
        source_note_id=src.id,
        target_note_id=tgt.id,
        similarity_score=0.7,
        link_type="semantic",
    )
    db_session.add(link)
    await db_session.commit()

    resp = await client.delete(
        f"/api/notes/{src.id}/links/{link.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 403, resp.text


async def test_delete_link_404_for_other_users_source_note(
    client: AsyncClient,
    auth_headers: dict,
    second_user_headers: dict,
    db_session: AsyncSession,
):
    """Trying to DELETE under a source note that isn't mine → 404 (no leak)."""
    user_id = await _user_id_from_headers(client, auth_headers)
    other_user_id = await _user_id_from_headers(client, second_user_headers)

    other_src = await _create_note_for_user(db_session, other_user_id, content="other-src")
    other_tgt = await _create_note_for_user(db_session, other_user_id, content="other-tgt")
    link = NoteLink(
        source_note_id=other_src.id,
        target_note_id=other_tgt.id,
        similarity_score=0.0,
        link_type="manual",
    )
    db_session.add(link)
    await db_session.commit()

    resp = await client.delete(
        f"/api/notes/{other_src.id}/links/{link.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 404, resp.text
