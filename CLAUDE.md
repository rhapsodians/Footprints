# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

Footprints v2 is a personal quantitative investment signal dashboard — a Flask web app tracking momentum, trend health, and rotation signals across a curated ETF universe (56 ETFs, 25 sectors). It also maps pension funds (L&G WorkSave, Irish Life) to ETF proxies and runs the same signal engine across them.

## Running Locally

```bash
pip install -r requirements.txt
python server.py          # → http://localhost:5000
# or
bash start_footprints.sh
```

`footprints.db` (SQLite, gitignored) is created automatically on first run via `db.init_schema()`. No test suite or linter config exists.

## Deployment (PythonAnywhere)

```bash
git push origin main
# Then on PythonAnywhere: git pull + click "Reload" in Web tab
```

Entry point for PythonAnywhere is `wsgi.py` (`from server import app as application`).

## Architecture

```
Request → server.py (Flask routes) → engine.py (computation) → db.py (SQLite)
```

**`config.py`** — Zero logic, all constants. Single source of truth for windows (4/12/20/100 weeks), thresholds, weights, the 25 sector codes, and `MODEL_VERSION = "weekly_v2_0"`. **Changing `MODEL_VERSION` without updating query strings causes all signals to disappear.**

**`engine.py`** — Pure Python/pandas, no Flask imports. Public API: `run_engine(prices_df, etf_meta_df, existing_signals_df) → (signal_rows, change_log_rows)`. 10-step cross-sectional pipeline: resample weekly → per-ticker features → RS → eligible filter → winsorize → percentile ranks → sector breadth → scores → classify → serialise/detect changes.

**`db.py`** — All SQLite via stdlib `sqlite3`. Key functions: `init_schema()`, `get_prices_df()`, `get_etf_meta()`, `get_signals_df(as_of_date)`, `upsert_signals()`, `import_lseg_rows()`. ⚠️ `init_schema()` does NOT create `pension_funds` or `pension_etf_map` tables — a fresh deploy will 500 on the heatmap/summary unless these are seeded manually.

**`server.py`** — 21 routes (8 page views, 8 admin POSTs, 2 JSON APIs, 3 utility). Contains `_parse_lseg()` for bulk LSEG Excel import and `_enrich_signals()` for dashboard enrichment. No business logic — delegates to engine/db.

## Key Design Constraints

- **All signals are cross-sectional** — rotation score changes if peers move, not just the ETF itself. The question is "what's the best opportunity *now*", not "has this crossed a fixed threshold".
- **Daily storage, weekly computation** — prices stored daily; engine always resamples to weekly Friday close before computing.
- **`VWRP.L` must be in universe with price data** — it's the default RS benchmark (`BASE_TICKER`). Per-ETF override via `etf_meta.benchmark_ticker`.
- **Data minimums**: `MIN_OBS_FULL=120` weekly bars for full model, `MIN_OBS_RS=21` for any signals, `MIN_OBS_TURNOVER=100` for turnover normalization.
- **LSEG is the sole data source** — `_parse_lseg()` expects a specific Excel column layout (`Exchange Date` header). Any alternative source needs its own parser.

## Database Schema Summary

- **`prices`**: `(date TEXT, ticker TEXT) PK` + OHLCV + source. Dates as `YYYY-MM-DD`. Prices in GBP (not pence).
- **`etf_meta`**: `ticker PK`, name, sector, active, display_order, suspended, benchmark_ticker. `active=0` excludes from signals; `suspended=1` keeps in Admin but excludes from signals.
- **`signals`**: `(date, ticker) PK` + 50+ columns added via `ALTER TABLE ADD COLUMN IF NOT EXISTS`. Always has `signal_model_version = "weekly_v2_0"`.
- **`signal_log`**: append-only change log written by `log_signal_changes()`.
- **`pension_funds`** / **`pension_etf_map`**: many-to-many fund↔ETF mapping. Fund `code` prefix (`LG` / `IL`) identifies provider.

## Documentation

Full documentation in `/docs/` (11 Markdown files). Key references:
- `docs/04_SIGNAL_LOGIC.md` — all KPI formulas with ranges and examples
- `docs/03_DATA_MODEL.md` — full ETF universe and signal field definitions
- `docs/08_DECISIONS_LOG.md` — why design choices were made
- `docs/10_REPRODUCTION_GUIDE.md` — step-by-step rebuild from zero including pension table seeding
