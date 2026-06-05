import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

FAKE_NOTE_ID = uuid.uuid4()
FAKE_USER_ID = uuid.uuid4()
LLM_DUE_AT = "2026-07-15T14:00:00+00:00"


def make_note(content, *, due_at=None, priority=None, recurring=None):
    note = MagicMock()
    note.id = FAKE_NOTE_ID
    note.user_id = FAKE_USER_ID
    note.content = content
    note.processing_status = "processed"
    note.source_type = "text"
    note.category = "Ideas"
    note.mood = None
    note.summary = None
    note.entities = []
    note.title = None
    note.tags = []
    note.due_at = due_at
    note.priority = priority
    note.recurring = recurring
    return note


def make_pipeline_response(*, due_at=LLM_DUE_AT, priority=None, recurring=None):
    payload = {
        "title": "Task note",
        "tags": [],
        "category": "Ideas",
        "mood": "neutral",
        "summary": "Summary.",
        "entities": [],
        "due_at": due_at,
        "priority": priority,
        "recurring": recurring,
    }
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = json.dumps(payload)
    return response


async def run_auto_tag(note, response):
    from app.pipeline.processor import AIPipeline

    mock_db = AsyncMock(spec=AsyncSession)
    mock_openai = AsyncMock()
    mock_openai.chat.completions.create = AsyncMock(return_value=response)

    pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)
    await pipeline._auto_tag_and_categorize(note)
    return mock_openai


async def test_regex_due_at_is_not_overwritten_by_llm():
    note = make_note("Submit by tomorrow")
    response = make_pipeline_response(due_at=LLM_DUE_AT)

    await run_auto_tag(note, response)

    assert note.due_at is not None
    assert note.due_at != datetime.fromisoformat(LLM_DUE_AT)


async def test_llm_due_at_fills_when_regex_misses():
    note = make_note("remind me when I land")
    response = make_pipeline_response(due_at=LLM_DUE_AT)

    await run_auto_tag(note, response)

    assert note.due_at == datetime.fromisoformat(LLM_DUE_AT)


async def test_existing_due_at_hint_is_not_overwritten():
    hinted_due_at = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
    note = make_note("Submit by tomorrow", due_at=hinted_due_at)
    response = make_pipeline_response(due_at=LLM_DUE_AT)

    await run_auto_tag(note, response)

    assert note.due_at == hinted_due_at
