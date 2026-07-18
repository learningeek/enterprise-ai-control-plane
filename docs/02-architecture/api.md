# API

REST API (FastAPI) is the primary interface. See `specs/api-contract.md` for the authoritative contract.
Key resource groups: usage events (ingest + query), metering/cost reports, policies, MCP inventory,
tenants/users (read from identity provider sync), forecasts/recommendations.

All ingest endpoints validate against `specs/event-schema.md` before persisting.
