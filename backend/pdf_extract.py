"""Fast PDF text extraction for ClariX.

Uses pypdf for text extraction. On the two large PDFs supplied for diagnosis,
pypdf extracted 284/285 pages in about 3/13 seconds, while pdfplumber was
slow enough on the annual report to exceed a 5-minute benchmark timeout.

Public functions and output structure are kept compatible with the existing
ClariX app: extract_text_from_pdf(bytes) -> str and
process_pdf(bytes, filename, chunk_size, overlap) -> (chunks, clean_text).
Page markers and per-chunk source/page/section metadata are preserved.
"""
import io
import logging
import re
import time

from pypdf import PdfReader
from backend.document_processor import clean_text, chunk_text

logger = logging.getLogger(__name__)

_PAGE_RE = re.compile(r"\[Page\s+(\d+)\]", re.IGNORECASE)
_SECTION_PATTERNS = [
    re.compile(r"\bArticle\s+\d{1,4}[A-Za-z]?\b", re.IGNORECASE),
    re.compile(r"\b(?:paragraph|section|clause)\s+\d{1,4}(?:\.\d+)*[A-Za-z]?\b", re.IGNORECASE),
]


def _metadata_for_chunk(text: str):
    pages = [int(x) for x in _PAGE_RE.findall(text)]
    page_start = min(pages) if pages else None
    page_end = max(pages) if pages else page_start
    refs = []
    for rx in _SECTION_PATTERNS:
        refs.extend(rx.findall(text))
    reference = refs[0] if refs else None
    return page_start, page_end, reference


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text with pypdf, preserving original PDF page numbers."""
    started = time.perf_counter()
    pages = []
    reader = PdfReader(io.BytesIO(file_bytes))
    page_count = len(reader.pages)
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[Page {i + 1}]\n{text.strip()}")
    result = "\n\n".join(pages)
    logger.info(
        "PDF extraction: pages=%s, extracted_pages=%s, chars=%s, seconds=%.2f",
        page_count, len(pages), len(result), time.perf_counter() - started
    )
    return result


def process_pdf(file_bytes: bytes, filename: str, chunk_size=800, overlap=100):
    """Full pipeline: bytes -> cleaned chunks with source/page/section metadata."""
    started = time.perf_counter()

    t0 = time.perf_counter()
    raw = extract_text_from_pdf(file_bytes)
    extract_seconds = time.perf_counter() - t0

    t0 = time.perf_counter()
    clean = clean_text(raw)
    clean_seconds = time.perf_counter() - t0

    t0 = time.perf_counter()
    chunks = chunk_text(clean, chunk_size, overlap)
    chunk_seconds = time.perf_counter() - t0

    t0 = time.perf_counter()
    for chunk in chunks:
        chunk["source"] = filename
        page_start, page_end, reference = _metadata_for_chunk(chunk["text"])
        chunk["page_start"] = page_start
        chunk["page_end"] = page_end
        chunk["section_reference"] = reference
    metadata_seconds = time.perf_counter() - t0

    logger.info(
        "PDF processing for %s: extract=%.2fs, clean=%.2fs, chunk=%.2fs, "
        "metadata=%.2fs, chunks=%s, total=%.2fs",
        filename, extract_seconds, clean_seconds, chunk_seconds,
        metadata_seconds, len(chunks), time.perf_counter() - started
    )
    return chunks, clean
