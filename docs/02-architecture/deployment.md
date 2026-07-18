# Deployment architecture

## On-premise
All components run inside the customer firewall: API, database, ML models, dashboard.

## Customer cloud (example: AWS)
Customer AWS account -> VPC -> EKS (Kubernetes) -> AI Control Plane -> RDS (database) -> S3 (storage).

## SaaS
Vendor cloud, multi-tenant: Tenant A / Tenant B / Tenant C sharing infrastructure with isolation,
encryption, RBAC, and audit logs as hard requirements.

Packaging: Docker Compose for local/dev, Helm charts for Kubernetes, Terraform modules for customer-cloud
provisioning. See `deployment/docker`, `deployment/kubernetes`, `deployment/terraform`.
