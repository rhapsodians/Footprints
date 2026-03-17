# 02 — Architecture

> **Audit status:** Verified against live repo structure and file contents.

## Repository Structure (Actual)

```
Footprints/                      # Repository root
│
├── server.py                    # Flask app: all routes, helpers, LSEG parser (752 lines)
├── engine.py                    # Signal computation pipeline — no Flask imports (722 lines)
├── db.py                        # All SQLite I/O — no Flask, no business logic (678 lines)
├── config.py                    # All constants, weights, thresholds, sector labels (180 lines)
├── wsgi.py                      # PythonAnywhere WSGI entry point
├── start_footprints.sh          # Shell script: local dev startup
├── requirements.txt             # Pinned dependencies (4 packages)
├── .gitignore
│
├── templates/                   # Jinja2 HTML templates
│   ├── home.html                # Route: /
│   ├── entry.html               # Route: /entry
│   ├── dashboard.html           # Route: /dashboard
│   ├── heatmap.html             # Route: /heatmap
│   ├── summary.html             # Route: /summary
│   ├── history.html             # Route: /history
│   ├── etf_history.html         # Route: /history/etf/<ticker>
│   ├── guide.html               # Route: /guide
│   └── admin.html               # Route: /admin
│
├── scripts/                     # Utility / maintenance scripts
│
├── archive/                     # v1 code and artefacts
│
└── ReadMes/                     # Legacy readme files
```

> **Note:** There is no `logic/` subdirectory, no `data/` folder in the repo, no `static/css/style.css` or `static/js/filters.js` committed to the public repo. The SQLite database `footprints.db` is created at runtime by `db.init_schema()` and is gitignored (contains real price data).

---

## Module Responsibilities

### `server.py` — Flask Application (Routes + Helpers)

The sole Flask file. Contains:

- Flask app instantiation and `secret_key` setup
- All route handlers (`@app.route`)
- Jinja2 helper functions registered via `app.jinja_env.globals`
- LSEG Excel parser (`_parse_lseg()`)
- Dashboard data enrichment (`_enrich_signals()`) — bridges v2 engine field names to v1-compatible display names used in templates
- Pension narrative generator (`_proxy_narrative()`) — generates plain-English signal summaries for each proxy ETF on the Summary page
- Excel template generator for weekly data entry (`export_template()`)
- Context builder helper (`_ctx()`) — assembles the standard template context dict

**Import pattern:** `server.py` imports `config`, `db`, `engine` directly. It never reaches into `engine.py` internals — it only calls `engine.run_engine()`.

### `engine.py` — Signal Computation Pipeline

Pure computation — no Flask, no DB calls. Accepts DataFrames, returns lists of dicts.

**Public API:** `run_engine(prices_df, etf_meta_df, existing_signals_df) → (signal_rows, change_log_rows)`

10-step pipeline (each step is a private function):
1. `_resample_weekly()` — daily OHLCV → weekly bars (Friday close)
2. `_per_ticker_features()` — MA20, MA100, pressure, turnover, volatility, trend score
3. `_compute_rs()` — relative strength vs benchmark (raw and vol-adjusted)
4. `_latest_eligible()` — reduce to latest row per ticker; filter active/non-suspended; attach sector
5. `_winsorize()` — clip extreme values at 2nd/98th percentile
6. `_cross_sectional_ranks()` — percentile rank within universe for key metrics
7. `_sector_breadth()` — sector-level aggregate stats and confirmation flags
8. `_compute_scores()` — confidence score (0–100) and rotation score (0–100) per ETF
9. `_classify_all()` — signal label + reason string per ETF
10. `_serialise()` → `_detect_changes()` — output dicts for DB write; change log

### `db.py` — Database Layer

All SQLite interaction. No analytics, no Flask imports. Uses `contextlib.contextmanager` for connection lifecycle with automatic commit/rollback.

**Key functions:**

| Function | Returns | Notes |
|----------|---------|-------|
| `init_schema()` | None | Creates all tables; runs additive column migrations; safe to re-run |
| `get_prices_df()` | DataFrame | All prices, sorted ticker/date |
| `get_etf_meta()` | DataFrame | All ETFs including suspended; `benchmark_ticker` filled from BASE_TICKER if NULL |
| `get_signals_df(as_of_date)` | DataFrame | Latest v2 signals, or signals for a specific date |
| `get_available_dates()` | list[str] | Dates with v2 signals, descending |
| `get_price_series_bulk()` | dict | Price series for multiple tickers in one query; used for sparklines |
| `get_pension_maps()` | (fund_map, etf_map) | fund_map: {id→{code,name,tickers}}; etf_map: {ticker→[fund_ids]} |
| `upsert_signals()` | int | INSERT OR REPLACE into signals table |
| `import_lseg_rows()` | (inserted, replaced) | Bulk upsert from LSEG export |
| `get_prev_signals()` | dict[str,str] | Previous signal per ticker for transition badge display |

### `config.py` — Central Configuration

All tunable parameters. **No logic.** Engine and server import directly from this module.

Key constants (confirmed values from code):

| Constant | Value | Description |
|----------|-------|-------------|
| `BASE_TICKER` | `"VWRP.L"` | Default RS benchmark |
| `MODEL_VERSION` | `"weekly_v2_0"` | Written to every signal row |
| `WINDOW_SHORT` | 4 | Weeks — RS short lookback |
| `WINDOW_MED` | 12 | Weeks — RS medium lookback |
| `WINDOW_LONG` | 20 | Weeks — RS long, pressure, vol, avg turnover |
| `WINDOW_MA20` | 20 | Weeks — moving average short |
| `WINDOW_MA100` | 100 | Weeks — moving average long |
| `WINDOW_TURN` | 100 | Weeks — turnover normalisation base |
| `PRESSURE_LAG` | 5 | Weeks — lookback for pressure_prev |
| `SPARKLINE_WEEKS` | 520 | Daily rows sent to dashboard (≈2 years) |
| `LIQUIDITY_FULL` | £5,000,000 | Weekly turnover at which liquidity confidence component = 1.0 |
| `WINSOR_LOWER` | 0.02 | 2nd percentile winsorisation floor |
| `WINSOR_UPPER` | 0.98 | 98th percentile winsorisation ceiling |

