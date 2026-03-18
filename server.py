"""
Footprints v2.0 — server.py
All business logic in engine.py / db.py. This file = routes + helpers only.
"""
import io, json, os
from datetime import date, timedelta, datetime

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from flask import (Flask, request, redirect, url_for,
                   render_template, flash, jsonify, send_file, make_response)

from collections import Counter
from config import SIG_STRONG_BUY, SIG_ACCUM, SIG_EXIT, SIG_EARLY_ACCUM
import config, db, engine

app = Flask(__name__)
app.secret_key = os.environ.get("FP2_SECRET_KEY", "fp2-dev-secret-change-in-production")

# ── Jinja helpers ─────────────────────────────────────────────────────────────
def _heat_class(v):
    try: v = float(v)
    except: return "heat-na"
    if v >= 75: return "heat-h"
    if v >= 55: return "heat-mh"
    if v >= 40: return "heat-m"
    if v >= 20: return "heat-ml"
    return "heat-l"

app.jinja_env.globals["heat_class"] = _heat_class
app.jinja_env.globals["get_flashed_messages"] = __import__("flask").get_flashed_messages

def _ctx(nav="", as_of=""):
    return dict(active_nav=nav, as_of_date=as_of,
                sector_labels=config.SECTOR_LABEL, sectors=config.SECTORS,
                sig_css=config.SIGNAL_CSS, model_version=config.MODEL_VERSION,
                base_ticker=config.BASE_TICKER)

def _dicts(rows):
    if hasattr(rows, "to_dict"): return rows.to_dict(orient="records")
    return [dict(r) for r in rows]

def _next_friday():
    """Return the coming Friday's date, or today if today is Friday."""
    d = date.today()
    days = (4 - d.weekday()) % 7   # 0 on Friday → return today
    return (d + timedelta(days=days)).isoformat()

# ── LSEG Excel parser (same as v1) ────────────────────────────────────────────
def _parse_lseg(file_bytes):
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
    ws = wb.active
    hrow = hdata = None
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if row[0] == "Exchange Date":
            hrow = i; hdata = row; break
    if hrow is None:
        raise ValueError("Cannot find 'Exchange Date' header — is this a standard LSEG export?")
    col = {}
    for j, h in enumerate(hdata or []):
        if not h: continue
        hn = str(h).strip().lower()
        if   hn == "close":  col["close"]  = j
        elif hn == "open":   col["open"]   = j
        elif hn == "low":    col["low"]    = j
        elif hn == "high":   col["high"]   = j
        elif hn == "volume": col["volume"] = j
    ci = col.get("close", 1)
    def _g(row, k, d):
        idx = col.get(k)
        if idx is None: return d
        return float(row[idx]) if idx < len(row) and row[idx] is not None else d
    out = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i <= hrow: continue
        if not row[0] or not isinstance(row[0], datetime): continue
        c = row[ci] if ci < len(row) else None
        if c is None: continue
        c = float(c)
        out.append((str(row[0].date()), _g(row,"open",c), _g(row,"high",c),
                    _g(row,"low",c), c, _g(row,"volume",0.0)))
    return sorted(out, key=lambda x: x[0])

