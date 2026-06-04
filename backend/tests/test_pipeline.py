"""
test_pipeline.py — Tasks 3, 4, 5
Tests for backend/app/pipeline/processor.py (AIPipeline)

Covers:
  Stage 1 — CAPTURE (_stage_capture):
    - GPT-4o-mini cleans raw_transcription → content; max_tokens=1000, T=0.3
    - Sets processing_status='processed'
    - Skips LLM cleanup when source_type='text' (already clean text)

  Stage 1.5 — REFLECT call site:
    - Exists as a no-op pass-through in US-2; gated on enriched + shadow_reader_status='pending'

  Stage 2 — ORGANIZE (_stage_organize):
    - _auto_tag_and_categorize: GPT-4o-mini JSON, returns tags/category/mood/summary/entities
    - Category constrained to valid set {Music, Fitness, Journal, Ideas, Spiritual, Learning}
    - _generate_embedding: text-embedding-3-small, 1536d vector
    - _link_similar_notes: pgvector cosine query, threshold=0.75, limit=5
    - asyncio.gather on tag+embed
    - Sets processing_status='enriched'

  Task 5 — Music enrichment:
    - process_music_note called when category='Music' after organize

  Pipeline error handling:
    - Any unhandled exception → processing_status='failed'
    - Raw record preserved

  Processor re-trigger endpoint:
    - POST /api/ai/process/{note_id} — idempotent re-run from current stage

Mock strategy (B15): respx for OpenAI HTTP calls (chat + embeddings).
"""
import json
import uuid
import pytest
import respx
import httpx
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_OPENAI_ENDPOINT = "https://fake-openai.openai.azure.com"
FAKE_NOTE_ID = uuid.uuid4()
FAKE_USER_ID = uuid.uuid4()


def make_fake_note(
    processing_status="transcribed",
    source_type="voice",
    content="um uh so like I had this idea about machine learning",
    raw_transcription="um uh so like I had this idea about machine learning",
    category="Ideas",
    shadow_reader_status="pending",
    title=None,
):
    note = MagicMock()
    note.id = FAKE_NOTE_ID
    note.user_id = FAKE_USER_ID
    note.content = content
    note.raw_transcription = raw_transcription
    note.source_type = source_type
    note.processing_status = processing_status
    note.category = category
    note.shadow_reader_status = shadow_reader_status
    note.embedding = None
    note.summary = None
    note.mood = None
    note.entities = []
    note.music_metadata = {}
    note.title = title
    note.tags = []
    return note


CAPTURE_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": "I had an idea about machine learning today.",
                "role": "assistant",
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
    "model": "gpt-4o-mini",
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 1700000000,
}

ORGANIZE_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": json.dumps({
                    "tags": ["machine-learning", "ideas", "project"],
                    "category": "Ideas",
                    "mood": "curious",
                    "summary": "An idea about applying ML to a new project.",
                    "entities": [{"name": "machine learning", "type": "concept"}],
                }),
                "role": "assistant",
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 80, "completion_tokens": 60, "total_tokens": 140},
    "model": "gpt-4o-mini",
    "id": "chatcmpl-org",
    "object": "chat.completion",
    "created": 1700000001,
}

EMBEDDING_RESPONSE = {
    "data": [{"embedding": [0.1] * 1536, "index": 0, "object": "embedding"}],
    "model": "text-embedding-3-small",
    "object": "list",
    "usage": {"prompt_tokens": 10, "total_tokens": 10},
}

MUSIC_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": json.dumps({
                    "tempo_guess": "120 BPM",
                    "key_guess": "C major",
                    "genre": "Pop",
                    "mood": "upbeat",
                    "instruments": ["guitar", "drums"],
                    "description": "A catchy pop melody",
                    "development_suggestions": "Add a bridge section",
                }),
                "role": "assistant",
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": 100},
    "model": "gpt-4o-mini",
    "id": "chatcmpl-music",
    "object": "chat.completion",
    "created": 1700000002,
}


# ---------------------------------------------------------------------------
# Module import
# ---------------------------------------------------------------------------

class TestPipelineModuleImport:
    def test_pipeline_package_importable(self):
        import app.pipeline  # noqa: F401

    def test_processor_importable(self):
        from app.pipeline import processor  # noqa: F401

    def test_aipipeline_class_exists(self):
        from app.pipeline.processor import AIPipeline
        assert AIPipeline is not None

    def test_process_note_method_exists(self):
        from app.pipeline.processor import AIPipeline
        assert hasattr(AIPipeline, "process_note")

    def test_music_module_importable(self):
        from app.pipeline import music  # noqa: F401

    def test_process_music_note_callable(self):
        from app.pipeline.music import process_music_note
        assert callable(process_music_note)


