# ClariX Intelligence

ClariX currently exposes exactly two product workspaces:

1. **Obligation Intelligence** — turns selected regulatory passages into structured obligations and records scope, conditions, exceptions, cross-references, interpretation, testable elements, and source metadata.
2. **Gap Analysis** — compares the prepared obligations with uploaded client evidence, shows element-level evidence checks, and exports a PDF report.

Create an account or sign in with a username and password. See [DEPLOYMENT_AND_STORAGE.md](DEPLOYMENT_AND_STORAGE.md) before deploying to Streamlit Community Cloud; set `DATABASE_URL` to a managed PostgreSQL database to persist account records across redeployments.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Set `GEMINI_API_KEY` in `.streamlit/secrets.toml` or the environment. For a persistent account store, also set `DATABASE_URL`. Without it, the app uses a local SQLite file for development and warns that this is not reliable durable storage on hosted deployments.

The two feature areas are intentionally narrow. Uploaded documents, indexes, prepared obligations and assessment results are currently session-scoped; this build does not claim to persist those across restarts. Results are evidence-based indications for qualified human review, not legal advice or proof of complete regulatory coverage.
