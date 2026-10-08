import sys
import os
import html

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

from backend.pdf_extract import process_pdf
from backend.balanced_store import BalancedStore as VectorStore
from backend.query_engine import query_compliance
from backend.doc_registry import DocRegistry
from backend.export_ui import export_buttons
from backend.excerpts_ui import make_excerpt_records, render_excerpts
from backend.trial_gate import (
    trial_exceeded,
    render_trial_status,
    render_trial_blocked,
)
from backend.accounts import (
    valid_name,
    create_account,
    get_account,
    increment_usage,
)
from config.settings import CHUNK_SIZE, CHUNK_OVERLAP, TOP_K


# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="ClariX Intelligence",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    """
<style>
    .main {
        background-color: #0D1B2A;
    }

    .stApp {
        background-color: #0D1B2A;
    }

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

    .requirement-card {
        background-color: #0F2235;
        border: 1px solid #1B3A5C;
        border-left: 4px solid #27AE60;
        border-radius: 10px;
        padding: 16px 18px;
        margin: 10px 0;
    }

    .requirement-title {
        color: #E8F1FA;
        font-size: 15px;
        font-weight: 600;
        margin-bottom: 12px;
    }

    .requirement-label {
        color: #5A6473;
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.7px;
        font-weight: 700;
    }

    .requirement-value {
        color: #A0B4C8;
        font-size: 13px;
        margin-top: 3px;
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

    .stButton > button:hover {
        opacity: 0.88;
    }

    [data-testid="stFileUploader"] {
        background-color: #0F2235;
        border: 1px dashed #1B6CA8;
        border-radius: 10px;
        padding: 10px;
    }

    #MainMenu,
    footer {
        visibility: hidden;
    }

    .stTabs [data-baseweb="tab"] {
        color: #5A6473;
        font-weight: 500;
    }

    .stTabs [aria-selected="true"] {
        color: #2D9CDB !important;
        border-bottom-color: #2D9CDB !important;
    }

    h1,
    h2,
    h3,
    h4 {
        color: #E8F1FA;
    }

    p,
    li {
        color: #A0B4C8;
    }

    label {
        color: #A0B4C8 !important;
    }
</style>
""",
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────

if "store" not in st.session_state:
    st.session_state.store = VectorStore()

if "chat" not in st.session_state:
    st.session_state.chat = []

if "docs_loaded" not in st.session_state:
    st.session_state.docs_loaded = []

if "test_results" not in st.session_state:
    st.session_state.test_results = None

if "registry" not in st.session_state:
    st.session_state.registry = DocRegistry()


# ─────────────────────────────────────────────────────────────────────────────
# FREE TRIAL ACCOUNT
# ─────────────────────────────────────────────────────────────────────────────

if "account_token" not in st.session_state:
    st.session_state.account_token = st.query_params.get("acct", "")

account = get_account(st.session_state.account_token)

if account is None:

    st.markdown("### Start your free trial")

    st.markdown(
        "Enter your name to begin -- no email or password needed. "
        "This gives you 5 free questions."
    )

    name_input = st.text_input(
        "Your name",
        key="trial_name_input",
    )

    if st.button("Start"):

        if valid_name(name_input):

            token = create_account(name_input)

            st.session_state.account_token = token
            st.query_params["acct"] = token

            st.rerun()

        else:

            st.error(
                "Please enter a name (letters, numbers, spaces, "
                "up to 60 characters)."
            )

    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# API KEY
# ─────────────────────────────────────────────────────────────────────────────

api_key = st.secrets.get("GEMINI_API_KEY", "")

store = st.session_state.store
registry = st.session_state.registry


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:

    st.markdown("### 📄 Upload Documents")

    uploaded = st.file_uploader(
        "Upload regulatory PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if uploaded:

        new_files = [
            f.name
            for f in uploaded
            if f.name not in st.session_state.docs_loaded
        ]

        if new_files:

            with st.spinner("Processing documents..."):

                for file in uploaded:

                    if file.name not in st.session_state.docs_loaded:

                        raw = file.read()

                        chunks, _ = process_pdf(
                            raw,
                            file.name,
                            chunk_size=CHUNK_SIZE,
                            overlap=CHUNK_OVERLAP,
                        )

                        registry.add(
                            file.name,
                            raw,
                        )

                        store.add_chunks(chunks)

                        st.session_state.docs_loaded.append(
                            file.name
                        )

            st.success(
                f"✅ {len(new_files)} document(s) indexed"
            )

    if st.session_state.docs_loaded:

        st.markdown("**Indexed documents:**")

        for doc in st.session_state.docs_loaded:
            st.markdown(f"• `{doc}`")

        st.markdown(
            f"**Total chunks:** `{store.doc_count}`"
        )

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
        st.metric(
            "Chunks",
            store.doc_count,
        )

    with col2:
        st.metric(
            "Docs",
            len(st.session_state.docs_loaded),
        )


# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    """
<div class="header-bar">

    <h1>⚖️ ClariX Intelligence</h1>

    <p>
        Evidence-led regulatory intelligence —
        understand requirements, find supporting evidence,
        and trace answers to their source.
    </p>

</div>
""",
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(
    [
        "💬 Regulatory Research",
        "🧪 Accuracy Test",
        "📖 How It Works",
    ]
)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — REGULATORY RESEARCH
# ─────────────────────────────────────────────────────────────────────────────

with tab1:

    if not st.session_state.docs_loaded:

        st.info(
            "👈 Upload a regulatory PDF in the sidebar to get started."
        )

    else:

        for turn in st.session_state.chat:

            if turn["role"] == "user":

                st.markdown(
                    f"""
                    <div style="text-align:right; margin:8px 0">
                        <span style="
                            background:#1B3A5C;
                            color:#E8F1FA;
                            padding:10px 16px;
                            border-radius:18px 18px 4px 18px;
                            display:inline-block;
                            max-width:80%;
                            font-size:14px;
                        ">
                            {html.escape(turn["content"])}
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            else:

                answer = turn["content"]

                citations = turn.get(
                    "citations",
                    [],
                )

                requirements = turn.get(
                    "requirements",
                    [],
                )

                render_excerpts(
                    st,
                    turn.get("excerpts", []),
                )

                badge_html = "".join(
                    f'<span class="citation-badge">'
                    f'{html.escape(str(c))}'
                    f'</span>'
                    for c in citations
                )

                st.markdown(
                    f"""
                    <div class="answer-box">
                        {answer}

                        {
                            '<br><br>'
                            '<b style="color:#5A6473;font-size:11px;">'
                            'CITED SOURCES:'
                            '</b><br>'
                            + badge_html
                            if citations
                            else ""
                        }
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # ─────────────────────────────────────────────────────
                # STRUCTURED REQUIREMENTS
                # ─────────────────────────────────────────────────────

                if requirements:

                    with st.expander(
                        f"🔎 Structured regulatory requirements "
                        f"({len(requirements)})"
                    ):

                        st.markdown(
                            """
                            <p style="
                                font-size:12px;
                                color:#7F93A8;
                            ">
                                ClariX has structured the relevant
                                regulatory text into requirement
                                elements. These include who the
                                requirement applies to, what action
                                is required, conditions, exceptions,
                                and cross-references.
                            </p>
                            """,
                            unsafe_allow_html=True,
                        )

                        for requirement in requirements:

                            source = requirement.get(
                                "source",
                                {},
                            )

                            conditions = requirement.get(
                                "conditions",
                                [],
                            )

                            exceptions = requirement.get(
                                "exceptions",
                                [],
                            )

                            cross_references = requirement.get(
                                "cross_references",
                                [],
                            )

                            if not isinstance(
                                conditions,
                                list,
                            ):
                                conditions = []

                            if not isinstance(
                                exceptions,
                                list,
                            ):
                                exceptions = []

                            if not isinstance(
                                cross_references,
                                list,
                            ):
                                cross_references = []

                            source_text = str(
                                source.get(
                                    "filename",
                                    "Unknown",
                                )
                            )

                            if source.get("page"):
                                source_text += (
                                    f" · Page "
                                    f"{source['page']}"
                                )

                            if source.get(
                                "reference"
                            ):
                                source_text += (
                                    f" · "
                                    f"{source['reference']}"
                                )

                            st.markdown(
                                f"""
                                <div class="requirement-card">

                                    <div class="requirement-title">
                                        {html.escape(
                                            str(
                                                requirement.get(
                                                    "requirement",
                                                    ""
                                                )
                                            )
                                        )}
                                    </div>

                                    <div class="requirement-label">
                                        Subject
                                    </div>

                                    <div class="requirement-value">
                                        {html.escape(
                                            str(
                                                requirement.get(
                                                    "subject",
                                                    ""
                                                )
                                                or
                                                "Not explicitly identified"
                                            )
                                        )}
                                    </div>

                                    <br>

                                    <div class="requirement-label">
                                        Action
                                    </div>

                                    <div class="requirement-value">
                                        {html.escape(
                                            str(
                                                requirement.get(
                                                    "action",
                                                    ""
                                                )
                                                or
                                                "Not explicitly identified"
                                            )
                                        )}
                                    </div>

                                    <br>

                                    <div class="requirement-label">
                                        Object
                                    </div>

                                    <div class="requirement-value">
                                        {html.escape(
                                            str(
                                                requirement.get(
                                                    "object",
                                                    ""
                                                )
                                                or
                                                "Not explicitly identified"
                                            )
                                        )}
                                    </div>

                                    <br>

                                    <div class="requirement-label">
                                        Conditions
                                    </div>

                                    <div class="requirement-value">
                                        {html.escape(
                                            ", ".join(
                                                str(x)
                                                for x in conditions
                                            )
                                            or
                                            "None identified in retrieved text"
                                        )}
                                    </div>

                                    <br>

                                    <div class="requirement-label">
                                        Exceptions
                                    </div>

                                    <div class="requirement-value">
                                        {html.escape(
                                            ", ".join(
                                                str(x)
                                                for x in exceptions
                                            )
                                            or
                                            "None identified in retrieved text"
                                        )}
                                    </div>

                                    <br>

                                    <div class="requirement-label">
                                        Scope
                                    </div>

                                    <div class="requirement-value">
                                        {html.escape(
                                            str(
                                                requirement.get(
                                                   
