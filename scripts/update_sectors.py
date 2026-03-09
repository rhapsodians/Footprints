"""
Sector taxonomy update — Footprints v2.0
Adds new sector codes to config.py and updates etf_meta sector assignments in DB.

Run from your footprints2 directory:
  python3 update_sectors.py

Steps:
  1. Dry-run preview (no changes)
  2. Confirm → apply config.py patch + DB updates
"""
import sqlite3, os, sys, re, shutil
from datetime import datetime

DB_PATH     = os.path.join(os.path.dirname(__file__), "footprints.db")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.py")

# ── New sector taxonomy ───────────────────────────────────────────────────────
NEW_SECTOR_LABELS = {
    "BASE":   "Global Base",
    "US":     "United States",
    "NAM":    "North America",
    "UK":     "United Kingdom",
    "EUR":    "Europe",
    "JAP":    "Japan",
    "APAC":   "Asia-Pacific",
    "EM":     "Emerging Markets",
    "TECH":   "Technology",
    "HEALTH": "Healthcare",
    "DEF":    "Defence",
    "PROP":   "Property",
    "COMM":   "Commodities",
    "MINING": "Mining",
    "BOND":   "Bonds",
    "GLOBAL": "Global Factor",
    "OTHER":  "Other",
}

# ── ETF sector changes (ticker → new_sector) ─────────────────────────────────
ETF_UPDATES = {
    # Reclassified
    "ISWSML.L":  "GLOBAL",   # World Small Cap — factor tilt
    "MAGG.L":    "GLOBAL",   # Growth Portfolio — multi-asset factor
    "IITU.L":    "US",       # S&P 500 IT — US equity with sector tilt
    "V3NB.L":    "NAM",      # ESG N America All Cap — includes Canada
    "VNRG.L":    "NAM",      # North America — includes Canada
    "VEUA.L":    "EUR",      # Developed Europe
    "VJPB.L":    "JAP",      # Japan
    "VDPG.L":    "APAC",     # Dev Asia-Pac ex-Japan
    "LGAG.L":    "APAC",     # L&G Asia Pacific Ex Japan
    "VGVFEG.L":  "EM",       # Emerging Markets
    "GIGB.L":    "MINING",   # S&P Global Mining — equities not physical
    "IS15.L":    "BOND",     # £ Corp Bond
    "AGHG.L":    "BOND",     # Amundi Core Gl Aggregate Bd
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def check_paths():
    if not os.path.exists(DB_PATH):
        sys.exit(f"✗ DB not found: {DB_PATH}")
    if not os.path.exists(CONFIG_PATH):
        sys.exit(f"✗ config.py not found: {CONFIG_PATH}")

def get_current_assignments(conn):
    rows = conn.execute(
        "SELECT ticker, sector, name FROM etf_meta ORDER BY ticker"
    ).fetchall()
    return {r[0]: {"sector": r[1], "name": r[2]} for r in rows}

def preview(conn):
    current = get_current_assignments(conn)
    print("\n" + "═"*70)
    print("SECTOR TAXONOMY UPDATE — DRY RUN")
    print("═"*70)

    print(f"\n{'NEW SECTOR CODES':}")
    print(f"  {'CODE':<8} {'LABEL'}")
    print(f"  {'─'*6}  {'─'*22}")
    for code, label in sorted(NEW_SECTOR_LABELS.items()):
        print(f"  {code:<8} {label}")

    print(f"\n{'ETF SECTOR CHANGES (13 ETFs)':}")
    print(f"  {'TICKER':<14} {'FROM':<8} {'TO':<8} NAME")
    print(f"  {'─'*12}  {'─'*7}  {'─'*7}  {'─'*40}")
    for ticker, new_sector in sorted(ETF_UPDATES.items()):
        meta = current.get(ticker)
        if not meta:
            print(f"  {ticker:<14} ⚠ not found in DB")
            continue
        old = meta["sector"] or "?"
        name = (meta["name"] or "")[:40]
        print(f"  {ticker:<14} {old:<8} → {new_sector:<8} {name}")

    unchanged = [t for t in current if t not in ETF_UPDATES]
    print(f"\n  {len(ETF_UPDATES)} ETFs will change · {len(unchanged)} unchanged · {len(current)} total")
    print()

def apply_config(dry_run=False):
    with open(CONFIG_PATH, "r") as f:
        content = f.read()

    # Build new SECTOR_LABEL block
    lines = ['SECTOR_LABEL: dict[str, str] = {\n']
    for code, label in sorted(NEW_SECTOR_LABELS.items()):
        lines.append(f'    "{code}":{" " * (8 - len(code))}"{label}",\n')
    lines.append('}\n')
    new_block = "".join(lines)

    # Replace existing block
    pattern = r'SECTOR_LABEL: dict\[str, str\] = \{[^}]+\}\n'
    if not re.search(pattern, content):
        print("  ⚠ Could not locate SECTOR_LABEL block in config.py — skipping config update")
        return False

    new_content = re.sub(pattern, new_block, content)

    if dry_run:
        return True

    # Backup
    backup = CONFIG_PATH + f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(CONFIG_PATH, backup)
    print(f"  config.py backed up → {os.path.basename(backup)}")

    with open(CONFIG_PATH, "w") as f:
        f.write(new_content)
    print(f"  config.py updated — {len(NEW_SECTOR_LABELS)} sector codes written")
    return True

def apply_db(conn):
    updated = 0
    for ticker, new_sector in ETF_UPDATES.items():
        cur = conn.execute(
            "UPDATE etf_meta SET sector=? WHERE ticker=?", (new_sector, ticker)
        )
        if cur.rowcount:
            updated += 1
        else:
            print(f"  ⚠ {ticker} not found in DB — skipped")
    conn.commit()
    print(f"  DB updated — {updated} ETF sector assignments changed")

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    check_paths()
    conn = sqlite3.connect(DB_PATH)

    preview(conn)

    confirm = input("Apply these changes? [YES to proceed]: ").strip()
    if confirm != "YES":
        print("Aborted — no changes made.")
        conn.close()
        sys.exit(0)

    print("\nApplying...")
    apply_config(dry_run=False)
    apply_db(conn)
    conn.close()

    print("\n✓ Done.")
    print("  Restart your Flask server to pick up the new sector labels in config.py.")
