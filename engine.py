"""
engine.py — Footprints v2.0
============================
Weekly cross-sectional rotation engine.

Pipeline
--------
Step 1  Resample daily OHLCV → weekly (Friday close)
Step 2  Per-ticker rolling features (trend, turnover, pressure, RS, vol)
Step 3  Merge benchmark RS
Step 4  Reduce to latest eligible row per ticker
Step 5  Winsorize selected cross-sectional metrics
Step 6  Cross-sectional percentile ranks
Step 7  Sector breadth and sector confirmation
Step 8  Confidence score and rotation score
Step 9  Signal classification and explainability
Step 10 Return list[dict] ready for db.upsert_signals()

Public API
----------
run_engine(prices_df, etf_meta_df) → (list[dict], list[dict])
    Returns (signal_rows, change_log_rows)
"""

import numpy as np
import pandas as pd
from typing import Any

import config


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Resample daily → weekly
# ─────────────────────────────────────────────────────────────────────────────

def _resample_weekly(prices_df: pd.DataFrame) -> pd.DataFrame:
    """
    Resample per-ticker daily OHLCV to weekly bars (week ending Friday).
    Aggregation: open=first, high=max, low=min, close=last, volume=sum.

    Short-week correction: if the last weekly bar's Friday label falls after
    the actual last price date (e.g. Good Friday is a public holiday so data
    ends Thursday), the bar is relabelled to the actual last price date.
    This ensures signal dates match trading days, not calendar Fridays.
    """
    prices_df = prices_df.copy()
    prices_df["date"] = pd.to_datetime(prices_df["date"])
    prices_df = prices_df.sort_values(["ticker", "date"])

    # Actual last price date across all tickers (used for short-week relabelling)
    last_price_date = prices_df["date"].max()

    parts = []
    for tkr, grp in prices_df.groupby("ticker"):
        g = grp.set_index("date")
        w = g[["open", "high", "low", "close", "volume"]].resample("W-FRI").agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        ).dropna(subset=["close"])
        w.index.name = "date"
        w = w.reset_index()

        # If the last bar's Friday label is beyond the last actual price date,
        # relabel it to the actual last price date for this ticker.
        if len(w) > 0:
            last_bar_date = w["date"].iloc[-1]
            ticker_last_price = grp["date"].max()
            if last_bar_date > ticker_last_price:
                w.loc[w.index[-1], "date"] = ticker_last_price

        w["ticker"] = tkr
        parts.append(w)

    weekly = pd.concat(parts, ignore_index=True)
    weekly["date"] = pd.to_datetime(weekly["date"])
    return weekly.sort_values(["ticker", "date"]).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Per-ticker rolling features
# ─────────────────────────────────────────────────────────────────────────────

