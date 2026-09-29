# LinkedIn Post

---

🔍 **I built an incident debugging agent that actually remembers — and it changes everything.**

Here's the problem I kept seeing: production goes down at 2 AM, the on-call engineer spends 30–45 minutes searching Slack, old tickets, and postmortems asking "have we seen this before?" Then they fix it. Write a postmortem. And the next engineer who sees the same failure starts from zero.

**Institutional knowledge lives in people's heads, not systems.**

So I built **Recall** — an AI-powered incident debugging agent with persistent memory.

The core idea: every incident, root cause, resolution, and "did the fix actually work?" gets stored as a structured memory in **Hindsight** (open source memory layer by Vectorize). When the next incident hits, the agent recalls relevant memories and delivers a structured diagnosis — grounded in your actual incident history, not generic LLM advice.

**The before/after is striking.**

Without memory: *"Check your database connection pool configuration."* 🤷

With Recall memory: *"We've seen this 4 times (Feb, Apr, Jun, Sep 2024). Root cause: RDS CPU at 90–97% from an unoptimized query. Fix: kill the long-running query with pg_terminate_backend, add a composite index. Prevention: CPU alert at 80%. Confidence: High (92%)."* ✅

The agent also:
- 🔁 Detects **precursors** — "there was a Node.js upgrade 2 hours before this OOM crash"
- 📊 Surfaces **patterns** — which services break most, which root causes recur
- 🔄 Learns from **feedback** — post-incident "this fix worked/didn't work" updates future recommendations
- ⚡ Shows **side-by-side** LLM-alone vs memory-powered — so you can see exactly what memory adds

**Tech stack:**
- Memory: Hindsight (hindsight-client SDK) — retain, recall, reflect
- LLM: Groq (gpt-oss-120b, fallback qwen3-32b)
- Backend: Python + FastAPI
- Frontend: Single-page app with Tailwind (dark/light mode, responsive)
- Deployed free on Hugging Face Spaces with Docker

**On data transparency:** I used the Kaggle Incident Event Log Dataset as a starting point, but it's an ITSM event log with no error messages or stack traces. LLM-generated enrichment fields are clearly labeled `source="synthetic_enrichment"` in every memory. The demo storyline uses hand-authored curated data, clearly marked as fictional. No fabricated history is ever presented as real.

The hardest part wasn't the tech — it was designing the memory schema so that incidents, change events, and post-incident feedback could all be queried together coherently. Hindsight's tagging and temporal retrieval made that possible.

Live demo and full code: [GitHub link placeholder]

What would you add to this? Slack auto-ingest? PagerDuty webhook? Auto-reflect on every postmortem? Let me know in the comments 👇

#DevOps #IncidentResponse #AI #MachineLearning #SRE #Hindsight #Groq #FastAPI #OpenSource #ProductionSystems

---
