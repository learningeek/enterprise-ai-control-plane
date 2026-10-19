# backend/metering

Token counting, cost calculation, chargeback — see docs/01-domain/metering.md.

- `duckdb_store.py` — `DuckDBEventSink` (an `EventSink` for `backend/connectors/`), idempotent on
  `event_id`, plus `usage_summary()` for per-(user/key, department, provider, model) aggregation. Local
  analytics store per ADR 0003 — not the eventual Postgres-backed system of record (`backend/gateway`).
- `report.py` — renders `usage_summary()` as a static HTML dashboard, leading with
  `aggregate_attribution()`'s headline metric (% of spend attributed to a known owner, not just the
  total — see docs/00-product/vision.md). Run via
  `python -m backend.connectors.cli report --config connectors.toml`, or directly:
  `python -m backend.metering.report <duckdb_path> <output_html_path>`.

Tests: `tests/metering/` (`.venv/bin/python -m pytest tests/metering/`).

Chargeback and full cost reconciliation are not built yet — no placeholder files for those per
`docs/99-meta/repository-evolution.md`.
