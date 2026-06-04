"""Quick prod inspection — counts users + notes per user with/without embeddings.

Run via:
    az containerapp exec --name cortexks-api --resource-group cortex-rg \
        --command "python -m scripts.inspect_db"

One-shot operator script; safe to leave in the repo.
"""
import asyncio


async def main() -> None:
    from sqlalchemy import select, func
    from app.database import SessionLocal
    from app.models.note import Note
    from app.models.note_link import NoteLink
    from app.models.user import User

    async with SessionLocal() as db:
        users = (await db.execute(select(User.id, User.email))).all()
        print(f"Users ({len(users)}):")
        for u in users:
            note_count = await db.scalar(
                select(func.count()).select_from(Note).where(Note.user_id == u[0])
            )
            with_emb = await db.scalar(
                select(func.count())
                .select_from(Note)
                .where(Note.user_id == u[0])
                .where(Note.embedding.is_not(None))
            )
            link_count = await db.scalar(
                select(func.count())
                .select_from(NoteLink)
                .join(Note, NoteLink.source_note_id == Note.id)
                .where(Note.user_id == u[0])
            )
            print(
                f"  {u[1]:50}  notes={note_count}  with_emb={with_emb}  links={link_count}"
            )


if __name__ == "__main__":
    asyncio.run(main())
