# ClariX focused build: deployment and account persistence

## Only two product workspaces

1. **Obligation Intelligence** — extracts and structures regulatory obligations, including subject, action, scope, conditions, exceptions, cross-references, semantic interpretation, atomic obligation elements, and source metadata.
2. **Gap Analysis** — assesses the already-prepared obligations against client evidence and produces a reviewable PDF report.

The username/password account entry, PDF upload controls, and logout are supporting access/input functions, not additional product workspaces. Dashboard, standalone regulatory Q&A, Documents, Reports, and Accuracy Test have been removed from the visible navigation. PDF export remains inside Gap Analysis.

## Persistent account storage (important)

A custom domain does **not** make a local SQLite file durable. Streamlit Community Cloud's local app filesystem should not be relied on to preserve accounts through redeployments or host resets.

The app supports a managed PostgreSQL database through `DATABASE_URL`. For a small early pilot, use a managed Postgres free tier (for example, Neon or Supabase) and configure the connection string as a Streamlit secret:

```toml
GEMINI_API_KEY = "your-existing-gemini-key"
DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require"
```

Do not commit `.streamlit/secrets.toml`, database URLs, passwords, API keys, or any other credentials to GitHub. The database table and username index are created automatically at first connection. `psycopg[binary]` is included in requirements.

If `DATABASE_URL` is absent, the app uses local SQLite for local development and shows a warning in the sidebar. That fallback is **not** a durable Streamlit Cloud solution. Configure `DATABASE_URL` before inviting early users; a custom domain is unrelated to this requirement.

## Data persistence boundary

The PostgreSQL database persists account names, usernames, password hashes/salts, trial counts and unlock state. Uploaded PDFs, vector indexes, structured obligations, and gap-analysis results still live in the Streamlit session's memory and are not saved across a browser session or app restart in this build. Do not promise saved assessments or document persistence yet.

## Account security notes

- Passwords are hashed using PBKDF2-HMAC-SHA256 with per-account random salts; plaintext passwords are not stored.
- The remembered-browser session token is retained in the `acct` URL query parameter for refresh continuity. Treat that URL as a bearer credential: anyone with the full URL may be able to reopen that session. Use Log out on shared devices.
- Existing name-only accounts do not have usernames/password hashes and cannot authenticate through the new login screen. Users will need to create username/password accounts unless those old accounts are manually migrated.

## Verification performed

See `TEST_RESULTS.md` for the exact local checks. Live Gemini requests, the deployed Streamlit instance, and an actual managed PostgreSQL connection must still be verified using deployment credentials before production use.
