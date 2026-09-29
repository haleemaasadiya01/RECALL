# 🔍 Recall – Incident Debugging Agent with Persistent Memory

![Python](https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi&logoColor=white)
![Hindsight](https://img.shields.io/badge/Memory-Hindsight%20by%20Vectorize-6d28d9?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48dGV4dCB5PSIuOWVtIiBmb250LXNpemU9IjkwIj7wn6eJPC90ZXh0Pjwvc3ZnPg==)
![Groq](https://img.shields.io/badge/LLM-Groq-f97316?logo=groq&logoColor=white)
![Tests](https://img.shields.io/badge/tests-35%20passing-22c55e)
![License](https://img.shields.io/badge/license-MIT-blue)

> **Stop re-learning the same incidents.** Recall gives your team AI-powered incident diagnosis that remembers every past failure — and gets smarter with each one.

---

## 🎬 Demo

![Dashboard Preview](https://github.com/haleemaasadiya01/HR-Analytics-Dashboard/blob/main/HRAnalyticDashboard.png)

**Before:** *"Connection timeout on DB write"* → LLM gives generic advice about checking connection pools.

**After (with Recall memory):** *"We've seen this 4 times before. Last time it was RDS at 95% CPU from an unoptimized query. Fix: kill the long-running query and add a composite index. Prevention: CPU alert at 80%. Confidence: High (92%)."*


---

## ✨ Features

- 🧠 **Persistent Memory** – Every incident, root cause, fix, and outcome stored in [Hindsight](https://hindsight.vectorize.io/) (Vectorize)
- 🔁 **"Have we seen this?"** – Instant recall of past occurrences with dates and links
- ⚠️ **Precursor Detection** – Correlates recent change events (deploys, config changes) with current symptoms
- 📊 **Pattern Insights** – Hindsight `reflect` surfaces recurring root causes, riskiest services, common precursors
- 🔄 **Feedback Loop** – Post-incident "fix worked / didn't work" updates future recommendations
- ⚡ **Memory vs No-Memory** – Side-by-side before/after comparison with the same query
- 🌙 **Dark/Light Mode** – Clean, professional UI with Tailwind
- 📱 **Responsive** – Works on mobile
- 🔒 **Secret Redaction** – API keys, tokens, emails scrubbed before storage
- 🐳 **Docker Ready** – One-command build and deploy

---

## 🏗️ Architecture

```
Engineer Query
     │
     ▼
Web UI (HTML/JS/Tailwind)
     │  POST /api/diagnose
     ▼
FastAPI Backend
     │
     ├─── recall() ──► Hindsight Cloud (Memory Bank)
     │                        ◄── recalled memories ──
     │
     └─── LLM call ──► Groq (gpt-oss-120b / qwen3-32b)
                              ◄── structured JSON ──
     │
     ▼
DiagnoseResponse (citations, confidence, precursors)
```

**Memory flow:**
- `retain` – stores incident/change/feedback with tags and timestamp
- `recall` – semantic search over memory bank, returns ranked results
- `reflect` – reasons over all memories to surface patterns

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [Hindsight API key](https://ui.hindsight.vectorize.io) (use promo code **MEMHACK99** for $50 credits)
- [Groq API key](https://console.groq.com) (free)

### Local Setup

```bash
git clone https://github.com/haleemaasadiya01/recall.git
cd recall

pip install -r requirements.txt

cp .env.example .env
# Edit .env: fill in HINDSIGHT_API_KEY and GROQ_API_KEY

uvicorn app.main:app --reload
# Open http://localhost:8000
```

### Load Demo Data

```bash
# Via the UI: click "🚀 Load Demo Incidents"
# OR via the ingest script:
python scripts/ingest_kaggle.py --dry-run   # preview
python scripts/ingest_kaggle.py             # ingest curated + Kaggle data
```

### Docker

```bash
docker build -t recall .
docker run --env-file .env -p 8000:8000 recall
```

---

## 📖 API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Health check / connection status |
| `/api/incidents` | POST | Ingest a single incident |
| `/api/incidents/batch` | POST | Bulk ingest incidents |
| `/api/incidents/upload` | POST | Upload JSON file |
| `/api/changes` | POST | Record a change event |
| `/api/diagnose` | POST | Diagnose an incident (with/without memory) |
| `/api/compare` | POST | Side-by-side memory vs no-memory |
| `/api/feedback` | POST | Submit post-incident feedback |
| `/api/patterns` | POST | Reflect on all incidents for patterns |

Full OpenAPI docs: `http://localhost:8000/api/docs`

---

## 🗂️ Project Structure

```
recall/
├── app/
│   ├── api/routes.py          # FastAPI endpoints
│   ├── models/schemas.py      # Pydantic schemas
│   ├── services/
│   │   ├── memory_service.py  # Hindsight retain/recall/reflect
│   │   ├── llm_service.py     # Groq calls + fallback
│   │   └── agent.py           # Orchestration
│   ├── utils/logging_utils.py # Redacting formatter
│   ├── config.py              # Settings from .env
│   └── main.py                # FastAPI app factory
├── frontend/
│   ├── index.html             # SPA (Tailwind CDN)
│   └── demo-data.json         # Curated demo incidents
├── scripts/
│   └── ingest_kaggle.py       # Kaggle dataset pipeline
├── data/
│   └── curated_incidents.json # 11 hand-authored demo incidents
├── tests/
│   └── test_recall.py         # 35 pytest tests
├── docs/
│   └── PROJECT_DOCUMENT.md    # Technical whitepaper
├── Dockerfile
├── DEPLOY.md                  # Deployment guide
├── DATA_SOURCES.md            # Dataset attribution
├── .env.example
└── requirements.txt
```

---

## 🧪 Tests

```bash
python -m pytest tests/ -v
# 35 passed in ~3s
```

Tests cover: redaction, schema validation, retain/recall/error handling, LLM fallback, JSON parsing, agent pipeline, Kaggle ingest helpers.

---

## 📊 Data Sources

| Source | Type | Note |
|---|---|---|
| [Kaggle Incident Event Log](https://www.kaggle.com/datasets/winmedals/incident-event-log-dataset) | ITSM event log | Verify license before redistribution; not bundled in repo |
| `data/curated_incidents.json` | Hand-authored demo | MIT; 11 fictional incidents for demonstration |

**LLM-enriched fields** (error messages, root cause, resolution steps) are clearly marked `source="synthetic_enrichment"` and are illustrative only.
See [DATA_SOURCES.md](DATA_SOURCES.md) for full field-level attribution.

---

## 🚢 Deployment

See [DEPLOY.md](DEPLOY.md) for step-by-step instructions for:
- Hugging Face Spaces (primary, free)
- Render (fallback, free)
- Fly.io (always-on option)

---

## 📄 License

MIT – see [LICENSE](LICENSE)

---

## 🙏 Credits

- **Memory**: [Hindsight by Vectorize](https://hindsight.vectorize.io/) – the memory layer that makes this possible
- **LLM**: [Groq](https://groq.com) – fast, free-tier inference
- **Dataset**: [Kaggle Incident Event Log](https://www.kaggle.com/datasets/winmedals/incident-event-log-dataset) – Winmedals
- **UI**: [Tailwind CSS](https://tailwindcss.com)
