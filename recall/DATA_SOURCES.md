# DATA_SOURCES.md – Dataset Attribution and Field Disclosure

## 1. Kaggle Incident Event Log Dataset

| Field | Value |
|---|---|
| **Name** | Incident Event Log Dataset |
| **URL** | https://www.kaggle.com/datasets/winmedals/incident-event-log-dataset |
| **Format** | CSV, ITSM event log (one row per state change; multiple rows per incident) |
| **License** | Please verify the license on the Kaggle dataset page before redistributing any portion of the data. This project does **not** bundle the raw CSV in the repository. |
| **Attribution** | Winmedals (Kaggle username), Incident Event Log Dataset, Kaggle, accessed 2025. |

### ⚠️ Dataset License Notice

**Before running the ingest script with redistribution in mind, confirm the license on the Kaggle page.**
The `data/raw/` directory is excluded from the repository via `.gitignore`.
The ingest script (`scripts/ingest_kaggle.py`) reads the CSV locally and stores a transformed representation in Hindsight Cloud – it does not redistribute the raw data.

### Column Mapping

The script auto-detects columns using fuzzy matching. Below is the expected mapping:

| Logical Field | Typical CSV Column(s) |
|---|---|
| Incident ID | `number`, `Incident Number` |
| Opened At | `opened_at` |
| Resolved At | `resolved_at` |
| Category | `category` |
| Subcategory | `subcategory` |
| Symptom / Description | `short_description`, `symptom` |
| Priority | `priority`, `urgency`, `impact` |
| Assignment Group | `assignment_group` |
| Resolved By | `resolved_by` |
| Closure Code | `close_code` |
| Service / CI | `cmdb_ci`, `configuration_item` |

### Field Origin Disclosure

| Field | Source | Note |
|---|---|---|
| Incident ID, timestamps | `source="kaggle"` | Original values, unchanged |
| Category, subcategory | `source="kaggle"` | Original values |
| Service / CI | `source="kaggle"` | Original values |
| Priority / severity | `source="kaggle"` | Mapped from original codes |
| Resolver name | `source="kaggle"` | Original values |
| Closure code | `source="kaggle"` | Original values |
| **error_messages** | `source="synthetic_enrichment"` | **LLM-generated** – grounded in real category/service/closure code but NOT from the original data |
| **root_cause** | `source="synthetic_enrichment"` | **LLM-generated** |
| **resolution_steps** | `source="synthetic_enrichment"` | **LLM-generated** |
| **prevention_notes** | `source="synthetic_enrichment"` | **LLM-generated** |
| **fix_style** | `source="synthetic_enrichment"` | **LLM-generated** |

**Synthetic enrichment fields are clearly marked in memory metadata (`source="synthetic_enrichment"`).**
They are illustrative only and should never be presented as real incident history.

---

## 2. Curated Demo Dataset

| Field | Value |
|---|---|
| **File** | `data/curated_incidents.json` |
| **Source** | Hand-authored by the Recall project for demonstration purposes |
| **License** | MIT (part of this project) |

The curated dataset contains:
- 4 "Connection timeout on DB write" incidents (demo storyline)
- 3 precursor pattern demonstrations (config change → incident)
- Examples of failed fixes and quick-patch vs proper-fix patterns
- Realistic service names, named engineers, and believable timelines

**These are entirely fictional.** Service names (`auth-service`, `payments-api`, `checkout-worker`, `search-indexer`) and engineer names are invented for demonstration purposes. Any resemblance to real systems or people is coincidental.

All curated fields are marked `source="curated_demo"` in memory metadata.

---

## 3. Summary

| Source | Records | Origin |
|---|---|---|
| Kaggle (original fields) | ~40–60 | Real ITSM event log data (columns as-is) |
| Kaggle (enriched fields) | ~40–60 | LLM-generated, grounded in real metadata |
| Curated demo | 11 incidents + 4 change events | Hand-authored for demonstration |
