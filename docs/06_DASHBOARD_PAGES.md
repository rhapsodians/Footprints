# 06 — Dashboard Pages & Routes

> **Audit status:** All routes verified from `server.py`. Template names confirmed. Pre-audit doc had wrong route names and missing pages.

## Full Route Map

| URL | Function | Template | Nav label |
|-----|----------|----------|-----------|
| `/` | `index()` | `home.html` | home |
| `/entry` GET | `entry()` | `entry.html` | entry |
| `/entry` POST | `entry_post()` | (redirect) | — |
| `/entry/export-template` | `export_template()` | (xlsx download) | — |
| `/entry/import-lseg` POST | `entry_import_lseg()` | (redirect) | — |
| `/entry/import-template` POST | `import_template()` | (redirect) | — |
| `/recompute` POST | `recompute()` | (redirect) | — |
| `/dashboard` | `dashboard()` | `dashboard.html` | dashboard |
| `/heatmap` | `heatmap()` | `heatmap.html` | heatmap |
| `/summary` | `summary()` | `summary.html` | summary |
| `/history` | `history()` | `history.html` | history |
| `/history/etf/<ticker>` | `etf_history()` | `etf_history.html` | — |
| `/guide` | `guide()` | `guide.html` | guide |
| `/admin` | `admin()` | `admin.html` | admin |
| `/admin/add_etf` POST | `admin_add_etf()` | (redirect) | — |
| `/admin/toggle-etf` POST | `admin_toggle_etf()` | (redirect) | — |
| `/admin/import-gap` POST | `admin_import_gap()` | (redirect) | — |
| `/admin/add-fund` POST | `admin_add_fund()` | (redirect) | — |
| `/admin/remove-fund` POST | `admin_remove_fund()` | (redirect) | — |
| `/admin/add-proxy` POST | `admin_add_proxy()` | (redirect) | — |
| `/admin/remove-proxy` POST | `admin_remove_proxy()` | (redirect) | — |
| `/api/prices/<ticker>` | `api_prices()` | (JSON) | — |
| `/api/signals` | `api_signals()` | (JSON) | — |

---

## Standard Template Context

Every page receives a standard context dict from `_ctx(nav, as_of)`:

```python
{
    "active_nav":     nav,              # e.g. "dashboard" — for nav highlighting
    "as_of_date":     as_of,            # ISO date string
    "sector_labels":  config.SECTOR_LABEL,  # {code: display_name}
    "sectors":        config.SECTORS,   # sorted list of sector codes
    "sig_css":        config.SIGNAL_CSS, # {signal: css_class}
    "model_version":  config.MODEL_VERSION,
    "base_ticker":    config.BASE_TICKER,
}
```

The `_heat_class(v)` Jinja2 global function is also registered, used for heatmap cell colouring:

```python
def _heat_class(v):
    # v is interpreted as a percentile 0–100
    if v >= 75: return "heat-h"
    if v >= 55: return "heat-mh"
    if v >= 40: return "heat-m"
    if v >= 20: return "heat-ml"
    return "heat-l"
```

---

## Page: Home (`/`)

**Purpose:** Landing page showing portfolio-level summary statistics.

**Data:** `db.get_signals_df()` + `db.get_latest_prices()` — signal counts by type.

**Context extras:**
```python
sig_counts      # dict of {signal_label: count} across all ETFs
n_active        # total active ETF count
as_of           # date of latest signals
```

**Note:** The home page shows aggregate stats, not the full ETF table. Navigate to `/dashboard` for the per-ETF signal table.

---

## Page: Data Entry (`/entry`)

**Purpose:** Weekly OHLCV data input. The primary data ingestion UI.

Three input methods:

### 1. Manual row entry
Form with one row per active ETF. Fields: Open, High, Low, Close (★ mandatory), Volume. Prefill from `?prefill=` JSON query parameter (used by template import redirect).

### 2. LSEG Excel file import (per-ticker)
Upload a single-ticker LSEG export. `_parse_lseg()` locates the `Exchange Date` header row, maps columns, and bulk-inserts via `db.import_lseg_rows()`.

### 3. Weekly entry template (all tickers at once)
- **Export template:** GET `/entry/export-template` → downloads an `.xlsx` file pre-populated with all active ETFs, prev-close prices, and styled with sector separators. Filename: `footprints_entry_{YYYY-MM-DD}.xlsx`
- **Import template:** POST `/entry/import-template` → reads the completed template, validates, redirects back to entry form with `prefill=` JSON parameter

After saving rows, the signal engine is automatically re-run (`engine.run_engine()`). Any signal changes are flashed to the user.

