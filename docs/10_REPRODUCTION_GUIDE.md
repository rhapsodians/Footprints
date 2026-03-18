# 10 — Reproduction Guide

> **Audit status:** Rewritten from scratch. Prior version had wrong entry point (`app.py`), wrong data layer (CSV), wrong signal labels, and a fabricated `signals.py` reference implementation. All corrected.

---

## Prerequisites

- Python 3.10+ (Python 3.12 recommended — matches PythonAnywhere current default)
- Git
- PythonAnywhere account (free tier workable; hacker tier recommended for scheduled tasks)
- GitHub access to `https://github.com/rhapsodians/Footprints`
- LSEG data access for price history (see Data Seeding section)

---

## Option A — Restore from Existing Deployment

Use when PythonAnywhere is already running and you need to reset, redeploy, or recover.

```bash
# On PythonAnywhere Bash console:
cd ~/Footprints
git fetch --all
git checkout main       # or: git checkout v2.0.0 if tagged

# If requirements may have changed:
pip install --user -r requirements.txt

# Reload the web app via PythonAnywhere Web tab UI
# (or use the PA API if you have a scheduled reload script)
```

The `footprints.db` file is **not** in the repo. If it exists on PythonAnywhere from the previous deployment, it is preserved across git pulls. If it has been lost, see Data Seeding below.

---

## Option B — Fresh Clone and Local Development

```bash
git clone https://github.com/rhapsodians/Footprints.git
cd Footprints
pip install -r requirements.txt

# Set the secret key (use any string for local dev):
export FP2_SECRET_KEY="local-dev-secret"

# Start the app:
python server.py
# Or: bash start_footprints.sh

# Navigate to: http://localhost:5000
# On first run, db.init_schema() creates footprints.db automatically
```

At this point the app starts but has no data. Proceed to Data Seeding.

---

## Option C — Fresh PythonAnywhere Deployment

### Step 1: Create the Web App

1. Log into PythonAnywhere → Web tab → Add new web app
2. Choose: Manual configuration → Python 3.12
3. Note the WSGI config file path (e.g. `/var/www/username_pythonanywhere_com_wsgi.py`)

### Step 2: Clone the Repository

```bash
# In PythonAnywhere Bash console:
git clone https://github.com/rhapsodians/Footprints.git ~/Footprints
cd ~/Footprints
pip install --user -r requirements.txt
```

### Step 3: Configure the WSGI File

Edit the PythonAnywhere WSGI config file to point to the repo's `wsgi.py`:

```python
# Contents of the PythonAnywhere WSGI config file:
import sys
sys.path.insert(0, '/home/<your_username>/Footprints')

from wsgi import app as application
```

Alternatively, if `wsgi.py` in the repo already handles this correctly, set the WSGI file to simply:
```python
from wsgi import app as application
```

### Step 4: Set Environment Variable

In PythonAnywhere Web tab → Environment variables section:
```
FP2_SECRET_KEY = <your-secret-key>
```

Use a strong random string, e.g. from `python -c "import secrets; print(secrets.token_hex(32))"`.

### Step 5: Reload and Verify

Click Reload in the Web tab. Navigate to your app URL. You should see the Home page (with zero signals — the DB is empty until data is seeded).

---

## Data Seeding

The `footprints.db` is not in the repo. After a fresh deployment, the database schema is created automatically by `db.init_schema()` on first run, but it contains no ETF metadata, no prices, and no signals. You must seed it.

### Step 1: Seed the ETF Universe

There is no automated ETF seeder in the repo. Options:

**Option A — Restore from backup:**
If you have a previous `footprints.db`, copy it to the app directory. This is the fastest recovery path.

```bash
# Example: upload via PythonAnywhere file manager or scp
scp footprints.db username@ssh.pythonanywhere.com:~/Footprints/
```

**Option B — Build from scratch via Admin UI:**
1. Navigate to `/admin`
2. Use "Add ETF" form for each ETF: Ticker, Name, Sector (dropdown), Display Order
3. Add `VWRP.L` first — it is both the RS benchmark and a signal instrument

**Option C — Direct SQL seed (fastest from-scratch approach):**

Use the SQL below to seed all 43 ETFs directly into `footprints.db`. Run in a SQLite client or via Python on PythonAnywhere:

