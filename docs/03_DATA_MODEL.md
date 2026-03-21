# 03 — Data Model

> **Audit status:** Verified against db.py, config.py, and server.py. All corrected from prior version.

## Price Data

### Storage Format

All prices are stored as **daily** OHLCV rows in the `prices` SQLite table. There is no separate weekly price store — weekly bars are computed on-the-fly by `engine._resample_weekly()` at signal computation time.

```
date       | ticker  | open    | high    | low     | close   | volume   | source
-----------|---------|---------|---------|---------|---------|----------|-------
2025-01-03 | VWRP.L  | 98.42   | 99.15   | 97.88   | 98.91   | 245000   | LSEG
```

**Key conventions:**
- `date`: ISO 8601 string (`YYYY-MM-DD`), daily trading dates
- Prices are in **GBP**. The engine explicitly notes "prices already in GBP — no pence conversion required". All LSE ETFs using `.L` suffix tickers are expected to be priced in pounds, not pence.
- `volume`: daily volume
- `source`: string field, currently always `"LSEG"`

### Weekly Resampling (engine.py Step 1)

The engine groups by ticker and resamples using pandas `resample("W-FRI")`:
- `open` = first of week
- `high` = max of week
- `low` = min of week
- `close` = last of week (Friday close)
- `volume` = sum of week

Rows with no Friday close (e.g. market-closed weeks) are dropped via `dropna(subset=["close"])`.

### Data Minimum Requirements

| Requirement | Config constant | Value | Purpose |
|-------------|----------------|-------|---------|
| Minimum obs for signal | `MIN_OBS_RS` | 21 weekly bars | Minimum to compute 20-week RS |
| Full model eligibility | `MIN_OBS_FULL` | 120 weekly bars | Full confidence score |
| Turnover normalisation | `MIN_OBS_TURNOVER` | 100 weekly bars | Reliable 100-week turnover baseline |
| Volatility | `MIN_OBS_VOL` | 20 weekly bars | 20-week realized vol |

ETFs below `MIN_OBS_RS` are excluded from signal output by `_latest_eligible()`.

---

## ETF Universe

### Structure in Database

The ETF universe is managed entirely via the `etf_meta` table — there is no hardcoded list in the code. ETFs are added/removed via the Admin page or directly via `db.add_etf()`.

Each ETF has:

| Field | Description |
|-------|-------------|
| `ticker` | Exchange ticker (e.g. `VWRP.L`, `ISF.L`) — **must include `.L` suffix for LSEG-sourced LSE ETFs** |
| `name` | Full display name |
| `sector` | Sector code — must match a key in `config.SECTOR_LABEL` |
| `active` | 1 = included in signals; 0 = excluded |
| `suspended` | 1 = temporarily excluded (data gap); shown in Admin but not in signals |
| `display_order` | Integer; controls row order in all views |
| `benchmark_ticker` | RS benchmark override; defaults to `VWRP.L` if NULL |

### Sector Codes (from `config.SECTOR_LABEL`)

| Code | Display Label |
|------|--------------|
| `BASE` | Global Benchmark |
| `US` | United States |
| `NAM` | North America |
| `UK` | United Kingdom |
| `EUR` | Europe |
| `JAP` | Japan |
| `APAC` | Asia-Pacific |
| `EM` | Emerging Markets |
| `INDIA` | India |
| `CHINA` | China |
| `TECH` | Technology |
| `HEALTH` | Healthcare |
| `DEF` | Defence |
| `FIN` | Financials |
| `INDUS` | Industrials |
| `UTILS` | Utilities |
| `ENERGY` | Energy |
| `CONS` | Consumer |
| `PROP` | Real Estate |
| `COMM` | Commodities |
| `MINING` | Mining |
| `BOND` | Fixed Income |
| `CASH` | Cash & Money Market |
| `GLOBAL` | Global Thematic |
| `OTHER` | Other |

### Benchmark

All ETFs default to `VWRP.L` as their RS benchmark (set in `config.BASE_TICKER`). **`VWRP.L` must itself be present in the ETF universe** — it is used both as a signal instrument and as the benchmark series for RS calculations. If `VWRP.L` is missing from `prices`, all RS fields will be NULL for all ETFs using the default benchmark.

To assign a custom benchmark to a specific ETF, set `etf_meta.benchmark_ticker` to any ticker that also has price data in the `prices` table.

---

## Signal Fields

