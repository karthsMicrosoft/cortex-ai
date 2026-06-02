"""Backfill semantic links for notes belonging to a single user.

Run via: az containerapp exec --command \\
    "python -m scripts.backfill_semantic_links --email <user-email>"

Use this operator script after semantic-link scoring changes or when notes
already have embeddings but their ``note_links`` rows need to be rebuilt.
The user-facing relink endpoint rate limit is intentionally bypassed here
(``last_relink_window=0``) so production maintenance runs do not short-circuit.

Single-user only (takes an email arg) to keep production backfills staged and
bounded. Use ``--dry-run`` first to count that user's notes with embeddings.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.services.semantic_links import rebuild_user_links

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_semantic_links")


async def backfill(
    email: str,
    dry_run: bool = False,
    limit_notes: int | None = None,
) -> int:
    from sqlalchemy import func, select

    from app.database import SessionLocal
    from app.models.note import Note
    from app.models.user import User

    async with SessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            print(f"User {email} not found", file=sys.stderr)
            return 1

        if dry_run:
            notes_with_embeddings = (
                await db.execute(
                    select(func.count(Note.id)).where(
                        Note.user_id == user.id,
                        Note.embedding.is_not(None),
                    )
                )
            ).scalar_one()
            print(f"notes_with_embeddings={notes_with_embeddings}")
            return 0

        result = await rebuild_user_links(
            db,
            user.id,
            last_relink_window=0,
            limit_notes=limit_notes,
        )
        await db.commit()

    print(
        f"created={result.created} "
        f"updated={result.updated} "
        f"duration_ms={result.duration_ms}"
    )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill semantic note links for one Cortex user."
    )
    parser.add_argument("--email", required=True, help="User email to backfill")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only count notes with embeddings; do not rebuild links",
    )
    parser.add_argument(
        "--limit-notes",
        type=int,
        default=None,
        help="Optional maximum number of source notes to relink",
    )
    args = parser.parse_args(argv)

    return asyncio.run(
        backfill(args.email, dry_run=args.dry_run, limit_notes=args.limit_notes)
    )


if __name__ == "__main__":
    sys.exit(main())
