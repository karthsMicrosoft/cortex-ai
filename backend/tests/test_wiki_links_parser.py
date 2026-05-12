"""
test_wiki_links_parser.py — PR 6.5

Tests for backend/app/pipeline/wiki_links.py::parse_and_link_wiki_refs.

The parser:
  - Extracts [[Title]] refs from note.content
  - Resolves each ref to a note in the same user's collection by either
    title (case-insensitive) or aliases (case-insensitive)
  - Creates a note_links row with link_type='wiki' for unique resolutions
  - Counts ambiguous (>1 match) refs as unresolved (NOT picking newest)
  - Excludes the source note itself
  - Excludes notes belonging to other users
  - Is idempotent (running twice does not create duplicate links)
"""
import uuid

import pytest
from sqlalchemy import select

from app.models.note import Note
from app.models.note_link import NoteLink
from app.models.user import User
from app.pipeline.wiki_links import parse_and_link_wiki_refs

pytestmark = pytest.mark.asyncio


async def _make_user(db_session, email_prefix="wiki"):
    user = User(
        email=f"{email_prefix}_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        display_name="Wiki Test",
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_note(db_session, user, *, content="body", title=None, aliases=None):
    note = Note(
        user_id=user.id,
        content=content,
        category="Ideas",
        title=title,
        aliases=aliases or [],
    )
    db_session.add(note)
    await db_session.flush()
    return note


async def _count_wiki_links(db_session, source_id):
    rows = (
        await db_session.execute(
            select(NoteLink).where(
                NoteLink.source_note_id == source_id,
                NoteLink.link_type == "wiki",
            )
        )
    ).scalars().all()
    return rows


async def test_parse_no_refs(db_session):
    user = await _make_user(db_session)
    src = await _make_note(db_session, user, content="just plain text, no refs here")
    result = await parse_and_link_wiki_refs(db_session, src)
    assert result["resolved"] == 0
    assert result["unresolved"] == 0
    assert result["links_created"] == 0
    assert result["unresolved_titles"] == []


async def test_parse_single_resolved(db_session):
    user = await _make_user(db_session)
    target = await _make_note(db_session, user, title="Foo", content="target body")
    src = await _make_note(db_session, user, content="see [[Foo]] for context")
    result = await parse_and_link_wiki_refs(db_session, src)
    assert result["resolved"] == 1
    assert result["links_created"] == 1
    assert result["unresolved"] == 0
    links = await _count_wiki_links(db_session, src.id)
    assert len(links) == 1
    assert links[0].target_note_id == target.id
    assert links[0].link_type == "wiki"


async def test_parse_alias_match(db_session):
    user = await _make_user(db_session)
    target = await _make_note(
        db_session, user, title="Real Title", aliases=["Foo"], content="t"
    )
    src = await _make_note(db_session, user, content="check [[Foo]]")
    result = await parse_and_link_wiki_refs(db_session, src)
    assert result["resolved"] == 1
    assert result["links_created"] == 1
    links = await _count_wiki_links(db_session, src.id)
    assert len(links) == 1
    assert links[0].target_note_id == target.id


async def test_parse_case_insensitive(db_session):
    user = await _make_user(db_session)
    target = await _make_note(db_session, user, title="foo", content="t")
    src = await _make_note(db_session, user, content="ref [[FOO]] here")
    result = await parse_and_link_wiki_refs(db_session, src)
    assert result["resolved"] == 1
    assert result["links_created"] == 1
    links = await _count_wiki_links(db_session, src.id)
    assert links[0].target_note_id == target.id


async def test_parse_unresolved(db_session):
    user = await _make_user(db_session)
    src = await _make_note(db_session, user, content="orphan ref [[Nonexistent]]")
    result = await parse_and_link_wiki_refs(db_session, src)
    assert result["resolved"] == 0
    assert result["unresolved"] == 1
    assert result["links_created"] == 0
    assert "Nonexistent" in result["unresolved_titles"]
    links = await _count_wiki_links(db_session, src.id)
    assert links == []


async def test_parse_ambiguous_two_matches_unresolved(db_session):
    user = await _make_user(db_session)
    await _make_note(db_session, user, title="Dup", content="A")
    await _make_note(db_session, user, title="Dup", content="B")
    src = await _make_note(db_session, user, content="ambiguous [[Dup]]")
    result = await parse_and_link_wiki_refs(db_session, src)
    assert result["resolved"] == 0
    assert result["unresolved"] == 1
    assert result["links_created"] == 0
    assert "Dup" in result["unresolved_titles"]
    links = await _count_wiki_links(db_session, src.id)
    assert links == []


async def test_parse_idempotent(db_session):
    user = await _make_user(db_session)
    target = await _make_note(db_session, user, title="Foo", content="t")
    src = await _make_note(db_session, user, content="see [[Foo]]")
    r1 = await parse_and_link_wiki_refs(db_session, src)
    r2 = await parse_and_link_wiki_refs(db_session, src)
    assert r1["links_created"] == 1
    assert r2["links_created"] == 0  # already exists
    assert r2["resolved"] == 1
    links = await _count_wiki_links(db_session, src.id)
    assert len(links) == 1


async def test_parse_self_reference_excluded(db_session):
    user = await _make_user(db_session)
    src = await _make_note(
        db_session, user, title="Self Title", content="self ref [[Self Title]]"
    )
    result = await parse_and_link_wiki_refs(db_session, src)
    assert result["links_created"] == 0
    links = await _count_wiki_links(db_session, src.id)
    assert links == []


async def test_parse_multiple_refs_in_one_note(db_session):
    user = await _make_user(db_session)
    a = await _make_note(db_session, user, title="Alpha", content="a")
    b = await _make_note(db_session, user, title="Beta", content="b")
    c = await _make_note(db_session, user, title="Gamma", content="c")
    src = await _make_note(
        db_session,
        user,
        content="refs: [[Alpha]] then [[Beta]] then [[Gamma]] done",
    )
    result = await parse_and_link_wiki_refs(db_session, src)
    assert result["resolved"] == 3
    assert result["links_created"] == 3
    links = await _count_wiki_links(db_session, src.id)
    target_ids = {lk.target_note_id for lk in links}
    assert target_ids == {a.id, b.id, c.id}


async def test_parse_other_users_notes_excluded(db_session):
    user1 = await _make_user(db_session, "u1")
    user2 = await _make_user(db_session, "u2")
    # The match candidate belongs to a different user
    await _make_note(db_session, user2, title="Foo", content="other")
    src = await _make_note(db_session, user1, content="see [[Foo]]")
    result = await parse_and_link_wiki_refs(db_session, src)
    assert result["resolved"] == 0
    assert result["unresolved"] == 1
    assert "Foo" in result["unresolved_titles"]
    links = await _count_wiki_links(db_session, src.id)
    assert links == []
