"""
scripts/ingest_kaggle.py

Loads the Kaggle Incident Event Log Dataset, collapses it to one record per
incident, maps columns onto the Recall schema, enriches missing fields with
the LLM (marked source="synthetic_enrichment"), and retains everything into
Hindsight.

Usage:
    python scripts/ingest_kaggle.py [--dry-run] [--limit N]

Reads KAGGLE_DATASET_PATH from .env (default: data/raw/incident_event_log.csv).
Idempotent – safe to re-run without duplicating memories.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── project root on path ──────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from app.config import get_settings
from app.models.schemas import IncidentCreate, Severity, FixStyle
from app.services.memory_service import retain_incident, ensure_bank
from app.services.llm_service import call_llm_json
from app.utils.logging_utils import get_logger

logger = get_logger("ingest_kaggle")
settings = get_settings()


# ── Constants ─────────────────────────────────────────────────────────────────

PLACEHOLDER_VALUES = {"?", "nan", "none", "null", "n/a", "na", "", "unknown"}

PRIORITY_MAP = {
    "1 - critical": "P1", "1": "P1",
    "2 - high": "P2", "2": "P2",
    "3 - moderate": "P3", "3": "P3",
    "4 - low": "P4", "4": "P4",
    "5 - planning": "P4", "5": "P4",
}

TECH_CATEGORIES = {
    "network", "hardware", "software", "database", "security",
    "infrastructure", "server", "application", "storage", "system",
    "compute", "middleware", "cloud", "virtualization", "monitoring",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def clean_val(v: any) -> str | None:
    """Return stripped string or None for placeholder values."""
    if v is None or pd.isna(v):
        return None
    s = str(v).strip()
    if s.lower() in PLACEHOLDER_VALUES:
        return None
    return s


def normalize_priority(raw: str | None) -> Severity:
    if raw is None:
        return Severity.P3
    key = str(raw).strip().lower()
    mapped = PRIORITY_MAP.get(key)
    if mapped:
        return Severity(mapped)
    # Try prefix match
    for k, v in PRIORITY_MAP.items():
        if key.startswith(k[0]):
            return Severity(v)
    return Severity.P3


def parse_ts(val: any) -> datetime | None:
    """Try multiple timestamp formats."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if s.lower() in PLACEHOLDER_VALUES:
        return None
    for fmt in (
        "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Try pandas fallback
    try:
        return pd.to_datetime(s).to_pydatetime().replace(tzinfo=timezone.utc)
    except Exception:
        return None


def is_technical(row: pd.Series, col_map: dict[str, str]) -> bool:
    """Heuristic: is this incident likely a technical/infrastructure issue?"""
    for col in ("category", "subcategory", "symptom", "assignment_group"):
        raw = row.get(col_map.get(col, ""), None)
        if raw and isinstance(raw, str):
            if any(t in raw.lower() for t in TECH_CATEGORIES):
                return True
    return False


# ── Column discovery ──────────────────────────────────────────────────────────

def discover_columns(df: pd.DataFrame) -> dict[str, str]:
    """
    Map logical field names to actual CSV column names using fuzzy matching.
    Returns a dict like {"incident_id": "Incident Number", ...}
    """
    cols_lower = {c.lower().replace(" ", "_"): c for c in df.columns}

    def find(candidates: list[str]) -> str | None:
        for c in candidates:
            if c in cols_lower:
                return cols_lower[c]
        # substring match
        for candidate in candidates:
            for key, real in cols_lower.items():
                if candidate in key:
                    return real
        return None

    return {
        "incident_id":      find(["number", "incident_number", "incident_id", "id"]),
        "opened_at":        find(["opened_at", "open_time", "created_at", "opened"]),
        "resolved_at":      find(["resolved_at", "resolve_time", "resolution_date", "closed_at"]),
        "category":         find(["category", "incident_type", "type"]),
        "subcategory":      find(["subcategory", "sub_category"]),
        "symptom":          find(["symptom", "short_description", "description", "summary"]),
        "priority":         find(["priority", "urgency", "impact"]),
        "assignment_group": find(["assignment_group", "support_group", "team"]),
        "resolver":         find(["resolved_by", "resolver", "assigned_to", "assignee"]),
        "closure_code":     find(["close_code", "closure_code", "resolution_code", "close_notes"]),
        "state":            find(["state", "status", "incident_state"]),
        "service":          find(["cmdb_ci", "configuration_item", "service", "ci", "component"]),
    }


# ── Collapse event log ────────────────────────────────────────────────────────

def collapse_to_incidents(df: pd.DataFrame, col_map: dict[str, str]) -> pd.DataFrame:
    """
    Collapse a multi-row event log to one row per incident_id.
    Keeps: earliest opened_at, latest resolved_at/state, last closure_code/resolver.
    """
    id_col = col_map.get("incident_id")
    if not id_col:
        logger.warning("No incident_id column found – treating each row as an incident")
        return df

    opened_col = col_map.get("opened_at")
    resolved_col = col_map.get("resolved_at")

    agg: dict[str, any] = {}
    for logical, real in col_map.items():
        if not real or real not in df.columns:
            continue
        if real == id_col:
            continue
        if real == opened_col:
            agg[real] = "first"
        elif real == resolved_col:
            agg[real] = "last"
        else:
            agg[real] = "last"

    if not agg:
        return df

    grouped = df.groupby(id_col, as_index=False).agg(agg)
    logger.info("Collapsed %d rows → %d unique incidents", len(df), len(grouped))
    return grouped


# ── LLM enrichment ────────────────────────────────────────────────────────────

def enrich_with_llm(row_dict: dict) -> dict:
    """
    Generate plausible error_messages, root_cause, resolution_steps,
    prevention_notes, and fix_style grounded in the real row data.
    Fields are marked source="synthetic_enrichment".
    """
    category = row_dict.get("category", "unknown")
    service = row_dict.get("service", "unknown")
    closure_code = row_dict.get("closure_code", "unknown")
    severity = row_dict.get("severity", "P3")
    title = row_dict.get("title", "incident")

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert SRE writing realistic incident records for a demo dataset. "
                "Generate plausible but CLEARLY FICTIONAL technical details for an ITSM incident. "
                "Ground details in the real metadata provided. "
                "Output valid JSON only."
            )
        },
        {
            "role": "user",
            "content": (
                f"Incident metadata:\n"
                f"- Title: {title}\n"
                f"- Category: {category}\n"
                f"- Service/CI: {service}\n"
                f"- Severity: {severity}\n"
                f"- Closure code: {closure_code}\n\n"
                "Generate realistic (but fictional) values for these fields. "
                "Return JSON with exactly these keys:\n"
                '{"error_messages": "...", "root_cause": "...", '
                '"resolution_steps": "...", "prevention_notes": "...", '
                '"fix_style": "quick_patch|proper_fix|rollback"}'
            )
        }
    ]

    result = call_llm_json(messages=messages)
    result["_llm_enriched"] = True
    return result


