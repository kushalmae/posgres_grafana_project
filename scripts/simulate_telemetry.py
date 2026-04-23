import csv
import time
import math
import random
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
INTERVAL_SECONDS = 5

HEADER = ["timestamp", "apid", "satellite", "subsystem", "metric_name", "metric_value", "status"]

# APIDs are fleet-wide — same ID means same subsystem on any satellite
APIDS = {
    "power":   100,
    "thermal": 101,
    "obc":     102,
    "comms":   103,
    "adcs":    104,
}

SPACECRAFT = ["Sat-A", "Sat-B"]

# Status thresholds: (warning_low, critical_low, warning_high, critical_high)
THRESHOLDS = {
    "battery_voltage":      (27.0, 25.0, 32.0, 33.5),
    "solar_current":        (None, None, 8.5,  9.5),
    "panel_temp":           (-10,  -20,  60.0, 75.0),
    "cpu_temp":             (None, None, 70.0, 85.0),
    "cpu_usage":            (None, None, 80.0, 95.0),
    "memory_usage":         (None, None, 80.0, 92.0),
    "link_quality":         (70.0, 50.0, None, None),
    "downlink_rate_kbps":   (200,  80,   None, None),
    "reaction_wheel_rpm":   (None, None, 4800, 5000),
    "magnetometer_nt":      (-600, -900, 600,  900),
    "attitude_error_deg":   (None, None, 2.0,  5.0),
    "gyro_rate_dps":        (None, None, 3.0,  6.0),
}


def get_status(signal_name, value):
    t = THRESHOLDS.get(signal_name)
    if not t:
        return "NOMINAL"
    w_lo, c_lo, w_hi, c_hi = t
    if c_lo is not None and value < c_lo:
        return "CRITICAL"
    if c_hi is not None and value > c_hi:
        return "CRITICAL"
    if w_lo is not None and value < w_lo:
        return "WARNING"
    if w_hi is not None and value > w_hi:
        return "WARNING"
    return "NOMINAL"


def simulate_signals(t, spacecraft):
    """
    t = elapsed seconds since simulation start.
    Sat-B runs with a phase offset and slight degradation.
    """
    offset = 37.0 if spacecraft == "Sat-B" else 0.0
    orbit  = 2 * math.pi * (t + offset) / 5400
    noise  = lambda scale: random.gauss(0, scale)

    battery_degradation = 0.8 if spacecraft == "Sat-B" else 0.0
    battery_voltage = round(29.5 + 2.0 * math.sin(orbit) - battery_degradation + noise(0.05), 2)
    solar_current   = round(max(0.0, 5.5 * math.sin(orbit) + noise(0.2)), 2)

    panel_temp = round(25 + 35 * math.sin(orbit) + noise(0.3), 1)
    cpu_temp   = round(45 + 8 * math.sin(orbit * 2) + noise(0.5), 1)

    cpu_usage    = round(min(100, max(0, 35 + 20 * math.sin(orbit * 3 + 1) + noise(2))), 1)
    memory_usage = round(min(100, max(0, 52 + 5 * math.sin(orbit * 0.5) + noise(0.5))), 1)

    link_quality  = round(min(100, max(0, 92 + 6 * math.cos(orbit * 2) + noise(1))), 1)
    downlink_rate = round(max(0, 850 + 300 * math.cos(orbit * 2) + noise(10)), 0)

    reaction_wheel = round(3500 + 800 * math.sin(orbit * 4) + noise(5), 0)
    magnetometer   = round(450 * math.sin(orbit + 1.2) + noise(5), 1)
    attitude_error = round(abs(0.3 + 0.5 * math.sin(orbit * 7) + noise(0.05)), 3)
    gyro_rate      = round(abs(0.15 + 0.1 * math.sin(orbit * 5) + noise(0.01)), 4)

    return [
        ("power",   "battery_voltage",    battery_voltage),
        ("power",   "solar_current",      solar_current),
        ("thermal", "panel_temp",         panel_temp),
        ("thermal", "cpu_temp",           cpu_temp),
        ("obc",     "cpu_usage",          cpu_usage),
        ("obc",     "memory_usage",       memory_usage),
        ("comms",   "link_quality",       link_quality),
        ("comms",   "downlink_rate_kbps", downlink_rate),
        ("adcs",    "reaction_wheel_rpm", reaction_wheel),
        ("adcs",    "magnetometer_nt",    magnetometer),
        ("adcs",    "attitude_error_deg", attitude_error),
        ("adcs",    "gyro_rate_dps",      gyro_rate),
    ]


def sat_label(spacecraft):
    return spacecraft.lower().replace("-", "_")


def csv_path(spacecraft, apid):
    """One CSV per satellite per APID — e.g. data/sat_a_apid_100.csv"""
    return DATA_DIR / f"{sat_label(spacecraft)}_apid_{apid}.csv"


def ensure_headers():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for spacecraft in SPACECRAFT:
        for apid in APIDS.values():
            path = csv_path(spacecraft, apid)
            try:
                with open(path, "r") as f:
                    if f.readline().strip() == ",".join(HEADER):
                        continue
            except FileNotFoundError:
                pass
            with open(path, "w", newline="") as f:
                csv.writer(f).writerow(HEADER)


def append_rows(path, rows):
    with open(path, "a", newline="") as f:
        csv.writer(f).writerows(rows)


if __name__ == "__main__":
    ensure_headers()
    start = time.time()

    files = [f"{sat_label(sc)}_apid_{a}.csv" for sc in SPACECRAFT for a in sorted(APIDS.values())]
    print(f"Simulating telemetry — {len(files)} CSV files (one per satellite per APID)")
    print(f"Fleet: {SPACECRAFT} | APIDs: {APIDS}")
    print(f"Interval: {INTERVAL_SECONDS}s | Ctrl+C to stop\n")

    tick = 0
    while True:
        t = time.time() - start
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        all_rows = []
        for spacecraft in SPACECRAFT:
            by_apid = {}
            for subsystem, metric_name, value in simulate_signals(t, spacecraft):
                apid = APIDS[subsystem]
                status = get_status(metric_name, value)
                row = [now, apid, spacecraft, subsystem, metric_name, value, status]
                by_apid.setdefault(apid, []).append(row)
                all_rows.append(row)
            for apid, rows in by_apid.items():
                append_rows(csv_path(spacecraft, apid), rows)

        tick += 1
        total_rows = len(all_rows)
        alerts = [r for r in all_rows if r[6] != "NOMINAL"]
        alert_str = " | ".join(f"{r[2]} APID{r[1]} {r[4]}={r[5]} [{r[6]}]" for r in alerts)
        print(
            f"[tick {tick:04d}] {now}  +{total_rows} rows"
            + (f"  ALERTS: {alert_str}" if alert_str else "")
        )

        time.sleep(INTERVAL_SECONDS)
