#!/usr/bin/env bash
# Start Postgres + Grafana, then run the CSV ingestor from the repo root.
# Usage: chmod +x start.sh && ./start.sh

set -euo pipefail
cd "$(dirname "$0")"

echo "Starting Docker Compose (Postgres + Grafana)..."
docker compose up -d

echo "Waiting for Postgres to accept connections..."
for i in $(seq 1 45); do
  if docker compose exec -T postgres pg_isready -U grafana_user -d local_csv_db >/dev/null 2>&1; then
    break
  fi
  sleep 1
  if [ "$i" -eq 45 ]; then
    echo "Postgres did not become ready in time. Check: docker compose logs postgres" >&2
    exit 1
  fi
done

echo "Installing Python dependencies..."
python -m pip install -q -r requirements.txt

echo ""
echo "Grafana: http://localhost:3000  (admin / admin)"
echo "Ingestor running — watching data/*.csv (Ctrl+C to stop)"
echo ""

python scripts/ingest_csv_to_postgres.py
