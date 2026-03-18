# 06 — Dashboard Pages & Routes

> **Audit status:** Fully verified against all 8 committed templates (zip upload) and the live PythonAnywhere `server.py` (uploaded directly). Key finding: the live `server.py` (627 lines) differs from GitHub (752 lines) — the `/summary` route was removed and merged into `/heatmap`.

---

## Design System (from `base.html`)

All pages extend `base.html`. The following is established at the base level and available everywhere.

### Fonts
- **Monospace:** IBM Plex Mono (300, 400, 500, 600 weights + italic) — used for all data, labels, KPIs, nav
- **Sans:** IBM Plex Sans (300, 400, 500 weights) — used for page titles, card titles, descriptions

### Theme System
Two themes via CSS custom properties on `html[data-theme]`. Toggle persists to `localStorage` under key `fp2_theme`. Default: `dark`.

**Dark theme key colours:**
```css
--bg:       #080a0d      /* page background */
--surface:  #0e1117      /* card / table background */
--surface2: #141820      /* hover / input background */
--border:   #1e2635      /* dividers */
--text:     #c4cdd8      /* primary text */
--text2:    #5e7080      /* secondary text */
--text3:    #38475a      /* muted / labels */
--accent:   #4a9eff      /* interactive / active */
--green:    #00d4a0      /* positive / bullish */
--yellow:   #f0c040      /* caution / early */
--red:      #ff4060      /* negative / bearish */
```

**Signal colour palette (CSS variables, used by both CSS and JS):**
```css
--sig-sb:    #00d4a0   /* STRONG BUY — green */
--sig-ea:    #f0c040   /* EARLY ACCUMULATION — yellow */
--sig-ah:    #4a9eff   /* ACCUMULATING/HOLD — blue */
--sig-nt:    #5e7080   /* NEUTRAL — grey */
--sig-ex:    #ff4060   /* EXIT/DISTRIBUTION — red */
/* Each has -bg (translucent fill) and -bd (border) variants */
```

### Navigation Bar
Sticky top nav (44px height). Contains:
- Brand: `FOOTPRINTS · [page name]` — links to `/`
- Nav links: Home | Entry | Dashboard | Heatmap | History | Guide | Admin
- Right side: `as of [date]` metadata + `◑ THEME` toggle button
- Active page highlighted with `class="active"` → `color: var(--accent); background: var(--blue-dim)`

### Score Bar Component
`.score-bar-fill[data-score="N"]` — JS in base.html auto-colours on load:
- ≥ 70 → green, ≥ 45 → blue, < 45 → red

---

## Full Route Map

| URL | Function | Template | Nav |
|-----|----------|----------|-----|
| `/` | `index()` | `home.html` | home |
| `/entry` GET | `entry()` | `entry.html` | entry |
| `/entry` POST | `entry_post()` | redirect | — |
| `/entry/export-template` | `export_template()` | xlsx download | — |
| `/entry/import-lseg` POST | `entry_import_lseg()` | redirect | — |
| `/entry/import-template` POST | `import_template()` | redirect | — |
| `/recompute` POST | `recompute()` | redirect | — |
| `/dashboard` | `dashboard()` | `dashboard.html` | dashboard |
| `/heatmap` | `heatmap()` | `heatmap.html` | heatmap |
| `/history` | `history()` | `history.html` | history |
| `/history/etf/<ticker>` | `etf_history()` | `etf_history.html` | — |
| `/guide` | `guide()` | `guide.html` | guide |
| `/admin` | `admin()` | `admin.html` | admin |
| `/admin/add_etf` POST | `admin_add_etf()` | redirect | — |
| `/admin/toggle-etf` POST | `admin_toggle_etf()` | redirect | — |
| `/admin/import-gap` POST | `admin_import_gap()` | redirect | — |
| `/admin/add-fund` POST | `admin_add_fund()` | redirect | — |
| `/admin/remove-fund` POST | `admin_remove_fund()` | redirect | — |
| `/admin/add-proxy` POST | `admin_add_proxy()` | redirect | — |
| `/admin/remove-proxy` POST | `admin_remove_proxy()` | redirect | — |
| `/admin/set-sector` POST | `admin_set_sector()` | redirect | — |
| `/api/prices/<ticker>` | `api_prices()` | JSON | — |
| `/api/signals` | `api_signals()` | JSON | — |