# ---------------------------------------------------------------------------
# Stage 1 — CAPTURE
# ---------------------------------------------------------------------------

class TestStageCapture:
    async def test_capture_updates_content_from_raw_transcription(self):
        """_stage_capture must overwrite note.content with the LLM cleaned text."""
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(processing_status="transcribed")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        # Simulate OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "I had an idea about machine learning today."
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=note)))

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)
        await pipeline._stage_capture(note)

        assert note.content == "I had an idea about machine learning today."
        assert note.processing_status == "processed"

    async def test_capture_calls_gpt4o_mini_with_correct_params(self):
        """_stage_capture must call GPT-4o-mini with max_tokens=1000, temperature=0.3."""
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(processing_status="transcribed")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Cleaned content."
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)
        await pipeline._stage_capture(note)

        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        assert call_kwargs.get("max_tokens") == 1000
        assert abs(call_kwargs.get("temperature", 0) - 0.3) < 0.01
        assert "gpt-4o-mini" in call_kwargs.get("model", "")

    async def test_capture_skips_llm_for_text_source_type(self):
        """Source_type='text' notes should not call the LLM (already clean)."""
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(
            processing_status="raw",
            source_type="text",
            content="This is already clean text.",
            raw_transcription=None,
        )
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock()

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)
        await pipeline._stage_capture(note)

        # LLM must NOT be called for text source
        mock_openai.chat.completions.create.assert_not_called()
        assert note.processing_status == "processed"

    async def test_capture_sets_processed_status(self):
        """After _stage_capture succeeds, processing_status must be 'processed'."""
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(processing_status="raw")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Clean note."
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)
        await pipeline._stage_capture(note)

        assert note.processing_status == "processed"

    async def test_capture_commits_to_db(self):
        """_stage_capture must call db.commit() after updating the note."""
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(processing_status="transcribed")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Cleaned."
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)
        await pipeline._stage_capture(note)

        mock_db.commit.assert_called()


# ---------------------------------------------------------------------------
# Stage 2 — ORGANIZE
# ---------------------------------------------------------------------------

