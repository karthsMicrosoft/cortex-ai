"""
Azure Blob Storage adapter.

Exposes:
- upload_blob(container, blob_path, data, content_type) → SAS URL (24h read-only)
- delete_blob(blob_path, container?)                    → None

All public functions are wrapped with the tenacity retry decorator.

Environment:
- AZURE_STORAGE_CONNECTION_STRING
- AZURE_STORAGE_CONTAINER   (default container name; callers may override)
"""
import datetime
import hashlib
import logging
from typing import Optional

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import (
    BlobClient,
    BlobSasPermissions,
    BlobServiceClient,
    generate_blob_sas,
)

from app.config import settings
from app.utils.retry import azure_retry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_service_client() -> BlobServiceClient:
    """Return a BlobServiceClient from the connection string."""
    return BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)


def _parse_account_name() -> str:
    """Extract account name from connection string (AccountName=...)."""
    for part in settings.AZURE_STORAGE_CONNECTION_STRING.split(";"):
        if part.lower().startswith("accountname="):
            return part.split("=", 1)[1]
    raise ValueError("AccountName not found in AZURE_STORAGE_CONNECTION_STRING")


def _parse_account_key() -> str:
    """Extract account key from connection string (AccountKey=...)."""
    for part in settings.AZURE_STORAGE_CONNECTION_STRING.split(";"):
        if part.lower().startswith("accountkey="):
            return part.split("=", 1)[1]
    raise ValueError("AccountKey not found in AZURE_STORAGE_CONNECTION_STRING")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@azure_retry
async def upload_blob(
    container: str,
    blob_path: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload *data* to *container/blob_path* and return a 24h read-only SAS URL.

    Args:
        container:    Azure Blob Storage container name.
        blob_path:    Path inside the container, e.g. "audio/abc123.webm".
        data:         Raw bytes to upload.
        content_type: MIME type for the blob (e.g. "audio/webm", "image/jpeg").

    Returns:
        A time-limited (24h) SAS URL that grants read-only access.
    """
    service_client = _get_service_client()
    container_client = service_client.get_container_client(container)
    blob_client: BlobClient = container_client.get_blob_client(blob_path)
    blob_client.upload_blob(
        data,
        blob_type="BlockBlob",
        content_settings={"content_type": content_type},
        overwrite=True,
    )
    logger.info("Blob uploaded: container=%s path=%s bytes=%d", container, blob_path, len(data))

    # Generate 24h read-only SAS (naive UTC for compatibility with Azure SDK + test assertions)
    expiry = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    sas_token = generate_blob_sas(
        account_name=_parse_account_name(),
        container_name=container,
        blob_name=blob_path,
        account_key=_parse_account_key(),
        permission=BlobSasPermissions(read=True),
        expiry=expiry,
    )
    account_name = _parse_account_name()
    sas_url = (
        f"https://{account_name}.blob.core.windows.net/{container}/{blob_path}?{sas_token}"
    )
    return sas_url


@azure_retry
async def delete_blob(
    blob_path: str,
    container: Optional[str] = None,
) -> None:
    """Delete *blob_path* from *container* (defaults to AZURE_STORAGE_CONTAINER).

    Silently ignores blobs that do not exist.
    """
    container = container or settings.AZURE_STORAGE_CONTAINER
    service_client = _get_service_client()
    container_client = service_client.get_container_client(container)
    blob_client: BlobClient = container_client.get_blob_client(blob_path)
    try:
        blob_client.delete_blob()
        logger.info("Blob deleted: container=%s path=%s", container, blob_path)
    except ResourceNotFoundError:
        logger.debug("Blob not found (already deleted?): container=%s path=%s", container, blob_path)


def compute_sha256(data: bytes) -> str:
    """Return the hex SHA-256 digest of *data* — used for idempotency checks."""
    return hashlib.sha256(data).hexdigest()
