"""
db.py — Footprints v2.0
========================
All SQLite interaction: schema creation, migration, reads, and writes.
No analytics live here. No Flask imports.

Public API
----------
get_conn()                  → sqlite3.Connection (row_factory set)
init_schema()               → create / migrate all tables
get_prices_df()             → pd.DataFrame of all prices
get_etf_meta()              → pd.DataFrame of etf_meta (active + suspended)
get_active_tickers()        → list[str]
get_signals_df()            → pd.DataFrame of latest signal per ticker
get_signal_history()        → pd.DataFrame of signal_log
upsert_signals(rows)        → write list[dict] into signals table
log_signal_changes(changes) → append to signal_log
get_weekly_entry_data()     → dict for the data-entry form
upsert_price_row(row)       → insert / replace one weekly OHLCV row
add_etf(meta)               → insert new ETF into etf_meta
set_etf_active(ticker, val) → toggle active flag
"""

import sqlite3
import os
from contextlib import contextmanager
from typing import Generator

import pandas as pd

from config import DB, BASE_TICKER, MODEL_VERSION

# ── Connection ────────────────────────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA wal_autocheckpoint=100")
    return conn


@contextmanager
def db_conn() -> Generator[sqlite3.Connection, None, None]:
    """Context manager — commits on clean exit, rolls back on exception."""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Schema ────────────────────────────────────────────────────────────────────

# All v2 columns for the signals table, in addition to the PK (date, ticker).
_SIGNALS_COLUMNS: list[tuple[str, str]] = [
    # Core
    ("signal",                    "TEXT"),
    ("signal_model_version",      "TEXT"),
    ("signal_reason",             "TEXT"),
    ("rotation_score",            "REAL"),
    ("confidence_score",          "REAL"),
    ("confidence_bucket",         "TEXT"),
    # Trend
    ("trend_score_raw",           "REAL"),
    ("trend_score_pct",           "REAL"),
    ("close",                     "REAL"),
    ("ma20",                      "REAL"),
    ("ma100",                     "REAL"),
    # Auditability
    ("n_obs",                     "INTEGER"),  # weekly bar count; used in confidence history component
    # Turnover
    ("turn_latest",               "REAL"),
    ("avg_turn_20w",              "REAL"),
    ("avg_turn_100w",             "REAL"),
    ("turnover_ratio_20_100",     "REAL"),
    ("turnover_z_20",             "REAL"),
    ("turn_cv20",                 "REAL"),
    ("turnover_rank_pct",         "REAL"),
    # Pressure
    ("pressure_20w",              "REAL"),
    ("pressure_prev_20w",         "REAL"),
    ("pressure_ratio_20w",        "REAL"),
    ("pressure_all_positive_20w", "INTEGER"),
    ("pressure_pos_weeks_20w",    "REAL"),
    ("pressure_pos_weeks_pct",    "REAL"),
    ("pressure_rank_pct",         "REAL"),
    # Raw RS
    ("rs4_raw",                   "REAL"),
    ("rs12_raw",                  "REAL"),
    ("rs20_raw",                  "REAL"),
    ("rs_accel_raw",              "REAL"),
    ("rs20_rank_pct",             "REAL"),
    # Vol-adjusted RS
    ("vol_20w",                   "REAL"),
    ("rs4_vol_adj",               "REAL"),
    ("rs12_vol_adj",              "REAL"),
    ("rs20_vol_adj",              "REAL"),
    ("rs_accel_vol_adj",          "REAL"),
    ("rs20_vol_adj_rank_pct",     "REAL"),
    ("rs_accel_vol_adj_rank_pct", "REAL"),
    # Sector
    ("sector_count",              "INTEGER"),
    ("sector_pct_rs4_pos",        "REAL"),
    ("sector_pct_rs12_pos",       "REAL"),
    ("sector_pct_rs20_pos",       "REAL"),
    ("sector_pct_rs_accel_pos",   "REAL"),
    ("sector_pct_positive_pressure", "REAL"),
    ("sector_pct_above_ma20",     "REAL"),
    ("sector_pct_above_ma100",    "REAL"),
    ("sector_median_rs20_vol_adj","REAL"),
    ("sector_median_pressure_rank","REAL"),
    ("sector_median_turnover_rank","REAL"),
    ("sector_score",              "REAL"),
    ("sector_confirmed",          "INTEGER"),
    ("sector_confirmation_pct",   "REAL"),
    # v1 display aliases — kept in schema so existing signal rows stay readable.
    # Not written by the v2 engine; computed at render time in server._enrich_signals().
    # Safe to remove in a future migration once all v1 signal rows have been purged.
    ("dv_surprise",               "REAL"),
    ("crdp20",                    "REAL"),
    ("rs20_pct",                  "REAL"),
    ("ret20_pct",                 "REAL"),
    ("ret_3m_pct",                "REAL"),
    ("trend",                     "INTEGER"),
]

