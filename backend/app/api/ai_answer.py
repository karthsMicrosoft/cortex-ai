"""
RAG endpoint — POST /api/ai/answer  (Phase 4 / PR 4.1).

Given a natural-language question, embed it, run hybrid search over the
caller's notes (re-using the canonical 0.7 * (1 - cosine) + 0.3 * ts_rank
SQL pattern from search.py), then ask GPT-4o-mini to compose a grounded
answer that cites notes by [N] index.

Behaviour summary:
- Input validated by pydantic (query 1..1000 chars; max_results 1..20).
- Zero retrieval rows → friendly canned answer, no OpenAI call.
- Otherwise build strict prompt + parse `[N]` citations.
- Per-user 30/hour rate limit (slowapi). 401 / 400 / 429 / 502 / 503 errors.
- `prior_messages` is accepted but UNUSED in this PR (PR 4.5).
"""
import json
import logging
import re
import time
import uuid
from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from openai import AsyncAzureOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.limiter import limiter
from app.schemas.ai_answer import (
    AnswerCitation,
    AnswerFilters,
    AnswerRequest,
    AnswerResponse,
    PriorMessage,
)
from app.services.openai_client import get_openai

logger = logging.getLogger(__name__)

router = APIRouter()

MODEL_NAME = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"

_MAX_RESULTS_HARD_CAP = 20
_NOTE_TRUNCATE_CHARS = 1500
_SNIPPET_CHARS = 240
_NO_MATCH_ANSWER = "I don't have any notes that match this question."

# Multi-turn caps (PR 4.5).
_PRIOR_MAX_ENTRIES = 8         # 4 user + 4 assistant turns max
_PRIOR_CONTENT_CHARS = 1000    # per-message cap

_SYSTEM_PROMPT = (
    "You are Cortex, the user's second brain. Answer using ONLY the provided "
    "notes. Cite each fact with [N] where N is the index of the note in the "
    "list. If the notes don't contain the answer, say so."
)

# ---------------------------------------------------------------------------
# Hybrid retrieval SQL (mirrors app/api/search.py::_HYBRID_SQL).
#
# Kept inline here (instead of importing from search.py) per the PR scope:
# "Don't change search.py". Including the same `n.embedding IS NOT NULL`
# guard so the PR-4.0a contract holds at this endpoint too.
# ---------------------------------------------------------------------------
_HYBRID_SQL_AI = text("""
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
  AND n.embedding IS NOT NULL
  AND (CAST(:category   AS text)        IS NULL OR n.category   = :category)
  AND (CAST(:date_from  AS timestamptz) IS NULL OR n.created_at >= :date_from)
  AND (CAST(:date_to    AS timestamptz) IS NULL OR n.created_at <= :date_to)
  AND (
    CAST(:tags AS text[]) IS NULL
    OR EXISTS (
      SELECT 1
      FROM note_tags nt
      JOIN tags t ON t.id = nt.tag_id
      WHERE nt.note_id = n.id
        AND t.user_id  = :user_id
        AND t.name     = ANY(:tags)
    )
  )
ORDER BY combined_score DESC NULLS LAST
LIMIT :limit
""")


# ---------------------------------------------------------------------------
# Retrieval helper — extracted so tests can patch it directly.
# ---------------------------------------------------------------------------