Signal fields are written to the `signals` table by `engine._serialise()` and read back by `db.get_signals_df()`. The full column list is defined in `db._SIGNALS_COLUMNS`. Key fields for understanding the system:

### Core Signal Fields

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `signal` | TEXT | See labels | Final classification |
| `signal_reason` | TEXT | — | Human-readable explanation, e.g. "High rotation score; strong vol-adj RS rank; positive 20w pressure" |
| `rotation_score` | REAL | 0–100 | Weighted sum of percentile ranks — primary sort field |
| `confidence_score` | REAL | 0–100 | Data quality / liquidity score |
| `confidence_bucket` | TEXT | HIGH/MODERATE/LOW | HIGH ≥ 75; MODERATE ≥ 50; LOW < 50 |

### Trend Fields

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `trend_score_raw` | REAL | 0–4 (int as float) | Sum of 4 binary conditions — see engine Step 2 |
| `trend_score_pct` | REAL | 0–100 | `trend_score_raw × 25` |
| `n_obs` | INTEGER | — | Weekly bar count for this ticker; used in confidence history component (`history = min(n_obs / 130, 1.0)`) |
| `close` | REAL | Price | Latest weekly close (GBP) |
| `ma20` | REAL | Price | 20-week SMA of close |
| `ma100` | REAL | Price | 100-week SMA of close |

### Relative Strength Fields

All RS values are **excess return** (ETF return minus benchmark return) over the period. Stored as decimals (0.08 = +8%).

| Field | Description |
|-------|-------------|
| `rs4_raw` | 4-week excess return |
| `rs12_raw` | 12-week excess return |
| `rs20_raw` | 20-week excess return |
| `rs_accel_raw` | RS acceleration: `rs4_raw - rs12_raw` |
| `rs4/12/20_vol_adj` | Vol-adjusted RS: `rs_raw / vol_20w` |
| `rs20_rank_pct` | Cross-sectional percentile rank of `rs20_raw` |
| `rs20_vol_adj_rank_pct` | Cross-sectional percentile rank of `rs20_vol_adj` |
| `rs_accel_vol_adj_rank_pct` | Cross-sectional percentile rank of `rs_accel_vol_adj` |

**Display note:** `server._enrich_signals()` converts `rs20_raw` (decimal) to `rs20_pct` (multiplied by 100) for template display.

### Pressure Fields

Pressure = CLV × daily volume turnover, accumulated over 20 weeks. CLV (Close Location Value) = `((close - low) - (high - close)) / (high - low)`. Ranges from -1 (close at low) to +1 (close at high).

| Field | Description |
|-------|-------------|
| `pressure_20w` | 20-week cumulative pressure (sum of CLV×DV) |
| `pressure_prev_20w` | Pressure 5 weeks ago (used for EARLY ACCUMULATION detection) |
| `pressure_ratio_20w` | Up pressure / down pressure over 20 weeks |
| `pressure_pos_weeks_pct` | % of the 20 weeks where weekly pressure was positive |
| `pressure_rank_pct` | Cross-sectional percentile rank of `pressure_20w` |

### Turnover Fields

| Field | Description |
|-------|-------------|
| `turn_latest` | Current week's turnover (close × volume) |
| `avg_turn_20w` | 20-week rolling average turnover |
| `avg_turn_100w` | 100-week rolling average turnover (normalisation base) |
| `turnover_ratio_20_100` | `avg_turn_20w / avg_turn_100w` — is recent activity above/below long-run norm? |
| `turnover_z_20` | Z-score of current week's turnover vs 100-week mean/std |
| `turn_cv20` | Coefficient of variation of turnover over 20 weeks (stability measure) |
| `turnover_rank_pct` | Cross-sectional percentile rank of `turnover_ratio_20_100` |

### Sector Fields

Attached to each ETF row from sector-level aggregation in engine Step 7.

| Field | Description |
|-------|-------------|
| `sector_score` | Weighted composite 0–100 for the sector |
| `sector_confirmed` | 1 if sector meets all three confirmation thresholds; 0 otherwise |
| `sector_pct_rs12_pos` | % of sector ETFs with positive 12-week RS |
| `sector_pct_above_ma100` | % of sector ETFs above MA100 |

---

## Pension Fund Tables

### `pension_funds`

Each row is a specific pension fund from a provider platform.

