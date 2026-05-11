"""
Seed dummy notes for a Cortex Second Brain test account.

Phase 4 / Round 16 / PR 4.0b. Adds ~75 hand-curated notes to a single user
account so that Phase 4 features (RAG, search filters, Brain View, wiki-link
demos) have a richer corpus to work against. Curated content lives in
``scripts/seed_data/notes.json``.

Usage (post-deploy, inside the live container):

    PYTHONIOENCODING=utf-8 az containerapp exec \\
        --name cortexks-api \\
        --resource-group cortex-rg \\
        --command "python scripts/seed_dummy_data.py karths@microsoft.com"

Behavior:
- Looks up the user by email; exits 1 if not found.
- Loads ``scripts/seed_data/notes.json`` (75 records).
- For each record, idempotently inserts a note: skips if a note with the same
  ``client_id`` already exists for the user.
- ``processing_status`` is set to ``'enriched'`` so the seeded notes appear as
  fully processed in the UI without round-tripping the AI pipeline.
- ``created_at`` is back-dated by ``days_ago`` so the notes form a realistic
  time spread across the past ~90 days.
- Tags are upserted into the user-scoped ``tags`` table and linked via
  ``note_tags``. Every seeded note also gets the ``seed:r16`` tag so that
  ``cleanup_seed_data.py`` can find and remove them later.

Embeddings: this script intentionally does NOT call the embedding pipeline.
That path requires async Azure OpenAI calls and a working network egress from
the script context. The seeded notes are inserted with ``embedding = NULL``;
PR 4.0a's NULL-handling fix in the search ranker keeps them out of the
top-K vector results until embeddings are backfilled. Backfill can be done
later via the existing pipeline (e.g., re-run the enrichment task on these
note IDs) without re-touching this script.

Idempotent: re-running the script is safe. Existing seeded notes (matched by
``client_id``) are skipped.
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

SEED_TAG = "seed:r16"
SEED_JSON_PATH = Path(__file__).parent / "seed_data" / "notes.json"


async def seed(email: str) -> int:
    """Seed dummy notes for ``email``. Returns process exit code."""
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models.note import Note
    from app.models.tag import Tag
    from app.models.user import User

    if not SEED_JSON_PATH.exists():
        logger.error("Seed JSON not found at %s", SEED_JSON_PATH)
        return 1

    with open(SEED_JSON_PATH, encoding="utf-8") as fh:
        seed_records = json.load(fh)

    logger.info("Loaded %d seed records from %s", len(seed_records), SEED_JSON_PATH)

    async with SessionLocal() as db:
        user_row = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user_row is None:
            logger.error("User with email=%s not found. Aborting.", email)
            return 1
        logger.info("Found user id=%s email=%s", user_row.id, user_row.email)

        # Cache user-scoped tags so we don't issue a SELECT per note per tag.
        existing_tags = (
            await db.execute(select(Tag).where(Tag.user_id == user_row.id))
        ).scalars().all()
        tag_cache: dict[str, Tag] = {t.name: t for t in existing_tags}

        async def get_or_create_tag(name: str) -> Tag:
            if name in tag_cache:
                return tag_cache[name]
            tag = Tag(user_id=user_row.id, name=name, is_auto=False)
            db.add(tag)
            await db.flush()
            tag_cache[name] = tag
            return tag

        seeded = 0
        skipped = 0

        for rec in seed_records:
            client_id = rec["client_id"]

            # Idempotency: skip if this client_id already exists for the user.
            existing = (
                await db.execute(
                    select(Note).where(
                        Note.user_id == user_row.id,
                        Note.client_id == client_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                skipped += 1
                continue

            note = Note(
                user_id=user_row.id,
                content=rec["content"],
                category=rec["category"],
                source_type=rec.get("source_type", "text"),
                processing_status="enriched",
                client_id=client_id,
            )
            db.add(note)
            await db.flush()  # populate note.id
            # Avoid the async lazy-load that "if tag not in note.tags" would trigger:
            # the note was just created, so tags is empty by definition.
            note.tags = []

            # Back-date created_at to spread the corpus across time.
            days_ago = int(rec.get("days_ago", 0))
            if days_ago > 0:
                # Use a parameterised UPDATE - dialect-agnostic via interval expression.
                from sqlalchemy import text as sql_text
                await db.execute(
                    sql_text(
                        "UPDATE notes "
                        "SET created_at = NOW() - make_interval(days => :days), "
                        "    updated_at = NOW() - make_interval(days => :days) "
                        "WHERE id = :id"
                    ),
                    {"days": days_ago, "id": note.id},
                )

            tag_names = list(rec.get("tags", []))
            if SEED_TAG not in tag_names:
                tag_names.append(SEED_TAG)

            for tag_name in tag_names:
                tag = await get_or_create_tag(tag_name)
                note.tags.append(tag)

            seeded += 1

        await db.commit()

        logger.info(
            "Seeded %d notes for user %s (skipped %d duplicates)",
            seeded,
            email,
            skipped,
        )
        print(
            f"Seeded {seeded} notes for user {email} (skipped {skipped} duplicates)"
        )

    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python seed_dummy_data.py <user-email>", file=sys.stderr)
        sys.exit(2)

    # Ensure ``app.*`` imports resolve when running with cwd=/app or /app/scripts.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(script_dir)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    sys.exit(asyncio.run(seed(sys.argv[1])))