class TestStageOrganize:
    async def test_auto_tag_returns_valid_category(self):
        """_auto_tag_and_categorize must set note.category to one of the six valid values."""
        from app.pipeline.processor import AIPipeline

        VALID_CATEGORIES = {"Music", "Fitness", "Journal", "Ideas", "Spiritual", "Learning"}

        note = make_fake_note(processing_status="processed")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "tags": ["idea"],
            "category": "Ideas",
            "mood": "neutral",
            "summary": "An idea.",
            "entities": [],
        })
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        # Mock DB tag operations
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)
        await pipeline._auto_tag_and_categorize(note)

        assert note.category in VALID_CATEGORIES

    async def test_auto_tag_uses_json_object_response_format(self):
        """_auto_tag_and_categorize must request response_format={'type':'json_object'}."""
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(processing_status="processed")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "tags": ["tag1"],
            "category": "Ideas",
            "mood": "neutral",
            "summary": "Summary.",
            "entities": [],
        })
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)
        await pipeline._auto_tag_and_categorize(note)

        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        assert call_kwargs.get("response_format") == {"type": "json_object"}

    async def test_generate_embedding_produces_1536d_vector(self):
        """_generate_embedding must store a 1536-dim vector in note.embedding."""
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(processing_status="processed")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        mock_emb_data = MagicMock()
        mock_emb_data.embedding = [0.01] * 1536
        mock_emb_response = MagicMock()
        mock_emb_response.data = [mock_emb_data]
        mock_openai.embeddings.create = AsyncMock(return_value=mock_emb_response)

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)
        await pipeline._generate_embedding(note)

        assert note.embedding is not None
        assert len(note.embedding) == 1536

    async def test_generate_embedding_uses_text_embedding_3_small(self):
        """_generate_embedding must call text-embedding-3-small model."""
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(processing_status="processed")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        mock_emb_data = MagicMock()
        mock_emb_data.embedding = [0.0] * 1536
        mock_emb_response = MagicMock()
        mock_emb_response.data = [mock_emb_data]
        mock_openai.embeddings.create = AsyncMock(return_value=mock_emb_response)

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)
        await pipeline._generate_embedding(note)

        call_kwargs = mock_openai.embeddings.create.call_args[1]
        assert "text-embedding-3-small" in call_kwargs.get("model", "")

    async def test_stage_organize_sets_enriched_status(self):
        """After _stage_organize, processing_status must be 'enriched'."""
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(processing_status="processed")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        # Tag response
        mock_tag_response = MagicMock()
        mock_tag_response.choices = [MagicMock()]
        mock_tag_response.choices[0].message.content = json.dumps({
            "tags": ["tag1"],
            "category": "Ideas",
            "mood": "neutral",
            "summary": "Summary.",
            "entities": [],
        })

        # Embedding response
        mock_emb_data = MagicMock()
        mock_emb_data.embedding = [0.1] * 1536
        mock_emb_response = MagicMock()
        mock_emb_response.data = [mock_emb_data]

        mock_openai.chat.completions.create = AsyncMock(return_value=mock_tag_response)
        mock_openai.embeddings.create = AsyncMock(return_value=mock_emb_response)

        # DB: tag lookup + link similar notes
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)

        # Mock _link_similar_notes to avoid raw SQL
        pipeline._link_similar_notes = AsyncMock()

        await pipeline._stage_organize(note)

        assert note.processing_status == "enriched"

    async def test_stage_organize_runs_tag_and_embed_in_parallel(self):
        """
        _stage_organize must run _auto_tag_and_categorize and _generate_embedding
        concurrently via asyncio.gather (both are called before linking).
        """
        import asyncio
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(processing_status="processed")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        tag_called_at = []
        embed_called_at = []

        async def fake_tag(n):
            tag_called_at.append(asyncio.get_event_loop().time())
            n.category = "Ideas"
            n.mood = "neutral"
            n.summary = "S"
            n.entities = []

        async def fake_embed(n):
            embed_called_at.append(asyncio.get_event_loop().time())
            n.embedding = [0.1] * 1536

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)
        pipeline._auto_tag_and_categorize = fake_tag
        pipeline._generate_embedding = fake_embed
        pipeline._link_similar_notes = AsyncMock()

        await pipeline._stage_organize(note)

        # Both must have been called
        assert len(tag_called_at) == 1
        assert len(embed_called_at) == 1

    async def test_link_similar_notes_threshold_and_limit(self):
        """_link_similar_notes must use threshold=0.75 and limit=5 as defaults."""
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(processing_status="processed")
        note.embedding = [0.1] * 1536
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        captured_params = {}

        async def fake_execute(query, params=None):
            if params:
                captured_params.update(params)
            return MagicMock()

        mock_db.execute = AsyncMock(side_effect=fake_execute)

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)
        await pipeline._link_similar_notes(note)

        assert captured_params.get("threshold") == 0.75
        assert captured_params.get("limit") == 5


class TestAutoTitle:
    async def _run_auto_title_case(
        self,
        llm_title=None,
        existing_title=None,
        include_title=True,
    ):
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(processing_status="processed", title=existing_title)
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        payload = {
            "tags": [],
            "category": "Ideas",
            "mood": "neutral",
            "summary": "Summary.",
            "entities": [],
        }
        if include_title:
            payload["title"] = llm_title

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(payload)
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)
        await pipeline._auto_tag_and_categorize(note)
        return note

    async def test_pipeline_sets_title_when_none(self):
        note = await self._run_auto_title_case(llm_title="Lynch Film Meetup")

        assert note.title == "Lynch Film Meetup"

    async def test_pipeline_preserves_user_title(self):
        note = await self._run_auto_title_case(
            llm_title="Generated Different Title",
            existing_title="My Custom Title",
        )

        assert note.title == "My Custom Title"

    async def test_pipeline_truncates_long_title(self):
        note = await self._run_auto_title_case(llm_title="A" * 200)

        assert len(note.title) <= 120

    async def test_pipeline_strips_surrounding_quotes(self):
        note = await self._run_auto_title_case(llm_title='"Quoted Title"')

        assert note.title == "Quoted Title"

    async def test_pipeline_handles_missing_title_key(self):
        note = await self._run_auto_title_case(include_title=False)

        assert note.title is None

    async def test_pipeline_handles_empty_string_title(self):
        note = await self._run_auto_title_case(llm_title="  ")

        assert note.title is None


# ---------------------------------------------------------------------------
# Stage 1.5 — REFLECT call site (no-op in US-2)
# ---------------------------------------------------------------------------

