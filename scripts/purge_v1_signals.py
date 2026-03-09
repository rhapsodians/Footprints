"""
purge_v1_signals.py — one-time cleanup
Deletes all pre-v2 signal rows (signal_model_version IS NULL).
These are v1-era rows that are never served by the v2 dashboard.
Run from the footprints2 directory: python3 purge_v1_signals.py
"""
import db

with db.db_conn() as conn:
    n = conn.execute("SELECT COUNT(*) FROM signals WHERE signal_model_version IS NULL").fetchone()[0]
    print(f"Found {n} v1 signal rows.")
    if n == 0:
        print("Nothing to do.")
    else:
        confirm = input(f"Delete {n} rows? Type YES to confirm: ")
        if confirm.strip() == "YES":
            conn.execute("DELETE FROM signals WHERE signal_model_version IS NULL")
            print(f"Deleted {n} rows. v2 signals intact.")
        else:
            print("Aborted.")