# ── Dashboard data helpers ────────────────────────────────────────────────────
def _enrich_signals(signals):
    """Add fields the dashboard JS needs that v2 engine stores differently."""
    for r in signals:
        # rs20_raw is a decimal excess return (e.g. 0.08 = +8%); multiply by 100 for display
        raw = r.get("rs20_raw")
        r["rs20_pct"] = (raw * 100) if raw is not None else 0.0
        # pressure → crdp20
        r["crdp20"] = r.get("pressure_20w") or 0.0
        # trend score as int
        r["trend"] = int(r.get("trend_score_raw") or 0)
        # dv_surprise — v2 has turnover_ratio_20_100
        r["dv_surprise"] = r.get("turnover_ratio_20_100") or 1.0
        # ret20/ret3m — computed from price series if present
        ps = r.get("price_series", [])
        if len(ps) >= 20:
            r["ret20_pct"] = (ps[-1]["c"] / ps[-20]["c"] - 1) * 100
        else:
            r["ret20_pct"] = None
        if len(ps) >= 63:
            r["ret_3m_pct"] = (ps[-1]["c"] / ps[-63]["c"] - 1) * 100
        else:
            r["ret_3m_pct"] = None
    return signals

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    signals_df = db.get_signals_df()
    signals    = _dicts(signals_df)
    dates      = db.get_available_dates()
    as_of      = dates[0] if dates else "—"
    counts = Counter(r.get("signal") or "NO DATA" for r in signals)
    ctx = _ctx("home", as_of)
    ctx.update(sig_counts=dict(counts), n_active=len(signals), as_of=as_of)
    return render_template("home.html", **ctx)

# ── Entry ─────────────────────────────────────────────────────────────────────
@app.route("/entry")
def entry():
    data      = db.get_weekly_entry_data()
    latest_p  = db.get_latest_prices()
    sigs_df   = db.get_signals_df()
    signals   = {r["ticker"]: r for r in _dicts(sigs_df)}
    prefill   = {}
    ctx = _ctx("entry")
    ctx.update(tickers=data["tickers"], default_date=_next_friday(),
               latest_prices=latest_p, signals=signals, prefill=prefill)
    return render_template("entry.html", **ctx)

@app.route("/entry", methods=["POST"])
def entry_post():
    entry_date = request.form.get("date","").strip()
    if not entry_date:
        flash("No date supplied.","err"); return redirect(url_for("entry"))
    td: dict[str,dict] = {}
    for key, val in request.form.items():
        if "__" not in key or not val.strip(): continue
        ticker, field = key.rsplit("__", 1)
        if field not in ("open","high","low","close","volume"): continue
        td.setdefault(ticker, {})[field] = val.strip()
    saved = skipped = 0
    for ticker, f in td.items():
        if not f.get("close"):
            skipped += 1; continue
        db.upsert_price_row({"date":entry_date,"ticker":ticker,
            "open":f.get("open") or f["close"],"high":f.get("high") or f["close"],
            "low":f.get("low") or f["close"],"close":f["close"],
            "volume":f.get("volume") or 0,"source":"LSEG"})
        saved += 1
    if saved:
        flash(f"Saved {saved} row(s) for {entry_date}.","ok")
        try:
            s_rows, c_rows = engine.run_engine(
                db.get_prices_df(), db.get_etf_meta(), db.get_signals_df(),
                as_of_date=entry_date,
            )
            db.upsert_signals(s_rows); db.log_signal_changes(c_rows)
            if c_rows:
                parts = " | ".join(f"{c['ticker']}: {c['old_signal']} → {c['new_signal']}" for c in c_rows)
                flash(f"Signal changes: {parts}","ok")
        except Exception as e:
            flash(f"Recompute failed: {e}","err")
    else:
        flash("No rows saved — fill at least one Close.","err")
    return redirect(url_for("entry"))

@app.route("/entry/import-lseg", methods=["POST"])
def entry_import_lseg():
    ticker = request.form.get("ticker","").strip().upper()
    f = request.files.get("lseg_file")
    if not ticker or not f:
        flash("Missing ticker or file.","err"); return redirect(url_for("entry"))
    try: rows = _parse_lseg(f.read())
    except Exception as e:
        flash(f"Parse error: {e}","err"); return redirect(url_for("entry"))
    if not rows:
        flash(f"No valid rows for {ticker}.","err"); return redirect(url_for("entry"))
    ins, rep = db.import_lseg_rows(ticker, rows)
    flash(f"{ticker}: {ins} new rows" + (f", {rep} updated." if rep else "."),"ok")
    return redirect(url_for("entry"))

