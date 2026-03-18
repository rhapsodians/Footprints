# 05 — Pension Proxy Methodology

> **Audit status:** Verified against server.py (summary route, _build_fund_rows, _proxy_narrative, _stance), db.py (pension tables), and config.py.

## The Problem

Retail pension platforms (L&G WorkSave, Irish Life) provide no real-time pricing, no technical analysis tools, and no signal infrastructure. Fund prices are T+1 or T+2 delayed. The platform is designed for passive, set-and-forget investors.

**Solution:** Map each pension fund to one or more liquid LSE-traded ETF proxies. Run the full Footprints signal engine across those proxies. Use the resulting signals to inform fund switching decisions on the pension platform.

---

## Two Providers

The system manages pension funds for two providers simultaneously, distinguished by the `code` field prefix in `pension_funds`:

| Prefix | Provider |
|--------|---------|
| `LG` | L&G WorkSave (UK occupational pension) |
| `IL` | Irish Life (Irish pension/retirement product) |

Both providers use the same DB tables. The `summary.py` route splits them on code prefix:

```python
lg_map = {fid: fd for fid, fd in fund_map.items() if fd["code"].startswith("LG")}
il_map = {fid: fd for fid, fd in fund_map.items() if fd["code"].startswith("IL")}
```

The Summary page renders each provider as a separate section.

---

## Database Structure

### `pension_funds` table

```sql
id            INTEGER PRIMARY KEY AUTOINCREMENT
code          TEXT UNIQUE    -- e.g. "LG001", "IL002"
name          TEXT           -- full fund name
display_order INTEGER
```

### `pension_etf_map` table

```sql
fund_id  INTEGER  -- FK → pension_funds.id
ticker   TEXT     -- FK → etf_meta.ticker (implicitly)
PRIMARY KEY (fund_id, ticker)
```

**Many-to-many:** A single pension fund can map to multiple ETF proxies (e.g. a broad global equity fund might map to both VWRP.L and SWDA.L). A single ETF can be the proxy for multiple funds.

### Admin UI Management

Funds and proxy mappings are managed entirely through the Admin page UI (route `/admin`). There is no CSV import for pension data. Functions in `db.py`:

- `add_pension_fund(code, name)` → insert fund
- `remove_pension_fund(fund_id)` → delete fund and all its proxy mappings
- `add_pension_proxy(fund_id, ticker)` → link ETF to fund
- `remove_pension_proxy(fund_id, ticker)` → unlink ETF from fund

---

## Principles of ETF Proxy Selection

1. **Index alignment** — the proxy ETF should track the same or near-identical index as the underlying pension fund
2. **LSE-listed, GBP-priced** — avoids FX translation artefacts in signal comparison; all tickers should use `.L` suffix
3. **Sufficient liquidity** — `avg_turn_20w` should be above `LIQUIDITY_FULL` (£5m/week) for HIGH confidence; low-liquidity proxies will receive LOW or MODERATE confidence buckets
4. **Physical replication preferred** — synthetic ETFs introduce swap counterparty risk that could decouple proxy from fund
5. **VWRP.L must be in the universe** — as the default benchmark, it must have price data or RS will be NULL for all default-benchmark ETFs

---

## Signal Aggregation for Pension Funds

### How a Fund's Stance is Determined

Each pension fund's "stance" is derived from the signals of all its proxy ETFs in aggregate, via `_build_fund_rows()` in `server.py`.

