"""Backfill embeddings for notes that have embedding=NULL.

Run via: az containerapp exec --command "python -m scripts.backfill_embeddings <user-email>"

Used in Round 16 to backfill embeddings for the 75 notes the seed
script inserted with NULL embeddings.

Goes through the production AIPipeline.process_note path so links
+ tags + categorization stay consistent. Idempotent: skips notes
that already have embeddings.

Single-user only (takes an email arg) to avoid surprise costs.
"""
import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_embeddings")


async def backfill(email: str) -> int:
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models.note import Note
    from app.models.user import User
    from app.pipeline.processor import AIPipeline
    from app.services.openai_client import get_openai_client

    async with SessionLocal() as db:
        user_row = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user_row is None:
            print(f"User {email} not found", file=sys.stderr)
            return 1

        rows = (
            await db.execute(
                select(Note.id).where(
                    Note.user_id == user_row.id,
                    Note.embedding.is_(None),
                )
            )
        ).scalars().all()
        note_ids = list(rows)
        logger.info("Found %d notes needing embedding for %s", len(note_ids), email)

    backfilled = 0
    failed = 0
    for nid in note_ids:
        try:
            async with SessionLocal() as task_db:
                pipeline = AIPipeline(openai_client=get_openai_client(), db=task_db)
                await pipeline.process_note(nid)
            backfilled += 1
            if backfilled % 10 == 0:
                logger.info("Progress: %d/%d", backfilled, len(note_ids))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning("Failed note %s: %s", nid, exc)

    msg = f"Backfilled embeddings for {backfilled} notes ({failed} failed) for {email}"
    logger.info(msg)
    print(msg)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.backfill_embeddings <user-email>", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(backfill(sys.argv[1])))