@app.route("/entry/import-lseg-bulk", methods=["POST"])
def entry_import_lseg_bulk():
    import os as _os
    files = request.files.getlist("bulk_files")
    if not files or all(f.filename == "" for f in files):
        flash("No files selected.", "err"); return redirect(url_for("entry"))

    known = set(db.get_active_tickers())
    results, errors = [], []

    for f in files:
        fname = f.filename or ""
        # Strip extension(s): AGHG.L.xlsx -> AGHG.L, BOTZ.L.xls -> BOTZ.L
        base = _os.path.splitext(fname)[0]
        ticker = base.upper().strip()

        if not ticker:
            errors.append(f"Unnamed file skipped")
            continue

        if ticker not in known:
            errors.append(f"{fname} — '{ticker}' not in universe")
            continue

        try:
            rows = _parse_lseg(f.read())
        except Exception as e:
            errors.append(f"{ticker} — parse error: {e}")
            continue

        if not rows:
            errors.append(f"{ticker} — no valid rows in file")
            continue

        try:
            ins, rep = db.import_lseg_rows(ticker, rows)
            results.append(f"{ticker}: +{ins} new, {rep} updated")
        except Exception as e:
            errors.append(f"{ticker} — DB error: {e}")

    if results:
        flash(f"Bulk import: {len(results)} ETF(s) — " + " · ".join(results), "ok")
    for err in errors:
        flash(f"⚠ {err}", "err")
    if not results and not errors:
        flash("No files processed.", "err")

    return redirect(url_for("entry"))


# ── Recompute ─────────────────────────────────────────────────────────────────
@app.route("/recompute", methods=["POST"])
def recompute():
    selected_date = request.form.get("date", "").strip()
    as_of_date    = request.form.get("as_of_date", "").strip() or None
    try:
        s_rows, c_rows = engine.run_engine(
            db.get_prices_df(), db.get_etf_meta(), db.get_signals_df(),
            as_of_date=as_of_date,
        )
        db.upsert_signals(s_rows); db.log_signal_changes(c_rows)
        date_label = f" for {as_of_date}" if as_of_date else ""
        msg = f"Recomputed {len(s_rows)} signals{date_label}."
        if c_rows: msg += f" {len(c_rows)} change(s) logged."
        flash(msg,"ok")
    except Exception as e:
        flash(f"Recompute failed: {e}","err"); raise
    # Redirect to the recomputed date (never a future date)
    today_str = date.today().isoformat()
    target = as_of_date or selected_date or ""
    if target > today_str:
        target = ""
    dest = url_for("dashboard")
    if target:
        dest += f"?date={target}"
    return redirect(dest)

# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    as_of     = request.args.get("date","")
    today_str = date.today().isoformat()
    dates     = [d for d in db.get_available_dates() if d <= today_str]
    if not as_of and dates: as_of = dates[0]
    sigs_df   = db.get_signals_df(as_of_date=as_of if as_of else None)
    signals   = _dicts(sigs_df)

    # Attach price series for sparklines + ret calculations
    # Only date + close inlined; open/high/low/volume fetched on demand via /api/prices
    tickers   = [r["ticker"] for r in signals]
    price_map = db.get_price_series_bulk(tickers, limit_per=config.SPARKLINE_WEEKS, as_of=as_of or None)
    for r in signals:
        daily = price_map.get(r["ticker"], [])
        # Resample daily → weekly (last close of each ISO week) server-side
        week_buckets: dict = {}
        for p in daily:
            d   = date.fromisoformat(p["d"])
            thu = d + timedelta(days=(3 - d.weekday()))
            key = thu.isocalendar()[:2]          # (year, isoweek)
            if key not in week_buckets or p["d"] > week_buckets[key]["d"]:
                week_buckets[key] = p
        weekly  = [week_buckets[k] for k in sorted(week_buckets)]
        closes  = [p["c"] for p in weekly]
        dates_w = [p["d"] for p in weekly]
        ma20    = [round(sum(closes[i-19:i+1])/20,  4) if i >= 19 else None for i in range(len(closes))]
        ma100   = [round(sum(closes[i-99:i+1])/100, 4) if i >= 99 else None for i in range(len(closes))]
        r["price_series"]  = [{"d": p["d"], "c": p["c"]} for p in daily]  # daily, for ret calcs
        r["weekly_dates"]  = dates_w
        r["weekly_closes"] = closes
        r["weekly_ma20"]   = ma20
        r["weekly_ma100"]  = ma100

    # Enrich with v1-compatible field names
    signals = _enrich_signals(signals)

    # Pension fund memberships
    fund_map, etf_fund_map = db.get_pension_maps()
    for r in signals:
        r["funds"] = etf_fund_map.get(r["ticker"], [])

    # Previous signal (for transition badge)
    prev_map = db.get_prev_signals(as_of_date=as_of if as_of else None)
    for r in signals:
        ps = prev_map.get(r["ticker"])
        r["prev_signal"] = ps if ps and ps != r.get("signal") else None
        r["signal_date"] = None  # v2 doesn't store transition date separately

    etf_data_js = json.dumps({r["ticker"]: r for r in signals}, default=str)
    fund_map_js = json.dumps({str(fid):{"code":fd["code"],"name":fd["name"],"tickers":fd["tickers"]}
                               for fid,fd in fund_map.items()})

    stats = dict(
        total=len(signals),
        strong_buy=sum(1 for r in signals if r.get("signal")==SIG_STRONG_BUY),
        early_acc=sum(1 for r in signals if r.get("signal")==SIG_EARLY_ACCUM),
        accum=sum(1 for r in signals if r.get("signal")==SIG_ACCUM),
        neutral=sum(1 for r in signals if r.get("signal")=="NEUTRAL"),
        exit=sum(1 for r in signals if r.get("signal")==SIG_EXIT),
        high_conf=sum(1 for r in signals if r.get("confidence_bucket")=="HIGH"),
        avg_rotation=f"{sum(r.get('rotation_score') or 0 for r in signals)/len(signals):.1f}" if signals else "—",
    )
    ctx = _ctx("dashboard", as_of)
    ctx.update(dates=dates, stats=stats,
               etf_data_js=etf_data_js, fund_map_js=fund_map_js,
               pension_funds=list(fund_map.values()))
    resp = make_response(render_template("dashboard.html", **ctx))
    resp.headers["Cache-Control"] = "no-store"
    return resp

