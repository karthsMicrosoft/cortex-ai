"""
Tests for app.services.pdf_ingest (Phase 5 / PR 5.4).

Covers:
  - extract_text() happy path on a small synthesized PDF
  - extract_text() multi-page concatenation + page_count
  - _chunk_paragraphs() respects max_chars boundary
  - _chunk_paragraphs() hard-splits a single paragraph that exceeds max_chars
  - _load_pdf() raises PdfEncryptedError for encrypted PDFs
  - _load_pdf() raises PdfPageLimitError for >100 pages
  - _load_pdf() raises PdfCorruptError for non-PDF bytes
"""
from __future__ import annotations

import io

import pytest
from reportlab.pdfgen import canvas

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers — synthesize PDFs in-memory using reportlab
# ---------------------------------------------------------------------------

def _make_pdf(pages_text: list[str], title: str | None = None) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    if title is not None:
        c.setTitle(title)
    for page_text in pages_text:
        # Write page text wrapped naively at 80 chars across multiple lines.
        y = 800
        for line in page_text.split("\n"):
            c.drawString(50, y, line[:200])
            y -= 14
            if y < 50:
                break
        c.showPage()
    c.save()
    return buf.getvalue()


def _make_encrypted_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, encrypt="hunter2")
    c.drawString(50, 800, "secret content")
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------

class TestExtractText:
    async def test_extract_text_simple_pdf(self):
        from app.services.pdf_ingest import extract_text

        pdf = _make_pdf(["Hello world. This is a tiny one page sample."], title="My Doc")
        out = await extract_text(pdf, "sample.pdf")

        assert out["page_count"] == 1
        assert out["title"] == "My Doc"
        assert isinstance(out["chunks"], list)
        assert len(out["chunks"]) >= 1
        assert "Hello world" in out["chunks"][0]

    async def test_extract_text_multi_page_pdf(self):
        from app.services.pdf_ingest import extract_text

        pdf = _make_pdf([
            "Page one alpha content.",
            "Page two bravo content.",
            "Page three charlie content.",
        ])
        out = await extract_text(pdf, "multi.pdf")

        assert out["page_count"] == 3
        # No metadata title set => falls back to filename without extension.
        assert out["title"] == "multi"
        joined = "\n".join(out["chunks"])
        assert "alpha" in joined
        assert "bravo" in joined
        assert "charlie" in joined

    async def test_extract_text_title_falls_back_to_filename(self):
        from app.services.pdf_ingest import extract_text

        pdf = _make_pdf(["just text"])
        out = await extract_text(pdf, "report-2024.PDF")
        assert out["title"] == "report-2024"


# ---------------------------------------------------------------------------
# _chunk_paragraphs
# ---------------------------------------------------------------------------

class TestChunkParagraphs:
    def test_chunk_paragraphs_respects_max_chars(self):
        from app.services.pdf_ingest import _chunk_paragraphs

        # 5 paragraphs of 100 chars each, max_chars=250 => groups of <=2 paragraphs (with separators).
        paras = [("x" * 100) for _ in range(5)]
        per_page = ["\n\n".join(paras)]
        chunks = _chunk_paragraphs(per_page, max_chars=250)

        assert len(chunks) >= 2
        for c in chunks:
            assert len(c) <= 250
        # All content present.
        joined = "".join(chunks)
        assert joined.count("x") == 500

    def test_chunk_paragraphs_hard_split_long_paragraph(self):
        from app.services.pdf_ingest import _chunk_paragraphs

        big = "y" * 1000
        chunks = _chunk_paragraphs([big], max_chars=300)

        assert len(chunks) >= 4  # 1000 / 300 = 4 chunks
        for c in chunks:
            assert len(c) <= 300
        assert "".join(chunks).count("y") == 1000

    def test_chunk_paragraphs_empty_input(self):
        from app.services.pdf_ingest import _chunk_paragraphs

        assert _chunk_paragraphs([]) == []
        assert _chunk_paragraphs(["", "   "]) == []


# ---------------------------------------------------------------------------
# _load_pdf — error cases
# ---------------------------------------------------------------------------

class TestLoadPdf:
    def test_load_pdf_rejects_encrypted(self):
        from app.services.pdf_ingest import PdfEncryptedError, _load_pdf

        pdf = _make_encrypted_pdf()
        with pytest.raises(PdfEncryptedError):
            _load_pdf(pdf)

    def test_load_pdf_rejects_over_100_pages(self):
        from app.services.pdf_ingest import PdfPageLimitError, _load_pdf

        pdf = _make_pdf([f"page {i}" for i in range(101)])
        with pytest.raises(PdfPageLimitError):
            _load_pdf(pdf)

    def test_load_pdf_rejects_corrupt(self):
        from app.services.pdf_ingest import PdfCorruptError, _load_pdf

        with pytest.raises(PdfCorruptError):
            _load_pdf(b"not a pdf at all")

    def test_load_pdf_accepts_valid(self):
        from app.services.pdf_ingest import _load_pdf

        pdf = _make_pdf(["ok"])
        reader = _load_pdf(pdf)
        assert len(reader.pages) == 1