```sql
CREATE TABLE pension_funds (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT UNIQUE,        -- e.g. "LG-UKEQUITY", "IL-AMUNDI_GOLD"
    name           TEXT,               -- full fund name
    display_order  INTEGER DEFAULT 99  -- sort order in Admin UI
)
```

> ⚠️ **Note:** `pension_funds` and `pension_etf_map` are **not created by `db.init_schema()`**. They must be created manually or seeded via the Admin UI before pension features work. See `10_REPRODUCTION_GUIDE.md` for SQL seed scripts.

The `code` field identifies the provider:
- `LG` prefix → L&G WorkSave
- `IL` prefix → Irish Life

### `pension_etf_map`

Links pension funds to their ETF proxies. A fund can have multiple proxies; an ETF can be a proxy for multiple funds.

```sql
CREATE TABLE pension_etf_map (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id    INTEGER REFERENCES pension_funds(id),
    ticker     TEXT    -- ETF ticker from etf_meta
)
``` The signal for a pension fund is derived from the signals of all its mapped proxy ETFs in aggregate (see Summary page logic in `05_PENSION_PROXY_METHODOLOGY.md`).

---

## V1 Compatibility Fields

The following fields exist in the `signals` schema but are **not written by the v2 engine**. They are computed at render time by `server._enrich_signals()` for backward-compatible template display:

| Field | How computed |
|-------|-------------|
| `rs20_pct` | `rs20_raw × 100` |
| `crdp20` | Alias of `pressure_20w` |
| `dv_surprise` | Alias of `turnover_ratio_20_100` |
| `ret20_pct` | `(price_series[-1] / price_series[-20] - 1) × 100` (from daily price series) |
| `ret_3m_pct` | `(price_series[-1] / price_series[-63] - 1) × 100` |
| `trend` | `int(trend_score_raw)` |

These fields exist as NULL columns in the DB schema for legacy row compatibility. Do not rely on them being populated in the DB — always use `_enrich_signals()` output in templates.

---

## Appendix A — ETF Universe Reference

> **Source:** Extracted directly from `footprints.db` (`etf_meta` table), March 2026. The universe has grown from the initial 43 ETFs to 55 following sector expansion into INDIA, CHINA, FIN, INDUS, UTILS, ENERGY, CONS, CASH sectors.
> **55 ETFs total; all active=1, suspended=0; all use `VWRP.L` as benchmark.**  
> Keep this table current whenever ETFs are added or removed via Admin. Re-extract with:
> ```sql
> SELECT display_order, ticker, name, sector, benchmark_ticker
> FROM etf_meta WHERE active=1 ORDER BY display_order, ticker;
> ```