# ── Heatmap ───────────────────────────────────────────────────────────────────
@app.route("/heatmap")
def heatmap():
    as_of = request.args.get("date","")
    today_str = date.today().isoformat()
    dates = [d for d in db.get_available_dates() if d <= today_str]
    if not as_of and dates: as_of = dates[0]
    sigs  = _dicts(db.get_signals_df(as_of_date=as_of if as_of else None))
    sigs  = _enrich_signals(sigs)
    sigs.sort(key=lambda r:(r.get("sector") or "",-(r.get("rotation_score") or 0)))
    seen = {}
    for r in sigs:
        s = r.get("sector","")
        if s and s not in seen:
            seen[s] = {k:r.get(k) for k in
                ("sector","sector_count","sector_pct_rs4_pos","sector_pct_rs12_pos",
                 "sector_pct_rs20_pos","sector_pct_positive_pressure",
                 "sector_pct_above_ma100","sector_score","sector_confirmed")}
    # Pension fund memberships
    fund_map, etf_fund_map = db.get_pension_maps()
    for r in sigs:
        r["funds"] = etf_fund_map.get(r["ticker"], [])
    fund_map_js = json.dumps({str(fid):{"code":fd["code"],"name":fd["name"],"tickers":fd["tickers"]}
                               for fid,fd in fund_map.items()})
    rows_js = json.dumps(sigs, default=str)

    # ── Weekly summary data (merged into same page) ───────────────────────
    prev_map = db.get_prev_signals(as_of_date=as_of if as_of else None)
    for r in sigs:
        ps = prev_map.get(r["ticker"])
        r["prev_signal"] = ps if ps and ps != r.get("signal") else None

    SIG_ORDER = {SIG_STRONG_BUY:0, SIG_EARLY_ACCUM:1, SIG_ACCUM:2, "NEUTRAL":3, SIG_EXIT:4}
    lg_map = {fid:fd for fid,fd in fund_map.items() if fd["code"].startswith("LG")}
    il_map = {fid:fd for fid,fd in fund_map.items() if fd["code"].startswith("IL")}
    lg_rows = _build_fund_rows(lg_map, sigs, SIG_ORDER)
    il_rows = _build_fund_rows(il_map, sigs, SIG_ORDER)

    all_fund_tickers = {t for fd in fund_map.values() for t in fd["tickers"]}
    def sig_rank(r):
        return (SIG_ORDER.get(r.get("signal","NEUTRAL"),3), -(r.get("rotation_score") or 0))
    notable = sorted(
        [r for r in sigs if r["ticker"] not in all_fund_tickers
         and r.get("signal") in (SIG_STRONG_BUY, SIG_EARLY_ACCUM, SIG_EXIT)],
        key=sig_rank
    )
    portfolio = dict(
        total=len(sigs),
        strong_buy=sum(1 for r in sigs if r.get("signal")==SIG_STRONG_BUY),
        early_acc=sum(1 for r in sigs if r.get("signal")==SIG_EARLY_ACCUM),
        accum=sum(1 for r in sigs if r.get("signal")==SIG_ACCUM),
        neutral=sum(1 for r in sigs if r.get("signal")=="NEUTRAL"),
        exit=sum(1 for r in sigs if r.get("signal")==SIG_EXIT),
        high_conf=sum(1 for r in sigs if r.get("confidence_bucket")=="HIGH"),
        transitions=sum(1 for r in sigs if r.get("prev_signal")),
    )

    ctx = _ctx("heatmap", as_of)
    ctx.update(
        dates=dates, signals=sigs,
        sector_stats=sorted(seen.values(),key=lambda s:-(s.get("sector_score") or 0)),
        fund_map_js=fund_map_js, rows_js=rows_js,
        lg_rows=lg_rows, il_rows=il_rows, notable=notable, portfolio=portfolio,
        sig_strong_buy=SIG_STRONG_BUY, sig_early_accum=SIG_EARLY_ACCUM,
        sig_accum=SIG_ACCUM, sig_exit=SIG_EXIT,
    )
    return render_template("heatmap.html", **ctx)



# ── Fund row helpers (used by heatmap route) ──────────────────────────────────

def _stance(buy_n, exit_n, neu_n, total):
    if buy_n == total:                              return "POSITIVE"
    if exit_n == total:                             return "NEGATIVE"
    if buy_n > exit_n and buy_n >= total * 0.6:    return "POSITIVE"
    if exit_n >= total * 0.5:                       return "NEGATIVE"
    if exit_n > buy_n and exit_n >= total * 0.4:   return "CAUTIOUS"
    if buy_n > 0 and exit_n == 0:                  return "MILD POS"
    if exit_n > 0 and buy_n == 0:                  return "MILD NEG"
    return "MIXED"