---

## Database Schema (SQLite — `footprints.db`)

### `prices` table

```sql
CREATE TABLE prices (
    date    TEXT NOT NULL,
    ticker  TEXT NOT NULL,
    open    REAL,
    high    REAL,
    low     REAL,
    close   REAL,
    volume  REAL,
    source  TEXT DEFAULT "LSEG",
    PRIMARY KEY (date, ticker)
)
```

- Date format: ISO 8601 string (`YYYY-MM-DD`)
- Prices in GBP (engine comment: "prices already in GBP — no pence conversion required")
- `source` field: currently always `"LSEG"` but schema-agnostic
- Index: `idx_prices_ticker_date_desc` on `(ticker, date DESC)` for fast bulk price queries

### `etf_meta` table

```sql
CREATE TABLE etf_meta (
    ticker           TEXT PRIMARY KEY,
    name             TEXT,
    sector           TEXT,
    active           INTEGER DEFAULT 1,
    display_order    INTEGER DEFAULT 99,
    suspended        INTEGER NOT NULL DEFAULT 0,
    benchmark_ticker TEXT    -- defaults to VWRP.L if NULL
)
```

- `active=0` excludes from signal generation and UI
- `suspended=1` excludes from signal generation but retains in admin view
- `display_order` controls sort order in all views
- `benchmark_ticker` per-ETF RS benchmark override; `db.py` fills NULL with `BASE_TICKER` on read

### `signals` table

```sql
CREATE TABLE signals (
    date    TEXT NOT NULL,
    ticker  TEXT NOT NULL,
    PRIMARY KEY (date, ticker)
    -- + 50+ columns added via ALTER TABLE migration in init_schema()
)
```

All signal columns are added by `_migrate_columns()` in `init_schema()` using `ALTER TABLE ADD COLUMN IF NOT EXISTS` pattern. See `db._SIGNALS_COLUMNS` for the full list of 50+ fields. Key fields:

| Field | Type | Description |
|-------|------|-------------|
| `signal` | TEXT | STRONG BUY / ACCUMULATING/HOLD / EARLY ACCUMULATION / NEUTRAL / EXIT/DISTRIBUTION |
| `signal_model_version` | TEXT | Always `"weekly_v2_0"` for v2 rows |
| `signal_reason` | TEXT | Human-readable explanation string |
| `rotation_score` | REAL | 0–100; weighted composite of percentile ranks |
| `confidence_score` | REAL | 0–100; liquidity/history/stability/sector/completeness |
| `confidence_bucket` | TEXT | HIGH / MODERATE / LOW |
| `trend_score_raw` | REAL | 0–4 integer (cast to float); see engine Step 2 |
| `rs20_raw` | REAL | 20-week excess return vs benchmark (decimal, e.g. 0.08 = +8%) |
| `pressure_20w` | REAL | 20-week cumulative CLV×turnover |
| `turnover_ratio_20_100` | REAL | avg_turn_20w / avg_turn_100w |

### `signal_log` table

```sql
CREATE TABLE signal_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    date           TEXT NOT NULL,
    ticker         TEXT NOT NULL,
    prev_signal    TEXT,
    new_signal     TEXT,
    rotation_score REAL,
    confidence_score REAL,
    logged_at      TEXT DEFAULT (datetime('now'))
)
```

Append-only. Written by `db.log_signal_changes()`. Used in the History page.

### `pension_funds` table

```sql
CREATE TABLE pension_funds (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT UNIQUE,   -- e.g. "LG001", "IL002"
    name           TEXT,
    display_order  INTEGER DEFAULT 99
)
```

Provider is inferred from `code` prefix: `LG` = L&G WorkSave, `IL` = Irish Life.

### `pension_etf_map` table

```sql
CREATE TABLE pension_etf_map (
    fund_id  INTEGER REFERENCES pension_funds(id),
    ticker   TEXT,
    PRIMARY KEY (fund_id, ticker)
)
```

Many-to-many: one fund can have multiple proxy ETFs; one ETF can map to multiple funds.

---

## Deployment

### PythonAnywhere

- **WSGI entry:** `wsgi.py` (imports `server.app`)
- **Reload:** Manual via PythonAnywhere Web tab "Reload" button after `git pull`
- **Environment variable:** `FP2_SECRET_KEY` must be set in PythonAnywhere's environment variables panel

### Local Development

```bash
git clone https://github.com/rhapsodians/Footprints.git
cd Footprints
pip install -r requirements.txt
python server.py          # or: bash start_footprints.sh
# → http://localhost:5000
```

On first run, `db.init_schema()` is called from `server.py __main__` block, creating `footprints.db`.

### Deployment Workflow

```bash
# Local: commit and push
git add .
git commit -m "Weekly update YYYY-MM-DD"
git push origin main

# PythonAnywhere Bash console:
cd ~/Footprints
git pull origin main
# Then click Reload in the Web tab, or use the PA API
```

---

## Requirements (Confirmed from `requirements.txt`)

```
flask>=3.0.0
numpy>=1.26.0
pandas>=2.1.0
openpyxl>=3.1.0
```

`sqlite3` is Python standard library — no separate install required.
