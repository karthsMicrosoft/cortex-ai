# Import all models so Alembic autogenerate can detect them.
from app.models.user import User  # noqa: F401
from app.models.note import Note  # noqa: F401
from app.models.tag import Tag, note_tags  # noqa: F401
from app.models.note_link import NoteLink  # noqa: F401
from app.models.vocabulary import UserVocabulary  # noqa: F401
from app.models.note_deletion import NoteDeletion  # noqa: F401
from app.models.revoked_jti import RevokedJTI  # noqa: F401
from app.models.canvas import Canvas  # noqa: F401
from app.models.canvas_item import CanvasItem  # noqa: F401
from app.models.canvas_edge import CanvasEdge  # noqa: F401
from app.models.push_subscription import PushSubscription  # noqa: F401
