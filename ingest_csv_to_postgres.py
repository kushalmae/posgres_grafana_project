import os
import time
import hashlib
import pandas as pd
from sqlalchemy import create_engine, text

CSV_FOLDER = "./data"
POLL_SECONDS = 5

DB_USER = "grafana_user"
DB_PASSWORD = "grafana_password"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "local_csv_db"

engine = create_engine(
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

REQUIRED_COLUMNS = ["timestamp", "satellite", "subsystem", "metric_name", "metric_value", "status"]


def create_tables():
    sql = """
    CREATE TABLE IF NOT EXISTS telemetry_history (
        id BIGSERIAL PRIMARY KEY,
        observed_at TIMESTAMPTZ NOT NULL,
        spacecraft TEXT NOT NULL,
        subsystem TEXT,
        signal_name TEXT NOT NULL,
        signal_value DOUBLE PRECISION,
        signal_unit TEXT,
        status TEXT,
        source_file TEXT,
        row_hash TEXT UNIQUE,
        inserted_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS telemetry_latest (
        spacecraft TEXT NOT NULL,
        subsystem TEXT,
        signal_name TEXT NOT NULL,
        signal_value DOUBLE PRECISION,
        signal_unit TEXT,
        status TEXT,
        observed_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (spacecraft, subsystem, signal_name)
    );
    """
    with engine.begin() as conn:
        conn.execute(text(sql))


def build_row_hash(row):
    raw = "|".join(str(v) for v in row.values)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ingest_file(file_path):
    try:
        df = pd.read_csv(file_path)
        if df.empty:
            return 0

        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            print(f"Skipping {file_path} — missing columns: {missing}")
            return 0

        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["metric_value"] = pd.to_numeric(df["metric_value"], errors="coerce")
        df = df.dropna(subset=["timestamp", "metric_value"])

        if df.empty:
            return 0

        df["source_file"] = os.path.basename(file_path)
        df["signal_unit"] = df.get("signal_unit", "")
        df["row_hash"] = df.apply(build_row_hash, axis=1)

        history_records = df.rename(columns={
            "timestamp": "observed_at",
            "satellite": "spacecraft",
            "metric_name": "signal_name",
            "metric_value": "signal_value",
        })[["observed_at", "spacecraft", "subsystem", "signal_name", "signal_value",
            "signal_unit", "status", "source_file", "row_hash"]].to_dict(orient="records")

        insert_history = text("""
            INSERT INTO telemetry_history
                (observed_at, spacecraft, subsystem, signal_name, signal_value,
                 signal_unit, status, source_file, row_hash)
            VALUES
                (:observed_at, :spacecraft, :subsystem, :signal_name, :signal_value,
                 :signal_unit, :status, :source_file, :row_hash)
            ON CONFLICT (row_hash) DO NOTHING;
        """)

        insert_latest = text("""
            INSERT INTO telemetry_latest
                (spacecraft, subsystem, signal_name, signal_value,
                 signal_unit, status, observed_at, updated_at)
            VALUES
                (:spacecraft, :subsystem, :signal_name, :signal_value,
                 :signal_unit, :status, :observed_at, NOW())
            ON CONFLICT (spacecraft, subsystem, signal_name) DO UPDATE SET
                signal_value = EXCLUDED.signal_value,
                signal_unit  = EXCLUDED.signal_unit,
                status       = EXCLUDED.status,
                observed_at  = EXCLUDED.observed_at,
                updated_at   = NOW();
        """)

        with engine.begin() as conn:
            result = conn.execute(insert_history, history_records)
            conn.execute(insert_latest, history_records)

        new_rows = result.rowcount
        if new_rows:
            print(f"[{file_path}] +{new_rows} new rows")
        return new_rows

    except Exception as e:
        print(f"Error ingesting {file_path}: {e}")
        return 0


def ingest_all():
    total = 0
    for filename in os.listdir(CSV_FOLDER):
        if filename.endswith(".csv"):
            total += ingest_file(os.path.join(CSV_FOLDER, filename))
    return total


if __name__ == "__main__":
    create_tables()
    print(f"Watching {CSV_FOLDER}/ every {POLL_SECONDS}s...")
    while True:
        ingest_all()
        time.sleep(POLL_SECONDS)