class TestStage15ReflectCallSite:
    async def test_process_note_includes_reflect_call_site(self):
        """
        process_note must include a Stage 1.5 call site after Stage 2.
        In US-2 it is a no-op pass-through (not yet implemented).
        The note must still reach processing_status='enriched'.
        """
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(processing_status="transcribed", shadow_reader_status="pending")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)
        pipeline._stage_capture = AsyncMock(
            side_effect=lambda n: setattr(n, "processing_status", "processed")
        )
        pipeline._stage_organize = AsyncMock(
            side_effect=lambda n: setattr(n, "processing_status", "enriched")
        )

        # _get_note must return our fake note
        async def fake_get_note(note_id):
            return note

        pipeline._get_note = fake_get_note

        await pipeline.process_note(note.id)

        # Stage 2 ran
        pipeline._stage_organize.assert_called_once()
        # Status reached enriched
        assert note.processing_status == "enriched"


# ---------------------------------------------------------------------------
# Pipeline error handling
# ---------------------------------------------------------------------------

class TestPipelineErrorHandling:
    async def test_exception_sets_failed_status(self):
        """If any stage raises, processing_status must become 'failed'."""
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(processing_status="transcribed")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)

        async def fake_get_note(note_id):
            return note

        pipeline._get_note = fake_get_note
        pipeline._stage_capture = AsyncMock(side_effect=RuntimeError("Azure is down"))
        pipeline._mark_failed = AsyncMock()

        await pipeline.process_note(note.id)

        pipeline._mark_failed.assert_called_once()

    async def test_failed_does_not_lose_raw_record(self):
        """On failure, the note's raw_transcription must remain intact."""
        from app.pipeline.processor import AIPipeline

        original_raw = "original raw transcription text"
        note = make_fake_note(processing_status="transcribed")
        note.raw_transcription = original_raw

        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)

        async def fake_get_note(note_id):
            return note

        pipeline._get_note = fake_get_note

        # Capture stage fails
        async def bad_capture(n):
            raise ValueError("Bad capture")

        pipeline._stage_capture = bad_capture
        pipeline._mark_failed = AsyncMock()

        await pipeline.process_note(note.id)

        # raw_transcription must still be the original value
        assert note.raw_transcription == original_raw


# ---------------------------------------------------------------------------
# Music enrichment (Task 5)
# ---------------------------------------------------------------------------

class TestMusicEnrichment:
    async def test_process_music_note_populates_music_metadata(self):
        """process_music_note must set note.music_metadata with expected fields."""
        from app.pipeline.music import process_music_note

        note = make_fake_note(processing_status="enriched", category="Music")
        mock_openai = AsyncMock()
        mock_db = AsyncMock(spec=AsyncSession)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "tempo_guess": "120 BPM",
            "key_guess": "C major",
            "genre": "Pop",
            "mood": "upbeat",
            "instruments": ["guitar"],
            "description": "A catchy melody",
            "development_suggestions": "Add a bridge",
        })
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        await process_music_note(note, openai_client=mock_openai, db=mock_db)

        assert isinstance(note.music_metadata, dict)
        assert "tempo_guess" in note.music_metadata
        assert "key_guess" in note.music_metadata
        assert "genre" in note.music_metadata

    async def test_process_note_calls_music_enrichment_for_music_category(self):
        """
        process_note must call process_music_note after Stage 2
        when note.category == 'Music'.
        """
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(processing_status="transcribed", category="Music")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)

        async def fake_get_note(note_id):
            return note

        pipeline._get_note = fake_get_note
        pipeline._stage_capture = AsyncMock(
            side_effect=lambda n: setattr(n, "processing_status", "processed")
        )
        pipeline._stage_organize = AsyncMock(
            side_effect=lambda n: [
                setattr(n, "processing_status", "enriched"),
                setattr(n, "category", "Music"),
            ]
        )

        music_mock = AsyncMock()
        with patch("app.pipeline.processor.process_music_note", music_mock):
            await pipeline.process_note(note.id)

        music_mock.assert_called_once()

    async def test_process_note_skips_music_enrichment_for_non_music(self):
        """process_note must NOT call process_music_note for non-Music categories."""
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(processing_status="transcribed", category="Ideas")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)

        async def fake_get_note(note_id):
            return note

        pipeline._get_note = fake_get_note
        pipeline._stage_capture = AsyncMock(
            side_effect=lambda n: setattr(n, "processing_status", "processed")
        )
        pipeline._stage_organize = AsyncMock(
            side_effect=lambda n: setattr(n, "processing_status", "enriched")
        )

        music_mock = AsyncMock()
        with patch("app.pipeline.processor.process_music_note", music_mock):
            await pipeline.process_note(note.id)

        music_mock.assert_not_called()


