"""Detect questions about the documents themselves (title, publisher,
page count, which files are loaded) as opposed to their content."""
import re

_DOC = (r"(?:document|pdf|file|regulation|directive|report|policy|paper|"
        r"standard|act|guidance)s?")

_PATTERNS = [
    r"\btitles?\b|\btitled\b|\bentitled\b",
    rf"\b(?:what|which)\s+{_DOC}\s+(?:is|are)\s+(?:this|that|these|those|it)\b",
    rf"\bwhat\s+(?:is|are)\s+(?:this|that|these|those)\s+{_DOC}\b",
    rf"\b(?:called|named|name\s+of)\b.*\b{_DOC}\b",
    rf"\b{_DOC}\b.*\b(?:called|named)\b",
    r"\b(?:who|which\s+(?:organi[sz]ation|body|authority|institution))"
    r"\s+(?:published|issued|authored|wrote|produced|released|adopted)\b",
    r"\b(?:author|publisher|issuer|issued\s+by|published\s+by|written\s+by)\b",
    r"\bhow\s+many\s+(?:pages|documents|files|pdfs)\b",
    r"\b(?:page\s+count|number\s+of\s+pages)\b",
    r"\bwhat\s+(?:documents|files|pdfs)\b.*\b(?:uploaded|loaded|indexed)\b",
    r"\b(?:which|what)\s+(?:documents|files|pdfs)\s+(?:are|do|have|did)\b",
    r"\b(?:list|show)\s+(?:me\s+)?(?:all\s+)?(?:the\s+)?"
    r"(?:uploaded\s+|indexed\s+|loaded\s+)?(?:documents|files|pdfs)\b",
]
_RX = [re.compile(p) for p in _PATTERNS]


def wants_identity(question: str) -> bool:
    q = (question or "").lower()
    return any(rx.search(q) for rx in _RX)
