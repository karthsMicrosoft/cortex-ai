"""
test_shadow_reader.py — US-8 Shadow Reader (TDD red phase)

Tests for:
  - backend/app/pipeline/shadow_reader.py (trigger logic, question generation, merge)
  - backend/app/api/shadow_reader.py (GET/POST answer/POST dismiss)
  - backend/app/api/users.py (PUT /api/users/me/shadow-reader/settings)
  - backend/app/pipeline/processor.py (B10 ordering: Stage 1.5 runs AFTER Stage 2)

Critical resolutions tested:
  B10 — Stage 1.5 runs AFTER Stage 2 (Organize); gated on
        processing_status='enriched' AND shadow_reader_status='pending'.
  B17 — Polling window: 10×2s + 5×5s (45s window); GET endpoint works before and after.
  Trigger: users.shadow_reader_enabled AND category not in disabled_categories
           AND word_count >= 50.
  Question cap: ≤ 2 questions, each ≤ 15 words.
  merge_answer_into_note: serializable transaction, content append, embedding regen async.

Design refs:
  features/cortex-second-brain/designs/design.md § Pipeline state machine (B10)
  SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md § F2.2, F2.4, F2.5
  us-8-shadow-reader.tasks.md
"""

import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIFTY_WORD_CONTENT = (
    "This is a music note about a D minor melody with a descending bassline "
    "I hummed this morning while thinking about sadness and longing and loss "
    "and also about beauty of melancholy harmony in minor keys."
)
# Exactly verify >= 50 words
assert len(FIFTY_WORD_CONTENT.split()) >= 50, "Test fixture must have >= 50 words"

FORTY_WORD_CONTENT = " ".join(["word"] * 40)
assert len(FORTY_WORD_CONTENT.split()) == 40


def make_fake_note(
    content=FIFTY_WORD_CONTENT,
    category="Music",
    shadow_reader_status="pending",
    processing_status="enriched",
    shadow_reader_questions=None,
    shadow_reader_answer=None,
):
    note = MagicMock()
    note.id = uuid.uuid4()
    note.user_id = uuid.uuid4()
    note.content = content
    note.category = category
    note.shadow_reader_status = shadow_reader_status
    note.processing_status = processing_status
    note.shadow_reader_questions = shadow_reader_questions
    note.shadow_reader_answer = shadow_reader_answer
    note.embedding = [0.1] * 1536
    return note


def make_fake_user(
    shadow_reader_enabled=True,
    shadow_reader_disabled_categories=None,
):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.shadow_reader_enabled = shadow_reader_enabled
    user.shadow_reader_disabled_categories = shadow_reader_disabled_categories or []
    return user


