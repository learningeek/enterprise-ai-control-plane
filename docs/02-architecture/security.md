# Security

- Encryption at rest and in transit for all deployment models.
- RBAC required for SaaS; recommended for all deployments.
- Audit logs for all governance actions (policy changes, blocks, overrides).
- On-premise/customer-cloud: no data leaves the customer boundary; the platform must not phone home
  usage-level data.

<!-- DECISION NEEDED: which compliance certifications to target (SOC 2 Type II, ISO 27001, etc.) —
     not yet decided; affects audit log retention and access control requirements. -->