_ETF_META_V2_COLUMNS: list[tuple[str, str]] = [
    ("benchmark_ticker", "TEXT"),   # defaults to BASE_TICKER if NULL
]

_PRICES_V2_COLUMNS: list[tuple[str, str]] = []  # no additions needed yet


def init_schema() -> None:
    """
    Create all tables if they don't exist, then apply additive migrations.
    All DDL runs inside a single transaction per table group.
    """
    with db_conn() as conn:
        # ── etf_meta ──────────────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS etf_meta (
                ticker          TEXT PRIMARY KEY,
                name            TEXT,
                sector          TEXT,
                active          INTEGER DEFAULT 1,
                display_order   INTEGER DEFAULT 99,
                suspended       INTEGER NOT NULL DEFAULT 0,
                benchmark_ticker TEXT
            )
        """)

        # ── prices ────────────────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prices (
                date    TEXT NOT NULL,
                ticker  TEXT NOT NULL,
                open    REAL,
                high    REAL,
                low     REAL,
                close   REAL,
                volume  REAL,
                source  TEXT DEFAULT "LSEG",
                PRIMARY KEY (date, ticker)
            )
        """)

        # ── signals ───────────────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                date    TEXT NOT NULL,
                ticker  TEXT NOT NULL,
                PRIMARY KEY (date, ticker)
            )
        """)

        # ── signal_log ────────────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                ticker      TEXT NOT NULL,
                prev_signal TEXT,
                new_signal  TEXT,
                rotation_score REAL,
                confidence_score REAL,
                logged_at   TEXT DEFAULT (datetime('now'))
            )
        """)
        # Migrate: ensure all expected columns exist (handles legacy DBs)
        _migrate_columns(conn, "signal_log", [
            ("prev_signal",      "TEXT"),
            ("new_signal",       "TEXT"),
            ("rotation_score",   "REAL"),
            ("confidence_score", "REAL"),
        ])

        # ── additive migrations ───────────────────────────────────────────────
        _migrate_columns(conn, "signals",  _SIGNALS_COLUMNS)
        _migrate_columns(conn, "etf_meta", _ETF_META_V2_COLUMNS)

        # Backfill benchmark_ticker for existing rows that have none
        conn.execute("""
            UPDATE etf_meta
            SET benchmark_ticker = ?
            WHERE benchmark_ticker IS NULL
        """, (BASE_TICKER,))

        # ── indexes ───────────────────────────────────────────────────────────
        # Descending date index so bulk price queries (ORDER BY ticker, date DESC)
        # are satisfied entirely by the index without a temporary B-TREE sort.
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_prices_ticker_date_desc
            ON prices (ticker, date DESC)
        """)


def _migrate_columns(
    conn: sqlite3.Connection,
    table: str,
    columns: list[tuple[str, str]],
) -> None:
    """Add any missing columns to an existing table. Safe to re-run."""
    existing = {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for col, typ in columns:
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")


# ── Reads ─────────────────────────────────────────────────────────────────────

def get_prices_df() -> pd.DataFrame:
    """All rows from prices, sorted by ticker then date."""
    with db_conn() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM prices ORDER BY ticker, date",
            conn,
        )
    df["date"] = pd.to_datetime(df["date"])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_etf_meta() -> pd.DataFrame:
    """Full etf_meta including suspended rows."""
    with db_conn() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM etf_meta ORDER BY display_order, ticker",
            conn,
        )
    # Ensure benchmark_ticker falls back to BASE_TICKER for any NULLs
    df["benchmark_ticker"] = df["benchmark_ticker"].fillna(BASE_TICKER)
    return df


def get_active_tickers() -> list[str]:
    """Tickers that are active=1 and suspended=0."""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT ticker FROM etf_meta WHERE active=1 AND suspended=0 "
            "ORDER BY display_order, ticker"
        ).fetchall()
    return [r["ticker"] for r in rows]


def get_signals_df(as_of_date: str | None = None) -> pd.DataFrame:
    """
    Latest signal row per ticker — v2 rows only (signal_model_version = 'weekly_v2_0').
    If as_of_date is given, returns signals for that exact date.
    Otherwise returns the most recent v2 date present in the table.
    Pre-v2 rows (signal_model_version IS NULL) are excluded to prevent stale
    v1 data being served through the v2 UI.
    """
    with db_conn() as conn:
        if as_of_date:
            df = pd.read_sql_query(
                "SELECT s.*, m.name, m.sector, m.display_order "
                "FROM signals s "
                "JOIN etf_meta m ON s.ticker = m.ticker "
                "WHERE s.date = ? AND s.signal_model_version = 'weekly_v2_0' "
                "AND m.active = 1 AND m.suspended = 0 "
                "ORDER BY m.display_order, s.ticker",
                conn,
                params=(as_of_date,),
            )
        else:
            df = pd.read_sql_query(
                "SELECT s.*, m.name, m.sector, m.display_order "
                "FROM signals s "
                "JOIN etf_meta m ON s.ticker = m.ticker "
                "WHERE s.date = ("
                "  SELECT MAX(date) FROM signals WHERE signal_model_version = 'weekly_v2_0'"
                ") AND s.signal_model_version = 'weekly_v2_0' "
                "AND m.active = 1 AND m.suspended = 0 "
                "ORDER BY m.display_order, s.ticker",
                conn,
            )
    return df


def get_signal_history(limit: int = 200) -> pd.DataFrame:
    """Most recent signal change log entries."""
    with db_conn() as conn:
        df = pd.read_sql_query(
            "SELECT l.id, l.date, l.ticker, l.prev_signal as old_signal, "
            "l.new_signal, l.rotation_score, l.confidence_score, l.logged_at, "
            "m.name, m.sector "
            "FROM signal_log l "
            "LEFT JOIN etf_meta m ON l.ticker = m.ticker "
            "ORDER BY l.logged_at DESC "
            "LIMIT ?",
            conn,
            params=(limit,),
        )
    return df


def get_available_dates() -> list[str]:
    """Sorted descending list of dates that have v2 signals (weekly_v2_0 only)."""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT date FROM signals "
            "WHERE signal_model_version = 'weekly_v2_0' ORDER BY date DESC"
        ).fetchall()
    return [r["date"] for r in rows]


def get_latest_prices_date() -> str | None:
    """Most recent date in the prices table."""
    with db_conn() as conn:
        row = conn.execute(
            "SELECT MAX(date) as d FROM prices"
        ).fetchone()
    return row["d"] if row else None


def get_ticker_price_history(ticker: str) -> pd.DataFrame:
    """Full OHLCV history for a single ticker, sorted ascending."""
    with db_conn() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM prices WHERE ticker=? ORDER BY date",
            conn,
            params=(ticker,),
        )
    df["date"] = pd.to_datetime(df["date"])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ── Writes ────────────────────────────────────────────────────────────────────

def upsert_signals(rows: list[dict]) -> int:
    """
    Insert or replace signal rows. Each dict must include 'date' and 'ticker'.
    Returns count of rows written.
    """
    if not rows:
        return 0

    cols = list(rows[0].keys())
    placeholders = ", ".join("?" * len(cols))
    col_names = ", ".join(cols)

    with db_conn() as conn:
        conn.executemany(
            f"INSERT OR REPLACE INTO signals ({col_names}) "
            f"VALUES ({placeholders})",
            [tuple(r[c] for c in cols) for r in rows],
        )
    return len(rows)


def log_signal_changes(changes: list[dict]) -> None:
    """
    Append rows to signal_log where the signal has changed.
    Each dict: {date, ticker, old_signal, new_signal, rotation_score, confidence_score}
    Note: old_signal is stored as prev_signal in the DB for legacy compatibility.
    """
    if not changes:
        return
    with db_conn() as conn:
        conn.executemany(
            "INSERT INTO signal_log "
            "(date, ticker, prev_signal, new_signal, rotation_score, confidence_score) "
            "VALUES (:date, :ticker, :old_signal, :new_signal, "
            ":rotation_score, :confidence_score)",
            changes,
        )


def upsert_price_row(row: dict) -> None:
    """
    Insert or replace one row in prices.
    row keys: date, ticker, open, high, low, close, volume, source
    """
    with db_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO prices "
            "(date, ticker, open, high, low, close, volume, source) "
            "VALUES (:date, :ticker, :open, :high, :low, :close, :volume, :source)",
            row,
        )


def add_etf(meta: dict) -> None:
    """
    Insert a new ETF into etf_meta.
    meta keys: ticker, name, sector, active, display_order, benchmark_ticker
    """
    meta.setdefault("active", 1)
    meta.setdefault("suspended", 0)
    meta.setdefault("display_order", 99)
    meta.setdefault("benchmark_ticker", BASE_TICKER)
    with db_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO etf_meta "
            "(ticker, name, sector, active, display_order, suspended, benchmark_ticker) "
            "VALUES (:ticker, :name, :sector, :active, :display_order, "
            ":suspended, :benchmark_ticker)",
            meta,
        )


def set_etf_active(ticker: str, active: bool) -> None:
    with db_conn() as conn:
        conn.execute(
            "UPDATE etf_meta SET active=? WHERE ticker=?",
            (1 if active else 0, ticker),
        )


def delete_etf(ticker: str) -> None:
    """Permanently remove an ETF and all its data from the database."""
    with db_conn() as conn:
        conn.execute("DELETE FROM pension_etf_map WHERE ticker=?", (ticker,))
        conn.execute("DELETE FROM signals WHERE ticker=?", (ticker,))
        conn.execute("DELETE FROM signal_log WHERE ticker=?", (ticker,))
        conn.execute("DELETE FROM prices WHERE ticker=?", (ticker,))
        conn.execute("DELETE FROM etf_meta WHERE ticker=?", (ticker,))


def get_weekly_entry_data() -> dict:
    """
    Returns everything the data-entry form needs:
    - active tickers with their latest price date
    - latest price date overall
    """
    with db_conn() as conn:
        tickers = conn.execute(
            "SELECT m.ticker, m.name, m.sector, "
            "  MAX(p.date) as last_price_date "
            "FROM etf_meta m "
            "LEFT JOIN prices p ON m.ticker = p.ticker "
            "WHERE m.active=1 AND m.suspended=0 "
            "GROUP BY m.ticker "
            "ORDER BY m.ticker"
        ).fetchall()

        latest_date = conn.execute(
            "SELECT MAX(date) as d FROM prices"
        ).fetchone()["d"]

    return {
        "tickers": [dict(r) for r in tickers],
        "latest_date": latest_date,
    }


# ── Pension fund helpers ──────────────────────────────────────────────────────

def get_pension_funds() -> list[dict]:
    """All pension funds ordered by display_order."""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT id, code, name, display_order FROM pension_funds ORDER BY display_order, name"
        ).fetchall()
    return [dict(r) for r in rows]


def get_pension_maps() -> tuple[dict, dict]:
    """Return (fund_map, etf_map).
    fund_map: {fund_id -> {id, code, name, tickers:[...]}}
    etf_map:  {ticker  -> [fund_id, ...]}
    """
    with db_conn() as conn:
        funds    = conn.execute(
            "SELECT id, code, name FROM pension_funds ORDER BY display_order, name"
        ).fetchall()
        mappings = conn.execute("SELECT fund_id, ticker FROM pension_etf_map").fetchall()
    fund_map = {f["id"]: {"id": f["id"], "code": f["code"],
                           "name": f["name"], "tickers": []} for f in funds}
    etf_map: dict[str, list] = {}
    for m in mappings:
        fid, t = m["fund_id"], m["ticker"]
        if fid in fund_map:
            fund_map[fid]["tickers"].append(t)
        etf_map.setdefault(t, []).append(fid)
    return fund_map, etf_map


def add_pension_fund(code: str, name: str) -> int:
    """Insert a new pension fund. Returns new id."""
    with db_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO pension_funds (code, name) VALUES (?,?)",
            (code.upper(), name),
        )
        row = conn.execute(
            "SELECT id FROM pension_funds WHERE code=?", (code.upper(),)
        ).fetchone()
    return row["id"] if row else -1


def remove_pension_fund(fund_id: int) -> None:
    with db_conn() as conn:
        conn.execute("DELETE FROM pension_etf_map WHERE fund_id=?", (fund_id,))
        conn.execute("DELETE FROM pension_funds WHERE id=?", (fund_id,))


def add_pension_proxy(fund_id: int, ticker: str) -> None:
    with db_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO pension_etf_map (fund_id, ticker) VALUES (?,?)",
            (fund_id, ticker.upper()),
        )


def remove_pension_proxy(fund_id: int, ticker: str) -> None:
    with db_conn() as conn:
        conn.execute(
            "DELETE FROM pension_etf_map WHERE fund_id=? AND ticker=?",
            (fund_id, ticker.upper()),
        )


# ── Price series helpers ──────────────────────────────────────────────────────

def get_price_series(ticker: str, limit: int = 520) -> list[dict]:
    """Recent OHLCV for a ticker (ascending). Used for sparklines and charts."""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM prices "
            "WHERE ticker=? ORDER BY date DESC LIMIT ?",
            (ticker, limit),
        ).fetchall()
    return [{"d": r["date"], "o": r["open"], "h": r["high"],
             "l": r["low"], "c": round(r["close"], 4),
             "v": r["volume"]} for r in reversed(rows)]


def get_price_series_bulk(
    tickers: list[str],
    limit_per: int = 520,
    as_of: str | None = None,
) -> dict[str, list]:
    """Fetch price series for multiple tickers in one query.

    as_of: if supplied (ISO date string), only rows on or before that date are
           returned. Used to keep sparklines consistent with a historical signal date.
    """
    if not tickers:
        return {}
    placeholders = ",".join("?" * len(tickers))
    params: list = list(tickers)
    date_clause = ""
    if as_of:
        date_clause = "AND date <= ? "
        params.append(as_of)
    with db_conn() as conn:
        rows = conn.execute(
            f"SELECT ticker, date, open, high, low, close, volume FROM prices "
            f"WHERE ticker IN ({placeholders}) {date_clause}ORDER BY ticker, date DESC",
            params,
        ).fetchall()
    result: dict[str, list] = {t: [] for t in tickers}
    counts: dict[str, int] = {t: 0 for t in tickers}
    for r in rows:
        t = r["ticker"]
        if counts[t] < limit_per:
            result[t].append({"d": r["date"], "o": r["open"], "h": r["high"],
                               "l": r["low"], "c": round(r["close"], 4),
                               "v": r["volume"]})
            counts[t] += 1
    # Reverse each list to ascending order
    for t in result:
        result[t].reverse()
    return result


def get_ticker_signal_history(ticker: str) -> list[dict]:
    """Full signal log for a single ticker."""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT date, prev_signal, new_signal, rotation_score, confidence_score, logged_at "
            "FROM signal_log WHERE ticker=? ORDER BY logged_at DESC",
            (ticker,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest_prices() -> dict[str, dict]:
    """Most recent price row per ticker (for entry form prev-close display)."""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT p.ticker, p.date, p.close FROM prices p "
            "INNER JOIN ("
            "  SELECT ticker, MAX(date) as md FROM prices GROUP BY ticker"
            ") lp ON p.ticker=lp.ticker AND p.date=lp.md"
        ).fetchall()
    return {r["ticker"]: {"date": r["date"], "close": r["close"]} for r in rows}


def get_prev_signals(as_of_date: str | None = None) -> dict[str, str]:
    """Signal from the week immediately before as_of_date per ticker.
    If as_of_date is None, uses the most recent date in the table.
    Requires SQLite >= 3.25 (window functions). Python 3.6+ ships 3.25+.
    """
    with db_conn() as conn:
        if as_of_date:
            rows = conn.execute("""
                SELECT ticker, signal AS prev_signal
                FROM (
                    SELECT ticker, signal,
                           ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
                    FROM signals
                    WHERE date < ? AND signal_model_version = 'weekly_v2_0'
                ) WHERE rn = 1
            """, (as_of_date,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT ticker, signal AS prev_signal
                FROM (
                    SELECT ticker, signal,
                           ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
                    FROM signals
                    WHERE signal_model_version = 'weekly_v2_0'
                ) WHERE rn = 2
            """).fetchall()
    return {r["ticker"]: r["prev_signal"] for r in rows}


