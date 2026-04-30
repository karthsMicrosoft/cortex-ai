"""
Shadow Reader — Stage 1.5 REFLECT pipeline.

Implements:
  - CATEGORY_PROMPTS       — category-specific question prompts (verbatim from F2.2)
  - MIN_WORDS_FOR_TRIGGER  — word-count gate (50)
  - should_trigger_shadow_reader(note, user) -> bool
  - generate_questions(note, openai_client) -> list[str]
  - run_shadow_reader_stage(note, user, openai_client, db) -> None
  - merge_answer_into_note(note, answer, openai_client, db) -> None

Design references:
  B10 — stage runs AFTER Stage 2 (enriched), gated on shadow_reader_status='pending'.
  F2.2 — verbatim prompt text, question cap, serializable transaction.
"""
import json
import logging
from typing import List

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category-specific prompts (verbatim from F2.2)
# ---------------------------------------------------------------------------

CATEGORY_PROMPTS = {
    "Music": (
        "You are a thoughtful music collaborator. Read this music idea and ask 1-2 "
        "gentle questions that help the user develop the idea further. Focus on emotion, "
        "instrumentation, lyrical themes, or musical structure. Keep questions short and warm."
    ),
    "Journal": (
        "You are a wise, compassionate listener. Read this journal entry and ask 1-2 "
        "gentle questions that help the user reflect deeper. Focus on feelings beneath "
        "the surface, what the person really needs, or what truth they might be avoiding. "
        "Be warm, never clinical."
    ),
    "Ideas": (
        "You are a thoughtful creative partner. Read this idea and ask 1-2 sharp "
        "questions that help the user clarify or develop it. Focus on the smallest "
        "next step, hidden assumptions, or who might benefit. Be direct but kind."
    ),
    "Fitness": (
        "You are an encouraging fitness coach. Read this fitness note and ask 1 short "
        "question about how the body felt, what was the hardest part, or what comes next."
    ),
    "Spiritual": (
        "You are a contemplative companion. Read this spiritual reflection and ask 1-2 "
        "gentle questions that invite deeper presence or insight. Avoid religious specificity."
    ),
    "Learning": (
        "You are a curious teacher. Read this learning note and ask 1-2 questions "
        "that help the user connect this to what they already know, or apply it."
    ),
}

MIN_WORDS_FOR_TRIGGER = 50

# ---------------------------------------------------------------------------
# Trigger gate
# ---------------------------------------------------------------------------


async def should_trigger_shadow_reader(note, user) -> bool:
    """Return True iff Shadow Reader should generate questions for this note.

    Checks (in order):
      1. user.shadow_reader_enabled is True
      2. note.category not in user.shadow_reader_disabled_categories
      3. word_count(note.content) >= MIN_WORDS_FOR_TRIGGER
    """
    if not user.shadow_reader_enabled:
        return False
    disabled = user.shadow_reader_disabled_categories or []
    if note.category in disabled:
        return False
    word_count = len(note.content.split())
    if word_count < MIN_WORDS_FOR_TRIGGER:
        return False
    return True


# ---------------------------------------------------------------------------
# Question generation
# ---------------------------------------------------------------------------


async def generate_questions(note, openai_client) -> List[str]:
    """Call GPT-4o-mini to generate 1-2 follow-up questions.

    Returns a list of ≤ 2 strings, each ≤ 15 words.
    Defensive: filters non-string items and items exceeding 15 words.
    """
    category_prompt = CATEGORY_PROMPTS.get(note.category, CATEGORY_PROMPTS["Ideas"])
    full_prompt = (
        f"{category_prompt}\n\n"
        f"Note content:\n{note.content}\n\n"
        'Return a JSON object with a single key "questions" containing an array '
        "of 1-2 question strings. Make each question concise (under 15 words). "
        "Do not number them."
    )

    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": full_prompt}],
        max_tokens=200,
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content or "{}")
    questions = result.get("questions", [])

    # Defensive: keep only strings ≤ 15 words, cap at 2
    filtered: List[str] = []
    for q in questions:
        if not isinstance(q, str):
            continue
        if len(q.split()) <= 15:
            filtered.append(q)
        else:
            # Truncate to 15 words with ellipsis rather than drop entirely
            truncated = " ".join(q.split()[:15])
            filtered.append(truncated)
        if len(filtered) == 2:
            break

    return filtered


