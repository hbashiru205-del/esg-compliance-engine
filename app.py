import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from backend.pdf_extract import process_pdf
from backend.balanced_store import BalancedStore as VectorStore
from backend.query_engine import query_compliance
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
tab1, tab2, tab3 = st.tabs(["💬 Ask Questions", "🧪 Accuracy Test", "📖 How It Works"])
