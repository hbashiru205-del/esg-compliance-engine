"""PDF extraction and processing with memory cleanup and timing."""
import io
import re
import time
import logging

import pdfplumber
from backend.document_processor import clean_text, chunk_text

logger = logging.getLogger(__name__)

_PAGE_RE = re.compile(r'\[Page\s+(\d+)\]', re.IGNORECASE)
_SECTION_PATTERNS = [
    re.compile(r'\bArticle\s+\d{1,4}[A-Za-z]?\b', re.IGNORECASE),
    re.compile(
        r'\b(?:paragraph|section|clause)\s+\d{1,4}'
        r'(?:\.\d+)*[A-Za-z]?\b',
        re.IGNORECASE,
    ),
]


def _metadata_for_chunk(text):
    pages = [int(x) for x in _PAGE_RE.findall(text)]
    page_start = min(pages) if pages else None
    page_end = max(pages) if pages else page_start

    reference = None
    for pattern in _SECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            reference = match.group(0)
            break

    return page_start, page_end, reference


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract PDF text and release each page's cached resources."""
    started = time.perf_counter()
    pages = []
    page_count = 0
    extracted_chars = 0

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        page_count = len(pdf.pages)

        for i, page in enumerate(pdf.pages):
            page_started = time.perf_counter()
            text = ""

            try:
                text = page.extract_text() or ""
            finally:
                page.flush_cache()
                if hasattr(page, "close"):
                    page.close()

            if text.strip():
                page_text = text.strip()
                pages.append(f"[Page {i + 1}]\n{page_text}")
                extracted_chars += len(page_text)

            # Log slow pages only, avoiding excessive log output.
            elapsed = time.perf_counter() - page_started
            if elapsed >= 1.0:
                logger.info(
                    "PDF page %s/%s took %.2fs",
                    i + 1, page_count, elapsed,
                )

    result = "\n\n".join(pages)

    logger.info(
        "PDF extraction: pages=%s, chars=%s, seconds=%.2f",
        page_count,
        extracted_chars,
        time.perf_counter() - started,
    )
    return result


def process_pdf(
    file_bytes: bytes,
    filename: str,
    chunk_size=800,
    overlap=100,
):
    """Process PDF bytes into cleaned, chunked text with metadata."""
    total_started = time.perf_counter()

    started = time.perf_counter()
    raw = extract_text_from_pdf(file_bytes)
    extraction_seconds = time.perf_counter() - started

    started = time.perf_counter()
    clean = clean_text(raw)
    cleaning_seconds = time.perf_counter() - started

    started = time.perf_counter()
    chunks = chunk_text(clean, chunk_size, overlap)
    chunking_seconds = time.perf_counter() - started

    started = time.perf_counter()
    for chunk in chunks:
        chunk["source"] = filename
        page_start, page_end, reference = _metadata_for_chunk(
            chunk["text"]
        )
        chunk["page_start"] = page_start
        chunk["page_end"] = page_end
        chunk["section_reference"] = reference
    metadata_seconds = time.perf_counter() - started

    logger.info(
        "PDF processing for %s: extraction=%.2fs, cleaning=%.2fs, "
        "chunking=%.2fs, metadata=%.2fs, chunks=%s, total=%.2fs",
        filename,
        extraction_seconds,
        cleaning_seconds,
        chunking_seconds,
        metadata_seconds,
        len(chunks),
        time.perf_counter() - total_started,
    )

    return chunks, clean
