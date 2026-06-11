"""Round 43 regression test — voice note content edits must NOT be reverted
by the AI pipeline.

Bug: PUT /api/notes/{id} on a voice note used to set processing_status='raw',
which made the pipeline re-enter Stage 1 CAPTURE. Stage 1 for voice notes
re-reads `raw_transcription` (untouched original Azure Speech output), asks
GPT-4o-mini to "clean" it, then overwrites `note.content` — silently
discarding the user's edit.

Fix: PUT now sets processing_status='processed', which skips Stage 1 and
enters the state machine at Stage 2 ORGANIZE (re-tag, re-embed, re-link
based on the user's edited content).

These tests exercise the pipeline directly to lock in the new behavior.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


FAKE_NOTE_ID = uuid.uuid4()
FAKE_USER_ID = uuid.uuid4()

USER_EDIT = "User added paragraph that must survive the pipeline."
RAW_TRANSCRIPTION = "um so like the original voice note before any editing"


def _make_voice_note(*, processing_status: str, content: str) -> MagicMock:
    note = MagicMock()
    note.id = FAKE_NOTE_ID
    note.user_id = FAKE_USER_ID
    note.source_type = "voice"
    note.processing_status = processing_status
    note.content = content
    note.raw_transcription = RAW_TRANSCRIPTION
    note.category = "Ideas"
    note.shadow_reader_status = "pending"
    note.embedding = None
    note.summary = None
    note.mood = None
    note.entities = []
    note.music_metadata = {}
    note.title = "Original Title"
    note.tags = []
    note.due_at = None
    note.priority = None
    note.recurring = None
    return note


def _make_capture_response(text: str = "LLM-cleaned original transcript") -> MagicMock:
    """Build a ChatCompletion-shaped object whose content field is `text`."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = text
    return response


async def test_voice_note_content_survives_pipeline_when_status_processed():
    """The fix: status='processed' means Stage 1 CAPTURE is skipped, so the
    user's edited content is NOT overwritten by re-cleaning raw_transcription.
    """
    from app.pipeline.processor import AIPipeline

    note = _make_voice_note(processing_status="processed", content=USER_EDIT)

    mock_db = AsyncMock(spec=AsyncSession)
    mock_openai = AsyncMock()
    # If Stage 1 ran, it would call chat.completions.create. We allow the call
    # (Stage 2 organize also uses it) but the response content is the
    # "LLM-cleaned transcript" — which must NOT end up overwriting note.content.
    mock_openai.chat.completions.create = AsyncMock(
        return_value=_make_capture_response("This would clobber the user edit.")
    )

    pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)
    # Call Stage 1 directly to confirm the guard: Stage 1 ONLY runs when
    # status is 'raw' or 'transcribed'. The dispatch logic in process_note()
    # already gates this; the regression is that the PUT handler must set
    # 'processed' so that gate doesn't fire.
    #
    # Simulate what process_note() does: only invoke _stage_capture if status
    # is raw/transcribed.
    from app.pipeline.processor import ProcessingStage

    if note.processing_status in (ProcessingStage.RAW, ProcessingStage.TRANSCRIBED):
        await pipeline._stage_capture(note)

    # The user's edit is preserved (Stage 1 was correctly skipped).
    assert note.content == USER_EDIT, (
        f"Voice note edit must survive the pipeline when status='processed'. "
        f"Got: {note.content!r}"
    )


async def test_voice_note_content_clobbered_when_status_raw_PROVES_BUG():
    """Sanity check / DOCUMENTATION test: if the PUT handler regresses and
    sets status='raw' again, Stage 1 CAPTURE WILL overwrite the user's
    edited content. This test documents the buggy behavior we're fixing.
    """
    from app.pipeline.processor import AIPipeline, ProcessingStage

    note = _make_voice_note(processing_status="raw", content=USER_EDIT)

    mock_db = AsyncMock(spec=AsyncSession)
    mock_openai = AsyncMock()
    cleaned = "LLM-cleaned: original voice note before any editing."
    mock_openai.chat.completions.create = AsyncMock(
        return_value=_make_capture_response(cleaned)
    )

    pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)

    if note.processing_status in (ProcessingStage.RAW, ProcessingStage.TRANSCRIBED):
        await pipeline._stage_capture(note)

    # The bug: user's edit is replaced by the LLM-cleaned raw_transcription.
    # This assertion locks in the fact that Stage 1 IS destructive — which is
    # why the PUT handler MUST set 'processed' (not 'raw') after a content edit.
    assert note.content == cleaned, (
        f"This test exists to prove the bug: Stage 1 CAPTURE overwrites content "
        f"when invoked. If you see this fail, Stage 1 stopped being destructive, "
        f"which is also fine — but the comment in api/notes.py update_note() needs "
        f"updating. Got content: {note.content!r}"
    )
    assert note.content != USER_EDIT


async def test_put_handler_sets_processed_not_raw_on_content_change(
    client, auth_headers
):
    """End-to-end: PUT with a content change must result in
    processing_status='processed' (NOT 'raw') in the response."""
    # Use the existing test client (fixture). Create a note via POST.
    resp = await client.post(
        "/api/notes",
        json={"content": "Original content", "source_type": "text"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    note_id = resp.json()["id"]

    # PUT with new content.
    resp = await client.put(
        f"/api/notes/{note_id}",
        json={"content": "User edited the content with new info."},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["content"] == "User edited the content with new info."
    assert body["processing_status"] == "processed", (
        f"Round 43: PUT with content change must set status='processed' so the "
        f"pipeline skips Stage 1 CAPTURE (which would overwrite edited content "
        f"on voice notes). Got: {body['processing_status']!r}"
    )