**LSEG Parser (`_parse_lseg()`):**
- Scans rows until it finds a row where `row[0] == "Exchange Date"`
- Maps columns: `close`, `open`, `low`, `high`, `volume` by header name (case-insensitive, lowercased)
- Parses datetime objects (requires rows to have `datetime` type in column 0)
- Returns sorted list of `(date_str, open, high, low, close, volume)` tuples

---

## Page: Signal Dashboard (`/dashboard`)

**Purpose:** Per-ETF signal table with sparklines. Primary analysis view.

**URL parameter:** `?date=YYYY-MM-DD` — view signals for a historical date. Defaults to latest.

**Data flow:**
1. Load signals from DB for the requested date
2. Load price series (daily, up to `SPARKLINE_WEEKS=520` rows) for all tickers via `db.get_price_series_bulk()`
3. **Server-side weekly resampling** for MA lines: resample daily prices to weekly using ISO week bucketing, then compute `ma20` and `ma100` from weekly closes for sparkline overlay
4. `_enrich_signals()` — add v1-compatible display fields
5. `db.get_pension_maps()` — attach fund membership to each ETF row
6. `db.get_prev_signals()` — attach previous signal for transition badge

**JavaScript data:** The full enriched signal dict is serialised to `etf_data_js` (JSON) and embedded in the page. Fund map is serialised to `fund_map_js`. Client-side JavaScript handles filtering, sorting, and sparkline rendering.

**Stats block** (passed to template):
```python
stats = {
    "total":        len(signals),
    "strong_buy":   count of STRONG BUY,
    "accum":        count of ACCUMULATING/HOLD,
    "neutral":      count of NEUTRAL,
    "exit":         count of EXIT/DISTRIBUTION,
    "high_conf":    count of confidence_bucket == "HIGH",
    "avg_rotation": average rotation_score across all ETFs,
}
```

**Cache control:** Response has `Cache-Control: no-store` to prevent stale data on back navigation.

---

## Page: KPI Heatmap (`/heatmap`)

**Purpose:** Cross-ETF heatmap — rows = ETFs, colour intensity = relative strength of each KPI within the universe.

**URL parameter:** `?date=YYYY-MM-DD`

**Data flow:**
1. Load signals, enrich, attach pension fund memberships
2. Sort by sector then descending rotation score
3. Build `sector_stats` — one entry per sector showing breadth metrics
4. Serialise to `rows_js` (JSON) for client-side rendering
5. Heatmap cell colouring uses `_heat_class(v)` Jinja2 global — CSS classes `heat-h`, `heat-mh`, `heat-m`, `heat-ml`, `heat-l` must be defined in the template CSS

---

## Page: Pension Summary (`/summary`)

**Purpose:** Pension-oriented view showing each fund's stance and proxy ETF signals, split by provider.

**URL parameter:** `?date=YYYY-MM-DD`

**Data flow:**
1. Load signals, enrich
2. Load pension maps, attach fund membership to each ETF
3. Get previous signals for transition badges
4. Split fund_map into LG and IL by code prefix
5. Build fund rows via `_build_fund_rows()` — see `05_PENSION_PROXY_METHODOLOGY.md` for stance logic
6. Build "notable" list: non-pension ETFs with STRONG BUY, EARLY ACCUMULATION, or EXIT signals
7. Build portfolio-level counts

**Template receives:**
- `lg_rows` — L&G funds sorted by stance
- `il_rows` — Irish Life funds sorted by stance
- `notable` — non-pension notable signals
- `portfolio` — aggregate counts (strong_buy, early_acc, accum, neutral, exit, high_conf, transitions)

**Cache control:** `Cache-Control: no-store`

---

## Page: Signal History (`/history`)

**Purpose:** Log of signal changes over time. Shows when signals transitioned between states.

**Data:** `db.get_signal_history(limit=300)` — most recent 300 entries from `signal_log` table, joined with `etf_meta` for name/sector.

---

## Page: ETF History (`/history/etf/<ticker>`)

**Purpose:** Full price and signal history for a single ETF.

**Data:**
- `db.get_price_series(ticker, limit=PRICE_HISTORY_LIMIT)` — up to 520 daily price rows
- `db.get_ticker_signal_history(ticker)` — all signal changes for this ticker
- `etf_meta` — name and sector

**Template receives:** `prices_js` (JSON of price series) for chart rendering; `sig_hist` for signal change log table.

---

## Page: Admin (`/admin`)

**Purpose:** ETF universe and pension fund management. Data quality monitoring.

**Functions available:**
- Add new ETF (with optional LSEG file for immediate historical data import)
- Suspend / resume / exclude / include individual ETFs
- Fill data gaps: upload LSEG file for existing ETF
- Add / remove pension funds
- Add / remove ETF proxy mappings to funds
- View DB stats: total price rows, date range, signal row count