async def _retrieve_notes(
    db: AsyncSession,
    openai_client: AsyncAzureOpenAI,
    user_id: uuid.UUID,
    query: str,
    max_results: int,
    filters: Optional[AnswerFilters],
) -> list[dict[str, Any]]:
    """Embed *query* and run hybrid retrieval against the user's notes.

    Returns a list of plain dicts — easier to patch in tests than ORM rows.
    Each dict has keys: note_id, content, summary, category,
    semantic_score, text_score, combined_score.

    Raises HTTPException(503) when the underlying SQL fails (e.g. pgvector
    is unavailable — same contract as search.py).
    """
    emb_response = await openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query,
    )
    query_embedding: list[float] = emb_response.data[0].embedding
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    params: dict[str, Any] = {
        "q_emb": embedding_str,
        "q_text": query,
        "user_id": str(user_id),
        "category": filters.category if filters else None,
        "date_from": filters.since if filters else None,
        "date_to": filters.until if filters else None,
        "tags": filters.tags if filters else None,
        "limit": max_results,
    }

    try:
        result = await db.execute(_HYBRID_SQL_AI, params)
        rows = result.fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "ai_answer._retrieve_notes: SQL failed error_class=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Retrieval is unavailable — vector index not ready",
        ) from exc

    return [
        {
            "note_id": str(row.id),
            "content": row.content or "",
            "summary": row.summary,
            "category": row.category,
            "semantic_score": float(row.semantic_score or 0.0),
            "text_score": float(row.text_score or 0.0),
            "combined_score": float(row.combined_score or 0.0),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Prompt + citation helpers
# ---------------------------------------------------------------------------

def _build_user_prompt(query: str, notes: list[dict[str, Any]]) -> str:
    lines = [f"Question: {query}", "", "Notes:"]
    for idx, note in enumerate(notes, start=1):
        body = (note.get("content") or "")[:_NOTE_TRUNCATE_CHARS]
        cat = note.get("category") or "Note"
        lines.append(f"[{idx}] ({cat}) {body}")
    lines.append("")
    lines.append(
        "Answer the question using only these notes. Cite supporting notes "
        "with [N]."
    )
    return "\n".join(lines)


def _title_for(note: dict[str, Any]) -> str:
    """Derive a human-friendly title: summary, else first line of content."""
    summary = (note.get("summary") or "").strip()
    if summary:
        return summary[:120]
    content = (note.get("content") or "").strip()
    first_line = content.splitlines()[0] if content else ""
    return (first_line or "Untitled note")[:120]


def _snippet_for(note: dict[str, Any]) -> str:
    return (note.get("content") or "")[:_SNIPPET_CHARS]


def _build_citations(notes: list[dict[str, Any]]) -> list[AnswerCitation]:
    """Build citations for every retrieved note. relevance = combined_score."""
    citations: list[AnswerCitation] = []
    for note in notes:
        try:
            note_uuid = uuid.UUID(str(note["note_id"]))
        except (ValueError, KeyError, TypeError):
            continue
        citations.append(
            AnswerCitation(
                note_id=note_uuid,
                title=_title_for(note),
                snippet=_snippet_for(note),
                relevance=float(note.get("combined_score") or 0.0),
            )
        )
    return citations


def _normalize_prior_messages(
    prior: Optional[list[PriorMessage]],
) -> list[dict[str, str]]:
    """Cap to last 8 entries and truncate each ``content`` to 1000 chars.

    Returns chat-completion-shaped dicts ready to splice into ``messages``.
    Empty / None input → ``[]`` (no prior context).
    """
    if not prior:
        return []
    # Keep only the most recent N entries.
    recent = prior[-_PRIOR_MAX_ENTRIES:]
    return [
        {"role": m.role, "content": (m.content or "")[:_PRIOR_CONTENT_CHARS]}
        for m in recent
    ]


# ---------------------------------------------------------------------------
# OpenAI invocation with single retry → 502 on failure.
# ---------------------------------------------------------------------------

async def _call_openai_with_retry(
    openai_client: AsyncAzureOpenAI,
    query: str,
    notes: list[dict[str, Any]],
    prior_messages: Optional[list[PriorMessage]] = None,
) -> str:
    user_prompt = _build_user_prompt(query, notes)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        *_normalize_prior_messages(prior_messages),
        {"role": "user", "content": user_prompt},
    ]

    last_exc: Optional[BaseException] = None
    for attempt in range(2):  # initial + one retry
        try:
            response = await openai_client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                max_tokens=600,
                temperature=0.3,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(
                "ai_answer: OpenAI attempt %d/2 failed error_class=%s",
                attempt + 1, type(exc).__name__,
            )

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Upstream LLM failed: {type(last_exc).__name__ if last_exc else 'unknown'}",
    )


# ---------------------------------------------------------------------------
# POST /answer
# ---------------------------------------------------------------------------

_NDJSON_MEDIA_TYPE = "application/x-ndjson"


def _wants_ndjson(request: Request) -> bool:
    """True iff the client asked for NDJSON streaming via Accept header."""
    accept = (request.headers.get("accept") or "").lower()
    return _NDJSON_MEDIA_TYPE in accept


def _ndjson(obj: dict) -> bytes:
    return (json.dumps(obj, default=str) + "\n").encode("utf-8")


