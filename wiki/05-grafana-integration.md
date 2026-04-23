# 05 · Grafana Integration

## How Grafana Connects to PostgreSQL

Grafana does not query the database directly from configuration files. It goes through a **data source** that is provisioned at startup.

The provisioning file `grafana/provisioning/datasources/datasources.yml` is mounted into the Grafana container at `/etc/grafana/provisioning/datasources/`. Grafana reads it on startup and creates the data source automatically.

```yaml
# datasources.yml (abbreviated)
datasources:
  - name: Telemetry PostgreSQL
    uid: telemetry_pg
    type: postgres
    url: postgres:5432          # Docker service name, not localhost
    database: local_csv_db
    user: grafana_user
    secureJsonData:
      password: grafana_password
    jsonData:
      sslmode: disable
      postgresVersion: 1600
    isDefault: true
```

Key detail: the host is `postgres:5432`, not `localhost:5432`. Inside the Docker network, `postgres` resolves to the PostgreSQL container. `localhost` would refer to the Grafana container itself, which has no database.

---

## Dashboard Provisioning

Dashboards are loaded from JSON files on disk. The provisioning config tells Grafana where to look:

```yaml
# dashboards.yml (abbreviated)
providers:
  - type: file
    options:
      path: /etc/grafana/dashboards   # mounted from ./grafana/dashboards/
    updateIntervalSeconds: 30          # re-scans for changes every 30s
    allowUiUpdates: true               # you can edit in the UI
```

When you change a dashboard JSON file, Grafana picks it up within 30 seconds. When you edit a dashboard in the Grafana UI, it updates in memory but **does not write back to the JSON file**. To persist UI edits:

```bash
python scripts/export_grafana_dashboards.py --flat
```

This calls the Grafana REST API, downloads the dashboard JSON, and overwrites the files in `grafana/dashboards/`. Commit those files to git to persist the changes.

---

## The Three Dashboards

### mission_control.json — Fleet Overview

The top-level view. Shows fleet-wide health at a glance.

Key panels:
- **Battery Voltage** (time-series): both spacecraft overlaid
- **Link Quality** (gauge): current value from `telemetry_latest`
- **CPU Temperature** (stat panel): colored by NOMINAL/WARNING/CRITICAL
- **Downlink Rate** (time-series): Sat-A vs Sat-B

Intended use: leave this on a screen. It shows if anything is wrong without needing to drill in.

### spacecraft_fleet_telemetry.json — All Signals by Spacecraft

Twelve panels arranged in a grid, one per signal. Each panel shows both spacecraft as separate time-series lines.

Useful for: comparing Sat-A and Sat-B behavior over the same time window. Detecting if one satellite's signals are drifting while the other is stable.

### spacecraft_detail.json — Single Spacecraft Deep Dive

Single spacecraft focus. Uses a Grafana variable (`$spacecraft`) to switch between Sat-A and Sat-B.

Key panels:
- All signals for the selected spacecraft
- Status table from `telemetry_latest`
- Alert history from `telemetry_history WHERE status != 'NOMINAL'`
- APID breakdown table

Useful for: investigating a specific spacecraft after seeing something concerning in the fleet view.

---

## How Grafana Queries Work

Grafana's PostgreSQL plugin uses `$__timeFilter(column)` as a macro that expands to:

```sql
column BETWEEN '2026-04-22T10:00:00Z' AND '2026-04-22T11:00:00Z'
```

Where the time range comes from the dashboard's time picker. This lets you zoom in/out on the time axis without changing the panel query.

Example panel query (battery voltage time-series):
```sql
SELECT
  observed_at AS time,
  signal_value,
  spacecraft AS metric
FROM telemetry_history
WHERE $__timeFilter(observed_at)
  AND signal_name = 'battery_voltage'
ORDER BY observed_at;
```

Grafana expects the result in a specific shape: a `time` column (TIMESTAMPTZ), a numeric value column, and optionally a `metric` column for the series label in multi-line charts.

---

## Refresh Rate

Dashboards are configured to auto-refresh every 5–10 seconds. With the ingestor polling every 5s and Grafana refreshing every 5–10s, end-to-end latency is typically 5–15 seconds from measurement to dashboard.

---

## Exporting Dashboards

After editing dashboards in the Grafana UI:

```bash
# Export all dashboards (flat format, matches provisioning)
python scripts/export_grafana_dashboards.py --flat

# Export and keep watching (re-export every 60s)
python scripts/export_grafana_dashboards.py --flat --watch --interval 60
```

The `--flat` flag strips the Grafana API envelope and writes just the inner dashboard JSON, which is the format the provisioner expects.

After export, commit the updated JSON files:
```bash
git add grafana/dashboards/
git commit -m "Update dashboard: mission_control - added reaction wheel panel"
```

---

## Grafana Login

| Setting | Value |
|---------|-------|
| URL | http://localhost:3000 |
| Username | admin |
| Password | admin |

Change the password via Grafana UI → Profile → Change Password if running in any shared environment. This is a local-dev default.

---

## Query Reference

Copy-paste ready queries for common panel types. All reference the `Telemetry PostgreSQL` data source (UID `telemetry_pg`).

**Time-series — all signals**
```sql
SELECT
  observed_at AS time,
  signal_value AS value,
  spacecraft || ' › ' || signal_name AS metric
FROM telemetry_history
WHERE $__timeFilter(observed_at)
ORDER BY observed_at;
```

**Time-series — battery voltage by spacecraft**
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

**Table — current state of all spacecraft**
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

**Table — active warnings and criticals**
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

**Stat panel — single signal latest value**
```sql
SELECT signal_value
FROM telemetry_latest
WHERE spacecraft = 'Sat-A'
  AND signal_name = 'battery_voltage';
```

**Bar gauge — battery voltage across all spacecraft**
```sql
SELECT spacecraft AS metric, signal_value AS value
FROM telemetry_latest
WHERE signal_name = 'battery_voltage';
```

Set dashboard **refresh interval to 5s or 10s** for near-real-time updates.

---

Next: [06 · Configuration & Deployment →](06-configuration-and-deployment.md)
