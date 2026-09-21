"""Streamlit export controls: PDF, Word, CSV and copy-to-clipboard."""
from backend.export_pdf import build_pdf
from backend.export_docx import build_docx
from backend.export_csv import build_csv
from backend.export_text import plain_text, copy_button_html

_FAILED = ("Error calling Gemini API", "No API key provided",
           "No relevant document sections")
_DOCX = ("application/vnd.openxmlformats-officedocument."
         "wordprocessingml.document")


def qa_pairs(chat):
    """Pair each question with its answer; skip failed/empty answers."""
    pairs, question = [], None
    for turn in chat:
        role = turn.get("role")
        if role == "user":
            question = turn.get("content", "")
        elif role == "assistant" and question is not None:
            answer = turn.get("answer_only") or turn.get("content", "")
            if answer.strip() and not answer.startswith(_FAILED):
                pairs.append({"question": question, "answer": answer,
                              "citations": turn.get("citations") or []})
            question = None
    return pairs


def _html(st, markup, height):
    """Render HTML; fall back to the explicit import if st.components is absent."""
    try:
        st.components.v1.html(markup, height=height)
    except AttributeError:
        import streamlit.components.v1 as components
        components.html(markup, height=height)


def export_buttons(st, chat, registry=None):
    pairs = qa_pairs(chat)
    if not pairs:
        return
    names = list(registry.docs) if registry is not None else None
    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            "\u2b07 PDF", build_pdf(pairs, names),
            file_name="clarix_answers.pdf", mime="application/pdf",
            key="export_pdf_btn")
    with c2:
        st.download_button(
            "\u2b07 Word", build_docx(pairs, names),
            file_name="clarix_answers.docx", mime=_DOCX,
            key="export_docx_btn")
    with c3:
        st.download_button(
            "\u2b07 CSV", build_csv(pairs),
            file_name="clarix_answers.csv", mime="text/csv",
            key="export_csv_btn")

    text_all = plain_text(pairs)
    text_last = plain_text(pairs[-1:], start=len(pairs))
    c4, c5 = st.columns(2)
    with c4:
        _html(st, copy_button_html(
            text_last, "\U0001f4cb Copy last answer"), 44)
    with c5:
        _html(st, copy_button_html(
            text_all, "\U0001f4cb Copy all"), 44)
    with st.expander("Plain text (use this if copy is blocked)"):
        st.code(text_all, language=None)