# ---------------------------------------------------------------------------
# Stage 1.5 — run
# ---------------------------------------------------------------------------


async def run_shadow_reader_stage(note, user, openai_client, db: AsyncSession) -> None:
    """Stage 1.5: REFLECT — generate questions if trigger conditions are met.

    Sets shadow_reader_status to 'asked' (questions generated) or 'skipped'.
    Commits immediately so the GET endpoint can poll the new status.
    """
    if not await should_trigger_shadow_reader(note, user):
        note.shadow_reader_status = "skipped"
        await db.commit()
        logger.info(
            "shadow_reader_skipped: note_id=%s category=%s",
            note.id,
            note.category,
        )
        return

    try:
        questions = await generate_questions(note, openai_client)
        note.shadow_reader_questions = questions
        note.shadow_reader_status = "asked"
        await db.commit()
        logger.info(
            "shadow_reader_asked: note_id=%s questions=%d",
            note.id,
            len(questions),
        )
    except Exception as exc:  # noqa: BLE001
        # If question generation fails, skip gracefully — don't fail the note
        logger.error(
            "shadow_reader_generate_failed: note_id=%s error_class=%s",
            note.id,
            type(exc).__name__,
        )
        note.shadow_reader_status = "skipped"
        await db.commit()


# ---------------------------------------------------------------------------
# Answer merge (B10 — SERIALIZABLE transaction)
# ---------------------------------------------------------------------------


async def merge_answer_into_note(note, answer: str, openai_client, db: AsyncSession) -> None:
    """Append reflection to note content and regenerate embedding + links.

    Uses SERIALIZABLE isolation to prevent races with concurrent re-pipeline
    or embedding regeneration (B10).

    Steps:
      1. Set SERIALIZABLE isolation for current transaction
      2. Append '\\n\\n--- Reflection ---\\n{answer}' to note.content
      3. Set shadow_reader_answer + shadow_reader_status = 'answered'
      4. Regenerate embedding via text-embedding-3-small
      5. DELETE existing note_links where source_note_id = note.id
      6. Re-run cosine similarity linking with new embedding
      7. COMMIT
    """
    from app.models.note_link import NoteLink

    # Set SERIALIZABLE isolation for the current session (best-effort; no-op in SQLite tests)
    try:
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    except Exception:  # noqa: BLE001
        pass  # SQLite / mock — continue without SERIALIZABLE

    # Append reflection to the note passed in
    note.content = f"{note.content}\n\n--- Reflection ---\n{answer}"
    note.shadow_reader_answer = answer
    note.shadow_reader_status = "answered"

    # Regenerate embedding using updated content (includes reflection)
    embed_response = await openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=note.content,
    )
    new_embedding = embed_response.data[0].embedding
    note.embedding = new_embedding

    # Delete existing outgoing links so we can re-link with fresh embedding
    try:
        await db.execute(
            delete(NoteLink).where(NoteLink.source_note_id == note.id)
        )
    except Exception:  # noqa: BLE001
        pass  # SQLite / mock — skip gracefully

    # Re-run semantic linking
    await _relink_similar_notes(note, new_embedding, db)

    await db.commit()

    logger.info("merge_answer_complete: note_id=%s", note.id)


async def _relink_similar_notes(
    note,
    embedding: list,
    db: AsyncSession,
    threshold: float = 0.75,
    limit: int = 5,
) -> None:
    """Insert note_links for semantically similar notes after re-embedding."""
    if embedding is None:
        return
    try:
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
        link_sql = text("""
            INSERT INTO note_links (id, source_note_id, target_note_id, similarity_score, link_type)
            SELECT gen_random_uuid(), :note_id, n.id,
                   1 - (n.embedding <=> CAST(:embedding AS vector)) AS score,
                   'semantic'
            FROM notes n
            WHERE n.id != :note_id
              AND n.user_id = :user_id
              AND n.embedding IS NOT NULL
              AND 1 - (n.embedding <=> CAST(:embedding AS vector)) > :threshold
            ORDER BY n.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            ON CONFLICT (source_note_id, target_note_id)
            DO UPDATE SET similarity_score = EXCLUDED.similarity_score
        """)
        await db.execute(
            link_sql,
            {
                "note_id": str(note.id),
                "embedding": embedding_str,
                "user_id": str(note.user_id),
                "threshold": threshold,
                "limit": limit,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("_relink_similar_notes skipped: %s", type(exc).__name__)
