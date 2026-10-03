"""Lightweight persistent accounts: a name, a question count, and
whether a paid access code has been entered -- nothing else. No
password, no email, no document content stored.

Storage is a SQLite file on the server's own disk. On Streamlit
Community Cloud this disk is wiped on every redeploy, so this survives
normal use between deploys but not a code push -- a real limitation,
not an oversight; a durable database would need a real hosted DB and
its own cost, a separate decision from this one.

The persistent link between a browser and its account is the token in
the page's own URL (st.query_params), since that is the one thing in
plain Streamlit that survives an ordinary page refresh. Losing that
specific URL (a different device, a cleared/rewritten link, a fresh
tab typed from scratch) means a fresh account, same as before -- an
honest, disclosed gap, not a claim of airtight enforcement.
"""
import re
import secrets
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "clarix_accounts.db"
_NAME_RE = re.compile(r"^[A-Za-z0-9 ,.\-']{1,60}$")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            token TEXT PRIMARY KEY,
            account_name TEXT NOT NULL,
            questions_used INTEGER NOT NULL DEFAULT 0,
            unlocked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)")]
    if "unlocked" not in cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN unlocked INTEGER NOT NULL DEFAULT 0")
    return conn


def valid_name(name: str) -> bool:
    return bool(name) and bool(_NAME_RE.match(name.strip()))


def create_account(account_name: str) -> str:
    token = secrets.token_urlsafe(16)
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO accounts (token, account_name) VALUES (?, ?)",
            (token, account_name.strip()),
        )
        conn.commit()
    finally:
        conn.close()
    return token


def get_account(token: str):
    if not token:
        return None
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT account_name, questions_used, unlocked FROM accounts WHERE token = ?",
            (token,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"account_name": row[0], "questions_used": row[1], "unlocked": bool(row[2])}


def increment_usage(token: str):
    conn = _connect()
    try:
        conn.execute(
            "UPDATE accounts SET questions_used = questions_used + 1 WHERE token = ?",
            (token,),
        )
        conn.commit()
    finally:
        conn.close()


def unlock_account(token: str):
    conn = _connect()
    try:
        conn.execute("UPDATE accounts SET unlocked = 1 WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


def is_unlocked(token: str) -> bool:
    account = get_account(token)
    return bool(account and account["unlocked"])


def trial_exceeded(token: str, limit: int = 5) -> bool:
    account = get_account(token)
    if account is None:
        return False
    if account["unlocked"]:
        return False
    return account["questions_used"] >= limit
