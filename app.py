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