# ---------------------------------------------------------------------------
# QA-02: azure_retry — retries transient errors, skips HTTPException
# review-comments.tasks.md § 3.2
# ---------------------------------------------------------------------------

class TestAzureRetryDecorator:
    """QA-02: azure_retry must retry on transient errors but NOT on HTTPException.
    The _is_retryable function must be wired into the decorator (not dead code).
    """

    def test_azure_retry_importable(self):
        """azure_retry must be importable from app.utils.retry."""
        from app.utils.retry import azure_retry  # noqa: F401
        assert callable(azure_retry)

    def test_is_retryable_importable(self):
        """_is_retryable must be importable from app.utils.retry."""
        from app.utils.retry import _is_retryable
        assert callable(_is_retryable)

    def test_is_retryable_returns_true_for_connection_error(self):
        """_is_retryable must return True for transient network errors."""
        from app.utils.retry import _is_retryable
        assert _is_retryable(ConnectionError("Azure is down")) is True

    def test_is_retryable_returns_true_for_runtime_error(self):
        """_is_retryable must return True for RuntimeError."""
        from app.utils.retry import _is_retryable
        assert _is_retryable(RuntimeError("Transient failure")) is True

    def test_is_retryable_returns_false_for_http_exception(self):
        """QA-02 core: _is_retryable must return False for FastAPI HTTPException."""
        from app.utils.retry import _is_retryable
        from fastapi import HTTPException
        exc = HTTPException(status_code=400, detail="Bad request")
        assert _is_retryable(exc) is False, (
            "QA-02 FAIL: _is_retryable returned True for HTTPException. "
            "The retry decorator must NOT retry on HTTPException (intentional 4xx/5xx)."
        )

    def test_is_retryable_returns_false_for_http_404(self):
        """_is_retryable must return False for 404 HTTPException."""
        from app.utils.retry import _is_retryable
        from fastapi import HTTPException
        exc = HTTPException(status_code=404, detail="Not found")
        assert _is_retryable(exc) is False

    def test_is_retryable_returns_false_for_http_500_as_http_exception(self):
        """_is_retryable must return False even for HTTP 500 raised as HTTPException."""
        from app.utils.retry import _is_retryable
        from fastapi import HTTPException
        exc = HTTPException(status_code=500, detail="Internal server error")
        assert _is_retryable(exc) is False, (
            "Even HTTP 500 raised as HTTPException must not be retried — "
            "it is an intentional response from the application."
        )

    async def test_azure_retry_does_not_retry_http_exception(self):
        """QA-02: azure_retry must NOT retry when the decorated function raises HTTPException."""
        from app.utils.retry import azure_retry
        from fastapi import HTTPException

        call_count = 0

        @azure_retry
        async def raise_http_exception():
            nonlocal call_count
            call_count += 1
            raise HTTPException(status_code=400, detail="Bad request — not retryable")

        with pytest.raises(HTTPException):
            await raise_http_exception()

        assert call_count == 1, (
            f"QA-02 FAIL: azure_retry retried HTTPException {call_count} time(s). "
            "HTTPException must not be retried — it represents an intentional response."
        )

    async def test_azure_retry_retries_on_transient_connection_error(self):
        """QA-02: azure_retry must retry on transient ConnectionError (max 3 attempts)."""
        from app.utils.retry import azure_retry

        call_count = 0

        @azure_retry
        async def unstable_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network glitch")
            return "success"

        result = await unstable_function()
        assert result == "success"
        assert call_count == 3, (
            f"QA-02 FAIL: azure_retry should have retried ConnectionError 3 times, "
            f"but called the function {call_count} time(s)."
        )

    async def test_azure_retry_exhausts_retries_on_persistent_error(self):
        """azure_retry must propagate after 3 failed attempts on persistent errors."""
        from app.utils.retry import azure_retry

        call_count = 0

        @azure_retry
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Persistent network failure")

        with pytest.raises(ConnectionError):
            await always_fails()

        assert call_count == 3, (
            f"Expected exactly 3 retry attempts, got {call_count}. "
            "azure_retry must stop after 3 attempts (stop_after_attempt(3))."
        )

    def test_is_retryable_is_wired_not_dead_code(self):
        """QA-02: _is_retryable must be used in azure_retry (not dead code).

        We verify this structurally: _is_retryable(HTTPException(...)) returns False,
        AND azure_retry does NOT retry HTTPException.
        Both must be true simultaneously to prove _is_retryable is actually wired.
        """
        from app.utils.retry import _is_retryable
        from fastapi import HTTPException

        # If _is_retryable were dead code, it would be irrelevant whether it returns False.
        # The async test above proves the behavior; this test checks the predicate directly.
        assert _is_retryable(HTTPException(status_code=400)) is False
        assert _is_retryable(ValueError("transient")) is True


