"""Debug script for Round 16 - investigate why /api/search returns 503.

Run via: az containerapp exec --command "python scripts/debug_search.py"
"""
import asyncio
from app.database import SessionLocal
from sqlalchemy import text


async def main():
    async with SessionLocal() as db:
        # Test 1: pgvector extension present?
        try:
            r = await db.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))
            row = r.fetchone()
            print(f"[1] pg_extension vector: {row.extname if row else 'MISSING'}")
        except Exception as e:
            print(f"[1] FAIL: {type(e).__name__}: {e}")

        # Test 2: notes count + embedding count
        try:
            r = await db.execute(text("SELECT COUNT(*) AS total, COUNT(embedding) AS with_emb FROM notes"))
            row = r.fetchone()
            print(f"[2] notes total={row.total} with_embedding={row.with_emb}")
        except Exception as e:
            print(f"[2] FAIL: {type(e).__name__}: {e}")

        # Test 3: embedding column type
        try:
            r = await db.execute(text(
                "SELECT data_type, udt_name FROM information_schema.columns "
                "WHERE table_name='notes' AND column_name='embedding'"
            ))
            row = r.fetchone()
            print(f"[3] embedding column type: data_type={row.data_type if row else 'NONE'} udt={row.udt_name if row else 'NONE'}")
        except Exception as e:
            print(f"[3] FAIL: {type(e).__name__}: {e}")

        # Test 4: replicate the search query exactly
        try:
            sample_emb = "[" + ",".join("0.1" for _ in range(1536)) + "]"
            sql = text(
                "SELECT n.id, "
                "(1 - (n.embedding <=> CAST(:q_emb AS vector))) AS s "
                "FROM notes n "
                "WHERE n.embedding IS NOT NULL "
                "LIMIT 1"
            )
            r = await db.execute(sql, {"q_emb": sample_emb})
            row = r.fetchone()
            print(f"[4] minimal vector search: {row.id if row else 'NO_ROW'}")
        except Exception as e:
            print(f"[4] FAIL: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
