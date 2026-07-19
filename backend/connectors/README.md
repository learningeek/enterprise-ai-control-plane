# backend/connectors

Okta/Entra, SAP, ServiceNow, Snowflake, Salesforce, and Tier 1 AI-provider admin APIs — see
`docs/02-architecture/connector-framework.md`.

- `base.py` — shared contract: `AIUsageEvent`, `Connector`, `EventSink`, `UserDirectory`
  (`CSVUserDirectory`, `InMemoryUserDirectory`, `PermissiveUserDirectory`), `HTTPClient` (`get` and
  `post`), `ApproximateCatalogCostEstimator`, `ModelIdResolver`.
- `anthropic_admin.py`, `openai_usage.py` — Tier 1 connectors pulling from Anthropic's and OpenAI's
  aggregate admin usage-report APIs (paginated `GET`, time-bucketed).
- `azure_openai.py` — Tier 1 connector querying an Azure Log Analytics workspace via KQL (`POST`, no
  pagination, per-request rows rather than aggregate buckets). A genuinely different vendor-integration
  shape from the other two, not a copy — read its module docstring before assuming symmetry.
- Follow whichever of these is the closer fit for Bedrock/GitHub Copilot/Gemini rather than inventing a
  new shape from scratch — but don't force a genuinely-different vendor into either shape either.
- `cli.py` — the entrypoint: `python -m backend.connectors.cli sync --config connectors.toml` runs every
  enabled connector into a DuckDB store (`backend/metering/duckdb_store.py`); `... report --config
  connectors.toml` regenerates the dashboard (`backend/metering/report.py`). See
  `connectors.example.toml` at the repo root for the config format.

Tests: `tests/connectors/` (`.venv/bin/python -m pytest tests/connectors/`).

Okta/Entra/SAP/ServiceNow/Snowflake/Salesforce connectors are not yet implemented — no placeholder files
for those per `docs/99-meta/repository-evolution.md`; they'll follow the same `base.py` contract when
built.
