# 07 · Operations Runbook

## Common Tasks

### Start the system from scratch
```bash
cp .env.example .env          # first time only
./start.sh                    # starts Docker + ingestor
```

### Generate historical data for dashboards
```bash
# Stop the ingestor first if running (Ctrl+C)
python scripts/generate_fake_data.py --days 7 --interval-minutes 1
python scripts/ingest_csv_to_postgres.py --once
# Restart ingestor for live mode
python scripts/ingest_csv_to_postgres.py
```

### Start live telemetry simulation
```bash
# In a separate terminal from the ingestor
python scripts/simulate_telemetry.py
```

### Export dashboard changes from Grafana UI to git
```bash
python scripts/export_grafana_dashboards.py --flat
git add grafana/dashboards/
git commit -m "Update dashboard: <describe change>"
```

---

## Stopping the System

**Stop the ingestor only** — press `Ctrl+C` in the terminal running `ingest_csv_to_postgres.py`. Containers keep running.

**Stop containers (keep data):**
```bash
docker compose down
```

**Stop containers and delete all stored data (volumes):**
```bash
docker compose down -v
```

`-v` destroys the named Docker volumes (`postgres_data`, `grafana_data`, `pgadmin_data`). All database rows, Grafana state, and pgAdmin config are gone. Use only for a full reset.

---

## Resetting the Database

**Soft reset (keep containers, wipe data):**
```bash
docker exec -it local-postgres psql -U grafana_user -d local_csv_db \
  -c "TRUNCATE telemetry_history, telemetry_latest;"
rm -f data/.ingest_state.json
```

**Hard reset (destroy everything, rebuild from scratch):**
```bash
docker compose down -v
rm -f data/.ingest_state.json
docker compose up -d
# Wait for Postgres to be ready, then:
python scripts/generate_fake_data.py --days 7
python scripts/ingest_csv_to_postgres.py --once
python scripts/ingest_csv_to_postgres.py
```

---

## Debugging

### "Grafana says no data"

**Check 1: Is Postgres running?**
```bash
docker ps | grep postgres
```

**Check 2: Does the database have rows?**
```bash
docker exec -it local-postgres psql -U grafana_user -d local_csv_db \
  -c "SELECT COUNT(*) FROM telemetry_history;"
```

**Check 3: Is the ingestor running and inserting?**
The ingestor prints a summary line every cycle. Look for:
```
[2026-04-22 10:00:05] Ingested 30 new rows from 10 files.
```
If it says `0 new rows`, either no new data has arrived or the state file thinks it's already processed everything. Delete `.ingest_state.json` and restart.

**Check 4: Is the Grafana data source working?**
Go to Grafana → Connections → Data Sources → Telemetry PostgreSQL → "Test". It should say "Database Connection OK".

**Check 5: Is the time range correct?**
If you generated data for `--days 7`, but Grafana's time picker is set to "Last 1 hour", you'll see nothing. Set the time range to "Last 7 days".

---

### "Ingestor crashed with DB connection error"

Usually means Postgres isn't ready yet. Check:
```bash
docker logs local-postgres | tail -20
```

If Postgres is still initializing, wait for:
```
database system is ready to accept connections
```

Then restart the ingestor.

---

### "Rows aren't being inserted (no error either)"

This usually means the rows already exist (hash collision = duplicate). To verify:
```bash
docker exec -it local-postgres psql -U grafana_user -d local_csv_db -c "
  SELECT COUNT(*) as total, MAX(inserted_at) as last_insert
  FROM telemetry_history;"
```

If `last_insert` is recent, new rows are being inserted. If it matches when you last ran the ingestor, no new data is coming in (check if the simulator is running or CSVs are being updated).

---

### "CSV file isn't being picked up"

Files must be in `./data/` and match the glob `*.csv`. Check:
```bash
ls -la data/*.csv
```

The ingestor scans for new files each cycle, so newly added files are picked up on the next poll (within 5 seconds).

---

## Adding a New Signal

1. Add signal definition to `simulate_telemetry.py` in the `SIGNALS` dict
2. Add threshold values to the thresholds dict in the same file
3. No schema changes needed—`signal_name` is TEXT, new names just work
4. If you want per-signal indexing: add a partial index in `init_db.sql`

---

## Adding a New Spacecraft

