# Architecture Wiki

This wiki explains how the PostgreSQL-Grafana telemetry pipeline works, from first principles to operational details.

Read in order if you're new. Jump to a section if you know what you need.

---

## Table of Contents

| Doc | What it covers |
|-----|---------------|
| [01 · System Overview](01-system-overview.md) | What this system is, why it exists, the one-sentence mental model |
| [02 · Data Flow](02-data-flow.md) | End-to-end: CSV → Python → PostgreSQL → Grafana |
| [03 · Database Design](03-database-design.md) | Schema, two-table pattern, indexes, design decisions |
| [04 · Ingestion Engine](04-ingestion-engine.md) | How the Python ingestor reads, deduplicates, and inserts data |
| [05 · Grafana Integration](05-grafana-integration.md) | Data source, provisioning, dashboard queries |
| [06 · Configuration & Deployment](06-configuration-and-deployment.md) | Docker Compose, environment variables, startup sequence |
| [07 · Operations Runbook](07-operations-runbook.md) | How to run, reset, debug, and extend the system |
| [08 · ERD](08-erd.md) | Entity relationship diagram, index map, signal topology, data volume model |

---

## The One-Liner

> CSV files land on disk → Python polls them every 5 seconds → rows go into PostgreSQL → Grafana shows live dashboards.

That's it. Everything else is details about how each step is made robust.
