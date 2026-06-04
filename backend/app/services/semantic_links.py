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
#
# Round 33 (2026-06-04): added phrase signal to catch literal repeated
# phrases like "Film Meetup" that recur across multiple notes but where
# the surrounding context is too different for cosine alone to fire.
# Weights rebalanced so they still sum to 1.0:
#   - SEM 0.55 (was 0.70) — still dominant; cosine remains the strongest
#     single signal
#   - TAG 0.15 (was 0.20)
#   - TITLE 0.10 (unchanged)
#   - PHRASE 0.20 (NEW) — literal-phrase repetition is high-intent

WEIGHT_SEMANTIC = 0.55
WEIGHT_TAG = 0.15
WEIGHT_TITLE = 0.10
WEIGHT_PHRASE = 0.20

# Composite threshold — a candidate is kept only when composite >= this.
DEFAULT_SEM_THRESHOLD = 0.55

# Per-component floor — at least ONE of these must hold so two notes
# with only a shared tag (or only a shared title token) aren't linked
# without ANY anchor strong enough on its own. Round 33: sem floor
# dropped from 0.65 -> 0.60 (the phrase signal supplements it); new
# phrase floor at 0.40.
FLOOR_SEMANTIC = 0.60
FLOOR_TAG = 0.50
FLOOR_TITLE = 0.50
FLOOR_PHRASE = 0.40

# Strong single-signal anchor — if ANY component clears its anchor value,
# the link qualifies regardless of the composite score. Catches the cases
# where one signal is overwhelmingly strong but the others happen to be
# zero (e.g. "Film Meetup" appears in many notes about totally different
# ideas -> phrase Jaccard ~0.5+ alone is enough; or two notes with very
# high cosine similarity but no shared tag/title/phrase still link).
# Without this single-signal path the composite math would punish "strong
# in one dimension, zero everywhere else" cases.
STRONG_SEMANTIC = 0.75
STRONG_TAG = 0.70
STRONG_TITLE = 0.70
STRONG_PHRASE = 0.50

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

# Multi-word capitalized phrases (Title Case n-grams of length >=2). Catches
# proper-noun phrases the user keeps reusing across notes — "Film Meetup",
# "Project Cortex", "Sunday Long Run", etc. The first character is anchored
# at a word boundary and must be uppercase; subsequent words also start
# uppercase. We allow apostrophes and hyphens inside a word.
_CAPITALIZED_PHRASE_RE = re.compile(
    r"\b[A-Z][a-zA-Z0-9'\-]+(?:\s+[A-Z][a-zA-Z0-9'\-]+)+\b"
)

# Hashtag-style tokens written into the body (e.g. "#film-meetup"). The user
# may type these manually as a deliberate link signal even when auto-tagging
# decides to use a different tag vocabulary.
_HASHTAG_RE = re.compile(r"#([a-zA-Z][a-zA-Z0-9_\-]+)")


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

    # Round 33: precompute the source note's salient phrases once.
    source_phrases = extract_salient_phrases(
        getattr(note, "content", None),
        title=getattr(note, "title", None),
        tag_names=source_tags,
    )

    for candidate in candidates:
        candidate_id = _as_uuid(_candidate_value(candidate, "id"))
        sem = float(_candidate_value(candidate, "sem") or 0.0)
        cand_title = _candidate_value(candidate, "title")
        cand_content = _candidate_value(candidate, "content")
        cand_tags = tags_by_note_id.get(candidate_id, set())
        tag = tag_jaccard(source_tags, cand_tags)
        title = title_jaccard(getattr(note, "title", None), cand_title)
        cand_phrases = extract_salient_phrases(
            cand_content,
            title=cand_title,
            tag_names=cand_tags,
        )
        phrase = phrase_jaccard(source_phrases, cand_phrases)
        composite = composite_score(sem=sem, tag=tag, title=title, phrase=phrase)
        if link_qualifies(
            sem=sem,
            tag=tag,
            title=title,
            phrase=phrase,
            composite=composite,
            threshold=sem_threshold,
        ):
            # Score the link by the *better* of the composite or the
            # single-signal strength so Brain View / sort-order stays
            # honest for pure-cosine-strong notes.
            score = max(composite, sem, tag, title, phrase)
            scored_candidates.append({"id": candidate_id, "score": score})

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


