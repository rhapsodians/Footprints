# 07 — Financial Rationale: Following the Instructional Money

> **Audit status:** Financial logic unchanged; updated to reflect v2 KPI names (Pressure, RS, Trend Score 0–4) rather than the v1 KPIs (RSI, mom4w/12w) used in prior documentation.

## Core Thesis

> "Don't predict the market. Read where the money is already going."

Footprints is built on the premise that retail investors are structurally disadvantaged in forming macro views, but have **information parity** in reading price action. Every institutional trade leaves a footprint in price and volume. The goal is to read those footprints systematically and mechanically.

This document explains *why* each KPI was chosen, what financial behaviour it detects, and why the combination is more robust than any single indicator.

---

## Why Technical Signals for Pension Funds?

Four structural facts make tactical rotation rational for pension accounts specifically:

1. **No CGT on pension fund switches.** Unlike ISA or GIA rebalancing, pension switches are tax-free within the wrapper. This eliminates the tax friction that typically makes tactical allocation uneconomic for retail investors.
2. **Drawdown is asymmetric at accumulation maturity.** A 40% drawdown at age 55 with a 10-year runway is qualitatively different from one at age 35 with 30 years. Protection matters more as the horizon shortens.
3. **Platforms allow switching.** L&G WorkSave and Irish Life both permit fund switches. The capability exists; it is just not commonly used systematically.
4. **Institutional money rotates.** Price action reflects those rotations. Proxy ETF signals detect them.

---

## Why These KPIs? (v2 Engine)

### Moving Averages (MA20, MA100) — The Structural Anchors

MA20 and MA100 are the two moving average levels tracked. They appear in the **Trend Score** (0–4) and are surfaced directly on the Dashboard sparklines.

**MA100 — the institutional line:** The 100-week MA represents approximately 2 years of price history. Large institutional allocators use long-period MAs as their structural benchmark for whether an asset class is in a secular bull or bear. When price crosses below MA100 on a weekly close in a broad-market ETF, it signals that passive inflows are no longer sufficient to maintain price — institutional sellers are outweighing buyers. This is a structural shift.

**MA20 — the tactical level:** The 20-week MA captures the medium-term trend — roughly one earnings cycle. In uptrends, price tends to bounce off MA20 as support. The relationship of MA20 vs MA100 (the golden/death cross structure) is one of the four components of the Trend Score.

**Trend Score (0–4):** Encodes the full MA structure into a single integer. A score of 4 means all four conditions are met simultaneously: price above both MAs, short MA above long MA, and long MA itself rising. Score 0 means complete structural breakdown. This replaces the v1 binary MA cross signal with a more granular, nuanced assessment.

### Relative Strength (RS) — The Rotation Signal

RS measures **excess return vs benchmark** (VWRP.L) over 4, 12, and 20 weeks. It is the primary driver of rotation score, given the highest weight (0.22 for `rs20_vol_adj_rank_pct`).

**Financial logic:** Cross-asset momentum research (Fama-French, AQR, Jegadeesh-Titman) consistently shows that assets with the highest 3–12 month trailing returns tend to continue outperforming over the next 1–3 months. This is the momentum premium — the most robustly documented anomaly in finance.

**Why vol-adjusted RS?** Raw RS favours high-volatility assets that happen to have moved recently. Vol-adjusted RS (`rs20_raw / vol_20w`) normalises for this — a modest but consistent outperformance from a low-volatility bond ETF can rank above a high-volatility sector ETF with the same raw RS. This produces a fairer comparison across different asset classes.

**RS acceleration (`rs_accel_raw = rs4_raw - rs12_raw`):** Positive acceleration means short-term RS is better than medium-term RS — momentum is building, not fading. This is the early warning signal used in the EARLY ACCUMULATION classification.

### Pressure (CLV-Based) — The Institutional Fingerprint

Pressure is the most distinctive v2 KPI. It combines where the close fell within the day's range (CLV) with the day's turnover, accumulated over 20 weeks.

```
CLV = ((close - low) - (high - close)) / (high - low)
    = +1 if close at the high (buyers dominated all day)
    = -1 if close at the low (sellers dominated all day)
    =  0 if close at midpoint

Pressure = CLV × (close × volume)   →  weighted by £ participation
```

