"""
One-time migration: transcode existing .webm audio blobs to .m4a (AAC) for Safari playback.

Bug 27 fix (Round 8): iOS Safari has zero WebM container support. Audio stored in
Blob Storage as audio/webm silently fails to play on iPhone. This script re-encodes
all existing notes whose audio_url references a .webm blob into M4A/AAC and updates
the notes.audio_url column to point at the new blob.

Idempotent: rows whose audio_url already ends in .m4a (or contains .m4a?) are skipped.

Run instructions (Lead runs post-deploy):
    az containerapp exec \\
        --name cortexks-api \\
        --resource-group cortex-rg \\
        --command "python scripts/migrate_audio_to_m4a.py"

The script exits cleanly on completion. Non-fatal row errors are logged and skipped
so a partial run can be resumed safely (already-migrated rows are skipped by the
idempotency guard).

Requirements (satisfied inside the Container App):
- DATABASE_URL env var (or settings.DATABASE_URL from app.config)
- AZURE_STORAGE_CONNECTION_STRING and AZURE_STORAGE_CONTAINER env vars
- ffmpeg in PATH (present in the Docker image since Round 4 / DECISIONS.md § 22n)
"""

import asyncio
import logging
import os
import sys
import tempfile
import urllib.request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def migrate() -> None:
    # Import app internals only after the module path is set up.
    from sqlalchemy import text
    from app.config import settings
    from app.database import SessionLocal
    from app.services.blob_storage import upload_blob
    from app.services.speech import _transcode_to_m4a, _write_temp

    async with SessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT id, audio_url FROM notes "
                    "WHERE audio_url IS NOT NULL "
                    "AND (audio_url LIKE '%.webm%' OR audio_url LIKE '%.ogg%')"
                )
            )
        ).fetchall()

    logger.info("Found %d rows to potentially migrate.", len(rows))

    migrated = 0
    skipped = 0
    failed = 0

    for row in rows:
        note_id = row[0]
        audio_url: str = row[1]

        # Idempotency: skip rows already pointing at an M4A blob.
        if ".m4a" in audio_url:
            logger.info("[SKIP] note=%s already has .m4a URL", note_id)
            skipped += 1
            continue

        logger.info("[START] note=%s  url=%s", note_id, audio_url[:80])

        # Download the existing blob (SAS URL — public read for 24h).
        src_path: str | None = None
        m4a_path: str | None = None
        try:
            # Strip SAS query params to get the bare blob path for re-upload key.
            # URL format: https://<account>.blob.core.windows.net/<container>/<path>?<sas>
            url_no_qs = audio_url.split("?")[0]
            # Derive blob_path: everything after <container>/
            container = settings.AZURE_STORAGE_CONTAINER
            marker = f"/{container}/"
            if marker not in url_no_qs:
                logger.warning("[SKIP] note=%s cannot parse blob path from URL", note_id)
                skipped += 1
                continue
            old_blob_path = url_no_qs.split(marker, 1)[1]

            # Determine source extension from blob path.
            _, src_ext = os.path.splitext(old_blob_path.split("?")[0])
            src_ext = src_ext or ".webm"

            # Download blob bytes via the SAS URL.
            with urllib.request.urlopen(audio_url, timeout=120) as resp:  # noqa: S310
                audio_bytes = resp.read()

            # Write to temp, transcode, read m4a bytes.
            src_path = _write_temp(audio_bytes, suffix=src_ext)
            m4a_path = _transcode_to_m4a(src_path)
            with open(m4a_path, "rb") as fh:
                m4a_bytes = fh.read()

            # Derive new blob key: replace extension with .m4a.
            base_blob = os.path.splitext(old_blob_path)[0]
            new_blob_path = base_blob + ".m4a"

            # Upload M4A blob.
            new_url = await upload_blob(
                container=container,
                blob_path=new_blob_path,
                data=m4a_bytes,
                content_type="audio/mp4",
            )

            # Update the DB row.
            async with SessionLocal() as db:
                await db.execute(
                    text("UPDATE notes SET audio_url = :url WHERE id = :id"),
                    {"url": new_url, "id": note_id},
                )
                await db.commit()

            logger.info("[DONE] note=%s  new_url=%s", note_id, new_url[:80])
            migrated += 1

        except Exception as exc:  # noqa: BLE001
            logger.error("[FAIL] note=%s  err=%s", note_id, exc)
            failed += 1
        finally:
            for path in (src_path, m4a_path):
                if path is not None:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

    logger.info(
        "Migration complete. migrated=%d  skipped=%d  failed=%d",
        migrated,
        skipped,
        failed,
    )
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    # Add the backend/app directory to sys.path so app.* imports resolve when
    # the script is run from the container with cwd=/app or cwd=/app/scripts.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(script_dir)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    asyncio.run(migrate())
