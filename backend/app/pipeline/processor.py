"""
AI Pipeline orchestrator — CODE framework.

Public interface:
    pipeline = AIPipeline(openai_client, db)
    await pipeline.process_note(note_id)

Pipeline state machine (B10 — Stage 2 before Stage 1.5):
    raw | transcribed  → [Stage 1 CAPTURE]  → processed
    processed          → [Stage 2 ORGANIZE] → enriched
    enriched / pending → [Stage 1.5 hook]   → enriched / asked|skipped (US-8)

Failure: any exception → processing_status='failed'; raw record preserved.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from openai import AsyncAzureOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.note import Note
from app.pipeline.music import process_music_note
from app.pipeline.shadow_reader import run_shadow_reader_stage
from app.pipeline.wiki_links import parse_and_link_wiki_refs
from app.services.deadline_extractor import extract as extract_deadline
from app.services.semantic_links import relink_single_note
from app.utils.db_helpers import get_or_create_tags_batch

logger = logging.getLogger(__name__)


def _note_field_is_empty(note: Note, field_name: str) -> bool:
    value = getattr(note, field_name, None)
    if value is None:
        return True
    if field_name == "due_at":
        return not isinstance(value, datetime)
    if field_name == "priority":
        return not isinstance(value, int) or isinstance(value, bool)
    if field_name == "recurring":
        return not isinstance(value, str) or not value.strip()
    return False


def _parse_llm_due_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_llm_priority(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        priority = int(value)
    except (TypeError, ValueError):
        return None
    return priority if priority in {1, 2, 3} else None


def _parse_llm_recurring(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    recurring = value.strip().lower()
    return recurring if recurring in {"daily", "weekly", "monthly"} else None


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ProcessingStage(str, Enum):
    RAW = "raw"
    TRANSCRIBED = "transcribed"
    PROCESSED = "processed"
    ENRICHED = "enriched"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class AIPipeline:
    """Event-driven AI processing pipeline implementing the CODE framework."""

    def __init__(self, openai_client: AsyncAzureOpenAI, db: AsyncSession) -> None:
        self.openai = openai_client
        self.db = db

    # -----------------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------------

    async def process_note(self, note_id: uuid.UUID) -> None:
        """Orchestrate Stage 1 → Stage 2 → Stage 1.5 hook for *note_id*.

        On any unhandled exception: sets processing_status='failed' and logs
        the error class (no note content logged).
        """
        note: Optional[Note] = None
        try:
            note = await self._get_note(note_id)
            if note is None:
                logger.error("Pipeline: note %s not found", note_id)
                return

            # Stage 1 — CAPTURE: clean raw transcription
            if note.processing_status in (
                ProcessingStage.RAW,
                ProcessingStage.TRANSCRIBED,
            ):
                await self._stage_capture(note)

            # Stage 2 — ORGANIZE: tag + embed + link
            if note.processing_status == ProcessingStage.PROCESSED:
                await self._stage_organize(note)

            # Phase 6 / PR 6.5 — Wiki-link parsing. Runs after Stage 2 so the
            # note is enriched (status committed) but BEFORE music enrichment
            # / Stage 1.5 hook. Failures are logged + swallowed so wiki-link
            # extraction never fails the whole pipeline.
            if note.processing_status == ProcessingStage.ENRICHED:
                try:
                    await parse_and_link_wiki_refs(self.db, note)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "pipeline_wiki_links_failed: note_id=%s error_class=%s",
                        note.id,
                        type(exc).__name__,
                    )

            # Music enrichment — called from process_note (not _stage_organize) so it
            # can be patched at the processor module level in tests.
            if note.processing_status == ProcessingStage.ENRICHED and note.category == "Music":
                try:
                    await process_music_note(note, self.openai, self.db)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "pipeline_music_enrichment_failed: note_id=%s error_class=%s",
                        note.id,
                        type(exc).__name__,
                    )

            # Stage 1.5 — REFLECT hook (US-8 fills in; no-op pass-through for US-2)
            if (
                note.processing_status == ProcessingStage.ENRICHED
                and note.shadow_reader_status == "pending"
            ):
                await self._stage_reflect_hook(note)

            logger.info("pipeline_stage_complete: all note_id=%s", note_id)

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "pipeline_failed: note_id=%s error_class=%s",
                note_id,
                type(exc).__name__,
            )
            await self._mark_failed(note_id)

    # -----------------------------------------------------------------------
    # Stage 1 — CAPTURE
    # -----------------------------------------------------------------------

    async def _stage_capture(self, note: Note) -> None:
        """Clean raw transcription via GPT-4o-mini → note.content.

        Prompt from spec § 2.5 verbatim.
        Skipped for source_type='text' (content already clean).
        """
        if note.source_type in ("text", "image"):
            # Text notes are already clean; image notes have OCR-extracted text
            # written directly to note.content during the OCR step. Either way,
            # there is no raw_transcription to clean — skip LLM cleanup and
            # advance status straight to PROCESSED. (Bug 14 fix 2026-05-01:
            # previously image notes hit the empty-raw_transcription guard
            # below and were wrongly marked 'failed' with "(no speech detected)".)
            note.processing_status = ProcessingStage.PROCESSED
            await self.db.commit()
            logger.info("pipeline_stage_complete: capture(skip) note_id=%s", note.id)
            return

        # Bug 6 fix (2026-05-01): if raw_transcription is empty/blank (Azure
        # Speech returned NoMatch — silence, language mismatch, corrupt audio),
        # the prompt below would resolve to "Raw transcription:\n\n" and
        # GPT-4o-mini answers "Sure! Please provide the raw voice note you
        # would like me to clean and structure." We never want that text in
        # the user's note content. Bail early with a clear marker and a
        # 'failed' status so the UI can surface the issue.
        raw_text = (note.raw_transcription or "").strip()
        if not raw_text:
            note.content = "(no speech detected — please re-record)"
            note.processing_status = ProcessingStage.FAILED
            await self.db.commit()
            logger.warning(
                "pipeline_stage_capture: empty raw_transcription on voice note %s",
                note.id,
            )
            return

        prompt = (
            "You are a personal knowledge assistant. Clean and structure this raw voice note.\n"
            "Rules:\n"
            "- Fix grammar and remove filler words (um, uh, like)\n"
            "- Preserve the original meaning and tone\n"
            "- Format into clear paragraphs\n"
            "- If it is a list, format as bullet points\n"
            "- Keep it concise but complete\n\n"
            f"Raw transcription:\n{raw_text}\n\n"
            "Return ONLY the cleaned text, nothing else."
        )

        response = await self.openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3,
        )

        cleaned = (response.choices[0].message.content or "").strip()
        # Defensive: if the LLM still produced an empty response (rare but
        # possible) keep the raw transcription rather than blanking the note.
        note.content = cleaned or raw_text
        note.processing_status = ProcessingStage.PROCESSED
        await self.db.commit()
        logger.info("pipeline_stage_complete: capture note_id=%s", note.id)

    # -----------------------------------------------------------------------
    # Stage 2 — ORGANIZE
    # -----------------------------------------------------------------------

    async def _stage_organize(self, note: Note) -> None:
        """Auto-tag + embed in parallel, then link similar notes → 'enriched'."""
        # Run tagging and embedding concurrently
        await asyncio.gather(
            self._auto_tag_and_categorize(note),
            self._generate_embedding(note),
        )
        # Link similar notes after embedding is available
        await self._link_similar_notes(note)

        note.processing_status = ProcessingStage.ENRICHED
        await self.db.commit()
        logger.info("pipeline_stage_complete: organize note_id=%s", note.id)

    async def _auto_tag_and_categorize(self, note: Note) -> None:
        """GPT-4o-mini JSON: extract note and task metadata."""
        extracted = extract_deadline(
            note.content or "",
            now=datetime.now(tz=timezone.utc),
            tz="UTC",
        )
        if extracted:
            if extracted.get("due_at") is not None and _note_field_is_empty(note, "due_at"):
                note.due_at = extracted["due_at"]
            if extracted.get("priority") is not None and _note_field_is_empty(note, "priority"):
                note.priority = extracted["priority"]
            if extracted.get("recurring") is not None and _note_field_is_empty(note, "recurring"):
                note.recurring = extracted["recurring"]

        prompt = (
            "Analyze this note and return a JSON object with:\n"
            "- title: a short meaningful 3-8 word title that captures the essence\n"
            "  (e.g. \"Film Meetup notes on Lynch debate\"). NO surrounding quotes.\n"
            "- tags: array of 3-5 relevant tags (lowercase, hyphenated)\n"
            "- category: exactly one of: Music, Fitness, Journal, Ideas, Spiritual, Learning\n"
            "- mood: emotional tone (single word or short phrase)\n"
            "- summary: 1-2 sentence summary\n"
            "- entities: array of {name, type} objects\n"
            "- due_at: ISO 8601 string with offset, or null. Capture fuzzy deadlines "
            "(\"when I land\", \"before our trip\", \"after lunch\").\n"
            "- priority: 1 (high), 2 (medium), 3 (low), or null\n"
            "- recurring: \"daily\", \"weekly\", or \"monthly\", or null\n\n"
            f"Note content:\n{note.content}\n\nReturn ONLY valid JSON."
        )

        response = await self.openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        result: dict = json.loads(response.choices[0].message.content or "{}")

        # Validate category
        valid_categories = {"Music", "Fitness", "Journal", "Ideas", "Spiritual", "Learning"}
        category = result.get("category", "Ideas")
        if category not in valid_categories:
            category = "Ideas"

        note.category = category
        note.mood = result.get("mood") or None
        note.summary = result.get("summary") or None
        note.entities = result.get("entities") or []

        if _note_field_is_empty(note, "due_at"):
            llm_due_at = _parse_llm_due_at(result.get("due_at"))
            if llm_due_at is not None:
                note.due_at = llm_due_at

        if _note_field_is_empty(note, "priority"):
            llm_priority = _parse_llm_priority(result.get("priority"))
            if llm_priority is not None:
                note.priority = llm_priority

        if _note_field_is_empty(note, "recurring"):
            llm_recurring = _parse_llm_recurring(result.get("recurring"))
            if llm_recurring is not None:
                note.recurring = llm_recurring

        raw_title = (result.get("title") or "").strip()
        if raw_title.startswith('"') and raw_title.endswith('"'):
            raw_title = raw_title[1:-1].strip()
        if raw_title and len(raw_title) > 120:
            raw_title = raw_title[:120]
        if raw_title and not (note.title and note.title.strip()):
            note.title = raw_title

        # Persist tags — batch upsert (PERF-01: replaces per-tag N+1 loop)
        tag_names = [
            tag_name.strip().lower()
            for tag_name in result.get("tags", [])
            if isinstance(tag_name, str) and tag_name.strip()
        ]
        if tag_names:
            new_tags = await get_or_create_tags_batch(
                self.db, note.user_id, tag_names, is_auto=True
            )
            for tag in new_tags:
                if tag not in note.tags:
                    note.tags.append(tag)

    async def _generate_embedding(self, note: Note) -> None:
        """Generate 1536-dim embedding via text-embedding-3-small."""
        response = await self.openai.embeddings.create(
            model="text-embedding-3-small",
            input=note.content,
        )
        note.embedding = response.data[0].embedding

    async def _link_similar_notes(
        self,
        note: Note,
        threshold: float = 0.75,
        limit: int = 5,
    ) -> None:
        """Insert/update note_links for semantically similar notes.

        Uses cosine similarity via pgvector. Falls back gracefully when embedding
        is not available or pgvector is not installed (e.g., SQLite tests).
        """
        if note.embedding is None:
            return

        try:
            await relink_single_note(
                self.db,
                note,
                top_n=limit,
                sem_threshold=threshold,
            )
        except Exception as exc:  # noqa: BLE001
            # pgvector not available in SQLite test env — skip gracefully
            logger.debug("_link_similar_notes skipped: %s", type(exc).__name__)

    # -----------------------------------------------------------------------
    # Stage 1.5 — REFLECT (US-8)
    # -----------------------------------------------------------------------

    async def _stage_reflect_hook(self, note: Note) -> None:
        """Stage 1.5: Shadow Reader — generate follow-up questions.

        Gate (checked by caller): processing_status=='enriched' AND
        shadow_reader_status=='pending'.

        Fetches the note's owner to check shadow_reader_enabled /
        shadow_reader_disabled_categories before delegating to
        run_shadow_reader_stage.
        """
        from app.models.user import User

        result = await self.db.execute(
            select(User).where(User.id == note.user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            logger.error(
                "shadow_reader: user %s not found for note %s",
                note.user_id,
                note.id,
            )
            note.shadow_reader_status = "skipped"
            await self.db.commit()
            return

        await run_shadow_reader_stage(note, user, self.openai, self.db)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    async def _get_note(self, note_id: uuid.UUID) -> Optional[Note]:
        """Fetch note by id with tags eagerly loaded."""
        result = await self.db.execute(
            select(Note)
            .options(selectinload(Note.tags))
            .where(Note.id == note_id)
        )
        return result.scalar_one_or_none()

    async def _ensure_tag(self, note: Note, name: str, is_auto: bool = True) -> None:
        """Get or create a Tag and associate it with *note*.

        Delegates to get_or_create_tags_batch for single-tag use.
        Kept for backward compatibility; batch callers use get_or_create_tags_batch directly.
        """
        tags = await get_or_create_tags_batch(
            self.db, note.user_id, [name], is_auto=is_auto
        )
        for tag in tags:
            if tag not in note.tags:
                note.tags.append(tag)

    async def _mark_failed(self, note_id: uuid.UUID) -> None:
        """Set processing_status='failed' for *note_id*. Preserves all other fields."""
        try:
            result = await self.db.execute(select(Note).where(Note.id == note_id))
            note = result.scalar_one_or_none()
            if note is not None:
                note.processing_status = ProcessingStage.FAILED
                await self.db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "pipeline_mark_failed_error: note_id=%s error_class=%s",
                note_id,
                type(exc).__name__,
            )
