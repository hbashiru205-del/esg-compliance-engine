import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from backend.pdf_extract import process_pdf
from backend.balanced_store import BalancedStore as VectorStore
from backend.query_engine import query_compliance
from backend.requirement_engine import extract_requirements, run_gap_analysis
from backend.doc_registry import DocRegistry
from backend.export_ui import export_buttons
from backend.excerpts_ui import make_excerpt_records, render_excerpts
from backend.trial_gate import trial_exceeded, render_trial_status, render_trial_blocked
from backend.accounts import valid_name, create_account, get_account, increment_usage
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
.stButton > button:hover { opacity: 0.88; }

    [data-testid="stFileUploader"] {
        background-color: #0F2235;
        border: 1px dashed #1B6CA8;
        border-radius: 10px;
        padding: 10px;
    }

    #MainMenu, footer { visibility: hidden; }/* -- part 2/7 -- */
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
if "structured_requirements" not in st.session_state: st.session_state.structured_requirements = []
if "gap_results" not in st.session_state: st.session_state.gap_results = []
if "registry"    not in st.session_state: st.session_state.registry    = DocRegistry()

# ── Free-trial account (name only -- no email, no password, no access ──────────
# code needed up front any more). Everyone gets 5 free questions immediately;
# an access code is only asked for once that trial is used up -- see
# backend/trial_gate.render_trial_blocked for that flow.
# The token lives in the page's own URL so it survives an ordinary refresh;
# losing that exact link starts a new trial, which is a known, disclosed gap.
if "account_token" not in st.session_state:
    st.session_state.account_token = st.query_params.get("acct", "")

account = get_account(st.session_state.account_token)

if account is None:
    st.markdown("### Start your free trial")
    st.markdown("Enter your name to begin -- no email or password needed. "
                 "This gives you 5 free questions.")
    name_input = st.text_input("Your name", key="trial_name_input")
    if st.button("Start"):
        if valid_name(name_input):
            token = create_account(name_input)
            st.session_state.account_token = token
            st.query_params["acct"] = token
            st.rerun()
        else:
            st.error("Please enter a name (letters, numbers, spaces, up to 60 characters).")
    st.stop()

# ── API key (server-side, invisible to users) ──────────────────────────────────
api_key = st.secrets.get("GEMINI_API_KEY", "")

