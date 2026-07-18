# ADR 0001: Modular monolith over microservices for v1

**Status:** accepted

**Decision:** Build `backend/` as a modular monolith (gateway/metering/governance/intelligence/connectors
as folders with clean internal boundaries), not as separate deployed services.

**Rationale:** Enterprise buyers evaluate a single deployable artifact first; premature service
decomposition adds operational complexity (service mesh, distributed tracing, network boundaries)
without a concrete scaling justification yet. Folder-level boundaries keep the option to split later.
