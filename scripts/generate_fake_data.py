"""
Generates historical telemetry into per-satellite per-APID CSV files.
Wipes existing APID CSVs and clears ingest state so everything re-ingests clean.

Usage:
    python scripts/generate_fake_data.py [--days N] [--interval-minutes M]
"""
import csv
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from simulate_telemetry import (
    simulate_signals, get_status,
    APIDS, SPACECRAFT, HEADER,
    csv_path, sat_label, DATA_DIR,
)


def generate(days: int, interval_minutes: int):
    end   = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(days=days)

    # Wipe and re-initialise all CSVs
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for spacecraft in SPACECRAFT:
        for apid in APIDS.values():
            with open(csv_path(spacecraft, apid), "w", newline="") as f:
                csv.writer(f).writerow(HEADER)

    # Clear ingest state so files are fully re-ingested
    state_file = DATA_DIR / ".ingest_state.json"
    if state_file.exists():
        state_file.unlink()
        print("Cleared ingest state.")

    step = timedelta(minutes=interval_minutes)
    current = start
    total_rows = 0
    ticks = 0

    # Pre-open one file handle per (spacecraft, apid)
    handles = {
        (sc, apid): open(csv_path(sc, apid), "a", newline="")
        for sc in SPACECRAFT
        for apid in APIDS.values()
    }
    writers = {key: csv.writer(f) for key, f in handles.items()}

    try:
        while current <= end:
            t = (current - start).total_seconds()
            timestamp = current.strftime("%Y-%m-%d %H:%M:%S")

            for spacecraft in SPACECRAFT:
                for subsystem, metric_name, value in simulate_signals(t, spacecraft):
                    apid = APIDS[subsystem]
                    status = get_status(metric_name, value)
                    writers[(spacecraft, apid)].writerow(
                        [timestamp, apid, spacecraft, subsystem, metric_name, value, status]
                    )
                    total_rows += 1

            current += step
            ticks += 1

            if ticks % 500 == 0:
                pct = (current - start) / timedelta(days=days) * 100
                print(f"  {pct:5.1f}%  {current.strftime('%Y-%m-%d %H:%M')}  ({total_rows:,} rows)")
    finally:
        for f in handles.values():
            f.close()

    return total_rows, ticks


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--interval-minutes", type=int, default=1)
    args = parser.parse_args()

    print(f"Generating {args.days} days at {args.interval_minutes}-min intervals...")
    print(f"Fleet: {SPACECRAFT}")
    print(f"APIDs (fleet-wide): { {v: k for k, v in APIDS.items()} }\n")

    total_rows, ticks = generate(args.days, args.interval_minutes)

    print(f"\nDone. {ticks} ticks × {len(SPACECRAFT)} sats × 12 signals = {total_rows:,} rows")
    print("Files written:")
    for spacecraft in SPACECRAFT:
        for subsystem, apid in sorted(APIDS.items(), key=lambda x: x[1]):
            path = csv_path(spacecraft, apid)
            size_kb = path.stat().st_size / 1024
            print(f"  {path.name:<30s}  {size_kb:7.1f} KB")
    print("\nRun: python scripts/ingest_csv_to_postgres.py --once")
