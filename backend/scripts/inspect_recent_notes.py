"""Round 39 diagnostic: list this user's recent notes + status + due_at."""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import desc, select


async def main(email: str, limit: int) -> int:
    import app.database as database
    from app.models.note import Note
    from app.models.user import User

    async with database.SessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            print(f"User {email} not found", file=sys.stderr)
            return 1
        notes = list(
            (
                await db.execute(
                    select(Note)
                    .where(Note.user_id == user.id)
                    .order_by(desc(Note.created_at))
                    .limit(limit)
                )
            ).scalars().all()
        )
        for n in notes:
            content = (n.content or "")[:80].replace("\n", " ")
            print(
                f"{n.created_at.isoformat()} status={n.processing_status:>10} due_at={n.due_at} "
                f"src={n.source_type:>5} title={n.title!r} content={content!r}"
            )
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.email, args.limit)))
