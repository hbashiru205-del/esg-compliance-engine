import re
import hashlib
from pathlib import Path
import pypdf


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract raw text from PDF bytes."""
    import io
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[Page {i+1}]\n{text.strip()}")
    return "\n\n".join(pages)


def clean_text(text: str) -> str:
    """Remove excessive whitespace and junk characters."""
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100):
    """
    Split text into overlapping chunks.
    Returns list of dicts: {id, text, char_start, char_end}
    """
    chunks = []
    start = 0
    idx = 0

    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            for boundary in ['. ', '.\n', '! ', '? ', '\n\n']:
                pos = text.rfind(boundary, start + chunk_size // 2, end)
                if pos != -1:
                    end = pos + len(boundary)
                    break

        chunk_text_content = text[start:end].strip()

        if chunk_text_content:
            chunk_id = hashlib.md5(f"{idx}:{chunk_text_content[:50]}".encode()).hexdigest()[:12]
            chunks.append({
                "id":         chunk_id,
                "text":       chunk_text_content,
                "char_start": start,
                "char_end":   end,
                "index":      idx,
            })
            idx += 1

        start = end - overlap

    return chunks


def process_pdf(file_bytes: bytes, filename: str, chunk_size=800, overlap=100):
    """Full pipeline: bytes → cleaned chunks with metadata."""
    raw   = extract_text_from_pdf(file_bytes)
    clean = clean_text(raw)
    chunks = chunk_text(clean, chunk_size, overlap)

    for c in chunks:
        c["source"] = filename

    return chunks, clean
