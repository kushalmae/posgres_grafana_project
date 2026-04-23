# Database Operations

## Full Reset

Wipes all data and volumes. Use when schema changes are breaking (column type changes, renamed columns, altered PKs or unique constraints).

```bash
docker-compose down -v
docker-compose up -d
python scripts/generate_fake_data.py --days 7
python scripts/ingest_csv_to_postgres.py --once
```

`generate_fake_data.py` automatically deletes `.ingest_state.json` so the ingest replays all CSVs from scratch.

---

## Non-Destructive Migration

Adds columns or indexes to a live database without downtime. Use for additive changes only.

```bash
docker exec -it local-postgres psql -U grafana_user -d local_csv_db
```

Then run your migration SQL:

```sql
ALTER TABLE telemetry_history ADD COLUMN IF NOT EXISTS apid INTEGER;
CREATE INDEX IF NOT EXISTS idx_telemetry_history_apid
    ON telemetry_history (apid, observed_at DESC);
```

All migration statements in `db/init_db.sql` use `IF NOT EXISTS` so they are safe to re-run.

---

## Purging Old Data

**Automatic** — the ingest script purges rows older than `TELEMETRY_RETENTION_DAYS` (default 30) approximately once per hour. Set the value in `.env`:

```
TELEMETRY_RETENTION_DAYS=14
```

**Manual** — connect to Postgres and run:

```sql
DELETE FROM telemetry_history WHERE observed_at < NOW() - INTERVAL '7 days';
VACUUM ANALYZE telemetry_history;
```

`VACUUM ANALYZE` reclaims disk space and updates query planner statistics after a large delete.

**Purge stale CSV files** — delete any CSV files in `data/` that are no longer part of the active pipeline:

```bash
rm data/telemetry.csv        # legacy single-file format
rm data/apid_100.csv         # old mixed-spacecraft format
```

---

## Connecting to Postgres

```bash
docker exec -it local-postgres psql -U grafana_user -d local_csv_db
```

Useful queries:

```sql
-- Row counts
SELECT COUNT(*) FROM telemetry_history;
SELECT COUNT(*) FROM telemetry_latest;

-- Data time range
SELECT MIN(observed_at), MAX(observed_at) FROM telemetry_history;

-- Rows per satellite and APID
SELECT spacecraft, apid, COUNT(*) AS rows
FROM telemetry_history
GROUP BY spacecraft, apid
ORDER BY spacecraft, apid;

-- Recent alerts
SELECT observed_at, spacecraft, apid, signal_name, signal_value, status
FROM telemetry_history
WHERE status != 'NOMINAL'
ORDER BY observed_at DESC
LIMIT 50;
```

---

## Migration Changelog

All migrations belong in `db/init_db.sql` using `IF NOT EXISTS` guards so they are idempotent and serve as a version history.

| Date       | Change                                      |
|------------|---------------------------------------------|
| 2026-04-22 | Added `apid INTEGER` to both tables         |
| 2026-04-22 | Added indexes on `observed_at`, `spacecraft/signal_name`, `apid`, alerts partial index |

---

## Rules of Thumb

- **Additive changes** (new column, new index) → non-destructive migration
- **Breaking changes** (type change, rename, PK/unique constraint) → full reset
- Always add migration SQL to `db/init_db.sql` with `IF NOT EXISTS`
- After a full reset, `generate_fake_data.py` regenerates historical data; `--days` and `--interval-minutes` are configurable
