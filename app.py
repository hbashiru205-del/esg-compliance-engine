import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from backend.document_processor import process_pdf
from backend.vector_store import VectorStore
from backend.query_engine import query_compliance
from config.settings import CHUNK_SIZE, CHUNK_OVERLAP, TOP_K

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ESG Compliance Engine",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0D1B2A; }
    .stApp { background-color: #0D1B2A; }

    [data-testid="stSidebar"] {
        background-color: #0A1520;
        border-right: 1px solid #1B3A5C;
    }

    .header-bar {
        background: linear-gradient(135deg, #1B6CA8, #0D4F82);
        padding: 20px 28px;
        border-radius: 12px;
        margin-bottom: 24px;
    }
    .header-bar h1 {
        color: white;
        font-size: 26px;
        font-weight: 700;
        margin: 0;
        letter-spacing: 0.5px;
    }
    .header-bar p {
        color: #BDD5EA;
        font-size: 13px;
        margin: 4px 0 0 0;
    }

    .answer-box {
        background-color: #0F2235;
        border: 1px solid #1B6CA8;
        border-left: 4px solid #2D9CDB;
        border-radius: 10px;
        padding: 20px 24px;
        margin: 12px 0;
        color: #E8F1FA;
        font-size: 14px;
        line-height: 1.7;
    }

    .citation-badge {
        display: inline-block;
        background-color: #1B3A5C;
        color: #2D9CDB;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 11px;
        margin: 3px 3px 3px 0;
        border: 1px solid #2D4A6A;
    }

    .metric-card {
        background-color: #0F2235;
        border: 1px solid #1B3A5C;
        border-radius: 10px;
        padding: 14px 18px;
        text-align: center;
    }
    .metric-value {
        font-size: 28px;
        font-weight: 700;
        color: #2D9CDB;
    }
    .metric-label {
        font-size: 11px;
        color: #5A6473;
        text-transform: uppercase;
        letter-spacing: 0.8px;
    }

    .status-pass     { color: #27AE60; font-weight: 600; }
    .status-partial  { color: #F39C12; font-weight: 600; }
    .status-fail     { color: #E74C3C; font-weight: 600; }

    .stTextInput > div > div > input,
    .stTextArea textarea {
        background-color: #0F2235 !important;
        color: #E8F1FA !important;
        border: 1px solid #1B3A5C !important;
        border-radius: 8px !important;
    }

    .stButton > button {
        background: linear-gradient(135deg, #1B6CA8, #0D4F82);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 10px 24px;
        font-weight: 600;
        width: 100%;
        transition: opacity 0.2s;
    }
    .stButton > button:hover { opacity: 0.88; }

    [data-testid="stFileUploader"] {
        background-color: #0F2235;
        border: 1px dashed #1B6CA8;
        border-radius: 10px;
        padding: 10px;
    }

    #MainMenu, footer { visibility: hidden; }

    .stTabs [data-baseweb="tab"] {
        color: #5A6473;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        color: #2D9CDB !important;
        border-bottom-color: #2D9CDB !important;
    }

    h1, h2, h3, h4 { color: #E8F1FA; }
    p, li { color: #A0B4C8; }
    label { color: #A0B4C8 !important; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
if "store"       not in st.session_state: st.session_state.store       = VectorStore()
if "chat"        not in st.session_state: st.session_state.chat        = []
if "docs_loaded" not in st.session_state: st.session_state.docs_loaded = []
if "test_results"not in st.session_state: st.session_state.test_results= None

store = st.session_state.store

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        placeholder="AIza...",
    
        

        help="Your key is never stored. Used only for this session."
    )

    st.markdown("---")
    st.markdown("### 📄 Upload Documents")
    uploaded = st.file_uploader(
        "Upload regulatory PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )

    if uploaded:
        new_files = [f.name for f in uploaded if f.name not in st.session_state.docs_loaded]
        if new_files:
            with st.spinner("Processing documents..."):
                for file in uploaded:
                    if file.name not in st.session_state.docs_loaded:
                        chunks, _ = process_pdf(
                            file.read(), file.name,
                            chunk_size=CHUNK_SIZE,
                            overlap=CHUNK_OVERLAP
                        )
                        store.add_chunks(chunks)
                        st.session_state.docs_loaded.append(file.name)
            st.success(f"✅ {len(new_files)} document(s) indexed")

    if st.session_state.docs_loaded:
        st.markdown("**Indexed documents:**")
        for doc in st.session_state.docs_loaded:
            st.markdown(f"• `{doc}`")
        st.markdown(f"**Total chunks:** `{store.doc_count}`")

        if st.button("🗑 Clear All Documents"):
            store.clear()
            st.session_state.docs_loaded = []
            st.session_state.chat = []
            st.rerun()

    st.markdown("---")
    st.markdown("### 📊 System Stats")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Chunks", store.doc_count)
    with col2:
        st.metric("Docs", len(st.session_state.docs_loaded))

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="header-bar">
    <h1>⚖️ ESG Compliance Engine</h1>
    <p>AI-powered regulatory document intelligence — instant, cited, audit-ready answers</p>
</div>
""", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["💬 Ask Questions", "🧪 Accuracy Test", "📖 How It Works"])

with tab1:
    if not st.session_state.docs_loaded:
        st.info("👈 Upload a regulatory PDF in the sidebar to get started.")
    else:
        for turn in st.session_state.chat:
            if turn["role"] == "user":
                st.markdown(f"""
                <div style='text-align:right; margin:8px 0'>
                    <span style='background:#1B3A5C; color:#E8F1FA; padding:10px 16px;
                    border-radius:18px 18px 4px 18px; display:inline-block;
                    max-width:80%; font-size:14px;'>{turn["content"]}</span>
                </div>""", unsafe_allow_html=True)
            else:
                answer   = turn["content"]
                citations = turn.get("citations", [])
                badge_html = "".join(
                    f'<span class="citation-badge">{c}</span>' for c in citations
                )
                st.markdown(f"""
                <div class="answer-box">
                    {answer}
                    {'<br><br><b style="color:#5A6473;font-size:11px;">CITED SOURCES:</b><br>' + badge_html if citations else ''}
                </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        col_q, col_btn = st.columns([5, 1])
        with col_q:
            question = st.text_input(
                "Ask a compliance question",
                placeholder="e.g. What are the Scope 3 emissions disclosure requirements?",
                label_visibility="collapsed",
                key="question_input"
            )
        with col_btn:
            ask = st.button("Ask ➤")

        st.markdown("<p style='font-size:11px; color:#3A4F63; margin-top:6px'>Quick questions:</p>",
                    unsafe_allow_html=True)
        qcols = st.columns(3)
        quick_qs = [
            "What are the main disclosure requirements?",
            "What penalties apply for non-compliance?",
            "Who is responsible for compliance oversight?",
        ]
        for i, qq in enumerate(quick_qs):
            with qcols[i]:
                if st.button(qq, key=f"qq_{i}"):
                    question = qq
                    ask = True

        if ask and question.strip():
            if not api_key:
                st.error("Please enter your Gemini API key in the sidebar.")
            else:
                with st.spinner("Retrieving relevant sections and generating answer..."):
                    chunks   = store.retrieve(question, top_k=TOP_K)
                    response = query_compliance(
                        question, chunks,
                        api_key=api_key,
                        chat_history=st.session_state.chat
                    )

                st.session_state.chat.append({"role": "user",    "content": question})
                st.session_state.chat.append({
                    "role":      "assistant",
                    "content":   response["answer"],
                    "citations": response["sources_used"],
                })
                st.rerun()

        if st.session_state.chat:
            if st.button("🗑 Clear chat"):
                st.session_state.chat = []
                st.rerun()

with tab2:
    st.markdown("### 🧪 System Accuracy Evaluation")
    st.markdown(
        "Runs 5 standard compliance questions against your uploaded documents "
        "and scores each answer for citation quality and relevance."
    )

    if not st.session_state.docs_loaded:
        st.info("Upload a document first to run the accuracy test.")
    elif not api_key:
        st.warning("Enter your Gemini API key in the sidebar to run the test.")
    else:
        if st.button("▶ Run Accuracy Test"):
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tests"))
            from tests.accuracy_test import run_accuracy_test
            with st.spinner("Running 5 test questions... this takes ~30 seconds"):
                results = run_accuracy_test(store, api_key, top_k=TOP_K)
            st.session_state.test_results = results

        if st.session_state.test_results:
            r = st.session_state.test_results
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f"""<div class="metric-card">
                    <div class="metric-value">{r['accuracy_pct']}%</div>
                    <div class="metric-label">Overall Accuracy</div></div>""",
                    unsafe_allow_html=True)
            with c2:
                st.markdown(f"""<div class="metric-card">
                    <div class="metric-value">{r['passed']}/{r['total']}</div>
                    <div class="metric-label">Tests Passed</div></div>""",
                    unsafe_allow_html=True)
            with c3:
                cited = sum(1 for x in r["results"] if x["cited"])
                st.markdown(f"""<div class="metric-card">
                    <div class="metric-value">{cited}/{r['total']}</div>
                    <div class="metric-label">Cited Answers</div></div>""",
                    unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            for res in r["results"]:
                status_class = {
                    "PASS":    "status-pass",
                    "PARTIAL": "status-partial",
                    "FAIL":    "status-fail",
                }[res["status"]]
                with st.expander(f"{res['question']}  —  [{res['status']}]"):
                    st.markdown(f"**Status:** <span class='{status_class}'>{res['status']}</span>",
                                unsafe_allow_html=True)
                    st.markdown(f"**Cited:** {'✅' if res['cited'] else '❌'}  |  "
                                f"**Chunks retrieved:** {res['n_chunks']}")
                    st.markdown("**Answer:**")
                    st.markdown(f"""<div class="answer-box">{res['answer']}</div>""",
                                unsafe_allow_html=True)

with tab3:
    st.markdown("### 📖 How the ESG Compliance Engine Works")

    steps = [
        ("1. Upload", "You upload your regulatory PDF documents (CSRD, AML, GDPR, internal policies, etc.)."),
        ("2. Process", "The engine splits each document into intelligent chunks, preserving sentence boundaries."),
        ("3. Index",   "Each chunk is indexed using TF-IDF scoring — making every section instantly searchable."),
        ("4. Retrieve","When you ask a question, the system finds the most relevant sections from your documents."),
        ("5. Generate","Gemini reads only those sections and generates a precise, cited answer."),
        ("6. Cite",    "Every answer includes exact source references — making it fully audit-ready."),
    ]
    for title, desc in steps:
        st.markdown(f"""
        <div style='background:#0F2235; border:1px solid #1B3A5C; border-radius:10px;
        padding:14px 20px; margin:8px 0;'>
            <b style='color:#2D9CDB'>{title}</b>
            <p style='color:#A0B4C8; margin:4px 0 0 0; font-size:13px;'>{desc}</p>
        </div>""", unsafe_allow_html=True)

    st.markdown("### 🔒 Data Privacy")
    st.markdown("""
    <div style='background:#0A1F0A; border:1px solid #27AE60; border-radius:10px; padding:16px 20px;'>
        <p style='color:#A8D5A2; margin:0; font-size:13px;'>
