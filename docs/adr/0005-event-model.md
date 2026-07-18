# ADR 0005: Single canonical AIUsageEvent

**Status:** accepted

**Decision:** All downstream modules (metering, billing, governance, ML, dashboards, forecasting) consume
one canonical, versioned `AIUsageEvent` rather than each maintaining its own data model of "AI usage."

**Rationale:** Prevents data model drift across modules and makes the platform easier to evolve; a single
schema versioned from day one avoids breaking customer integrations as the platform grows.