# ── Main pipeline ─────────────────────────────────────────────────────────────

def main(dry_run: bool = False, limit: int = 50) -> None:
    dataset_path = Path(settings.KAGGLE_DATASET_PATH)
    if not dataset_path.exists():
        logger.error("Dataset not found at %s – place the CSV in data/raw/", dataset_path)
        sys.exit(1)

    logger.info("Loading dataset from %s", dataset_path)

    # ── Step 1: Load ──────────────────────────────────────────────────────────
    try:
        df = pd.read_csv(dataset_path, low_memory=False)
    except Exception as exc:
        logger.error("Failed to read CSV: %s", exc)
        sys.exit(1)

    logger.info("Loaded %d rows × %d columns", len(df), len(df.columns))
    logger.info("Columns: %s", list(df.columns))

    # ── Step 2: Clean ─────────────────────────────────────────────────────────
    df = df.replace("?", pd.NA)
    df = df.drop_duplicates()
    logger.info("After dedup: %d rows", len(df))

    col_map = discover_columns(df)
    logger.info("Column mapping: %s", {k: v for k, v in col_map.items() if v})

    # ── Step 3: Collapse ──────────────────────────────────────────────────────
    df = collapse_to_incidents(df, col_map)

    # ── Step 4: Select representative incidents ───────────────────────────────
    # Prioritize technical/infrastructure categories
    tech_mask = df.apply(lambda r: is_technical(r, col_map), axis=1)
    tech_df = df[tech_mask]
    other_df = df[~tech_mask]

    # Take up to limit, favoring technical
    n_tech = min(len(tech_df), int(limit * 0.7))
    n_other = min(len(other_df), limit - n_tech)

    sample_tech = tech_df.sample(min(n_tech, len(tech_df)), random_state=42) if n_tech > 0 else pd.DataFrame()
    sample_other = other_df.sample(min(n_other, len(other_df)), random_state=42) if n_other > 0 else pd.DataFrame()
    sample = pd.concat([sample_tech, sample_other]).reset_index(drop=True)

    logger.info("Selected %d incidents for ingestion (%d technical, %d other)",
                len(sample), len(sample_tech), len(sample_other))

    # ── Step 5: Map → schema + enrich ────────────────────────────────────────
    counts = {"source_kaggle": 0, "source_synthetic": 0, "failed": 0}
    ingested_incidents = []

    for idx, row in sample.iterrows():
        try:
            # Map real columns
            inc_id = clean_val(row.get(col_map.get("incident_id", ""), None))
            opened_raw = row.get(col_map.get("opened_at", ""), None)
            resolved_raw = row.get(col_map.get("resolved_at", ""), None)

            opened_at = parse_ts(opened_raw) or datetime.now(timezone.utc)
            resolved_at = parse_ts(resolved_raw)

            duration = None
            if resolved_at and opened_at:
                delta = resolved_at - opened_at
                duration = max(0, int(delta.total_seconds() / 60))

            category = clean_val(row.get(col_map.get("category", ""), None)) or "General"
            subcategory = clean_val(row.get(col_map.get("subcategory", ""), None))
            symptom = clean_val(row.get(col_map.get("symptom", ""), None))
            service = clean_val(row.get(col_map.get("service", ""), None)) or "unknown-service"
            priority_raw = clean_val(row.get(col_map.get("priority", ""), None))
            severity = normalize_priority(priority_raw)
            resolver = clean_val(row.get(col_map.get("resolver", ""), None))
            closure_code = clean_val(row.get(col_map.get("closure_code", ""), None))
            assignment_group = clean_val(row.get(col_map.get("assignment_group", ""), None))

            title = symptom or f"{category} incident on {service}"
            if subcategory and subcategory.lower() not in title.lower():
                title = f"{category}/{subcategory}: {title}"
            title = title[:300]

            # LLM enrichment for missing technical fields
            row_dict = {
                "title": title,
                "category": category,
                "service": service,
                "severity": severity.value,
                "closure_code": closure_code or "unknown",
            }
            enriched = enrich_with_llm(row_dict) if settings.is_groq_configured() else {}

            fix_style_raw = enriched.get("fix_style", "unknown")
            try:
                fix_style = FixStyle(fix_style_raw)
            except ValueError:
                fix_style = FixStyle.UNKNOWN

            tags = [
                f"source:kaggle",
                f"category:{category.lower().replace(' ', '-')}",
                f"service:{service.lower().replace(' ', '-')}",
            ]
            if assignment_group:
                tags.append(f"team:{assignment_group.lower().replace(' ', '-')[:40]}")

            metadata_notes = {
                "original_category": category,
                "original_service": service,
                "original_priority": priority_raw or "unknown",
                "original_closure_code": closure_code or "unknown",
                "incident_id": inc_id or str(idx),
            }
            if enriched.get("_llm_enriched"):
                metadata_notes["enrichment_note"] = (
                    "error_messages, root_cause, resolution_steps, prevention_notes "
                    "are LLM-generated (synthetic_enrichment) – not from the original dataset"
                )

            incident = IncidentCreate(
                title=title,
                timestamp=opened_at,
                affected_services=[service],
                severity=severity,
                error_messages=enriched.get("error_messages"),
                root_cause=enriched.get("root_cause"),
                resolution_steps=enriched.get("resolution_steps"),
                prevention_notes=enriched.get("prevention_notes"),
                fixed_by=resolver,
                fix_style=fix_style,
                duration_minutes=duration,
                tags=tags,
                source="kaggle" if not enriched.get("_llm_enriched") else "synthetic_enrichment",
            )

            ingested_incidents.append(incident.model_dump(mode="json"))

            if not dry_run:
                result = retain_incident(incident)
                if result.get("success"):
                    counts["source_kaggle"] += 1
                    if enriched.get("_llm_enriched"):
                        counts["source_synthetic"] += 1
                else:
                    counts["failed"] += 1
                    logger.warning("Failed to retain: %s – %s", title[:60], result.get("message"))
            else:
                logger.info("[DRY RUN] Would retain: %s (sev=%s)", title[:60], severity.value)
                counts["source_kaggle"] += 1

        except Exception as exc:
            logger.error("Error processing row %d: %s", idx, exc)
            counts["failed"] += 1

    # ── Step 6: Summary ───────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("KAGGLE INGEST SUMMARY")
    print("="*60)
    print(f"Total processed: {len(sample)}")
    print(f"Successfully retained: {counts['source_kaggle']}")
    print(f"  of which LLM-enriched: {counts['source_synthetic']}")
    print(f"Failed: {counts['failed']}")
    if dry_run:
        print("(DRY RUN – no data written to Hindsight)")
    print("="*60 + "\n")

    # ── Step 7: Also load curated incidents ───────────────────────────────────
    curated_path = Path(__file__).parent.parent / "data" / "curated_incidents.json"
    if curated_path.exists():
        logger.info("Loading curated demo incidents from %s", curated_path)
        with open(curated_path) as f:
            curated = json.load(f)

        curated_count = 0
        for inc_data in curated.get("incidents", []):
            try:
                incident = IncidentCreate(**inc_data)
                if not dry_run:
                    result = retain_incident(incident)
                    if result.get("success"):
                        curated_count += 1
                else:
                    curated_count += 1
                    logger.info("[DRY RUN] Would retain curated: %s", inc_data.get("title", "?")[:60])
            except Exception as exc:
                logger.error("Failed to retain curated incident: %s", exc)

        print(f"Curated demo incidents retained: {curated_count}")

        # Also retain change events from curated data
        from app.models.schemas import ChangeEventCreate
        from app.services.memory_service import retain_change_event
        change_count = 0
        for ce_data in curated.get("change_events", []):
            try:
                event = ChangeEventCreate(**ce_data)
                if not dry_run:
                    result = retain_change_event(event)
                    if result.get("success"):
                        change_count += 1
                else:
                    change_count += 1
            except Exception as exc:
                logger.error("Failed to retain change event: %s", exc)
        print(f"Curated change events retained: {change_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Kaggle incident dataset into Hindsight")
    parser.add_argument("--dry-run", action="store_true", help="Parse and map without writing to Hindsight")
    parser.add_argument("--limit", type=int, default=50, help="Max incidents to ingest from Kaggle (default 50)")
    args = parser.parse_args()

    if not args.dry_run:
        ensure_bank()

    main(dry_run=args.dry_run, limit=args.limit)
