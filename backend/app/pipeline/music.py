"""
Music note enrichment pipeline module.

Exposes:
    process_music_note(note, openai_client, db) → None

Per spec § 2.9: when note.category == 'Music', extract music-specific metadata
from the note content via GPT-4o-mini and persist to note.music_metadata.

Fields extracted:
    tempo_guess          — BPM estimate or qualitative (e.g. "fast", "120 BPM")
    key_guess            — Musical key (e.g. "C major", "A minor")
    genre                — Genre (e.g. "jazz", "hip-hop", "classical")
    mood                 — Emotional feel (e.g. "melancholic", "upbeat")
    instruments          — List of instruments mentioned or implied
    description          — Short description of the musical idea
    development_suggestions — 2-3 ways to develop the idea further
"""
import json
import logging

from openai import AsyncAzureOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note

logger = logging.getLogger(__name__)

_MUSIC_PROMPT = """\
You are a music theory expert and producer. Analyze this music note and return a JSON object with:
- tempo_guess: estimated BPM or qualitative tempo (e.g. "slow", "moderate", "fast", "120 BPM")
- key_guess: musical key if discernible (e.g. "C major", "A minor", "unknown")
- genre: musical genre that best fits (e.g. "jazz", "hip-hop", "folk", "classical")
- mood: emotional character of the music (e.g. "melancholic", "energetic", "peaceful")
- instruments: array of instruments mentioned or implied
- description: 1-2 sentence description of the musical idea
- development_suggestions: array of 2-3 concrete ways to develop this musical idea further

Note content:
{content}

Return ONLY valid JSON with these exact keys."""


async def process_music_note(
    note: Note,
    openai_client: AsyncAzureOpenAI,
    db: AsyncSession,
) -> None:
    """Enrich a Music-category note with music-specific metadata.

    Fills note.music_metadata with tempo_guess, key_guess, genre, mood,
    instruments, description, and development_suggestions.
    Commits the session after updating.
    """
    if not note.content:
        return

    prompt = _MUSIC_PROMPT.format(content=note.content)

    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.4,
        response_format={"type": "json_object"},
    )

    result: dict = {}
    try:
        result = json.loads(response.choices[0].message.content or "{}")
    except (json.JSONDecodeError, AttributeError):
        logger.warning("music_enrichment: JSON parse failed for note_id=%s", note.id)

    music_metadata = {
        "tempo_guess": result.get("tempo_guess"),
        "key_guess": result.get("key_guess"),
        "genre": result.get("genre"),
        "mood": result.get("mood"),
        "instruments": result.get("instruments") or [],
        "description": result.get("description"),
        "development_suggestions": result.get("development_suggestions") or [],
    }

    note.music_metadata = music_metadata
    await db.flush()
    logger.info("music_enrichment: complete note_id=%s genre=%s", note.id, music_metadata.get("genre"))
