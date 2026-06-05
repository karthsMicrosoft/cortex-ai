"""Round 39 one-off cleanup: clear due_at values that the LLM hallucinated
into the past (before R39's fix added current-date context to the prompt).

Run: python -m scripts.cleanup_past_due_at --email <user-email>

Idempotent: only clears due_at on notes WHERE due_at < cutoff (default: 2026-01-01).
Re-pipeline can re-fill them correctly because Round 39 now passes the current
date + timezone to the LLM.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cleanup_past_due_at")


async def cleanup(email: str, cutoff_iso: str, dry_run: bool = False) -> int:
    from sqlalchemy import select

    import app.database as database
    from app.models.note import Note
    from app.models.user import User

    cutoff = datetime.fromisoformat(cutoff_iso)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)

    async with database.SessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            print(f"User {email} not found", file=sys.stderr)
            return 1

        bad = list(
            (
                await db.execute(
                    select(Note).where(Note.user_id == user.id, Note.due_at.is_not(None), Note.due_at < cutoff)
                )
            ).scalars().all()
        )
        logger.info("Found %d notes with due_at < %s for %s", len(bad), cutoff.isoformat(), email)
        for n in bad:
            content = (n.content or "")[:80]
            logger.info("  id=%s title=%r due_at=%s content=%r", n.id, n.title, n.due_at, content)

        if dry_run:
            logger.info("dry_run=True, no changes written")
            return 0

        for n in bad:
            n.due_at = None
            n.reminder_sent_at = None
        await db.commit()
        logger.info("Cleared due_at on %d notes", len(bad))
        return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Clear hallucinated past due_at values for one user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--cutoff", default="2026-01-01T00:00:00+00:00",
                        help="ISO timestamp; notes with due_at strictly less than this are cleared")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    return asyncio.run(cleanup(args.email, args.cutoff, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
