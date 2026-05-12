"""Backfill wiki links for notes belonging to a single user.

Run via: az containerapp exec --command \\
    "python -m scripts.backfill_wiki_links <user-email>"

Iterates every note for the user and re-parses ``[[Title]]`` refs in the
content, creating ``note_links`` rows of type ``'wiki'`` for resolutions
that don't already exist. Idempotent — existing wiki links survive.

Single-user only (takes an email arg) so the production rollout for the
4-feature initiative can be staged per account.
"""
import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_wiki_links")


async def backfill(email: str) -> int:
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.note import Note
    from app.models.user import User
    from app.pipeline.wiki_links import parse_and_link_wiki_refs

    async with SessionLocal() as db:
        user_row = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user_row is None:
            print(f"User {email} not found", file=sys.stderr)
            return 1

        note_ids = (
            await db.execute(select(Note.id).where(Note.user_id == user_row.id))
        ).scalars().all()
        logger.info("Found %d notes for %s", len(note_ids), email)

    total_resolved = 0
    total_unresolved = 0
    total_links_created = 0
    failed = 0
    processed = 0

    for nid in note_ids:
        try:
            async with SessionLocal() as task_db:
                note = (
                    await task_db.execute(select(Note).where(Note.id == nid))
                ).scalar_one_or_none()
                if note is None:
                    continue
                result = await parse_and_link_wiki_refs(task_db, note)
                await task_db.commit()
            total_resolved += result["resolved"]
            total_unresolved += result["unresolved"]
            total_links_created += result["links_created"]
            processed += 1
            if processed % 25 == 0:
                logger.info(
                    "Progress: %d/%d (links_created=%d)",
                    processed,
                    len(note_ids),
                    total_links_created,
                )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning("Failed note %s: %s", nid, exc)

    msg = (
        f"Wiki-link backfill done for {email}: "
        f"processed={processed} links_created={total_links_created} "
        f"resolved={total_resolved} unresolved={total_unresolved} failed={failed}"
    )
    logger.info(msg)
    print(msg)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            "Usage: python -m scripts.backfill_wiki_links <user-email>",
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(asyncio.run(backfill(sys.argv[1])))
