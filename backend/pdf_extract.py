"""PDF extraction and chunk metadata for ClariX.

Keeps the public process_pdf/extract_text_from_pdf API while preserving page
numbers and carrying an ESRS disclosure heading forward to subsequent chunks
until a new recognized heading is encountered.
"""
import io
import re

from pypdf import PdfReader
from backend.document_processor import clean_text, chunk_text

_PAGE_RE = re.compile(r"\[Page\s+(\d+)\]", re.IGNORECASE)
_ESRS_CODE = r"(?:ESRS\s+2|(?:E|S|G)\d{1,2}-\d{1,3}|GOV-\d{1,2}|SBM-\d{1,2}|IRO-\d{1,2}|BP-\d{1,2}|MDR-[A-Z]{1,3})"
_ESRS_HEADING_PATTERNS = [
    re.compile(rf"^\s*({_ESRS_CODE})\s*(?:[.:—–-]\s*)?(?:$|\s+\S)", re.IGNORECASE | re.MULTILINE),
    re.compile(rf"\b(?:Disclosure Requirement|DR)\s+({_ESRS_CODE})\b", re.IGNORECASE),
]
_SECTION_PATTERNS = [
    re.compile(r"\bArticle\s+\d{1,4}[A-Za-z]?\b", re.IGNORECASE),
    re.compile(r"\b(?:paragraph|section|clause)\s+\d{1,4}(?:\.\d+)*[A-Za-z]?\b", re.IGNORECASE),
]


def _continues_sentence(text: str, pos: int) -> bool:
    """True if the text after a code on the same line continues in lowercase."""
    tail = re.sub(r"^[ \t]*[.:\u2014\u2013-]?[ \t]*", "", text[pos:pos + 80])
    return bool(tail) and tail[0].islower()


def _metadata_for_chunk(text: str):
    pages = [int(x) for x in _PAGE_RE.findall(text)]
    page_start = min(pages) if pages else None
    page_end = max(pages) if pages else page_start
    esrs_ref = None
    for idx, rx in enumerate(_ESRS_HEADING_PATTERNS):
        for match in rx.finditer(text):
            # A line that merely wraps in the PDF and starts with a code
            # ("E1-2 and Article 19a ...") continues a sentence; it is a
            # cross-reference, not a heading. Headings are followed by a
            # capitalised title or end of line.
            if idx == 0 and _continues_sentence(text, match.end(1)):
                continue
            # Normalize spacing/case without inventing codes.
            esrs_ref = re.sub(r"\s+", " ", match.group(1)).upper()
            break
        if esrs_ref:
            break
    refs = []
    for rx in _SECTION_PATTERNS:
        refs.extend(m.group(0) for m in rx.finditer(text))
    return page_start, page_end, esrs_ref or (refs[0] if refs else None)


def _page_at_offset(text: str, offset: int):
    current = None
    for match in _PAGE_RE.finditer(text, 0, max(0, min(len(text), offset + 1))):
        current = int(match.group(1))
    return current


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract raw text with explicit original PDF page markers using pypdf."""
    pages = []
    reader = PdfReader(io.BytesIO(file_bytes))
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[Page {i + 1}]\n{text.strip()}")
    return "\n\n".join(pages)


def process_pdf(file_bytes: bytes, filename: str, chunk_size=800, overlap=100):
    """Return (chunks, cleaned text), with inherited disclosure/page metadata."""
    raw = extract_text_from_pdf(file_bytes)
    clean = clean_text(raw)
    chunks = chunk_text(clean, chunk_size, overlap)
    active_esrs_ref = None
    active_page = None
    for chunk in chunks:
        chunk["source"] = filename
        start = chunk.get("char_start", 0)
        page_start, page_end, reference = _metadata_for_chunk(chunk.get("text", ""))
        if page_start is None:
            page_start = _page_at_offset(clean, start) or active_page
        if page_end is None:
            page_end = page_start
        if page_start is not None:
            active_page = page_start
        if reference and re.fullmatch(_ESRS_CODE, reference, re.IGNORECASE):
            active_esrs_ref = reference
        elif reference is None and active_esrs_ref:
            reference = active_esrs_ref
        chunk["page_start"] = page_start
        chunk["page_end"] = page_end
        chunk["section_reference"] = reference
    return chunks, clean