store = st.session_state.store
registry = st.session_state.registry

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📄 Upload Documents")
    uploaded = st.file_uploader(
        "Upload regulatory PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed"
)# -- part 3/7 --
    if uploaded:
        new_files = [f.name for f in uploaded if f.name not in st.session_state.docs_loaded]
        if new_files:
            with st.spinner("Processing documents..."):
                for file in uploaded:
                    if file.name not in st.session_state.docs_loaded:
                        raw = file.read()
                        chunks, _ = process_pdf(
                            raw, file.name,
                            chunk_size=CHUNK_SIZE,
                            overlap=CHUNK_OVERLAP
                        )
                        registry.add(file.name, raw)
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
            registry.clear()
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
tab1, tab2, tab3, tab4 = st.tabs(["💬 Ask Questions", "🧩 Regulatory Intelligence", "🧪 Accuracy Test", "📖 How It Works"])# -- part 4/7 --
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
                reasoning = turn.get("reasoning", "")
                citations = turn.get("citations", [])
                if reasoning:
                    with st.expander("🔍 Show reasoning"):
                        st.markdown(reasoning)
                render_excerpts(st, turn.get("excerpts", []))
                badge_html = "".join(
                    f'<span class="citation-badge">{c}</span>' for c in citations
                )
                st.markdown(f"""
                <div class="answer-box">
                    {answer}
                    {'<br><br><b style="color:#5A6473;font-size:11px;">CITED SOURCES:</b><br>' + badge_html if citations else ''}
                </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        render_trial_status(st, st.session_state.account_token)
        col_q, col_btn = st.columns([5, 1])

        with col_q:
            question = st.text_input(
                "Ask a compliance question",
                placeholder="e.g. What are the Scope 3 emissions disclosure requirements?",
                label_visibility="collapsed",
                key="question_input",
            )

        with col_btn:
            ask = st.button("Ask ➤")

        st.markdown(
            "<p style='font-size:11px; color:#3A4F63; margin-top:6px'>Quick questions:</p>",
            unsafe_allow_html=True,
        )

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
            if trial_exceeded(st.session_state.account_token):
                render_trial_blocked(st, st.session_state.account_token)
            elif not api_key:
                st.error("System configuration issue — please contact support.")
            else:
                with st.spinner("Retrieving relevant sections and generating answer..."):
                    chunks   = store.retrieve(question, top_k=TOP_K)
                    chunks   = registry.add_identity_context(question, chunks)
                    response = query_compliance(
                        question, chunks,
                        api_key=api_key,
                        chat_history=st.session_state.chat
                    )

                st.session_state.chat.append({"role": "user",    "content": question})
                st.session_state.chat.append({
                    "role":       "assistant",
                    "content":    response["answer"],
                    "answer_only":response["answer"],
                    "reasoning":  response.get("reasoning", ""),
                    "citations":  response["sources_used"],
                    "excerpts":   make_excerpt_records(chunks),
                })
                increment_usage(st.session_state.account_token)
                st.rerun()

            if st.session_state.chat:
        if st.button("🗑 Clear chat"):
            st.session_state.chat = []
            st.rerun()

    export_buttons(st, st.session_state.chat, registry)


with tab2:
    st.markdown("### 🧩 Regulatory Intelligence")
        "Turn retrieved regulatory text into structured requirements before using it "
        "for research or evidence-led gap analysis."
    )

    if not st.session_state.docs_loaded:
        st.info("Upload a regulatory PDF first.")
    elif not api_key:
        st.warning("System configuration issue — please contact support.")
    else:
        requirement_question = st.text_input(
            "What regulatory area should ClariX understand?",
            placeholder="e.g. What are the climate transition-plan requirements?",
            key="requirement_question",
        )
        if st.button("Extract structured requirements", key="extract_requirements_btn") and requirement_question.strip():
            with st.spinner("Retrieving and structuring regulatory requirements..."):
                req_chunks = store.retrieve(requirement_question, top_k=TOP_K)
                req_chunks = registry.add_identity_context(requirement_question, req_chunks)
                st.session_state.structured_requirements = extract_requirements(
                    req_chunks, api_key=api_key, max_requirements=10
                )

        requirements = st.session_state.get("structured_requirements", [])
        if requirements:
            st.success(f"{len(requirements)} structured requirement(s) identified.")
            for req in requirements:
                with st.expander(f"{req['id']} · {req['requirement']}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"**Subject**\n\n{req['subject'] or 'Not stated in retrieved text'}")
                        st.markdown(f"**Action**\n\n{req['action'] or 'Not stated in retrieved text'}")
                        st.markdown(f"**Object**\n\n{req['object'] or 'Not stated in retrieved text'}")
                    with c2:
                        st.markdown(f"**Scope**\n\n{req['scope'] or 'Not stated in retrieved text'}")
                        st.markdown(f"**Conditions**\n\n{', '.join(req['conditions']) if req['conditions'] else 'None identified'}")
                        st.markdown(f"**Exceptions**\n\n{', '.join(req['exceptions']) if req['exceptions'] else 'None identified'}")
                    if req["cross_references"]:
                        st.markdown("**Cross-references**")
                        for ref in req["cross_references"]:
                            st.markdown(f"- {ref}")
                    source = req["source"]
                    st.caption(
                        f"Source: {source.get('filename', 'Unknown')} · "
                        f"{source.get('reference') or 'reference not identified'} · "
                        f"page {source.get('page') or 'unknown'}"
                    )
                    
        st.markdown("---")
        st.markdown("#### Evidence-led gap analysis")
        st.caption(
            "The next step is to run these structured requirements against a separate "
            "client-evidence document set. This reuses the same requirement objects."
        )
        client_files = st.file_uploader(
            "Upload client evidence PDFs",
            type=["pdf"],
            accept_multiple_files=True,
            key="client_evidence_uploader",
        )
        if client_files and requirements:
            if st.button("Run evidence assessment", key="run_gap_btn"):
                client_store = VectorStore()
                for file in client_files:
                    raw = file.read()
                    client_chunks, _ = process_pdf(
                        raw, file.name,
                        chunk_size=CHUNK_SIZE,
                        overlap=CHUNK_OVERLAP,
                    )
                    client_store.add_chunks(client_chunks)
                with st.spinner("Matching requirements to client evidence..."):
                    gap_results = run_gap_analysis(
                        requirements, client_store, api_key=api_key, evidence_top_k=4
                    )
                st.session_state.gap_results = gap_results

        gap_results = st.session_state.get("gap_results", [])
        if gap_results:
            counts = {s: 0 for s in ["Addressed", "Partially addressed", "Potential gap"]}
            for item in gap_results:
                counts[item["assessment"]["status"]] += 1
            a, b, c = st.columns(3)
            a.metric("Addressed", counts["Addressed"])
            b.metric("Partially addressed", counts["Partially addressed"])
            c.metric("Potential gaps", counts["Potential gap"])

            for item in gap_results:
                assessment = item["assessment"]
                with st.expander(f"{item['id']} · {assessment['status']} · {item['requirement']}"):
                    st.markdown(f"**Assessment**\n\n{assessment['assessment']}")
                    if assessment["missing_elements"]:
                        st.markdown("**Elements not demonstrated**")
                        for missing in assessment["missing_elements"]:
                            st.markdown(f"- {missing}")
                    if assessment["evidence"]:
                        st.markdown("**Evidence used**")
                        for ev in assessment["evidence"]:
                                                        st.markdown(
                                f"- **{ev.get('filename', 'Unknown')}** · "
                                f"{ev.get('reference') or 'reference not identified'} · "
                                f"page {ev.get('page') or 'unknown'}"
                            )
                            if ev.get("quote"):
                                st.caption(ev["quote"])

with tab2:
    st.markdown("### 🧪 System Accuracy Evaluation")
    st.markdown(
        "Runs 5 standard compliance questions against your uploaded documents "
        "and scores each answer for citation quality and relevance."
    )

    if not st.session_state.docs_loaded:
        st.info("Upload a document first to run the accuracy test.")
    elif not api_key:
        st.warning("System configuration issue — please contact support.")
    else:
        if st.button("▶ Run Accuracy Test"):
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tests"))
            from tests.accuracy_test import run_accuracy_test
            with st.spinner("Running 5 test questions... this takes ~30 seconds"):
                results = run_accuracy_test(store, api_key, top_k=TOP_K, registry=registry)
            st.session_state.test_results = results# -- part 6/7 --
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

with tab4:
    st.markdown("### 📖 How the ESG Compliance Engine Works")# -- part 7/7 --
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
        ✅ Your documents themselves are processed <b>in-session only</b> and never stored.<br>
        ℹ️ Your trial account stores only your name and a count of questions asked -- nothing else, and no document content.<br>
        ℹ️ Trial sessions currently run on shared processing infrastructure suited to public and general regulatory documents. Pilot clients are moved to a dedicated, paid processing tier.
        </p>
    </div>""", unsafe_allow_html=True)
    