> **Live vs GitHub divergence:** The live `server.py` has no `/summary` route. The pension summary functionality was merged into `/heatmap`. The GitHub repo `server.py` is 125 lines longer and still has the old `/summary` route — it should be updated with the live version.

---

## Page: Home (`/`) — `home.html`

Two-column layout (1fr + 268px sidebar). On mobile (≤860px) stacks to single column.

**Left column — Navigation Cards (2-column grid):**

| Card | Colour | Destination | Description shown |
|------|--------|-------------|-------------------|
| Entry Form | Blue | `/entry` | Enter weekly OHLCV data from LSEG Workspace |
| Dashboard | Green | `/dashboard` | Signal cards with sparklines and detail panel |
| Heatmap | Green | `/heatmap` | KPI heatmap · weekly fund summary · sector overview — all in one |
| History | Neutral | `/history` | Signal change log and database coverage |
| KPI Guide | Neutral | `/guide` | Plain-English guide to every signal and metric |
| Admin | Neutral | `/admin` | Add or exclude ETFs, import LSEG history |

**Right sidebar — Signal Summary Panel:**

Displays count of each signal type with colour coding. Iterates `sig_counts` dict passed from server. Signals with count = 0 are hidden. At the bottom: a `Recompute Signals` button (POST to `/recompute`).

**Hero section:**
- Title: "Institutional **Footprints**"
- Subtitle: "Weekly ETF rotation engine · L&G Pension Fund Universe"
- Tag: `[model_version] · as of [as_of]`

---

## Page: Dashboard (`/dashboard`) — `dashboard.html` (829 lines)

**URL parameter:** `?date=YYYY-MM-DD` for historical view. `?open=TICKER` to auto-open a specific ETF's detail panel on load.

**External dependency:** `Chart.js 4.4.1` loaded from `cdnjs.cloudflare.com`. Used for sparklines and the detail panel price chart.

**JS globals from server:**
```javascript
const D   = {{ etf_data_js|safe }};    // {ticker: enriched_signal_dict}
const PF  = {{ fund_map_js|safe }};    // {fund_id: {code, name, tickers[]}}
const SL  = {{ sector_labels|tojson }}; // {sector_code: display_label}
```

### Signal Filter Chips Bar (`.sum-bar`)

Five signal chips at the top: STRONG BUY | EARLY ACC | ACCUMULATING | NEUTRAL | EXIT/DIST | ALL. Each shows a live count. Clicking filters the card grid to that signal type via `filt(sig)`. Counts update via `counts()`.

### Filter / Sort Control Band (`.hm-controls-dash`)

Three rows, built to mirror the heatmap control band pattern:

**Row 1 — Pension Fund filter** (`#fund-bar`, hidden until populated by JS): Chips auto-built from `PF` dict. Format: `"LG-GLOB-DEV (1)"`. Clicking calls `filtFund(fid, btn)`.

**Row 2 — Sector filter** (`#sector-bar`, hidden until populated by JS): Chips auto-built from sectors present in data, in a fixed display order (`BASE → UK → US → NAM → EUR → JAP → APAC → EM → GLOBAL → TECH → HEALTH → DEF → PROP → COMM → MINING → BOND → OTHER`). Format: `"Technology (5)"`.

**Row 3 — Sort buttons**: SIGNAL (default) | TICKER A–Z | ROTATION | RS20% | DV SURPRISE | TREND | SIZE

### ETF Card Grid (`.grid`)

Cards are built client-side via `buildCards()`. Each card (`div.etf-card`) has:
- **Left border** 3px coloured by signal: green (SB/EA/AH), grey (NT), red (EX)
- **Header row**: ticker (bold), ETF name, fund code tags, sector tag, signal badge with prev signal strikethrough if changed
- **Metric grid** (6 cells, 3-column): CLOSE | RS20% | TREND (4 dots) | TURN RATIO | PRESSURE 20W (spans 2) | AVG TURN/WK + latest + ratio badge (spans 2)
- **Sparkline**: `<canvas width="270" height="56">` drawn via `spark()` using Chart.js
- **Click**: calls `openD(ticker)` to open the detail panel

