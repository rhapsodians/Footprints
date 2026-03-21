# Footprints — Project Knowledge Base

> **Audit status:** All documents verified against live code (server.py, engine.py, db.py, config.py) from https://github.com/rhapsodians/Footprints as of March 2026.  
> Documents supersede the pre-audit versions written from memory. Where code is the authority, code wins.

---

## Document Map

| File | Contents |
|------|----------|
| `01_PROJECT_OVERVIEW.md` | Vision, goals, version history, key architectural decisions |
| `02_ARCHITECTURE.md` | File layout, module responsibilities, deployment, DB schema |
| `03_DATA_MODEL.md` | ETF universe structure, OHLCV schema, signal fields, pension DB tables |
| `04_SIGNAL_LOGIC.md` | All KPI computations as actually implemented in engine.py |
| `05_PENSION_PROXY_METHODOLOGY.md` | Pension fund mapping, DB structure, two-provider model, Summary page logic |
| `06_DASHBOARD_PAGES.md` | All pages (Home, Entry, Dashboard, Heatmap, Summary, History, Admin, Guide) |
| `07_FINANCIAL_RATIONALE.md` | "Follow the instructional money" thesis — why these KPIs, what they reveal |
| `08_DECISIONS_LOG.md` | Chronological log of design decisions, assumptions, rejected alternatives |
| `09_BASELINES.md` | Known-good states and restoration instructions |
| `10_REPRODUCTION_GUIDE.md` | Step-by-step rebuild from zero, including DB seeding and deployment |

---

## Quick Reference — Actual State

| Item | Actual Value (from code) |
|------|--------------------------|
| Active version | **v2.0** (`MODEL_VERSION = "weekly_v2_0"`) |
| Main Flask file | `server.py` (not `app.py`) |
| Signal engine | `engine.py` |
| Database layer | `db.py` → SQLite file `footprints.db` |
| Configuration | `config.py` |
| WSGI entry | `wsgi.py` |
| Startup script | `start_footprints.sh` |
| Data store | **SQLite** (not CSV) |
| Price data cadence | **Daily** OHLCV stored; resampled to weekly inside engine |
| Data source | **LSEG Excel exports** (not Yahoo Finance) |
| Benchmark | `VWRP.L` (default); per-ETF override via `etf_meta.benchmark_ticker` |
| Signal labels | STRONG BUY / ACCUMULATING/HOLD / EARLY ACCUMULATION / NEUTRAL / EXIT/DISTRIBUTION |
| Pension providers | LG (L&G WorkSave) and IL (Irish Life) |
| Key dependency | `openpyxl` (LSEG import/export) — not documented in prior versions |
| ETF universe | 55 active ETFs across 25 sector codes |
| Pension funds | 19 (14 L&G WorkSave + 5 Irish Life) |
| Pages | Home, Entry, Dashboard, Heatmap, History, ETF History, Guide, Admin, Universe |
| Secret key | `FP2_SECRET_KEY` env var; fallback for dev only |

---

## Critical Corrections vs Prior Documentation

The following were **wrong** in the pre-audit documentation and are now corrected:

1. **Flask entry point is `server.py`**, not `app.py`
2. **Data is stored in SQLite** (`footprints.db`), not CSV files
3. **Prices are daily**, not weekly — the engine resamples internally
4. **No RSI** in v2 signal engine — replaced by CLV-based Pressure and vol-adjusted RS
5. **Signal labels are not BUY/HOLD/SELL** — they are STRONG BUY / ACCUMULATING/HOLD / EARLY ACCUMULATION / NEUTRAL / EXIT/DISTRIBUTION
6. **No `logic/` subdirectory** — all Python is in root-level files
7. **No `filters.js` or `style.css` in `/static/`** — these may exist but are not in the root; templates are in `/templates/`
8. **`openpyxl` is a required dependency** — not mentioned in prior docs
9. **Two pension providers** (LG + IL), not one
10. **Trend score is 0–4**, not a -7 to +7 composite
11. **AVG TURN rolling window is 20 weeks** (`WINDOW_LONG = 20`) for `avg_turn_20w`; 100 weeks for normalisation base
12. **There is no macro regime filter** — the system is purely quantitative/cross-sectional; no manual regime overlay exists in the current code

---

## How to Use This Documentation

