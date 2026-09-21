"""Build a PDF of question/answer pairs (reportlab)."""
import io
import re
from datetime import datetime
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
)

_MAP = {"\u2192": "->", "\u2190": "<-", "\u2264": "<=", "\u2265": ">=",
        "\u2713": "v", "\u2714": "v", "\u2011": "-", "\u2212": "-"}


def _safe(text: str) -> str:
    """Standard PDF fonts only cover Latin-1/cp1252; swap or mark the rest."""
    for k, v in _MAP.items():
        text = text.replace(k, v)
    return text.encode("cp1252", "replace").decode("cp1252")


def _markup(text: str) -> str:
    text = re.sub(r"(?m)^\s*[\*\-]\s+", "\u2022 ", _safe(text))
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return text.replace("\n", "<br/>")


def build_pdf(pairs, doc_names=None, title="Compliance Q&A Export",
              brand="Clarix Intelligence") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, title=title, author=brand,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm)
    ss = getSampleStyleSheet()
    q_style = ParagraphStyle(
        "q", parent=ss["Heading3"], spaceBefore=8,
        textColor=colors.HexColor("#1B3A5C"))
    body = ParagraphStyle("b", parent=ss["BodyText"], leading=14)
    small = ParagraphStyle(
        "s", parent=ss["BodyText"], fontSize=8.5, leading=11,
        textColor=colors.HexColor("#555555"))

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillGray(0.4)
        canvas.drawString(20 * mm, 10 * mm, _safe(brand))
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {d.page}")
        canvas.restoreState()

    story = [Paragraph(escape(_safe(title)), ss["Title"]),
             Paragraph(f"Generated {datetime.now():%d %b %Y, %H:%M}", small)]
    if doc_names:
        names = ", ".join(doc_names)
        story.append(Paragraph("Documents indexed: " + escape(_safe(names)),
                               small))
    story.append(Spacer(1, 6))
    for n, p in enumerate(pairs, 1):
        story.append(HRFlowable(width="100%", color=colors.lightgrey))
        story.append(Paragraph(f"Q{n}. " + _markup(p["question"]), q_style))
        story.append(Paragraph(_markup(p["answer"]), body))
        if p.get("citations"):
            cites = "; ".join(p["citations"])
            story.append(Spacer(1, 3))
            story.append(Paragraph("<b>Cited sources:</b> "
                                   + escape(_safe(cites)), small))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
