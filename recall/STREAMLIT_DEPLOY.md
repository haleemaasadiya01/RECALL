# Deploying Recall to Streamlit Cloud (Free Public Link)

Streamlit Community Cloud gives you a **free, permanent public URL** for any public GitHub repo in ~2 minutes.

---

## Prerequisites

- A **public GitHub repo** containing this project  
  (already at `https://github.com/haleemaasadiya01/recall`)
- A **Streamlit account** — sign up free at [share.streamlit.io](https://share.streamlit.io) (use your GitHub account)
- Your **Hindsight API key** and **Groq API key** (stored as Streamlit secrets, not in the repo)

---

## Step 1 — Push to GitHub

Make sure the following files are committed and pushed:

```
streamlit_app.py          ← the Streamlit app
streamlit_requirements.txt← dependencies for Streamlit Cloud
.streamlit/config.toml   ← theme config
app/                     ← backend services (unchanged)
data/curated_incidents.json
```

```bash
git add streamlit_app.py streamlit_requirements.txt .streamlit/config.toml
git commit -m "feat: add Streamlit UI"
git push
```

---

## Step 2 — Deploy on Streamlit Cloud

1. Go to **[share.streamlit.io](https://share.streamlit.io)** and sign in with GitHub.
2. Click **"New app"**.
3. Fill in:
   - **Repository**: `haleemaasadiya01/recall`
   - **Branch**: `main`
   - **Main file path**: `streamlit_app.py`
4. Click **"Advanced settings"** → **"Secrets"** and paste your keys (see Step 3 below).
5. Click **"Deploy!"**

Your live URL will be something like:  
`https://haleemaasadiya01-recall-streamlit-app-xxxxxx.streamlit.app`

---

## Step 3 — Add Secrets (API Keys)

In the Streamlit Cloud dashboard, under **Settings → Secrets**, paste:

```toml
HINDSIGHT_API_KEY = "your-hindsight-api-key-here"
GROQ_API_KEY      = "your-groq-api-key-here"

# Optional overrides
HINDSIGHT_BANK_ID      = "recall-incidents"
GROQ_PRIMARY_MODEL     = "openai/gpt-oss-120b"
GROQ_FALLBACK_MODEL    = "qwen/qwen3-32b"
```

> ⚠️ **Never commit API keys to the repo.** Streamlit secrets are encrypted and injected as environment variables at runtime.

---

## Step 4 — Set requirements file

Streamlit Cloud needs to know which requirements file to use.  
It will auto-detect `streamlit_requirements.txt` if `requirements.txt` is absent or if you specify it.

To be explicit, in the deploy dialog, set **"Requirements file"** to `streamlit_requirements.txt`.

Alternatively, you can rename `streamlit_requirements.txt` to `requirements.txt` — but note this removes the `pytest` and `uvicorn` entries that the test suite uses. Your call.

---

## Step 5 — Load Demo Data

Once deployed:

1. Open your live URL.
2. Click the **📦 Load Demo Data** tab.
3. Click **"🚀 Load All Demo Data into Memory"**.
4. Then go to the **⚖️ Compare** tab and try:
   > *"Connection timeout on DB write. PostgreSQL write operations hanging on payments-api."*

You'll see the before/after memory difference live.

---

## Updating the App

Any `git push` to `main` automatically triggers a redeploy on Streamlit Cloud. No CI/CD setup needed.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `ModuleNotFoundError: hindsight_client` | Check that `streamlit_requirements.txt` is the requirements file in settings |
| `GROQ_API_KEY not set` | Add it under Settings → Secrets in the Streamlit Cloud dashboard |
| App stuck on spinner | Groq free tier rate limit — wait ~10s and retry |
| `asyncio` errors | Already handled by `run_async()` in `streamlit_app.py` |
| Blank screen on first load | Normal — click any tab to initialize |

---

## Local Testing (before pushing)

```bash
pip install streamlit
streamlit run streamlit_app.py
```

Make sure your `.env` file has:

```
HINDSIGHT_API_KEY=your-key
GROQ_API_KEY=your-key
```
