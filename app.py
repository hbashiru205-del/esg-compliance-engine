import os
import sys
import html
import io
from datetime import datetime

import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

from backend.pdf_extract import process_pdf
from backend.balanced_store import BalancedStore
from backend.query_engine import query_compliance
from backend.requirement_engine import prepare_requirements, run_gap_analysis
from backend.doc_registry import DocRegistry
from backend.export_ui import export_buttons
from backend.excerpts_ui import make_excerpt_records, render_excerpts
from backend.trial_gate import trial_exceeded, render_trial_status, render_trial_blocked
from backend.accounts import valid_name, valid_username, create_user, authenticate_user, login_lockout_seconds, get_account, increment_usage
from backend.admin_ui import render_admin_panel
from config.settings import CHUNK_SIZE, CHUNK_OVERLAP, TOP_K


# -----------------------------------------------------------------------------
# Page configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="ClariX Intelligence",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------------------------------------------------------
# Visual system — designed to mirror the Lovable ClariX prototype
# -----------------------------------------------------------------------------
st.markdown(
    """
<style>
:root {
    --bg: #081722;
    --panel: #0d2230;
    --panel-2: #102a3a;
    --border: #234255;
    --text: #eef7fb;
    --muted: #91a8b7;
    --teal: #39c6b0;
    --blue: #4da9ff;
    --green: #32c48d;
    --amber: #f2b84b;
    --red: #ef6a78;
}

.stApp { background: var(--bg); color: var(--text); }
.main .block-container { max-width: 1320px; padding-top: 1.3rem; padding-bottom: 4rem; }
[data-testid="stSidebar"] { background: #06131d; border-right: 1px solid var(--border); }
[data-testid="stSidebar"] > div:first-child { padding-top: 1rem; }

h1,h2,h3,h4,h5 { color: var(--text) !important; }
p,li,label,.stCaption { color: var(--muted) !important; }

.brand {
    display:flex; align-items:center; gap:10px; margin-bottom:26px;
}
.brand-mark {
    width:34px; height:34px; border-radius:10px;
    background:linear-gradient(135deg,#39c6b0,#247bd0);
    display:flex; align-items:center; justify-content:center;
    color:#06131d; font-weight:900; font-size:18px;
}
.brand-name { font-size:19px; font-weight:800; color:#f2fbff; }
.brand-sub { font-size:10px; color:#6f8797; margin-top:-2px; }

.hero {
    background:linear-gradient(135deg,#0d3041 0%,#103b4c 50%,#0b2636 100%);
    border:1px solid #25566b; border-radius:18px; padding:30px 34px;
    margin-bottom:22px; box-shadow:0 12px 40px rgba(0,0,0,.16);
}
.hero-kicker { color:#55d6c0; font-size:11px; font-weight:800; letter-spacing:1.6px; text-transform:uppercase; }
.hero h1 { margin:7px 0 8px; font-size:34px; line-height:1.1; }
.hero p { margin:0; max-width:760px; font-size:14px; line-height:1.7; }

.section-title { margin:28px 0 12px; }
.section-title h2 { font-size:22px; margin:0; }
.section-title p { margin:3px 0 0; font-size:13px; }

.card {
    background:var(--panel); border:1px solid var(--border); border-radius:14px;
    padding:18px; min-height:108px;
}
.metric-card { background:var(--panel); border:1px solid var(--border); border-radius:14px; padding:17px; }
.metric-value { font-size:30px; font-weight:800; color:#4db8ff; line-height:1; }
.metric-label { color:#91a8b7; font-size:12px; margin-top:8px; }

.workflow { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin:10px 0 20px; }
.workflow-step { background:#0d2635; border:1px solid #274a5c; padding:9px 12px; border-radius:9px; color:#d9edf5; font-size:12px; }
.workflow-arrow { color:#4c7285; }

.finding {
    background:var(--panel); border:1px solid var(--border); border-radius:13px;
    padding:15px 17px; margin:8px 0;
}
.finding-id { color:#7895a5; font-size:10px; font-weight:800; letter-spacing:1px; }
.finding-title { color:#edf7fb; font-weight:700; margin:4px 0 8px; }
.badge { display:inline-block; padding:4px 9px; border-radius:999px; font-size:10px; font-weight:800; margin-right:5px; }
.badge-green { background:#123e35; color:#5de0b5; border:1px solid #216f5b; }
.badge-amber { background:#40321b; color:#f4c767; border:1px solid #80662a; }
.badge-red { background:#421f29; color:#ff8995; border:1px solid #7c3543; }

.source-box {
    background:#091b27; border:1px solid #27485a; border-left:4px solid #4da9ff;
    border-radius:10px; padding:14px 16px; margin:8px 0;
}
.source-label { color:#5bb7ff; font-size:10px; font-weight:800; letter-spacing:.8px; text-transform:uppercase; }
.source-text { color:#c8dbe4; font-size:13px; line-height:1.7; margin-top:6px; }

.chain { border-left:2px solid #2a5267; padding-left:16px; margin:10px 0 4px 7px; }
.chain-node { margin:0 0 15px; }
.chain-dot { color:#39c6b0; font-weight:900; }
.chain-label { color:#718b9a; font-size:10px; text-transform:uppercase; letter-spacing:.9px; font-weight:800; }
.chain-value { color:#e7f2f6; font-size:13px; margin-top:3px; }

.status-strip { padding:12px 14px; border-radius:10px; background:#0b1e2a; border:1px solid var(--border); }

div[data-testid="stButton"] > button {
    border-radius:9px; border:1px solid #2c5265; background:#102b3b; color:#e7f5fa;
    font-weight:650; min-height:40px;
}
div[data-testid="stButton"] > button:hover { border-color:#39c6b0; color:#ffffff; }

.stTextInput > div > div, .stTextArea > div > div, .stSelectbox > div > div {
    background:#0d2230 !important; border-color:#29495a !important; color:#edf7fb !important;
}
[data-testid="stFileUploader"] { background:#0d2230; border:1px dashed #315b6e; border-radius:12px; }
.stTabs [data-baseweb="tab"] { color:#8fa6b5; }
.stTabs [aria-selected="true"] { color:#39c6b0 !important; }

.sidebar-note { color:#6f8797; font-size:11px; line-height:1.55; }
.sidebar-active { background:#102d3a; border:1px solid #245263; border-radius:9px; padding:8px 10px; color:#dffaf6; }

[data-testid="stMetricValue"] { color:#4db8ff; }
#MainMenu, footer { visibility:hidden; }
</style>
""",
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Session state
# -----------------------------------------------------------------------------
def ss_init(key, value):
    if key not in st.session_state:
        st.session_state[key] = value


ss_init("account_token", st.query_params.get("acct", ""))
ss_init("reg_store", BalancedStore())
ss_init("client_store", BalancedStore())
ss_init("reg_registry", DocRegistry())
ss_init("client_registry", DocRegistry())
ss_init("reg_docs", [])
ss_init("client_docs", [])
ss_init("chat", [])
ss_init("structured_requirements", [])
ss_init("gap_results", [])
ss_init("assessment_name", "")
ss_init("assessment_id", "")
ss_init("test_results", None)
ss_init("page", "Dashboard")
ss_init("selected_finding", "")

account = get_account(st.session_state.account_token)


# -----------------------------------------------------------------------------
# Trial start
# -----------------------------------------------------------------------------
if account is None:
    st.markdown(
        """
        <div class="hero">
            <div class="hero-kicker">ClariX Intelligence</div>
            <h1>Evidence-led regulatory intelligence.</h1>
            <p>Turn regulations into traceable requirements, source evidence and clearer gap-analysis findings.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("### Welcome to ClariX")
    st.caption("Sign in to your account or create one. No email or Google account is required.")
    login_tab, create_tab = st.tabs(["Log in", "Create account"])

    with login_tab:
        with st.form("clarix_login_form"):
            login_username = st.text_input("Username", key="login_username")
            login_password = st.text_input("Password", type="password", key="login_password")
            remember_me = st.checkbox("Remember this browser", value=True, key="remember_login")
            login_submit = st.form_submit_button("Log in", type="primary", use_container_width=True)
        if login_submit:
            wait = login_lockout_seconds(login_username)
            token = None if wait else authenticate_user(login_username, login_password)
            if wait:
                st.error(f"Too many failed attempts. Please try again in about {max(1, -(-wait // 60))} minute(s).")
            elif token:
                st.session_state.account_token = token
                if remember_me:
                    st.query_params["acct"] = token
                else:
                    st.query_params.clear()
                st.rerun()
            else:
                st.error("Username or password is incorrect.")

    with create_tab:
        with st.form("clarix_create_account_form"):
            create_name = st.text_input("Your name", key="create_account_name")
            create_username = st.text_input("Choose a username", key="create_account_username", help="3–32 characters: letters, numbers, dots, underscores, or hyphens.")
            create_password = st.text_input("Create a password", type="password", key="create_account_password", help="Use at least 8 characters.")
            confirm_password = st.text_input("Confirm password", type="password", key="confirm_account_password")
            create_submit = st.form_submit_button("Create account", type="primary", use_container_width=True)
        if create_submit:
            if create_password != confirm_password:
                st.error("The passwords do not match.")
            else:
                try:
                    token = create_user(create_username, create_password, create_name)
                    st.session_state.account_token = token
                    st.query_params["acct"] = token
                    st.success("Account created. Welcome to ClariX!")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
                except Exception:
                    st.error("ClariX could not create your account right now. Please try again.")
    st.stop()


api_key = st.secrets.get("GEMINI_API_KEY", "")
reg_store = st.session_state.reg_store
client_store = st.session_state.client_store
reg_registry = st.session_state.reg_registry
client_registry = st.session_state.client_registry


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def badge(status: str) -> str:
    cls = {
        "Addressed": "badge-green",
        "Partially addressed": "badge-amber",
        "Potential gap": "badge-red",
        "Insufficient evidence": "badge-amber",
        "Assessment failed": "badge-red",
    }.get(status, "badge-amber")
    return f'<span class="badge {cls}">{html.escape(status)}</span>'


def metric_card(value, label):
    return f'<div class="metric-card"><div class="metric-value">{html.escape(str(value))}</div><div class="metric-label">{html.escape(label)}</div></div>'


def process_uploads(files, store, registry, tracked, kind_label):
    if not files:
        return tracked
    new_names = [f.name for f in files if f.name not in tracked]
    if not new_names:
        return tracked
    with st.spinner(f"Processing {kind_label.lower()}..."):
        for file in files:
            if file.name in tracked:
                continue
            raw = file.read()
            chunks, _ = process_pdf(raw, file.name, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
            store.add_chunks(chunks)
            registry.add(file.name, raw)
            tracked.append(file.name)
    return tracked


def clear_all():
    reg_store.clear(); client_store.clear()
    reg_registry.clear(); client_registry.clear()
    st.session_state.reg_docs = []
    st.session_state.client_docs = []
    st.session_state.chat = []
    st.session_state.structured_requirements = []
    st.session_state.gap_results = []
    st.session_state.assessment_name = ""
    st.session_state.assessment_id = ""


def gap_counts(results):
    counts = {
        "Addressed": 0,
        "Partially addressed": 0,
        "Potential gap": 0,
        "Insufficient evidence": 0,
        "Assessment failed": 0,
    }
    for item in results:
        status = item.get("assessment", {}).get("status", "Insufficient evidence")
        if status not in counts:
            status = "Insufficient evidence"
        counts[status] += 1
    return counts


def evidence_chain(item):
    req = item
    assessment = item.get("assessment", {})
    source = req.get("source", {})
    st.markdown('<div class="chain">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="chain-node"><div class="chain-label"><span class="chain-dot">●</span> Regulatory requirement</div>'
        f'<div class="chain-value">{html.escape(req.get("requirement", ""))}</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="chain-node"><div class="chain-label"><span class="chain-dot">●</span> Regulatory source</div>'
        f'<div class="chain-value">{html.escape(source.get("filename", "Unknown"))} · {html.escape(str(source.get("reference") or "Reference not identified"))} · page {html.escape(str(source.get("page") or "unknown"))}</div></div>',
        unsafe_allow_html=True,
    )
    evs = assessment.get("evidence", [])
    if evs:
        for ev in evs:
            st.markdown(
                f'<div class="chain-node"><div class="chain-label"><span class="chain-dot">●</span> Client evidence</div>'
                f'<div class="chain-value">{html.escape(ev.get("filename", "Unknown"))} · {html.escape(str(ev.get("reference") or "Reference not identified"))} · page {html.escape(str(ev.get("page") or "unknown"))}</div></div>',
                unsafe_allow_html=True,
            )
            if ev.get("quote"):
                st.markdown(f'<div class="source-box"><div class="source-label">Evidence excerpt</div><div class="source-text">{html.escape(ev["quote"])}</div></div>', unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="chain-node"><div class="chain-label"><span class="chain-dot">●</span> Client evidence</div>'
            '<div class="chain-value">No matching evidence was identified in the selected documents.</div></div>',
            unsafe_allow_html=True,
        )
    st.markdown(
        f'<div class="chain-node"><div class="chain-label"><span class="chain-dot">●</span> Assessment</div>'
        f'<div class="chain-value">{html.escape(assessment.get("assessment", ""))}</div></div></div>',
        unsafe_allow_html=True,
    )


def render_finding(item, idx):
    assessment = item.get("assessment", {})
    status = assessment.get("status", "Potential gap")
    st.markdown(f'<div class="finding"><div class="finding-id">FINDING · {html.escape(item.get("id", f"REQ-{idx+1:03d}"))}</div><div class="finding-title">{html.escape(item.get("requirement", "Requirement"))}</div>{badge(status)}</div>', unsafe_allow_html=True)
    st.markdown("#### Requirement")
    st.write(item.get("requirement", ""))
    interpretation = item.get("interpretation", {})
    if interpretation:
        with st.expander("Regulatory understanding", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Applicability**\n\n{interpretation.get('applicability') or 'Not identified'}")
                st.markdown(f"**Operative obligation**\n\n{interpretation.get('operative_obligation') or item.get('requirement','')}")
                st.markdown(f"**Qualifiers**\n\n{', '.join(interpretation.get('qualifiers', [])) or 'None identified'}")
            with c2:
                st.markdown(f"**Exceptions**\n\n{', '.join(interpretation.get('exceptions', [])) or 'None identified'}")
                st.markdown(f"**Dependencies**\n\n{', '.join(interpretation.get('dependencies', [])) or 'None identified'}")
                st.markdown(f"**Confidence**\n\n{interpretation.get('confidence','Medium')}")
            if interpretation.get("interpretation_notes"):
                st.info(interpretation["interpretation_notes"])
            elements = interpretation.get("obligation_elements", [])
            if elements:
                st.markdown("**Obligation checklist**")
                st.caption("Each item is a separate testable element. Reviewer confirmation is still required.")
                for element in elements:
                    st.markdown(f"- **{html.escape(element.get('element_type', 'Duty'))}:** {html.escape(element.get('element', ''))}")
                    if element.get("evidence_test"):
                        st.caption("Evidence test: " + element["evidence_test"])
            questions = interpretation.get("verification_questions", [])
            if questions:
                st.markdown("**Verify before concluding**")
                for question in questions:
                    st.markdown(f"- {html.escape(question)}")
        unresolved = item.get("unresolved_references", [])
        if unresolved:
            st.warning("Unresolved regulatory references: " + ", ".join(unresolved) + ". Verify these provisions before relying on the finding.")
    source = item.get("source", {})
    st.markdown("#### Regulatory source")
    st.markdown(
        f'<div class="source-box"><div class="source-label">Source</div><div class="source-text">{html.escape(source.get("filename", "Unknown"))} · {html.escape(str(source.get("reference") or "Reference not identified"))} · page {html.escape(str(source.get("page") or "unknown"))}</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown("#### Evidence chain")
    evidence_chain(item)
    checks = assessment.get("element_checks", [])
    if checks:
        st.markdown("#### Element-by-element evidence check")
        for check in checks:
            label = f"**{html.escape(check.get('status', 'Unclear'))}** — {html.escape(check.get('element', ''))}"
            st.markdown(label)
            if check.get("evidence_quote"):
                st.markdown(f"> {html.escape(check['evidence_quote'])}")
                src = check.get("source", {})
                if src:
                    st.caption(" · ".join(str(src.get(k)) for k in ("filename", "reference", "page") if src.get(k)))
            if check.get("note"):
                st.caption(check["note"])
    if assessment.get("missing_elements"):
        st.markdown("#### Elements not demonstrated")
        for x in assessment["missing_elements"]:
            st.markdown(f"- {x}")
    for question in assessment.get("verification_questions", []):
        st.warning("Verification needed: " + question)
    st.caption("Evidence-based indication · Consultant review required")


def build_gap_report(results, assessment_name, assessment_id):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib import colors

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8.5, leading=12))
    styles.add(ParagraphStyle(name="Title2", parent=styles["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#16485a")))
    story = [Paragraph("ClariX Intelligence", styles["Title2"]), Paragraph("Evidence-Led Regulatory Gap Analysis", styles["Heading2"]), Spacer(1, 8)]
    story.append(Paragraph(f"Prepared for consultant review · {datetime.now().strftime('%d %b %Y')}", styles["Small"]))
    story.append(Paragraph(f"Assessment: {html.escape(assessment_name or 'Regulatory assessment')}", styles["BodyText"]))
    story.append(Paragraph(f"Reference: {html.escape(assessment_id or 'CLX-DEMO')}", styles["BodyText"]))
    counts = gap_counts(results)
    story.append(Spacer(1, 14))
    summary_headers = ["Reviewed", "Addressed", "Partial", "Potential gaps", "Insufficient evidence", "Assessment failed"]
    summary_values = [str(len(results)), str(counts["Addressed"]), str(counts["Partially addressed"]), str(counts["Potential gap"]), str(counts["Insufficient evidence"]), str(counts["Assessment failed"])]
    story.append(Table([summary_headers, summary_values], colWidths=[55,62,55,65,100,75], repeatRows=1, style=TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#16485a')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#b8c9d0')),('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTSIZE',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)])))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Coverage limitation: this report evaluates only the requirements extracted for this run. It must not be interpreted as confirmation that every applicable requirement in the full standard was reviewed.", styles["Small"]))
    story.append(Spacer(1, 12))
    for item in results:
        a = item.get("assessment", {})
        src = item.get("source", {})
        story.append(Paragraph(f"{item.get('id')} · {a.get('status')}", styles["Heading3"]))
        story.append(Paragraph(html.escape(item.get("requirement", "")), styles["BodyText"]))
        story.append(Paragraph(f"Source: {html.escape(src.get('filename','Unknown'))} · {html.escape(str(src.get('reference') or 'not identified'))} · page {html.escape(str(src.get('page') or 'unknown'))}", styles["Small"]))
        interp = item.get("interpretation", {})
        if interp:
            story.append(Paragraph(f"Applicability: {html.escape(interp.get('applicability','') or 'Not identified')}", styles["Small"]))
            story.append(Paragraph(f"Operative obligation: {html.escape(interp.get('operative_obligation','') or item.get('requirement',''))}", styles["Small"]))
            if interp.get('interpretation_notes'):
                story.append(Paragraph(f"Regulatory interpretation: {html.escape(interp.get('interpretation_notes',''))}", styles["Small"]))
        story.append(Paragraph(f"Assessment: {html.escape(a.get('assessment',''))}", styles["Small"]))
        for ev in a.get("evidence", []):
            story.append(Paragraph(f"Evidence: {html.escape(ev.get('filename','Unknown'))} · {html.escape(str(ev.get('reference') or 'not identified'))} · page {html.escape(str(ev.get('page') or 'unknown'))} · {html.escape(ev.get('quote',''))}", styles["Small"]))
        story.append(Spacer(1, 10))
    doc.build(story)
    return buf.getvalue()


# -----------------------------------------------------------------------------
# Sidebar navigation and document management
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        '<div class="brand"><div class="brand-mark">◈</div><div><div class="brand-name">ClariX</div><div class="brand-sub">REGULATORY INTELLIGENCE</div></div></div>',
        unsafe_allow_html=True,
    )

    pages = ["Dashboard", "Regulatory Research", "Gap Analysis", "Documents", "Reports", "Accuracy Test", "Admin"]
    page = st.radio("Navigation", pages, index=pages.index(st.session_state.page), label_visibility="collapsed")
    st.session_state.page = page

    st.markdown("---")
    st.markdown("**Regulatory framework**")
    reg_files = st.file_uploader("Upload regulation PDFs", type=["pdf"], accept_multiple_files=True, label_visibility="collapsed", key="reg_upload_sidebar")
    if reg_files:
        st.session_state.reg_docs = process_uploads(reg_files, reg_store, reg_registry, st.session_state.reg_docs, "regulatory documents")

    st.markdown("**Client evidence**")
    client_files = st.file_uploader("Upload client evidence PDFs", type=["pdf"], accept_multiple_files=True, label_visibility="collapsed", key="client_upload_sidebar")
    if client_files:
        st.session_state.client_docs = process_uploads(client_files, client_store, client_registry, st.session_state.client_docs, "client documents")

    st.markdown("---")
    st.markdown(f'<div class="sidebar-note"><b>{html.escape(account["account_name"])}</b><br>{len(st.session_state.reg_docs)} regulatory · {len(st.session_state.client_docs)} client documents<br>{reg_store.doc_count + client_store.doc_count} indexed chunks</div>', unsafe_allow_html=True)
    if st.button("Clear workspace"):
        clear_all(); st.rerun()
    if st.button("Log out", key="logout_button"):
        clear_all()   # never leave one user's documents, chat or findings in the session for the next login
        st.session_state.test_results = None
        st.session_state.selected_finding = ""
        st.session_state.page = "Dashboard"
        st.session_state.account_token = ""
        st.query_params.clear()
        st.rerun()


# -----------------------------------------------------------------------------
# Global header
# -----------------------------------------------------------------------------
st.markdown(
    """
    <div class="hero">
        <div class="hero-kicker">Evidence-led regulatory intelligence</div>
        <h1>FROM REGULATION TO A CLEAR ASSESSMENT</h1>
        <p>Every requirement. Every source. Every relevant piece of evidence. ClariX helps consultants move from regulatory text to a traceable research and gap-analysis workflow.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Dashboard
# -----------------------------------------------------------------------------
if page == "Dashboard":
    st.markdown('<div class="section-title"><h2>Workspace overview</h2><p>Your current regulatory research and evidence-led assessment workspace.</p></div>', unsafe_allow_html=True)
    counts = gap_counts(st.session_state.gap_results)
    c1,c2,c3,c4 = st.columns(4)
    c1.markdown(metric_card(1 if st.session_state.gap_results else 0, "Active assessments"), unsafe_allow_html=True)
    c2.markdown(metric_card(len(st.session_state.reg_docs) + len(st.session_state.client_docs), "Documents"), unsafe_allow_html=True)
    c3.markdown(metric_card(counts["Potential gap"], "Potential gaps"), unsafe_allow_html=True)
    c4.markdown(metric_card(len(st.session_state.structured_requirements), "Requirements identified"), unsafe_allow_html=True)

    st.markdown('<div class="section-title"><h2>Assessment workflow</h2></div>', unsafe_allow_html=True)
    st.markdown('<div class="workflow"><span class="workflow-step">Regulation</span><span class="workflow-arrow">→</span><span class="workflow-step">Requirement</span><span class="workflow-arrow">→</span><span class="workflow-step">Source</span><span class="workflow-arrow">→</span><span class="workflow-step">Client evidence</span><span class="workflow-arrow">→</span><span class="workflow-step">Gap assessment</span></div>', unsafe_allow_html=True)

    left, right = st.columns([1.35, 1])
    with left:
        st.markdown('<div class="section-title"><h2>Current assessment</h2></div>', unsafe_allow_html=True)
        if st.session_state.gap_results:
            name = st.session_state.assessment_name or "Current assessment"
            st.markdown(f'<div class="card"><b>{html.escape(name)}</b><br><span style="color:#7895a5;font-size:12px">{html.escape(st.session_state.assessment_id or "CLX-2026-001")} · {len(st.session_state.gap_results)} requirements reviewed</span></div>', unsafe_allow_html=True)
            cc = gap_counts(st.session_state.gap_results)
            a,b,c = st.columns(3)
            a.markdown(metric_card(cc["Addressed"], "Addressed"), unsafe_allow_html=True)
            b.markdown(metric_card(cc["Partially addressed"], "Partially addressed"), unsafe_allow_html=True)
            c.markdown(metric_card(cc["Potential gap"], "Potential gaps"), unsafe_allow_html=True)
        else:
            st.info("No assessment yet. Upload a regulatory framework and client evidence, then open Gap Analysis.")
            if st.button("Start a new gap analysis", type="primary"):
                st.session_state.page = "Gap Analysis"; st.rerun()
    with right:
        st.markdown('<div class="section-title"><h2>Documents</h2></div>', unsafe_allow_html=True)
        if st.session_state.reg_docs or st.session_state.client_docs:
            for name in st.session_state.reg_docs:
                st.markdown(f'<div class="finding"><b>REGULATION</b><br>{html.escape(name)}</div>', unsafe_allow_html=True)
            for name in st.session_state.client_docs:
                st.markdown(f'<div class="finding"><b>CLIENT EVIDENCE</b><br>{html.escape(name)}</div>', unsafe_allow_html=True)
        else:
            st.caption("No documents uploaded yet.")


# -----------------------------------------------------------------------------
# Regulatory Research
# -----------------------------------------------------------------------------
elif page == "Regulatory Research":
    st.markdown('<div class="section-title"><h2>Regulatory Research</h2><p>Ask questions against your uploaded regulatory corpus, then structure the relevant requirements.</p></div>', unsafe_allow_html=True)
    render_trial_status(st, st.session_state.account_token)

    if not st.session_state.reg_docs:
        st.info("Upload one or more regulatory PDFs using the sidebar to begin.")
    else:
        q = st.text_input("Research question", placeholder="e.g. What are the climate transition-plan requirements?", key="research_question")
        if st.button("Run regulatory research", type="primary") and q.strip():
            if trial_exceeded(st.session_state.account_token):
                render_trial_blocked(st, st.session_state.account_token)
            elif not api_key:
                st.error("System configuration issue — please contact support.")
            else:
                with st.spinner("Retrieving relevant provisions and preparing a cited answer..."):
                    chunks = reg_store.retrieve(q, top_k=TOP_K)
                    chunks = reg_registry.add_identity_context(q, chunks)
                    response = query_compliance(q, chunks, api_key=api_key, chat_history=st.session_state.chat)
                st.session_state.chat.append({"role":"user","content":q})
                st.session_state.chat.append({"role":"assistant","content":response["answer"],"answer_only":response["answer"],"reasoning":response.get("reasoning",""),"citations":response["sources_used"],"excerpts":make_excerpt_records(chunks)})
                increment_usage(st.session_state.account_token)
                st.rerun()

        if st.session_state.chat:
            last_answer = st.session_state.chat[-1]
            if last_answer.get("role") == "assistant":
                st.markdown('<div class="section-title"><h3>Latest answer</h3></div>', unsafe_allow_html=True)
                st.markdown(f'<div class="answer-box">{last_answer.get("content","")}</div>', unsafe_allow_html=True)
                render_excerpts(st, last_answer.get("excerpts", []))
            export_buttons(st, st.session_state.chat, reg_registry)

        st.markdown("---")
        st.markdown("### Structure regulatory requirements")
        rq = st.text_input("Regulatory area", placeholder="e.g. climate transition plans, Scope 3 disclosures", key="structure_question")
        if st.button("Extract structured requirements", key="structure_btn") and rq.strip():
            if not api_key:
                st.error("System configuration issue — please contact support.")
            else:
                with st.spinner("Structuring requirements from the retrieved provisions..."):
                    chunks = reg_store.retrieve(rq, top_k=TOP_K)
                    chunks = reg_registry.add_identity_context(rq, chunks)
                    st.session_state.structured_requirements = prepare_requirements(chunks, api_key=api_key, max_requirements=10, corpus_chunks=reg_store.chunks)

        reqs = st.session_state.structured_requirements
        if reqs:
            st.success(f"{len(reqs)} structured requirement(s) identified.")
            for req in reqs:
                with st.expander(f'{req["id"]} · {req["requirement"]}'):
                    a,b = st.columns(2)
                    with a:
                        st.markdown(f'**Subject**\n\n{req.get("subject") or "Not identified"}')
                        st.markdown(f'**Action**\n\n{req.get("action") or "Not identified"}')
                        st.markdown(f'**Object**\n\n{req.get("object") or "Not identified"}')
                    with b:
                        st.markdown(f'**Scope**\n\n{req.get("scope") or "Not identified"}')
                        st.markdown(f'**Conditions**\n\n{", ".join(req.get("conditions", [])) or "None identified"}')
                        st.markdown(f'**Exceptions**\n\n{", ".join(req.get("exceptions", [])) or "None identified"}')
                    src=req.get("source",{})
                    st.caption(f'Source: {src.get("filename","Unknown")} · {src.get("reference") or "reference not identified"} · page {src.get("page") or "unknown"}')
                    interpretation=req.get("interpretation", {})
                    if interpretation:
                        st.markdown("**Regulatory understanding**")
                        st.markdown(f"**Applicability:** {interpretation.get('applicability') or 'Not identified'}")
                        st.markdown(f"**Operative obligation:** {interpretation.get('operative_obligation') or req.get('requirement','')}")
                        if interpretation.get("qualifiers"):
                            st.markdown(f"**Qualifiers:** {', '.join(interpretation['qualifiers'])}")
                        if interpretation.get("dependencies"):
                            st.markdown(f"**Dependencies:** {', '.join(interpretation['dependencies'])}")
                        if interpretation.get("interpretation_notes"):
                            st.caption(interpretation["interpretation_notes"])
                    if req.get("unresolved_references"):
                        st.warning("Unresolved references: " + ", ".join(req["unresolved_references"]))


# -----------------------------------------------------------------------------
# Gap Analysis
# -----------------------------------------------------------------------------
elif page == "Gap Analysis":
    st.markdown('<div class="section-title"><h2>New Gap Analysis</h2><p>Compare regulatory requirements against client evidence and surface traceable potential gaps.</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="workflow"><span class="workflow-step">1 · Regulation</span><span class="workflow-arrow">→</span><span class="workflow-step">2 · Requirements</span><span class="workflow-arrow">→</span><span class="workflow-step">3 · Evidence</span><span class="workflow-arrow">→</span><span class="workflow-step">4 · Assessment</span></div>', unsafe_allow_html=True)

    assessment_name = st.text_input("Assessment name", value=st.session_state.assessment_name, placeholder="e.g. Unilever — ESRS E1 Gap Analysis", key="assessment_name_input")
    if assessment_name != st.session_state.assessment_name:
        st.session_state.assessment_name = assessment_name

    if not st.session_state.reg_docs:
        st.warning("Upload the regulatory framework in the sidebar first.")
    if not st.session_state.client_docs:
        st.info("Upload the client's supporting documents in the sidebar. These are kept separate from the regulatory corpus.")

    if st.session_state.reg_docs and st.session_state.client_docs:
        st.info("Coverage note: the current workflow extracts a limited set of requirements for each run. This is a focused assessment sample, not a completeness-certified review of the entire standard.")
        if st.button("Run Gap Analysis", type="primary"):
            if not api_key:
                st.error("System configuration issue — please contact support.")
            else:
                with st.spinner("Reading requirements → searching client evidence → assessing findings..."):
                    # Use several complementary queries, deduplicate by stable chunk identity,
                    # and keep the result explicitly described as a sample rather than a complete
                    # inventory of every obligation in the uploaded standard.
                    assessment_query = st.session_state.assessment_name.strip()
                    base_queries = [
                        assessment_query or "regulatory disclosure requirements",
                        "applicability scope thresholds exceptions conditions disclosure requirements",
                        "policies actions targets metrics transition plans obligations",
                        "definitions cross references reporting requirements disclosure requirements",
                    ]
                    selected_chunks = []
                    seen_chunk_keys = set()
                    per_query = max(6, min(10, TOP_K))
                    for query in base_queries:
                        matches = reg_store.retrieve(query, top_k=per_query)
                        for chunk in matches:
                            key = (chunk.get("source"), chunk.get("id") or chunk.get("index"), chunk.get("text", "")[:100])
                            if key not in seen_chunk_keys:
                                seen_chunk_keys.add(key)
                                selected_chunks.append(chunk)
                    req_chunks = reg_registry.add_identity_context(assessment_query or base_queries[1], selected_chunks)
                    reqs = prepare_requirements(req_chunks, api_key=api_key, max_requirements=10, corpus_chunks=reg_store.chunks)
                    if not reqs:
                        st.error("ClariX could not identify structured requirements from the selected regulatory documents.")
                    else:
                        results = run_gap_analysis(reqs, client_store, api_key=api_key, evidence_top_k=4)
                        st.session_state.structured_requirements = reqs
                        st.session_state.gap_results = results
                        st.session_state.assessment_id = f"CLX-{datetime.now().strftime('%Y%m%d-%H%M')}"
                        st.session_state.selected_finding = results[0]["id"] if results else ""
                        st.rerun()

    if st.session_state.gap_results:
        results = st.session_state.gap_results
        counts = gap_counts(results)
        st.markdown('<div class="section-title"><h2>Assessment summary</h2><p>Evidence-based indication only. Consultant review remains required.</p></div>', unsafe_allow_html=True)
        a,b,c,d,e,f = st.columns(6)
        a.markdown(metric_card(len(results), "Reviewed"), unsafe_allow_html=True)
        b.markdown(metric_card(counts["Addressed"], "Addressed"), unsafe_allow_html=True)
        c.markdown(metric_card(counts["Partially addressed"], "Partial"), unsafe_allow_html=True)
        d.markdown(metric_card(counts["Potential gap"], "Potential gaps"), unsafe_allow_html=True)
        e.markdown(metric_card(counts["Insufficient evidence"], "Insufficient evidence"), unsafe_allow_html=True)
        f.markdown(metric_card(counts["Assessment failed"], "Assessment failed"), unsafe_allow_html=True)

        st.markdown("### Findings")
        for idx, item in enumerate(results):
            a=item.get("assessment",{}); status=a.get("status","Potential gap")
            st.markdown(f'<div class="finding"><div class="finding-id">{html.escape(item.get("id",""))}</div><div class="finding-title">{html.escape(item.get("requirement",""))}</div>{badge(status)} <span style="color:#7895a5;font-size:11px">{html.escape(a.get("assessment",""))}</span></div>', unsafe_allow_html=True)
            if st.button(f'Open finding · {item.get("id")}', key=f'open_{item.get("id")}_{idx}'):
                st.session_state.selected_finding = item.get("id","")

        selected = next((x for x in results if x.get("id") == st.session_state.selected_finding), results[0])
        st.markdown("---")
        st.markdown("### Finding detail")
        render_finding(selected, results.index(selected))

        st.download_button("Export assessment report (PDF)", build_gap_report(results, st.session_state.assessment_name, st.session_state.assessment_id), file_name=f"{st.session_state.assessment_id or 'clarix-assessment'}.pdf", mime="application/pdf")


# -----------------------------------------------------------------------------
# Documents
# -----------------------------------------------------------------------------
elif page == "Documents":
    st.markdown('<div class="section-title"><h2>Documents</h2><p>Regulatory sources and client evidence are indexed separately.</p></div>', unsafe_allow_html=True)
    a,b = st.columns(2)
    with a:
        st.markdown("### Regulatory framework")
        if st.session_state.reg_docs:
            for name in st.session_state.reg_docs:
                info=reg_registry.docs.get(name,{})
                st.markdown(f'<div class="finding"><b>{html.escape(name)}</b><br><span style="color:#7895a5;font-size:11px">{info.get("pages") or "?"} pages · indexed into {sum(1 for c in reg_store.chunks if c.get("source")==name)} chunks</span></div>', unsafe_allow_html=True)
        else: st.caption("No regulatory documents uploaded.")
    with b:
        st.markdown("### Client evidence")
        if st.session_state.client_docs:
            for name in st.session_state.client_docs:
                info=client_registry.docs.get(name,{})
                st.markdown(f'<div class="finding"><b>{html.escape(name)}</b><br><span style="color:#7895a5;font-size:11px">{info.get("pages") or "?"} pages · indexed into {sum(1 for c in client_store.chunks if c.get("source")==name)} chunks</span></div>', unsafe_allow_html=True)
        else: st.caption("No client evidence uploaded.")


# -----------------------------------------------------------------------------
# Reports
# -----------------------------------------------------------------------------
elif page == "Reports":
    st.markdown('<div class="section-title"><h2>Reports</h2><p>Export the evidence chain and assessment findings for consultant review.</p></div>', unsafe_allow_html=True)
    if not st.session_state.gap_results:
        st.info("Run a gap analysis first. Your report will appear here.")
    else:
        results=st.session_state.gap_results
        counts=gap_counts(results)
        st.markdown('<div class="hero"><div class="hero-kicker">Evidence-led compliance review</div><h1>Regulatory Gap Analysis</h1><p>Prepared for consultant review · Assessment report</p></div>', unsafe_allow_html=True)
        a,b,c,d,e,f=st.columns(6)
        a.markdown(metric_card(len(results),"Reviewed"),unsafe_allow_html=True)
        b.markdown(metric_card(counts["Addressed"],"Addressed"),unsafe_allow_html=True)
        c.markdown(metric_card(counts["Partially addressed"],"Partial"),unsafe_allow_html=True)
        d.markdown(metric_card(counts["Potential gap"],"Potential gaps"),unsafe_allow_html=True)
        e.markdown(metric_card(counts["Insufficient evidence"],"Insufficient evidence"),unsafe_allow_html=True)
        f.markdown(metric_card(counts["Assessment failed"],"Assessment failed"),unsafe_allow_html=True)
        st.markdown("### Executive summary")
        st.write(f"ClariX reviewed {len(results)} structured regulatory requirements against the selected client evidence. {counts['Potential gap']} potential gaps and {counts['Partially addressed']} partially addressed requirements were identified for consultant review.")
        st.markdown("### Findings")
        for item in results:
            st.markdown(f"**{item.get('id')} · {item.get('assessment',{}).get('status')}** — {item.get('requirement')}")
        st.download_button("Download PDF report", build_gap_report(results, st.session_state.assessment_name, st.session_state.assessment_id), file_name=f"{st.session_state.assessment_id or 'clarix-report'}.pdf", mime="application/pdf")


# -----------------------------------------------------------------------------
# Accuracy test
# -----------------------------------------------------------------------------
elif page == "Accuracy Test":
    st.markdown('<div class="section-title"><h2>System Accuracy Evaluation</h2><p>Internal benchmark for retrieval and citation behaviour. This is a testing tool, not a customer-facing accuracy guarantee.</p></div>', unsafe_allow_html=True)
    if not st.session_state.reg_docs:
        st.info("Upload regulatory documents first.")
    elif not api_key:
        st.warning("System configuration issue — please contact support.")
    else:
        if st.button("Run accuracy test"):
            from tests.accuracy_test import run_accuracy_test
            with st.spinner("Running the benchmark questions..."):
                st.session_state.test_results = run_accuracy_test(reg_store, api_key, top_k=TOP_K, registry=reg_registry)
        r=st.session_state.test_results
        if r:
            a,b,c=st.columns(3)
            a.markdown(metric_card(f"{r['accuracy_pct']}%","Overall benchmark score"),unsafe_allow_html=True)
            b.markdown(metric_card(f"{r['passed']}/{r['total']}","Tests passed"),unsafe_allow_html=True)
            cited=sum(1 for x in r["results"] if x["cited"])
            c.markdown(metric_card(f"{cited}/{r['total']}","Cited answers"),unsafe_allow_html=True)
            for x in r["results"]:
                with st.expander(f"{x['status']} · {x['question']}"):
                    st.write(x["answer"])
                    st.caption(f"Retrieved chunks: {x['n_chunks']} · Cited: {'yes' if x['cited'] else 'no'}")


# -----------------------------------------------------------------------------
# Admin — manual subscription activation and expiry management
# -----------------------------------------------------------------------------
elif page == "Admin":
    render_admin_panel()


# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.markdown("---")
st.caption("ClariX Intelligence · Evidence-based indication · Consultant review required")
