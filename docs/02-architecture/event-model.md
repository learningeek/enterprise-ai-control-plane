# Event model

`AIUsageEvent` is the canonical, immutable, versioned fact record for the whole system. See
`specs/event-schema.md` for the authoritative field list. Every module (metering, billing, governance,
ML, dashboards, forecasting) is a consumer of this same event stream — never invent a parallel model
for "the same fact" in a different module.

Event versioning: the schema carries a version number from day one so the platform can evolve without
breaking existing customer integrations that ingest events.
