"""
Image OCR pipeline module — B5 resolution.

OCR lives here (pipeline/ocr.py), NOT in services/vision.py.
The Azure AI Vision ImageAnalysisClient is constructed inline (single call site).

Exposes:
    process_image_note(note, db) → None
    extract_text_from_image_url(url) → str

Per spec § 4.1 and task 6.1:
- Uses azure-ai-vision-imageanalysis 1.0.*
- Calls the READ analysis feature on note.image_url
- Writes extracted text to note.content
- Sets note.processing_status = 'transcribed' so Stage 2 (ORGANIZE) runs
- Wraps Vision SDK call with the tenacity retry decorator from utils/retry.py
"""
import logging
from typing import Optional

from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.core.credentials import AzureKeyCredential
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.note import Note
from app.utils.retry import azure_retry

logger = logging.getLogger(__name__)


@azure_retry
async def extract_text_from_image_url(url: str) -> str:
    """Call Azure AI Vision READ feature on *url* and return extracted text.

    Constructs the ImageAnalysisClient inline (single call site — no
    separate services/vision.py module per B5 design resolution).

    Args:
        url: Publicly accessible URL of the image to analyze.

    Returns:
        Extracted text string (joined lines), or empty string if no text found.
    """
    import asyncio

    client = ImageAnalysisClient(
        endpoint=settings.AZURE_VISION_ENDPOINT,
        credential=AzureKeyCredential(settings.AZURE_VISION_KEY),
    )

    # Vision SDK is synchronous — run in executor to avoid blocking event loop
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client.analyze_from_url(
            image_url=url,
            visual_features=[VisualFeatures.READ],
        ),
    )

    if result.read is None:
        return ""

    # Collect all text lines from all blocks
    lines: list[str] = []
    for block in result.read.blocks:
        for line in block.lines:
            lines.append(line.text)

    extracted = "\n".join(lines)
    logger.info(
        "ocr: extracted %d chars from url (truncated to 200 for log): %.200s",
        len(extracted),
        url,
    )
    return extracted


async def process_image_note(note: Note, db: Optional[AsyncSession] = None) -> None:
    """OCR an image note: extract text, update note.content, set status='transcribed'.

    After this runs, the main pipeline (Stage 1 CAPTURE is skipped for images;
    Stage 2 ORGANIZE runs) should be scheduled.

    Args:
        note: The Note ORM object with source_type='image' and image_url set.
        db:   Optional async SQLAlchemy session. If provided, commit() is called.
    """
    if not note.image_url:
        logger.warning("process_image_note: note %s has no image_url", note.id)
        return

    try:
        extracted_text = await extract_text_from_image_url(note.image_url)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "process_image_note: OCR failed note_id=%s error_class=%s",
            note.id,
            type(exc).__name__,
        )
        note.processing_status = "failed"
        if db is not None:
            await db.commit()
        return

    note.content = extracted_text or note.content  # keep original if OCR returned nothing
    note.processing_status = "transcribed"  # triggers Stage 2 in the main pipeline
    if db is not None:
        await db.commit()
    logger.info("process_image_note: complete note_id=%s text_len=%d", note.id, len(extracted_text))
