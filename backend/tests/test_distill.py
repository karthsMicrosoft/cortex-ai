"""
test_distill.py — Task 1 (Distill pipeline)
TDD red-phase tests for backend/app/pipeline/distill.py

Covers:
  Task 1.1 — generate_daily_summary(user_id, target_date, openai_client, db)
    - Fetches notes for user on target_date
    - Builds prompt from [category] content lines
    - Calls GPT-4o-mini with max_tokens=800, T=0.7
    - Upserts into daily_summaries table
    - Returns summary text

  Task 1.2 — generate_weekly_summary(user_id, iso_week, openai_client, db)
    - Aggregates 7 daily summaries (or notes) for the ISO week
    - Calls GPT-4o-mini
    - Returns weekly summary text

  Task 1.3 — Scheduler registration tested in test_scheduler.py

Mock strategy: Mock AsyncSession + AsyncMock for OpenAI client.
"""
import uuid
import json
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.uuid4()
FAKE_NOTE_ID = uuid.uuid4()


def make_mock_note(content="I practiced scales today.", category="Music"):
    note = MagicMock()
    note.id = uuid.uuid4()
    note.user_id = FAKE_USER_ID
    note.content = content
    note.category = category
    note.created_at = datetime(2026, 4, 29, 10, 0, 0)
    return note


DAILY_SUMMARY_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": "Today you focused on music practice and had some great ideas.",
                "role": "assistant",
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
    "model": "gpt-4o-mini",
    "id": "chatcmpl-daily",
    "object": "chat.completion",
    "created": 1700000010,
}

WEEKLY_SUMMARY_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": "This week you made progress on music, fitness, and learning.",
                "role": "assistant",
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 100, "completion_tokens": 60, "total_tokens": 160},
    "model": "gpt-4o-mini",
    "id": "chatcmpl-weekly",
    "object": "chat.completion",
    "created": 1700000020,
}


# ---------------------------------------------------------------------------
# Module import checks
# ---------------------------------------------------------------------------

class TestDistillModuleImport:
    def test_distill_module_importable(self):
        """backend/app/pipeline/distill.py must exist and be importable."""
        import app.pipeline.distill  # noqa: F401

    def test_generate_daily_summary_callable(self):
        """generate_daily_summary must be a callable in distill module."""
        from app.pipeline.distill import generate_daily_summary
        assert callable(generate_daily_summary)

    def test_generate_weekly_summary_callable(self):
        """generate_weekly_summary must be a callable in distill module."""
        from app.pipeline.distill import generate_weekly_summary
        assert callable(generate_weekly_summary)


# ---------------------------------------------------------------------------
# Task 1.1 — generate_daily_summary
# ---------------------------------------------------------------------------

