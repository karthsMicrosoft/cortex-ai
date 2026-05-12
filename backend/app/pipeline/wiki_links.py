"""
Wiki-link parser — Phase 6 / PR 6.5.

Parses ``[[Title]]`` style references from a note's content and creates
``note_links`` rows of type ``'wiki'`` to the resolved target notes.

Resolution rules (per PR 6.5 spec):
  - Match the same user's notes only.
  - A ref resolves when exactly one note has ``lower(title) == lower(ref)``
    OR has an alias whose lowercase matches ``lower(ref)``.
  - 0 matches → unresolved.
  - 2+ matches → unresolved (ambiguous; do NOT pick most recent).
  - The source note itself is skipped (not counted as resolved or unresolved).
  - Idempotent: existing wiki links are preserved (no duplicate creation).

Public API:
    await parse_and_link_wiki_refs(db, source_note) -> WikiLinkResult
"""
from __future__ import annotations

import logging
import re
from typing import List, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note
from app.models.note_link import NoteLink

logger = logging.getLogger(__name__)

# Regex: [[<anything that isn't a closing bracket or a newline>]]
WIKI_REF_RE = re.compile(r"\[\[([^\]\n]+)\]\]")


class WikiLinkResult(TypedDict):
    resolved: int
    unresolved: int
    links_created: int
    unresolved_titles: List[str]


def _extract_refs(content: str | None) -> List[str]:
    """Return de-whitespaced wiki refs in source order (duplicates preserved)."""
    if not content:
        return []
    return [m.strip() for m in WIKI_REF_RE.findall(content) if m and m.strip()]


async def parse_and_link_wiki_refs(
    db: AsyncSession, source_note: Note
) -> WikiLinkResult:
    """Parse [[Title]] refs and create wiki links to resolved targets.

    Idempotent. Safe to call repeatedly (existing wiki links survive).
    """
    refs = _extract_refs(source_note.content)
    result: WikiLinkResult = {
        "resolved": 0,
        "unresolved": 0,
        "links_created": 0,
        "unresolved_titles": [],
    }

    if not refs:
        return result

    # Fetch every candidate note for this user (excluding the source note).
    # SQLite tests use JSON for aliases; Postgres uses TEXT[]. To stay
    # portable we do the case-insensitive match in Python — fine for the
    # per-user note volume we expect (hundreds, not millions).
    rows = (
        await db.execute(
            select(Note.id, Note.title, Note.aliases).where(
                Note.user_id == source_note.user_id,
                Note.id != source_note.id,
            )
        )
    ).all()
    candidates = [(r[0], r[1], r[2] or []) for r in rows]

    source_title_lower = (source_note.title or "").strip().lower() or None

    for ref in refs:
        ref_lower = ref.lower()

        # Self-reference: skip silently (don't count as unresolved either).
        if source_title_lower and ref_lower == source_title_lower:
            continue

        # Find matching candidates (deduped by id).
        matches: list = []
        for cid, ctitle, caliases in candidates:
            if ctitle and ctitle.lower() == ref_lower:
                matches.append(cid)
                continue
            for alias in caliases:
                if isinstance(alias, str) and alias.lower() == ref_lower:
                    matches.append(cid)
                    break
        matches = list(dict.fromkeys(matches))

        if len(matches) != 1:
            result["unresolved"] += 1
            result["unresolved_titles"].append(ref)
            continue

        # Exactly one resolution. Idempotent insert.
        target_id = matches[0]
        result["resolved"] += 1

        existing = (
            await db.execute(
                select(NoteLink.id).where(
                    NoteLink.source_note_id == source_note.id,
                    NoteLink.target_note_id == target_id,
                    NoteLink.link_type == "wiki",
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue

        link = NoteLink(
            source_note_id=source_note.id,
            target_note_id=target_id,
            similarity_score=1.0,  # wiki refs are explicit, full-confidence
            link_type="wiki",
        )
        db.add(link)
        try:
            await db.flush()
            result["links_created"] += 1
        except Exception as exc:  # noqa: BLE001
            # Race against another writer for the same triple — safe to ignore.
            logger.debug(
                "wiki_link_insert_skipped: source=%s target=%s error_class=%s",
                source_note.id,
                target_id,
                type(exc).__name__,
            )
            await db.rollback()

    return result
