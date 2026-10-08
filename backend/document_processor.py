import re
import hashlib
from pathlib import Path
import pypdf


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF bytes while preserving page boundaries."""
    import io

    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    pages = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""

        if text.strip():
            pages.append({
                "page": i + 1,
                "text": text.strip(),
            })

    return pages


def clean_text(text: str) -> str:
    """Clean extracted document text."""
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


def detect_regulatory_reference(text: str) -> str:
    """
    Try to identify an Article, paragraph, section, or similar
    regulatory reference from a chunk.
    """

    patterns = [
        r'\bArticle\s+\d+(?:\([^)]+\))?',
        r'\bArt\.\s*\d+(?:\([^)]+\))?',
        r'\bParagraph\s+\d+(?:\([^)]+\))?',
        r'\bparagraph\s+\d+(?:\([^)]+\))?',
        r'\bSection\s+\d+(?:\.\d+)*',
        r'\bsection\s+\d+(?:\.\d+)*',
        r'\b§\s*\d+(?:\.\d+)*',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return match.group(0)

    return ""


def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 100,
    page_number: int = None,
):
    """
    Split text into overlapping chunks while preserving metadata.
    """

    chunks = []
    start = 0
    idx = 0

    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            for boundary in ['. ', '.\n', '! ', '? ', '\n\n']:
                pos = text.rfind(
                    boundary,
                    start + chunk_size // 2,
                    end
                )

                if pos != -1:
                    end = pos + len(boundary)
                    break

        chunk_text_content = text[start:end].strip()

        if chunk_text_content:
            chunk_id = hashlib.md5(
                f"{idx}:{chunk_text_content[:50]}".encode()
            ).hexdigest()[:12]

            chunks.append({
                "id": chunk_id,
                "text": chunk_text_content,
                "char_start": start,
                "char_end": end,
                "index": idx,
                "page_start": page_number,
                "page_end": page_number,
                "regulatory_reference": detect_regulatory_reference(
                    chunk_text_content
                ),
            })

            idx += 1

        next_start = end - overlap

        if next_start <= start:
            next_start = end

        start = next_start

    return chunks


def process_pdf(
    file_bytes: bytes,
    filename: str,
    chunk_size: int = 800,
    overlap: int = 100,
):
    """
    Full PDF processing pipeline.

    Returns:
        chunks, clean_text
    """

    pages = extract_text_from_pdf(file_bytes)

    all_chunks = []
    cleaned_pages = []

    for page_data in pages:
        page_number = page_data["page"]
        page_text = clean_text(page_data["text"])

        if not page_text:
            continue

        cleaned_pages.append(
            f"[Page {page_number}]\n{page_text}"
        )

        page_chunks = chunk_text(
            page_text,
            chunk_size=chunk_size,
            overlap=overlap,
            page_number=page_number,
        )

        for chunk in page_chunks:
            chunk["source"] = filename

            # Keep the page explicitly available for citations.
            chunk["page"] = page_number

            all_chunks.append(chunk)

    clean = "\n\n".join(cleaned_pages)

    return all_chunks, clean