```bash
# On PythonAnywhere:
cd ~/footprints2
python3 -c "
import sqlite3
conn = sqlite3.connect('footprints.db')
etfs = [
    (1,  'AGHG.L',   'Amundi Core Gl Aggregate Bd UCITS ETF GBP Hgd Dist', 'BOND',   'VWRP.L'),
    (2,  'AINF.L',   'iShares AI Infrastructure',                           'TECH',   'VWRP.L'),
    (3,  'BOTZ.L',   'Global X Robotics & AI',                              'TECH',   'VWRP.L'),
    (4,  'BTEK.L',   'iShares NASDAQ Biotech',                              'HEALTH', 'VWRP.L'),
    (5,  'CNX1.L',   'iShares NASDAQ 100',                                  'US',     'VWRP.L'),
    (6,  'CUKS.L',   'iShares MSCI UK Small Cap UCITS ETF GBP (Acc)',       'UK',     'VWRP.L'),
    (7,  'DBXWD1.L', 'Xtrackers MSCI World Swap UCITS ETF 1D',             'BASE',   'VWRP.L'),
    (8,  'DFND.L',   'iShares Global Aerospace & Def',                      'DEF',    'VWRP.L'),
    (9,  'DFNG.L',   'VanEck Defense',                                      'DEF',    'VWRP.L'),
    (10, 'DRDR.L',   'iShares Healthcare Innovation',                       'HEALTH', 'VWRP.L'),
    (11, 'EQGB.L',   'Invesco EQQQ NASDAQ-100 (GBP Hdg)',                   'US',     'VWRP.L'),
    (12, 'FTAL.L',   'StSt SPDR FTSE UK All Share UCITS ETF Acc',           'UK',     'VWRP.L'),
    (13, 'GIGB.L',   'VanEck S&P Global Mining',                            'MINING', 'VWRP.L'),
    (14, 'HPROP.L',  'HSBC FTSE EPRA NAREIT Dev',                           'PROP',   'VWRP.L'),
    (15, 'IAUP.L',   'iShares Gold Producers UCITS ETF USD (Acc)',           'COMM',   'VWRP.L'),
    (16, 'IDWP.L',   'iShares Dvlp Mrkts Prop Yld UCITS ETF USD Dist',     'PROP',   'VWRP.L'),
    (17, 'IITU.L',   'iShares S&P500 Info Tech',                            'US',     'VWRP.L'),
    (18, 'IS15.L',   'iShares £ Corp Bond 0-5yr UCITS ETF GBP (Dist)',      'BOND',   'VWRP.L'),
    (19, 'ISWSML.L', 'iShares MSCI World Small Cap UCITS ETF USD (Acc)',    'GLOBAL', 'VWRP.L'),
    (20, 'IWDP.L',   'iShares Dev Mkts Property',                           'PROP',   'VWRP.L'),
    (21, 'IWFQ.L',   'iShares MSCI World Quality',                          'GLOBAL', 'VWRP.L'),
    (22, 'LGAG.L',   'L&G Asia Pacific Ex Japan Equity UCITS ETF USD Acc',  'APAC',   'VWRP.L'),
    (23, 'MAGG.L',   'iShares Growth Portfolio UCITS ETF GBP Hedged Acc',   'GLOBAL', 'VWRP.L'),
    (24, 'NATP.L',   'Future of Defence ETF',                               'DEF',    'VWRP.L'),
    (25, 'RBOT.L',   'iShares Robotics (GBP)',                              'TECH',   'VWRP.L'),
    (26, 'RBTX.L',   'iShares Robotics (USD)',                              'TECH',   'VWRP.L'),
    (27, 'RIUS.L',   'L&G US ESG Paris Aligned UCITS ETF USD Acc',          'US',     'VWRP.L'),
    (28, 'SGLN.L',   'iShares Physical Gold ETC',                           'COMM',   'VWRP.L'),
    (29, 'SMGB.L',   'VanEck Semiconductors',                               'TECH',   'VWRP.L'),
    (30, 'SSLN.L',   'iShares Physical Silver ETC',                         'COMM',   'VWRP.L'),
    (31, 'SWDA.L',   'iShares Core MSCI World UCITS ETF USD (Acc)',         'BASE',   'VWRP.L'),
    (32, 'V3NB.L',   'Vanguard ESG N America All Cap UCITS ETF USD Acc',    'NAM',    'VWRP.L'),
    (33, 'VDPG.L',   'Vanguard Dev Asia-Pac ex-Jpn',                        'APAC',   'VWRP.L'),
    (34, 'VEUA.L',   'Vanguard Developed Europe',                           'EUR',    'VWRP.L'),
    (35, 'VGVFEG.L', 'Vanguard FTSE Emerging Mkts UCITS ETF USD Acc',       'EM',     'VWRP.L'),
    (36, 'VHVG.L',   'Vanguard FTSE Developed World UCITS ETF USD A',       'BASE',   'VWRP.L'),
    (37, 'VJPB.L',   'Vanguard FTSE Japan',                                 'JAP',    'VWRP.L'),
    (38, 'VNRG.L',   'Vanguard North America',                              'NAM',    'VWRP.L'),
    (39, 'VUKG.L',   'Vanguard FTSE 100',                                   'UK',     'VWRP.L'),
    (40, 'VUSA.L',   'Vanguard S&P 500',                                    'US',     'VWRP.L'),
    (41, 'VWRP.L',   'Vanguard FTSE All-World',                             'BASE',   'VWRP.L'),
    (99, 'AMGAGG.L', 'Amundi Core Global Aggregate Bond',                   'BOND',   'VWRP.L'),
    (99, 'LYCSH2.L', 'Amundi Smart Overnight Rtn UCITS ETF GBP Hgd Acc',    'BOND',   'VWRP.L'),
]
conn.executemany(
    'INSERT OR IGNORE INTO etf_meta (display_order,ticker,name,sector,benchmark_ticker,active,suspended) VALUES (?,?,?,?,?,1,0)',
    etfs
)
conn.commit()
print(f'Seeded {len(etfs)} ETFs')
conn.close()
"
```

