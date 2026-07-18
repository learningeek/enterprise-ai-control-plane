# Deployment models

Three deployment models, same product and APIs, different boundary:

## 1. On-premise
Runs entirely inside the customer's firewall. Data never leaves the enterprise network. Best for
regulated/sensitive industries. All components (API, database, ML models, dashboard) run on
customer-owned infrastructure.

## 2. Customer cloud
Runs inside the customer's own AWS/Azure/GCP account/VPC (e.g. EKS + RDS + S3 on AWS). Customer owns the
infrastructure and billing; vendor provides the deployment artifacts (Helm charts, Terraform modules).

## 3. SaaS
Vendor-hosted, multi-tenant. Requires tenant isolation, encryption at rest/in transit, RBAC, and audit
logging as first-class requirements, not afterthoughts.

<!-- DECISION NEEDED: whether SaaS tenant isolation is pooled (shared schema, tenant_id column) or
     siloed (schema-per-tenant / database-per-tenant). See docs/02-architecture/database.md. -->