**Sparkline rendering (`spark()`):** Uses `weekly_closes`, `weekly_ma20`, `weekly_ma100` from the server-side weekly resampling. Drawn with Chart.js line chart — price line coloured by signal, MA20 in `#5b8cf5` (blue), MA100 in `#f5c842` (yellow).

**Card metric hover tooltips:** Each metric cell has `onmouseenter="showKpi(event, key, val, ticker)"`. The `kpiCtx()` function generates contextual interpretations just like the heatmap tooltip system.

### Detail Slide Panel (`div.dp`)

Opens on card click (or `?open=TICKER`). Slides in from the right. Contains:
- ETF ticker + name header
- **Chart canvas** (`#dc`) — Chart.js price chart (weekly, with MA20 + MA100 overlays). Expand button opens full-screen chart (`#fs-ov`) with the same data.
- **Metric grid** (`#dmet`): rotation score, confidence, trend 4 conditions, RS20%, pressure, turnover, sector breadth confirmation
- **Signal conditions** (`#dcond`): shows which of the 4/5 signal conditions pass/fail for current signal
- **Price levels** (`#dlev`): close, MA20, MA100, % distance from each
- **Signal reason** text from `signal_reason` field

### Price History Modal (`#hist-ov`)

Triggered from detail panel. Fetches `/api/prices/<ticker>` and renders a sortable table of all daily OHLCV rows with columns: DATE | OPEN | HIGH | LOW | CLOSE | VOLUME | TURNOVER. Click column headers to sort. Shows row count.

### KPI Definitions in Dashboard

The `KPI` object in `dashboard.html` defines display metadata and contextual interpretations for:

| Key | Title |
|-----|-------|
| `close` | CLOSE PRICE |
| `trend` | TREND HEALTH |
| `dvs` | TURNOVER RATIO (20W/100W) — aliased from `dv_surprise` |
| `crdp` | PRESSURE 20W — aliased from `crdp20` |
| `rotation` | ROTATION SCORE |
| `rs20` | RS20% — RELATIVE STRENGTH |
| `ret20` | 20-WEEK RETURN |
| `ret3m` | 3-MONTH RETURN |
| `ma20` | PRICE vs MA20 |
| `ma100` | PRICE vs MA100 |
| `turn` | AVG WEEKLY TURNOVER |
| `sig_sb/ea/ah/nt/ex` | Signal definitions (shown in KPI popover) |

---

## Page: KPI Heatmap (`/heatmap`) — `heatmap.html` ⚠️ MAJOR CHANGES

The heatmap has been substantially rewritten. The prior documentation was largely incorrect. This section documents the actual current state.

### Layout Structure

```
[Page Header + Date Selector]
[Filter Band — 3 rows: Signal | Provider | Legend]
[Section Header: ETF TABLE (with count)]
[ETF Heatmap Table — 18 columns]
[Section Header: SECTOR OVERVIEW]
[Sector Tile Grid]
[Floating Tooltip (injected into body)]
```

### Data Passed to Template

```python
signals      # list of enriched signal dicts (Jinja iteration)
rows_js      # JSON string of same data — consumed by JS as const DATA
fund_map_js  # JSON: {fund_id: {code, name, tickers[]}}
sector_stats # list of sector aggregate dicts (sorted by sector_score desc)
# Also from _ctx(): sector_labels (SL in JS), sectors
```

### Filter Band (3 rows)

**Row 1 — Signal filter** (`#hm-score-chips`):
Chips: ALL | [N] STRONG BUY | [N] ACCUM | [N] NEUTRAL | [N] EXIT | [N] CHANGES

Counts shown live inside chips. "CHANGES" filters to ETFs where `prev_signal` is set (signal changed this week).

JS function: `scoreFilt(sig, el)` — sets `activeScoreSig`, updates chip `.on` state, calls `render()`.

