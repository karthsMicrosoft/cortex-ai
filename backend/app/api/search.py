"""
Search endpoints — hybrid semantic + full-text search.

Endpoints:
  POST /api/search                   — hybrid search (0.7 semantic + 0.3 ts_rank)
  GET  /api/search/similar/{note_id} — top-N notes by cosine to source note

All endpoints require auth.
"""
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.note import Note
from app.schemas.search import SearchRequest, SearchResultItem
from app.services.openai_client import get_openai, get_openai_client  # get_openai patched by tests

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# POST /api/search
# ---------------------------------------------------------------------------

# Canonical hybrid SQL from design § "Semantic Search" (B7).
# Includes tags EXISTS subquery against note_tags ⨝ tags.
_HYBRID_SQL = text("""
SELECT
  n.id, n.content, n.summary, n.category, n.created_at,
  (1 - (n.embedding <=> CAST(:q_emb AS vector)))                               AS semantic_score,
  ts_rank(to_tsvector('english', n.content),
          plainto_tsquery('english', :q_text))                                  AS text_score,
  0.7 * (1 - (n.embedding <=> CAST(:q_emb AS vector))) +
  0.3 * ts_rank(to_tsvector('english', n.content),
                plainto_tsquery('english', :q_text))                            AS combined_score
FROM notes n
WHERE n.user_id = :user_id
  AND (:category   IS NULL OR n.category   = :category)
  AND (:date_from  IS NULL OR n.created_at >= :date_from)
  AND (:date_to    IS NULL OR n.created_at <= :date_to)
  AND (
    :tags IS NULL
    OR EXISTS (
      SELECT 1
      FROM note_tags nt
      JOIN tags t ON t.id = nt.tag_id
      WHERE nt.note_id = n.id
        AND t.user_id  = :user_id
        AND t.name     = ANY(:tags)
    )
  )
ORDER BY combined_score DESC
LIMIT :limit
OFFSET :offset
""")


@router.post("", response_model=list[SearchResultItem])
async def search_notes(
    payload: SearchRequest,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SearchResultItem]:
    """Hybrid semantic + full-text search over the user's notes.

    Embeds the query via text-embedding-3-small, then runs the canonical B7
    hybrid SQL (0.7 semantic + 0.3 ts_rank) with optional category, tags,
    and date filters.
    """
    openai_client = await get_openai()

    # Embed the query
    emb_response = await openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=payload.query,
    )
    query_embedding: list[float] = emb_response.data[0].embedding
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    # Build parameters — use None for disabled filters (SQL uses IS NULL check)
    params = {
        "q_emb": embedding_str,
        "q_text": payload.query,
        "user_id": str(current_user_id),
        "category": payload.category,
        "date_from": payload.date_from,
        "date_to": payload.date_to,
        "tags": payload.tags,  # list[str] | None → ANY(:tags) handles None as no-op
        "limit": payload.limit,
        "offset": payload.offset,
    }

    try:
        result = await db.execute(_HYBRID_SQL, params)
        rows = result.fetchall()
    except Exception as exc:  # noqa: BLE001
        # pgvector not available (e.g. SQLite tests) — fallback not implemented.
        logger.error("search_notes: SQL failed error_class=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search is unavailable — vector index not ready",
        ) from exc

    return [
        SearchResultItem(
            id=row.id,
            content=row.content,
            summary=row.summary,
            category=row.category,
            created_at=row.created_at,
            semantic_score=float(row.semantic_score or 0.0),
            text_score=float(row.text_score or 0.0),
            combined_score=float(row.combined_score or 0.0),
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# GET /api/search/similar/{note_id}
# ---------------------------------------------------------------------------

# PERF-08 fix: pass the already-fetched source embedding as a parameter instead
# of doing a Cartesian product FROM notes n, notes src.  The cross-join loaded
# the source note's 1536-float embedding twice from the DB (6 KB of extra I/O)
# and prevented the query planner from using the HNSW index efficiently.
_SIMILAR_SQL = text("""
SELECT
  n.id, n.content, n.summary, n.category, n.created_at,
  (1 - (n.embedding <=> CAST(:source_emb AS vector)))           AS semantic_score,
  0.0                                                            AS text_score,
  (1 - (n.embedding <=> CAST(:source_emb AS vector)))           AS combined_score
FROM notes n
WHERE n.id        != :source_note_id
  AND n.user_id   = :user_id
  AND n.embedding IS NOT NULL
ORDER BY n.embedding <=> CAST(:source_emb AS vector)
LIMIT :limit
""")


@router.get("/similar/{note_id}", response_model=list[SearchResultItem])
async def get_similar_notes(
    note_id: uuid.UUID = Path(...),
    limit: int = Query(default=10, ge=1, le=50),
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SearchResultItem]:
    """Return the top-N most similar notes to *note_id* by cosine distance.

    The source note must belong to the authenticated user.
    """
    # Verify ownership
    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.user_id == current_user_id)
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    if note.embedding is None:
        return []

    # Build embedding string from the already-loaded note object (PERF-08)
    source_emb_str = "[" + ",".join(str(x) for x in note.embedding) + "]"

    try:
        rows_result = await db.execute(
            _SIMILAR_SQL,
            {
                "source_note_id": str(note_id),
                "source_emb": source_emb_str,
                "user_id": str(current_user_id),
                "limit": limit,
            },
        )
        rows = rows_result.fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.error("get_similar_notes: SQL failed error_class=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Similar-note lookup is unavailable — vector index not ready",
        ) from exc

    return [
        SearchResultItem(
            id=row.id,
            content=row.content,
            summary=row.summary,
            category=row.category,
            created_at=row.created_at,
            semantic_score=float(row.semantic_score or 0.0),
            text_score=float(row.text_score or 0.0),
            combined_score=float(row.combined_score or 0.0),
        )
        for row in rows
    ]
