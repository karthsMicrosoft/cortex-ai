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
from enum import Enum
from typing import Optional

from openai import AsyncAzureOpenAI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.note import Note
from app.models.note_link import NoteLink
from app.models.tag import Tag, note_tags as note_tags_table
from app.pipeline.music import process_music_note  # noqa: F401 (patched by tests)
from app.pipeline.shadow_reader import run_shadow_reader_stage  # noqa: F401 (patched by tests)

logger = logging.getLogger(__name__)

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
        if note.source_type == "text":
            # Text notes are already clean — skip LLM cleanup, advance status.
            note.processing_status = ProcessingStage.PROCESSED
            await self.db.commit()
            logger.info("pipeline_stage_complete: capture(skip) note_id=%s", note.id)
            return

        prompt = (
            "You are a personal knowledge assistant. Clean and structure this raw voice note.\n"
            "Rules:\n"
            "- Fix grammar and remove filler words (um, uh, like)\n"
            "- Preserve the original meaning and tone\n"
            "- Format into clear paragraphs\n"
            "- If it is a list, format as bullet points\n"
            "- Keep it concise but complete\n\n"
            f"Raw transcription:\n{note.raw_transcription or note.content}\n\n"
            "Return ONLY the cleaned text, nothing else."
        )

        response = await self.openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3,
        )

        cleaned = response.choices[0].message.content or ""
        note.content = cleaned
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
        """GPT-4o-mini JSON: extract tags, category, mood, summary, entities."""
        prompt = (
            "Analyze this note and return a JSON object with:\n"
            "- tags: array of 3-5 relevant tags (lowercase, hyphenated)\n"
            "- category: exactly one of: Music, Fitness, Journal, Ideas, Spiritual, Learning\n"
            "- mood: emotional tone (single word or short phrase)\n"
            "- summary: 1-2 sentence summary\n"
            "- entities: array of {name, type} objects\n\n"
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

        # Persist tags
        for tag_name in result.get("tags", []):
            if isinstance(tag_name, str) and tag_name.strip():
                await self._ensure_tag(note, tag_name.strip().lower(), is_auto=True)

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
            link_sql = text("""
                INSERT INTO note_links (id, source_note_id, target_note_id, similarity_score, link_type)
                SELECT gen_random_uuid(), :note_id, n.id,
                       1 - (n.embedding <=> CAST(:embedding AS vector)) AS score,
                       'semantic'
                FROM notes n
                WHERE n.id != :note_id
                  AND n.user_id = :user_id
                  AND n.embedding IS NOT NULL
                  AND 1 - (n.embedding <=> CAST(:embedding AS vector)) > :threshold
                ORDER BY n.embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
                ON CONFLICT (source_note_id, target_note_id)
                DO UPDATE SET similarity_score = EXCLUDED.similarity_score
            """)
            embedding_str = "[" + ",".join(str(x) for x in note.embedding) + "]"
            await self.db.execute(
                link_sql,
                {
                    "note_id": str(note.id),
                    "embedding": embedding_str,
                    "user_id": str(note.user_id),
                    "threshold": threshold,
                    "limit": limit,
                },
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
        """Get or create a Tag and associate it with *note*."""
        result = await self.db.execute(
            select(Tag).where(Tag.user_id == note.user_id, Tag.name == name)
        )
        tag = result.scalar_one_or_none()
        if tag is None:
            tag = Tag(user_id=note.user_id, name=name, is_auto=is_auto)
            self.db.add(tag)
            await self.db.flush()

        # Associate if not already linked
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
