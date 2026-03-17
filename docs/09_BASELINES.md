# 09 — Baselines & Known-Good States

> **Audit status:** Rewritten against actual repo. Prior version contained baselines for features that don't exist (CSV storage, `app.py`, RSI). The v2.0 baseline below reflects what the code actually does.

---

## How Baselines Work in This Repo

There are currently **no git tags** in the repository (14 commits, none tagged). This means restoration to a specific state requires identifying the correct commit hash manually.

**Immediate recommended action:**
```bash
# On your local machine or PythonAnywhere:
git log --oneline   # identify the current working commit hash
git tag v2.0.0 <hash> -m "First stable baseline — post audit March 2026"
git push origin v2.0.0
```

Once tagged, restoration is: `git checkout v2.0.0`

---

## Baseline: v1.0 — Single Script (Archived)

**Status:** Archived in `archive/` folder in the repo.

**State:**
- Single Python script, Pandas HTML output
- No Flask, no web deployment
- MA20/MA100 crossover and simple momentum signals
- BUY / HOLD / SELL labels
- No pension proxy logic
- No database — CSV data files

**How to run from archive:**
- Locate the v1 script in `archive/`
- Run locally: `python <script_name>.py`
- No PythonAnywhere deployment needed or possible

**No restoration path to production.** v1 is purely archival.

---

## Baseline: v2.0.0 — Current Stable (as of March 2026 Audit)

**Date documented:** March 2026  
**Git status:** 14 commits on `main`; no tags yet  
**Recommended tag:** `v2.0.0`

### What is Confirmed Working

| Component | State |
|-----------|-------|
| `server.py` | All routes functional (Home, Entry, Dashboard, Heatmap, Summary, History, ETF History, Guide, Admin) |
| `engine.py` | Full 10-step pipeline; STRONG BUY / ACCUMULATING/HOLD / EARLY ACCUMULATION / NEUTRAL / EXIT/DISTRIBUTION |
| `db.py` | Schema creation + migration; all read/write functions |
| `config.py` | All constants, weights, thresholds defined |
| `wsgi.py` | PythonAnywhere WSGI entry |
| LSEG import | `_parse_lseg()` + `entry_import_lseg()` route |
| Template export | `export_template()` → `.xlsx` download |
| Template import | `import_template()` → prefill redirect |
| Signal recompute | Auto-trigger on data save; manual via `/recompute` |
| Pension summary | Two providers (LG, IL); stance logic; proxy narrative |
| Admin management | Add/remove ETFs, funds, proxies; gap fill; toggle active/suspended |
| API endpoints | `/api/prices/<ticker>` and `/api/signals` |

### Known State at This Baseline

- **DB file:** `footprints.db` — not in repo; must be populated separately
- **No git tags:** See above — tag immediately
- **`requirements.txt`:** Uses `>=` pins — exact versions in the live environment are unrecorded
- **Secret key:** `FP2_SECRET_KEY` env var must be set on PythonAnywhere

### Files at This Baseline

```
server.py          752 lines
engine.py          722 lines
db.py              678 lines
config.py          180 lines
wsgi.py            (short)
requirements.txt   4 lines
start_footprints.sh
templates/         9 HTML templates
scripts/           utility scripts
archive/           v1 artefacts
ReadMes/           legacy docs
```

### How to Restore / Verify

```bash
# If tagged:
git checkout v2.0.0

# If not tagged yet, on PythonAnywhere:
cd ~/Footprints
git log --oneline     # note the current HEAD hash
# Confirm server.py is 752 lines, engine.py is 722 lines

# Verify the app starts:
python server.py
# Should print: "Footprints v2.0 — http://localhost:5000"
# (db.init_schema() runs automatically on __main__ start)
```

---

## Live Data Snapshot (March 2026)

Extracted from `footprints.db` for reference. Confirms the state of the database at the time of documentation.

| Metric | Value |
|--------|-------|
| Total ETFs in `etf_meta` | 43 |
| Active ETFs | 43 (all active=1, suspended=0) |
| Total price rows | 18,737 daily OHLCV rows |
| Price date range | 2024-03-01 → 2026-03-13 |
| Pension funds | 20 (15 LG, 5 IL) |
| Pension ETF mappings | 20 |
| Total signal rows | 1,828 |
| Latest signal date | 2026-03-13 |
| Signal log entries | 77 |

**Latest signal distribution (2026-03-13):**

| Signal | Count |
|--------|-------|
| NEUTRAL | 27 |
| EXIT/DISTRIBUTION | 7 |
| STRONG BUY | 5 |
| ACCUMULATING/HOLD | 4 |
| EARLY ACCUMULATION | 0 |

**ETFs with shortest price history (confidence risk):**

| Ticker | Daily rows | Weekly bars (approx) | Notes |
|--------|-----------|---------------------|-------|
| AINF.L | 271 | ~13 | Below MIN_OBS_FULL; LOW confidence |
| DFND.L | 224 | ~10 | Below MIN_OBS_FULL; LOW confidence |
| DBXWD1.L | 126 | ~25 | Above MIN_OBS_RS; MODERATE confidence |
| IDWP.L | 126 | ~25 | Above MIN_OBS_RS; MODERATE confidence |
| IS15.L | 126 | ~25 | Above MIN_OBS_RS; MODERATE confidence |
| LGAG.L | 126 | ~25 | Above MIN_OBS_RS; MODERATE confidence |
| MAGG.L | 126 | ~25 | Above MIN_OBS_RS; MODERATE confidence |
| RIUS.L | 126 | ~25 | Above MIN_OBS_RS; MODERATE confidence |
| SWDA.L | 126 | ~25 | Above MIN_OBS_RS; MODERATE confidence |

---

## Baseline Maintenance Protocol

Going forward, tag every significant change:

```bash
# Pattern:
git tag v2.X.Y -m "Short description of what changed"
git push origin v2.X.Y
```

### Recommended Tag Cadence

| Trigger | Example |
|---------|---------|
| New page added | `/portfolio` page → `v2.1.0` |
| New signal class added | Fifth signal type → `v2.2.0` |
| Engine weight changes | Rotation weight tuning → `v2.1.1` |
| Schema migration | New DB column → `v2.1.2` |
| Bug fix affecting signals | Pressure calculation fix → `v2.0.1` |
| Documentation-only change | No tag needed |

### What to Record for Each Baseline

When adding an entry to this document for a new baseline:

1. Date and tag name
2. Line counts for the four main Python files (quick sanity check)
3. `MODEL_VERSION` value in `config.py` — if this changes, it's a major baseline
4. Any open issues at the time of tagging
5. Key config values that differ from prior baseline (new weights, thresholds, etc.)

---

## Future Baseline Candidates

| Feature / Change | Likely Tag | Notes |
|-----------------|-----------|-------|
| Exact `pip freeze` recorded and committed | `v2.0.0` or `v2.0.1` | Should be done immediately |
| `seed_db.py` development dataset added | `v2.0.1` | Enables clean-room testing |
| Automated data fetch (if PythonAnywhere tier upgraded) | `v2.1.0` | Major workflow change |
| New page: Portfolio tracker | `v2.1.0` | Tracks current pension allocation vs recommended |
| Signal history chart on ETF history page | `v2.0.2` | UI enhancement |
