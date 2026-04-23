import csv
import time
import math
import random
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "data" / "telemetry.csv"
INTERVAL_SECONDS = 5

HEADER = ["timestamp", "satellite", "subsystem", "metric_name", "metric_value", "status"]

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
    t = elapsed seconds since start
    Each signal uses sine/cosine to mimic orbital physics + noise.
    Sat-B runs slightly degraded to make dashboards interesting.
    """
    offset = 37.0 if spacecraft == "Sat-B" else 0.0   # phase offset between sats
    orbit  = 2 * math.pi * (t + offset) / 5400        # ~90 min orbit period
    noise  = lambda scale: random.gauss(0, scale)

    # Power subsystem
    # Battery charges in sunlight, drains in eclipse (sine wave)
    battery_base = 29.5 + 2.0 * math.sin(orbit)
    battery_degradation = 0.8 if spacecraft == "Sat-B" else 0.0
    battery_voltage = round(battery_base - battery_degradation + noise(0.05), 2)

    # Solar current peaks when facing sun
    solar_current = round(max(0.0, 5.5 * math.sin(orbit) + noise(0.2)), 2)

    # Thermal subsystem
    # Panel temp swings between eclipse cold and sunlit hot
    panel_temp = round(25 + 35 * math.sin(orbit) + noise(0.3), 1)
    cpu_temp   = round(45 + 8 * math.sin(orbit * 2) + noise(0.5), 1)

    # On-board computer
    cpu_usage    = round(min(100, max(0, 35 + 20 * math.sin(orbit * 3 + 1) + noise(2))), 1)
    memory_usage = round(min(100, max(0, 52 + 5 * math.sin(orbit * 0.5) + noise(0.5))), 1)

    # Comms subsystem
    # Link quality drops near horizon passes
    link_quality    = round(min(100, max(0, 92 + 6 * math.cos(orbit * 2) + noise(1))), 1)
    downlink_rate   = round(max(0, 850 + 300 * math.cos(orbit * 2) + noise(10)), 0)

    # ADCS (attitude determination and control)
    reaction_wheel  = round(3500 + 800 * math.sin(orbit * 4) + noise(5), 0)
    magnetometer    = round(450 * math.sin(orbit + 1.2) + noise(5), 1)
    attitude_error  = round(abs(0.3 + 0.5 * math.sin(orbit * 7) + noise(0.05)), 3)
    gyro_rate       = round(abs(0.15 + 0.1 * math.sin(orbit * 5) + noise(0.01)), 4)

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


def append_rows(rows):
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def ensure_header():
    try:
        with open(CSV_PATH, "r") as f:
            first = f.readline().strip()
            if first == ",".join(HEADER):
                return
    except FileNotFoundError:
        pass
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV_PATH, "w", newline="") as f:
        csv.writer(f).writerow(HEADER)


if __name__ == "__main__":
    ensure_header()
    start = time.time()
    print("Simulating telemetry — appending to", CSV_PATH)
    print("Signals: battery_voltage, solar_current, panel_temp, cpu_temp,")
    print("         cpu_usage, memory_usage, link_quality, downlink_rate_kbps,")
    print("         reaction_wheel_rpm, magnetometer_nt, attitude_error_deg, gyro_rate_dps")
    print(f"Interval: {INTERVAL_SECONDS}s | Ctrl+C to stop\n")

    tick = 0
    while True:
        t = time.time() - start
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        rows = []

        for spacecraft in ["Sat-A", "Sat-B"]:
            for subsystem, metric_name, value in simulate_signals(t, spacecraft):
                status = get_status(metric_name, value)
                rows.append([now, spacecraft, subsystem, metric_name, value, status])

        append_rows(rows)
        tick += 1

        non_nominal = [(r[1], r[3], r[4], r[5]) for r in rows if r[5] != "NOMINAL"]
        status_str = " | ".join(f"{sc} {sig}={val} [{st}]" for sc, sig, val, st in non_nominal)
        print(f"[tick {tick:04d}] {now}  +{len(rows)} rows" + (f"  ALERTS: {status_str}" if status_str else ""))

        time.sleep(INTERVAL_SECONDS)
