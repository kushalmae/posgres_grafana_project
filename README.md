# Local Telemetry Pipeline: CSV → PostgreSQL → Grafana

A local near-real-time telemetry dashboard pipeline. Python polls CSV files every 5 seconds, inserts new rows into PostgreSQL (deduped by row hash), and Grafana queries Postgres to render live panels.

```
/data/*.csv  →  Python ingestor (poll 5s)  →  Local Postgres  →  Grafana (refresh 5–10s)
```

---

## Project Structure

```
.
├── start.ps1 / start.sh        # One-shot: Docker up + deps + ingestor
├── docker-compose.yml          # Postgres + Grafana + pgAdmin
├── requirements.txt
├── .env.example                # Copy to .env and fill in credentials
├── db/
│   └── init_db.sql             # Schema — auto-applied on first Postgres start
├── scripts/
│   ├── ingest_csv_to_postgres.py     # Main ingest worker
│   ├── simulate_telemetry.py         # Optional live data generator
│   ├── generate_fake_data.py         # Historical backfill
│   └── export_grafana_dashboards.py  # Save dashboard edits to git
├── data/
│   └── *.csv                   # Drop CSV files here to ingest
├── grafana/
│   ├── dashboards/             # Dashboard JSON (version-controlled)
│   └── provisioning/           # Auto-configured datasource + dashboard loader
└── wiki/                       # All documentation (start here)
    └── README.md
```

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Python 3.9+

---

## Quick Start

### Option A — start everything (recommended)

Copy `.env.example` to `.env` first (first time only), then with Docker running:

**Windows (PowerShell)**
```powershell
.\start.ps1
```

**macOS / Linux**
```bash
chmod +x start.sh
./start.sh
```

This brings up Postgres and Grafana, waits until Postgres is ready, installs Python dependencies, then runs the CSV ingestor. Press **Ctrl+C** to stop the ingestor; containers keep running.

### Option B — manual steps

#### 1. Start containers
```bash
docker compose up -d
```

This starts PostgreSQL 16 on `localhost:5432`, Grafana on `http://localhost:3000`, and pgAdmin on `http://localhost:5050`. The schema is created automatically from `db/init_db.sql` on first run. Grafana is provisioned with the PostgreSQL data source and fleet dashboards.

#### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

#### 3. Run the ingestor
```bash
python scripts/ingest_csv_to_postgres.py
```

#### Optional: live sample data
In a second terminal:
```bash
python scripts/simulate_telemetry.py
```

---

## Stopping

```bash
docker compose down          # stop containers, keep data
docker compose down -v       # stop containers and delete all stored data
```

See the [Operations Runbook](wiki/07-operations-runbook.md) for reset and debug procedures.

---

## Documentation

| Guide | Description |
|-------|-------------|
| [System Overview](wiki/01-system-overview.md) | What this is and why it exists |
| [Data Flow](wiki/02-data-flow.md) | End-to-end pipeline walkthrough |
| [Database Design](wiki/03-database-design.md) | Schema, indexes, dedup, migrations |
| [Ingestion Engine](wiki/04-ingestion-engine.md) | CSV format, how the ingestor works |
| [Grafana Integration](wiki/05-grafana-integration.md) | Dashboards, queries, export |
| [Configuration & Deployment](wiki/06-configuration-and-deployment.md) | Env vars, Docker Compose |
| [Operations Runbook](wiki/07-operations-runbook.md) | Run, reset, debug, extend |
| [ERD](wiki/08-erd.md) | Entity relationship diagram |
