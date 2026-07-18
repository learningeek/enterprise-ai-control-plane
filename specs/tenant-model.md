# Spec: tenant model (v1 draft)

**Status:** draft — depends on the pooled-vs-siloed decision flagged in
`docs/02-architecture/database.md`.

Default assumption for v1: pooled multi-tenancy — every table carries a mandatory `tenant_id`, enforced
via row-level security at the database layer, not just application-layer filtering. On-premise/customer-
cloud deployments run with exactly one tenant.