**Row 2 — Provider filter** (`#hm-prov-chips`):
Chips: ALL | L&G (blue tinted) | Irish Life (green tinted) | Notable (no pension fund)

JS function: `provFilt(prov, el)` — sets `activeProvider` to `'ALL'`/`'LG'`/`'IL'`/`'NO'`.

**Row 3 — Legend:**
Five swatches with labels: Strong + | Mild + | Neutral | Mild − | Strong −

### ETF Heatmap Table — 18 Columns

| # | Column Header | Sort key | Data field | Colour logic |
|---|--------------|----------|------------|-------------|
| 1 | PROVIDER | `provider` | Fund code prefix | Pill: L&G=blue, Irish Life=green, Notable=grey |
| 2 | PENSION FUND | `fund` | Fund code chips | Fund code tags from `TICKER_FUND` lookup |
| 3 | TICKER | `ticker` | `e.ticker` | Link `↗ TICKER` → `/dashboard?open=TICKER` |
| 4 | ETF NAME | `name` | `e.name` | Text, truncated with ellipsis; `min-width:220px; max-width:260px` |
| 5 | SECTOR | `sector` | `SL[e.sector]` | Text label from sector_labels map |
| 6 | SIGNAL | `signal` | `e.signal` | Signal pill class `.s-SB/.s-EA/.s-AH/.s-NT/.s-EX`; shows prev signal with strikethrough if changed |
| 7 | ROTATION | `rotation` | `e.rotation_score` | `rotCls()` → hi-5 to lo-4 |
| 8 | CONF | `confidence` | `e.confidence_bucket` | `confCls()` → hi-3/hi-1/lo-2 |
| 9 | TREND | `trend` | `trend_score_raw` | 4 coloured dots only (green/grey); score text removed |
| 10 | RS20 V-ADJ | `rs20va` | `rs20_vol_adj_rank_pct` | `pctCls()` percentile colouring |
| 11 | RS ACCEL | `rsaccel` | `rs_accel_vol_adj_rank_pct` | `pctCls()` |
| 12 | RS20% | `rs20raw` | `rs20_raw` (×100 for display) | `ic()` symmetric ±thresholds [0.5,2,5,10,15]% |
| 13 | PRESSURE 20W | `pressure` | `pressure_20w` | `ic()` thresholds [1e4,5e5,2e6,1e7,5e7] |
| 14 | PRESS WKS% | `ppw` | `pressure_pos_weeks_pct` | `ic()` centred at 50% |
| 15 | TURN RATIO | `turnover` | `turnover_ratio_20_100` | `ic()` centred at 1.0 |
| 16 | TURN Z | `turnz` | `turnover_z_20` | `ic()` z-score bands |
| 17 | AVG TURN /wk | `size` | `avg_turn_20w` | `lqCls()` — liquidity grade; `/wk` in header not cell |
| 18 | LATEST TURN /wk | `latest` | `turn_latest` | `lqCls()` + ratio badge inline with value on same line; `/wk` in header not cell; sortable |

### Colour Class System

**Directional (hi/lo):** `ic(value, thresholds)` — symmetric bipolar scale:
```
hi-5  green 55% opacity   (≥ threshold[4])
hi-4  green 38%
hi-3  green 22%
hi-2  green 12%
hi-1  green 6%
hi-0  surface (neutral)
lo-1  red 6%
lo-2  red 12%
lo-3  red 22%
lo-4  red 38%
lo-5  red 55%           (≤ -threshold[4])
```

**Percentile (pct):** `pctCls(v)` — for rank fields (0–100):
```
hi-5  ≥ 80
hi-3  ≥ 65
hi-1  ≥ 50
hi-0  ≥ 35
lo-2  ≥ 20
lo-4  < 20
```

**Liquidity (lq):** `lqCls(v)` — for turnover amounts:
```
lq-5  ≥ £500M/wk   ultra-liquid
lq-4  ≥ £50M/wk    very liquid
lq-3  ≥ £5M/wk     institutional grade
lq-2  ≥ £1M/wk     moderate
lq-1  ≥ £250K/wk   lower
lq-0  < £250K/wk   low — treat with caution
```