def extract_salient_phrases(
    content: Optional[str],
    title: Optional[str] = None,
    tag_names: Optional[set[str]] = None,
) -> set[str]:
    """Pull salient lowercased phrases out of a note's BODY.

    A "salient phrase" is a literal piece of text whose repetition across
    notes is a strong intent signal that the notes belong together.
    We collect from ``content`` only:
      - Multi-word capitalized phrases (e.g. ``"Film Meetup"``,
        ``"Project Cortex"``). One-word capitalized tokens are
        intentionally excluded -- they're too noisy ("Today", "I", a
        sentence-leading word).
      - Hashtag-style tokens (``#film-meetup`` -> ``film-meetup``). The
        user may type these as a deliberate link signal even when auto-
        tagging chooses a different tag vocabulary.

    NOTE on the ``title`` and ``tag_names`` parameters: they are kept on
    the signature for backwards compatibility with R32-era callers but
    are deliberately IGNORED. Title and tag overlap are already their
    own composite signals (``title_jaccard`` / ``tag_jaccard``); folding
    them into the phrase set dilutes the literal-phrase signal -- e.g.
    two notes that both literally say "Film Meetup" would produce
    Jaccard ~0.16 once the unrelated title/tag tokens get mixed in,
    far below the phrase floor. Keeping phrases body-only ensures
    ``phrase_jaccard ≈ 1.0`` for the user's repro case.

    Returns an empty set when ``content`` is empty / None.
    """
    del title, tag_names  # documented as no-ops; see docstring above.
    phrases: set[str] = set()
    if not content:
        return phrases
    for match in _CAPITALIZED_PHRASE_RE.findall(content):
        phrases.add(match.strip().lower())
    for match in _HASHTAG_RE.findall(content):
        phrases.add(match.strip().lower())
    return phrases


def phrase_jaccard(left: set[str], right: set[str]) -> float:
    """Jaccard overlap of two salient-phrase sets. Returns 0 when both empty."""
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def composite_score(
    *, sem: float, tag: float, title: float, phrase: float = 0.0,
) -> float:
    """Linear composite of the four signals.

    ``phrase`` has a default of 0.0 so older callers that haven't been
    updated still produce a valid (slightly lower) score.
    """
    score = (
        WEIGHT_SEMANTIC * sem
        + WEIGHT_TAG * tag
        + WEIGHT_TITLE * title
        + WEIGHT_PHRASE * phrase
    )
    return round(score, 12)


def passes_floor(
    *, sem: float, tag: float, title: float, phrase: float = 0.0,
) -> bool:
    """At least one component must clear its floor.

    ``phrase`` defaults to 0.0 for backwards compatibility; callers that
    don't pass it simply lose access to the phrase-anchor path.
    """
    return (
        sem >= FLOOR_SEMANTIC
        or tag >= FLOOR_TAG
        or title >= FLOOR_TITLE
        or phrase >= FLOOR_PHRASE
    )


def has_strong_single_signal(
    *, sem: float, tag: float, title: float, phrase: float = 0.0,
) -> bool:
    """Return True if at least one signal is strong enough to anchor a link
    on its own, regardless of how weak the other signals are.

    The composite-path math punishes "strong in one dimension, zero
    everywhere else" cases -- a perfect cosine of 0.9 alone gives composite
    = 0.55 * 0.9 = 0.495, which fails the 0.55 threshold. This predicate is
    the safety net for those obviously-related cases.
    """
    return (
        sem >= STRONG_SEMANTIC
        or tag >= STRONG_TAG
        or title >= STRONG_TITLE
        or phrase >= STRONG_PHRASE
    )


def link_qualifies(
    *,
    sem: float,
    tag: float,
    title: float,
    phrase: float,
    composite: float,
    threshold: float,
) -> bool:
    """Two-path link qualification (Round 33).

    Path A (composite): ``composite >= threshold`` AND at least one
    component clears its floor. Catches notes that are jointly similar
    across multiple weak-to-medium signals.

    Path B (strong single signal): any one signal is overwhelmingly
    strong. Catches the user's "Film Meetup" case (the literal phrase
    repeats across many notes but the embeddings + tags differ widely)
    AND preserves the Round 32 behaviour where a pure-cosine match of
    0.9+ links even when nothing else overlaps.
    """
    composite_path = composite >= threshold and passes_floor(
        sem=sem, tag=tag, title=title, phrase=phrase,
    )
    if composite_path:
        return True
    return has_strong_single_signal(sem=sem, tag=tag, title=title, phrase=phrase)


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
        SELECT id, title, content, embedding <=> CAST(:emb AS vector) AS dist,
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