**Option D — SQL seed for pension funds** (run after ETF seed):

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('footprints.db')

# Create pension tables if they don't exist (not created by init_schema)
conn.execute('''CREATE TABLE IF NOT EXISTS pension_funds (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT UNIQUE,
    name          TEXT,
    display_order INTEGER DEFAULT 99
)''')
conn.execute('''CREATE TABLE IF NOT EXISTS pension_etf_map (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id INTEGER REFERENCES pension_funds(id),
    ticker  TEXT
)''')
conn.commit()

funds = [
    ('LG-ACTIVE_GLOBAL',   'L&G MT Active Global Equity'),
    ('LG-APAC-EXJP',       'PMC Future World AsiaPacific(ex Japan)Eq Ind 3'),
    ('LG-ASIAPAC_EXJP',    'L&G PMC Future World AsiaPacific(ex Japan)Eq Ind 3'),
    ('LG-CORPBONDS',       'L&G PMC AAA-AA-A Corp Bond All Stocks Index 3'),
    ('LG-EMGMKTS',         'L&G MT Emerging Markets Index'),
    ('LG-FUTURE_WLD_ASSET','L&G Future World Global Assets'),
    ('LG-GLOB-DEV',        'L&G PMC Future World Global Equity Index 3'),
    ('LG-GLOBAL_ISLAMIC',  'L&G PMC Global Equity (Islamic) Index 3'),
    ('LG-GLBREALEST',      'L&G PMC Global Real Estate Index 3'),
    ('LG-NORTHAMERICA',    'L&G PMC North America Index 3'),
    ('LG-SHRTBOND',        'L&G PMC Short Dated Sterling Corp Bond Index 3'),
    ('LG-SMALLCOMP',       'L&G PMC World (Ex-UK) Smaller Companies Index 3'),
    ('LG-UKEQUITY',        'L&G PMC UK Equity Index 3'),
    ('LG-UKSMLCAPS',       'L&G PMC UK Smaller Companies Index 3'),
    ('LG-WRLD-EXUK',       'L&G PMC Future World Global Equity (Ex-UK) Index 3'),
    ('IL-AMUNDI_GOLD',     'Irish Life Amundi Physical Gold ETC'),
    ('IL-AMUNDIABSLRETURN','Irish Life Amundi Absolute Return'),
    ('IL-EUROPE',          'Irish Life MSCI Europe ETF'),
    ('IL-GLBL-BONDS',      'Irish Life Global Aggregate Bond'),
    ('IL-INFLATIONBOND',   'Irish Life Inflation Linked Bond'),
]
conn.executemany('INSERT OR IGNORE INTO pension_funds (code,name) VALUES (?,?)', funds)
conn.commit()

proxies = [
    ('LG-ACTIVE_GLOBAL',    'SWDA.L'),
    ('LG-APAC-EXJP',        'LGAG.L'),
    ('LG-ASIAPAC_EXJP',     'LGAG.L'),
    ('LG-CORPBONDS',        'IS15.L'),
    ('LG-EMGMKTS',          'VGVFEG.L'),
    ('LG-FUTURE_WLD_ASSET', 'MAGG.L'),
    ('LG-GLOB-DEV',         'VHVG.L'),
    ('LG-GLOBAL_ISLAMIC',   'DBXWD1.L'),
    ('LG-GLBREALEST',       'IDWP.L'),
    ('LG-NORTHAMERICA',     'V3NB.L'),
    ('LG-SHRTBOND',         'IS15.L'),
    ('LG-SMALLCOMP',        'ISWSML.L'),
    ('LG-UKEQUITY',         'FTAL.L'),
    ('LG-UKSMLCAPS',        'CUKS.L'),
    ('LG-WRLD-EXUK',        'VWRP.L'),
    ('IL-AMUNDI_GOLD',      'SGLN.L'),
    ('IL-AMUNDIABSLRETURN', 'AMGAGG.L'),
    ('IL-EUROPE',           'VEUA.L'),
    ('IL-GLBL-BONDS',       'AGHG.L'),
    ('IL-INFLATIONBOND',    'LYCSH2.L'),
]
# Get fund ids then insert mappings
for code, ticker in proxies:
    row = conn.execute('SELECT id FROM pension_funds WHERE code=?', (code,)).fetchone()
    if row:
        conn.execute('INSERT OR IGNORE INTO pension_etf_map (fund_id,etf_ticker) VALUES (?,?)', (row[0], ticker))
conn.commit()
print(f'Seeded {len(funds)} funds, {len(proxies)} mappings')
conn.close()
"
```

**Sector codes reference** (`config.SECTOR_LABEL`): `BASE`, `US`, `NAM`, `UK`, `EUR`, `JAP`, `APAC`, `EM`, `TECH`, `HEALTH`, `DEF`, `PROP`, `COMM`, `MINING`, `BOND`, `GLOBAL`, `OTHER`

### Step 2: Seed Pension Fund Mappings

1. Navigate to `/admin`
2. Scroll to pension funds section
3. Add each fund with its code (`LG001`, `IL001`, etc.) and full name
4. For each fund, add its proxy ETF ticker(s)

L&G funds use `LG` prefix; Irish Life funds use `IL` prefix. The Summary page splits on this prefix.

### Step 3: Import Historical Price Data

For each ETF, import historical OHLCV from LSEG:

1. Log into LSEG Workspace or LSEG data terminal
2. Export the ETF's price history as Excel (`.xlsx`)
3. Navigate to `/entry` → "Import LSEG file" section
4. Select the ticker and upload the file
5. Repeat for all ETFs

**Minimum history for full model:** `MIN_OBS_FULL = 120` weekly bars (~2.3 years of daily data).  
**Absolute minimum for any signal:** `MIN_OBS_RS = 21` weekly bars.

The LSEG parser expects:
- A row where `row[0] == "Exchange Date"` as the header
- Columns named (case-insensitive): `close`, `open`, `low`, `high`, `volume`
- Date column (`row[0]`) as Python `datetime` objects (not strings)

### Step 4: Run Initial Signal Computation

After price data is imported, trigger a recompute:

```bash
# Option A — via UI:
# Navigate to /entry → submit any date → auto-recompute triggers
# Or: POST to /recompute (there may be a button on the dashboard)

# Option B — direct Python (on PythonAnywhere console or locally):
cd ~/Footprints
python -c "
import db, engine
db.init_schema()
s_rows, c_rows = engine.run_engine(db.get_prices_df(), db.get_etf_meta(), db.get_signals_df())
db.upsert_signals(s_rows)
db.log_signal_changes(c_rows)
print(f'Computed {len(s_rows)} signals, {len(c_rows)} changes')
"
```

After this, `/dashboard` should show signals for all ETFs with sufficient history.

---

## Weekly Maintenance Workflow

Each week (Sunday evening or Monday morning):

```
1. Open LSEG Workspace and export Friday close OHLCV for all 43 active ETFs as .xlsx files

2. Navigate to /entry and import:
   - BULK: Use "↑ BULK IMPORT" — select all TICKER.xlsx files at once → click IMPORT ALL
   - Per-ticker: Use "↑ LSEG IMPORT" — select ticker from dropdown, upload its file → IMPORT
   (Template import/export no longer exists)

3. Verify flash messages after import:
   - "Saved N rows for YYYY-MM-DD"
   - "Recomputed N signals"
   - Any signal changes listed (e.g. "VWRP.L: NEUTRAL → ACCUMULATING/HOLD")

4. Navigate to /dashboard — verify signals updated, check as_of date is this week's Friday

5. Navigate to /heatmap — review pension fund stances (LG and IL sections in the Pension Summary); check any Notable signals

6. Navigate to /history — confirm signal changes are logged if any occurred

7. Back up footprints.db manually — it is gitignored and not version-controlled
```

---

## Providing Context to a New Conversation

When starting a new development session with Claude (or any assistant), paste this at the start:

```
I'm working on Footprints v2.0 — a Python Flask ETF signal dashboard deployed on PythonAnywhere.
GitHub: https://github.com/rhapsodians/Footprints

Architecture (confirmed from code):
- server.py: Flask app, all routes, LSEG parser (583 lines)
- engine.py: 10-step cross-sectional signal pipeline (722 lines)
- db.py: SQLite layer, footprints.db (678 lines)
- config.py: all constants and weights (180 lines)
- wsgi.py: PythonAnywhere WSGI entry
- templates/: 9 Jinja2 HTML templates

Key facts:
- Data: daily OHLCV in SQLite; resampled to weekly in engine
- Source: LSEG Excel exports
- Benchmark: VWRP.L (default); per-ETF override via etf_meta.benchmark_ticker
- Signals: STRONG BUY / ACCUMULATING/HOLD / EARLY ACCUMULATION / NEUTRAL / EXIT/DISTRIBUTION
- Rotation score: weighted percentile rank composite (0–100)
- Pension: two providers (LG = L&G WorkSave, IL = Irish Life) in same DB
- No RSI in v2; CLV-based Pressure replaces it
- Admin: inline sector editor on ETF tiles → POST /admin/set-sector → db.set_etf_sector()
- Entry: bulk LSEG import → POST /entry/import-lseg-bulk (files named TICKER.xlsx); template import/export removed
- No macro regime filter; all signals are cross-sectional/quantitative
- Requirements: flask>=3.0, numpy>=1.26, pandas>=2.1, openpyxl>=3.1

Documentation: footprints-docs/ folder (README.md is the index)
Current stable baseline: v2.0.0 (March 2026)

Current task: [describe what you're working on]
```

---

## Troubleshooting

### App starts but `/dashboard` shows no signals

- Check `db.get_available_dates()` returns dates with `signal_model_version = 'weekly_v2_0'`
- Run the signal recompute (see Step 4 above)
- Verify `etf_meta` has active ETFs: `SELECT * FROM etf_meta WHERE active=1 AND suspended=0`
- Verify `prices` has data: `SELECT ticker, COUNT(*) FROM prices GROUP BY ticker`

### LSEG import returns "Cannot find 'Exchange Date' header"

- The uploaded file is not in the expected LSEG export format
- Verify the file has a row where the first column value is exactly `"Exchange Date"`
- Check the file is `.xlsx` not `.xls` (openpyxl does not support `.xls`)

### All RS fields are NULL in signals

- `VWRP.L` is missing from `prices` or has no data for the relevant dates
- Check: `SELECT COUNT(*) FROM prices WHERE ticker='VWRP.L'`
- If zero, import VWRP.L price history first

### Signal not updating after data entry

- Check flash messages for "Recompute failed: ..." — catch the error message
- Run the recompute Python snippet directly (see Step 4) to see the full traceback
- Common cause: a ticker in `etf_meta` with `active=1` but no rows in `prices` (engine will still run but that ticker will be dropped in `_latest_eligible()`)

### PythonAnywhere "Reload" not picking up changes

- Confirm `git pull` ran successfully (check for merge conflicts)
- Check `server.py` imports: any syntax error in any of the four main files will cause a 500 on all pages
- Check PythonAnywhere error log in the Web tab

### `FP2_SECRET_KEY` warning in logs

- Set the environment variable in PythonAnywhere Web tab → Environment variables
- Never use the fallback `"fp2-dev-secret-change-in-production"` in production

---

## Known Documentation Gaps (Items to Complete)

The following items were not fully resolvable during the audit and represent the remaining reproduction risks:

| Gap | Impact | Status |
|-----|--------|--------|
| **ETF universe list** | HIGH | ✅ Resolved — `03_DATA_MODEL.md` Appendix A + SQL seed script in this doc |
| **Pension fund + proxy list** | HIGH | ✅ Resolved — `05_PENSION_PROXY_METHODOLOGY.md` Appendix B + SQL seed script in this doc |
| **HTML templates** | MEDIUM | ✅ Resolved — all 8 committed templates documented in `06_DASHBOARD_PAGES.md` |
| **Admin route bug** | HIGH | ✅ Resolved — toggle-etf fix deployed |
| **Git tag** | LOW | ✅ Resolved — `v2.0.0` tagged and pushed |
| **`scripts/` folder** | LOW | ⚠️ Open — inspect on PythonAnywhere; document any scripts used regularly |
| **Exact `pip freeze` output** | LOW | ⚠️ Open — run `pip freeze > requirements_locked.txt` on PythonAnywhere and commit |
