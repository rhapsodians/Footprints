# Footprints v2.0 — AI Context File

> **Purpose**: Paste this file at the start of a new Claude chat to restore full context.  
> **Update**: Ask Claude to regenerate this file after any significant session.  
> **Last updated**: 2026-03-21

---

## What This Is

Footprints is a personal pension fund rotation signal tool built by Joe. It tracks 56 LSE-listed ETFs as proxies for pension fund allocations across L&G and Irish Life. It computes weekly relative-strength rotation signals and presents them via a Flask web app.

---

## Deployment Stack

| Layer | Detail |
|---|---|
| Language | Python 3.12 / Flask |
| Database | SQLite (`footprints.db`) |
| Frontend | Jinja2 templates, vanilla JS, Chart.js 4.4.1, IBM Plex Mono/Sans |
| Mac project | `/Users/joe/Library/CloudStorage/Dropbox/Investing/Footprints v2/` |
| Git repo | `https://github.com/rhapsodians/Footprints/` |
| Production | PythonAnywhere — `footprints.pythonanywhere.com` |
| Deploy flow | Edit on Mac → git push → git pull on PA → touch wsgi.py |

---

## Key Files

```
footprints2/
├── server.py          # Flask routes, ETF_DESC dict, ETF_URLS dict
├── db.py              # All database access functions
├── engine.py          # Signal computation (weekly_v2_0 model)
├── config.py          # Constants — SECTOR_LABEL, signal thresholds, BASE_TICKER
├── footprints.db      # SQLite — golden source always on Mac
└── templates/
    ├── base.html      # Nav, CSS variables, theme toggle
    ├── home.html      # Landing page with nav tiles
    ├── dashboard.html # Signal cards + RHS slide-in detail panel
    ├── heatmap.html   # KPI heatmap table + sector overview tiles
    ├── universe.html  # ETF descriptions, sidebar, detail panel, factsheet links
    ├── entry.html     # LSEG bulk import, recompute trigger
    ├── history.html   # Signal change log
    ├── guide.html     # KPI explanations
    └── admin.html     # ETF management (add/delete)
```

---

## Design System

- **Theme**: Dark (`--bg: #080a0d`), light mode togglable
- **Fonts**: IBM Plex Mono (data/UI) + IBM Plex Sans (body text)
- **CSS variables** defined in `base.html` — always use these, never hardcode colours
- **Signal colours**: `--sig-sb` (green), `--sig-ea` (yellow), `--sig-ah` (blue), `--sig-nt` (grey), `--sig-ex` (red)
- **Heatmap pattern**: `.hm-controls` control band, `.ctrl-lbl` (110px), `.chip` buttons — reused in Universe page
- **Page headers**: `.page-title` / `.page-subtitle` from base.html

---

## Signal Model (weekly_v2_0)

- **Benchmark**: `VWRP.L` (Vanguard FTSE All-World) — all RS calculated against this
- **Frequency**: Weekly (Friday close)
- **Signals**: STRONG BUY, EARLY ACCUMULATION, ACCUMULATING/HOLD, NEUTRAL, EXIT/DISTRIBUTION
- **Key thresholds**: rotation_score ≥ 72 = STRONG BUY, ≥ 60 = ACCUM, ≤ 35 = EXIT
- **Engine**: `engine.run_engine(as_of_date=)` clips prices to ≤ that date before computing

### V2 field name aliases (important — dashboard JS expects these)
`_enrich_signals()` in server.py maps:
- `rs20_raw * 100` → `rs20_pct`
- `pressure_20w` → `crdp20`
- `turnover_ratio_20_100` → `dv_surprise`
- `trend_score_raw` → `trend`

**Always call `_enrich_signals()` before returning signal data to JS.**

---

## API Endpoints

| Route | Notes |
|---|---|
| `GET /api/signals` | Lightweight — all 56 ETF signals, no chart data (~107KB) |
| `GET /api/signals/<ticker>` | Single ETF with weekly chart arrays — enriched. Used by Universe detail panel |
| `GET /api/prices/<ticker>` | Full OHLCV history for history modal |

---

## ETF Universe — 56 Active ETFs

