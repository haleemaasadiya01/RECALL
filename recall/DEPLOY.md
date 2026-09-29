# DEPLOY.md – Deploying Recall to Production (Free Tier)

## Prerequisites

- Docker installed locally
- GitHub account
- Hugging Face account (primary) or Render account (fallback)
- Hindsight Cloud API key → https://ui.hindsight.vectorize.io (use promo code **MEMHACK99** for $50 credits)
- Groq API key → https://console.groq.com (free tier)

---

## Step 1 – Local Setup & Secrets

```bash
cd recall
cp .env.example .env
# Edit .env and fill in:
#   HINDSIGHT_API_KEY=your_key
#   GROQ_API_KEY=your_key
```

## Step 2 – Verify Locally with Docker

```bash
# Build
docker build -t recall:local .

# Run
docker run --env-file .env -p 8000:8000 recall:local

# Test
curl http://localhost:8000/api/health
# Expected: {"status":"ok","hindsight_connected":true,...}
```

Open http://localhost:8000 in your browser. Click **Load Demo Incidents**, then run the demo query.

---

## Step 3 – Git Setup

```bash
cd recall
git init
git add .
git commit -m "feat: initial Recall – Incident Debugging Agent"

# Create repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/recall.git
git push -u origin main
```

> `.gitignore` already excludes `.env` and `data/raw/`. **Never commit secrets.**

---

## Option A – Hugging Face Spaces (Recommended)

Hugging Face Spaces supports Docker containers for free with public URLs.

### 4a-1. Create a Space

1. Go to https://huggingface.co/new-space
2. **Space name**: `recall-incident-agent`
3. **SDK**: `Docker`
4. **Hardware**: `CPU basic` (free)
5. Click **Create Space**

### 4a-2. Add Secrets

In your Space → **Settings** → **Repository secrets**:

| Secret Name | Value |
|---|---|
| `HINDSIGHT_API_KEY` | your Hindsight key |
| `GROQ_API_KEY` | your Groq key |
| `HINDSIGHT_BANK_ID` | `recall-incidents` |
| `HINDSIGHT_BASE_URL` | `https://api.hindsight.vectorize.io` |

### 4a-3. Deploy

```bash
# Add HF remote (get your token from https://huggingface.co/settings/tokens)
git remote add hf https://YOUR_HF_TOKEN@huggingface.co/spaces/YOUR_USERNAME/recall-incident-agent
git push hf main
```

The Space will build and deploy automatically (~3-5 minutes).
Your public URL: `https://YOUR_USERNAME-recall-incident-agent.hf.space`

### Cold Start Handling

Hugging Face Spaces on CPU free tier may sleep after inactivity. The app shows a friendly "Waking up…" banner with a progress bar until the server responds.

---

## Option B – Render Free Web Service (Fallback)

### 5b-1. Create Service

1. Go to https://render.com → **New** → **Web Service**
2. Connect your GitHub repo
3. **Environment**: `Docker`
4. **Plan**: Free

### 5b-2. Add Environment Variables

In Render dashboard → **Environment** tab, add the same keys as above.

### 5b-3. Deploy

Render auto-deploys on every push to `main`. URL format: `https://recall-incident-agent.onrender.com`

> **Note on Render free tier**: Services spin down after 15 minutes of inactivity. The cold-start banner handles this gracefully.

---

## Option C – Fly.io (If you need always-on)

```bash
fly auth login
fly launch  # Follow prompts; use Dockerfile
fly secrets set HINDSIGHT_API_KEY=... GROQ_API_KEY=...
fly deploy
```

---

## Step 5 – Load Demo Data

Once deployed:
1. Open the public URL
2. Click the **🚀 Load Demo Incidents** button in the sidebar
3. Wait ~30 seconds for all 11 incidents to be retained in Hindsight
4. Run the demo query: *"Connection timeout on DB write. PostgreSQL write operations are hanging on the payments-api service."*
5. Toggle Memory ON/OFF to see the before/after difference

---

## Step 6 – (Optional) Ingest Kaggle Data

If you have the Kaggle dataset (`data/raw/incident_event_log.csv`):

```bash
# Inspect columns first
python scripts/ingest_kaggle.py --dry-run --limit 10

# Full ingest (requires HINDSIGHT_API_KEY and GROQ_API_KEY)
python scripts/ingest_kaggle.py --limit 50
```

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `hindsight_connected: false` | Check `HINDSIGHT_API_KEY` is set and valid |
| `groq_configured: false` | Check `GROQ_API_KEY` is set |
| HF Space not building | Check `Dockerfile` syntax; look at Build Logs in Space settings |
| Demo data button fails | Ensure `frontend/demo-data.json` is in the repo (it's included) |
| Cold start > 60s | Normal for free tier; the banner will wait automatically |
