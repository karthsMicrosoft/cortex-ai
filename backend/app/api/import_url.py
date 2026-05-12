"""
URL import endpoint — POST /api/import/url  (Phase 5 / PR 5.2).

Accepts a public URL, fetches it through the SSRF-hardened
``app.services.url_ingest`` pipeline, and creates a Note row with
``source_url`` / ``source_title`` populated. The note is left at
``processing_status='raw'`` so the existing AI pipeline (Stage 1+2)
picks it up via the same code path used for voice/text notes.

Per-user rate limit: 30/hour.
"""
import logging
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import require_scope
from app.database import get_db
from app.limiter import limiter
from app.models.note import Note
from app.services.url_ingest import (
    ContentTooLargeError,
    ExtractionEmptyError,
    InvalidURLError,
    PrivateIPError,
    UnsupportedContentTypeError,
    UpstreamError,
    UpstreamTimeoutError,
    fetch_and_extract,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Defensive truncation: chunking belongs to PR 5.4 (PDF). For URLs we cap the
# stored note body at 50_000 chars and append a notice when truncated.
_NOTE_CONTENT_CHAR_CAP = 50_000
_TRUNCATION_NOTICE = "\n\n[Content truncated — original article exceeded 50,000 characters]"


class ImportURLRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)


class ImportURLResponse(BaseModel):
    note_id: uuid.UUID
    source_url: str
    source_title: str
    char_count: int


# ---------------------------------------------------------------------------
# POST /api/import/url
# ---------------------------------------------------------------------------

@router.post(
    "/url",
    response_model=ImportURLResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/hour")
async def import_url(
    request: Request,
    response: Response,
    payload: ImportURLRequest = Body(...),
    current_user_id: uuid.UUID = Depends(require_scope({None, "clip"})),
    db: AsyncSession = Depends(get_db),
) -> ImportURLResponse:
    """Fetch *payload.url* and create a Note row from the extracted article."""
    try:
        page = await fetch_and_extract(payload.url)
    except InvalidURLError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except PrivateIPError as exc:
        logger.warning(
            "import_url: SSRF block user=%s url=%s reason=%s",
            current_user_id, payload.url, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="URL resolves to a private/internal address",
        ) from exc
    except ContentTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Page exceeds 5 MB limit",
        ) from exc
    except UnsupportedContentTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except ExtractionEmptyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not extract article content from page",
        ) from exc
    except UpstreamTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Upstream server timed out",
        ) from exc
    except UpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream fetch failed: {exc}",
        ) from exc

    title = (page["title"] or "").strip()[:500] or "Untitled"
    body = page["content"] or ""
    char_count = len(body)
    stored_content = body
    if len(stored_content) > _NOTE_CONTENT_CHAR_CAP:
        stored_content = stored_content[:_NOTE_CONTENT_CHAR_CAP] + _TRUNCATION_NOTICE

    note = Note(
        user_id=current_user_id,
        content=stored_content,
        source_type="text",
        category="Ideas",
        processing_status="raw",
        source_url=page["final_url"],
        source_title=title,
    )
    db.add(note)
    await db.flush()
    note_id = note.id
    await db.commit()

    logger.info(
        "import_url: user=%s note_id=%s source_url=%s chars=%d",
        current_user_id, note_id, page["final_url"], char_count,
    )

    return ImportURLResponse(
        note_id=note_id,
        source_url=page["final_url"],
        source_title=title,
        char_count=char_count,
    )
