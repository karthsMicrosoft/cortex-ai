import uuid

import pytest
from sqlalchemy import select

from app.models.note import Note
from app.models.note_link import NoteLink
from app.models.tag import Tag, note_tags
from app.models.user import User
from app.services import semantic_links
from app.services.semantic_links import (
    RelinkResult,
    composite_score,
    passes_floor,
    rebuild_user_links,
    relink_single_note,
    tag_jaccard,
    title_jaccard,
)


@pytest.fixture(autouse=True)
def clear_relink_rate_limit():
    semantic_links._last_run.clear()
    yield
    semantic_links._last_run.clear()


def test_tag_jaccard_empty_both_zero():
    assert tag_jaccard(set(), set()) == 0.0


def test_tag_jaccard_disjoint_zero():
    assert tag_jaccard({"a", "b"}, {"c", "d"}) == 0.0


def test_tag_jaccard_identical_one():
    assert tag_jaccard({"a", "b"}, {"a", "b"}) == 1.0


def test_tag_jaccard_partial():
    assert tag_jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)


def test_title_jaccard_empty_or_none_zero():
    assert title_jaccard(None, "hello") == 0.0
    assert title_jaccard("", "hello") == 0.0
    assert title_jaccard("hello", None) == 0.0
    assert title_jaccard("hello", "") == 0.0


def test_title_jaccard_stopwords_removed():
    assert title_jaccard("the cat in the hat", "a cat with a hat") == 1.0


def test_title_jaccard_partial():
    assert title_jaccard("morning run stats", "evening run report") == pytest.approx(1 / 5)


def test_composite_score_weights():
    assert composite_score(sem=1, tag=1, title=1) == 1.0
    assert composite_score(sem=0, tag=0, title=0) == 0.0
    assert composite_score(sem=1, tag=0, title=0) == pytest.approx(0.7)


def test_passes_floor_semantic_anchor():
    assert passes_floor(sem=0.7, tag=0.0, title=0.0) is True


def test_passes_floor_tag_anchor():
    assert passes_floor(sem=0.0, tag=0.5, title=0.0) is True


def test_passes_floor_title_anchor():
    assert passes_floor(sem=0.0, tag=0.0, title=0.5) is True


def test_passes_floor_below_all():
    assert passes_floor(sem=0.3, tag=0.3, title=0.3) is False


def _embedding_for_db(db_session):
    dialect = db_session.get_bind().dialect.name
    if dialect == "postgresql":
        return [0.1] * 1536
    return "[0.1]"


async def _make_user(db_session):
    user = User(
        email=f"semantic_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        display_name="Semantic",
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_note(db_session, user, *, title="Note", tags=None, embedding=None):
    note = Note(
        user_id=user.id,
        content=title or "content",
        title=title,
        category="Ideas",
        embedding=embedding,
    )
    db_session.add(note)
    await db_session.flush()

    for tag_name in tags or []:
        existing = await db_session.execute(
            select(Tag).where(Tag.user_id == user.id, Tag.name == tag_name)
        )
        tag = existing.scalar_one_or_none()
        if tag is None:
            tag = Tag(user_id=user.id, name=tag_name, is_auto=True)
            db_session.add(tag)
            await db_session.flush()
        await db_session.execute(
            note_tags.insert().values(note_id=note.id, tag_id=tag.id)
        )
    await db_session.flush()
    return note


async def _links_for_source(db_session, source_id):
    result = await db_session.execute(
        select(NoteLink).where(
            NoteLink.source_note_id == source_id,
            NoteLink.link_type == "semantic",
        )
    )
    return result.scalars().all()


@pytest.mark.asyncio
async def test_relink_single_note_no_embedding_returns_empty(db_session):
    user = await _make_user(db_session)
    note = await _make_note(db_session, user, title="Source", embedding=None)

    result = await relink_single_note(db_session, note)

    assert result == RelinkResult()


@pytest.mark.asyncio
async def test_relink_single_note_semantic_peer_creates_link(db_session, monkeypatch):
    user = await _make_user(db_session)
    embedding = _embedding_for_db(db_session)
    source = await _make_note(db_session, user, title="Source", embedding=embedding)
    peer = await _make_note(db_session, user, title="Peer", embedding=embedding)

    async def fake_candidates(db, note, **kwargs):
        return [{"id": peer.id, "title": peer.title, "sem": 0.9}]

    monkeypatch.setattr(semantic_links, "_fetch_vector_candidates", fake_candidates)

    result = await relink_single_note(db_session, source)
    links = await _links_for_source(db_session, source.id)

    assert result.created == 1
    assert result.updated == 0
    assert len(links) == 1
    assert links[0].target_note_id == peer.id
    assert links[0].similarity_score == pytest.approx(0.63)


@pytest.mark.asyncio
async def test_relink_single_note_only_floor_passing_peer_linked(db_session, monkeypatch):
    user = await _make_user(db_session)
    embedding = _embedding_for_db(db_session)
    source = await _make_note(db_session, user, title="Source", tags=["shared"], embedding=embedding)
    floor_peer = await _make_note(db_session, user, title="Floor peer", tags=["shared"], embedding=embedding)
    no_floor_peer = await _make_note(db_session, user, title="No floor peer", embedding=embedding)

    async def fake_candidates(db, note, **kwargs):
        return [
            {"id": floor_peer.id, "title": floor_peer.title, "sem": 0.4},
            {"id": no_floor_peer.id, "title": no_floor_peer.title, "sem": 0.4},
        ]

    monkeypatch.setattr(semantic_links, "_fetch_vector_candidates", fake_candidates)

    result = await relink_single_note(db_session, source, sem_threshold=0.2)
    links = await _links_for_source(db_session, source.id)

    assert result.created == 1
    assert {link.target_note_id for link in links} == {floor_peer.id}


@pytest.mark.asyncio
async def test_relink_single_note_rerun_upserts_updates_existing(db_session, monkeypatch):
    user = await _make_user(db_session)
    embedding = _embedding_for_db(db_session)
    source = await _make_note(db_session, user, title="Source", embedding=embedding)
    peer = await _make_note(db_session, user, title="Peer", embedding=embedding)
    sem_value = 0.9

    async def fake_candidates(db, note, **kwargs):
        return [{"id": peer.id, "title": peer.title, "sem": sem_value}]

    monkeypatch.setattr(semantic_links, "_fetch_vector_candidates", fake_candidates)

    first = await relink_single_note(db_session, source)
    sem_value = 0.95
    second = await relink_single_note(db_session, source)
    links = await _links_for_source(db_session, source.id)

    assert first.created == 1
    assert first.updated == 0
    assert second.created == 0
    assert second.updated == 1
    assert len(links) == 1
    assert links[0].similarity_score == pytest.approx(0.665)


@pytest.mark.asyncio
async def test_rebuild_user_links_rate_limit_skips_recent_run(db_session):
    user = await _make_user(db_session)

    first = await rebuild_user_links(db_session, user.id)
    second = await rebuild_user_links(db_session, user.id)

    assert first.skipped_recent is False
    assert second.skipped_recent is True
    assert second.duration_ms == 0


@pytest.mark.asyncio
async def test_rebuild_user_links_empty_notes_zero_counters(db_session):
    user = await _make_user(db_session)

    result = await rebuild_user_links(db_session, user.id)

    assert result.created == 0
    assert result.updated == 0
    assert result.skipped_recent is False
