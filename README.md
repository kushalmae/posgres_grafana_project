# Local Telemetry Pipeline: CSV → PostgreSQL → Grafana

A local near-real-time telemetry dashboard pipeline. Python polls CSV files every 5 seconds, inserts new rows into PostgreSQL (deduped by row hash), and Grafana queries Postgres to render live panels.

```
/data/*.csv  →  Python ingestor (poll 5s)  →  Local Postgres  →  Grafana (refresh 5–10s)
```

---

## Project Structure

```
.
├── docker-compose.yml          # Postgres + Grafana
├── requirements.txt
├── db/
│   └── init_db.sql             # Schema — mounted on first Postgres start
├── scripts/
│   ├── ingest_csv_to_postgres.py
│   ├── simulate_telemetry.py   # Optional synthetic CSV append
│   └── export_grafana_dashboards.py
├── data/
│   └── telemetry.csv           # Sample / live CSV input
├── grafana/
│   ├── dashboards/
│   └── provisioning/
│       ├── dashboards/dashboards.yml
│       └── datasources/datasources.yml
└── .gitignore
```

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Python 3.9+

---

## Quick Start

### 1. Start containers

```bash
docker compose up -d
```

This starts:
- **PostgreSQL 16** on `localhost:5432`
- **Grafana** on `http://localhost:3000`

The schema (`telemetry_history` and `telemetry_latest`) is created automatically from `db/init_db.sql` on first run.

Grafana is provisioned on startup with:
- a **PostgreSQL** data source (UID `telemetry_pg`, default) pointing at the `postgres` service
- the dashboards under `grafana/dashboards/` (Mission Control, fleet telemetry, spacecraft detail)

If you already had Grafana data volumes from an older setup, you may see a second legacy data source in the UI; you can delete the unused one, or reset with `docker compose down -v` (this wipes Postgres data too).

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the ingestor

```bash
python scripts/ingest_csv_to_postgres.py
```

The ingestor watches `./data/` every 5 seconds. New rows appended to any `.csv` file will be inserted into Postgres automatically. Duplicate rows are silently ignored via SHA-256 row hash.

### Optional: live sample data

In a second terminal:

```bash
python scripts/simulate_telemetry.py
```

This appends new rows to `./data/telemetry.csv` on the same cadence as the ingestor so dashboards update continuously.

---

## CSV Format

Place CSV files in the `./data/` folder. Required columns:

| Column | Type | Example |
|---|---|---|
| `timestamp` | datetime | `2026-04-18 10:00:00` |
| `satellite` | text | `Sat-A` |
| `subsystem` | text | `power` |
| `metric_name` | text | `battery_voltage` |
| `metric_value` | float | `28.4` |
| `status` | text | `NOMINAL` |

Optional column: `signal_unit` (e.g. `V`, `°C`, `%`)

Example:

```csv
timestamp,satellite,subsystem,metric_name,metric_value,status
2026-04-18 10:00:00,Sat-A,power,battery_voltage,28.4,NOMINAL
2026-04-18 10:00:05,Sat-A,power,battery_voltage,28.3,NOMINAL
2026-04-18 10:00:10,Sat-B,power,battery_voltage,26.1,CRITICAL
```

---

## Database Schema

### `telemetry_history`
Append-only table. Every observed value is stored here. Powers time-series panels.

| Column | Description |
|---|---|
| `observed_at` | Timestamp from CSV |
| `spacecraft` | Satellite name |
| `subsystem` | Subsystem (power, thermal, comms) |
| `signal_name` | Metric name |
| `signal_value` | Numeric value |
| `signal_unit` | Unit (optional) |
| `status` | NOMINAL / WARNING / CRITICAL |
| `source_file` | Source CSV filename |
| `row_hash` | SHA-256 dedup key (UNIQUE) |

### `telemetry_latest`
Upserted on every ingest cycle. One row per `(spacecraft, subsystem, signal_name)`. Powers status boards and stat panels.

---

## Grafana

Open **http://localhost:3000** (default login `admin` / `admin`). The **Telemetry PostgreSQL** data source and fleet dashboards are loaded from `grafana/provisioning/`.

If you disabled provisioning or need a manual data source, use host `postgres:5432` (the Docker service name, not `localhost`), database `local_csv_db`, user `grafana_user`, password `grafana_password`, TLS disabled.

To export dashboards from a running instance into this repo’s format, run `python scripts/export_grafana_dashboards.py --flat` so JSON matches file provisioning (inner dashboard object only).

---

## Grafana Queries

### Time-series — all signals
```sql
SELECT
  observed_at AS time,
  signal_value AS value,
  spacecraft || ' › ' || signal_name AS metric
FROM telemetry_history
WHERE $__timeFilter(observed_at)
ORDER BY observed_at;
```

### Time-series — battery voltage by spacecraft
```sql
SELECT
  observed_at AS time,
  signal_value AS value,
  spacecraft AS metric
FROM telemetry_history
WHERE $__timeFilter(observed_at)
  AND signal_name = 'battery_voltage'
ORDER BY observed_at;
```

### Table — current state of all spacecraft
```sql
SELECT
  spacecraft,
  subsystem,
  signal_name,
  signal_value,
  status,
  observed_at
FROM telemetry_latest
ORDER BY spacecraft, subsystem;
```

### Table — active warnings and criticals
```sql
SELECT
  spacecraft,
  signal_name,
  signal_value,
  status,
  observed_at
FROM telemetry_latest
WHERE status IN ('WARNING', 'CRITICAL')
ORDER BY status DESC, spacecraft;
```

### Stat panel — single signal latest value
```sql
SELECT signal_value
FROM telemetry_latest
WHERE spacecraft = 'Sat-A'
  AND signal_name = 'battery_voltage';
```

### Bar gauge — battery voltage across all spacecraft
```sql
SELECT spacecraft AS metric, signal_value AS value
FROM telemetry_latest
WHERE signal_name = 'battery_voltage';
```

Set dashboard **refresh interval to 5s or 10s** for near-real-time updates.

---

## Stopping

```bash
docker compose down
```

To also delete all stored data:

```bash
docker compose down -v
```

---

## Architecture Notes

- **Deduplication**: Every row gets a SHA-256 hash of all its values. `ON CONFLICT (row_hash) DO NOTHING` prevents duplicate inserts regardless of how often the CSV is re-read.
- **Two-table pattern**: `telemetry_history` for trends, `telemetry_latest` for current state — both updated on every ingest cycle.
- **Append or overwrite CSVs**: Both modes work. The row hash handles deduplication either way.
- **Multiple CSV files**: Drop any number of `.csv` files into `./data/` — all are ingested each cycle.