1. **Reproducing the project** → `10_REPRODUCTION_GUIDE.md`
2. **Understanding a KPI formula** → `04_SIGNAL_LOGIC.md` (maths) + `07_FINANCIAL_RATIONALE.md` (why)
3. **Pension rotation decisions** → `05_PENSION_PROXY_METHODOLOGY.md`
4. **Why something was built a certain way** → `08_DECISIONS_LOG.md`
5. **Reverting to a prior version** → `09_BASELINES.md`
6. **Starting a new Claude conversation** → paste the context block from `10_REPRODUCTION_GUIDE.md`

---

## Remaining Gaps — Action Required

| Priority | Action | Where |
|----------|--------|-------|
| ✅ Done | ETF universe (55 ETFs) from live DB | `03_DATA_MODEL.md` Appendix A |
| ✅ Done | Pension fund + proxy mappings (20 funds) from live DB | `05_PENSION_PROXY_METHODOLOGY.md` Appendix B |
| ✅ Done | All templates fully documented | `06_DASHBOARD_PAGES.md` |
| ✅ Done | Signal priority order confirmed: SB(1)→AH(2)→EA(3)→EXIT(4)→NEUTRAL(5) | `04_SIGNAL_LOGIC.md` |
| ✅ Done | Admin route bug fixed (toggle-etf) | `08_DECISIONS_LOG.md` |
| ✅ Done | Git tag `v2.0.0` created | `09_BASELINES.md` |
| ✅ Done | Inline sector editor on Admin tiles | `06_DASHBOARD_PAGES.md`, `08_DECISIONS_LOG.md` |
| ✅ Done | Bulk LSEG import added; template import/export removed | `06_DASHBOARD_PAGES.md` |
| ✅ Done | Footprints logo in nav and home hero | `06_DASHBOARD_PAGES.md` |
| ✅ Done | Sector labels updated (Global Benchmark, Real Estate, Fixed Income, Global Thematic) | `03_DATA_MODEL.md`, `08_DECISIONS_LOG.md` |
| ✅ Done | Entry page redesign — upload-only, manual OHLCV table removed | `06_DASHBOARD_PAGES.md` |
| ✅ Done | Engine as_of_date param for targeted Friday recompute | `02_ARCHITECTURE.md`, `08_DECISIONS_LOG.md` |
| ✅ Done | Admin Delete ETF replaces Suspend/Exclude; toggle-etf route removed | `06_DASHBOARD_PAGES.md`, `08_DECISIONS_LOG.md` |
| ✅ Done | ETF universe expanded 43→55; 8 new sector codes (INDIA, CHINA, FIN, INDUS, UTILS, ENERGY, CONS, CASH) | `03_DATA_MODEL.md`, `08_DECISIONS_LOG.md` |
| ✅ Done | Universe page added (/universe) with ETF descriptions and factsheet links | `06_DASHBOARD_PAGES.md` |
| ✅ Done | admin/set-sector removed; sector changes via scripts/update_sectors.py | `08_DECISIONS_LOG.md` |
| ✅ Done | Pension fund count corrected 20→19; IL-INFLATIONBOND proxy changed to INXG.L | `05_PENSION_PROXY_METHODOLOGY.md` |
| ✅ Done | Utility scripts documented (backfill_signals, update_sectors, purge_v1_signals) | `10_REPRODUCTION_GUIDE.md` |
| ✅ Done | ETF universe expanded to 55 ETFs; 8 new sectors (INDIA, CHINA, FIN, INDUS, UTILS, ENERGY, CONS, CASH) | `03_DATA_MODEL.md`, `08_DECISIONS_LOG.md` |
| ✅ Done | Universe page added (/universe) with ETF descriptions and factsheet links | `06_DASHBOARD_PAGES.md` |
| ✅ Done | admin/set-sector removed; sector updates via update_sectors.py script | `08_DECISIONS_LOG.md` |
| ✅ Done | Scripts: backfill_signals.py, update_sectors.py, purge_v1_signals.py | `10_REPRODUCTION_GUIDE.md` |
| ✅ Done | Pension funds: 20→19 (LG-APAC-EXJP removed); IL-INFLATIONBOND proxy → INXG.L | `05_PENSION_PROXY_METHODOLOGY.md` |
| ✅ Done | Seed scripts updated for 55 ETFs + 19 pension funds | `10_REPRODUCTION_GUIDE.md` |
| 🟢 Low | Run `pip freeze > requirements_locked.txt` on PythonAnywhere and commit | repo root |
| 🔴 High | `pension_funds` + `pension_etf_map` not in `init_schema()` — fresh deploy will 500 | Add to `db.init_schema()`; workaround in `10_REPRODUCTION_GUIDE.md` |
| 🟢 Low | `footprints.db` backup strategy — gitignored so not version controlled | Consider periodic manual backup |
