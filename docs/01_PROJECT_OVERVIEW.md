# 01 — Project Overview

> **Audit status:** Verified against live code. All corrected from prior version.

## Vision

Footprints is a personal quantitative investment signal dashboard that tracks momentum, trend health, and rotation signals across a curated ETF universe. The name reflects the core philosophy: **follow the footprints of institutional and smart money** by reading price action and volume signals rather than reacting to news.

Two purposes:
1. **Sector / macro ETF monitoring** — identify which parts of the market have accumulation, momentum, and trend characteristics worth acting on.
2. **Pension fund proxy tracking** — since retail pension platforms (L&G WorkSave, Irish Life) don't offer real-time pricing or technical tools, each internal fund is mapped to a liquid ETF proxy and the same signal engine is run across them.

---

## Goals

- Weekly signal generation requiring minimal manual input (~15 minutes per cycle)
- Systematic, rules-based rotation — emotion removed from pension switching decisions
- Transparent KPI logic: every number traceable to a formula in `engine.py` and a threshold in `config.py`
- Multi-page web dashboard readable on desktop and mobile
- Deployable for near-zero cost on PythonAnywhere

---

## Version History

### v1.0 (Archived)

- Single Python script, Pandas-driven HTML output, local only
- Signals: basic MA crossover (MA20 vs MA100), simple momentum
- No web deployment, no pension proxy logic
- **Location in repo:** `archive/` folder
- **Status:** Superseded. No active maintenance.

### v2.0 (Active)

**Model version string:** `"weekly_v2_0"` — written to every signal row in SQLite; used to filter out any legacy v1 rows that may exist in a migrated database.

The v2 engine is a **complete architectural rewrite**, not an incremental change:

| Dimension | v1 | v2 |
|-----------|----|----|
| Entry point | Single script | `server.py` (Flask) |
| Business logic | Inline | Separated: `engine.py`, `db.py`, `config.py` |
| Data store | CSV files | SQLite — `footprints.db` |
| Price cadence | Weekly CSV | **Daily** OHLCV in DB; engine resamples to weekly internally |
| Data source | Manual / Yahoo Finance | **LSEG Excel exports** via `_parse_lseg()` in `server.py` |
| Signal model | MA crossover + momentum | 10-step cross-sectional pipeline |
| Signal labels | BUY / HOLD / SELL | STRONG BUY / ACCUMULATING/HOLD / EARLY ACCUMULATION / NEUTRAL / EXIT/DISTRIBUTION |
| Core KPIs | MA20, MA100, RSI, mom | RS (raw + vol-adj), Pressure (CLV), Trend Score (0–4), Rotation Score (0–100), Confidence (0–100) |
| Benchmark | None | VWRP.L default; per-ETF override via `etf_meta.benchmark_ticker` |
| Pension model | Not present | DB-driven; two providers (LG, IL) via `pension_funds` + `pension_etf_map` tables |
| Pages | Signal table | Home, Entry, Dashboard, Heatmap, Summary, History, ETF History, Guide, Admin |

---

## Technology Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Web framework | Flask ≥ 3.0 | Entry point: `server.py` |
| Signal engine | Pure Python + pandas/numpy | `engine.py` — no Flask imports |
| Database | SQLite (via `sqlite3` stdlib) | `db.py` — no ORM |
| Excel I/O | `openpyxl` ≥ 3.1 | LSEG import + weekly entry template export |
| Data manipulation | `pandas` ≥ 2.1 | Resampling, rolling calculations |
| Numerics | `numpy` ≥ 1.26 | Vectorised operations in engine |
| WSGI | `wsgi.py` | PythonAnywhere WSGI config points here |
| Startup | `start_footprints.sh` | Shell script for local dev startup |

---

## Key Design Decisions and Constraints

**Cross-sectional scoring.** All signals are relative. Rotation score, confidence score, and percentile ranks are computed across the live universe on each run date. An ETF's signal can change without its own metrics changing, simply because peers have moved around it. This is by design — the system is asking "what is the best opportunity *now* given what else is available", not "has this ETF crossed a fixed threshold".

**Daily storage, weekly signals.** Prices are stored daily to support sparklines and ETF history charts without re-importing. The engine always resamples to weekly bars (Friday close) before computing any signal metrics. Weekly bars are never stored directly.

**LSEG as sole data source.** All price data enters via LSEG Excel exports. The parser (`_parse_lseg()`) expects an `Exchange Date` header row in a specific column layout. Any alternative data source would require a new parser function; the DB schema is source-agnostic (the `source` field in `prices` accepts any string).

**No authentication.** The app has no login system. Access is by URL obscurity. Do not deploy with sensitive portfolio data visible to the open internet.

**Secret key management.** `app.secret_key` is set from `FP2_SECRET_KEY` environment variable. The hardcoded fallback `"fp2-dev-secret-change-in-production"` must **never** be used in production.

**Two pension providers.** The `summary.py` route in `server.py` splits pension funds by `code` prefix: `LG` (L&G WorkSave) and `IL` (Irish Life). Both use the same underlying `pension_funds` and `pension_etf_map` tables. Adding a third provider requires only a new code prefix — no schema changes needed.

**Model version gating.** The string `"weekly_v2_0"` is used in all signal queries in `db.py`. Changing `MODEL_VERSION` in `config.py` without updating these query strings will cause all signals to disappear from the UI. Treat `MODEL_VERSION` as a migration key.