| Order | Ticker | Name | Sector |
|------:|--------|------|--------|
| 1 | AGHG.L | Amundi Core Gl Aggregate Bd UCITS ETF GBP Hgd Dist | BOND |
| 2 | AINF.L | iShares AI Infrastructure | TECH |
| 3 | BOTZ.L | Global X Robotics & AI | TECH |
| 4 | BTEK.L | iShares NASDAQ Biotech | HEALTH |
| 5 | CNX1.L | iShares NASDAQ 100 | US |
| 6 | CUKS.L | iShares MSCI UK Small Cap UCITS ETF GBP (Acc) | UK |
| 8 | DFND.L | iShares Global Aerospace & Def | DEF |
| 9 | DFNG.L | VanEck Defense | DEF |
| 10 | DRDR.L | iShares Healthcare Innovation | HEALTH |
| 12 | FTAL.L | StSt SPDR FTSE UK All Share UCITS ETF Acc | UK |
| 13 | GIGB.L | VanEck S&P Global Mining | MINING |
| 14 | HPROP.L | HSBC FTSE EPRA NAREIT Dev | PROP |
| 15 | IAUP.L | iShares Gold Producers UCITS ETF USD (Acc) | MINING |
| 16 | IDWP.L | iShares Dvlp Mrkts Prop Yld UCITS ETF USD Dist | PROP |
| 17 | IITU.L | iShares S&P500 Info Tech | TECH |
| 18 | IS15.L | iShares £ Corp Bond 0-5yr UCITS ETF GBP (Dist) | BOND |
| 19 | ISWSML.L | iShares MSCI World Small Cap UCITS ETF USD (Acc) | GLOBAL |
| 21 | IWFQ.L | iShares MSCI World Quality | GLOBAL |
| 22 | LGAG.L | L&G Asia Pacific Ex Japan Equity UCITS ETF USD Acc | APAC |
| 24 | NATP.L | Future of Defence ETF | DEF |
| 26 | RBTX.L | iShares Robotics (USD) | TECH |
| 27 | RIUS.L | L&G US ESG Paris Aligned UCITS ETF USD Acc | US |
| 28 | SGLN.L | iShares Physical Gold ETC | COMM |
| 29 | SMGB.L | VanEck Semiconductors | TECH |
| 30 | SSLN.L | iShares Physical Silver ETC | COMM |
| 31 | SWDA.L | iShares Core MSCI World UCITS ETF USD (Acc) | BASE |
| 32 | V3NB.L | Vanguard ESG N America All Cap UCITS ETF USD Acc | NAM |
| 33 | VDPG.L | Vanguard Dev Asia-Pac ex-Jpn | APAC |
| 34 | VEUA.L | Vanguard Developed Europe | EUR |
| 35 | VGVFEG.L | Vanguard FTSE Emerging Mkts UCITS ETF USD Acc | EM |
| 36 | VHVG.L | Vanguard FTSE Developed World UCITS ETF USD A | BASE |
| 37 | VJPB.L | Vanguard FTSE Japan | JAP |
| 38 | VNRG.L | Vanguard North America | NAM |
| 39 | VUKG.L | Vanguard FTSE 100 | UK |
| 40 | VUSA.L | Vanguard S&P 500 | US |
| 41 | VWRP.L | Vanguard FTSE All-World | BASE |
| 99 | AMGAGG.L | Amundi Core Global Aggregate Bond | BOND |
| 99 | EXCS.L | iShares MSCI EM ex-China UCITS ETF USD Acc | EM |
| 99 | IASH.L | iShares MSCI China A UCITS ETF USD (Acc) | CHINA |
| 99 | IESU.L | iShares S&P 500 Energy Sector UCITS ETF USD (Acc) | ENERGY |
| 99 | IHYG.L | iShares € High Yield Corp Bond UCITS ETF EUR D | BOND |
| 99 | INRG.L | iShares Global Clean Energy Trnstn UCITS ETF USD D | ENERGY |
| 99 | INXG.L | iShares £ Index-Linked Gilts UCITS ETF GBP Dist | BOND |
| 99 | ISIIND.L | iShares MSCI India UCITS USD (Acc) ETF | INDIA |
| 99 | ISWD.L | iShares MSCI World Islamic UCITS ETF USD (Dist) | GLOBAL |
| 99 | ITPS.L | iShares $ TIPS UCITS ETF USD (Acc) | BOND |
| 99 | IUCS.L | iShares S&P 500 Consumer Staples Sector UCITS ETF | CONS |
| 99 | IUHC.L | iShares S&P 500 Health Care Sctr UCITS ETF USD A | HEALTH |
| 99 | IUIS.L | iShares S&P 500 Industrials Sector UCITS ETF USD (Acc) | INDUS |
| 99 | IUUS.L | iShares S&P 500 Utilities Sector UCITS ETF USD (Acc) | UTILS |
| 99 | IWVL.L | iShares Edge MSCI Wld Val Fctr UCITS ETF USD A | GLOBAL |
| 99 | LYCSH2.L | Amundi Smart Overnight Rtn UCITS ETF GBP Hgd Acc | CASH |
| 99 | VFEM.L | Vanguard FTSE Emerging Mkts UCITS ETF USD Dis | EM |
| 99 | WCOD.L | StSt SPDR MSCI World Con Discretionary UCITS ETF | CONS |
| 99 | XWFS.L | Xtrackers MSCI World Financials UCITS 1C ETF | FIN |

**Notes:**
- VWRP.L (order=41) is both the default RS benchmark AND a signal instrument. Must be present and have price data.
- ETFs with display_order=99 are later additions not yet assigned a sequential order.
- Sector codes: BASE=Global Benchmark, BOND=Fixed Income, CASH=Cash & Money Market, COMM=Commodities, CONS=Consumer, DEF=Defence, EM=Emerging Markets, ENERGY=Energy, FIN=Financials, GLOBAL=Global Thematic, HEALTH=Healthcare, INDIA=India, CHINA=China, INDUS=Industrials, JAP=Japan, MINING=Mining, NAM=North America, PROP=Real Estate, TECH=Technology, UK=United Kingdom, UTILS=Utilities.
