"""
Distill stage — daily and weekly summary generation (CODE framework: Distill).

Public API:
    generate_daily_summary(user_id, target_date, openai_client, db) → DailySummary
    generate_weekly_summary(user_id, iso_week, openai_client, db) → dict
    run_daily_distill()   — APScheduler entry point (no args, single-user MVP)
    run_weekly_distill()  — APScheduler entry point (no args, single-user MVP)

Spec reference: § 2.5
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, timedelta
from typing import Optional

from openai import AsyncAzureOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_summary import DailySummary
from app.models.note import Note

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Core summarisation helpers
# ---------------------------------------------------------------------------

def _build_daily_prompt(notes: list[Note]) -> str:
    """Build the GPT-4o-mini prompt for a daily summary."""
    lines = []
    for n in notes:
        category = n.category or "Unknown"
        content = (n.content or "").strip()
        if content:
            lines.append(f"[{category}] {content}")
    notes_block = "\n".join(lines) if lines else "(no notes)"
    return (
        "You are a personal knowledge assistant helping the user review their day.\n"
        "Summarise the following notes captured today into a concise daily recap.\n"
        "Rules:\n"
        "- Write 3–5 sentences max.\n"
        "- Highlight key themes, ideas, and emotions.\n"
        "- End with one actionable insight or question to consider.\n"
        "- Return ONLY the summary text, no headings.\n\n"
        f"Today's notes:\n{notes_block}\n\n"
        "Summary:"
    )


def _build_weekly_prompt(daily_summaries: list[DailySummary], notes: list[Note]) -> str:
    """Build the GPT-4o-mini prompt for a weekly summary."""
    if daily_summaries:
        # Prefer aggregating daily summaries
        lines = []
        for ds in daily_summaries:
            lines.append(f"[{ds.summary_date}] {ds.summary_text}")
        block = "\n".join(lines)
        source = "daily summaries"
    else:
        # Fall back to raw notes
        lines = []
        for n in notes:
            content = (n.content or "").strip()
            if content:
                lines.append(f"[{n.category}] {content}")
        block = "\n".join(lines) if lines else "(no notes)"
        source = "notes"

    return (
        "You are a personal knowledge assistant helping the user reflect on their week.\n"
        f"Based on the following {source}, write a weekly recap.\n"
        "Rules:\n"
        "- Write 5–8 sentences.\n"
        "- Identify recurring themes, progress, and patterns across categories.\n"
        "- End with 2 forward-looking questions or intentions for the coming week.\n"
        "- Return ONLY the recap text, no headings.\n\n"
        f"This week's {source}:\n{block}\n\n"
        "Weekly recap:"
    )


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

async def generate_daily_summary(
    user_id,
    target_date: date,
    openai_client: AsyncAzureOpenAI,
    db: AsyncSession,
) -> DailySummary:
    """
    Fetch all user notes for *target_date*, call GPT-4o-mini, upsert into
    `daily_summaries`, and return the ORM object.

    Spec § 2.5: max_tokens=800, temperature=0.7.
    """
    import uuid as _uuid
    if not isinstance(user_id, _uuid.UUID):
        user_id = _uuid.UUID(str(user_id))

    # Fetch notes created on target_date
    day_start = target_date
    day_end = target_date + timedelta(days=1)

    result = await db.execute(
        select(Note).where(
            Note.user_id == user_id,
            Note.created_at >= str(day_start),
            Note.created_at < str(day_end),
        )
    )
    notes = list(result.scalars().all())

    prompt = _build_daily_prompt(notes)

    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
        temperature=0.7,
    )
    summary_text = (response.choices[0].message.content or "").strip()

    # Extract themes via a lightweight heuristic (first 5 category names seen)
    categories_seen: list[str] = []
    for n in notes:
        if n.category and n.category not in categories_seen:
            categories_seen.append(n.category)
    key_themes = categories_seen[:5]

    # Upsert: check if a row already exists for (user_id, target_date)
    existing_result = await db.execute(
        select(DailySummary).where(
            DailySummary.user_id == user_id,
            DailySummary.summary_date == target_date,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.summary_text = summary_text
        existing.key_themes = key_themes
        existing.note_count = len(notes)
        await db.commit()
        await db.refresh(existing)
        logger.info(
            "distill_daily_updated: user_id=%s date=%s notes=%d",
            user_id, target_date, len(notes),
        )
        return existing
    else:
        summary = DailySummary(
            user_id=user_id,
            summary_date=target_date,
            summary_text=summary_text,
            key_themes=key_themes,
            note_count=len(notes),
        )
        db.add(summary)
        await db.commit()
        await db.refresh(summary)
        logger.info(
            "distill_daily_created: user_id=%s date=%s notes=%d",
            user_id, target_date, len(notes),
        )
        return summary


async def generate_weekly_summary(
    user_id,
    iso_week: str,
    openai_client: AsyncAzureOpenAI,
    db: AsyncSession,
) -> dict:
    """
    Aggregate seven daily summaries (or raw notes) for *iso_week* into a
    higher-level weekly recap.

    *iso_week* format: "YYYY-WNN" e.g. "2026-W17".

    Returns a dict with keys: week, summary_text, daily_summaries, note_count.
    """
    import uuid as _uuid
    if not isinstance(user_id, _uuid.UUID):
        user_id = _uuid.UUID(str(user_id))

    # Parse ISO week string → Monday date of that week
    year_str, week_str = iso_week.split("-W")
    year = int(year_str)
    week_num = int(week_str)
    monday = date.fromisocalendar(year, week_num, 1)
    sunday = monday + timedelta(days=6)

    # Fetch existing daily summaries for the 7 days
    daily_result = await db.execute(
        select(DailySummary).where(
            DailySummary.user_id == user_id,
            DailySummary.summary_date >= monday,
            DailySummary.summary_date <= sunday,
        ).order_by(DailySummary.summary_date)
    )
    daily_summaries = list(daily_result.scalars().all())

    # Also fetch raw notes as fallback
    notes_result = await db.execute(
        select(Note).where(
            Note.user_id == user_id,
            Note.created_at >= str(monday),
            Note.created_at < str(sunday + timedelta(days=1)),
        )
    )
    notes = list(notes_result.scalars().all())

    prompt = _build_weekly_prompt(daily_summaries, notes)

    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
        temperature=0.7,
    )
    weekly_text = (response.choices[0].message.content or "").strip()

    total_note_count = sum(ds.note_count for ds in daily_summaries) or len(notes)

    return {
        "week": iso_week,
        "summary_text": weekly_text,
        "daily_summaries": [
            {
                "date": str(ds.summary_date),
                "summary_text": ds.summary_text,
                "note_count": ds.note_count,
            }
            for ds in daily_summaries
        ],
        "note_count": total_note_count,
    }


# ---------------------------------------------------------------------------
# APScheduler entry points (single-user MVP)
# ---------------------------------------------------------------------------

def run_daily_distill() -> None:
    """
    APScheduler cron entry point — runs nightly at 23:59.
    Generates daily summaries for every user in the database.
    """

    async def _inner() -> None:
        from app.database import SessionLocal
        from app.models.user import User
        from app.services.openai_client import get_openai_client

        openai_client = get_openai_client()
        today = date.today()

        async with SessionLocal() as db:
            result = await db.execute(select(User))
            users = result.scalars().all()
            for user in users:
                try:
                    await generate_daily_summary(user.id, today, openai_client, db)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "run_daily_distill_error: user_id=%s error_class=%s",
                        user.id, type(exc).__name__,
                    )

    asyncio.run(_inner())


def run_weekly_distill() -> None:
    """
    APScheduler cron entry point — runs every Sunday at 23:59.
    Generates weekly summaries for every user.
    """

    async def _inner() -> None:
        from app.database import SessionLocal
        from app.models.user import User
        from app.services.openai_client import get_openai_client

        openai_client = get_openai_client()
        today = date.today()
        iso_cal = today.isocalendar()
        iso_week = f"{iso_cal[0]}-W{iso_cal[1]:02d}"

        async with SessionLocal() as db:
            result = await db.execute(select(User))
            users = result.scalars().all()
            for user in users:
                try:
                    await generate_weekly_summary(user.id, iso_week, openai_client, db)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "run_weekly_distill_error: user_id=%s error_class=%s",
                        user.id, type(exc).__name__,
                    )

    asyncio.run(_inner())