def make_openai_questions_response(questions):
    """Produce a fake OpenAI chat.completions response for question generation."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = json.dumps({"questions": questions})
    return response


def make_openai_embedding_response(dim=1536):
    """Produce a fake OpenAI embeddings response."""
    emb_data = MagicMock()
    emb_data.embedding = [0.9] * dim
    response = MagicMock()
    response.data = [emb_data]
    return response


# ---------------------------------------------------------------------------
# 1. Module imports
# ---------------------------------------------------------------------------


class TestShadowReaderModuleImports:
    def test_shadow_reader_pipeline_module_importable(self):
        import app.pipeline.shadow_reader  # noqa: F401

    def test_should_trigger_shadow_reader_exists(self):
        from app.pipeline.shadow_reader import should_trigger_shadow_reader
        assert callable(should_trigger_shadow_reader)

    def test_generate_questions_exists(self):
        from app.pipeline.shadow_reader import generate_questions
        assert callable(generate_questions)

    def test_run_shadow_reader_stage_exists(self):
        from app.pipeline.shadow_reader import run_shadow_reader_stage
        assert callable(run_shadow_reader_stage)

    def test_merge_answer_into_note_exists(self):
        from app.pipeline.shadow_reader import merge_answer_into_note
        assert callable(merge_answer_into_note)

    def test_category_prompts_dict_exists(self):
        from app.pipeline.shadow_reader import CATEGORY_PROMPTS
        assert isinstance(CATEGORY_PROMPTS, dict)

    def test_min_words_constant_is_50(self):
        from app.pipeline.shadow_reader import MIN_WORDS_FOR_TRIGGER
        assert MIN_WORDS_FOR_TRIGGER == 50

    def test_category_prompts_has_all_six_categories(self):
        from app.pipeline.shadow_reader import CATEGORY_PROMPTS
        required = {"Music", "Journal", "Ideas", "Fitness", "Spiritual", "Learning"}
        assert required.issubset(set(CATEGORY_PROMPTS.keys()))


# ---------------------------------------------------------------------------
# 2. Trigger conditions — should_trigger_shadow_reader
# ---------------------------------------------------------------------------


class TestShouldTriggerShadowReader:
    async def test_triggers_when_all_conditions_met(self):
        from app.pipeline.shadow_reader import should_trigger_shadow_reader
        note = make_fake_note(content=FIFTY_WORD_CONTENT, category="Music")
        user = make_fake_user(shadow_reader_enabled=True)
        result = await should_trigger_shadow_reader(note, user)
        assert result is True

    async def test_no_trigger_when_user_disabled(self):
        from app.pipeline.shadow_reader import should_trigger_shadow_reader
        note = make_fake_note(content=FIFTY_WORD_CONTENT, category="Music")
        user = make_fake_user(shadow_reader_enabled=False)
        result = await should_trigger_shadow_reader(note, user)
        assert result is False

    async def test_no_trigger_when_category_is_disabled(self):
        from app.pipeline.shadow_reader import should_trigger_shadow_reader
        note = make_fake_note(content=FIFTY_WORD_CONTENT, category="Fitness")
        user = make_fake_user(
            shadow_reader_enabled=True,
            shadow_reader_disabled_categories=["Fitness"],
        )
        result = await should_trigger_shadow_reader(note, user)
        assert result is False

    async def test_triggers_for_non_disabled_category_when_others_disabled(self):
        from app.pipeline.shadow_reader import should_trigger_shadow_reader
        note = make_fake_note(content=FIFTY_WORD_CONTENT, category="Music")
        user = make_fake_user(
            shadow_reader_enabled=True,
            shadow_reader_disabled_categories=["Fitness"],
        )
        result = await should_trigger_shadow_reader(note, user)
        assert result is True

    async def test_no_trigger_when_word_count_below_50(self):
        from app.pipeline.shadow_reader import should_trigger_shadow_reader
        note = make_fake_note(content=FORTY_WORD_CONTENT, category="Music")
        user = make_fake_user(shadow_reader_enabled=True)
        result = await should_trigger_shadow_reader(note, user)
        assert result is False

    async def test_triggers_when_word_count_exactly_50(self):
        from app.pipeline.shadow_reader import should_trigger_shadow_reader
        content_50 = " ".join(["word"] * 50)
        note = make_fake_note(content=content_50, category="Journal")
        user = make_fake_user(shadow_reader_enabled=True)
        result = await should_trigger_shadow_reader(note, user)
        assert result is True

    async def test_triggers_when_word_count_above_50(self):
        from app.pipeline.shadow_reader import should_trigger_shadow_reader
        content_100 = " ".join(["word"] * 100)
        note = make_fake_note(content=content_100, category="Ideas")
        user = make_fake_user(shadow_reader_enabled=True)
        result = await should_trigger_shadow_reader(note, user)
        assert result is True

    async def test_no_trigger_when_disabled_categories_is_none_treated_as_empty(self):
        """shadow_reader_disabled_categories=None must be treated as empty list."""
        from app.pipeline.shadow_reader import should_trigger_shadow_reader
        note = make_fake_note(content=FIFTY_WORD_CONTENT, category="Music")
        user = make_fake_user(shadow_reader_enabled=True, shadow_reader_disabled_categories=None)
        result = await should_trigger_shadow_reader(note, user)
        assert result is True

    async def test_all_six_categories_can_trigger(self):
        from app.pipeline.shadow_reader import should_trigger_shadow_reader
        categories = ["Music", "Journal", "Ideas", "Fitness", "Spiritual", "Learning"]
        user = make_fake_user(shadow_reader_enabled=True)
        for cat in categories:
            note = make_fake_note(content=FIFTY_WORD_CONTENT, category=cat)
            result = await should_trigger_shadow_reader(note, user)
            assert result is True, f"Expected trigger for category={cat}"


# ---------------------------------------------------------------------------
# 3. Question generation — generate_questions
# ---------------------------------------------------------------------------


class TestGenerateQuestions:
    async def test_generate_questions_calls_gpt4o_mini(self):
        from app.pipeline.shadow_reader import generate_questions
        note = make_fake_note(category="Music")
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            return_value=make_openai_questions_response(
                ["What emotion does this melody evoke?", "What instrument do you imagine?"]
            )
        )
        await generate_questions(note, mock_openai)
        assert mock_openai.chat.completions.create.called
        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        assert "gpt-4o-mini" in call_kwargs.get("model", "")

    async def test_generate_questions_uses_max_tokens_200(self):
        from app.pipeline.shadow_reader import generate_questions
        note = make_fake_note(category="Journal")
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            return_value=make_openai_questions_response(["What feeling underlies this?"])
        )
        await generate_questions(note, mock_openai)
        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        assert call_kwargs.get("max_tokens") == 200

    async def test_generate_questions_uses_temperature_07(self):
        from app.pipeline.shadow_reader import generate_questions
        note = make_fake_note(category="Ideas")
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            return_value=make_openai_questions_response(["What is the smallest next step?"])
        )
        await generate_questions(note, mock_openai)
        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        assert abs(call_kwargs.get("temperature", 0) - 0.7) < 0.01

    async def test_generate_questions_uses_json_object_response_format(self):
        from app.pipeline.shadow_reader import generate_questions
        note = make_fake_note(category="Fitness")
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            return_value=make_openai_questions_response(["How did your body feel?"])
        )
        await generate_questions(note, mock_openai)
        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        assert call_kwargs.get("response_format") == {"type": "json_object"}

    async def test_generate_questions_caps_at_two(self):
        """Even if LLM returns 3+ questions, the function must return at most 2."""
        from app.pipeline.shadow_reader import generate_questions
        note = make_fake_note(category="Music")
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            return_value=make_openai_questions_response(
                ["Q1?", "Q2?", "Q3?", "Q4?"]  # LLM hallucinated more
            )
        )
        result = await generate_questions(note, mock_openai)
        assert len(result) <= 2

    async def test_generate_questions_returns_list_of_strings(self):
        from app.pipeline.shadow_reader import generate_questions
        note = make_fake_note(category="Spiritual")
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            return_value=make_openai_questions_response(
                ["What presence does this invite?", "What insight arises?"]
            )
        )
        result = await generate_questions(note, mock_openai)
        assert isinstance(result, list)
        assert all(isinstance(q, str) for q in result)

    async def test_generate_questions_filters_to_max_15_words_each(self):
        """Questions longer than 15 words must be filtered out defensively."""
        from app.pipeline.shadow_reader import generate_questions
        note = make_fake_note(category="Learning")
        long_q = " ".join(["word"] * 20)  # 20 words — over limit
        short_q = "What does this connect to for you?"  # ≤ 15 words
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            return_value=make_openai_questions_response([long_q, short_q])
        )
        result = await generate_questions(note, mock_openai)
        for q in result:
            assert len(q.split()) <= 15, f"Question exceeds 15 words: '{q}'"

    async def test_generate_questions_uses_category_specific_prompt(self):
        """The Music category prompt must differ from the Journal category prompt."""
        from app.pipeline.shadow_reader import generate_questions, CATEGORY_PROMPTS
        note_music = make_fake_note(category="Music")
        note_journal = make_fake_note(category="Journal")
        captured_prompts = []

        async def fake_create(**kwargs):
            messages = kwargs.get("messages", [])
            if messages:
                captured_prompts.append(messages[0].get("content", ""))
            return make_openai_questions_response(["Q?"])

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(side_effect=fake_create)

        await generate_questions(note_music, mock_openai)
        await generate_questions(note_journal, mock_openai)

        assert len(captured_prompts) == 2
        assert captured_prompts[0] != captured_prompts[1], (
            "Music and Journal prompts must differ"
        )

    async def test_generate_questions_falls_back_to_ideas_for_unknown_category(self):
        """Unknown category must fall back to CATEGORY_PROMPTS['Ideas']."""
        from app.pipeline.shadow_reader import generate_questions, CATEGORY_PROMPTS
        note = make_fake_note(category="UnknownCategory")
        ideas_prompt = CATEGORY_PROMPTS["Ideas"]
        captured_prompt = []

        async def fake_create(**kwargs):
            messages = kwargs.get("messages", [])
            if messages:
                captured_prompt.append(messages[0].get("content", ""))
            return make_openai_questions_response(["Q?"])

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(side_effect=fake_create)
        await generate_questions(note, mock_openai)

        assert captured_prompt, "create must have been called"
        assert ideas_prompt in captured_prompt[0], (
            "Fallback must use IDEAS prompt for unknown categories"
        )

    async def test_generate_questions_handles_empty_questions_key(self):
        """If LLM returns JSON with empty 'questions' list, return empty list (no crash)."""
        from app.pipeline.shadow_reader import generate_questions
        note = make_fake_note(category="Music")
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            return_value=make_openai_questions_response([])
        )
        result = await generate_questions(note, mock_openai)
        assert isinstance(result, list)
        assert result == []


# ---------------------------------------------------------------------------
# 4. run_shadow_reader_stage — state transitions
# ---------------------------------------------------------------------------


class TestRunShadowReaderStage:
    async def test_stage_sets_status_asked_when_triggered(self):
        from app.pipeline.shadow_reader import run_shadow_reader_stage
        note = make_fake_note(content=FIFTY_WORD_CONTENT, category="Music")
        user = make_fake_user(shadow_reader_enabled=True)
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            return_value=make_openai_questions_response(["What emotion does this evoke?"])
        )
        await run_shadow_reader_stage(note, user, mock_openai, mock_db)
        assert note.shadow_reader_status == "asked"

    async def test_stage_persists_questions_when_asked(self):
        from app.pipeline.shadow_reader import run_shadow_reader_stage
        note = make_fake_note(content=FIFTY_WORD_CONTENT, category="Journal")
        user = make_fake_user(shadow_reader_enabled=True)
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            return_value=make_openai_questions_response(
                ["What feeling is beneath this?", "What do you really need?"]
            )
        )
        await run_shadow_reader_stage(note, user, mock_openai, mock_db)
        assert isinstance(note.shadow_reader_questions, list)
        assert len(note.shadow_reader_questions) >= 1

    async def test_stage_sets_status_skipped_when_not_triggered_user_disabled(self):
        from app.pipeline.shadow_reader import run_shadow_reader_stage
        note = make_fake_note(content=FIFTY_WORD_CONTENT, category="Music")
        user = make_fake_user(shadow_reader_enabled=False)
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()
        await run_shadow_reader_stage(note, user, mock_openai, mock_db)
        assert note.shadow_reader_status == "skipped"

    async def test_stage_sets_status_skipped_when_not_triggered_short_note(self):
        from app.pipeline.shadow_reader import run_shadow_reader_stage
        note = make_fake_note(content=FORTY_WORD_CONTENT, category="Music")
        user = make_fake_user(shadow_reader_enabled=True)
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()
        await run_shadow_reader_stage(note, user, mock_openai, mock_db)
        assert note.shadow_reader_status == "skipped"

    async def test_stage_sets_status_skipped_when_category_disabled(self):
        from app.pipeline.shadow_reader import run_shadow_reader_stage
        note = make_fake_note(content=FIFTY_WORD_CONTENT, category="Fitness")
        user = make_fake_user(
            shadow_reader_enabled=True,
            shadow_reader_disabled_categories=["Fitness"],
        )
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()
        await run_shadow_reader_stage(note, user, mock_openai, mock_db)
        assert note.shadow_reader_status == "skipped"

    async def test_stage_does_not_call_llm_when_skipped(self):
        from app.pipeline.shadow_reader import run_shadow_reader_stage
        note = make_fake_note(content=FORTY_WORD_CONTENT, category="Music")
        user = make_fake_user(shadow_reader_enabled=True)
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock()
        await run_shadow_reader_stage(note, user, mock_openai, mock_db)
        mock_openai.chat.completions.create.assert_not_called()

    async def test_stage_commits_to_db(self):
        from app.pipeline.shadow_reader import run_shadow_reader_stage
        note = make_fake_note(content=FIFTY_WORD_CONTENT, category="Ideas")
        user = make_fake_user(shadow_reader_enabled=True)
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            return_value=make_openai_questions_response(["What is the smallest next step?"])
        )
        await run_shadow_reader_stage(note, user, mock_openai, mock_db)
        mock_db.commit.assert_called()

    async def test_stage_commits_on_skip_too(self):
        from app.pipeline.shadow_reader import run_shadow_reader_stage
        note = make_fake_note(content=FORTY_WORD_CONTENT, category="Music")
        user = make_fake_user(shadow_reader_enabled=True)
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()
        await run_shadow_reader_stage(note, user, mock_openai, mock_db)
        mock_db.commit.assert_called()


# ---------------------------------------------------------------------------
# 5. merge_answer_into_note — B10 serializable transaction
# ---------------------------------------------------------------------------


class TestMergeAnswerIntoNote:
    async def test_appends_reflection_section_to_content(self):
        from app.pipeline.shadow_reader import merge_answer_into_note
        original_content = FIFTY_WORD_CONTENT
        note = make_fake_note(content=original_content, shadow_reader_status="asked")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()
        mock_openai.embeddings.create = AsyncMock(
            return_value=make_openai_embedding_response()
        )
        answer = "It feels melancholy, like rain on glass."
        await merge_answer_into_note(note, answer, mock_openai, mock_db)
        assert "--- Reflection ---" in note.content
        assert answer in note.content
        assert note.content.startswith(original_content)

    async def test_appends_reflection_with_exact_format(self):
        """Exact format: \\n\\n--- Reflection ---\\n{answer}"""
        from app.pipeline.shadow_reader import merge_answer_into_note
        original_content = FIFTY_WORD_CONTENT
        note = make_fake_note(content=original_content, shadow_reader_status="asked")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()
        mock_openai.embeddings.create = AsyncMock(
            return_value=make_openai_embedding_response()
        )
        answer = "It feels melancholy."
        await merge_answer_into_note(note, answer, mock_openai, mock_db)
        expected_suffix = f"\n\n--- Reflection ---\n{answer}"
        assert note.content.endswith(expected_suffix), (
            f"Expected content to end with {repr(expected_suffix)}, got {repr(note.content[-100:])}"
        )

    async def test_sets_shadow_reader_answer(self):
        from app.pipeline.shadow_reader import merge_answer_into_note
        note = make_fake_note(shadow_reader_status="asked")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()
        mock_openai.embeddings.create = AsyncMock(
            return_value=make_openai_embedding_response()
        )
        answer = "Cello with soft piano."
        await merge_answer_into_note(note, answer, mock_openai, mock_db)
        assert note.shadow_reader_answer == answer

    async def test_sets_status_answered(self):
        from app.pipeline.shadow_reader import merge_answer_into_note
        note = make_fake_note(shadow_reader_status="asked")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()
        mock_openai.embeddings.create = AsyncMock(
            return_value=make_openai_embedding_response()
        )
        await merge_answer_into_note(note, "My answer.", mock_openai, mock_db)
        assert note.shadow_reader_status == "answered"

    async def test_regenerates_embedding_using_text_embedding_3_small(self):
        from app.pipeline.shadow_reader import merge_answer_into_note
        note = make_fake_note(shadow_reader_status="asked")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()
        mock_openai.embeddings.create = AsyncMock(
            return_value=make_openai_embedding_response()
        )
        await merge_answer_into_note(note, "My answer.", mock_openai, mock_db)
        assert mock_openai.embeddings.create.called
        call_kwargs = mock_openai.embeddings.create.call_args[1]
        assert "text-embedding-3-small" in call_kwargs.get("model", "")

    async def test_embedding_input_includes_reflection_content(self):
        """Embedding must be generated on the FULL updated content (including reflection)."""
        from app.pipeline.shadow_reader import merge_answer_into_note
        note = make_fake_note(content=FIFTY_WORD_CONTENT, shadow_reader_status="asked")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()
        captured_input = []

        async def fake_embed(**kwargs):
            captured_input.append(kwargs.get("input", ""))
            return make_openai_embedding_response()

        mock_openai.embeddings.create = AsyncMock(side_effect=fake_embed)
        answer = "Cello with soft piano."
        await merge_answer_into_note(note, answer, mock_openai, mock_db)
        assert captured_input, "embeddings.create must have been called"
        assert answer in captured_input[0], (
            "Embedding input must include the reflection answer"
        )

    async def test_commits_to_db(self):
        from app.pipeline.shadow_reader import merge_answer_into_note
        note = make_fake_note(shadow_reader_status="asked")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()
        mock_openai.embeddings.create = AsyncMock(
            return_value=make_openai_embedding_response()
        )
        await merge_answer_into_note(note, "My answer.", mock_openai, mock_db)
        mock_db.commit.assert_called()


# ---------------------------------------------------------------------------
# 6. Pipeline ordering (B10) — Stage 1.5 runs AFTER Stage 2
# ---------------------------------------------------------------------------


class TestB10PipelineOrdering:
    async def test_reflect_runs_after_organize_in_process_note(self):
        """
        process_note must call run_shadow_reader_stage AFTER _stage_organize completes.
        B10 resolution: Stage 1.5 is the LAST stage, after Stage 2.

        The processor uses _stage_reflect_hook which fetches the user then calls
        run_shadow_reader_stage. We patch _stage_reflect_hook directly to track
        call order without needing DB fixtures for the user lookup.
        """
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(
            content=FIFTY_WORD_CONTENT,
            processing_status="transcribed",
            shadow_reader_status="pending",
        )
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        call_order = []

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)

        async def fake_get_note(note_id):
            return note

        async def fake_capture(n):
            call_order.append("capture")
            n.processing_status = "processed"

        async def fake_organize(n):
            call_order.append("organize")
            n.processing_status = "enriched"

        async def fake_reflect_hook(n):
            call_order.append("reflect")

        pipeline._get_note = fake_get_note
        pipeline._stage_capture = fake_capture
        pipeline._stage_organize = fake_organize
        pipeline._stage_reflect_hook = fake_reflect_hook

        await pipeline.process_note(note.id)

        # Verify order: capture → organize → reflect
        assert "organize" in call_order, "organize must be called"
        assert "reflect" in call_order, "_stage_reflect_hook must be called after organize"
        organize_idx = call_order.index("organize")
        reflect_idx = call_order.index("reflect")
        assert organize_idx < reflect_idx, (
            f"Stage 2 (organize at {organize_idx}) must come BEFORE Stage 1.5 "
            f"(reflect at {reflect_idx}) — B10 ordering"
        )

    async def test_reflect_stage_gated_on_enriched_status(self):
        """
        _stage_reflect_hook must only be called when processing_status='enriched'
        AND shadow_reader_status='pending'.
        """
        from app.pipeline.processor import AIPipeline

        note = make_fake_note(
            content=FIFTY_WORD_CONTENT,
            processing_status="transcribed",
            shadow_reader_status="pending",
        )
        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)

        async def fake_get_note(note_id):
            return note

        async def fake_capture(n):
            n.processing_status = "processed"

        async def fake_organize(n):
            n.processing_status = "enriched"

        reflect_mock = AsyncMock()
        pipeline._get_note = fake_get_note
        pipeline._stage_capture = fake_capture
        pipeline._stage_organize = fake_organize
        pipeline._stage_reflect_hook = reflect_mock

        await pipeline.process_note(note.id)

        # By the time reflect hook is called, processing_status must be 'enriched'
        assert note.processing_status == "enriched", (
            "note must have processing_status='enriched' after organize"
        )
        reflect_mock.assert_called_once_with(note)

    async def test_reflect_not_called_when_shadow_reader_status_not_pending(self):
        """
        If shadow_reader_status is already 'asked', 'answered', 'dismissed', or 'skipped',
        _stage_reflect_hook must NOT be called again (idempotent guard).
        """
        from app.pipeline.processor import AIPipeline

        for terminal_status in ["asked", "answered", "dismissed", "skipped"]:
            note = make_fake_note(
                content=FIFTY_WORD_CONTENT,
                processing_status="transcribed",
                shadow_reader_status=terminal_status,
            )
            mock_db = AsyncMock(spec=AsyncSession)
            mock_openai = AsyncMock()

            pipeline = AIPipeline(openai_client=mock_openai, db=mock_db)

            async def fake_get_note(note_id):
                return note

            async def fake_capture(n):
                n.processing_status = "processed"

            async def fake_organize(n):
                n.processing_status = "enriched"

            reflect_mock = AsyncMock()
            pipeline._get_note = fake_get_note
            pipeline._stage_capture = fake_capture
            pipeline._stage_organize = fake_organize
            pipeline._stage_reflect_hook = reflect_mock

            await pipeline.process_note(note.id)

            reflect_mock.assert_not_called(), (
                f"_stage_reflect_hook must NOT be called when "
                f"shadow_reader_status='{terminal_status}'"
            )


# ---------------------------------------------------------------------------
# 7. API endpoints
# ---------------------------------------------------------------------------


class TestShadowReaderAPIModuleImports:
    def test_shadow_reader_api_module_importable(self):
        import app.api.shadow_reader  # noqa: F401

    def test_shadow_reader_api_router_exists(self):
        from app.api.shadow_reader import router
        assert router is not None

    def test_schemas_importable(self):
        import app.schemas.shadow_reader  # noqa: F401

    def test_shadow_reader_answer_schema_exists(self):
        from app.schemas.shadow_reader import ShadowReaderAnswer
        assert ShadowReaderAnswer is not None

    def test_shadow_reader_questions_out_schema_exists(self):
        from app.schemas.shadow_reader import ShadowReaderQuestionsOut
        assert ShadowReaderQuestionsOut is not None

    def test_shadow_reader_settings_schema_exists(self):
        from app.schemas.shadow_reader import ShadowReaderSettings
        assert ShadowReaderSettings is not None


class TestGetShadowReaderEndpoint:
    async def test_get_shadow_reader_requires_auth(self, client):
        note_id = str(uuid.uuid4())
        resp = await client.get(f"/api/notes/{note_id}/shadow-reader")
        assert resp.status_code == 401

    async def test_get_shadow_reader_returns_404_for_unknown_note(self, client, auth_headers):
        note_id = str(uuid.uuid4())
        resp = await client.get(
            f"/api/notes/{note_id}/shadow-reader",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_get_shadow_reader_returns_status_and_questions(self, client, auth_headers, db_session):
        """GET returns {status, questions[]} for a note owned by the user."""
        from app.models.note import Note
        import uuid as _uuid

        user_resp = await client.get("/api/auth/me", headers=auth_headers)
        if user_resp.status_code != 200:
            pytest.skip("Auth/me endpoint not available")
        user_id = _uuid.UUID(user_resp.json()["id"])

        note = Note(
            user_id=user_id,
            content=FIFTY_WORD_CONTENT,
            source_type="text",
            processing_status="enriched",
            shadow_reader_status="asked",
            shadow_reader_questions=["What emotion does this evoke?"],
        )
        db_session.add(note)
        await db_session.flush()
        note_id = str(note.id)

        resp = await client.get(f"/api/notes/{note_id}/shadow-reader", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "questions" in data
        assert data["status"] == "asked"
        assert isinstance(data["questions"], list)

    async def test_get_shadow_reader_returns_pending_status_before_pipeline(
        self, client, auth_headers, db_session
    ):
        """When shadow_reader_status='pending', GET returns status='pending', questions=[]."""
        from app.models.note import Note
        import uuid as _uuid

        user_resp = await client.get("/api/auth/me", headers=auth_headers)
        if user_resp.status_code != 200:
            pytest.skip("Auth/me endpoint not available")
        user_id = _uuid.UUID(user_resp.json()["id"])

        note = Note(
            user_id=user_id,
            content=FIFTY_WORD_CONTENT,
            source_type="text",
            processing_status="transcribed",
            shadow_reader_status="pending",
        )
        db_session.add(note)
        await db_session.flush()

        resp = await client.get(f"/api/notes/{note.id}/shadow-reader", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["questions"] == []

    async def test_get_shadow_reader_does_not_expose_other_users_note(
        self, client, auth_headers, second_user_headers, db_session
    ):
        """GET must return 404 if the note belongs to a different user."""
        from app.models.note import Note
        import uuid as _uuid

        user2_resp = await client.get("/api/auth/me", headers=second_user_headers)
        if user2_resp.status_code != 200:
            pytest.skip("Auth/me endpoint not available")
        user2_id = _uuid.UUID(user2_resp.json()["id"])

        note = Note(
            user_id=user2_id,
            content=FIFTY_WORD_CONTENT,
            source_type="text",
            shadow_reader_status="asked",
            shadow_reader_questions=["Some question?"],
        )
        db_session.add(note)
        await db_session.flush()

        resp = await client.get(f"/api/notes/{note.id}/shadow-reader", headers=auth_headers)
        assert resp.status_code == 404


class TestAnswerShadowReaderEndpoint:
    async def test_answer_requires_auth(self, client):
        note_id = str(uuid.uuid4())
        resp = await client.post(
            f"/api/notes/{note_id}/shadow-reader/answer",
            json={"answer": "My reflection."},
        )
        assert resp.status_code == 401

    async def test_answer_returns_409_when_status_not_asked(self, client, auth_headers, db_session):
        """POST answer returns 409 if shadow_reader_status != 'asked'."""
        from app.models.note import Note
        import uuid as _uuid

        user_resp = await client.get("/api/auth/me", headers=auth_headers)
        if user_resp.status_code != 200:
            pytest.skip("Auth/me endpoint not available")
        user_id = _uuid.UUID(user_resp.json()["id"])

        for bad_status in ["pending", "skipped", "dismissed", "answered"]:
            note = Note(
                user_id=user_id,
                content=FIFTY_WORD_CONTENT,
                source_type="text",
                shadow_reader_status=bad_status,
            )
            db_session.add(note)
            await db_session.flush()

            resp = await client.post(
                f"/api/notes/{note.id}/shadow-reader/answer",
                json={"answer": "My reflection."},
                headers=auth_headers,
            )
            assert resp.status_code == 409, (
                f"Expected 409 when status='{bad_status}', got {resp.status_code}"
            )

    async def test_answer_returns_200_and_schedules_merge(self, client, auth_headers, db_session):
        """POST answer returns 200 immediately; merge runs as background task."""
        from app.models.note import Note
        import uuid as _uuid

        user_resp = await client.get("/api/auth/me", headers=auth_headers)
        if user_resp.status_code != 200:
            pytest.skip("Auth/me endpoint not available")
        user_id = _uuid.UUID(user_resp.json()["id"])

        note = Note(
            user_id=user_id,
            content=FIFTY_WORD_CONTENT,
            source_type="text",
            shadow_reader_status="asked",
            shadow_reader_questions=["What emotion does this evoke?"],
        )
        db_session.add(note)
        await db_session.flush()

        with patch("app.api.shadow_reader.merge_answer_into_note", AsyncMock()):
            resp = await client.post(
                f"/api/notes/{note.id}/shadow-reader/answer",
                json={"answer": "It feels melancholy, like rain on glass."},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") in ("answered", "processing")

    async def test_answer_returns_404_for_unknown_note(self, client, auth_headers):
        note_id = str(uuid.uuid4())
        resp = await client.post(
            f"/api/notes/{note_id}/shadow-reader/answer",
            json={"answer": "My answer."},
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestDismissShadowReaderEndpoint:
    async def test_dismiss_requires_auth(self, client):
        note_id = str(uuid.uuid4())
        resp = await client.post(f"/api/notes/{note_id}/shadow-reader/dismiss")
        assert resp.status_code == 401

    async def test_dismiss_sets_status_dismissed(self, client, auth_headers, db_session):
        from app.models.note import Note
        import uuid as _uuid

        user_resp = await client.get("/api/auth/me", headers=auth_headers)
        if user_resp.status_code != 200:
            pytest.skip("Auth/me endpoint not available")
        user_id = _uuid.UUID(user_resp.json()["id"])

        note = Note(
            user_id=user_id,
            content=FIFTY_WORD_CONTENT,
            source_type="text",
            shadow_reader_status="asked",
            shadow_reader_questions=["What emotion does this evoke?"],
        )
        db_session.add(note)
        await db_session.flush()

        resp = await client.post(
            f"/api/notes/{note.id}/shadow-reader/dismiss",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "dismissed"

    async def test_dismiss_returns_404_for_unknown_note(self, client, auth_headers):
        note_id = str(uuid.uuid4())
        resp = await client.post(
            f"/api/notes/{note_id}/shadow-reader/dismiss",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_dismiss_does_not_affect_other_users_note(
        self, client, auth_headers, second_user_headers, db_session
    ):
        from app.models.note import Note
        import uuid as _uuid

        user2_resp = await client.get("/api/auth/me", headers=second_user_headers)
        if user2_resp.status_code != 200:
            pytest.skip("Auth/me endpoint not available")
        user2_id = _uuid.UUID(user2_resp.json()["id"])

        note = Note(
            user_id=user2_id,
            content=FIFTY_WORD_CONTENT,
            source_type="text",
            shadow_reader_status="asked",
        )
        db_session.add(note)
        await db_session.flush()

        resp = await client.post(
            f"/api/notes/{note.id}/shadow-reader/dismiss",
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestShadowReaderSettingsEndpoint:
    async def test_settings_endpoint_requires_auth(self, client):
        resp = await client.put(
            "/api/users/me/shadow-reader/settings",
            json={"enabled": True, "disabled_categories": []},
        )
        assert resp.status_code == 401

    async def test_settings_endpoint_exists_and_accepts_put(self, client, auth_headers):
        resp = await client.put(
            "/api/users/me/shadow-reader/settings",
            json={"enabled": True, "disabled_categories": []},
            headers=auth_headers,
        )
        assert resp.status_code not in (404, 405), (
            f"PUT /api/users/me/shadow-reader/settings must exist, got {resp.status_code}"
        )

    async def test_settings_enables_shadow_reader(self, client, auth_headers):
        resp = await client.put(
            "/api/users/me/shadow-reader/settings",
            json={"enabled": True, "disabled_categories": []},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    async def test_settings_disables_shadow_reader(self, client, auth_headers):
        resp = await client.put(
            "/api/users/me/shadow-reader/settings",
            json={"enabled": False, "disabled_categories": []},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    async def test_settings_persists_disabled_categories(self, client, auth_headers):
        resp = await client.put(
            "/api/users/me/shadow-reader/settings",
            json={"enabled": True, "disabled_categories": ["Fitness", "Journal"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    async def test_settings_persists_to_db_and_affects_trigger(
        self, client, auth_headers, db_session
    ):
        """
        After disabling shadow reader, run_shadow_reader_stage must see
        shadow_reader_enabled=False on the user and skip.
        Integration-level: disable → verify DB field.
        """
        resp = await client.put(
            "/api/users/me/shadow-reader/settings",
            json={"enabled": False, "disabled_categories": []},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # Read back the user from DB to confirm persistence
        user_resp = await client.get("/api/auth/me", headers=auth_headers)
        if user_resp.status_code != 200:
            pytest.skip("Auth/me endpoint not available")

        import uuid as _uuid
        from app.models.user import User
        from sqlalchemy import select

        user_id = _uuid.UUID(user_resp.json()["id"])
        result = await db_session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is not None:
            assert user.shadow_reader_enabled is False


# ---------------------------------------------------------------------------
# 8. NoteOut schema exposes shadow reader fields
# ---------------------------------------------------------------------------


class TestNoteOutSchemaHasShadowReaderFields:
    def test_note_out_exposes_shadow_reader_status(self):
        try:
            from app.schemas.note import NoteOut
            import inspect
            fields = NoteOut.model_fields if hasattr(NoteOut, "model_fields") else NoteOut.__fields__
            assert "shadow_reader_status" in fields, (
                "NoteOut must expose shadow_reader_status"
            )
        except ImportError:
            pytest.skip("NoteOut schema not yet implemented")

    def test_note_out_exposes_shadow_reader_questions(self):
        try:
            from app.schemas.note import NoteOut
            fields = NoteOut.model_fields if hasattr(NoteOut, "model_fields") else NoteOut.__fields__
            assert "shadow_reader_questions" in fields, (
                "NoteOut must expose shadow_reader_questions"
            )
        except ImportError:
            pytest.skip("NoteOut schema not yet implemented")

    def test_note_out_exposes_shadow_reader_answer(self):
        try:
            from app.schemas.note import NoteOut
            fields = NoteOut.model_fields if hasattr(NoteOut, "model_fields") else NoteOut.__fields__
            assert "shadow_reader_answer" in fields, (
                "NoteOut must expose shadow_reader_answer"
            )
        except ImportError:
            pytest.skip("NoteOut schema not yet implemented")


# ---------------------------------------------------------------------------
# 9. User model exposes shadow reader columns
# ---------------------------------------------------------------------------


class TestUserModelHasShadowReaderColumns:
    def test_user_model_has_shadow_reader_enabled(self):
        try:
            from app.models.user import User
            assert hasattr(User, "shadow_reader_enabled"), (
                "User model must have shadow_reader_enabled column"
            )
        except ImportError:
            pytest.skip("User model not yet implemented")

    def test_user_model_has_shadow_reader_disabled_categories(self):
        try:
            from app.models.user import User
            assert hasattr(User, "shadow_reader_disabled_categories"), (
                "User model must have shadow_reader_disabled_categories column"
            )
        except ImportError:
            pytest.skip("User model not yet implemented")


# ---------------------------------------------------------------------------
# 10. Note model exposes shadow reader columns
# ---------------------------------------------------------------------------


class TestNoteModelHasShadowReaderColumns:
    def test_note_model_has_shadow_reader_status(self):
        try:
            from app.models.note import Note
            assert hasattr(Note, "shadow_reader_status"), (
                "Note model must have shadow_reader_status column"
            )
        except ImportError:
            pytest.skip("Note model not yet implemented")

    def test_note_model_has_shadow_reader_questions(self):
        try:
            from app.models.note import Note
            assert hasattr(Note, "shadow_reader_questions"), (
                "Note model must have shadow_reader_questions column"
            )
        except ImportError:
            pytest.skip("Note model not yet implemented")

    def test_note_model_has_shadow_reader_answer(self):
        try:
            from app.models.note import Note
            assert hasattr(Note, "shadow_reader_answer"), (
                "Note model must have shadow_reader_answer column"
            )
        except ImportError:
            pytest.skip("Note model not yet implemented")


# ---------------------------------------------------------------------------
# 11. Category-specific prompts — spot-check tone / content
# ---------------------------------------------------------------------------


class TestCategoryPromptContent:
    def test_music_prompt_mentions_music_concepts(self):
        from app.pipeline.shadow_reader import CATEGORY_PROMPTS
        prompt = CATEGORY_PROMPTS["Music"].lower()
        # Music prompt should reference musical concepts
        assert any(word in prompt for word in ["music", "instrument", "emotion", "melody"])

    def test_journal_prompt_mentions_reflection(self):
        from app.pipeline.shadow_reader import CATEGORY_PROMPTS
        prompt = CATEGORY_PROMPTS["Journal"].lower()
        assert any(word in prompt for word in ["journal", "feel", "reflect", "deeper", "compassion"])

    def test_ideas_prompt_mentions_development(self):
        from app.pipeline.shadow_reader import CATEGORY_PROMPTS
        prompt = CATEGORY_PROMPTS["Ideas"].lower()
        assert any(word in prompt for word in ["idea", "develop", "clarify", "step", "creative"])

    def test_fitness_prompt_mentions_body_or_performance(self):
        from app.pipeline.shadow_reader import CATEGORY_PROMPTS
        prompt = CATEGORY_PROMPTS["Fitness"].lower()
        assert any(word in prompt for word in ["fitness", "body", "hard", "coach", "next"])

    def test_spiritual_prompt_does_not_specify_religion(self):
        from app.pipeline.shadow_reader import CATEGORY_PROMPTS
        prompt = CATEGORY_PROMPTS["Spiritual"].lower()
        # Must be non-denominational per spec
        assert "religious" not in prompt or "avoid" in prompt or "without" in prompt

    def test_learning_prompt_mentions_knowledge_connection(self):
        from app.pipeline.shadow_reader import CATEGORY_PROMPTS
        prompt = CATEGORY_PROMPTS["Learning"].lower()
        assert any(word in prompt for word in ["learn", "know", "connect", "apply", "teacher"])

    def test_all_prompts_are_nonempty_strings(self):
        from app.pipeline.shadow_reader import CATEGORY_PROMPTS
        for cat, prompt in CATEGORY_PROMPTS.items():
            assert isinstance(prompt, str), f"CATEGORY_PROMPTS['{cat}'] must be a string"
            assert len(prompt.strip()) > 20, f"CATEGORY_PROMPTS['{cat}'] is too short"
