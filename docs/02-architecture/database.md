# Database

- **PostgreSQL** — primary transactional store: users, tenants, applications, AI events, policies.
- **DuckDB** — analytics engine for large usage analysis and forecasting queries over historical events.

<!-- DECISION NEEDED: SaaS tenant isolation model — pooled (shared tables + tenant_id column) vs siloed
     (schema-per-tenant or database-per-tenant). Pooled is simpler to operate; siloed is easier to sell
     into regulated customers. Default assumption for v1: pooled with a mandatory tenant_id on every
     table and row-level security, revisit if an enterprise customer requires stronger isolation. -->