**Heatmap note:** The prior documentation described `_heat_class()` with classes `heat-h`, `heat-mh`, `heat-m`, `heat-ml`, `heat-l`. These are **not used in the current heatmap template**. The current template uses the `hi-*/lo-*/lq-*` system described above. `_heat_class()` remains registered in Jinja globals but is not called by the current heatmap.

### Tooltip System (KPI Tooltips)

A floating tooltip `div#ktt` is injected into `document.body` (bypassing stacking context issues). Each heatmap cell has `onmouseenter="showHmTip(event, key, val, ticker)"` / `onmouseleave="hideKtt()"`.

**Tooltip content is dynamically generated** by `hmCtx(key, val)` — for every KPI it produces:
- A contextual interpretation string (`t`) based on the actual value
- A colour classification (`c`): `'pos'` / `'neg'` / `'neu'` / `'warn'`

Tooltip also shows `HM_KPI[key].def` — a plain-English definition of the metric. These definitions are embedded in the template JS and match the financial rationale in `07_FINANCIAL_RATIONALE.md`.

**KPI definitions embedded in template:**

| Key | Definition text |
|-----|----------------|
| `signal` | Composite signal from all KPI groups. Driven by rotation score, trend, pressure, RS. |
| `rotation` | Weighted composite 0–100: 18% trend, 22% vol-adj RS20, 15% RS accel rank, 15% turnover rank, 15% pressure rank, 10% pressure positive weeks%, 5% sector confirmation. |
| `conf` | Signal reliability 0–100: 30% liquidity (vs £5M/wk), 20% history depth (vs 100w), 15% turnover stability, 20% sector confirmation, 15% data completeness. HIGH≥75, MODERATE 50–74, LOW<50. |
| `trend` | Score 0–4: (1) Close>MA20 (2) Close>MA100 (3) MA20>MA100 (4) MA100 now > MA100 20w ago. |
| `rs20va` | (20w ETF return minus VWRP.L return) ÷ 20w realised volatility, cross-sectionally ranked 0–100pct. |
| `rsaccel` | (RS4 raw − RS12 raw) ÷ vol_20w, ranked 0–100pct. Measures whether outperformance is accelerating. |
| `rs20raw` | ETF 20w return minus VWRP.L 20w return. Positive = outperforming the global market. |
| `pressure` | Sum of (CLV × £turnover) over 20 weeks. CLV = ((close−low)−(high−close))/(high−low). |
| `ppw` | % of the last 20 weeks where signed pressure was positive. |
| `turnratio` | 20w average £ turnover ÷ 100w average £ turnover. Above 1.0 = participation expanding. |
| `turnz` | (Latest week £ volume − 100w mean) ÷ 100w std dev. Winsorised at 2nd/98th pct. |
| `turn` | Mean £ value traded per week over last 20 weeks. ≥£5M/wk = institutional grade. |

### Sorting

All 18 columns are sortable. Click header → sort by that column; click again → reverse. Active sort column highlighted with `.active` class. Sort function: `doSort(key, btn)` → sets `curSort`, flips `sortDir`, calls `render()`.

Sort keys: `provider`, `fund`, `ticker`, `name`, `sector`, `signal`, `rotation`, `confidence`, `trend`, `rs20va`, `rsaccel`, `rs20raw`, `pressure`, `ppw`, `turnover`, `turnz`, `size` (AVG TURN), `latest` (LATEST TURN).

Default sort: `signal` (by `SO` signal order dict: SB=0, EA=1, AH=2, NT=3, EX=4), then by `rotation_score` descending within each signal group.

### Client-Side Filtering and Rendering

All filtering and row generation is done client-side in JavaScript. `render()` function:
1. Gets sorted data from `getSorted()`
2. Applies sector filter (`activeSector`)
3. Applies provider filter (`activeProvider`)
4. Applies signal filter (`activeScoreSig`)
5. Generates HTML via `mkRow(e)` for each ETF
6. Injects into `tbody#hb`
7. Updates count in `#etf-section-count`
8. Updates scorecard counts in chip badges

