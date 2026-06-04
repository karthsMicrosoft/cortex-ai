"""Backfill generated titles for existing untitled notes belonging to one user.

Run via: python -m scripts.backfill_titles --email <user-email>

Single-user only to keep production backfills staged and bounded. Use
``--dry-run`` first to count notes that would be titled without OpenAI calls or
DB writes.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.services.openai_client import get_openai_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_titles")


async def backfill(
    email: str,
    dry_run: bool = False,
    limit_notes: int | None = None,
) -> int:
    from sqlalchemy import or_, select

    import app.database as database
    from app.models.note import Note
    from app.models.user import User

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
                or_(Note.title.is_(None), Note.title == ""),
                Note.content.is_not(None),
                Note.content != "",
            )
            .order_by(Note.created_at.desc())
        )
        if limit_notes is not None:
            stmt = stmt.limit(limit_notes)

        notes = list((await db.execute(stmt)).scalars().all())
        total = len(notes)
        logger.info("Found %d untitled notes for %s", total, email)

        if dry_run:
            print(f"would_title={total}")
            return 0

        openai = get_openai_client()
        titled = 0
        for note in notes:
            response = await openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": (
                        "Generate a short meaningful 3-8 word title that captures the essence of this note. "
                        "Return ONLY the title, no quotes, no markdown, no extra text.\n\n"
                        f"Note:\n{note.content}\n\nTitle:"
                    ),
                }],
                max_tokens=40,
                temperature=0.3,
            )
            raw = (response.choices[0].message.content or "").strip()
            if raw.startswith('"') and raw.endswith('"'):
                raw = raw[1:-1].strip()
            if raw:
                note.title = raw[:120]
            titled += 1

            if titled % 10 == 0:
                await db.commit()
                print(f"titled {titled}/{total}")

        if titled % 10 != 0:
            await db.commit()
        logger.info("Titled %d notes for %s", titled, email)
        return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill generated titles for one Cortex user."
    )
    parser.add_argument("--email", required=True, help="User email to backfill")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only count untitled notes; do not call OpenAI or write titles",
    )
    parser.add_argument(
        "--limit-notes",
        type=int,
        default=None,
        help="Optional maximum number of notes to title",
    )
    args = parser.parse_args(argv)

    return asyncio.run(
        backfill(args.email, dry_run=args.dry_run, limit_notes=args.limit_notes)
    )


if __name__ == "__main__":
    sys.exit(main())
