"""
Upload endpoint — B6 dedicated module.

Endpoints:
  POST /api/upload   — multipart file upload → Azure Blob → SAS URL

Auth required on all routes.
"""
import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.config import settings
from app.database import get_db
from app.models.note import Note
from app.services.blob_storage import upload_blob
from app.services.pdf_ingest import (
    PdfCorruptError,
    PdfEncryptedError,
    PdfPageLimitError,
    PdfTooLargeError,
    extract_text,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# POST /api/upload
# ---------------------------------------------------------------------------

_ALLOWED_CONTENT_TYPES: set[str] = {
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
    "application/octet-stream",
}

_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB (audio/image cap)
_MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB (PDF cap; tighter for DoS protection)
_PDF_EXTRACT_TIMEOUT_SECONDS = 30.0


@router.post("/upload", summary="Upload a media file to Azure Blob Storage")
async def upload_file(
    file: UploadFile = File(...),
    current_user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Upload *file* to Azure Blob Storage and return a 24-hour SAS URL.

    - Accepts audio (webm, ogg, mp4, mpeg, wav), image (jpeg, png, gif, webp),
      and PDF (application/pdf) files.
    - File size limit: 50 MB for audio/image, 20 MB for PDF.
    - For PDFs: extracts text, chunks at paragraph boundaries (≤45k chars per
      chunk), and creates a parent Note + child Notes wired via
      `source_parent_id`. Returns the parent note id and chunk metadata.
    - For audio/image: returns `{ "url": "<sas_url>", "blob_path": "..." }`.
    """
    # Validate content type
    content_type = file.content_type or "application/octet-stream"
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type: {content_type}",
        )

    is_pdf = content_type == "application/pdf"
    size_limit = _MAX_PDF_BYTES if is_pdf else _MAX_FILE_SIZE_BYTES

    # Read and validate size
    data = await file.read()
    if len(data) > size_limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {size_limit // (1024 * 1024)} MB",
        )

    # Determine folder + extension
    if is_pdf:
        folder = "pdfs"
    elif content_type.startswith("audio/"):
        folder = "audio"
    else:
        folder = "images"
    ext = _content_type_ext(content_type, file.filename)
    blob_path = f"{folder}/{current_user_id}/{uuid.uuid4()}{ext}"

    sas_url = await upload_blob(
        container=settings.AZURE_STORAGE_CONTAINER,
        blob_path=blob_path,
        data=data,
        content_type=content_type,
    )
    logger.info("upload_file: user=%s blob_path=%s", current_user_id, blob_path)

    if not is_pdf:
        return {"url": sas_url, "blob_path": blob_path}

    # ---- PDF: extract, chunk, persist parent + children -------------------
    try:
        extracted = await asyncio.wait_for(
            extract_text(data, file.filename or "document.pdf"),
            timeout=_PDF_EXTRACT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        logger.warning("upload_file: PDF extraction timed out for %s", blob_path)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="PDF text extraction timed out",
        ) from exc
    except PdfTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except PdfEncryptedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Encrypted PDFs are not supported",
        ) from exc
    except PdfPageLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except PdfCorruptError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse PDF: {exc}",
        ) from exc

    chunks = extracted["chunks"] or [""]
    title = extracted["title"]

    parent = Note(
        user_id=current_user_id,
        content=chunks[0],
        source_type="text",
        source_url=sas_url,
        source_title=title,
        processing_status="raw",
    )
    db.add(parent)
    await db.flush()  # populate parent.id

    for i, chunk in enumerate(chunks[1:], start=1):
        child = Note(
            user_id=current_user_id,
            content=chunk,
            source_type="text",
            source_parent_id=parent.id,
            source_title=f"{title} (part {i + 1})",
            processing_status="raw",
        )
        db.add(child)

    await db.commit()
    await db.refresh(parent)

    return {
        "url": sas_url,
        "blob_path": blob_path,
        "note_id": str(parent.id),
        "source_parent_id": str(parent.id),
        "chunk_count": len(chunks),
        "page_count": extracted["page_count"],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _content_type_ext(content_type: str, filename: str | None) -> str:
    """Return file extension for *content_type*, falling back to *filename*."""
    mapping = {
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/mp4": ".mp4",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
    }
    if content_type in mapping:
        return mapping[content_type]
    if filename:
        import os
        _, ext = os.path.splitext(filename)
        if ext:
            return ext
    return ""
