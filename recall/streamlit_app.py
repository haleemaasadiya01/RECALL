"""
Recall – Streamlit UI
Incident Debugging Agent with Persistent Memory (Hindsight + Groq)
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Optional

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ─── Page config (MUST be first Streamlit call) ───────────────────────────────

st.set_page_config(
    page_title="Recall – Incident Debugging Agent",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Lazy import app services (after env is loaded) ───────────────────────────

@st.cache_resource
def _bootstrap():
    """Import services once, cache the module refs."""
    from app.services import agent as _agent
    from app.services import memory_service as _memory
    from app.models.schemas import (
        IncidentCreate,
        ChangeEventCreate,
        FeedbackSubmit,
        Severity,
        FixStyle,
        ChangeEventType,
    )
    return _agent, _memory, IncidentCreate, ChangeEventCreate, FeedbackSubmit, Severity, FixStyle, ChangeEventType


def run_async(coro):
    """Run an async coroutine from synchronous Streamlit context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ─── CSS ──────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .recall-header { font-size: 2.2rem; font-weight: 700; letter-spacing: -0.5px; margin-bottom: 0; }
    .recall-sub    { color: #57606a; font-size: 1rem; margin-top: 0; }
    .confidence-pill {
        display: inline-block; padding: 3px 14px; border-radius: 999px;
        font-size: 0.85rem; font-weight: 600;
    }
    .pill-high   { background: #d1fae5; color: #065f46; }
    .pill-medium { background: #fef3c7; color: #92400e; }
    .pill-low    { background: #fee2e2; color: #991b1b; }
    .pill-none   { background: #f3f4f6; color: #374151; }
    .memory-card {
        background: #f7f8fa; border: 1px solid #e5e7eb;
        border-radius: 8px; padding: 12px 16px; margin: 6px 0;
        font-size: 0.85rem;
    }
    .section-label { font-weight: 600; font-size: 0.9rem; color: #374151; margin-bottom: 4px; }
    .seen-yes { color: #065f46; font-weight: 700; }
    .seen-no  { color: #57606a; font-style: italic; }
</style>
""", unsafe_allow_html=True)


# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🔍 Recall")
    st.caption("Incident Debugging Agent with Persistent Memory")
    st.divider()

    # API key inputs (shown if not set via env)
    hindsight_key = os.getenv("HINDSIGHT_API_KEY", "")
    groq_key = os.getenv("GROQ_API_KEY", "")

    if not hindsight_key:
        hindsight_key = st.text_input("Hindsight API Key", type="password",
                                       placeholder="paste key here",
                                       help="Get free credits at ui.hindsight.vectorize.io — promo code MEMHACK99")
        if hindsight_key:
            os.environ["HINDSIGHT_API_KEY"] = hindsight_key

    if not groq_key:
        groq_key = st.text_input("Groq API Key", type="password",
                                  placeholder="paste key here",
                                  help="Free at console.groq.com — no credit card required")
        if groq_key:
            os.environ["GROQ_API_KEY"] = groq_key

    st.divider()

    # Status indicators
    hindsight_ok = bool(os.getenv("HINDSIGHT_API_KEY"))
    groq_ok = bool(os.getenv("GROQ_API_KEY"))

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"{'🟢' if hindsight_ok else '🔴'} Hindsight")
    with col2:
        st.markdown(f"{'🟢' if groq_ok else '🔴'} Groq")

    st.divider()
    st.caption("Built with Hindsight (Vectorize) + Groq")
    st.caption("[GitHub](https://github.com/haleemaasadiya01/recall) · [Hindsight](https://ui.hindsight.vectorize.io)")


# ─── Header ───────────────────────────────────────────────────────────────────

st.markdown('<p class="recall-header">🔍 Recall</p>', unsafe_allow_html=True)
st.markdown('<p class="recall-sub">AI-powered incident debugging with persistent memory</p>', unsafe_allow_html=True)
st.divider()


# ─── Tabs ─────────────────────────────────────────────────────────────────────

tab_diagnose, tab_compare, tab_add, tab_changes, tab_feedback, tab_patterns, tab_load = st.tabs([
    "🩺 Diagnose",
    "⚖️ Compare",
    "➕ Add Incident",
    "⚡ Change Events",
    "✅ Feedback",
    "📊 Patterns",
    "📦 Load Demo Data",
])


# ─── Helper: render a DiagnoseResponse ───────────────────────────────────────

def _confidence_pill(label: str, score: float) -> str:
    cls = {"High": "pill-high", "Medium": "pill-medium", "Low": "pill-low"}.get(label, "pill-none")
    pct = int(score * 100)
    return f'<span class="confidence-pill {cls}">{label} ({pct}%)</span>'


def render_diagnosis(result, title: str = "Diagnosis"):
    st.subheader(title)

    # Have we seen this?
    if result.have_we_seen_this:
        st.markdown(
            f'<p class="seen-yes">✅ Yes — seen {result.occurrence_count}× '
            f'({", ".join(result.occurrence_dates[:5]) or "dates unknown"})</p>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<p class="seen-no">❌ No prior match found in memory</p>', unsafe_allow_html=True)

    # Confidence
    st.markdown(
        _confidence_pill(result.confidence_label, result.confidence),
        unsafe_allow_html=True,
    )
    st.write("")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown('<p class="section-label">Root Cause Hypothesis</p>', unsafe_allow_html=True)
        st.info(result.root_cause_hypothesis)

        st.markdown('<p class="section-label">Recommended Fix</p>', unsafe_allow_html=True)
        st.success(result.recommended_fix)

    with col_b:
        st.markdown('<p class="section-label">What to Check First</p>', unsafe_allow_html=True)
        if result.what_to_check_first:
            for i, item in enumerate(result.what_to_check_first, 1):
                st.markdown(f"**{i}.** {item}")
        else:
            st.caption("—")

        st.markdown('<p class="section-label">Possible Precursors</p>', unsafe_allow_html=True)
        if result.possible_precursors:
            for p in result.possible_precursors:
                st.markdown(f"• {p}")
        else:
            st.caption("None identified")

    st.markdown('<p class="section-label">Prevention Recommendation</p>', unsafe_allow_html=True)
    st.warning(result.prevention_recommendation)

    # Memories used
    if result.memories_used:
        with st.expander(f"🧠 Memories used ({len(result.memories_used)})"):
            for m in result.memories_used:
                tags_str = " · ".join(m.tags[:6]) if m.tags else "no tags"
                st.markdown(
                    f'<div class="memory-card"><strong>{m.id}</strong> &nbsp;|&nbsp; '
                    f'<code>{tags_str}</code><br>{m.text[:400]}{"…" if len(m.text) > 400 else ""}</div>',
                    unsafe_allow_html=True,
                )


# ─── TAB: Diagnose ────────────────────────────────────────────────────────────

with tab_diagnose:
    st.subheader("Diagnose an Incident")
    st.caption("Paste a stack trace, error message, or describe the symptom in plain English.")

    query_input = st.text_area(
        "Incident description",
        placeholder='e.g. "Connection timeout on DB write. PostgreSQL write operations hanging on payments-api."',
        height=120,
    )
    col1, col2 = st.columns([2, 1])
    with col1:
        service_filter = st.text_input("Service filter (optional)", placeholder="e.g. payments-api")
    with col2:
        with_memory = st.checkbox("Use Hindsight memory", value=True)

    if st.button("🩺 Diagnose", type="primary", disabled=not query_input.strip()):
        if not os.getenv("GROQ_API_KEY"):
            st.error("Groq API key required — add it in the sidebar.")
        else:
            _agent, _memory, *_ = _bootstrap()
            with st.spinner("Consulting memory and running diagnosis…"):
                try:
                    result = run_async(
                        _agent.diagnose(
                            query=query_input.strip(),
                            service_filter=service_filter.strip() or None,
                            with_memory=with_memory,
                        )
                    )
                    render_diagnosis(result)
                except Exception as exc:
                    st.error(f"Diagnosis failed: {exc}")


# ─── TAB: Compare ─────────────────────────────────────────────────────────────

with tab_compare:
    st.subheader("Before vs After Memory")
    st.caption("Run the same query without and with Hindsight memory — see the difference side by side.")

    compare_query = st.text_area(
        "Incident description",
        placeholder='e.g. "Payments API is down. DB connections timing out."',
        height=100,
        key="compare_query",
    )

    if st.button("⚖️ Run Comparison", type="primary", disabled=not compare_query.strip()):
        if not os.getenv("GROQ_API_KEY"):
            st.error("Groq API key required — add it in the sidebar.")
        else:
            _agent, _memory, *_ = _bootstrap()
            with st.spinner("Running both queries (this takes ~10–15s)…"):
                try:
                    without = run_async(_agent.diagnose(query=compare_query.strip(), with_memory=False))
                    with_mem = run_async(_agent.diagnose(query=compare_query.strip(), with_memory=True))

                    left, right = st.columns(2)
                    with left:
                        st.markdown("### ❌ Without Memory (Plain LLM)")
                        render_diagnosis(without, title="")
                    with right:
                        st.markdown("### ✅ With Recall Memory")
                        render_diagnosis(with_mem, title="")
                except Exception as exc:
                    st.error(f"Comparison failed: {exc}")


# ─── TAB: Add Incident ────────────────────────────────────────────────────────

with tab_add:
    st.subheader("Add Incident to Memory")
    st.caption("Store a resolved incident so Recall can learn from it.")

    with st.form("incident_form"):
        title = st.text_input("Title *", placeholder="e.g. Connection timeout on DB write – payments-api")
        col1, col2 = st.columns(2)
        with col1:
            severity = st.selectbox("Severity", ["P1", "P2", "P3", "P4"], index=2)
        with col2:
            affected_services = st.text_input("Affected services", placeholder="payments-api, rds-primary")

        col3, col4 = st.columns(2)
        with col3:
            fixed_by = st.text_input("Fixed by")
        with col4:
            fix_style = st.selectbox("Fix style", ["unknown", "quick_patch", "proper_fix", "rollback"])

        duration = st.number_input("Duration (minutes)", min_value=0, value=0)
        error_messages = st.text_area("Error messages", height=80)
        root_cause = st.text_area("Root cause *", height=80)
        resolution_steps = st.text_area("Resolution steps", height=80)
        prevention_notes = st.text_area("Prevention notes", height=60)

        submitted = st.form_submit_button("💾 Store in Memory", type="primary")

    if submitted:
        if not title.strip() or not root_cause.strip():
            st.error("Title and root cause are required.")
        elif not os.getenv("HINDSIGHT_API_KEY"):
            st.error("Hindsight API key required — add it in the sidebar.")
        else:
            _, _memory, IncidentCreate, _, _, Severity, FixStyle, _ = _bootstrap()
            try:
                incident = IncidentCreate(
                    title=title.strip(),
                    affected_services=affected_services,
                    severity=Severity(severity),
                    fixed_by=fixed_by.strip() or None,
                    fix_style=FixStyle(fix_style),
                    duration_minutes=int(duration) if duration > 0 else None,
                    error_messages=error_messages.strip() or None,
                    root_cause=root_cause.strip(),
                    resolution_steps=resolution_steps.strip() or None,
                    prevention_notes=prevention_notes.strip() or None,
                    source="manual",
                )
                with st.spinner("Storing incident…"):
                    result = run_async(_memory.retain_incident(incident))
                if result.get("success"):
                    st.success(f"✅ Incident stored! Memory ID: `{result.get('memory_id', '?')}`")
                else:
                    st.error(f"Failed: {result.get('message', 'Unknown error')}")
            except Exception as exc:
                st.error(f"Error: {exc}")


# ─── TAB: Change Events ───────────────────────────────────────────────────────

with tab_changes:
    st.subheader("Log a Change Event")
    st.caption("Track deploys, config changes, and infra updates as precursor signals for future diagnoses.")

    with st.form("change_form"):
        ev_title = st.text_input("Title *", placeholder="e.g. New fraud detection feature v3.1.2 deployed")
        col1, col2 = st.columns(2)
        with col1:
            ev_type = st.selectbox("Event type", ["deploy", "config", "infra", "dependency", "other"])
        with col2:
            ev_services = st.text_input("Affected services", placeholder="payments-api, checkout-worker")

        ev_author = st.text_input("Author")
        ev_description = st.text_area("Description *", height=100,
                                       placeholder="What changed and why?")

        ev_submitted = st.form_submit_button("⚡ Log Change Event", type="primary")

    if ev_submitted:
        if not ev_title.strip() or not ev_description.strip():
            st.error("Title and description are required.")
        elif not os.getenv("HINDSIGHT_API_KEY"):
            st.error("Hindsight API key required — add it in the sidebar.")
        else:
            _, _memory, _, ChangeEventCreate, _, _, _, ChangeEventType = _bootstrap()
            try:
                event = ChangeEventCreate(
                    title=ev_title.strip(),
                    event_type=ChangeEventType(ev_type),
                    affected_services=ev_services,
                    description=ev_description.strip(),
                    author=ev_author.strip() or None,
                )
                with st.spinner("Logging change event…"):
                    result = run_async(_memory.retain_change_event(event))
                if result.get("success"):
                    st.success(f"✅ Change event logged! ID: `{result.get('memory_id', '?')}`")
                else:
                    st.error(f"Failed: {result.get('message', 'Unknown error')}")
            except Exception as exc:
                st.error(f"Error: {exc}")


# ─── TAB: Feedback ────────────────────────────────────────────────────────────

with tab_feedback:
    st.subheader("Submit Post-Incident Feedback")
    st.caption("Tell Recall whether a fix worked — this reinforces the learning loop for future diagnoses.")

    with st.form("feedback_form"):
        fb_title = st.text_input("Incident title *", placeholder="e.g. Connection timeout on DB write – payments-api")
        col1, col2 = st.columns(2)
        with col1:
            fb_worked = st.radio("Did the fix work?", ["Yes", "No"], horizontal=True)
        with col2:
            fb_style = st.selectbox("Fix style", ["unknown", "quick_patch", "proper_fix", "rollback"])

        fb_root_cause = st.text_area("Confirmed root cause", height=70)
        fb_notes = st.text_area("Notes", height=70, placeholder="Anything that would help the next engineer")

        fb_submitted = st.form_submit_button("✅ Submit Feedback", type="primary")

    if fb_submitted:
        if not fb_title.strip():
            st.error("Incident title is required.")
        elif not os.getenv("HINDSIGHT_API_KEY"):
            st.error("Hindsight API key required — add it in the sidebar.")
        else:
            _, _memory, _, _, _, _, FixStyle, _ = _bootstrap()
            with st.spinner("Storing feedback…"):
                try:
                    result = run_async(
                        _memory.retain_feedback(
                            incident_title=fb_title.strip(),
                            fix_worked=(fb_worked == "Yes"),
                            actual_root_cause=fb_root_cause.strip() or None,
                            notes=fb_notes.strip() or None,
                            fix_style=fb_style,
                        )
                    )
                    if result.get("success"):
                        st.success("✅ Feedback stored — Recall will use this in future diagnoses.")
                    else:
                        st.error(f"Failed: {result.get('message', 'Unknown error')}")
                except Exception as exc:
                    st.error(f"Error: {exc}")


# ─── TAB: Patterns ────────────────────────────────────────────────────────────

with tab_patterns:
    st.subheader("Pattern Insights")
    st.caption(
        "Uses Hindsight's `reflect` capability to synthesize recurring root causes, "
        "riskiest services, and common precursors across all stored incidents."
    )

    if st.button("📊 Analyse Patterns", type="primary"):
        if not os.getenv("HINDSIGHT_API_KEY"):
            st.error("Hindsight API key required — add it in the sidebar.")
        else:
            _, _memory, *_ = _bootstrap()
            with st.spinner("Reflecting on all stored memories (this may take 15–20s)…"):
                try:
                    query = (
                        "Analyse all stored incidents and change events. "
                        "Surface: (1) top recurring root causes with frequency, "
                        "(2) riskiest services by incident count and severity, "
                        "(3) common precursor patterns (change event → incident), "
                        "(4) team fix preferences (quick patch vs proper fix ratio), "
                        "(5) prevention recommendations. Use headers, bullet points, and tables."
                    )
                    result = run_async(_memory.reflect_patterns(query=query))
                    st.markdown(result.text)
                    if result.facts_used:
                        st.caption(f"Based on {result.facts_used} memory facts.")
                except Exception as exc:
                    st.error(f"Pattern analysis failed: {exc}")


# ─── TAB: Load Demo Data ──────────────────────────────────────────────────────

with tab_load:
    st.subheader("Load Demo Dataset")
    st.caption(
        "Load the curated demo incidents and change events into Hindsight memory. "
        "This gives Recall real data to work with for the Diagnose and Compare tabs."
    )

    # Show dataset preview
    try:
        with open("data/curated_incidents.json") as f:
            demo_data: dict[str, Any] = json.load(f)
        incidents = demo_data.get("incidents", [])
        changes = demo_data.get("change_events", [])

        st.info(
            f"📦 Dataset: **{len(incidents)} incidents** and **{len(changes)} change events**\n\n"
            "Includes a recurring DB timeout storyline on the payments-api — perfect for demoing the Compare tab."
        )

        with st.expander("Preview incidents"):
            for inc in incidents:
                st.markdown(
                    f"**{inc['title']}** — `{inc['severity']}` — "
                    f"{', '.join(inc['affected_services'])} — {inc['timestamp'][:10]}"
                )

        with st.expander("Preview change events"):
            for chg in changes:
                st.markdown(f"**{chg['title']}** — `{chg['event_type']}` — {chg['timestamp'][:10]}")

    except FileNotFoundError:
        st.warning("data/curated_incidents.json not found.")
        incidents, changes = [], []

    if st.button("🚀 Load All Demo Data into Memory", type="primary"):
        if not os.getenv("HINDSIGHT_API_KEY"):
            st.error("Hindsight API key required — add it in the sidebar.")
        elif not incidents and not changes:
            st.error("No demo data found.")
        else:
            _, _memory, IncidentCreate, ChangeEventCreate, _, Severity, FixStyle, ChangeEventType = _bootstrap()

            progress = st.progress(0, text="Loading…")
            total = len(incidents) + len(changes)
            done = 0
            errors = 0

            for raw in incidents:
                try:
                    inc = IncidentCreate(**raw)
                    result = run_async(_memory.retain_incident(inc))
                    if not result.get("success"):
                        errors += 1
                except Exception as exc:
                    st.warning(f"Skipped '{raw.get('title','?')}': {exc}")
                    errors += 1
                done += 1
                progress.progress(done / total, text=f"Incidents: {done}/{len(incidents)}")

            for raw in changes:
                try:
                    chg = ChangeEventCreate(**raw)
                    result = run_async(_memory.retain_change_event(chg))
                    if not result.get("success"):
                        errors += 1
                except Exception as exc:
                    st.warning(f"Skipped '{raw.get('title','?')}': {exc}")
                    errors += 1
                done += 1
                progress.progress(done / total, text=f"Change events: {done - len(incidents)}/{len(changes)}")

            progress.empty()

            if errors == 0:
                st.success(
                    f"✅ All {total} records loaded into Hindsight memory!\n\n"
                    "Now try the **Compare** tab with: "
                    "*\"Connection timeout on DB write. PostgreSQL write operations hanging on payments-api.\"*"
                )
            else:
                st.warning(f"Loaded with {errors} error(s). Check warnings above.")
