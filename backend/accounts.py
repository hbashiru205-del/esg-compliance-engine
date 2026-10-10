"""ClariX username/password accounts with optional durable PostgreSQL storage.

Set DATABASE_URL to a managed PostgreSQL connection string in deployment secrets.
Without it, local SQLite is used for development only and may be lost on redeploy.
Passwords are PBKDF2-HMAC-SHA256 hashes with per-user salts; plaintext is never stored.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).with_name("clarix_accounts.db")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
_NAME_RE = re.compile(r"^[A-Za-z0-9 ,.'-]{1,60}$")
_HASH_ROUNDS = 600_000
MAX_FAILED_LOGINS = 5          # consecutive wrong passwords before a temporary lock
LOCKOUT_SECONDS = 15 * 60


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        try:
            import streamlit as st
            url = str(st.secrets.get("DATABASE_URL", "")).strip()
        except Exception:
            url = ""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def storage_mode() -> str:
    return "postgresql" if _database_url() else "sqlite-local"


def _connect():
    url = _database_url()
    if url:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("DATABASE_URL is configured but psycopg is missing; install psycopg[binary].") from exc
        conn = psycopg.connect(url, connect_timeout=10)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                token TEXT PRIMARY KEY,
                account_name TEXT NOT NULL,
                questions_used INTEGER NOT NULL DEFAULT 0,
                unlocked INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                username TEXT,
                password_salt TEXT,
                password_hash TEXT
            )
        """)
        for column, sql_type in (("username", "TEXT"), ("password_salt", "TEXT"), ("password_hash", "TEXT")):
            conn.execute(f"ALTER TABLE accounts ADD COLUMN IF NOT EXISTS {column} {sql_type}")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_username ON accounts (username) WHERE username IS NOT NULL")
        conn.execute("CREATE TABLE IF NOT EXISTS login_attempts (username TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0, locked_until DOUBLE PRECISION NOT NULL DEFAULT 0)")
        conn.commit()
        return conn

    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            token TEXT PRIMARY KEY,
            account_name TEXT NOT NULL,
            questions_used INTEGER NOT NULL DEFAULT 0,
            unlocked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
    for name, sql_type in (("username", "TEXT"), ("password_salt", "TEXT"), ("password_hash", "TEXT")):
        if name not in cols:
            conn.execute(f"ALTER TABLE accounts ADD COLUMN {name} {sql_type}")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_username ON accounts(username) WHERE username IS NOT NULL")
    # Tracked per typed username (even unknown ones) so locking does not reveal which usernames exist.
    conn.execute("CREATE TABLE IF NOT EXISTS login_attempts (username TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0)")
    conn.commit()
    return conn


def _execute(conn, sql: str, params=()):
    if storage_mode() == "postgresql":
        sql = sql.replace("?", "%s")
    return conn.execute(sql, params)


def valid_name(name: str) -> bool:
    return bool(name and _NAME_RE.fullmatch(name.strip()))


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def valid_username(username: str) -> bool:
    return bool(_USERNAME_RE.fullmatch(normalize_username(username)))


def _password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), _HASH_ROUNDS).hex()


def create_user(username: str, password: str, account_name: str) -> str:
    username = normalize_username(username)
    account_name = (account_name or "").strip()
    if not valid_username(username):
        raise ValueError("Username must be 3–32 characters and use only letters, numbers, dots, underscores, or hyphens.")
    if not valid_name(account_name):
        raise ValueError("Please enter a valid name (up to 60 characters).")
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if len(password) > 1024:
        raise ValueError("Password is too long.")

    token = secrets.token_urlsafe(32)
    salt = secrets.token_hex(16)
    digest = _password_hash(password, salt)
    conn = _connect()
    try:
        _execute(conn,
            "INSERT INTO accounts (token, account_name, username, password_salt, password_hash) VALUES (?, ?, ?, ?, ?)",
            (token, account_name, username, salt, digest),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        # Avoid leaking database-specific errors to the UI.
        if "unique" in str(exc).lower() or "duplicate key" in str(exc).lower():
            raise ValueError("That username is already taken. Please choose another.") from exc
        raise
    finally:
        conn.close()
    return token


def login_lockout_seconds(username: str) -> int:
    """Seconds remaining before this username may try again (0 if not locked)."""
    username = normalize_username(username)
    if not username:
        return 0
    conn = _connect()
    try:
        row = _execute(conn, "SELECT locked_until FROM login_attempts WHERE username = ?", (username,)).fetchone()
    finally:
        conn.close()
    remaining = (float(row[0]) - time.time()) if row else 0
    return int(remaining) + 1 if remaining > 0 else 0


def _record_login_failure(username: str) -> None:
    conn = _connect()
    try:
        row = _execute(conn, "SELECT failures FROM login_attempts WHERE username = ?", (username,)).fetchone()
        failures = (row[0] if row else 0) + 1
        locked_until = 0.0
        if failures >= MAX_FAILED_LOGINS:
            locked_until, failures = time.time() + LOCKOUT_SECONDS, 0
        _execute(conn,
                 "INSERT INTO login_attempts (username, failures, locked_until) VALUES (?, ?, ?) "
                 "ON CONFLICT (username) DO UPDATE SET failures = EXCLUDED.failures, locked_until = EXCLUDED.locked_until",
                 (username, failures, locked_until))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _clear_login_failures(username: str) -> None:
    conn = _connect()
    try:
        _execute(conn, "DELETE FROM login_attempts WHERE username = ?", (username,))
        conn.commit()
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> str | None:
    username = normalize_username(username)
    if not username or not password or len(password) > 1024:
        return None
    if login_lockout_seconds(username) > 0:
        return None            # locked: do not even test the password
    conn = _connect()
    try:
        row = _execute(conn,
            "SELECT token, password_salt, password_hash FROM accounts WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        conn.close()
    token = None
    if not row or not row[1] or not row[2]:
        # Spend similar time as a real check so unknown usernames are not revealed by timing.
        _password_hash(password, "00" * 16)
    else:
        try:
            if hmac.compare_digest(_password_hash(password, row[1]), row[2]):
                token = row[0]
        except (ValueError, TypeError):
            token = None
    if token:
        _clear_login_failures(username)
    else:
        _record_login_failure(username)
    return token


def get_account(token: str):
    if not token:
        return None
    conn = _connect()
    try:
        row = _execute(conn,
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
        _execute(conn, "UPDATE accounts SET questions_used = questions_used + 1 WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


def unlock_account(token: str):
    conn = _connect()
    try:
        _execute(conn, "UPDATE accounts SET unlocked = 1 WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


def is_unlocked(token: str) -> bool:
    account = get_account(token)
    return bool(account and account["unlocked"])


def trial_exceeded(token: str, limit: int = 5) -> bool:
    account = get_account(token)
    return bool(account and not account["unlocked"] and account["questions_used"] >= limit)
