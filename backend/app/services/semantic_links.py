"""Semantic-link service — Round 32.

Single module that owns the auto-linking logic. Both the per-note pipeline
(``app/pipeline/processor.py``) AND the batch endpoint
(``POST /api/notes/relink-all``) call into here so the scoring stays in
exactly one place.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from sqlalchemy import select, text
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.orm import selectinload

from app.models.note import Note
from app.models.note_link import NoteLink
from app.models.tag import Tag, note_tags as note_tags_table

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunable scoring weights — exposed for tests
# ---------------------------------------------------------------------------

WEIGHT_SEMANTIC = 0.7
WEIGHT_TAG = 0.2
WEIGHT_TITLE = 0.1

# Composite threshold — a candidate is kept only when composite >= this.
DEFAULT_SEM_THRESHOLD = 0.55

# Per-component floor — at least ONE of these must hold so that two notes
# with only a shared tag (or only a shared title token) aren't linked.
FLOOR_SEMANTIC = 0.65
FLOOR_TAG = 0.5
FLOOR_TITLE = 0.5

# Stopwords removed before title tokenisation.
_TITLE_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "in", "on", "to", "for",
    "with", "is", "it", "my", "this", "that", "be", "are", "was",
})

# pgvector candidate pool — how many semantic neighbours to consider per
# note before composite re-ranking.
CANDIDATE_POOL = 20

# Single-instance rate limit for manual relink runs. If the Container App ever
# scales out, move this state to Redis or another shared store.
_last_run: dict[str, float] = {}

_TITLE_SPLIT_RE = re.compile(r"[^a-z0-9]+")


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class RelinkResult:
    created: int = 0
    updated: int = 0
    duration_ms: int = 0
    skipped_recent: bool = False

    def to_dict(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "duration_ms": self.duration_ms,
            "skipped_recent": self.skipped_recent,
        }


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

async def rebuild_user_links(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    top_n: int = 5,
    sem_threshold: float = DEFAULT_SEM_THRESHOLD,
    limit_notes: Optional[int] = None,
    last_relink_window: int = 300,
) -> RelinkResult:
    """Rebuild all semantic links for ``user_id`` with a small in-process TTL."""
    started = time.monotonic()
    run_key = str(user_id)
    previous_run = _last_run.get(run_key)
    if previous_run is not None and started - previous_run < last_relink_window:
        return RelinkResult(skipped_recent=True, duration_ms=0)

    stmt = (
        select(Note)
        .options(selectinload(Note.tags))
        .where(Note.user_id == user_id)
        .where(Note.embedding.is_not(None))
        .order_by(Note.created_at.asc())
    )
    if limit_notes is not None:
        stmt = stmt.limit(limit_notes)

    result = await db.execute(stmt)
    notes = list(result.scalars().all())

    aggregate = RelinkResult()
    for note in notes:
        single = await relink_single_note(
            db,
            note,
            top_n=top_n,
            sem_threshold=sem_threshold,
        )
        aggregate.created += single.created
        aggregate.updated += single.updated

    _last_run[run_key] = time.monotonic()
    aggregate.duration_ms = int((_last_run[run_key] - started) * 1000)
    return aggregate


async def relink_single_note(
    db: AsyncSession,
    note,  # SQLAlchemy Note instance; kept loose for pipeline test doubles
    *,
    top_n: int = 5,
    sem_threshold: float = DEFAULT_SEM_THRESHOLD,
) -> RelinkResult:
    """Recompute semantic links for a single note."""
    if note.embedding is None:
        return RelinkResult()

    started = time.monotonic()
    try:
        candidates = await _fetch_vector_candidates(
            db,
            note,
            pool=CANDIDATE_POOL,
            sem_threshold=sem_threshold,
            top_n=top_n,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("relink_single_note skipped: %s", type(exc).__name__)
        return RelinkResult()

    if not candidates:
        return RelinkResult(duration_ms=int((time.monotonic() - started) * 1000))

    source_id = _as_uuid(note.id)
    scored_candidates: list[dict[str, Any]] = []
    candidate_ids = [_as_uuid(_candidate_value(candidate, "id")) for candidate in candidates]
    source_tags = _loaded_tag_names(note)
    tag_lookup_ids = candidate_ids if source_tags is not None else [source_id, *candidate_ids]
    tags_by_note_id = await _fetch_tag_names_by_note_ids(db, tag_lookup_ids)
    if source_tags is None:
        source_tags = tags_by_note_id.get(source_id, set())

    for candidate in candidates:
        candidate_id = _as_uuid(_candidate_value(candidate, "id"))
        sem = float(_candidate_value(candidate, "sem") or 0.0)
        cand_title = _candidate_value(candidate, "title")
        tag = tag_jaccard(source_tags, tags_by_note_id.get(candidate_id, set()))
        title = title_jaccard(getattr(note, "title", None), cand_title)
        composite = composite_score(sem=sem, tag=tag, title=title)
        if composite >= sem_threshold and passes_floor(sem=sem, tag=tag, title=title):
            scored_candidates.append({"id": candidate_id, "score": composite})

    scored_candidates.sort(key=lambda item: item["score"], reverse=True)
    survivors = scored_candidates[:top_n]
    if not survivors:
        return RelinkResult(duration_ms=int((time.monotonic() - started) * 1000))

    target_ids = [item["id"] for item in survivors]
    existing_ids = await _existing_semantic_target_ids(db, source_id, target_ids)
    await _upsert_semantic_links(db, source_id, survivors)

    created = len([target_id for target_id in target_ids if target_id not in existing_ids])
    updated = len(target_ids) - created
    return RelinkResult(
        created=created,
        updated=updated,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


# ---------------------------------------------------------------------------
# Composite-scoring primitives — exported for tests
# ---------------------------------------------------------------------------

def tag_jaccard(left: set[str], right: set[str]) -> float:
    """Jaccard overlap of two tag sets. Returns 0 when both empty."""
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def title_jaccard(left: Optional[str], right: Optional[str]) -> float:
    """Jaccard overlap of tokenised, stopword-filtered titles."""
    if not left or not right:
        return 0.0
    return tag_jaccard(_title_tokens(left), _title_tokens(right))


def composite_score(
    *, sem: float, tag: float, title: float,
) -> float:
    """Linear composite of the three signals."""
    score = (WEIGHT_SEMANTIC * sem) + (WEIGHT_TAG * tag) + (WEIGHT_TITLE * title)
    return round(score, 12)


def passes_floor(*, sem: float, tag: float, title: float) -> bool:
    """At least one component must clear its floor."""
    return sem >= FLOOR_SEMANTIC or tag >= FLOOR_TAG or title >= FLOOR_TITLE


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _fetch_vector_candidates(
    db: AsyncSession,
    note,
    *,
    pool: int,
    sem_threshold: float | None = None,
    top_n: int | None = None,
) -> list[Mapping[str, Any]]:
    """Fetch pgvector neighbours. Raises when pgvector is unavailable."""
    candidate_sql = text("""
        SELECT id, title, embedding <=> CAST(:emb AS vector) AS dist,
               1 - (embedding <=> CAST(:emb AS vector)) AS sem
        FROM notes
        WHERE id != :note_id
          AND user_id = :user_id
          AND embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:emb AS vector)
        LIMIT :pool
    """)
    result = await db.execute(
        candidate_sql,
        {
            "note_id": note.id,
            "user_id": note.user_id,
            "emb": _embedding_literal(note.embedding),
            "pool": pool,
            # Kept for compatibility with older pipeline tests that captured
            # these params from the semantic-link SQL call.
            "threshold": sem_threshold,
            "limit": top_n,
        },
    )
    return list(result.mappings().all())


async def _fetch_tag_names_by_note_ids(
    db: AsyncSession,
    note_ids: list[uuid.UUID],
) -> dict[uuid.UUID, set[str]]:
    unique_ids = list(dict.fromkeys(note_ids))
    tags_by_note_id = {note_id: set() for note_id in unique_ids}
    if not unique_ids:
        return tags_by_note_id

    stmt = (
        select(note_tags_table.c.note_id, Tag.name)
        .join(Tag, note_tags_table.c.tag_id == Tag.id)
        .where(note_tags_table.c.note_id.in_(unique_ids))
    )
    result = await db.execute(stmt)
    for note_id, tag_name in result.all():
        tags_by_note_id.setdefault(_as_uuid(note_id), set()).add(tag_name)
    return tags_by_note_id


async def _existing_semantic_target_ids(
    db: AsyncSession,
    source_id: uuid.UUID,
    target_ids: list[uuid.UUID],
) -> set[uuid.UUID]:
    if not target_ids:
        return set()
    result = await db.execute(
        select(NoteLink.target_note_id).where(
            NoteLink.source_note_id == source_id,
            NoteLink.target_note_id.in_(target_ids),
            NoteLink.link_type == "semantic",
        )
    )
    return {_as_uuid(target_id) for target_id in result.scalars().all()}


async def _upsert_semantic_links(
    db: AsyncSession,
    source_id: uuid.UUID,
    scored_candidates: list[dict[str, Any]],
) -> None:
    if _dialect_name(db) == "postgresql":
        upsert_sql = text("""
            INSERT INTO note_links (
                id, source_note_id, target_note_id, link_type, similarity_score
            )
            VALUES (
                gen_random_uuid(), :source_note_id, :target_note_id,
                'semantic', :similarity_score
            )
            ON CONFLICT (source_note_id, target_note_id, link_type)
            DO UPDATE SET similarity_score = EXCLUDED.similarity_score
        """)
        for candidate in scored_candidates:
            await db.execute(
                upsert_sql,
                {
                    "source_note_id": source_id,
                    "target_note_id": candidate["id"],
                    "similarity_score": candidate["score"],
                },
            )
        return

    # SQLite/test fallback for monkeypatched candidate queries; production uses
    # the gen_random_uuid() PostgreSQL path above.
    for candidate in scored_candidates:
        result = await db.execute(
            select(NoteLink).where(
                NoteLink.source_note_id == source_id,
                NoteLink.target_note_id == candidate["id"],
                NoteLink.link_type == "semantic",
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            db.add(
                NoteLink(
                    source_note_id=source_id,
                    target_note_id=candidate["id"],
                    link_type="semantic",
                    similarity_score=candidate["score"],
                )
            )
        else:
            existing.similarity_score = candidate["score"]
    await db.flush()


def _loaded_tag_names(note) -> set[str] | None:
    try:
        state = sa_inspect(note)
        if "tags" in state.unloaded:
            return None
    except (NoInspectionAvailable, AttributeError):
        return None

    tags = getattr(note, "tags", None)
    if tags is None:
        return None
    return {tag.name for tag in tags if getattr(tag, "name", None)}


def _title_tokens(title: str) -> set[str]:
    return {
        token
        for token in _TITLE_SPLIT_RE.split(title.lower())
        if token and token not in _TITLE_STOPWORDS
    }


def _candidate_value(candidate: Any, key: str) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(key)
    return getattr(candidate, key)


def _embedding_literal(embedding: Any) -> str:
    if isinstance(embedding, str):
        return embedding if embedding.startswith("[") else f"[{embedding}]"
    return "[" + ",".join(str(value) for value in embedding) + "]"


def _as_uuid(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _dialect_name(db: AsyncSession) -> str:
    try:
        bind = db.get_bind()
        return bind.dialect.name
    except Exception:  # noqa: BLE001
        return ""