def import_lseg_rows(ticker: str, rows: list[tuple]) -> tuple[int, int]:
    """
    Bulk upsert LSEG rows for a ticker.
    rows: list of (date_str, open, high, low, close, volume)
    Returns (inserted, replaced).
    """
    if not rows:
        return 0, 0
    dates = [r[0] for r in rows]
    with db_conn() as conn:
        # Fetch existing dates in one query rather than one SELECT per row
        placeholders = ",".join("?" * len(dates))
        existing = {
            row[0]
            for row in conn.execute(
                f"SELECT date FROM prices WHERE ticker=? AND date IN ({placeholders})",
                [ticker] + dates,
            ).fetchall()
        }
        conn.executemany(
            "INSERT OR REPLACE INTO prices "
            "(date,ticker,open,high,low,close,volume,source) "
            "VALUES (?,?,?,?,?,?,?,'LSEG')",
            [(r[0], ticker, r[1], r[2], r[3], r[4], r[5]) for r in rows],
        )
    inserted = sum(1 for d in dates if d not in existing)
    replaced  = sum(1 for d in dates if d in existing)
    return inserted, replaced


def get_etf_universe():
    """Return full ETF list with sector, provider mapping for the ETF descriptions page."""
    with db_conn() as conn:
        rows = conn.execute('''
            SELECT
                e.ticker,
                e.name,
                e.sector,
                e.benchmark_ticker,
                GROUP_CONCAT(pf.code, '||') as fund_codes,
                GROUP_CONCAT(pf.name, '||') as fund_names
            FROM etf_meta e
            LEFT JOIN pension_etf_map pem ON e.ticker = pem.ticker
            LEFT JOIN pension_funds pf ON pem.fund_id = pf.id
            WHERE e.active = 1
            GROUP BY e.ticker
            ORDER BY e.sector, e.ticker
        ''').fetchall()
        return [dict(r) for r in rows]