| Ticker | Sector | Full Name |
|---|---|---|
| LGAG.L | APAC | L&G Asia Pacific Ex Japan Equity UCITS ETF USD Acc |
| VDPG.L | APAC | Vanguard Dev Asia-Pac ex-Jpn |
| SWDA.L | BASE | iShares Core MSCI World UCITS ETF USD (Acc) |
| VHVG.L | BASE | Vanguard FTSE Developed World UCITS ETF USD A |
| VWRP.L | BASE | Vanguard FTSE All-World ← RS BENCHMARK |
| AGHG.L | BOND | Amundi Core Gl Aggregate Bd UCITS ETF GBP Hgd Dist |
| AMGAGG.L | BOND | Amundi Core Global Aggregate Bond |
| INXG.L | BOND | iShares £ Index-Linked Gilts UCITS ETF GBP Dist |
| IS15.L | BOND | iShares £ Corp Bond 0-5yr UCITS ETF GBP (Dist) |
| ITPS.L | BOND | iShares $ TIPS UCITS ETF USD (Acc) |
| LYCSH2.L | CASH | Amundi Smart Overnight Rtn UCITS ETF GBP Hgd Acc |
| IASH.L | CHINA | iShares MSCI China A UCITS ETF USD (Acc) |
| SGLN.L | COMM | iShares Physical Gold ETC |
| SSLN.L | COMM | iShares Physical Silver ETC |
| IUCS.L | CONS | iShares S&P 500 Consumer Staples Sector UCITS ETF |
| WCOD.L | CONS | StSt SPDR MSCI World Con Discretionary UCITS ETF |
| DFND.L | DEF | iShares Global Aerospace & Def |
| DFNG.L | DEF | VanEck Defense |
| NATP.L | DEF | Future of Defence ETF |
| EXCS.L | EM | iShares MSCI EM ex-China UCITS ETF USD Acc |
| VFEM.L | EM | Vanguard FTSE Emerging Mkts UCITS ETF USD Dis |
| VGVFEG.L | EM | Vanguard FTSE Emerging Mkts UCITS ETF USD Acc |
| IESU.L | ENERGY | iShares S&P 500 Energy Sector UCITS ETF USD (Acc) |
| INRG.L | ENERGY | iShares Global Clean Energy Trnstn UCITS ETF USD D |
| VEUA.L | EUR | Vanguard Developed Europe |
| XWFS.L | FIN | Xtrackers MSCI World Financials UCITS 1C ETF |
| ISWD.L | GLOBAL | iShares MSCI World Islamic UCITS ETF USD (Dist) |
| ISWSML.L | GLOBAL | iShares MSCI World Small Cap UCITS ETF USD (Acc) |
| IWFQ.L | GLOBAL | iShares MSCI World Quality |
| IWVL.L | GLOBAL | iShares Edge MSCI Wld Val Fctr UCITS ETF USD A |
| BTEK.L | HEALTH | iShares NASDAQ Biotech |
| DRDR.L | HEALTH | iShares Healthcare Innovation |
| IUHC.L | HEALTH | iShares S&P 500 Health Care Sctr UCITS ETF USD A |
| ISIIND.L | INDIA | iShares MSCI India UCITS USD (Acc) ETF |
| IUIS.L | INDUS | iShares S&P 500 Industrials Sector UCITS ETF USD (Acc) |
| VJPB.L | JAP | Vanguard FTSE Japan |
| GIGB.L | MINING | VanEck S&P Global Mining |
| IAUP.L | MINING | iShares Gold Producers UCITS ETF USD (Acc) |
| V3NB.L | NAM | Vanguard ESG N America All Cap UCITS ETF USD Acc |
| VNRG.L | NAM | Vanguard North America |
| HPROP.L | PROP | HSBC FTSE EPRA NAREIT Dev |
| IDWP.L | PROP | iShares Dvlp Mrkts Prop Yld UCITS ETF USD Dist |
| AINF.L | TECH | iShares AI Infrastructure |
| BOTZ.L | TECH | Global X Robotics & AI |
| IITU.L | TECH | iShares S&P500 Info Tech |
| RBOT.L | TECH | iShares Robotics (GBP) — duplicate of RBTX (GBP share class) |
| RBTX.L | TECH | iShares Robotics (USD) |
| SMGB.L | TECH | VanEck Semiconductors |
| CUKS.L | UK | iShares MSCI UK Small Cap UCITS ETF GBP (Acc) |
| FTAL.L | UK | StSt SPDR FTSE UK All Share UCITS ETF Acc |
| VUKG.L | UK | Vanguard FTSE 100 |
| CNX1.L | US | iShares NASDAQ 100 |
| EQGB.L | US | Invesco EQQQ NASDAQ-100 (GBP Hdg) — duplicate of CNX1 |
| RIUS.L | US | L&G US ESG Paris Aligned UCITS ETF USD Acc |
| VUSA.L | US | Vanguard S&P 500 |
| IUUS.L | UTILS | iShares S&P 500 Utilities Sector UCITS ETF USD (Acc) |

### Sector Labels (config.py SECTOR_LABEL)
BASE=Global Benchmark, US=United States, NAM=North America, UK=United Kingdom, EUR=Europe, JAP=Japan, APAC=Asia-Pacific, EM=Emerging Markets, INDIA=India, CHINA=China, TECH=Technology, HEALTH=Healthcare, DEF=Defence, FIN=Financials, INDUS=Industrials, UTILS=Utilities, ENERGY=Energy, CONS=Consumer, PROP=Real Estate, COMM=Commodities, MINING=Mining, BOND=Fixed Income, CASH=Cash & Money Market, GLOBAL=Global Thematic

---

## Pension Fund Proxies — 19 Funds

