"""Facts read directly from each PDF file. Kept apart from the search
index: nothing here is chunked, scored or written by the model."""
import io
import pypdf
import pdfplumber
from backend.identity_intent import wants_identity

# Shown to the model, and by it, back to the person as the chunk tag in
# every citation for one of these records — e.g. "[Source: sfdr.pdf,
# Chunk #Document Info]" — so it needs to read like a real citation.
RECORD_LABEL = "Document Info"


class DocRegistry:
    def __init__(self):
        self.docs = {}

    def add(self, filename: str, file_bytes: bytes) -> dict:
        info = {"filename": filename, "pages": None, "props": {},
                "first_page": None, "first_page_no": None}
        # Properties (title/author/subject) aren't affected by the
        # extract_text() word-splitting bug pdf_extract.py works around,
        # so pypdf is fine for those; only the page count and the actual
        # first-page text use pdfplumber, for the same reason pdf_extract.py
        # does -- see that file's docstring.
        try:
            meta = pypdf.PdfReader(io.BytesIO(file_bytes)).metadata
            for key in ("title", "author", "subject"):
                val = str(getattr(meta, key, None) or "").strip()
                if val:
                    info["props"][key] = val
        except Exception:
            pass
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                info["pages"] = len(pdf.pages)
                for n in range(min(3, len(pdf.pages))):
                    text = (pdf.pages[n].extract_text() or "").strip()
                    if text:
                        info["first_page"], info["first_page_no"] = text, n + 1
                        break
        except Exception:
            pass  # a registry problem must never block indexing
        self.docs[filename] = info
        return info

    def _record(self, info: dict, cap: int) -> str:
        pages = info["pages"] if info["pages"] is not None else "unknown"
        lines = ["DOCUMENT RECORD (read directly from the PDF file, "
                 "not from search)",
                 f"File name: {info['filename']}",
                 f"Page count: {pages}"]
        if info["props"]:
            props = "; ".join(f"{k}: {v}" for k, v in info["props"].items())
            lines.append("Embedded PDF properties (set by whoever made the "
                         f"file; may be blank or wrong): {props}")
        else:
            lines.append("Embedded PDF properties: none set")
        if info["first_page"]:
            lines.append(f"Text of the first page with text "
                         f"(page {info['first_page_no']}):")
            lines.append(info["first_page"][:cap])
        else:
            lines.append("No extractable text on the first three pages "
                         "(possibly a scanned image).")
        return "\n".join(lines)

    def identity_chunks(self) -> list:
        cap = 1500 if len(self.docs) <= 3 else 600
        return [{"source": name, "text": self._record(info, cap),
                 "index": RECORD_LABEL, "score": 1.0}
                for name, info in self.docs.items()]

    def add_identity_context(self, question: str, chunks: list) -> list:
        if self.docs and wants_identity(question):
            return self.identity_chunks() + list(chunks)
        return chunks

    def clear(self):
        self.docs = {}
