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
if "authenticated" not in st.session_state: st.session_state.authenticated = False

# ── Access Gate ──────────────────────────────────────────────────────────────
VALID_CODES = [c.strip() for c in st.secrets.get("ACCESS_CODES", "").split(",") if c.strip()]

if not st.session_state.authenticated:
    st.markdown("### Access Required")
    st.markdown("Enter the access code provided to you to continue.")
    code_input = st.text_input("Access code", type="password")
    if st.button("Enter"):
        if code_input.strip() in VALID_CODES:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Invalid access code. Contact hello@clarixintel.com for access.")
    st.stop()

# ── API key (server-side, invisible to users) ──────────────────────────────────
api_key = st.secrets.get("GEMINI_API_KEY", "")

store = st.session_state.store

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
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
    

    



    
    
    

    