| Fund Code | Proxy ETF | Fund Name |
|---|---|---|
| IL-AMUNDIABSLRETURN | LYCSH2.L | Amundi Absolute Return Multi-Strategy |
| IL-AMUNDI_GOLD | SGLN.L | Amundi Physical Gold ETC Series P |
| IL-EUROPE | VEUA.L | Irish Life Indexed European Equity |
| IL-GLBL-BONDS | AGHG.L | Irish Life Amundi Global Aggregate Bond |
| IL-INFLATIONBOND | INXG.L | Indexed Inflation Linked Bond |
| LG-ACTIVE_GLOBAL | SWDA.L | L&G MT Active Global Equity |
| LG-ASIAPAC_EXJP | LGAG.L | L&G PMC Future World AsiaPacific ex Japan |
| LG-CORPBONDS | IS15.L | L&G PMC AAA-AA-A Corp Bond All Stocks |
| LG-EMGMKTS | VGVFEG.L | L&G MT Emerging Markets Index |
| LG-FUTURE_WLD_ASSET | IWVL.L | L&G MT Future World Multi-Asset |
| LG-GLBREALEST | IDWP.L | L&G MT Global Real Estate Equity |
| LG-GLOB-DEV | VHVG.L | L&G MT Global Developed Equity |
| LG-GLOBAL_ISLAMIC | ISWD.L | L&G PMC HSBC Islamic Global Equity Index |
| LG-NORTHAMERICA | V3NB.L | L&G PMC Future World North America |
| LG-SHRTBOND | IS15.L | L&G MT Short Dated Bond Index Fund |
| LG-SMALLCOMP | ISWSML.L | L&G MT Smaller Companies Index |
| LG-UKEQUITY | FTAL.L | L&G PMC UK Equity Index 3 |
| LG-UKSMLCAPS | CUKS.L | L&G MT UK Smaller Companies |
| LG-WRLD-EXUK | VWRP.L | L&G PMC Future World Europe ex UK |

---

## Current Signal State (as of 2026-03-13)
- 56 ETFs with signals for 2026-03-13
- 38 ETFs with signals for 2026-03-06 (pre-expansion)
- Weekly LSEG data entered manually via Entry page bulk import

---

## Pages / Routes

| Route | Nav label | Purpose |
|---|---|---|
| `/` | Home | Landing page with signal summary + nav tiles |
| `/entry` | Entry | Bulk LSEG CSV import, recompute trigger |
| `/dashboard` | Dashboard | ETF signal cards, RHS slide-in detail panel |
| `/heatmap` | Heatmap | KPI table (all metrics) + sector overview tiles |
| `/history` | History | Signal change log |
| `/universe` | Universe | ETF descriptions, sidebar nav, factsheet links, detail panel |
| `/guide` | Guide | KPI plain-English explanations |
| `/admin` | Admin | Add/delete ETFs, two-step delete confirmation |
| `/api/signals` | — | JSON: all 56 signals (lightweight, no chart data) |
| `/api/signals/<ticker>` | — | JSON: single ETF signal + weekly chart arrays (enriched) |
| `/api/prices/<ticker>` | — | JSON: full OHLCV history |

---

## Known Pending Items / Flagged Issues

- **RBOT.L** and **EQGB.L** are duplicates (same fund/index as RBTX.L and CNX1.L respectively) — candidate for deletion
- **LG-WRLD-EXUK** fund name says "Europe ex-UK" but is mapped to VWRP.L (global All-World) — mapping may be wrong, needs verification against actual fund holdings
- **IL-AMUNDIABSLRETURN** is an Absolute Return fund proxied by LYCSH2.L (cash) — imperfect proxy, no better LSE-listed alternative exists
- No signal data before 2026-02-20 (full 56-ETF history only from 2026-03-13)

---

## Development Conventions

- **DB changes**: Always apply targeted SQL on Mac first, then replicate on PythonAnywhere. Never wholesale replace the DB file from sandbox to Mac.
- **Golden source**: `footprints.db` on Mac is always authoritative. Upload to Claude when starting a new session for DB-related work.
- **Config sectors**: When adding new sectors, update `config.py` SECTOR_LABEL dict AND the dashboard.html `ORDER` array in the sector filter JS.
- **Signal field names**: Use `_enrich_signals()` aliases (`rs20_pct`, `crdp20`, `dv_surprise`) in all JS. Raw v2 names (`rs20_raw`, `pressure_20w`, `turnover_ratio_20_100`) are in the DB only.
- **Fixed position elements** (modals, slide panels): Must be in `{% block scripts %}`, NOT `{% block content %}`. The content block is wrapped in a `</div>` in base.html that creates a stacking context.
- **Heatmap table width**: `.page{max-width:none}` must be set in heatmap and universe block head to override base.html's 1600px cap.

---

## How to Start a New Chat

1. Paste this file into the chat (or upload it)
2. Optionally upload `footprints.db` if doing DB/signal work
3. Say what you want to work on

Claude will be fully oriented without needing to re-explain the architecture.