### Sector Overview (below ETF table)

A grid of clickable sector tiles. Clicking a tile filters the ETF table to that sector (click again to clear). Toggle between "ALL ETFs" and "PENSION PROXIES" views.

**Each sector tile shows:**
- Sector name + average rotation score (colour coded by `_rotCl()`)
- A coloured left border (4px) indicating sector strength (srot-0 to srot-5)
- A signal distribution bar (proportional bar for SB/EA/AH/NT/EX)
- List of ETFs in sector, sorted by rotation score descending, each showing:
  - Ticker + name
  - Fund code tags (if mapped to any pension fund)
  - 4px left stripe coloured by signal type

**View toggle:**
- ALL ETFs — shows all ETFs in each sector tile
- PENSION PROXIES — shows only ETFs mapped to at least one pension fund

---

## Pension Summary — Merged into `/heatmap`

> **The `/summary` route no longer exists in the live server.** The pension fund summary (fund stances, LG/IL rows, notable signals, portfolio counts) was merged into the `/heatmap` route. `heatmap.html` receives and renders all of it.

The live `/heatmap` route passes to `heatmap.html`:
```python
# Standard heatmap data:
signals, sector_stats, fund_map_js, rows_js, dates

# Pension summary data (merged from former /summary route):
lg_rows      # L&G fund list with stance + proxy signals
il_rows      # Irish Life fund list
notable      # non-pension ETFs with STRONG BUY/EA/EXIT signals
portfolio    # {total, strong_buy, early_acc, accum, neutral, exit, high_conf, transitions}
sig_strong_buy, sig_early_accum, sig_accum, sig_exit  # signal label constants
```

See `05_PENSION_PROXY_METHODOLOGY.md` for the pension stance logic (`_build_fund_rows`, `_stance`).

---

## Page: Signal History (`/history`) — `history.html` (88 lines)

Simple server-rendered table. No client-side JS filtering. Columns:

| Column | Source field |
|--------|-------------|
| Date | `row.date` |
| Ticker | `row.ticker` |
| Name | `row.name` |
| Sector | `sector_labels[row.sector]` |
| From | `row.old_signal` — coloured with `sig_css` |
| → | separator |
| To | `row.new_signal` — coloured with `sig_css` |
| Rotation | `row.rotation_score` (1 dp) |
| Confidence | `row.confidence_score` (0 dp) |
| Logged | `row.logged_at[:16]` (datetime truncated to minute) |

Empty state message: "No signal transitions recorded yet."

---

## Page: KPI Guide (`/guide`) — `guide.html` (415 lines)

Two-column layout: sticky sidebar nav (left) + scrollable main content (right).

**Sidebar links** to sections:
- The Signal (output)
- Signal Logic Reference (exact conditions table)
- Rotation Score
- Confidence Score
- Trend Score (KPI 1)
- Pressure 20W (KPI 2)
- Vol-Adj RS (KPI 4)
- Turnover Block (KPI 5)

**Signal Logic Reference table** (priority order as implemented, confirmed from guide):

| Priority | Signal | Conditions |
|----------|--------|-----------|
| 1 | EARLY ACCUMULATION | pressure_prev_20w ≤ 0 AND pressure_20w > 0 AND rs_accel_raw > 0 AND rs4_raw > 0 AND turnover_z_20 > 0 AND close < MA100 |
| 2 | STRONG BUY | rotation_score ≥ 72 AND trend_score_raw ≥ 3 AND pressure_20w > 0 AND rs20_raw > 0 AND confidence_score ≥ 50 |
| 3 | ACCUMULATING/HOLD | rotation_score ≥ 60 AND trend_score_raw ≥ 3 AND pressure_20w > 0 AND rs20_raw > 0 |
| 4 | EXIT/DISTRIBUTION | rotation_score < 35 AND trend_score_raw ≤ 2 AND pressure_20w < 0 AND rs20_raw < 0 |
| 5 | NEUTRAL | None of the above |

Each KPI section includes: definition, formula, interpretation scale, and plain-English explanation.

---

## Page: Admin (`/admin`) — `admin.html` (493 lines)

