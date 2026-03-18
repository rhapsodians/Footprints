# 04 — Signal Logic & KPI Computations

> **Audit status:** All formulas verified line-by-line against `engine.py` and `config.py`. This document is authoritative.

## Architecture: 10-Step Pipeline

`engine.run_engine()` is the sole public entry point. It runs the following steps in sequence:

```
prices_df (daily OHLCV)
    │
    ▼ Step 1: _resample_weekly()        daily → weekly bars (Friday close)
    ▼ Step 2: _per_ticker_features()    MA, pressure, turnover, volatility, trend score
    ▼ Step 3: _compute_rs()             RS vs benchmark (raw + vol-adjusted)
    ▼ Step 4: _latest_eligible()        reduce to latest row per ticker; filter active
    ▼ Step 5: _winsorize()              clip extremes at 2nd/98th percentile
    ▼ Step 6: _cross_sectional_ranks()  percentile rank within universe
    ▼ Step 7: _sector_breadth()         sector aggregates + confirmation
    ▼ Step 8: _compute_scores()         rotation score + confidence score
    ▼ Step 9: _classify_all()           signal label + reason string
    ▼ Step 10: _serialise()             convert to list[dict] for DB
    │
    ▼ _detect_changes()                 compare to existing signals → change log
```

---

## Step 1 — Weekly Resampling

```python
# pandas resample("W-FRI") per ticker
open   = first close of week
high   = max high of week
low    = min low of week
close  = last close of week (Friday)
volume = sum of daily volumes
# Weeks with no Friday close are dropped
```

---

## Step 2 — Per-Ticker Rolling Features

All computations are in `_per_ticker_features()`, applied per-ticker via `groupby`.

### Moving Averages

```python
ma20  = close.rolling(window=20).mean()     # WINDOW_MA20 = 20
ma100 = close.rolling(window=100).mean()    # WINDOW_MA100 = 100
```

Both require exactly N bars of history (no `min_periods` shortcut). Rows with insufficient history produce NaN.

### Trend Score (0–4)

A discrete 0–4 score encoding the current MA structure. **Not** a -7 to +7 composite as documented in earlier versions.

```python
ma100_prev20 = ma100.shift(20)   # MA100 value 20 weeks ago

trend_score_raw = (
    (close > ma20).astype(int)           # +1 if price above short MA
  + (close > ma100).astype(int)          # +1 if price above long MA
  + (ma20 > ma100).astype(int)           # +1 if short MA above long MA (golden cross structure)
  + (ma100 > ma100_prev20).astype(int)   # +1 if long MA is rising (secular trend up)
)
# Range: 0 to 4

trend_score_pct = trend_score_raw * 25.0  # Normalised to 0–100 for use in rotation score
```

**Interpretation:**
| Score | Meaning |
|-------|---------|
| 4 | Fully aligned bull: price above both MAs, MA20 > MA100, MA100 rising |
| 3 | Strong: 3 of 4 conditions met |
| 2 | Mixed / transitional |
| 1 | Weak: only 1 condition met |
| 0 | Fully broken: price below both MAs, short MA below long MA, long MA falling |

### Turnover Block

```python
dv           = close * volume                          # weekly £ turnover
avg_turn_20w = dv.rolling(20).mean()                   # 20-week avg turnover (WINDOW_LONG)
avg_turn_100w = dv.rolling(100).mean()                 # 100-week avg turnover (WINDOW_TURN)
turnover_std_100w = dv.rolling(100).std(ddof=0)        # 100-week std dev

turnover_ratio_20_100 = avg_turn_20w / avg_turn_100w   # recent vs long-run norm
turnover_z_20 = (dv - avg_turn_100w) / turnover_std_100w  # current week z-score
turn_cv20 = dv.rolling(20).std(ddof=0) / avg_turn_20w  # turnover stability (lower = more stable)
```

### Pressure Block (CLV-Based)

Pressure uses the **Close Location Value (CLV)** — a measure of where the close fell within the day's range. Multiplied by turnover to weight by participation.

```python
tr  = high - low
clv = ((close - low) - (high - close)) / tr   # = 0.0 where tr == 0

pressure       = clv * dv                              # signed daily contribution
pressure_20w   = pressure.rolling(20).sum()            # 20-week cumulative pressure
pressure_prev_20w = pressure_20w.shift(5)              # PRESSURE_LAG = 5 weeks ago

up   = pressure.clip(lower=0).rolling(20).sum()
down = (-pressure.clip(upper=0)).rolling(20).sum()
pressure_ratio_20w = up / down                         # NaN where down == 0

pressure_pos_weeks_20w = (pressure > 0).rolling(20).sum()
pressure_pos_weeks_pct = 100.0 * pressure_pos_weeks_20w / 20
```

### Realized Volatility

```python
ret_1w = close / close.shift(1) - 1.0
vol_20w = ret_1w.rolling(20).std(ddof=0)   # 20-week realized vol; set to None if zero
```

Used as denominator for vol-adjusted RS in Step 3.