def _build_fund_rows(fund_map, sigs, SIG_ORDER):
    """Return list of fund dicts, sorted positive→negative within each provider."""
    def sig_rank(r):
        return (SIG_ORDER.get(r.get("signal","NEUTRAL"), 3), -(r.get("rotation_score") or 0))

    rows = []
    for fid, fd in fund_map.items():
        fund_tickers = set(fd["tickers"])
        fund_sigs = [r for r in sigs if r["ticker"] in fund_tickers]
        if not fund_sigs:
            continue
        fund_sigs.sort(key=sig_rank)
        buys  = [r for r in fund_sigs if r.get("signal") in (SIG_STRONG_BUY, SIG_EARLY_ACCUM, SIG_ACCUM)]
        exits = [r for r in fund_sigs if r.get("signal") == SIG_EXIT]
        neu   = [r for r in fund_sigs if r.get("signal") == "NEUTRAL"]
        total = len(fund_sigs)
        stance = _stance(len(buys), len(exits), len(neu), total)
        STANCE_ORDER = {"POSITIVE":0,"MILD POS":1,"MIXED":2,"CAUTIOUS":3,"MILD NEG":4,"NEGATIVE":5}
        rows.append(dict(
            id=fid, code=fd["code"], name=fd["name"],
            stance=stance, stance_order=STANCE_ORDER.get(stance,3),
            sigs=fund_sigs, buy_n=len(buys), exit_n=len(exits), neu_n=len(neu), total=total,
            transitions=[(r["ticker"],r["prev_signal"],r["signal"])
                         for r in fund_sigs if r.get("prev_signal")],
        ))
    rows.sort(key=lambda x: (x["stance_order"], x["code"]))
    return rows
# ── History ───────────────────────────────────────────────────────────────────
@app.route("/history")
def history():
    ctx = _ctx("history")
    ctx.update(history=_dicts(db.get_signal_history(limit=300)),
               dates=db.get_available_dates())
    return render_template("history.html", **ctx)

@app.route("/history/etf/<ticker>")
def etf_history(ticker):
    ticker  = ticker.upper()
    prices  = db.get_price_series(ticker, limit=config.PRICE_HISTORY_LIMIT)
    sig_h   = db.get_ticker_signal_history(ticker)
    meta_df = db.get_etf_meta()
    row     = meta_df[meta_df["ticker"]==ticker]
    name    = row["name"].iloc[0] if not row.empty else ticker
    sector  = row["sector"].iloc[0] if not row.empty else ""
    ctx     = _ctx("history")
    ctx.update(ticker=ticker, name=name, sector=sector,
               prices=list(reversed(prices)), sig_hist=sig_h,
               prices_js=json.dumps(prices))
    return render_template("etf_history.html", **ctx)

# ── Guide ─────────────────────────────────────────────────────────────────────
@app.route("/guide")
def guide():
    return render_template("guide.html", **_ctx("guide"))

# ── Admin ─────────────────────────────────────────────────────────────────────
@app.route("/admin")
def admin():
    meta_df = db.get_etf_meta()
    etfs    = sorted(_dicts(meta_df), key=lambda e: e.get("ticker",""))
    with db.db_conn() as conn:
        rc = {r[0]:r[1] for r in conn.execute("SELECT ticker,COUNT(*) FROM prices GROUP BY ticker").fetchall()}
        pr = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
        dr = conn.execute("SELECT MIN(date),MAX(date) FROM prices").fetchone()
        sr = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    for e in etfs: e["rows"] = rc.get(e["ticker"],0)
    fund_map, _ = db.get_pension_maps()
    pension_funds_with_tickers = [
        {**f, "tickers": fund_map[f["id"]]["tickers"]}
        for f in db.get_pension_funds()
    ]
    ctx = _ctx("admin")
    ctx.update(etfs=etfs, pension_funds=pension_funds_with_tickers,
               db_stats=dict(price_rows=pr, date_min=dr[0] or "—",
                             date_max=dr[1] or "—", signal_rows=sr,
                             model_version=config.MODEL_VERSION))
    return render_template("admin.html", **ctx)