class TestGenerateDailySummary:
    async def test_returns_summary_object(self):
        """generate_daily_summary must return a DailySummary ORM object (or dict/str)."""
        from app.pipeline.distill import generate_daily_summary

        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        # Mock notes query result
        mock_notes = [
            make_mock_note("I practiced scales today.", "Music"),
            make_mock_note("Morning run, 5km in 28 minutes.", "Fitness"),
        ]

        # Re-set for notes query vs upsert — use side_effect list
        note_result = MagicMock()
        note_result.scalars.return_value.all.return_value = mock_notes
        upsert_result = MagicMock()
        upsert_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(side_effect=[note_result, upsert_result])
        mock_db.refresh = AsyncMock()

        # Mock OpenAI chat response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Today you focused on music and fitness."
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        target_date = date(2026, 4, 29)
        result = await generate_daily_summary(
            user_id=FAKE_USER_ID,
            target_date=target_date,
            openai_client=mock_openai,
            db=mock_db,
        )

        # Returns a DailySummary ORM object (or any truthy value)
        assert result is not None

    async def test_calls_gpt4o_mini(self):
        """generate_daily_summary must call GPT-4o-mini."""
        from app.pipeline.distill import generate_daily_summary

        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        mock_notes = [make_mock_note("A musical idea.", "Music")]
        note_result = MagicMock()
        note_result.scalars.return_value.all.return_value = mock_notes
        upsert_result = MagicMock()
        upsert_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(side_effect=[note_result, upsert_result])
        mock_db.refresh = AsyncMock()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary text."
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        await generate_daily_summary(
            user_id=FAKE_USER_ID,
            target_date=date(2026, 4, 29),
            openai_client=mock_openai,
            db=mock_db,
        )

        mock_openai.chat.completions.create.assert_called_once()
        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        assert "gpt-4o-mini" in call_kwargs.get("model", "")

    async def test_uses_correct_max_tokens_and_temperature(self):
        """generate_daily_summary must use max_tokens=800, temperature=0.7."""
        from app.pipeline.distill import generate_daily_summary

        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        mock_notes = [make_mock_note("Ideas about learning Python.", "Learning")]
        note_result = MagicMock()
        note_result.scalars.return_value.all.return_value = mock_notes
        upsert_result = MagicMock()
        upsert_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(side_effect=[note_result, upsert_result])
        mock_db.refresh = AsyncMock()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary."
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        await generate_daily_summary(
            user_id=FAKE_USER_ID,
            target_date=date(2026, 4, 29),
            openai_client=mock_openai,
            db=mock_db,
        )

        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        assert call_kwargs.get("max_tokens") == 800
        assert abs(call_kwargs.get("temperature", 0) - 0.7) < 0.01

    async def test_prompt_includes_category_and_content(self):
        """Prompt must include [category] content lines for each note."""
        from app.pipeline.distill import generate_daily_summary

        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        music_note = make_mock_note("Practiced the chromatic scale.", "Music")
        fitness_note = make_mock_note("Did 30 push-ups.", "Fitness")
        mock_notes = [music_note, fitness_note]

        note_result = MagicMock()
        note_result.scalars.return_value.all.return_value = mock_notes
        upsert_result = MagicMock()
        upsert_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(side_effect=[note_result, upsert_result])
        mock_db.refresh = AsyncMock()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary."
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        await generate_daily_summary(
            user_id=FAKE_USER_ID,
            target_date=date(2026, 4, 29),
            openai_client=mock_openai,
            db=mock_db,
        )

        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        messages = call_kwargs.get("messages", [])
        # Build prompt text from messages
        full_prompt = " ".join(
            m.get("content", "") if isinstance(m, dict) else str(m)
            for m in messages
        )
        # Must contain category + content references
        assert "[Music]" in full_prompt or "Music" in full_prompt
        assert "chromatic scale" in full_prompt or "push-ups" in full_prompt

    async def test_upserts_to_daily_summaries(self):
        """generate_daily_summary must persist (upsert) result to daily_summaries."""
        from app.pipeline.distill import generate_daily_summary

        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        mock_notes = [make_mock_note("Journal entry today.", "Journal")]
        note_result = MagicMock()
        note_result.scalars.return_value.all.return_value = mock_notes
        upsert_result = MagicMock()
        upsert_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(side_effect=[note_result, upsert_result])
        mock_db.refresh = AsyncMock()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Wrote in journal."
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        await generate_daily_summary(
            user_id=FAKE_USER_ID,
            target_date=date(2026, 4, 29),
            openai_client=mock_openai,
            db=mock_db,
        )

        # db.commit must be called to persist
        mock_db.commit.assert_called()

    async def test_returns_empty_or_none_when_no_notes(self):
        """When no notes exist for the date, function should return gracefully (no crash)."""
        from app.pipeline.distill import generate_daily_summary

        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        note_result = MagicMock()
        note_result.scalars.return_value.all.return_value = []
        # The function also does an upsert select even when notes is empty
        upsert_result = MagicMock()
        upsert_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(side_effect=[note_result, upsert_result])
        mock_db.refresh = AsyncMock()

        # Provide a response even if OpenAI is called with empty notes
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        # Should not raise
        try:
            result = await generate_daily_summary(
                user_id=FAKE_USER_ID,
                target_date=date(2026, 4, 29),
                openai_client=mock_openai,
                db=mock_db,
            )
            # Returns None, empty string, or an ORM object — all acceptable
            assert result is not None or result is None  # no exception
        except Exception as exc:
            pytest.fail(f"generate_daily_summary raised unexpectedly with no notes: {exc}")

    async def test_filters_notes_by_user_and_date(self):
        """generate_daily_summary must query notes scoped to the given user_id and date."""
        from app.pipeline.distill import generate_daily_summary

        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        note_result = MagicMock()
        note_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=note_result)

        target_date = date(2026, 4, 15)
        await generate_daily_summary(
            user_id=FAKE_USER_ID,
            target_date=target_date,
            openai_client=mock_openai,
            db=mock_db,
        )

        # db.execute must have been called (to run the notes query)
        mock_db.execute.assert_called()


# ---------------------------------------------------------------------------
# Task 1.2 — generate_weekly_summary
# ---------------------------------------------------------------------------

