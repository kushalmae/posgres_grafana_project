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
