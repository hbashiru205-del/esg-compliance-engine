"""Text extraction for process_pdf(), swapped from pypdf to pdfplumber.

pypdf's extract_text() inserts a stray space inside many words on the
two real regulation PDFs tested here -- "Article" comes out as
"Ar ticle" on the large majority of pages (a kerning/width-table quirk
reading these PDFs' embedded CID TrueType fonts). Since the tokenizer
splits on word boundaries, a broken word never matches the same word
in a question, which silently weakens retrieval for the single most
common word in a regulation ("article") -- on every question that
names an article number, not just the ones this project happened to
test. pdfplumber extracted both real PDFs with zero broken words on
any page (58/58 and 16/16 clean, versus 43/58 and 12/16 broken with
pypdf).

Same function names and output contract as backend.document_processor,
so this is a drop-in replacement; document_processor.py itself is left
exactly as it was, and chunk_text/clean_text are reused from it rather
than duplicated.
"""
import io
import pdfplumber
from backend.document_processor import clean_text, chunk_text


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract raw text from PDF bytes."""
    pages = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"[Page {i+1}]\n{text.strip()}")
    return "\n\n".join(pages)


def process_pdf(file_bytes: bytes, filename: str, chunk_size=800, overlap=100):
    """Full pipeline: bytes -> cleaned chunks with metadata."""
    raw = extract_text_from_pdf(file_bytes)
    clean = clean_text(raw)
    chunks = chunk_text(clean, chunk_size, overlap)
    for c in chunks:
        c["source"] = filename
    return chunks, clean