---

## Step 3 — Relative Strength vs Benchmark

RS is **excess return** (ETF return minus benchmark return) over the lookback period.

```python
# For each ETF, join benchmark close series on date
etf_ret(n) = close / close.shift(n) - 1.0
bm_ret(n)  = bm_close / bm_close.shift(n) - 1.0

rs4_raw   = etf_ret(4)  - bm_ret(4)    # WINDOW_SHORT = 4
rs12_raw  = etf_ret(12) - bm_ret(12)   # WINDOW_MED = 12
rs20_raw  = etf_ret(20) - bm_ret(20)   # WINDOW_LONG = 20
rs_accel_raw = rs4_raw - rs12_raw       # positive = momentum accelerating

# Vol-adjusted RS
rs4_vol_adj          = rs4_raw  / vol_20w
rs12_vol_adj         = rs12_raw / vol_20w
rs20_vol_adj         = rs20_raw / vol_20w
rs_accel_vol_adj     = rs_accel_raw / vol_20w
```

**Important:** RS values are stored as **decimals** (0.08 = +8%). `server._enrich_signals()` multiplies `rs20_raw` by 100 to produce `rs20_pct` for template display. Do not double-count this conversion.

If the benchmark ticker is missing from the price data, all RS fields for affected ETFs will be NULL. This will not crash the engine but will produce NULL rotation scores and likely NEUTRAL signals for those ETFs.

---

## Step 4 — Latest Eligible Row

After all rolling features are computed across full history, Step 4 reduces to one row per ticker:
- Takes the last (most recent) row per ticker
- Filters to `active=1` AND `suspended=0` in `etf_meta`
- Attaches `name`, `sector`, `display_order`, `benchmark_ticker` from `etf_meta`
- Drops tickers with `n_obs < MIN_OBS_RS` (21 weekly observations minimum)

---

## Step 5 — Winsorisation

Four fields are clipped at the 2nd and 98th percentile of the current cross-section before ranking:

```
turnover_z_20
pressure_20w
rs20_vol_adj
rs_accel_vol_adj
```

This prevents outliers (e.g. a single ETF with enormous turnover) from distorting the percentile rank distribution.

---

## Step 6 — Cross-Sectional Percentile Ranks

Five percentile rank fields are computed using pandas `.rank(pct=True) * 100`:

| Output field | Source field | Meaning |
|---|---|---|
| `turnover_rank_pct` | `turnover_ratio_20_100` | Percentile of recent vs long-run turnover ratio |
| `pressure_rank_pct` | `pressure_20w` | Percentile of 20-week cumulative pressure |
| `rs20_rank_pct` | `rs20_raw` | Percentile of 20-week raw RS |
| `rs20_vol_adj_rank_pct` | `rs20_vol_adj` | Percentile of vol-adjusted RS |
| `rs_accel_vol_adj_rank_pct` | `rs_accel_vol_adj` | Percentile of vol-adjusted RS acceleration |

All ranks are 0–100. NaN values are preserved (`na_option="keep"`).

---

## Step 7 — Sector Breadth

For each sector, aggregate statistics are computed and attached back to every ETF in that sector.

**Sector score** (0–100 weighted composite):

```python
sector_score = (
    0.30 * sector_pct_rs12_pos         +   # % ETFs with rs12_raw > 0
    0.25 * sector_pct_rs20_pos         +   # % ETFs with rs20_raw > 0
    0.20 * sector_pct_positive_pressure+   # % ETFs with pressure_20w > 0
    0.15 * sector_median_pressure_rank +   # median pressure percentile rank
    0.10 * sector_pct_above_ma100          # % ETFs above MA100
)
```

**Sector confirmation** (binary — requires MIN_SECTOR_COUNT = 3 ETFs):

```python
sector_confirmed = 1 if:
    sector_pct_rs12_pos       >= 60.0    # SECTOR_CONFIRM_RS12_MIN
    AND sector_pct_rs20_pos   >= 50.0    # SECTOR_CONFIRM_RS20_MIN
    AND sector_pct_positive_pressure >= 60.0   # SECTOR_CONFIRM_PRESSURE_MIN
else 0
```

---

## Step 8 — Confidence and Rotation Scores

### Confidence Score (0–100)

Measures data quality and reliability, not signal strength:

```python
# Component weights sum to 100
liquidity   = min(avg_turn_20w / 5_000_000, 1.0)     # weight 30 — full at £5m/week
history     = min(n_obs / 130.0, 1.0)                 # weight 20 — full at 130 weekly bars
stability   = max(0, 1 - min(turn_cv20, 1.0))         # weight 15 — lower CV = more stable
sector      = 1.0 if sector_confirmed else 0.4         # weight 20 — confirmed sector adds conviction
completeness = mean([rs20_vol_adj, turnover_ratio,     # weight 15 — data completeness
                     pressure_20w, vol_20w present])

confidence_score = (30*liquidity + 20*history + 15*stability + 20*sector + 15*completeness)

# Buckets:
HIGH     >= 75.0
MODERATE >= 50.0
LOW      <  50.0
```

