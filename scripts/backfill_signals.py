#!/usr/bin/env python3
"""
backfill_signals.py — back-populate v2 signals for all historical Fridays.

For each Friday that has full price coverage but no v2 signals, this script:
  1. Truncates the prices DataFrame to that Friday and earlier
  2. Runs run_engine() — which takes the last row per ticker (= that Friday's close)
  3. Writes the resulting signal rows with date = that Friday

Run from the footprints2 directory:
    python3 backfill_signals.py [--dry-run]
"""
import sys
from datetime import date

import pandas as pd

import db, engine


def get_backfill_fridays(prices_df: pd.DataFrame, existing_v2_dates: set[str]) -> list[str]:
    """
    Return all Fridays (ISO date strings) where:
    - Every active ticker has a price row on or before that Friday
    - No v2 signal already exists for that date
    Sorted oldest-first.
    """
    active_tickers = set(
        db.get_etf_meta()
        .query("active == 1 and suspended == 0")["ticker"]
    )
    n_required = len(active_tickers)

    # For each Friday in the price data, count how many active tickers
    # have at least one price row on or before that date
    prices_df = prices_df.copy()
    prices_df["date"] = pd.to_datetime(prices_df["date"])
    fridays = sorted(
        prices_df[prices_df["date"].dt.dayofweek == 4]["date"].dt.date.unique()
    )

    eligible = []
    for fri in fridays:
        fri_str = fri.isoformat()
        if fri_str in existing_v2_dates:
            continue  # already computed
        subset = prices_df[prices_df["date"].dt.date <= fri]
        coverage = subset[subset["ticker"].isin(active_tickers)]["ticker"].nunique()
        if coverage >= n_required:
            eligible.append(fri_str)

    return eligible


def backfill(dry_run: bool = False) -> None:
    print("Loading prices and meta...")
    prices_df = db.get_prices_df()
    meta_df   = db.get_etf_meta()
    existing_v2 = set(db.get_available_dates())

    fridays = get_backfill_fridays(prices_df, existing_v2)

    if not fridays:
        print("Nothing to backfill — all eligible Fridays already have v2 signals.")
        return

    print(f"Found {len(fridays)} Friday(s) to backfill:")
    for f in fridays:
        print(f"  {f}")

    if dry_run:
        print("\n[dry-run] No rows written.")
        return

    confirm = input(f"\nBackfill {len(fridays)} dates? Type YES to proceed: ")
    if confirm.strip() != "YES":
        print("Aborted.")
        return

    prices_df["date"] = pd.to_datetime(prices_df["date"])
    total_written = 0

    for fri in fridays:
        cutoff = pd.Timestamp(fri)
        # Truncate prices to this Friday and earlier so the engine sees
        # that Friday's close as the latest bar
        slice_df = prices_df[prices_df["date"] <= cutoff].copy()

        signal_rows, _ = engine.run_engine(slice_df, meta_df)

        # Force date to the Friday being backfilled (engine uses last bar date,
        # which should already match, but be explicit)
        for r in signal_rows:
            r["date"] = fri

        if signal_rows:
            n = db.upsert_signals(signal_rows)
            total_written += n
            print(f"  {fri}  →  {n} signals written")
        else:
            print(f"  {fri}  →  0 signals (skipped)")

    print(f"\nDone. {total_written} signal rows written across {len(fridays)} dates.")
    print("Dates now available in the dashboard dropdown:")
    for d in db.get_available_dates():
        print(f"  {d}")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    backfill(dry_run=dry_run)
