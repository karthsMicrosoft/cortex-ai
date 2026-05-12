"""
PDF ingestion service (Phase 5 / PR 5.4).

Extract text from text-based PDFs and split it into chunks suitable for
storing as Note rows. OCR for image-only PDFs is intentionally out of
scope here (Phase 7+).

Public API:
    extract_text(pdf_bytes, filename) -> ExtractedPdf

Errors raised by _load_pdf (mapped to HTTP status codes by the API layer):
    PdfTooLargeError    -> 413
    PdfEncryptedError   -> 422
    PdfPageLimitError   -> 422
    PdfCorruptError     -> 422
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
from typing import TypedDict

import pypdf

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Limits (DoS protection). The API layer also enforces the size limit before
# calling into this module, but we keep a defensive copy here too.
# ---------------------------------------------------------------------------
MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB
MAX_PAGES = 100
# Notes table content cap is 50_000 chars; leave headroom for safety.
_DEFAULT_MAX_CHARS = 45_000


class ExtractedPdf(TypedDict):
    title: str
    page_count: int
    chunks: list[str]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PdfIngestError(Exception):
    """Base class for PDF ingestion errors."""


class PdfTooLargeError(PdfIngestError):
    pass


class PdfEncryptedError(PdfIngestError):
    pass


class PdfPageLimitError(PdfIngestError):
    pass


class PdfCorruptError(PdfIngestError):
    pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def extract_text(pdf_bytes: bytes, filename: str) -> ExtractedPdf:
    """Extract text and chunk it. Heavy work runs in a worker thread."""
    return await asyncio.to_thread(_extract_text_sync, pdf_bytes, filename)


def _extract_text_sync(pdf_bytes: bytes, filename: str) -> ExtractedPdf:
    reader = _load_pdf(pdf_bytes)
    title = _extract_title(reader, filename)
    per_page = _extract_per_page_text(reader)
    chunks = _chunk_paragraphs(per_page, max_chars=_DEFAULT_MAX_CHARS)
    if not chunks:
        # No extractable text — keep at least one empty placeholder so the
        # caller can still create a parent note pointing at the source blob.
        chunks = [""]
    return ExtractedPdf(title=title, page_count=len(reader.pages), chunks=chunks)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_pdf(pdf_bytes: bytes) -> pypdf.PdfReader:
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise PdfTooLargeError(
            f"PDF exceeds {MAX_PDF_BYTES // (1024 * 1024)} MB limit"
        )
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:  # noqa: BLE001 — pypdf raises a variety of types
        raise PdfCorruptError(f"Could not parse PDF: {exc}") from exc

    if reader.is_encrypted:
        raise PdfEncryptedError("Encrypted PDFs are not supported")

    # Access pages defensively; some malformed PDFs only blow up here.
    try:
        page_count = len(reader.pages)
    except Exception as exc:  # noqa: BLE001
        raise PdfCorruptError(f"Could not enumerate pages: {exc}") from exc

    if page_count > MAX_PAGES:
        raise PdfPageLimitError(
            f"PDF has {page_count} pages; max supported is {MAX_PAGES}"
        )
    return reader


def _extract_per_page_text(reader: pypdf.PdfReader) -> list[str]:
    out: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("pdf_ingest: page extract_text failed: %s", exc)
            text = ""
        out.append(text)
    return out


def _chunk_paragraphs(per_page: list[str], max_chars: int = _DEFAULT_MAX_CHARS) -> list[str]:
    """Greedily pack paragraphs into chunks of <= max_chars.

    Steps:
      1. Join all page texts with a blank line separator.
      2. Split on '\\n\\n' to get paragraphs.
      3. Greedily concatenate paragraphs (rejoined with '\\n\\n') until the
         next one would exceed max_chars; then start a new chunk.
      4. If a single paragraph is longer than max_chars, hard-split it at
         the limit boundary.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")

    joined = "\n\n".join(p for p in per_page if p and p.strip())
    if not joined.strip():
        return []

    # Split + drop blank paragraphs.
    paragraphs = [p.strip() for p in joined.split("\n\n") if p and p.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    sep = "\n\n"

    for para in paragraphs:
        # Hard-split paragraphs longer than max_chars.
        if len(para) > max_chars:
            # First flush whatever we've accumulated.
            if current:
                chunks.append(sep.join(current))
                current = []
                current_len = 0
            for i in range(0, len(para), max_chars):
                chunks.append(para[i : i + max_chars])
            continue

        addition = len(para) + (len(sep) if current else 0)
        if current_len + addition > max_chars:
            # Flush current and start fresh with this paragraph.
            chunks.append(sep.join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += addition

    if current:
        chunks.append(sep.join(current))
    return chunks


def _extract_title(reader: pypdf.PdfReader, filename: str) -> str:
    try:
        meta = reader.metadata
        if meta and getattr(meta, "title", None):
            title = str(meta.title).strip()
            # Some generators (e.g., reportlab) populate a placeholder
            # "untitled" when the author didn't set a title — treat that
            # as no title and fall back to the filename.
            if title and title.lower() != "untitled":
                return title
    except Exception as exc:  # noqa: BLE001
        logger.debug("pdf_ingest: metadata.title read failed: %s", exc)

    base = os.path.basename(filename or "")
    stem, _ext = os.path.splitext(base)
    return stem or base or "Untitled PDF"
