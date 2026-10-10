"""Persistent accounts with manual subscription expiry."""
import hashlib, hmac, re, secrets, sqlite3, time
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).parent / "clarix_accounts.db"
_NAME_RE = re.compile(r"^[A-Za-z0-9 ,.\-']{1,60}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
_HASH_ROUNDS = 600_000
_SECRET_COLUMNS = ("password_salt", "password_hash")  # never returned to callers
MAX_FAILED_LOGINS = 5          # consecutive wrong passwords before a temporary lock
LOCKOUT_SECONDS = 15 * 60

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
        "activated_at":"TEXT",
        "username":"TEXT", "password_salt":"TEXT", "password_hash":"TEXT"}
    for col, definition in migrations.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE accounts ADD COLUMN {col} {definition}")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_username ON accounts(username) WHERE username IS NOT NULL")
    # Tracked per typed username (even unknown ones) so locking does not reveal which usernames exist.
    conn.execute("CREATE TABLE IF NOT EXISTS login_attempts (username TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0)")
    conn.commit()
    return conn

def _public(row):
    """Row as a dict without password material."""
    return {k: row[k] for k in row.keys() if k not in _SECRET_COLUMNS}

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
    d = _public(row)
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
        d = _public(row)
        d["unlocked"] = bool(d["unlocked"]); d["suspended"] = bool(d["suspended"])
        d["subscription_active"] = _active(row)
        d["expired"] = bool(d["unlocked"] and d["paid_through"] and not d["suspended"] and not d["subscription_active"])
        result.append(d)
    return result

# ---------------------------------------------------------------------------
# Username / password sign-in (PBKDF2-HMAC-SHA256, per-user random salt)
# ---------------------------------------------------------------------------
def normalize_username(username):
    return (username or "").strip().lower()

def valid_username(username):
    return bool(_USERNAME_RE.fullmatch(normalize_username(username)))

def _password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                               bytes.fromhex(salt), _HASH_ROUNDS).hex()

def create_user(username, password, account_name):
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
        conn.execute("INSERT INTO accounts (token, account_name, username, password_salt, password_hash) VALUES (?, ?, ?, ?, ?)",
                     (token, account_name, username, salt, digest))
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError("That username is already taken. Please choose another.") from exc
    finally:
        conn.close()
    return token

def login_lockout_seconds(username):
    """Seconds remaining before this username may try again (0 if not locked)."""
    username = normalize_username(username)
    if not username:
        return 0
    conn = _connect()
    try:
        row = conn.execute("SELECT locked_until FROM login_attempts WHERE username = ?", (username,)).fetchone()
    finally:
        conn.close()
    remaining = (row["locked_until"] - time.time()) if row else 0
    return int(remaining) + 1 if remaining > 0 else 0

def _record_login_failure(username):
    conn = _connect()
    try:
        row = conn.execute("SELECT failures, locked_until FROM login_attempts WHERE username = ?", (username,)).fetchone()
        failures = (row["failures"] if row else 0) + 1
        locked_until = 0.0
        if failures >= MAX_FAILED_LOGINS:
            locked_until, failures = time.time() + LOCKOUT_SECONDS, 0
        conn.execute("INSERT INTO login_attempts (username, failures, locked_until) VALUES (?, ?, ?) "
                     "ON CONFLICT(username) DO UPDATE SET failures=excluded.failures, locked_until=excluded.locked_until",
                     (username, failures, locked_until))
        conn.commit()
    finally:
        conn.close()

def _clear_login_failures(username):
    conn = _connect()
    try:
        conn.execute("DELETE FROM login_attempts WHERE username = ?", (username,))
        conn.commit()
    finally:
        conn.close()

def authenticate_user(username, password):
    username = normalize_username(username)
    if not username or not password or len(password) > 1024:
        return None
    if login_lockout_seconds(username) > 0:
        return None            # locked: do not even test the password
    conn = _connect()
    try:
        row = conn.execute("SELECT token, password_salt, password_hash FROM accounts WHERE username = ?",
                           (username,)).fetchone()
    finally:
        conn.close()
    token = None
    if not row or not row["password_salt"] or not row["password_hash"]:
        # Spend similar time as a real check so unknown usernames are not revealed by timing.
        _password_hash(password, "00" * 16)
    else:
        try:
            candidate = _password_hash(password, row["password_salt"])
            if hmac.compare_digest(candidate, row["password_hash"]):
                token = row["token"]
        except (ValueError, TypeError):
            token = None
    if token:
        _clear_login_failures(username)
    else:
        _record_login_failure(username)
    return token