1. Add spacecraft entry to `simulate_telemetry.py`'s spacecraft list
2. The ingestor picks up new CSVs automatically
3. No schema changes needed
4. Update Grafana dashboards: add the new spacecraft to `$spacecraft` variable options in the detail dashboard

---

## Adding a New Dashboard Panel

1. Edit the dashboard in Grafana UI (`http://localhost:3000`)
2. Add the panel, write the SQL query
3. Save in Grafana UI
4. Export: `python scripts/export_grafana_dashboards.py --flat`
5. Commit: `git add grafana/dashboards/ && git commit -m "..."`

The exported JSON is the source of truth. Editing JSON by hand is possible but error-prone—prefer the UI.

---

## Checking Disk Usage

```bash
# CSV files
du -sh data/

# Postgres volume
docker system df -v | grep postgres

# Row count and approximate table size
docker exec -it local-postgres psql -U grafana_user -d local_csv_db -c "
  SELECT
    pg_size_pretty(pg_total_relation_size('telemetry_history')) AS history_size,
    pg_size_pretty(pg_total_relation_size('telemetry_latest')) AS latest_size,
    COUNT(*) AS row_count
  FROM telemetry_history;"
```

---

## Manual Data Purge

**Delete rows older than N days:**
```sql
DELETE FROM telemetry_history WHERE observed_at < NOW() - INTERVAL '7 days';
VACUUM ANALYZE telemetry_history;
```

`VACUUM ANALYZE` reclaims disk space and updates query planner statistics after a large delete. Run it after any `DELETE` that removes more than 10% of the table.

**Purge stale CSV files** — remove CSV files that are no longer part of the active pipeline:
```bash
rm data/old_satellite.csv
```

The ingestor will no longer pick them up on the next poll cycle. Their state entry in `.ingest_state.json` becomes stale but harmless.

---

## Manual Vacuum

After bulk deletes (especially after `TRUNCATE` or large purges), reclaim space:
```bash
docker exec -it local-postgres psql -U grafana_user -d local_csv_db \
  -c "VACUUM ANALYZE telemetry_history;"
```

This updates planner statistics and reclaims dead tuple space. Run after any `DELETE` that removes more than 10% of the table.

---

## Useful SQL Snippets

**Row counts:**
```sql
SELECT COUNT(*) FROM telemetry_history;
SELECT COUNT(*) FROM telemetry_latest;
```

**Data time range:**
```sql
SELECT MIN(observed_at), MAX(observed_at) FROM telemetry_history;
```

**Rows per spacecraft and APID:**
```sql
SELECT spacecraft, apid, COUNT(*) AS rows
FROM telemetry_history
GROUP BY spacecraft, apid
ORDER BY spacecraft, apid;
```

**Latest reading per spacecraft:**
```sql
SELECT spacecraft, signal_name, signal_value, status, observed_at
FROM telemetry_latest
ORDER BY spacecraft, signal_name;
```

**Active alerts (last 1 hour):**
```sql
SELECT spacecraft, signal_name, signal_value, status, observed_at
FROM telemetry_history
WHERE status != 'NOMINAL'
  AND observed_at > NOW() - INTERVAL '1 hour'
ORDER BY observed_at DESC;
```

**Ingestion rate (rows per minute, last 30 min):**
```sql
SELECT
  date_trunc('minute', inserted_at) AS minute,
  COUNT(*) AS rows_inserted
FROM telemetry_history
WHERE inserted_at > NOW() - INTERVAL '30 minutes'
GROUP BY 1
ORDER BY 1;
```

**Check for gaps in data (signals missing for >1 minute):**
```sql
SELECT spacecraft, signal_name, MAX(observed_at) AS last_seen,
       NOW() - MAX(observed_at) AS age
FROM telemetry_history
WHERE observed_at > NOW() - INTERVAL '10 minutes'
GROUP BY spacecraft, signal_name
HAVING NOW() - MAX(observed_at) > INTERVAL '1 minute'
ORDER BY age DESC;
```

**Ingest lag (time between measurement and insertion):**
```sql
SELECT
  AVG(EXTRACT(EPOCH FROM (inserted_at - observed_at))) AS avg_lag_seconds,
  MAX(EXTRACT(EPOCH FROM (inserted_at - observed_at))) AS max_lag_seconds
FROM telemetry_history
WHERE inserted_at > NOW() - INTERVAL '1 hour';
```

---

← Back to [Wiki Index](README.md)
