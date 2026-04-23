import os
import json
import time
import hashlib
import logging
from io import StringIO
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_FOLDER = REPO_ROOT / "data"
STATE_FILE = CSV_FOLDER / ".ingest_state.json"
POLL_SECONDS = 5
RETENTION_DAYS = int(os.getenv("TELEMETRY_RETENTION_DAYS", "30"))
CLEANUP_EVERY_N = 720  # ~1 hour at 5s interval

engine = create_engine(
    f"postgresql+psycopg2://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME')}"
)

REQUIRED_COLUMNS = ["timestamp", "satellite", "subsystem", "metric_name", "metric_value", "status"]


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def build_row_hash(row):
    raw = "|".join(str(row[k]) for k in sorted(row.index))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_new_rows(file_path, byte_offset):
    """Return (DataFrame, new_byte_offset) for rows appended since byte_offset."""
    with open(file_path, "r", newline="", encoding="utf-8") as f:
        header_line = f.readline()
        header_end = f.tell()
        # Reset offset if the file was truncated or recreated
        if byte_offset > os.path.getsize(file_path):
            logger.warning("%s appears truncated — resetting offset", file_path.name)
            byte_offset = 0
        f.seek(max(header_end, byte_offset))
        new_content = f.read()
        end_offset = f.tell()

    if not new_content.strip():
        return pd.DataFrame(), end_offset

    return pd.read_csv(StringIO(header_line + new_content)), end_offset


def ingest_file(file_path, state):
    filename = file_path.name
    byte_offset = state.get(filename, 0)

    try:
        df, new_offset = read_new_rows(file_path, byte_offset)
        if df.empty:
            return 0

        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            logger.warning("Skipping %s — missing columns: %s", filename, missing)
            return 0

        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["metric_value"] = pd.to_numeric(df["metric_value"], errors="coerce")
        df = df.dropna(subset=["timestamp", "metric_value"])
        if df.empty:
            return 0

        df["source_file"] = filename
        df["signal_unit"] = df.get("signal_unit", "")
        df["row_hash"] = df.apply(build_row_hash, axis=1)
        # apid is optional — present in per-APID CSVs, absent in legacy files
        if "apid" not in df.columns:
            df["apid"] = None
        else:
            df["apid"] = pd.to_numeric(df["apid"], errors="coerce").astype(object).where(df["apid"].notna(), None)

        history_records = df.rename(columns={
            "timestamp": "observed_at",
            "satellite": "spacecraft",
            "metric_name": "signal_name",
            "metric_value": "signal_value",
        })[["observed_at", "spacecraft", "subsystem", "apid", "signal_name", "signal_value",
            "signal_unit", "status", "source_file", "row_hash"]].to_dict(orient="records")

        insert_history = text("""
            INSERT INTO telemetry_history
                (observed_at, spacecraft, subsystem, apid, signal_name, signal_value,
                 signal_unit, status, source_file, row_hash)
            VALUES
                (:observed_at, :spacecraft, :subsystem, :apid, :signal_name, :signal_value,
                 :signal_unit, :status, :source_file, :row_hash)
            ON CONFLICT (row_hash) DO NOTHING;
        """)

        insert_latest = text("""
            INSERT INTO telemetry_latest
                (spacecraft, subsystem, apid, signal_name, signal_value,
                 signal_unit, status, observed_at, updated_at)
            VALUES
                (:spacecraft, :subsystem, :apid, :signal_name, :signal_value,
                 :signal_unit, :status, :observed_at, NOW())
            ON CONFLICT (spacecraft, subsystem, signal_name) DO UPDATE SET
                signal_value = EXCLUDED.signal_value,
                signal_unit  = EXCLUDED.signal_unit,
                apid         = EXCLUDED.apid,
                status       = EXCLUDED.status,
                observed_at  = EXCLUDED.observed_at,
                updated_at   = NOW();
        """)

        with engine.begin() as conn:
            result = conn.execute(insert_history, history_records)
            conn.execute(insert_latest, history_records)

        new_rows = result.rowcount
        if new_rows:
            logger.info("[%s] +%d new rows", filename, new_rows)

        state[filename] = new_offset
        return new_rows

    except Exception as e:
        logger.error("Error ingesting %s: %s", filename, e)
        return 0


def ingest_all(state):
    total = 0
    for path in CSV_FOLDER.glob("*.csv"):
        total += ingest_file(path, state)
    save_state(state)
    return total


def purge_old_rows():
    with engine.begin() as conn:
        result = conn.execute(text(
            f"DELETE FROM telemetry_history WHERE observed_at < NOW() - INTERVAL '{RETENTION_DAYS} days'"
        ))
    if result.rowcount:
        logger.info("Purged %d rows older than %d days", result.rowcount, RETENTION_DAYS)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Ingest once and exit (batch mode)")
    args = parser.parse_args()

    state = load_state()

    if args.once:
        logger.info("Batch ingest — %s/", CSV_FOLDER)
        total = ingest_all(state)
        logger.info("Done. %d new rows ingested.", total)
    else:
        logger.info(
            "Watching %s/ every %ds | retention=%d days | schema: db/init_db.sql",
            CSV_FOLDER, POLL_SECONDS, RETENTION_DAYS,
        )
        tick = 0
        while True:
            ingest_all(state)
            tick += 1
            if tick % CLEANUP_EVERY_N == 0:
                purge_old_rows()
            time.sleep(POLL_SECONDS)