**ETF table shows:** ticker, name, sector, active status, suspended status, row count in prices table.

---

## Page: Guide (`/guide`)

Static informational page explaining how to use the dashboard. No dynamic data.

---

## API Endpoints

### `GET /api/prices/<ticker>`

Returns JSON:
```json
{
    "rows": [
        {"d": "2025-01-03", "o": 98.42, "h": 99.15, "l": 97.88, "c": 98.91, "v": 245000, "turnover": 24198950.0},
        ...
    ]
}
```
Turnover field added at serve time: `c * v`. Up to `PRICE_HISTORY_LIMIT=520` rows.

### `GET /api/signals`

Returns all current signals as JSON array of dicts. No date filtering — always returns latest.

---

## Next Friday Helper

`_next_friday()` is used to pre-populate the date field in the entry form:

```python
def _next_friday():
    d = date.today()
    days = (4 - d.weekday()) % 7   # 0 if today is Friday
    return (d + timedelta(days=days)).isoformat()
```

Returns today's date if today is Friday; otherwise the coming Friday.

---

## Client-Side Rendering — What the Templates Must Implement

> **Gap note for reproduction:** The HTML templates (`templates/*.html`) are not included in this documentation suite. They were not accessible during the audit. The information below is derived from what `server.py` passes to each template and must be used to reconstruct them if the template files are lost.

### JSON Data Blobs (Dashboard and Heatmap)

The dashboard and heatmap routes embed two JSON objects directly into the HTML:

```html
<!-- server.py passes these to the template -->
<script>
  const etfData   = {{ etf_data_js | safe }};   // dict: {ticker: signal_row_dict}
  const fundMap   = {{ fund_map_js | safe }};    // dict: {fund_id: {code, name, tickers[]}}
</script>
```

`etf_data_js` contains the fully enriched signal dict for every active ETF, keyed by ticker. Each value includes all signal fields plus:
- `weekly_closes` — array of weekly close prices (for sparklines)
- `weekly_ma20` — array of MA20 values (for sparkline overlay)
- `weekly_ma100` — array of MA100 values (for sparkline overlay)
- `weekly_dates` — array of ISO date strings
- `price_series` — raw daily prices (for ret20/ret3m calculations)
- `funds` — list of fund IDs this ETF belongs to

### Sparklines

Sparklines are rendered client-side using the `weekly_closes`, `weekly_ma20`, and `weekly_ma100` arrays. The specific library or SVG approach is not confirmed from the Python code alone. The template must:
- Iterate each ETF row
- Draw a mini line chart of `weekly_closes` (last N weeks)
- Optionally overlay MA20 and MA100 lines
- Colour the price line green if `close > ma20`, red if below

### Heatmap Cell Colouring

The `_heat_class(v)` function is registered as a Jinja2 global and used in `heatmap.html`:

```
v >= 75  → class "heat-h"   (strong positive)
v >= 55  → class "heat-mh"  (moderate-high positive)
v >= 40  → class "heat-m"   (neutral)
v >= 20  → class "heat-ml"  (moderate-low negative)
v < 20   → class "heat-l"   (strong negative)
```

The CSS must define these five classes with appropriate colour gradients (e.g. dark green → white → dark red, or similar).

### Signal CSS Classes

`config.SIGNAL_CSS` maps each signal label to a CSS class name:

```python
SIGNAL_CSS = {
    "STRONG BUY":         "green",
    "ACCUMULATING/HOLD":  "green",
    "EARLY ACCUMULATION": "yellow",
    "NEUTRAL":            "neutral",
    "EXIT/DISTRIBUTION":  "red",
}
```

The template uses `{{ sig_css[row.signal] }}` to apply the class. The CSS must define `.green`, `.yellow`, `.neutral`, `.red` signal badge/pill styles.

### Filter and Sort (Dashboard)

The dashboard passes `etf_data_js` to JavaScript. The JS layer must implement:
- Filter by signal type (checkboxes or toggle buttons)
- Filter by sector (dropdown)
- Sort by any column (rotation_score, rs20_pct, pressure_20w, trend, etc.)
- Show/hide rows without page reload

The implementation approach (vanilla JS table filtering, or a library) is not confirmed from `server.py` alone and should be documented or inspected from the actual `dashboard.html`.

### Pension Fund Filter

The `fund_map_js` blob enables a "show only ETFs in fund X" filter. Each ETF row has a `funds` array of fund IDs; the filter shows rows where `funds.includes(selectedFundId)`.

### Historical Date Selector

Both `/dashboard` and `/summary` accept `?date=YYYY-MM-DD`. The templates receive a `dates` list (all available signal dates, descending) and must render a `<select>` dropdown that navigates to `?date=<selected>` on change.
