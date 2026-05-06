# Import all models so Alembic autogenerate can detect them.
from app.models.user import User  # noqa: F401
from app.models.note import Note  # noqa: F401
from app.models.tag import Tag, note_tags  # noqa: F401
from app.models.note_link import NoteLink  # noqa: F401
from app.models.vocabulary import UserVocabulary  # noqa: F401
from app.models.note_deletion import NoteDeletion  # noqa: F401
