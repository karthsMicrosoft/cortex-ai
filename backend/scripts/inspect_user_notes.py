"""Per-user inspection: notes broken down by processing_status + content snippet.

Run via:
    az containerapp exec --name cortexks-api --resource-group cortex-rg \
        --command "python -m scripts.inspect_user_notes --email <user>"
"""
from __future__ import annotations

import argparse
import asyncio
import sys


async def main(email: str, pattern: str | None) -> int:
    from sqlalchemy import select, func, or_
    from app.database import SessionLocal
    from app.models.note import Note
    from app.models.user import User

    async with SessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            print(f"User {email!r} not found", file=sys.stderr)
            return 1

        print(f"User: {user.email}  id={user.id}")
        rows = (
            await db.execute(
                select(Note.processing_status, func.count(), func.count(Note.embedding))
                .where(Note.user_id == user.id)
                .group_by(Note.processing_status)
            )
        ).all()
        print("Breakdown by processing_status (count / with_embedding):")
        for status, total, with_emb in rows:
            print(f"  {status:14}  total={total:4}  with_embedding={with_emb}")

        if pattern:
            results = (
                await db.execute(
                    select(Note.id, Note.title, Note.processing_status,
                           Note.embedding.is_not(None).label("has_emb"))
                    .where(Note.user_id == user.id)
                    .where(or_(Note.content.ilike(f"%{pattern}%"),
                               Note.title.ilike(f"%{pattern}%")))
                )
            ).all()
            print(f"Notes matching {pattern!r} ({len(results)}):")
            for nid, title, status, has_emb in results:
                emb_note = "yes" if has_emb else "MISSING"
                title_disp = (title or "(no title)")[:60]
                print(f"  status={status:12}  emb={emb_note}  title={title_disp}  id={nid}")
    return 0


def cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--pattern", default=None,
                    help="Substring to filter title/content by (case-insensitive).")
    args = ap.parse_args()
    return asyncio.run(main(args.email, args.pattern))


if __name__ == "__main__":
    sys.exit(cli())
