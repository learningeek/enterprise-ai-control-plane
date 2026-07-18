# Spec: API contract (v1 draft)

**Status:** draft — refine endpoint list and request/response shapes as backend is implemented, but keep
this file as the source of truth updated in lockstep with implementation.

## Resource groups

- `POST /v1/events` — ingest an `AIUsageEvent` (validates against `specs/event-schema.md`)
- `GET /v1/events` — query events (filterable by tenant, department, application, model, time range)
- `GET /v1/metering/summary` — aggregated cost/usage (see `docs/01-domain/metering.md`)
- `GET /v1/policies` / `POST /v1/policies` — governance policy CRUD
- `GET /v1/incidents` — governance incidents
- `GET /v1/mcp/servers` / `GET /v1/mcp/tool-calls` — MCP inventory and usage
- `GET /v1/forecast` — cost forecast and optimization recommendations

All endpoints require `tenant_id` scoping (see `docs/02-architecture/database.md` for isolation model).
