"""Backfill due_at / priority / recurring for existing notes belonging to one
user (Round 35).

Runs the regex extractor (free, fast) on each note's content. With ``--include-llm``,
also re-runs the AI pipeline for notes where the regex found nothing — useful
for fuzzy phrasing ("when I land", "before our trip") that only the LLM picks
up. Without ``--include-llm`` the script is a pure-CPU operation with no
Azure OpenAI cost.

Run via: ``python -m scripts.backfill_due_dates --email <user-email>``

Single-user only to keep production backfills bounded. ``--dry-run`` counts
what would change without writing.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_due_dates")


async def backfill(
    email: str,
    dry_run: bool = False,
    include_llm: bool = False,
    limit_notes: int | None = None,
    tz: str = "UTC",
) -> int:
    from sqlalchemy import or_, select

    import app.database as database
    from app.models.note import Note
    from app.models.user import User
    from app.services.deadline_extractor import extract

    async with database.SessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            print(f"User {email} not found", file=sys.stderr)
            return 1

        stmt = (
            select(Note)
            .where(
                Note.user_id == user.id,
                Note.due_at.is_(None),
                Note.content.is_not(None),
                Note.content != "",
            )
            .order_by(Note.created_at.desc())
        )
        if limit_notes is not None:
            stmt = stmt.limit(limit_notes)

        notes = list((await db.execute(stmt)).scalars().all())
        total = len(notes)
        logger.info("Found %d notes with no due_at for %s", total, email)

        regex_hits = llm_hits = unchanged = 0
        now = datetime.now(timezone.utc)

        for note in notes:
            result = extract(note.content or "", now=now, tz=tz)
            if result:
                if not dry_run:
                    if "due_at" in result and note.due_at is None:
                        raw_due = result["due_at"]
                        # `extract` returns datetime objects, but be tolerant
                        # of ISO strings for forward-compat with the TS port.
                        note.due_at = (
                            raw_due
                            if isinstance(raw_due, datetime)
                            else datetime.fromisoformat(raw_due)
                        )
                    if "priority" in result and note.priority is None:
                        note.priority = result["priority"]
                    if "recurring" in result and note.recurring is None:
                        note.recurring = result["recurring"]
                regex_hits += 1
            else:
                unchanged += 1

            if not dry_run and (regex_hits + llm_hits) % 25 == 0 and regex_hits + llm_hits > 0:
                await db.commit()
                print(f"processed {regex_hits + llm_hits}/{total}")

        if not dry_run:
            await db.commit()

        logger.info(
            "regex_hits=%d llm_hits=%d unchanged=%d (total=%d, dry_run=%s)",
            regex_hits, llm_hits, unchanged, total, dry_run,
        )

        # --include-llm pass: re-pipeline notes that regex missed AND have an
        # embedding (cheaper signal that the note is interesting). Uses the
        # existing AIPipeline._auto_tag_and_categorize which now also extracts
        # due_at via the LLM as a safety net.
        if include_llm and not dry_run:
            from app.pipeline.processor import AIPipeline
            from app.services.openai_client import get_openai_client

            misses = [n for n in notes if n.due_at is None]
            logger.info("LLM pass over %d regex-miss notes", len(misses))

            pipeline = AIPipeline(db, get_openai_client())
            for note in misses:
                try:
                    await pipeline._auto_tag_and_categorize(note)
                    if note.due_at is not None:
                        llm_hits += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("LLM pass failed for note %s: %s", note.id, exc)
                if llm_hits and llm_hits % 10 == 0:
                    await db.commit()
                    print(f"llm_filled {llm_hits}")
            await db.commit()
            logger.info("LLM pass filled %d additional due_at values", llm_hits)

        print(
            f"summary: total={total} regex_hits={regex_hits} llm_hits={llm_hits} "
            f"unchanged={unchanged} dry_run={dry_run}"
        )
        return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill due_at/priority/recurring for one Cortex user."
    )
    parser.add_argument("--email", required=True, help="User email to backfill")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only count what would change; no DB writes or OpenAI calls",
    )
    parser.add_argument(
        "--include-llm",
        action="store_true",
        help=(
            "After the regex pass, re-run the LLM extractor on notes that the "
            "regex missed (catches fuzzy phrasing). Costs OpenAI tokens."
        ),
    )
    parser.add_argument(
        "--tz",
        default="UTC",
        help="IANA tz name for date interpretation (default: UTC)",
    )
    parser.add_argument(
        "--limit-notes",
        type=int,
        default=None,
        help="Optional maximum number of notes to process",
    )
    args = parser.parse_args(argv)

    return asyncio.run(
        backfill(
            args.email,
            dry_run=args.dry_run,
            include_llm=args.include_llm,
            limit_notes=args.limit_notes,
            tz=args.tz,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
