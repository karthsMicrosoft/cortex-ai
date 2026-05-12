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
