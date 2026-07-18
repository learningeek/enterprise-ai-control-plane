# Data model overview

The canonical entity is `AIUsageEvent` (full schema in `specs/event-schema.md`). Supporting reference
data: users, tenants, applications, providers, models, departments, policies, billing accounts, SSO
groups, MCP inventory, MCP tool calls, incidents, monthly cost history, shadow AI records.

See `docs/01-domain/` for what each entity means in business terms, and `docs/04-simulation/` for how
realistic instances of this data are generated for development and demos.