Two-section layout:

### Section 1 — ETF Universe

Two-column: Add ETF form (left) + ETF tile grid (right).

**Add ETF form** (POST `/admin/add_etf`): Ticker, Name, Sector (dropdown from `config.SECTOR_LABEL`), Display Order, Benchmark Ticker (defaults to VWRP.L), optional LSEG file upload for immediate history import.

**ETF tile grid**: One tile per ETF showing ticker, name, row count in prices table, status dot (active=green, suspended=yellow, inactive=grey). Action buttons per tile:

| Action | Route | Condition shown |
|--------|-------|----------------|
| Unsuspend | POST `/admin/unsuspend` | If suspended |
| Suspend | POST `/admin/suspend` | If active and not suspended |
| Deactivate | POST `/admin/deactivate` | If active and not suspended |
| Activate | POST `/admin/activate` | If not active |

> **Route confirmed from live server.py:** The live server uses `/admin/toggle-etf` with an `action` parameter (`suspend`/`resume`/`exclude`/`include`). The `admin.html` template uses `/admin/suspend`, `/admin/unsuspend`, `/admin/deactivate`, `/admin/activate` as individual routes — these **do not exist** in the live server. This means the admin suspend/activate buttons are currently broken (will 404). The template needs updating to use the `toggle-etf` route with the correct `action` value, OR new individual routes need to be added to `server.py`.

**DB stats panel**: Shows price_rows, date_min, date_max, signal_rows, model_version.

**Gap fill**: Upload LSEG file for an existing ticker to fill price history gaps. POST `/admin/import-gap`.

### Section 2 — Pension Funds

Two-column: Add Fund form (left) + Fund tile grid (right).

**Add Fund form** (POST `/admin/add-fund`): Code, Name.

**Fund tile grid**: One tile per fund showing code, name, and proxy ETF chips. Each proxy chip is a button — clicking it submits a remove-proxy form (POST `/admin/remove-proxy`). Add proxy via dropdown of active ETFs + hidden fund_id input (POST `/admin/add-proxy`). Delete fund button with JS `confirm()` prompt (POST `/admin/remove-fund`).

---

## Page: ETF History (`/history/etf/<ticker>`) — `etf_history.html`

> Not in the uploaded zip. Documented from `server.py` route.

Receives: `ticker`, `name`, `sector`, `prices` (reversed list), `sig_hist`, `prices_js` (JSON for chart).

Shows a price chart and a signal change log table for a single ETF.

---

## API Endpoints

### `GET /api/prices/<ticker>`
Returns JSON `{"rows": [...]}` where each row: `{d, o, h, l, c, v, turnover}`. Up to `PRICE_HISTORY_LIMIT=520` daily rows. Used by dashboard detail panel for the price history modal and chart.

### `GET /api/signals`
Returns all current signals as JSON array. No date filtering — always returns latest.

---

## Template Commit Status

| Template | In GitHub repo | Notes |
|----------|---------------|-------|
| `base.html` | ✅ | Fully documented — design system, nav, theme |
| `home.html` | ✅ | Fully documented — nav cards, signal summary |
| `heatmap.html` | ✅ | Fully documented — 18-col table, sector grid, tooltips |
| `dashboard.html` | ✅ | Fully documented — card grid, detail panel, Chart.js |
| `entry.html` | ✅ | Documented — 3-method import bar, manual form |
| `history.html` | ✅ | Fully documented — simple server-rendered table |
| `guide.html` | ✅ | Documented — KPI guide with signal logic table |
| `admin.html` | ✅ | Documented — ETF tiles, fund tiles, route discrepancy noted |
| `summary.html` | ❌ | **Does not exist** — `/summary` route removed; pension summary merged into `/heatmap` |
| `etf_history.html` | ❓ | Not in uploaded zip — confirm whether still needed |

**Action required — sync GitHub with live:**
```bash
# On PythonAnywhere:
cd ~/footprints2
# Copy live server.py to repo (it has the merged heatmap/summary route)
# Then commit:
git add server.py templates/
git commit -m "server: merge summary into heatmap route; update templates"
git push origin main
```
