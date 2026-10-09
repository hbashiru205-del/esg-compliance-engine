"""Persistent accounts with manual subscription expiry."""
import re, secrets, sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).parent / "clarix_accounts.db"
_NAME_RE = re.compile(r"^[A-Za-z0-9 ,.\-']{1,60}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("""CREATE TABLE IF NOT EXISTS accounts (
        token TEXT PRIMARY KEY, account_name TEXT NOT NULL,
        questions_used INTEGER NOT NULL DEFAULT 0,
        unlocked INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        paid_through TEXT, suspended INTEGER NOT NULL DEFAULT 0,
        activated_at TEXT)""")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(accounts)")}
    migrations = {
        "unlocked":"INTEGER NOT NULL DEFAULT 0",
        "created_at":"TEXT NOT NULL DEFAULT (datetime('now'))",
        "paid_through":"TEXT", "suspended":"INTEGER NOT NULL DEFAULT 0",
        "activated_at":"TEXT"}
    for col, definition in migrations.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE accounts ADD COLUMN {col} {definition}")
    conn.commit()
    return conn

def valid_name(name):
    return bool(name) and bool(_NAME_RE.fullmatch(name.strip()))

def create_account(account_name):
    token = secrets.token_urlsafe(24)
    conn = _connect()
    try:
        conn.execute("INSERT INTO accounts (token, account_name) VALUES (?, ?)",
                     (token, account_name.strip()))
        conn.commit()
    finally: conn.close()
    return token

def _active(row):
    if not row or not row["unlocked"] or row["suspended"] or not row["paid_through"]:
        return False
    try: return date.fromisoformat(row["paid_through"]) >= date.today()
    except (TypeError, ValueError): return False

def get_account(token):
    if not token: return None
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM accounts WHERE token=?", (token,)).fetchone()
    finally: conn.close()
    if row is None: return None
    d = dict(row)
    d["unlocked"] = bool(d["unlocked"])
    d["suspended"] = bool(d["suspended"])
    d["subscription_active"] = _active(row)
    d["expired"] = bool(d["unlocked"] and d["paid_through"] and not d["suspended"] and not d["subscription_active"])
    return d

def increment_usage(token):
    conn = _connect()
    try:
        conn.execute("UPDATE accounts SET questions_used=questions_used+1 WHERE token=?", (token,))
        conn.commit()
    finally: conn.close()

def set_subscription(token, paid_through):
    if not _DATE_RE.fullmatch(paid_through): raise ValueError("Date must be YYYY-MM-DD.")
    date.fromisoformat(paid_through)
    conn = _connect()
    try:
        cur = conn.execute("""UPDATE accounts SET unlocked=1, paid_through=?,
            suspended=0, activated_at=datetime('now') WHERE token=?""", (paid_through, token))
        conn.commit()
        if not cur.rowcount: raise ValueError("Account token was not found.")
    finally: conn.close()

def unlock_account(token, paid_through=None):
    if not paid_through:
        raise ValueError("A paid-through date is required.")
    set_subscription(token, paid_through)

def suspend_account(token, suspended=True):
    conn = _connect()
    try:
        cur = conn.execute("UPDATE accounts SET suspended=? WHERE token=?", (int(suspended), token))
        conn.commit()
        if not cur.rowcount: raise ValueError("Account token was not found.")
    finally: conn.close()

def is_unlocked(token):
    a = get_account(token)
    return bool(a and a["subscription_active"])

def trial_exceeded(token, limit=5):
    a = get_account(token)
    if not a or a["subscription_active"]:
        return False
    # Once a paid account expires or is suspended, do not fall back to leftover trial questions.
    if a["unlocked"]:
        return True
    return a["questions_used"] >= limit

def list_accounts():
    conn = _connect()
    try: rows = conn.execute("SELECT * FROM accounts ORDER BY created_at DESC").fetchall()
    finally: conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["unlocked"] = bool(d["unlocked"]); d["suspended"] = bool(d["suspended"])
        d["subscription_active"] = _active(row)
        d["expired"] = bool(d["unlocked"] and d["paid_through"] and not d["suspended"] and not d["subscription_active"])
        result.append(d)
    return result