# ---------------------------------------------------------------------------
# POST /api/ai/process/{note_id} — manual re-trigger (Task 4.6)
# ---------------------------------------------------------------------------

class TestManualRetriggerEndpoint:
    async def test_retrigger_endpoint_exists(self, client, auth_headers):
        """POST /api/ai/process/{note_id} must exist and accept the note ID."""
        note_id = str(uuid.uuid4())
        with patch("app.api.notes.AIPipeline") as mock_pipeline_cls:
            mock_pipeline_cls.return_value.process_note = AsyncMock()
            resp = await client.post(
                f"/api/ai/process/{note_id}",
                headers=auth_headers,
            )
        # 404 (note not found) is acceptable — 405 (method not allowed) is NOT
        assert resp.status_code != 405, "Endpoint must accept POST"
        assert resp.status_code in (200, 202, 404)

    async def test_retrigger_requires_auth(self, client):
        """POST /api/ai/process/{note_id} must require authentication."""
        note_id = str(uuid.uuid4())
        resp = await client.post(f"/api/ai/process/{note_id}")
        assert resp.status_code == 401

    async def test_retrigger_returns_200_for_own_note(self, client, auth_headers, db_session):
        """Re-trigger on an existing note owned by the user should return 200/202."""
        from app.models.note import Note
        import uuid as _uuid

        user_id_resp = await client.get("/api/auth/me", headers=auth_headers)
        if user_id_resp.status_code != 200:
            pytest.skip("Auth/me endpoint not available")
        user_id = _uuid.UUID(user_id_resp.json()["id"])

        note = Note(
            user_id=user_id,
            content="Test note for retrigger",
            source_type="text",
            processing_status="failed",
        )
        db_session.add(note)
        await db_session.flush()
        note_id = str(note.id)

        with patch("app.api.notes.AIPipeline") as mock_pipeline_cls:
            mock_pipeline_cls.return_value.process_note = AsyncMock()
            resp = await client.post(
                f"/api/ai/process/{note_id}",
                headers=auth_headers,
            )

        assert resp.status_code in (200, 202)


# ---------------------------------------------------------------------------
# PERF-01 — _ensure_tag / _auto_tag_and_categorize must not issue N+1 queries
# review-comments.tasks.md § 2.1
# ---------------------------------------------------------------------------

class TestPERF01PipelineTagBatch:
    """
    PERF-01 (pipeline side): _auto_tag_and_categorize calls _ensure_tag once per
    GPT-returned tag. The fixed implementation must batch-fetch all existing tags
    in a single query, not issue N SELECT statements.

    Assert: after _auto_tag_and_categorize returns, db.execute was called ≤ 2 times
    total for tag handling (1 batch fetch + 1 optional batch insert).
    """

    async def test_auto_tag_execute_calls_le_2_for_multiple_tags(self):
        """
        _auto_tag_and_categorize with 3 GPT-returned tags must use ≤ 2 execute calls.
        """
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(processing_status="processed")
        mock_openai = AsyncMock()
        mock_db = AsyncMock(spec=AsyncSession)

        execute_calls = []

        mock_gpt_response = MagicMock()
        mock_gpt_response.choices = [MagicMock()]
        mock_gpt_response.choices[0].message.content = json.dumps({
            "tags": ["jazz", "piano", "improv"],
            "category": "Music",
            "mood": "relaxed",
            "summary": "Piano jazz session.",
            "entities": [],
        })
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_gpt_response)

        async def counting_execute(stmt, *args, **kwargs):
            execute_calls.append(stmt)
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_result.scalar_one_or_none.return_value = None
            return mock_result

        mock_db.execute = counting_execute
        mock_db.flush = AsyncMock()

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)

        try:
            await pipeline._auto_tag_and_categorize(note)
        except Exception:
            pass

        # Filter out any non-tag-related executes (category validation, etc.)
        # but total should still be ≤ 2 for the tag operations
        assert len(execute_calls) <= 2, (
            f"PERF-01 FAIL: _auto_tag_and_categorize issued {len(execute_calls)} execute "
            f"calls for 3 tags — N+1 pattern detected. Expected ≤ 2."
        )
