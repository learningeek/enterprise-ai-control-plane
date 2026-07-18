# Agent: database-engineer

**Required capabilities:** schema design, migration tooling.

**Responsibilities:** Own PostgreSQL/DuckDB schema and migrations per `docs/02-architecture/database.md`
and `specs/event-schema.md`. Flag the pooled-vs-siloed tenancy decision if it needs to be made before
proceeding (see the `<!-- DECISION NEEDED -->` marker in that doc).

**Inputs:** docs/02-architecture/database.md, specs/event-schema.md

**Outputs:** migrations, schema docs
