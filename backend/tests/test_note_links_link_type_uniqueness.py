"""
test_note_links_link_type_uniqueness.py — PR 6.0

Verifies that the `note_links` uniqueness constraint is on the triple
(source_note_id, target_note_id, link_type) — NOT on the pair
(source_note_id, target_note_id) as in the original schema.

This allows manual + semantic + wiki links to coexist for the same A->B pair
while still preventing duplicate links of the same type.
"""
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.note import Note
from app.models.note_link import NoteLink
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _make_user_and_two_notes(db_session):
    user = User(
        email=f"link_uq_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        display_name="LinkUQ",
    )
    db_session.add(user)
    await db_session.flush()

    a = Note(user_id=user.id, content="note A content", category="Ideas")
    b = Note(user_id=user.id, content="note B content", category="Ideas")
    db_session.add_all([a, b])
    await db_session.flush()
    return a, b


async def test_can_have_semantic_and_manual_for_same_pair(db_session):
    """A->B with link_type='semantic' AND link_type='manual' must both succeed."""
    a, b = await _make_user_and_two_notes(db_session)
    db_session.add(
        NoteLink(source_note_id=a.id, target_note_id=b.id, similarity_score=0.9, link_type="semantic")
    )
    await db_session.flush()
    db_session.add(
        NoteLink(source_note_id=a.id, target_note_id=b.id, similarity_score=1.0, link_type="manual")
    )
    await db_session.flush()


async def test_can_have_semantic_and_wiki_for_same_pair(db_session):
    a, b = await _make_user_and_two_notes(db_session)
    db_session.add(
        NoteLink(source_note_id=a.id, target_note_id=b.id, similarity_score=0.9, link_type="semantic")
    )
    await db_session.flush()
    db_session.add(
        NoteLink(source_note_id=a.id, target_note_id=b.id, similarity_score=1.0, link_type="wiki")
    )
    await db_session.flush()


async def test_cannot_have_two_semantic_for_same_pair(db_session):
    a, b = await _make_user_and_two_notes(db_session)
    db_session.add(
        NoteLink(source_note_id=a.id, target_note_id=b.id, similarity_score=0.9, link_type="semantic")
    )
    await db_session.flush()
    db_session.add(
        NoteLink(source_note_id=a.id, target_note_id=b.id, similarity_score=0.8, link_type="semantic")
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_cannot_have_two_manual_for_same_pair(db_session):
    a, b = await _make_user_and_two_notes(db_session)
    db_session.add(
        NoteLink(source_note_id=a.id, target_note_id=b.id, similarity_score=1.0, link_type="manual")
    )
    await db_session.flush()
    db_session.add(
        NoteLink(source_note_id=a.id, target_note_id=b.id, similarity_score=1.0, link_type="manual")
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_cannot_have_two_wiki_for_same_pair(db_session):
    a, b = await _make_user_and_two_notes(db_session)
    db_session.add(
        NoteLink(source_note_id=a.id, target_note_id=b.id, similarity_score=1.0, link_type="wiki")
    )
    await db_session.flush()
    db_session.add(
        NoteLink(source_note_id=a.id, target_note_id=b.id, similarity_score=1.0, link_type="wiki")
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()
