"""
Upload endpoint — B6 dedicated module.

Endpoints:
  POST /api/upload   — multipart file upload → Azure Blob → SAS URL

Auth required on all routes.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.auth.jwt import get_current_user
from app.config import settings
from app.services.blob_storage import upload_blob

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
    "application/octet-stream",
}

_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("/upload", summary="Upload a media file to Azure Blob Storage")
async def upload_file(
    file: UploadFile = File(...),
    current_user_id: uuid.UUID = Depends(get_current_user),
) -> dict:
    """Upload *file* to Azure Blob Storage and return a 24-hour SAS URL.

    - Accepts audio (webm, ogg, mp4, mpeg, wav) and image (jpeg, png, gif, webp) files.
    - File size limit: 50 MB.
    - Returns `{ "url": "<sas_url>", "blob_path": "<container_path>" }`.
    """
    # Validate content type
    content_type = file.content_type or "application/octet-stream"
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type: {content_type}",
        )

    # Read and validate size
    data = await file.read()
    if len(data) > _MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {_MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB",
        )

    # Determine folder from content type
    folder = "audio" if content_type.startswith("audio/") else "images"
    ext = _content_type_ext(content_type, file.filename)
    blob_path = f"{folder}/{current_user_id}/{uuid.uuid4()}{ext}"

    sas_url = await upload_blob(
        container=settings.AZURE_STORAGE_CONTAINER,
        blob_path=blob_path,
        data=data,
        content_type=content_type,
    )
    logger.info("upload_file: user=%s blob_path=%s", current_user_id, blob_path)
    return {"url": sas_url, "blob_path": blob_path}


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
    }
    if content_type in mapping:
        return mapping[content_type]
    if filename:
        import os
        _, ext = os.path.splitext(filename)
        if ext:
            return ext
    return ""