async def _stream_openai_tokens(
    openai_client: AsyncAzureOpenAI,
    query: str,
    notes: list[dict[str, Any]],
    prior_messages: Optional[list[PriorMessage]] = None,
) -> AsyncIterator[str]:
    """Async-iterate token chunks from OpenAI streaming chat completion."""
    user_prompt = _build_user_prompt(query, notes)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        *_normalize_prior_messages(prior_messages),
        {"role": "user", "content": user_prompt},
    ]
    stream = await openai_client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        max_tokens=600,
        temperature=0.3,
        stream=True,
    )
    async for chunk in stream:
        try:
            delta = chunk.choices[0].delta
            text_piece = getattr(delta, "content", None)
        except (AttributeError, IndexError):
            text_piece = None
        if text_piece:
            yield text_piece


async def _streaming_answer(
    started: float,
    openai_client: AsyncAzureOpenAI,
    user_id: uuid.UUID,
    query: str,
    notes: list[dict[str, Any]],
    prior_messages: Optional[list[PriorMessage]] = None,
) -> AsyncIterator[bytes]:
    """Yield NDJSON frames: meta → token* → done | error."""
    yield _ndjson({
        "type": "meta",
        "retrieval_count": len(notes),
        "model": MODEL_NAME,
    })

    if not notes:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        yield _ndjson({
            "type": "token",
            "text": _NO_MATCH_ANSWER,
        })
        yield _ndjson({
            "type": "done",
            "citations": [],
            "elapsed_ms": elapsed_ms,
        })
        return

    collected: list[str] = []
    try:
        async for piece in _stream_openai_tokens(
            openai_client, query, notes, prior_messages
        ):
            collected.append(piece)
            yield _ndjson({"type": "token", "text": piece})
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "ai_answer.stream: OpenAI failed error_class=%s",
            type(exc).__name__,
        )
        yield _ndjson({
            "type": "error",
            "detail": f"Upstream LLM failed: {type(exc).__name__}",
        })
        return

    answer_text = "".join(collected)
    citations = _build_citations(notes)
    # Restrict citations to those actually referenced via [N] markers when
    # any are present; otherwise fall back to all retrieved notes (mirrors
    # the non-streaming behaviour which returns one citation per row).
    referenced = {int(m) for m in re.findall(r"\[(\d+)\]", answer_text)}
    if referenced:
        citations = [
            c for i, c in enumerate(citations, start=1) if i in referenced
        ] or citations

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "ai_answer.stream: user_id=%s retrieval_count=%d elapsed_ms=%d",
        user_id, len(notes), elapsed_ms,
    )
    yield _ndjson({
        "type": "done",
        "citations": [
            {
                "note_id": str(c.note_id),
                "title": c.title,
                "snippet": c.snippet,
                "relevance": c.relevance,
            }
            for c in citations
        ],
        "elapsed_ms": elapsed_ms,
    })


@router.post("/answer")
@limiter.limit("30/hour")
async def answer(
    request: Request,
    payload: AnswerRequest,
    response: Response,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    openai_client: AsyncAzureOpenAI = Depends(get_openai),
):
    """Answer a natural-language question using the user's notes (RAG).

    Content negotiation:
      * Accept: application/x-ndjson  → NDJSON token stream
      * Anything else (default)       → single JSON AnswerResponse
    """
    started = time.perf_counter()

    # Defensive cap: pydantic already enforces <=20, but if a future change
    # loosens that, keep the hard cap here too.
    max_results = min(payload.max_results, _MAX_RESULTS_HARD_CAP)

    notes = await _retrieve_notes(
        db=db,
        openai_client=openai_client,
        user_id=current_user_id,
        query=payload.query,
        max_results=max_results,
        filters=payload.filters,
    )

    if _wants_ndjson(request):
        return StreamingResponse(
            _streaming_answer(
                started=started,
                openai_client=openai_client,
                user_id=current_user_id,
                query=payload.query,
                notes=notes,
                prior_messages=payload.prior_messages,
            ),
            media_type=_NDJSON_MEDIA_TYPE,
        )

    if not notes:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return AnswerResponse(
            answer=_NO_MATCH_ANSWER,
            citations=[],
            model=MODEL_NAME,
            retrieval_count=0,
            elapsed_ms=elapsed_ms,
        )

    answer_text = await _call_openai_with_retry(
        openai_client=openai_client,
        query=payload.query,
        notes=notes,
        prior_messages=payload.prior_messages,
    )

    citations = _build_citations(notes)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "ai_answer: user_id=%s retrieval_count=%d elapsed_ms=%d",
        current_user_id, len(notes), elapsed_ms,
    )
    return AnswerResponse(
        answer=answer_text,
        citations=citations,
        model=MODEL_NAME,
        retrieval_count=len(notes),
        elapsed_ms=elapsed_ms,
    )
