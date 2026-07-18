# backend/connectors

Okta/Entra, SAP, ServiceNow, Snowflake, Salesforce, and Tier 1 AI-provider admin APIs — see
`docs/02-architecture/connector-framework.md`.

- `base.py` — shared contract: `AIUsageEvent`, `Connector`, `EventSink`, `UserDirectory`, `HTTPClient`,
  `ApproximateCatalogCostEstimator`, `ModelIdResolver`.
- `anthropic_admin.py`, `openai_usage.py` — Tier 1 connectors, pull from Anthropic's and OpenAI's admin
  usage APIs respectively. Follow this pattern for Azure OpenAI, Bedrock, and GitHub Copilot rather than
  inventing a new shape per vendor.

Tests: `tests/connectors/` (`.venv/bin/python -m pytest tests/connectors/`).

Okta/Entra/SAP/ServiceNow/Snowflake/Salesforce connectors are not yet implemented — no placeholder files
for those per `docs/99-meta/repository-evolution.md`; they'll follow the same `base.py` contract when
built.
