CREATE TABLE IF NOT EXISTS telemetry_history (
    id BIGSERIAL PRIMARY KEY,
    observed_at TIMESTAMPTZ NOT NULL,
    spacecraft TEXT NOT NULL,
    subsystem TEXT,
    apid INTEGER,
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
    apid INTEGER,
    signal_name TEXT NOT NULL,
    signal_value DOUBLE PRECISION,
    signal_unit TEXT,
    status TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (spacecraft, subsystem, signal_name)
);

-- Migration: add apid to existing deployments (safe to run repeatedly)
ALTER TABLE telemetry_history ADD COLUMN IF NOT EXISTS apid INTEGER;
ALTER TABLE telemetry_latest  ADD COLUMN IF NOT EXISTS apid INTEGER;

CREATE INDEX IF NOT EXISTS idx_telemetry_history_observed_at
    ON telemetry_history (observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_telemetry_history_spacecraft_signal
    ON telemetry_history (spacecraft, signal_name, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_telemetry_history_apid
    ON telemetry_history (apid, observed_at DESC);

-- Partial index — only non-nominal rows, keeps alert queries fast
CREATE INDEX IF NOT EXISTS idx_telemetry_history_alerts
    ON telemetry_history (status, observed_at DESC)
    WHERE status != 'NOMINAL';
