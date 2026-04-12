"""
config.py — Footprints v2.0
============================
Central configuration: constants, weights, thresholds, sector labels.
All tuneable parameters live here so engine.py and server.py stay clean.
"""

# ── Identity ──────────────────────────────────────────────────────────────────

APP_NAME    = "Footprints"
APP_VERSION = "2.0"
MODEL_VERSION = "weekly_v2_0"

# ── Database ──────────────────────────────────────────────────────────────────

import os
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "footprints.db")

# ── Benchmark ─────────────────────────────────────────────────────────────────

BASE_TICKER = "VWRP.L"   # Default benchmark for all RS calculations.
                          # etf_meta.benchmark_ticker overrides per-ETF if set.

# ── Sectors ───────────────────────────────────────────────────────────────────

SECTOR_LABEL: dict[str, str] = {
    "BASE":   "Global Benchmark",
    "US":     "United States",
    "NAM":    "North America",
    "UK":     "United Kingdom",
    "EUR":    "Europe",
    "JAP":    "Japan",
    "APAC":   "Asia-Pacific",
    "EM":     "Emerging Markets",
    "INDIA":  "India",
    "CHINA":  "China",
    "TECH":   "Technology",
    "HEALTH": "Healthcare",
    "DEF":    "Defence",
    "FIN":    "Financials",
    "INDUS":  "Industrials",
    "UTILS":  "Utilities",
    "ENERGY": "Energy",
    "CSTAP": "Consumer Staples",
    "CDISC": "Consumer Discretionary",
    "PROP":   "Real Estate",
    "COMM":   "Commodities",
    "MINING": "Mining",
    "BOND":   "Fixed Income",
    "CASH":   "Cash & Money Market",
    "MAST":   "Multi-Asset",
    "GLOBAL": "Global Thematic",
    "OTHER":  "Other",
}
SECTORS = sorted(SECTOR_LABEL.keys())

# ── UI constants ──────────────────────────────────────────────────────────────

SPARKLINE_WEEKS      = 520  # daily rows sent to dashboard; resampled to weekly in JS for MA calculation
PRICE_HISTORY_LIMIT  = 520  # daily rows served via /api/prices and ETF history view

# ── Data minimums ─────────────────────────────────────────────────────────────
# Hard minimums for model eligibility (weekly observations).

MIN_OBS_FULL      = 120   # Full model eligibility (spec §3.2)
MIN_OBS_RS        = 21    # Minimum for 20-week RS
MIN_OBS_VOL       = 20    # Minimum for 20-week realized volatility
MIN_OBS_TURNOVER  = 100   # Minimum for turnover normalization
MIN_SECTOR_COUNT  = 3     # Minimum ETFs in sector for valid breadth

CONFIDENCE_HISTORY_DENOM = 130.0  # history_component → 1.0 at this weekly obs count (spec §9.1B)

# ── Rolling windows ───────────────────────────────────────────────────────────

WINDOW_SHORT  = 4    # weeks  (RS short)
WINDOW_MED    = 12   # weeks  (RS medium)
WINDOW_LONG   = 20   # weeks  (RS long, pressure, vol)
WINDOW_MA20   = 20   # weeks  (moving average short)
WINDOW_MA100  = 100  # weeks  (moving average long)
WINDOW_TURN   = 100  # weeks  (turnover normalisation base)
PRESSURE_LAG  = 5    # weeks  (pressure_prev lookback)

# ── Winsorization bounds ──────────────────────────────────────────────────────

WINSOR_LOWER = 0.02
WINSOR_UPPER = 0.98

# ── Liquidity threshold for confidence score ──────────────────────────────────
# Turnover (£) at which liquidity_component reaches 1.0

LIQUIDITY_FULL = 5_000_000.0   # £5m weekly turnover

# ── Rotation score weights ────────────────────────────────────────────────────
# Must sum to 1.0

ROTATION_WEIGHTS: dict[str, float] = {
    "trend_score_pct":           0.18,
    "rs20_vol_adj_rank_pct":     0.22,
    "rs_accel_vol_adj_rank_pct": 0.15,
    "turnover_rank_pct":         0.15,
    "pressure_rank_pct":         0.15,
    "pressure_pos_weeks_pct":    0.10,
    "sector_confirmation_pct":   0.05,
}

assert abs(sum(ROTATION_WEIGHTS.values()) - 1.0) < 1e-9, \
    "ROTATION_WEIGHTS must sum to 1.0"

# ── Confidence score weights ──────────────────────────────────────────────────
# Points out of 100 for each component

CONFIDENCE_WEIGHTS: dict[str, float] = {
    "liquidity":    30.0,
    "history":      20.0,
    "stability":    15.0,
    "sector":       20.0,
    "completeness": 15.0,
}

assert abs(sum(CONFIDENCE_WEIGHTS.values()) - 100.0) < 1e-9, \
    "CONFIDENCE_WEIGHTS must sum to 100.0"

CONFIDENCE_SECTOR_CONFIRMED   = 1.0   # multiplier when sector confirmed
CONFIDENCE_SECTOR_UNCONFIRMED = 0.4   # multiplier when sector not confirmed

# ── Confidence buckets ────────────────────────────────────────────────────────

CONFIDENCE_HIGH     = 75.0
CONFIDENCE_MODERATE = 50.0
# Below CONFIDENCE_MODERATE → LOW

# ── Sector confirmation thresholds ────────────────────────────────────────────

SECTOR_CONFIRM_RS12_MIN     = 60.0   # % of sector ETFs with rs12_raw > 0
SECTOR_CONFIRM_RS20_MIN     = 50.0   # % of sector ETFs with rs20_raw > 0
SECTOR_CONFIRM_PRESSURE_MIN = 60.0   # % of sector ETFs with pressure_20w > 0

# ── Sector score weights ──────────────────────────────────────────────────────

SECTOR_SCORE_WEIGHTS: dict[str, float] = {
    "sector_pct_rs12_pos":          0.30,
    "sector_pct_rs20_pos":          0.25,
    "sector_pct_positive_pressure": 0.20,
    "sector_median_pressure_rank":  0.15,
    "sector_pct_above_ma100":       0.10,
}

# ── Signal thresholds ─────────────────────────────────────────────────────────

SIGNAL_STRONG_BUY = dict(
    rotation_score_min  = 72.0,
    trend_score_raw_min = 3,
    confidence_min      = 50.0,
)

SIGNAL_ACCUM_HOLD = dict(
    rotation_score_min  = 60.0,
    trend_score_raw_min = 3,
)

SIGNAL_EXIT = dict(
    rotation_score_max  = 35.0,
    trend_score_raw_max = 2,
)

# ── Signal labels ─────────────────────────────────────────────────────────────

SIG_STRONG_BUY  = "STRONG BUY"
SIG_ACCUM       = "ACCUMULATING/HOLD"
SIG_EARLY_ACCUM = "EARLY ACCUMULATION"
SIG_EXIT        = "EXIT/DISTRIBUTION"
SIG_NEUTRAL     = "NEUTRAL"

SIGNAL_ORDER = [
    SIG_STRONG_BUY,
    SIG_ACCUM,
    SIG_EARLY_ACCUM,
    SIG_NEUTRAL,
    SIG_EXIT,
]

# ── UI colour map for signals ─────────────────────────────────────────────────

SIGNAL_CSS: dict[str, str] = {
    SIG_STRONG_BUY:  "green",
    SIG_ACCUM:       "green",
    SIG_EARLY_ACCUM: "yellow",
    SIG_NEUTRAL:     "neutral",
    SIG_EXIT:        "red",
}
