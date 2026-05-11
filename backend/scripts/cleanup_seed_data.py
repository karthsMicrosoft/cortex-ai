"""
Cleanup dummy seed notes inserted by ``seed_dummy_data.py``.

Phase 4 / Round 16 / PR 4.0b. Removes every note for a user that carries the
``seed:r16`` tag (and removes the join rows in ``note_tags``). Tag rows
themselves are preserved because tags are user-scoped and may be referenced
by other notes.

Usage:

    PYTHONIOENCODING=utf-8 az containerapp exec \\
        --name cortexks-api \\
        --resource-group cortex-rg \\
        --command "python scripts/cleanup_seed_data.py karths@microsoft.com"
"""
import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

SEED_TAG = "seed:r16"


async def cleanup(email: str) -> int:
    from sqlalchemy import delete, select
    from app.database import SessionLocal
    from app.models.note import Note
    from app.models.tag import Tag, note_tags
    from app.models.user import User

    async with SessionLocal() as db:
        user_row = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user_row is None:
            logger.error("User with email=%s not found. Aborting.", email)
            return 1

        seed_tag = (
            await db.execute(
                select(Tag).where(Tag.user_id == user_row.id, Tag.name == SEED_TAG)
            )
        ).scalar_one_or_none()

        if seed_tag is None:
            logger.info("No '%s' tag found for user %s. Nothing to clean.", SEED_TAG, email)
            print(f"Cleaned up 0 notes tagged {SEED_TAG} for {email}")
            return 0

        # Find all notes for this user that carry the seed tag.
        note_ids = (
            await db.execute(
                select(Note.id)
                .join(note_tags, note_tags.c.note_id == Note.id)
                .where(Note.user_id == user_row.id, note_tags.c.tag_id == seed_tag.id)
            )
        ).scalars().all()

        if not note_ids:
            logger.info("No notes carry the '%s' tag for user %s.", SEED_TAG, email)
            print(f"Cleaned up 0 notes tagged {SEED_TAG} for {email}")
            return 0

        logger.info("Deleting %d seeded notes for user %s", len(note_ids), email)

        # Drop join rows first to avoid orphaning, then the notes themselves.
        # (The notes table FK has ON DELETE CASCADE for note_tags so the second
        # DELETE alone would suffice; we do both for clarity and defense in
        # depth.)
        await db.execute(
            delete(note_tags).where(note_tags.c.note_id.in_(note_ids))
        )
        await db.execute(delete(Note).where(Note.id.in_(note_ids)))
        await db.commit()

        logger.info(
            "Cleaned up %d notes tagged %s for %s",
            len(note_ids),
            SEED_TAG,
            email,
        )
        print(
            f"Cleaned up {len(note_ids)} notes tagged {SEED_TAG} for {email}"
        )

    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python cleanup_seed_data.py <user-email>", file=sys.stderr)
        sys.exit(2)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(script_dir)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    sys.exit(asyncio.run(cleanup(sys.argv[1])))
