"""
test_pipeline_wiki_integration.py — PR 6.5

Verifies AIPipeline.process_note runs parse_and_link_wiki_refs after Stage 2
and tolerates parser failures without failing the whole pipeline.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


def _make_fake_note():
    note = MagicMock()
    note.id = uuid.uuid4()
    note.user_id = uuid.uuid4()
    note.content = "see [[Foo]]"
    note.processing_status = "transcribed"
    note.shadow_reader_status = "skipped"
    note.source_type = "voice"
    note.raw_transcription = "see Foo"
    note.category = "Ideas"
    note.embedding = None
    return note


async def test_process_note_runs_wiki_parser_after_stage2():
    from app.pipeline.processor import AIPipeline

    note = _make_fake_note()
    mock_db = AsyncMock(spec=AsyncSession)
    mock_openai = AsyncMock()

    pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)

    pipeline._stage_capture = AsyncMock(
        side_effect=lambda n: setattr(n, "processing_status", "processed")
    )
    pipeline._stage_organize = AsyncMock(
        side_effect=lambda n: setattr(n, "processing_status", "enriched")
    )

    async def fake_get_note(note_id):
        return note

    pipeline._get_note = fake_get_note

    with patch(
        "app.pipeline.processor.parse_and_link_wiki_refs",
        new=AsyncMock(return_value={
            "resolved": 1,
            "unresolved": 0,
            "links_created": 1,
            "unresolved_titles": [],
        }),
    ) as wiki_mock:
        await pipeline.process_note(note.id)

    wiki_mock.assert_awaited_once()
    args, _ = wiki_mock.call_args
    # signature: parse_and_link_wiki_refs(db, source_note)
    assert args[1] is note


async def test_pipeline_continues_if_wiki_parser_fails():
    from app.pipeline.processor import AIPipeline

    note = _make_fake_note()
    mock_db = AsyncMock(spec=AsyncSession)
    mock_openai = AsyncMock()

    pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)

    pipeline._stage_capture = AsyncMock(
        side_effect=lambda n: setattr(n, "processing_status", "processed")
    )
    pipeline._stage_organize = AsyncMock(
        side_effect=lambda n: setattr(n, "processing_status", "enriched")
    )
    pipeline._mark_failed = AsyncMock()

    async def fake_get_note(note_id):
        return note

    pipeline._get_note = fake_get_note

    with patch(
        "app.pipeline.processor.parse_and_link_wiki_refs",
        new=AsyncMock(side_effect=RuntimeError("wiki parser exploded")),
    ):
        await pipeline.process_note(note.id)

    # Note must still reach 'enriched' — wiki parser failure is not fatal
    assert note.processing_status == "enriched"
    pipeline._mark_failed.assert_not_called()
