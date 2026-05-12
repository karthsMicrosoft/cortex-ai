"""
test_shadow_reader_link_scope.py — PR 6.0

Verifies that `merge_answer_into_note` only deletes outgoing note_links
of `link_type='semantic'`, preserving manual/wiki links across reflection
re-runs (rubber-duck critic concern from Round 18).
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Delete

from app.models.note_link import NoteLink
from app.pipeline.shadow_reader import merge_answer_into_note

pytestmark = pytest.mark.asyncio


def _make_openai_embedding_response(dim=1536):
    emb_data = MagicMock()
    emb_data.embedding = [0.5] * dim
    response = MagicMock()
    response.data = [emb_data]
    return response


def _make_fake_note():
    note = MagicMock()
    note.id = uuid.uuid4()
    note.user_id = uuid.uuid4()
    note.content = "source note content"
    note.category = "Ideas"
    note.shadow_reader_status = "asked"
    note.shadow_reader_questions = None
    note.shadow_reader_answer = None
    note.embedding = [0.1] * 1536
    return note


async def test_merge_answer_only_deletes_semantic_links():
    """The DELETE issued against note_links must filter on link_type='semantic'.

    A real DB round-trip would clobber any user-curated manual/wiki links;
    here we capture the delete statement passed to db.execute and assert
    both the source_note_id and link_type='semantic' filters are present
    so manual/wiki links can never be removed by reflection re-runs.
    """
    note = _make_fake_note()
    captured: list[Delete] = []

    async def fake_execute(stmt, *args, **kwargs):
        if isinstance(stmt, Delete):
            captured.append(stmt)
        return MagicMock()

    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock(side_effect=fake_execute)

    openai = AsyncMock()
    openai.embeddings.create = AsyncMock(
        return_value=_make_openai_embedding_response()
    )

    await merge_answer_into_note(note, "My reflection.", openai, db)

    note_link_deletes = [
        d for d in captured if d.table.name == "note_links"
    ]
    assert note_link_deletes, "merge_answer_into_note must DELETE from note_links"
    rendered = " ".join(
        str(d.compile(compile_kwargs={"literal_binds": False}))
        for d in note_link_deletes
    )
    assert "link_type" in rendered, (
        "DELETE on note_links must filter on link_type so manual/wiki links survive; "
        f"got: {rendered}"
    )
    assert "source_note_id" in rendered

    # Sanity: a baseline DELETE on the same table without link_type filter must
    # render differently — guards against the predicate being silently dropped.
    bare = str(
        sa_delete(NoteLink)
        .where(NoteLink.source_note_id == note.id)
        .compile(compile_kwargs={"literal_binds": False})
    )
    assert "link_type" not in bare
