"""
Insights API endpoints.

Routes (all require Bearer auth):
  GET  /api/ai/summary/daily?date=YYYY-MM-DD   → DailySummary row or 404
  GET  /api/ai/summary/weekly?week=YYYY-WNN    → weekly summary dict
  GET  /api/insights/graph                      → { nodes, links } capped at 200
  GET  /api/insights/patterns                   → { patterns: [{theme, evidence_note_ids}] }
  POST /api/ai/generate                         → { generated_text }
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.daily_summary import DailySummary
from app.models.note import Note
from app.models.note_link import NoteLink
from app.services.openai_client import OpenAIDep

logger = logging.getLogger(__name__)

# Two routers — mounted at different prefixes in main.py
ai_summary_router = APIRouter()  # prefix=/api/ai
insights_router = APIRouter()    # prefix=/api/insights


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DailySummaryOut(BaseModel):
    id: str
    user_id: str
    summary_date: str
    summary_text: str
    key_themes: list[str]
    note_count: int
    mood_summary: Optional[str]
    created_at: str

    model_config = {"from_attributes": True}


class WeeklySummaryOut(BaseModel):
    week: str
    summary_text: str
    daily_summaries: list[dict]
    note_count: int


class GraphNode(BaseModel):
    id: str
    label: str
    category: str


class GraphLink(BaseModel):
    source: str
    target: str
    score: float


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    links: list[GraphLink]


class PatternItem(BaseModel):
    theme: str
    evidence_note_ids: list[str]


class PatternsOut(BaseModel):
    patterns: list[PatternItem]


class GenerateRequest(BaseModel):
    kind: str  # 'song' | 'practice' | 'reflection'
    source_note_ids: list[str]


class GenerateOut(BaseModel):
    generated_text: str


# ---------------------------------------------------------------------------
# GET /api/ai/summary/daily
# ---------------------------------------------------------------------------

@ai_summary_router.get("/summary/daily", response_model=DailySummaryOut)
async def get_daily_summary(
    date_param: Optional[str] = Query(default=None, alias="date"),
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DailySummaryOut:
    """
    Return the daily summary for *date* (YYYY-MM-DD).
    Defaults to today if *date* is omitted.
    Returns 404 if no summary exists for the requested date.
    """
    if date_param is None:
        target_date = date.today()
    else:
        try:
            target_date = date.fromisoformat(date_param)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid date format: {date_param!r}. Use YYYY-MM-DD.",
            ) from exc

    result = await db.execute(
        select(DailySummary).where(
            DailySummary.user_id == current_user_id,
            DailySummary.summary_date == target_date,
        )
    )
    summary = result.scalar_one_or_none()
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No daily summary found for {target_date}",
        )

    return DailySummaryOut(
        id=str(summary.id),
        user_id=str(summary.user_id),
        summary_date=str(summary.summary_date),
        summary_text=summary.summary_text,
        key_themes=summary.key_themes or [],
        note_count=summary.note_count,
        mood_summary=summary.mood_summary,
        created_at=summary.created_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# GET /api/ai/summary/weekly
# ---------------------------------------------------------------------------

@ai_summary_router.get("/summary/weekly", response_model=WeeklySummaryOut)
async def get_weekly_summary(
    week: Optional[str] = Query(default=None),
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    openai: OpenAIDep,
) -> WeeklySummaryOut:
    """
    Return (or generate on-demand) a weekly summary for *week* (YYYY-WNN).
    Defaults to the current ISO week if *week* is omitted.
    """
    if week is None:
        today = date.today()
        iso_cal = today.isocalendar()
        week = f"{iso_cal[0]}-W{iso_cal[1]:02d}"

    try:
        from app.pipeline.distill import generate_weekly_summary
        data = await generate_weekly_summary(current_user_id, week, openai, db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid week format: {exc}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not generate weekly summary: {type(exc).__name__}",
        ) from exc

    return WeeklySummaryOut(**data)


# ---------------------------------------------------------------------------
# GET /api/insights/graph
# ---------------------------------------------------------------------------

_GRAPH_NODE_CAP = 200


@insights_router.get("/graph", response_model=GraphOut)
async def get_graph(
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GraphOut:
    """
    Return force-directed graph data from notes + note_links.
    Nodes are capped at 200 (most recently created first).
    """
    # Fetch up to 200 notes (newest first) to use as nodes
    notes_result = await db.execute(
        select(Note)
        .where(Note.user_id == current_user_id)
        .order_by(Note.created_at.desc())
        .limit(_GRAPH_NODE_CAP)
    )
    notes = list(notes_result.scalars().all())
    note_ids = {n.id for n in notes}

    nodes = [
        GraphNode(
            id=str(n.id),
            label=(n.summary or n.content[:60]) if (n.summary or n.content) else str(n.id),
            category=n.category,
        )
        for n in notes
    ]

    # Fetch links between those nodes
    if note_ids:
        links_result = await db.execute(
            select(NoteLink).where(
                NoteLink.source_note_id.in_(note_ids),
                NoteLink.target_note_id.in_(note_ids),
            )
        )
        links_orm = list(links_result.scalars().all())
    else:
        links_orm = []

    links = [
        GraphLink(
            source=str(lnk.source_note_id),
            target=str(lnk.target_note_id),
            score=lnk.similarity_score,
        )
        for lnk in links_orm
    ]

    return GraphOut(nodes=nodes, links=links)


# ---------------------------------------------------------------------------
# GET /api/insights/patterns
# ---------------------------------------------------------------------------

@insights_router.get("/patterns", response_model=PatternsOut)
async def get_patterns(
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    openai: OpenAIDep,
) -> PatternsOut:
    """
    Use GPT-4o-mini to detect themes/patterns across the last 14 days of notes.
    Returns { patterns: [{theme, evidence_note_ids}] }.
    """
    cutoff = datetime.utcnow() - timedelta(days=14)
    notes_result = await db.execute(
        select(Note).where(
            Note.user_id == current_user_id,
            Note.created_at >= cutoff,
        ).order_by(Note.created_at.desc()).limit(100)
    )
    notes = list(notes_result.scalars().all())

    if not notes:
        return PatternsOut(patterns=[])

    # Build summarised note list
    note_lines = []
    for n in notes:
        snippet = (n.summary or n.content or "")[:120].replace("\n", " ")
        note_lines.append(f'[id={n.id}][{n.category}] {snippet}')
    notes_block = "\n".join(note_lines)

    prompt = (
        "You are a personal knowledge assistant analysing a user's recent notes.\n"
        "Identify 3–6 recurring themes or patterns across these notes.\n"
        "For each pattern, list the note IDs that are evidence for it.\n\n"
        "Return ONLY a JSON object with a single key 'patterns', which is an array.\n"
        "Each element must have:\n"
        "  - 'theme': a concise theme label (< 10 words)\n"
        "  - 'evidence_note_ids': array of UUIDs (from the [id=…] values)\n\n"
        f"Recent notes (last 14 days):\n{notes_block}\n\n"
        "JSON:"
    )

    response = await openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.5,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
        patterns_raw = data.get("patterns", [])
    except (json.JSONDecodeError, AttributeError):
        patterns_raw = []

    # Validate structure
    patterns: list[PatternItem] = []
    valid_ids = {str(n.id) for n in notes}
    for item in patterns_raw:
        if not isinstance(item, dict):
            continue
        theme = str(item.get("theme", ""))
        evidence_ids = [
            eid for eid in item.get("evidence_note_ids", [])
            if isinstance(eid, str) and eid in valid_ids
        ]
        if theme:
            patterns.append(PatternItem(theme=theme, evidence_note_ids=evidence_ids))

    return PatternsOut(patterns=patterns)


# ---------------------------------------------------------------------------
# POST /api/ai/generate  (Express)
# ---------------------------------------------------------------------------

_KIND_PROMPTS: dict[str, str] = {
    "song": (
        "You are a creative music-writing assistant for a musician's second brain.\n"
        "Based on the following notes, generate a rough song idea: title, mood, "
        "key themes, 2–3 verse concepts, and a chorus hook.\n"
        "Keep it inspiring, concise, and creative.\n\n"
    ),
    "practice": (
        "You are a music practice coach.\n"
        "Based on the following notes, create a focused practice plan for the next session: "
        "warm-up (5 min), core technique exercises (15 min), repertoire work (10 min), "
        "and a reflection prompt.\n\n"
    ),
    "reflection": (
        "You are a thoughtful journaling guide.\n"
        "Based on the following notes, write a personal reflection: "
        "acknowledge what was captured, surface an insight, and pose one deep question.\n"
        "Tone: warm, curious, grounded. 3–4 sentences.\n\n"
    ),
}


@ai_summary_router.post("/generate", response_model=GenerateOut)
async def generate_express(
    payload: GenerateRequest,
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    openai: OpenAIDep,
) -> GenerateOut:
    """
    Express generator: produce a song idea, practice plan, or reflection from
    selected notes.

    FR-2.6/2.7/2.8 — kind must be 'song', 'practice', or 'reflection'.
    """
    kind = payload.kind
    if kind not in _KIND_PROMPTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid kind {kind!r}. Must be one of: song, practice, reflection.",
        )

    if not payload.source_note_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="source_note_ids must not be empty.",
        )

    # Fetch source notes (ownership check implicit — filter by user_id)
    try:
        source_uuids = [uuid.UUID(sid) for sid in payload.source_note_ids]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID in source_note_ids: {exc}",
        ) from exc

    notes_result = await db.execute(
        select(Note).where(
            Note.id.in_(source_uuids),
            Note.user_id == current_user_id,
        )
    )
    notes = list(notes_result.scalars().all())

    if not notes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No accessible notes found for the given source_note_ids.",
        )

    # Build notes block
    note_lines = [
        f"[{n.category}] {(n.content or '').strip()}"
        for n in notes
        if n.content
    ]
    notes_block = "\n\n".join(note_lines)
    system_prompt = _KIND_PROMPTS[kind]
    full_prompt = system_prompt + f"Notes:\n{notes_block}\n\nGenerate:"

    response = await openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": full_prompt}],
        max_tokens=700,
        temperature=0.8,
    )
    generated_text = (response.choices[0].message.content or "").strip()

    logger.info(
        "express_generate: user_id=%s kind=%s notes=%d",
        current_user_id, kind, len(notes),
    )
    return GenerateOut(generated_text=generated_text)