@app.route("/admin/add_etf", methods=["POST"])
def admin_add_etf():
    f = request.files.get("lseg_file")
    meta = dict(ticker=request.form.get("ticker","").strip().upper(),
                name=request.form.get("name","").strip(),
                sector=request.form.get("sector","OTHER"),
                benchmark_ticker=request.form.get("benchmark_ticker",config.BASE_TICKER).strip(),
                display_order=int(request.form.get("display_order",99) or 99),
                active=1, suspended=0)
    if not meta["ticker"]:
        flash("Ticker required.","err"); return redirect(url_for("admin"))
    db.add_etf(meta)
    if f and f.filename:
        try:
            rows = _parse_lseg(f.read())
            ins,rep = db.import_lseg_rows(meta["ticker"],rows)
            flash(f"Added {meta['ticker']} with {ins} price rows.","ok")
        except Exception as e:
            flash(f"Added {meta['ticker']} but history import failed: {e}","err")
    else:
        flash(f"Added {meta['ticker']}.","ok")
    return redirect(url_for("admin"))

@app.route("/admin/delete-etf", methods=["POST"])
def admin_delete_etf():
    t = request.form.get("ticker","").strip().upper()
    if not t:
        flash("No ticker provided.","err"); return redirect(url_for("admin"))
    try:
        db.delete_etf(t)
        flash(f"{t} permanently deleted — all price and signal data removed.","ok")
    except Exception as e:
        flash(f"Delete failed: {e}","err")
    return redirect(url_for("admin"))

@app.route("/admin/import-gap", methods=["POST"])
def admin_import_gap():
    t = request.form.get("ticker","").upper()
    f = request.files.get("lseg_file")
    if not t or not f:
        flash("Missing ticker or file.","err"); return redirect(url_for("admin"))
    try:
        rows = _parse_lseg(f.read())
        ins,rep = db.import_lseg_rows(t, rows)
        flash(f"{t} gap fill: {ins} new, {rep} updated.","ok")
    except Exception as e:
        flash(f"Gap fill failed: {e}","err")
    return redirect(url_for("admin"))

@app.route("/admin/add-fund", methods=["POST"])
def admin_add_fund():
    code = request.form.get("code","").strip().upper()
    name = request.form.get("name","").strip()
    if not code or not name:
        flash("Code and name required.","err"); return redirect(url_for("admin"))
    db.add_pension_fund(code, name)
    flash(f"Fund '{code}' added.","ok")
    return redirect(url_for("admin"))

@app.route("/admin/remove-fund", methods=["POST"])
def admin_remove_fund():
    db.remove_pension_fund(int(request.form.get("fund_id",0)))
    flash("Fund removed.","ok")
    return redirect(url_for("admin"))

@app.route("/admin/add-proxy", methods=["POST"])
def admin_add_proxy():
    fid = int(request.form.get("fund_id",0))
    t   = request.form.get("ticker","").upper()
    db.add_pension_proxy(fid, t)
    flash(f"{t} added to fund.","ok")
    return redirect(url_for("admin"))

@app.route("/admin/remove-proxy", methods=["POST"])
def admin_remove_proxy():
    fid = int(request.form.get("fund_id",0))
    t   = request.form.get("ticker","").upper()
    db.remove_pension_proxy(fid, t)
    flash(f"{t} removed from fund.","ok")
    return redirect(url_for("admin"))

# ── APIs ──────────────────────────────────────────────────────────────────────
@app.route("/api/prices/<ticker>")
def api_prices(ticker):
    rows = db.get_price_series(ticker.upper(), limit=config.PRICE_HISTORY_LIMIT)
    # Add turnover field
    for r in rows:
        r["turnover"] = (r["c"] * r["v"]) if r.get("v") else None
    return jsonify({"rows": rows})

@app.route("/api/signals")
def api_signals():
    return jsonify(_dicts(db.get_signals_df()))

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    db.init_schema()
    debug = os.environ.get("FP2_DEBUG", "0").lower() in ("1", "true", "yes")
    print(f"Footprints v{config.APP_VERSION} — http://localhost:5000")
    app.run(debug=debug, port=5000)