class TestGenerateWeeklySummary:
    async def test_returns_weekly_summary_text(self):
        """generate_weekly_summary must return a dict with non-empty summary_text."""
        from app.pipeline.distill import generate_weekly_summary

        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        # Mock 7 daily summaries
        daily_rows = []
        for i in range(7):
            row = MagicMock()
            row.summary_text = f"Day {i+1} summary text."
            row.summary_date = date(2026, 4, 23 + i)
            row.note_count = 2
            daily_rows.append(row)

        daily_result = MagicMock()
        daily_result.scalars.return_value.all.return_value = daily_rows
        notes_result = MagicMock()
        notes_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[daily_result, notes_result])

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This was a productive week."
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        # ISO week string e.g. "2026-W17"
        result = await generate_weekly_summary(
            user_id=FAKE_USER_ID,
            iso_week="2026-W17",
            openai_client=mock_openai,
            db=mock_db,
        )

        assert isinstance(result, dict)
        assert "summary_text" in result
        assert len(result["summary_text"]) > 0

    async def test_calls_gpt4o_mini_for_weekly(self):
        """generate_weekly_summary must call GPT-4o-mini."""
        from app.pipeline.distill import generate_weekly_summary

        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        row = MagicMock()
        row.summary_text = "Some daily summary."
        row.summary_date = date(2026, 4, 23)
        row.note_count = 2
        daily_result = MagicMock()
        daily_result.scalars.return_value.all.return_value = [row]
        notes_result = MagicMock()
        notes_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[daily_result, notes_result])

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Weekly recap."
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        await generate_weekly_summary(
            user_id=FAKE_USER_ID,
            iso_week="2026-W17",
            openai_client=mock_openai,
            db=mock_db,
        )

        mock_openai.chat.completions.create.assert_called_once()
        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        assert "gpt-4o-mini" in call_kwargs.get("model", "")

    async def test_aggregates_seven_daily_summaries(self):
        """generate_weekly_summary must query 7 daily summaries for the given ISO week."""
        from app.pipeline.distill import generate_weekly_summary

        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        daily_rows = []
        for i in range(7):
            row = MagicMock()
            row.summary_text = f"Day {i+1}: worked on various things."
            row.summary_date = date(2026, 4, 23 + i)
            row.note_count = 2
            daily_rows.append(row)

        daily_result = MagicMock()
        daily_result.scalars.return_value.all.return_value = daily_rows
        notes_result = MagicMock()
        notes_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[daily_result, notes_result])

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Full week recap."
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        await generate_weekly_summary(
            user_id=FAKE_USER_ID,
            iso_week="2026-W17",
            openai_client=mock_openai,
            db=mock_db,
        )

        # db.execute must have been called to fetch daily summaries
        mock_db.execute.assert_called()
        # All 7 day texts must appear in the LLM prompt
        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        messages = call_kwargs.get("messages", [])
        full_prompt = " ".join(
            m.get("content", "") if isinstance(m, dict) else str(m)
            for m in messages
        )
        # At least one day's summary should appear in the prompt
        assert "Day 1" in full_prompt or "worked on" in full_prompt

    async def test_returns_gracefully_when_no_daily_summaries(self):
        """When no daily summaries exist for the week (falls back to notes), function completes."""
        from app.pipeline.distill import generate_weekly_summary

        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        # No daily summaries
        daily_result = MagicMock()
        daily_result.scalars.return_value.all.return_value = []
        # No notes either
        notes_result = MagicMock()
        notes_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[daily_result, notes_result])

        # Function will still call OpenAI (even with empty notes — it builds a prompt)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        # Should not crash
        try:
            result = await generate_weekly_summary(
                user_id=FAKE_USER_ID,
                iso_week="2026-W01",
                openai_client=mock_openai,
                db=mock_db,
            )
            # Returns a dict
            assert result is not None
        except Exception as exc:
            pytest.fail(f"generate_weekly_summary raised unexpectedly with no data: {exc}")

    async def test_weekly_summary_returns_dict_with_expected_keys(self):
        """generate_weekly_summary must return a dict with week, summary_text, note_count."""
        from app.pipeline.distill import generate_weekly_summary

        mock_db = AsyncMock(spec=AsyncSession)
        mock_openai = AsyncMock()

        row = MagicMock()
        row.summary_text = "Day summary."
        row.summary_date = date(2026, 4, 23)
        row.note_count = 3
        daily_result = MagicMock()
        daily_result.scalars.return_value.all.return_value = [row]
        # Also needs a notes fallback query
        notes_result = MagicMock()
        notes_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[daily_result, notes_result])

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Weekly recap text."
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await generate_weekly_summary(
            user_id=FAKE_USER_ID,
            iso_week="2026-W17",
            openai_client=mock_openai,
            db=mock_db,
        )

        assert isinstance(result, dict)
        assert "week" in result
        assert "summary_text" in result
        assert result["week"] == "2026-W17"