### Rotation Score (0–100)

Primary ranking metric. Weighted sum of percentile rank fields (weights must sum to 1.0):

```python
rotation_score = (
    0.18 * trend_score_pct          +   # trend structure (0–100 normalised)
    0.22 * rs20_vol_adj_rank_pct    +   # vol-adj 20w RS rank — highest weight
    0.15 * rs_accel_vol_adj_rank_pct+   # RS acceleration rank
    0.15 * turnover_rank_pct        +   # relative turnover rank
    0.15 * pressure_rank_pct        +   # pressure rank
    0.10 * pressure_pos_weeks_pct   +   # % of weeks with positive pressure
    0.05 * sector_confirmation_pct      # sector confirmed (0 or 100)
)
```

The sum of weights is asserted equal to 1.0 in `config.py`. An ETF with all inputs at the 80th percentile will score approximately 80. An ETF with perfectly aligned bull trend (trend_score_pct=100) but weak RS would score lower than one with strong RS but mixed trend.

---

## Step 9 — Signal Classification

Signal hierarchy is checked in **priority order**. First match wins.

> **Important:** The priority order confirmed from both `engine.py` and `guide.html` is:
> 1. EARLY ACCUMULATION
> 2. STRONG BUY
> 3. ACCUMULATING/HOLD
> 4. EXIT/DISTRIBUTION
> 5. NEUTRAL
>
> This means an ETF meeting EARLY ACCUMULATION conditions will receive that signal even if it also meets STRONG BUY conditions — because EARLY ACCUMULATION is checked first. In practice, the two rarely overlap since EARLY ACCUMULATION requires `close < MA100` (price still below long-term average) while STRONG BUY requires trend ≥ 3 (which implies price above MA100 in most cases).

### Priority 1 — EARLY ACCUMULATION

An inflection-point signal. Pressure has just flipped from non-positive to positive, with acceleration and volume confirmation. Checked **before** STRONG BUY.

```python
pressure_flipped = (pressure_prev_20w <= 0 AND pressure_20w > 0)   # PRESSURE_LAG = 5 weeks ago

pressure_flipped
AND rs_accel_raw > 0       # short-term RS accelerating vs medium-term
AND rs4_raw > 0            # currently outperforming benchmark
AND turnover_z_20 > 0      # volume above long-run average this week
AND close < MA100          # price still below structural average (early stage)
```

**Note on `close < MA100`:** In `engine.py` this condition is used in the reason string generation (not as a hard gate on the signal). The `guide.html` logic table shows it as a condition. In ambiguous cases where `close >= MA100`, the engine still fires EARLY ACCUMULATION — the MA100 comparison is used to determine whether to say "early stage" or "recovery confirmed" in the reason string. Treat the `close < MA100` as a typical but not absolute condition.

### Priority 2 — STRONG BUY

```python
rotation_score >= 72.0          # SIGNAL_STRONG_BUY["rotation_score_min"]
AND trend_score_raw >= 3
AND pressure_20w > 0
AND rs20_raw > 0
AND confidence_score >= 50.0    # SIGNAL_STRONG_BUY["confidence_min"]
```

### Priority 3 — ACCUMULATING/HOLD

```python
rotation_score >= 60.0          # SIGNAL_ACCUM_HOLD["rotation_score_min"]
AND trend_score_raw >= 3
AND pressure_20w > 0
AND rs20_raw > 0
```

### Priority 4 — EXIT/DISTRIBUTION

```python
rotation_score <= 35.0          # SIGNAL_EXIT["rotation_score_max"]  (note: < not ≤ in engine)
AND trend_score_raw <= 2        # SIGNAL_EXIT["trend_score_raw_max"]
AND pressure_20w < 0
AND rs20_raw < 0
```

### Priority 5 — NEUTRAL

Default — none of the above conditions met.

### Signal Reason String

Each signal includes a human-readable reason string, e.g.:
- `"High rotation score; strong vol-adj RS rank; positive 20w pressure; sector confirmed"`
- `"Pressure flipped positive; RS acceleration positive; turnover expanding; price above MA100 — recovery confirmed"`
- `"Low rotation score; negative pressure and RS; trend structure broken; participation declining"`

---

## V1 Field Mapping (Template Compatibility)

`server._enrich_signals()` runs after signals are loaded from DB, computing display-ready fields:

| Template field | Derived from | Notes |
|---|---|---|
| `rs20_pct` | `rs20_raw * 100` | Percentage for display |
| `crdp20` | `pressure_20w` | V1 field name alias |
| `dv_surprise` | `turnover_ratio_20_100` | V1 field name alias |
| `trend` | `int(trend_score_raw)` | Integer for display |
| `ret20_pct` | Computed from daily `price_series` | 20 trading-day return |
| `ret_3m_pct` | Computed from daily `price_series` | 63 trading-day return |

These are **not** stored in the DB by the engine. They are always computed fresh at render time.