**Financial logic:** Institutional accumulation leaves a specific footprint: volume above average, closes consistently in the upper half of the day's range. Institutional distribution leaves the mirror pattern: elevated volume, closes in the lower half. Pressure over 20 weeks captures whether smart money has been systematically buying or selling, regardless of where the price has moved in absolute terms.

A rising price on negative pressure = retail FOMO without institutional support = fragile. A flat price on positive pressure = stealth accumulation = potential breakout ahead. This is the "follow the money, not the price" insight at the heart of the system.

**Pressure flip (EARLY ACCUMULATION):** When `pressure_20w` crosses from non-positive to positive (detected via `pressure_prev_20w` 5 weeks prior), combined with accelerating RS and expanding turnover, this signals the early stage of institutional accumulation — before the price has moved enough to qualify for ACCUMULATING/HOLD. This is the system's early-warning classification.

### Turnover Ratio (Recent vs Long-Run Norm) — Confirming Participation

`turnover_ratio_20_100 = avg_turn_20w / avg_turn_100w`

A ratio > 1 means recent turnover is above the 2-year norm — elevated institutional participation. A ratio < 1 means participation is below normal — fading interest.

**Financial logic:** Volume is the lie detector of price action. Price can move on thin volume (easily reversed) or heavy volume (structural). The ratio contextualises recent turnover against the asset's own history, rather than comparing it cross-sectionally (which would favour large-cap ETFs regardless of their own trend context).

### Confidence Score — Not a Signal, a Quality Flag

The confidence score (0–100) measures **data quality and reliability**, not signal strength. An ETF with excellent signals but only 22 weeks of history will receive LOW confidence. An illiquid ETF with £500k weekly turnover will receive LOW confidence. This prevents the system from acting on technically valid but practically unreliable signals.

Components: liquidity (30%), history depth (20%), turnover stability (15%), sector confirmation (20%), data completeness (15%).

**The confidence score does not affect the signal label directly** (except STRONG BUY, which requires `confidence >= 50`). It is surfaced to the user to indicate how much weight to give the signal when making actual decisions.

---

## Why Cross-Sectional Scoring?

The rotation score is a percentile rank composite, not a fixed-threshold composite. This means:

- The question being answered is always **"what is the best opportunity right now, given what else is available?"** — not "has this ETF passed an absolute threshold?"
- An ETF in a rising market with moderate RS will score higher than an ETF in a falling market with the same absolute RS, because its peers have weaker RS
- When everything is selling off, the ETF that is falling least will still show relatively positive RS and pressure — which is correct behaviour for a rotation system

This is why signals can change week-to-week even when an individual ETF's metrics haven't changed much: the cross-section has moved around it.

---

## What Footprints Does NOT Try to Do

- **Predict tops and bottoms** — it responds to confirmed trend and accumulation changes, always with some lag but with cross-sectional confirmation
- **Forecast macro events** — it reads the price signal of macro events, not the events themselves
- **Replace professional advice** — Footprints is a personal decision-support tool
- **Implement a regime filter** — there is no macro regime overlay in the current engine. The user applies their own macro judgment to the signal outputs

---

## Academic References

| Concept | Reference |
|---------|-----------|
| Momentum premium | Jegadeesh & Titman (1993); AQR Capital momentum research |
| Moving average signals | Faber (2007) "A Quantitative Approach to Tactical Asset Allocation" — 10-month MA model; Footprints adapts this to 20-week (≈ 5 month) and 100-week (≈ 2 year) weekly equivalents |
| Volume/pressure confirmation | O'Neil CANSLIM — volume confirmation of breakouts and distribution phases |
| CLV-based accumulation/distribution | Larry Williams, Marc Chaikin — Chaikin Money Flow uses same CLV × volume principle |
| Vol-adjusted RS | AQR momentum factor research; Sharpe ratio-style RS normalisation |

Faber (2007) is the most directly relevant reference: a 10-month moving average applied to asset class indices, with a simple "invest when above, exit when below" rule, produced near-equity returns with materially lower drawdowns over 100+ years of data. Footprints extends this with additional cross-sectional KPIs and a more granular rotation framework.
