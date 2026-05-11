"""Debug script for Round 16 - investigate why /api/search returns 503.

Run via: az containerapp exec --command "python -m scripts.debug_search"
"""
import asyncio
from app.database import SessionLocal
from sqlalchemy import text


async def main():
    async with SessionLocal() as db:
        # Test the EXACT hybrid SQL that production uses
        sample_emb = "[" + ",".join("0.1" for _ in range(1536)) + "]"
        params = {
            "q_emb": sample_emb,
            "q_text": "leadership",
            "user_id": "94ee33c1-8901-4f1a-a683-a1909c9e2d91",  # karths user id from seed log
            "category": None,
            "date_from": None,
            "date_to": None,
            "tags": None,
            "limit": 5,
            "offset": 0,
        }
        sql = text("""
SELECT
  n.id, n.content, n.summary, n.category, n.created_at,
  (1 - (n.embedding <=> CAST(:q_emb AS vector)))                               AS semantic_score,
  ts_rank(to_tsvector('english', n.content),
          plainto_tsquery('english', :q_text))                                  AS text_score,
  0.7 * (1 - (n.embedding <=> CAST(:q_emb AS vector))) +
  0.3 * ts_rank(to_tsvector('english', n.content),
                plainto_tsquery('english', :q_text))                            AS combined_score
FROM notes n
WHERE n.user_id = :user_id
  AND n.embedding IS NOT NULL
  AND (:category   IS NULL OR n.category   = :category)
  AND (:date_from  IS NULL OR n.created_at >= :date_from)
  AND (:date_to    IS NULL OR n.created_at <= :date_to)
  AND (
    :tags IS NULL
    OR EXISTS (
      SELECT 1
      FROM note_tags nt
      JOIN tags t ON t.id = nt.tag_id
      WHERE nt.note_id = n.id
        AND t.user_id  = :user_id
        AND t.name     = ANY(:tags)
    )
  )
ORDER BY combined_score DESC NULLS LAST
LIMIT :limit
OFFSET :offset
        """)
        try:
            r = await db.execute(sql, params)
            rows = r.fetchall()
            print(f"[OK] hybrid SQL returned {len(rows)} rows")
            for row in rows[:3]:
                print(f"  - {row.id} score={row.combined_score:.3f}")
        except Exception as e:
            print(f"[FAIL] hybrid SQL: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())