**Signal ranking order** (used for sorting within a fund's proxy list):

```python
SIG_ORDER = {
    SIG_STRONG_BUY:    0,   # "STRONG BUY"
    SIG_EARLY_ACCUM:   1,   # "EARLY ACCUMULATION"
    SIG_ACCUM:         2,   # "ACCUMULATING/HOLD"
    "NEUTRAL":         3,
    SIG_EXIT:          4,   # "EXIT/DISTRIBUTION"
}
```

**Stance determination** via `_stance(buy_n, exit_n, neu_n, total)`:

| Condition | Stance |
|-----------|--------|
| All proxies BUY/ACCUM | POSITIVE |
| All proxies EXIT | NEGATIVE |
| BUY > EXIT AND buy_n ≥ 60% of total | POSITIVE |
| exit_n ≥ 50% of total | NEGATIVE |
| EXIT > BUY AND exit_n ≥ 40% | CAUTIOUS |
| buy_n > 0 AND exit_n == 0 | MILD POS |
| exit_n > 0 AND buy_n == 0 | MILD NEG |
| Otherwise | MIXED |

**Stance display order** (funds sorted by this on Summary page):

```
POSITIVE → MILD POS → MIXED → CAUTIOUS → MILD NEG → NEGATIVE
```

### Summary Page — Now Part of `/heatmap`

> **The `/summary` route no longer exists.** The pension fund summary was merged into the `/heatmap` route in the live server. `heatmap.html` now renders both the ETF heatmap and the pension fund summary on the same page.

The live `/heatmap` route passes all pension summary data to `heatmap.html`:
- `lg_rows` — L&G WorkSave funds sorted by stance
- `il_rows` — Irish Life funds sorted by stance
- `notable` — non-pension ETFs with STRONG BUY, EARLY ACCUMULATION, or EXIT signals
- `portfolio` — `{total, strong_buy, early_acc, accum, neutral, exit, high_conf, transitions}`

The underlying pension logic (`_build_fund_rows`, `_stance`) remains unchanged — only the delivery mechanism moved from a separate page to the heatmap page.

---

## Proxy Narrative Generation

For each proxy ETF on the Summary page, `_proxy_narrative()` in `server.py` generates a 5-sentence plain-English narrative. This is pre-computed server-side (not AI-generated at runtime). Structure:

1. **Overall verdict** — signal label + rotation score vs 50-point threshold
2. **Momentum / RS** — 20-week RS direction, magnitude, percentile rank; RS acceleration direction
3. **Pressure / flow** — 20-week pressure character (strongly positive → strongly negative); turnover z-score note if elevated
4. **Trend** — trend score 0–4 mapped to one of 5 fixed descriptions
5. **Sector context + signal change** — sector score and confirmation; notes any signal transition this week

**Trend score descriptions (used in sentence 4):**

| Score | Text |
|-------|------|
| 4 | "Price is above both the 20-week and 100-week moving averages, and the shorter average is above the longer — a fully aligned bullish trend structure." |
| 3 | "Price is above both key moving averages, though the trend structure is not yet fully aligned." |
| 2 | "Price is above one moving average but below another, indicating a mixed or transitional trend." |
| 1 | "Price is below the key moving averages, suggesting the trend remains under pressure." |
| 0 | "Price is below both moving averages and trend structure is bearish." |

---

## Weekly Decision Workflow

Each week after updating prices and recomputing signals:

1. Navigate to `/summary`
2. Review LG and IL fund stances — which have moved to CAUTIOUS/NEGATIVE?
3. For any fund with NEGATIVE stance or recent NEUTRAL→EXIT transition across its proxies, consider switching to a defensive/cash option
4. For POSITIVE stance funds with recent signal upgrades, consider increasing allocation
5. Review "Notable Signals" section for non-pension ETFs showing STRONG BUY or EXIT — these inform broader macro context

### Switch Execution Constraints (L&G WorkSave)

- Switch notice: submit before midday cut-off for same-day pricing
- Settlement: T+1 to T+2; plan 2–3 business days ahead
- No CGT on pension fund switches (within pension wrapper)
- Check platform rules on maximum switches per year

### Switch Execution Constraints (Irish Life)

- Confirm current cut-off times and settlement periods with Irish Life directly — these vary by product type
- No CGT on pension fund switches within the ARF/PRSA/occupational pension wrapper

---

## Important Proxy Limitations

**VWRP.L as benchmark AND proxy:** VWRP.L is both the default RS benchmark and likely a proxy for a global equity pension fund. Its RS vs itself will always be zero. This is correct behaviour — it is the market baseline. Other ETFs' RS is measured against VWRP.L, which is meaningful.

**Sector ETFs as proxies:** If a pension fund has a broad global mandate but the only available proxy is a sector ETF (e.g. technology), the signal will capture sector-level, not fund-level, behaviour. Interpret with appropriate caution.

**No Track A / Track B structure in current code:** The prior documentation described a Track A (equity growth) and Track B (defensive) rotation framework. This structure is **not implemented in the current codebase**. The system tracks all funds equally; the user applies their own rotation decision logic based on stance outputs.

**No macro regime filter in current code:** The prior documentation described a macro regime overlay (risk-on / caution / risk-off). This does **not exist** in the current engine. All signal outputs are purely quantitative and cross-sectional. Macro regime interpretation is the user's responsibility, informed by the signals.

---

## Appendix B — Pension Fund & Proxy Mapping Reference

> **Source:** Extracted directly from `footprints.db` (`pension_funds` + `pension_etf_map` tables), March 2026.  
> **20 funds total: 15 L&G WorkSave (LG-), 5 Irish Life (IL-).**  
> Keep current whenever funds or proxies are added/removed via Admin. Re-extract with:
> ```sql
> SELECT pf.code, pf.name, pem.ticker
> FROM pension_funds pf
> JOIN pension_etf_map pem ON pf.id = pem.fund_id
> ORDER BY pf.code, pem.ticker;
> ```

### L&G WorkSave Funds (15 funds, `LG-` prefix)

| Code | Fund Name | Proxy ETF | Proxy Description |
|------|-----------|-----------|-------------------|
| LG-ACTIVE_GLOBAL | L&G MT Active Global Equity | SWDA.L | iShares Core MSCI World |
| LG-APAC-EXJP | PMC Future World AsiaPacific(ex Japan)Eq Ind 3 | LGAG.L | L&G Asia Pacific Ex Japan |
| LG-ASIAPAC_EXJP | L&G PMC Future World AsiaPacific(ex Japan)Eq Ind 3 | LGAG.L | L&G Asia Pacific Ex Japan |
| LG-CORPBONDS | L&G PMC AAA-AA-A Corp Bond All Stocks Index 3 | IS15.L | iShares £ Corp Bond 0-5yr |
| LG-EMGMKTS | L&G MT Emerging Markets Index | VGVFEG.L | Vanguard FTSE Emerging Mkts |
| LG-FUTURE_WLD_ASSET | L&G MT Future World Multi-Asset | MAGG.L | iShares Growth Portfolio GBP Hdg |
| LG-GLBREALEST | L&G MT Global Real Estate Equity | IDWP.L | iShares Dvlp Mrkts Prop Yld |
| LG-GLOB-DEV | L&G MT Global Developed Equity | VHVG.L | Vanguard FTSE Developed World |
| LG-GLOBAL_ISLAMIC | L&G PMC HSBC Islamic Global Equity Index Fund 3 | DBXWD1.L | Xtrackers MSCI World Swap |
| LG-NORTHAMERICA | L&G PMC Future World North America Eq Index Fund 3 | V3NB.L | Vanguard ESG N America All Cap |
| LG-SHRTBOND | L&G MT Short Dated Bond Index Fund | IS15.L | iShares £ Corp Bond 0-5yr |
| LG-SMALLCOMP | L&G MT Smaller Companies Index | ISWSML.L | iShares MSCI World Small Cap |
| LG-UKEQUITY | L&G PMC UK Equity Index 3 | FTAL.L | SPDR FTSE UK All Share |
| LG-UKSMLCAPS | L&G MT UK Smaller Companies | CUKS.L | iShares MSCI UK Small Cap |
| LG-WRLD-EXUK | L&G PMC Future World Europe(ex UK) Eq Index Fund 3 | VWRP.L | Vanguard FTSE All-World |

### Irish Life Funds (5 funds, `IL-` prefix)

| Code | Fund Name | Proxy ETF | Proxy Description |
|------|-----------|-----------|-------------------|
| IL-AMUNDIABSLRETURN | Amundi Absolute Return Multi-Strategy | AMGAGG.L | Amundi Core Global Aggregate Bond |
| IL-AMUNDI_GOLD | Amundi Physical Gold ETC Series P | SGLN.L | iShares Physical Gold ETC |
| IL-EUROPE | Irish Life Indexed European Equity P | VEUA.L | Vanguard Developed Europe |
| IL-GLBL-BONDS | Irish Life Amundi Global Aggregate Bond Series P | AGHG.L | Amundi Core Gl Aggregate Bd GBP Hgd |
| IL-INFLATIONBOND | Indexed Inflation Linked Bond | LYCSH2.L | Amundi Smart Overnight Rtn GBP Hgd |

**Proxy notes:**
- **LG-APAC-EXJP and LG-ASIAPAC_EXJP** map to the same proxy (LGAG.L) — these appear to be two entries for the same underlying fund; the duplicate should be reviewed via Admin.
- **LG-CORPBONDS and LG-SHRTBOND** both map to IS15.L — correct, as IS15.L (iShares £ Corp Bond 0-5yr) is the appropriate proxy for both short-dated and IG corp bond mandates.
- **LG-GLOBAL_ISLAMIC** maps to DBXWD1.L (Xtrackers MSCI World Swap) — this is a conventional fund, not a Shariah-screened ETF. This proxy has index alignment (MSCI World) but does not replicate the Islamic screening of the underlying fund. Interpret signals with caution for this fund.
- **LG-WRLD-EXUK** maps to VWRP.L (All-World including UK) — minor mismatch vs an ex-UK mandate; acceptable as directional proxy.
- **IL-INFLATIONBOND** maps to LYCSH2.L (Amundi Smart Overnight Return — a cash/overnight rate ETF) — this is a poor proxy for an inflation-linked bond fund. Signals should be treated as indicative only.