def _per_ticker_features(weekly: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all per-ticker rolling features in a single groupby pass.
    Prices are already in GBP (no pence conversion required).
    """

    def _features(g: pd.DataFrame) -> pd.DataFrame:
        g = g.sort_values("date").copy()
        close  = g["close"]
        high   = g["high"]
        low    = g["low"]
        volume = g["volume"]

        # ── Returns ───────────────────────────────────────────────────────────
        g["ret_1w"] = close / close.shift(1) - 1.0

        # ── Turnover (GBP, prices already in GBP) ────────────────────────────
        g["dv"] = close * volume

        # ── CLV and pressure ─────────────────────────────────────────────────
        tr = high - low
        clv = np.where(
            tr == 0,
            0.0,
            ((close - low) - (high - close)) / tr,
        )
        g["clv"]      = clv
        g["pressure"] = clv * g["dv"]

        # ── Moving averages ───────────────────────────────────────────────────
        g["ma20"]  = close.rolling(config.WINDOW_MA20).mean()
        g["ma100"] = close.rolling(config.WINDOW_MA100).mean()

        # ── Trend score (0–4) ─────────────────────────────────────────────────
        ma100_prev20 = g["ma100"].shift(config.WINDOW_LONG)
        g["trend_score_raw"] = (
            (close > g["ma20"]).astype(int) +
            (close > g["ma100"]).astype(int) +
            (g["ma20"] > g["ma100"]).astype(int) +
            (g["ma100"] > ma100_prev20).astype(int)
        ).astype(float)
        g["trend_score_pct"] = 25.0 * g["trend_score_raw"]

        # ── Turnover block ────────────────────────────────────────────────────
        g["turn_latest"]          = g["dv"]
        g["avg_turn_20w"]         = g["dv"].rolling(config.WINDOW_LONG).mean()
        g["avg_turn_100w"]        = g["dv"].rolling(config.WINDOW_TURN).mean()
        g["turnover_std_100w"]    = g["dv"].rolling(config.WINDOW_TURN).std(ddof=0)
        g["turnover_ratio_20_100"] = g["avg_turn_20w"] / g["avg_turn_100w"]
        g["turnover_z_20"]        = (
            (g["turn_latest"] - g["avg_turn_100w"]) / g["turnover_std_100w"]
        )
        g["turn_cv20"] = (
            g["dv"].rolling(config.WINDOW_LONG).std(ddof=0) / g["avg_turn_20w"]
        )
        # Guard zero denominator
        g.loc[g["avg_turn_20w"] == 0, "turn_cv20"] = None

        # ── Pressure block ────────────────────────────────────────────────────
        g["pressure_20w"]      = g["pressure"].rolling(config.WINDOW_LONG).sum()
        g["pressure_prev_20w"] = g["pressure_20w"].shift(config.PRESSURE_LAG)

        up   = g["pressure"].clip(lower=0).rolling(config.WINDOW_LONG).sum()
        down = (-g["pressure"].clip(upper=0)).rolling(config.WINDOW_LONG).sum()

        g["up_pressure_20w"]   = up
        g["down_pressure_20w"] = down

        # Null-safe pressure ratio
        ratio = np.where(down == 0, np.nan, up / down)
        g["pressure_ratio_20w"]        = ratio
        g["pressure_all_positive_20w"] = (down == 0).astype(int)

        g["pressure_pos_weeks_20w"] = (
            (g["pressure"] > 0).rolling(config.WINDOW_LONG).sum()
        )
        g["pressure_pos_weeks_pct"] = (
            100.0 * g["pressure_pos_weeks_20w"] / config.WINDOW_LONG
        )

        # ── Realized volatility ───────────────────────────────────────────────
        g["vol_20w"] = g["ret_1w"].rolling(config.WINDOW_LONG).std(ddof=0)
        g.loc[g["vol_20w"] == 0, "vol_20w"] = None   # guard zero vol

        # ── Observation count (used for confidence) ───────────────────────────
        g["n_obs"] = np.arange(1, len(g) + 1, dtype=float)

        return g

    parts = []
    for tkr, grp in weekly.groupby("ticker"):
        result = _features(grp.copy())
        result["ticker"] = tkr
        parts.append(result)

    return pd.concat(parts, ignore_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Merge benchmark and compute RS
# ─────────────────────────────────────────────────────────────────────────────

def _compute_rs(
    featured: pd.DataFrame,
    etf_meta: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge benchmark close for each ETF (using etf_meta.benchmark_ticker)
    and compute raw and vol-adjusted RS.

    Because all 40 ETFs currently share VWRP.L as benchmark, we vectorise
    the common case. Per-ETF overrides are supported via benchmark_ticker.
    """
    # Build benchmark lookup: {benchmark_ticker → Series(date → close)}
    benchmarks: dict[str, pd.Series] = {}
    for bm in etf_meta["benchmark_ticker"].unique():
        bm_rows = featured[featured["ticker"] == bm][["date", "close"]].copy()
        if bm_rows.empty:
            continue
        bm_rows = bm_rows.set_index("date")["close"].rename(bm)
        benchmarks[bm] = bm_rows

    # Map ticker → benchmark_ticker
    bm_map = etf_meta.set_index("ticker")["benchmark_ticker"].to_dict()

    parts = []
    for tkr, grp in featured.groupby("ticker", group_keys=False):
        grp = grp.copy().sort_values("date")
        bm_ticker = bm_map.get(tkr, config.BASE_TICKER)

        if bm_ticker not in benchmarks:
            # Benchmark data missing — RS fields stay null
            for col in (
                "rs4_raw", "rs12_raw", "rs20_raw", "rs_accel_raw",
                "rs4_vol_adj", "rs12_vol_adj", "rs20_vol_adj", "rs_accel_vol_adj",
            ):
                grp[col] = np.nan
            parts.append(grp)
            continue

        bm_series = benchmarks[bm_ticker]
        grp = grp.join(
            bm_series.rename("bm_close"),
            on="date",
            how="left",
        )

        close    = grp["close"]
        bm_close = grp["bm_close"]

        # Raw RS (excess return vs benchmark)
        etf_ret  = lambda n: close / close.shift(n) - 1.0
        bm_ret   = lambda n: bm_close / bm_close.shift(n) - 1.0

        grp["rs4_raw"]      = etf_ret(config.WINDOW_SHORT) - bm_ret(config.WINDOW_SHORT)
        grp["rs12_raw"]     = etf_ret(config.WINDOW_MED)   - bm_ret(config.WINDOW_MED)
        grp["rs20_raw"]     = etf_ret(config.WINDOW_LONG)  - bm_ret(config.WINDOW_LONG)
        grp["rs_accel_raw"] = grp["rs4_raw"] - grp["rs12_raw"]

        # Vol-adjusted RS (null if vol_20w is null/zero)
        vol = grp["vol_20w"]
        grp["rs4_vol_adj"]      = grp["rs4_raw"]      / vol
        grp["rs12_vol_adj"]     = grp["rs12_raw"]     / vol
        grp["rs20_vol_adj"]     = grp["rs20_raw"]     / vol
        grp["rs_accel_vol_adj"] = grp["rs_accel_raw"] / vol

        parts.append(grp)

    return pd.concat(parts, ignore_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Reduce to latest eligible row per ticker
# ─────────────────────────────────────────────────────────────────────────────

def _latest_eligible(
    featured: pd.DataFrame,
    etf_meta: pd.DataFrame,
) -> pd.DataFrame:
    """
    Take the last row per ticker. Attach sector. Filter to active, non-suspended.
    Retain all tickers that meet at least MIN_OBS_RS (21 weekly obs).
    """
    active_tickers = set(
        etf_meta.loc[
            (etf_meta["active"] == 1) & (etf_meta["suspended"] == 0),
            "ticker",
        ]
    )

    latest = (
        featured[featured["ticker"].isin(active_tickers)]
        .sort_values(["ticker", "date"])
        .groupby("ticker", group_keys=False)
        .last()
        .reset_index()
    )

    # Attach sector and name
    meta_cols = etf_meta[["ticker", "name", "sector", "display_order", "benchmark_ticker"]]
    latest = latest.merge(meta_cols, on="ticker", how="left")

    # Drop tickers below absolute minimum
    latest = latest[latest["n_obs"] >= config.MIN_OBS_RS].copy()

    return latest


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — Winsorization
# ─────────────────────────────────────────────────────────────────────────────

_WINSOR_COLS = [
    "turnover_z_20",
    "pressure_20w",
    "rs20_vol_adj",
    "rs_accel_vol_adj",
]


def _winsorize(latest: pd.DataFrame) -> pd.DataFrame:
    latest = latest.copy()
    for col in _WINSOR_COLS:
        if col not in latest.columns:
            continue
        s = latest[col].dropna()
        if s.empty:
            continue
        lo = s.quantile(config.WINSOR_LOWER)
        hi = s.quantile(config.WINSOR_UPPER)
        latest[col] = latest[col].clip(lo, hi)
    return latest


# ─────────────────────────────────────────────────────────────────────────────
# Step 6 — Cross-sectional percentile ranks
# ─────────────────────────────────────────────────────────────────────────────

_RANK_MAP: dict[str, str] = {
    "turnover_ratio_20_100": "turnover_rank_pct",
    "pressure_20w":          "pressure_rank_pct",
    "rs20_raw":              "rs20_rank_pct",
    "rs20_vol_adj":          "rs20_vol_adj_rank_pct",
    "rs_accel_vol_adj":      "rs_accel_vol_adj_rank_pct",
}


def _cross_sectional_ranks(latest: pd.DataFrame) -> pd.DataFrame:
    latest = latest.copy()
    for src, dst in _RANK_MAP.items():
        if src in latest.columns:
            latest[dst] = latest[src].rank(pct=True, na_option="keep") * 100.0
    return latest


# ─────────────────────────────────────────────────────────────────────────────
# Step 7 — Sector breadth and confirmation
# ─────────────────────────────────────────────────────────────────────────────

def _sector_breadth(latest: pd.DataFrame) -> pd.DataFrame:
    latest = latest.copy()

    def _pct_pos(s: pd.Series) -> float:
        valid = s.dropna()
        if valid.empty:
            return np.nan
        return 100.0 * (valid > 0).mean()

    def _median(s: pd.Series) -> float:
        return float(s.median()) if not s.dropna().empty else np.nan

    sector_stats: list[dict] = []
    for sector, grp in latest.groupby("sector"):
        n = len(grp)
        stat: dict[str, Any] = {
            "sector": sector,
            "sector_count": n,
            "sector_pct_rs4_pos":            _pct_pos(grp["rs4_raw"]),
            "sector_pct_rs12_pos":           _pct_pos(grp["rs12_raw"]),
            "sector_pct_rs20_pos":           _pct_pos(grp["rs20_raw"]),
            "sector_pct_rs_accel_pos":       _pct_pos(grp["rs_accel_raw"]),
            "sector_pct_positive_pressure":  _pct_pos(grp["pressure_20w"]),
            "sector_pct_above_ma20":         100.0 * (grp["close"] > grp["ma20"]).mean(),
            "sector_pct_above_ma100":        100.0 * (grp["close"] > grp["ma100"]).mean(),
            "sector_median_rs20_vol_adj":    _median(grp["rs20_vol_adj"]),
            "sector_median_pressure_rank":   _median(grp.get("pressure_rank_pct", pd.Series(dtype=float))),
            "sector_median_turnover_rank":   _median(grp.get("turnover_rank_pct", pd.Series(dtype=float))),
        }

        # Sector score
        stat["sector_score"] = (
            config.SECTOR_SCORE_WEIGHTS["sector_pct_rs12_pos"]          * _nan0(stat["sector_pct_rs12_pos"]) +
            config.SECTOR_SCORE_WEIGHTS["sector_pct_rs20_pos"]          * _nan0(stat["sector_pct_rs20_pos"]) +
            config.SECTOR_SCORE_WEIGHTS["sector_pct_positive_pressure"] * _nan0(stat["sector_pct_positive_pressure"]) +
            config.SECTOR_SCORE_WEIGHTS["sector_median_pressure_rank"]  * _nan0(stat["sector_median_pressure_rank"]) +
            config.SECTOR_SCORE_WEIGHTS["sector_pct_above_ma100"]       * _nan0(stat["sector_pct_above_ma100"])
        )

        # Sector confirmation
        if n >= config.MIN_SECTOR_COUNT:
            stat["sector_confirmed"] = int(
                _nan0(stat["sector_pct_rs12_pos"])          >= config.SECTOR_CONFIRM_RS12_MIN and
                _nan0(stat["sector_pct_rs20_pos"])          >= config.SECTOR_CONFIRM_RS20_MIN and
                _nan0(stat["sector_pct_positive_pressure"]) >= config.SECTOR_CONFIRM_PRESSURE_MIN
            )
        else:
            stat["sector_confirmed"] = 0

        stat["sector_confirmation_pct"] = 100.0 if stat["sector_confirmed"] else 0.0

        sector_stats.append(stat)

    sector_df = pd.DataFrame(sector_stats)
    latest = latest.merge(sector_df, on="sector", how="left")
    return latest


def _nan0(v: Any) -> float:
    """Return 0.0 if v is None or NaN, else float(v)."""
    if v is None:
        return 0.0
    try:
        return 0.0 if np.isnan(v) else float(v)
    except (TypeError, ValueError):
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Step 8 — Confidence and rotation score
# ─────────────────────────────────────────────────────────────────────────────

def _confidence_score(row: pd.Series) -> tuple[float, str]:
    """Compute confidence score (0–100) and bucket label for one ETF row."""
    w = config.CONFIDENCE_WEIGHTS

    # Liquidity
    avg_turn = _nan0(row.get("avg_turn_20w"))
    liquidity = min(avg_turn / config.LIQUIDITY_FULL, 1.0)

    # History
    n_obs = _nan0(row.get("n_obs"))
    history = min(n_obs / config.CONFIDENCE_HISTORY_DENOM, 1.0)

    # Stability (lower cv = more stable)
    cv = row.get("turn_cv20")
    if cv is None or (isinstance(cv, float) and np.isnan(cv)):
        stability = 0.5   # neutral penalty for missing cv
    else:
        stability = max(0.0, 1.0 - min(float(cv), 1.0))

    # Sector
    confirmed = _nan0(row.get("sector_confirmed"))
    sector = (
        config.CONFIDENCE_SECTOR_CONFIRMED
        if confirmed == 1
        else config.CONFIDENCE_SECTOR_UNCONFIRMED
    )

    # Data completeness
    required = ["rs20_vol_adj", "turnover_ratio_20_100", "pressure_20w", "vol_20w"]
    present = [
        0.0 if (row.get(f) is None or (isinstance(row.get(f), float) and np.isnan(row.get(f))))
        else 1.0
        for f in required
    ]
    completeness = float(np.mean(present))

    score = (
        w["liquidity"]    * liquidity    +
        w["history"]      * history      +
        w["stability"]    * stability    +
        w["sector"]       * sector       +
        w["completeness"] * completeness
    )

    if score >= config.CONFIDENCE_HIGH:
        bucket = "HIGH"
    elif score >= config.CONFIDENCE_MODERATE:
        bucket = "MODERATE"
    else:
        bucket = "LOW"

    return round(score, 2), bucket


def _rotation_score(row: pd.Series) -> float:
    """Weighted rotation score (0–100) for one ETF row."""
    total = 0.0
    for field, weight in config.ROTATION_WEIGHTS.items():
        total += weight * _nan0(row.get(field))
    return round(total, 2)


def _compute_scores(latest: pd.DataFrame) -> pd.DataFrame:
    latest = latest.copy()
    def _scores(r: pd.Series) -> pd.Series:
        conf_score, conf_bucket = _confidence_score(r)
        return pd.Series({
            "confidence_score":  conf_score,
            "confidence_bucket": conf_bucket,
            "rotation_score":    _rotation_score(r),
        })
    scores = latest.apply(_scores, axis=1)
    latest = pd.concat([latest, scores], axis=1)
    return latest


# ─────────────────────────────────────────────────────────────────────────────
# Step 9 — Signal classification and explainability
# ─────────────────────────────────────────────────────────────────────────────

def _classify(row: pd.Series) -> tuple[str, str]:
    """Return (signal_label, signal_reason) for one ETF row."""
    rs   = _nan0(row.get("rotation_score"))
    tr   = _nan0(row.get("trend_score_raw"))
    p20  = row.get("pressure_20w")
    p20v = _nan0(p20)
    r20  = row.get("rs20_raw")
    r20v = _nan0(r20)
    conf = _nan0(row.get("confidence_score"))

    p_prev   = row.get("pressure_prev_20w")
    p_prevv  = _nan0(p_prev)
    racc     = _nan0(row.get("rs_accel_raw"))
    rs4      = _nan0(row.get("rs4_raw"))
    tz20     = _nan0(row.get("turnover_z_20"))
    close    = _nan0(row.get("close"))
    ma100    = _nan0(row.get("ma100"))

    sc = config

    # ── STRONG BUY ────────────────────────────────────────────────────────────
    if (
        rs   >= sc.SIGNAL_STRONG_BUY["rotation_score_min"] and
        tr   >= sc.SIGNAL_STRONG_BUY["trend_score_raw_min"] and
        p20v  > 0 and
        r20v  > 0 and
        conf >= sc.SIGNAL_STRONG_BUY["confidence_min"]
    ):
        reason_parts = ["High rotation score"]
        if _nan0(row.get("rs20_vol_adj_rank_pct")) >= 70:
            reason_parts.append("strong vol-adj RS rank")
        if p20v > 0:
            reason_parts.append("positive 20w pressure")
        if _nan0(row.get("sector_confirmed")) == 1:
            reason_parts.append("sector confirmed")
        if _nan0(row.get("turnover_rank_pct")) >= 60:
            reason_parts.append("elevated turnover rank")
        return sc.SIG_STRONG_BUY, "; ".join(reason_parts)

    # ── ACCUMULATING/HOLD ────────────────────────────────────────────────────
    if (
        rs  >= sc.SIGNAL_ACCUM_HOLD["rotation_score_min"] and
        tr  >= sc.SIGNAL_ACCUM_HOLD["trend_score_raw_min"] and
        p20v > 0 and
        r20v > 0
    ):
        reason_parts = ["Solid rotation score; positive pressure and RS"]
        if _nan0(row.get("rs20_vol_adj_rank_pct")) >= 50:
            reason_parts.append("above-median vol-adj RS rank")
        return sc.SIG_ACCUM, "; ".join(reason_parts)

    # ── EARLY ACCUMULATION ───────────────────────────────────────────────────
    # Pressure has just flipped positive after being non-positive
    pressure_flipped = (
        p_prev is not None and
        not (isinstance(p_prev, float) and np.isnan(p_prev)) and
        p_prevv <= 0 and
        p20v > 0
    )
    if (
        pressure_flipped and
        racc  > 0 and
        rs4   > 0 and
        tz20  > 0
    ):
        reason_parts = [
            "Pressure flipped positive",
            "RS acceleration positive",
        ]
        if tz20 > 0:
            reason_parts.append("turnover expanding")
        if ma100 > 0 and close < ma100:
            reason_parts.append("price below MA100 — early stage")
        elif ma100 > 0 and close >= ma100:
            reason_parts.append("price above MA100 — recovery confirmed")
        return sc.SIG_EARLY_ACCUM, "; ".join(reason_parts)

    # ── EXIT/DISTRIBUTION ────────────────────────────────────────────────────
    if (
        rs   < sc.SIGNAL_EXIT["rotation_score_max"] and
        tr   <= sc.SIGNAL_EXIT["trend_score_raw_max"] and
        p20v  < 0 and
        r20v  < 0
    ):
        reason_parts = ["Low rotation score; negative pressure and RS"]
        if tr <= 1:
            reason_parts.append("trend structure broken")
        if _nan0(row.get("turnover_rank_pct")) < 40:
            reason_parts.append("participation declining")
        return sc.SIG_EXIT, "; ".join(reason_parts)

    # ── NEUTRAL ───────────────────────────────────────────────────────────────
    neutral_parts = ["Mixed signals"]
    if rs >= 50:
        neutral_parts.append("above-median rotation score")
    elif rs < 50:
        neutral_parts.append("below-median rotation score")
    return sc.SIG_NEUTRAL, "; ".join(neutral_parts)


def _classify_all(latest: pd.DataFrame) -> pd.DataFrame:
    latest = latest.copy()
    def _row(r: pd.Series) -> pd.Series:
        signal, reason = _classify(r)
        return pd.Series({"signal": signal, "signal_reason": reason})
    classified = latest.apply(_row, axis=1)
    latest = pd.concat([latest, classified], axis=1)
    latest["signal_model_version"] = config.MODEL_VERSION
    return latest


# ─────────────────────────────────────────────────────────────────────────────
# Step 10 — Serialise to dicts for DB write
# ─────────────────────────────────────────────────────────────────────────────

# Columns to write to signals table (must match db._SIGNALS_COLUMNS + PKs)
_OUTPUT_COLS = [
    "date", "ticker",
    "signal", "signal_model_version", "signal_reason",
    "rotation_score", "confidence_score", "confidence_bucket",
    "trend_score_raw", "trend_score_pct",
    "close", "ma20", "ma100",
    "n_obs",
    "turn_latest", "avg_turn_20w", "avg_turn_100w",
    "turnover_ratio_20_100", "turnover_z_20", "turn_cv20", "turnover_rank_pct",
    "pressure_20w", "pressure_prev_20w", "pressure_ratio_20w",
    "pressure_all_positive_20w", "pressure_pos_weeks_20w",
    "pressure_pos_weeks_pct", "pressure_rank_pct",
    "rs4_raw", "rs12_raw", "rs20_raw", "rs_accel_raw", "rs20_rank_pct",
    "vol_20w",
    "rs4_vol_adj", "rs12_vol_adj", "rs20_vol_adj", "rs_accel_vol_adj",
    "rs20_vol_adj_rank_pct", "rs_accel_vol_adj_rank_pct",
    "sector_count", "sector_pct_rs4_pos", "sector_pct_rs12_pos",
    "sector_pct_rs20_pos", "sector_pct_rs_accel_pos",
    "sector_pct_positive_pressure", "sector_pct_above_ma20",
    "sector_pct_above_ma100", "sector_median_rs20_vol_adj",
    "sector_median_pressure_rank", "sector_median_turnover_rank",
    "sector_score", "sector_confirmed", "sector_confirmation_pct",
]


def _to_python(v: Any) -> Any:
    """Convert numpy scalars / NaN to Python-native types for SQLite."""
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    return v


def _serialise(latest: pd.DataFrame) -> list[dict]:
    rows = []
    for _, row in latest.iterrows():
        d: dict = {}
        for col in _OUTPUT_COLS:
            val = row.get(col, None)
            d[col] = _to_python(val)
        # Ensure date is a string
        if isinstance(d["date"], pd.Timestamp):
            d["date"] = d["date"].strftime("%Y-%m-%d")
        rows.append(d)
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Change detection
# ─────────────────────────────────────────────────────────────────────────────

def _detect_changes(
    new_rows: list[dict],
    existing_df: pd.DataFrame,
) -> list[dict]:
    """
    Compare new signal classifications against the most recent existing signals.
    Returns list[dict] for signal_log.
    """
    if existing_df.empty:
        return []

    prev = existing_df.set_index("ticker")["signal"].to_dict()
    changes = []
    for row in new_rows:
        tkr = row["ticker"]
        old = prev.get(tkr)
        new = row.get("signal")
        if old is not None and old != new:
            changes.append({
                "date":             row["date"],
                "ticker":           tkr,
                "old_signal":       old,
                "new_signal":       new,
                "rotation_score":   row.get("rotation_score"),
                "confidence_score": row.get("confidence_score"),
            })
    return changes


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_engine(
    prices_df: pd.DataFrame,
    etf_meta_df: pd.DataFrame,
    existing_signals_df: pd.DataFrame | None = None,
    as_of_date: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Run the full v2 signal engine.

    Parameters
    ----------
    prices_df           : raw daily OHLCV from db.get_prices_df()
    etf_meta_df         : etf universe from db.get_etf_meta()
    existing_signals_df : current signals from db.get_signals_df() for change detection
    as_of_date          : if given (YYYY-MM-DD, must be a Friday), restrict prices
                          to <= that date so the engine produces signals for exactly
                          that week-end. Useful for backfilling or recomputing a
                          specific historical Friday when newer data already exists.

    Returns
    -------
    (signal_rows, change_log_rows)
        signal_rows      → pass to db.upsert_signals()
        change_log_rows  → pass to db.log_signal_changes()
    """
    if existing_signals_df is None:
        existing_signals_df = pd.DataFrame()

    # If a target date is supplied, clip prices to that Friday
    if as_of_date:
        cutoff = pd.Timestamp(as_of_date)
        prices_df = prices_df[prices_df["date"] <= cutoff].copy()

    # Pipeline
    weekly  = _resample_weekly(prices_df)
    feat    = _per_ticker_features(weekly)
    feat    = _compute_rs(feat, etf_meta_df)
    latest  = _latest_eligible(feat, etf_meta_df)
    latest  = _winsorize(latest)
    latest  = _cross_sectional_ranks(latest)
    latest  = _sector_breadth(latest)
    latest  = _compute_scores(latest)
    latest  = _classify_all(latest)

    signal_rows = _serialise(latest)
    change_rows = _detect_changes(signal_rows, existing_signals_df)

    return signal_rows, change_rows
