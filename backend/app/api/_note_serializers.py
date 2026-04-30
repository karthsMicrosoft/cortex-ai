"""
Shared Note serializer — private to the api package.

Provides a single _note_to_out(note) helper used by both notes.py and voice.py
so that all NoteOut fields (including shadow_reader_*) are populated from the
DB object in one place.

QA-05 fix: eliminates the duplicate _note_to_out implementations that existed
in notes.py and voice.py, where the voice.py copy omitted shadow_reader_* fields.
"""
from app.models.note import Note
from app.schemas.note import NoteOut


def _note_to_out(note: Note) -> NoteOut:
    """Convert Note ORM object to NoteOut schema, building tags list.

    Includes all shadow_reader_* fields so that voice upload responses
    correctly reflect DB values rather than Pydantic defaults.
    """
    tag_names = [t.name for t in note.tags] if note.tags else []
    return NoteOut(
        id=note.id,
        user_id=note.user_id,
        content=note.content,
        raw_transcription=note.raw_transcription,
        summary=note.summary,
        source_type=note.source_type,
        category=note.category,
        audio_url=note.audio_url,
        image_url=note.image_url,
        audio_duration_seconds=note.audio_duration_seconds,
        mood=note.mood,
        music_metadata=note.music_metadata or {},
        processing_status=note.processing_status,
        sync_status=note.sync_status,
        client_id=note.client_id,
        tags=tag_names,
        # Phase 2 — Shadow Reader fields (all three; voice.py copy was missing these)
        shadow_reader_status=note.shadow_reader_status or "pending",
        shadow_reader_questions=note.shadow_reader_questions,
        shadow_reader_answer=note.shadow_reader_answer,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )
