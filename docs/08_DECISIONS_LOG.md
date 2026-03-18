# 08 — Decisions Log

> **Audit status:** Rewritten from scratch against actual codebase. Entries that described features that do not exist (Track A/B, macro regime filter, RSI, CSV storage) have been corrected or removed. New entries added for decisions visible in the code but not previously documented.

---

## Format

```
### [DATE / VERSION] — [Decision Title]
**Decision:** What was decided
**Rationale:** Why
**Alternatives considered:** What else was evaluated
**Assumptions / Constraints:** What is assumed true
**Status:** Active | Superseded | Deferred | Open
```

---

## Foundational Architecture

### [v2.0] — Flask over single-script; `server.py` as entry point

**Decision:** Rebuild as a multi-file Flask web application. Entry point is `server.py`.
**Rationale:** PythonAnywhere deployment requires a WSGI-compatible app. Flask is minimal, familiar, and PythonAnywhere-native. The `wsgi.py` file wraps `server.app` for WSGI.
**Alternatives considered:** Streamlit (insufficient HTML/CSS control, harder PythonAnywhere deployment); Django (overkill for single-user); FastAPI + React (too complex).
**Status:** Active.

### [v2.0] — Strict separation: `server.py` / `engine.py` / `db.py` / `config.py`

**Decision:** Hard boundary between Flask routing (`server.py`), signal computation (`engine.py`), database I/O (`db.py`), and configuration (`config.py`). Cross-imports are one-directional: `server.py` imports all three; `engine.py` imports only `config`; `db.py` imports only `config`.
**Rationale:** Allows signal engine to be tested or run standalone without a Flask context. Keeps DB logic out of business logic. Makes `config.py` the single source of truth for all tunable parameters.
**Assumption:** All parameters that might need tuning live in `config.py`. If a threshold is hardcoded anywhere in `engine.py` or `server.py`, it should be moved to `config.py`.
**Status:** Active.

### [v2.0] — SQLite over CSV

**Decision:** All data (prices, signals, ETF metadata, pension mappings) stored in SQLite (`footprints.db`). No CSV files for data.
**Rationale:** CSV storage (used in v1) had no query capability, no atomic writes, and grew unwieldy with daily price history. SQLite provides SQL queries, transactions, and WAL mode for concurrent reads with no external server dependency.
**Implementation details:** `db.py` uses Python's stdlib `sqlite3`. WAL mode enabled (`PRAGMA journal_mode=WAL`). Foreign keys enabled. Connection wrapped in `@contextmanager` with auto-commit/rollback.
**Alternatives considered:** PostgreSQL (requires external server, overkill for single-user); pandas CSV (v1 approach, superseded).
**Status:** Active.

### [v2.0] — Daily price storage, weekly signal computation

**Decision:** Prices are stored as daily OHLCV in the `prices` table. The engine resamples to weekly bars internally on every run.
**Rationale:** Daily storage enables sparklines, ETF history charts, and 3-month return calculations without re-importing data. Storing weekly bars separately would require maintaining two price tables in sync.
**Trade-off:** The engine must process more rows per run. At current scale (~40 ETFs × ~500 daily rows = ~20,000 rows), this is negligible.
**Assumption:** All prices are in GBP. Engine comment: "prices already in GBP — no pence conversion required". LSE ETFs with `.L` suffix are expected to be priced in pounds.
**Status:** Active.

---

## Data Source

### [v2.0] — LSEG Excel exports as sole data source

**Decision:** All price data enters via LSEG (London Stock Exchange Group) Excel file exports, parsed by `_parse_lseg()` in `server.py`.
**Rationale:** LSEG provides reliable, clean OHLCV data for LSE-listed ETFs. The parser handles the specific LSEG layout (finds `Exchange Date` header row; maps column names by lowercased header).
**Alternatives considered:** Yahoo Finance via `yfinance` — blocked by PythonAnywhere free-tier HTTP whitelist; Alpha Vantage — requires API key management; manual CSV — v1 approach, error-prone.
**Implementation note:** The `source` field in the `prices` table is always `"LSEG"` currently, but the schema is source-agnostic. A new parser for a different source would only need to produce the same `(date, open, high, low, close, volume)` tuple format.
**Status:** Active. Revisit if PythonAnywhere tier is upgraded (paid tier allows arbitrary outbound HTTP).

### [v2.0] — Weekly entry template (Excel) for bulk import

**Decision:** Provide a downloadable, pre-populated `.xlsx` template covering all active ETFs, which the user fills in and re-uploads.
**Rationale:** Reduces the friction of the weekly update cycle. The template includes prev-close prices, sector groupings, and styling to make data entry fast and error-resistant.
**Implementation:** `openpyxl` generates the template server-side; upload handler reads it back and redirects to the entry form pre-filled via `?prefill=` JSON query param.
**Status:** Active.

---

## Signal Model

### [v2.0] — Cross-sectional percentile scoring over fixed thresholds

**Decision:** All ETF rankings are computed cross-sectionally within the current universe on each run date. Rotation score is a weighted sum of percentile ranks, not absolute values.
**Rationale:** Fixed thresholds (e.g. "RS > 5% = good") break down across different market regimes, asset classes, and time periods. Cross-sectional scoring always answers "what is relatively best right now" — which is the correct question for rotation.
**Implication:** Signals can change week-to-week without an ETF's own metrics changing, because the cross-section has shifted. This is correct and by design, not a bug.
**Status:** Active.

### [v2.0] — VWRP.L as default benchmark

**Decision:** All RS calculations default to VWRP.L (Vanguard FTSE All-World) as benchmark. Per-ETF overrides via `etf_meta.benchmark_ticker`.
**Rationale:** VWRP.L is a liquid, GBP-denominated global market cap benchmark. It represents "the market" for a UK-based investor. RS vs VWRP.L answers "is this ETF beating the global market?" which is the relevant question for tactical rotation.
**Important constraint:** VWRP.L must itself be in the ETF universe with price data. If it is missing, all RS fields will be NULL for all default-benchmark ETFs.
**Alternatives considered:** MSCI World (no direct liquid GBP ETF with SWDA having near-identical characteristics); S&P 500 (US-centric, inappropriate as a global benchmark).
**Status:** Active.

### [v2.0] — CLV-based Pressure over RSI

**Decision:** Use CLV (Close Location Value) × daily turnover, accumulated over 20 weeks, as the primary "buying/selling pressure" metric. RSI is not used in v2.
**Rationale:** RSI measures price change velocity, not institutional participation. CLV × volume measures whether professional money is accumulating (closing consistently at highs on volume) or distributing (closing consistently at lows on volume). The latter is more directly aligned with the "follow the money" thesis.
**Practical advantage:** Pressure can detect stealth accumulation (rising pressure + flat price) that RSI cannot.
**Status:** Active.

### [v2.0] — Trend Score (0–4) over -7 to +7 composite

**Decision:** Trend is encoded as a discrete 0–4 integer: four binary MA conditions, each contributing +1.
**Rationale:** Simple, interpretable, and stable. Each increment has a clear meaning. The -7 to +7 composite was designed in prior documentation but never implemented.
**Four conditions (equal weight):**
1. Close > MA20
2. Close > MA100
3. MA20 > MA100 (golden cross structure)
4. MA100 > MA100 shifted 20 weeks (long-term MA is rising)
**Status:** Active.

### [v2.0] — EARLY ACCUMULATION as a distinct signal

**Decision:** Add EARLY ACCUMULATION as a fourth signal class, sitting between NEUTRAL and ACCUMULATING/HOLD in the hierarchy.
**Rationale:** By the time an ETF qualifies for ACCUMULATING/HOLD (rotation ≥ 60, trend ≥ 3), it has already moved significantly. The EARLY ACCUMULATION signal fires earlier — when pressure has just flipped from non-positive to positive — giving a lead on potential rotation candidates.
**Risk:** Higher false positive rate than ACCUMULATING/HOLD. Treat EARLY ACCUMULATION as "watch closely" rather than "act immediately."
**Status:** Active.

### [v2.0] — PRESSURE_LAG = 5 weeks

**Decision:** "Previous pressure" for EARLY ACCUMULATION detection is taken 5 weeks ago (`pressure_prev_20w = pressure_20w.shift(5)`).
**Rationale:** 5 weeks provides enough lookback to confirm a genuine flip (not noise) while remaining responsive enough to catch early accumulation.
**Open question:** This value was set empirically. A shorter lag (e.g. 1 week) would be more responsive but noisier; a longer lag (e.g. 10 weeks) would be more confirmed but slower.
**Status:** Active. Candidate for tuning in v2.1.

### [v2.0] — Winsorisation at 2nd/98th percentile

**Decision:** Clip four cross-sectional metrics at the 2nd and 98th percentile before ranking.
**Rationale:** A single outlier ETF (e.g. one experiencing a corporate event with extreme turnover or pressure) would compress all other ETFs into a narrow band of the rank distribution. Winsorisation prevents this without removing outlier data.
**Fields winsorised:** `turnover_z_20`, `pressure_20w`, `rs20_vol_adj`, `rs_accel_vol_adj`.
**Status:** Active.

---

## Pension Fund Model

### [v2.0] — Two providers in one system (LG + IL)

**Decision:** Support L&G WorkSave and Irish Life pension funds in the same application, distinguished by `code` prefix (`LG` / `IL`).
**Rationale:** Both providers serve the same user. Maintaining separate applications would be redundant and increase maintenance overhead.
**Implementation:** `server.summary()` splits `fund_map` on code prefix. Summary page renders provider sections separately. No schema changes are needed to add more providers — add a new code prefix and the split logic extends naturally.
**Status:** Active.

### [v2.0] — Pension mappings managed via Admin UI (not CSV)

**Decision:** All pension fund and proxy mapping management is done through the `/admin` UI. There is no CSV import for pension data.
**Rationale:** Pension fund lists are relatively stable (changed rarely) and small. A UI with discrete add/remove actions is safer than a CSV import that could accidentally overwrite the entire mapping.
**Status:** Active.

### [v2.0] — Many-to-many fund/ETF mapping

**Decision:** Use a `pension_etf_map` join table (many-to-many) rather than storing a single proxy ticker per fund.
**Rationale:** Some pension funds have no single perfect ETF proxy. Mapping two or three proxies gives a more robust signal (the fund's stance is the aggregate of its proxies) and allows the user to add or remove proxies as the ETF universe evolves.
**Status:** Active.

---

## Deferred / Open Items

### [OPEN] — Automated data fetch

**Decision:** DEFERRED. No automated weekly data pull.
**Blocker:** PythonAnywhere free/hacker tier restricts outbound HTTP to a whitelist that does not include Yahoo Finance or LSEG APIs.
**Options:** (a) Upgrade to paid PythonAnywhere tier (allows arbitrary outbound HTTP); (b) Run a scheduled local script that pushes data to the DB directly; (c) Accept the LSEG manual export workflow indefinitely.
**Status:** Deferred. Revisit if manual update becomes a friction point.

### [OPEN] — `requirements.txt` uses minimum version pins (`>=`), not exact pins

**Decision:** `requirements.txt` uses `>=` constraints (e.g. `flask>=3.0.0`), not exact versions.
**Risk:** A future dependency upgrade could introduce breaking changes without warning.
**Recommendation:** Run `pip freeze > requirements_locked.txt` on the live PythonAnywhere environment periodically and commit it as a reference. Use it to reproduce the exact environment if needed.
**Status:** Open. Low urgency until a breaking change occurs.

### [OPEN] — No authentication

**Decision:** No login system exists.
**Rationale:** Single-user personal tool; access by URL obscurity is sufficient for current use.
**Risk:** If the PythonAnywhere URL is discovered, anyone can access the dashboard and (via Admin) modify ETF universe and pension mappings.
**Mitigation options:** Basic HTTP auth via PythonAnywhere `.htpasswd`; Flask-Login if multi-user ever needed.
**Status:** Open. Acceptable risk for current use case.

### [v2.0 — live] — Pension Summary merged into /heatmap (no separate /summary route)

**Decision:** The `/summary` route was removed. The pension fund summary data (LG/IL fund stances, notable signals, portfolio counts) is now computed inside the `/heatmap` route handler and passed to `heatmap.html` alongside the heatmap data.
**Rationale:** Reduces navigation — users get the ETF heatmap and pension fund summary in one page rather than switching between two.
**Impact on code:** `_proxy_narrative()` (5-sentence ETF narrative generator) and `_short_sig()` were removed as they were only used by the former `/summary` route.
**Impact on docs:** `05_PENSION_PROXY_METHODOLOGY.md` summary page description remains valid — the data logic is unchanged; only the URL and template have changed.
**GitHub sync needed:** The GitHub `server.py` still has the old `/summary` route. Push the live version.
**Status:** Active (live). GitHub stale.

### [OPEN] — Admin ETF suspend/activate buttons broken (route mismatch)

**Issue:** `admin.html` submits ETF status changes to `/admin/suspend`, `/admin/unsuspend`, `/admin/deactivate`, `/admin/activate` as individual POST routes. The live `server.py` only defines `/admin/toggle-etf` with an `action` form parameter (`suspend`/`resume`/`exclude`/`include`). These four routes do not exist → clicking suspend/activate/deactivate in admin currently returns 404.
**Fix options:**
- Option A: Update `admin.html` to submit to `/admin/toggle-etf` with `<input type="hidden" name="action" value="suspend">` etc.
- Option B: Add the four individual routes to `server.py` as thin wrappers around the toggle logic.
Option A is simpler.
**Status:** Open — bug confirmed. Admin ETF status changes non-functional until resolved.

### [v2.0 — live] — Signal priority order corrected (EA is priority 1, not after SB)

**Decision:** EARLY ACCUMULATION is checked before STRONG BUY in the signal classification hierarchy. Priority order: EA (1) → SB (2) → AH (3) → EXIT (4) → NEUTRAL (5).
**Rationale:** An ETF beginning to accumulate (pressure just turned positive, price still below MA100) should be flagged as EA even if its rotation score happens to be high. The EA signal is an early-warning state — the MA100 condition (`close < MA100`) means it structurally cannot also be a full STRONG BUY (which requires trend ≥ 3, implying price above both MAs).
**Note:** Prior documentation incorrectly stated STRONG BUY was checked first.
**Status:** Active. Confirmed from both `engine.py` and `guide.html` logic table.

### [OPEN] — Admin route discrepancy: template vs server.py

**Issue:** `admin.html` submits to `/admin/suspend`, `/admin/unsuspend`, `/admin/deactivate`, `/admin/activate` as individual routes. But the GitHub version of `server.py` only defines `/admin/toggle-etf` with an `action` parameter.
**Possible explanations:** (a) `server.py` was updated on PythonAnywhere after the last GitHub push, adding these routes; (b) The template is wrong and the admin suspend/activate functionality is broken; (c) `server.py` on PythonAnywhere differs from the GitHub version.
**Action:** SSH into PythonAnywhere, run `grep "admin/suspend\|admin/unsuspend\|admin/deactivate\|admin/activate\|toggle-etf" ~/footprints2/server.py` to confirm which routes actually exist.
**Status:** Open — verify before relying on admin ETF status changes.

**Decision:** The heatmap uses a custom 11-level bipolar colour class system (`hi-5` → `hi-0` → `lo-5`) plus a 6-level liquidity scale (`lq-0` to `lq-5`). Thresholds are hardcoded per KPI.
**Rationale:** Hardcoded thresholds give consistent visual meaning across weeks. Percentile colouring would make every week look equally distributed regardless of absolute levels — masking market extremes.
**Note:** `_heat_class()` is still registered in Jinja globals but is not used by the current heatmap. The `heat-h/mh/m/ml/l` classes from prior documentation are obsolete.
**Status:** Active.

### [v2.0] — Heatmap tooltips: contextual interpretation, not static definitions

**Decision:** Each heatmap cell tooltip dynamically generates a contextual interpretation of the specific value (e.g. "£2.4M — Moderately liquid."), shown alongside the static field definition.
**Implementation:** `hmCtx(key, val)` function in `heatmap.html` — branching logic per KPI.
**Status:** Active.

### [v2.0] — Heatmap Sector Overview: clickable tiles filter the ETF table

**Decision:** Sector tiles below the ETF table are clickable — selecting one filters the table to that sector. Toggle between ALL ETFs and PENSION PROXIES views.
**Status:** Active.

### [v2.0] — Heatmap Provider filter replaces individual fund chips

**Decision:** Filter band has Provider row (ALL / L&G / Irish Life / Notable) rather than individual fund chips.
**Rationale:** Fund list grew too large for per-fund chips. Provider-level is sufficient for the primary use case.
**Status:** Active.

### [OPEN] — `summary.html` and other templates not committed to GitHub repo

**Decision:** OPEN — `summary.html` (and possibly other templates) exist on PythonAnywhere but have not been pushed to GitHub.
**Risk:** If PythonAnywhere is reset or the file is accidentally deleted, the Summary page cannot be recovered from the repo.
**Action:** `git add templates/ && git commit -m "templates: add all Jinja2 HTML templates" && git push`
**Status:** Open — high priority.

### [OPEN] — Git tags not created for version milestones

**Decision:** No `git tag` commands have been run.
**Recommendation:** `git tag v2.0.0 -m "Stable baseline" && git push origin v2.0.0`
**Status:** Open. Low effort, high value for future restoration.

### [OPEN] — `footprints.db` not in the repo (correctly gitignored)

**Decision:** The database is gitignored. This is correct — it contains real price data.
**Implication:** A fresh clone has no data. A new developer must seed the database. See `10_REPRODUCTION_GUIDE.md` for the seeding process.
**Status:** Open. Consider adding a `seed_db.py` script with a small synthetic dataset for development/testing.
