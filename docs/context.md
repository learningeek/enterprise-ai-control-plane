# Project context

Read this before doing anything else in this repository, every session.

## What this is

An **Enterprise AI Control Plane**: a platform that helps large organizations meter AI usage, understand
adoption, control cost, govern usage (including MCP/agent usage), detect risk, and forecast/optimize spend.
Framed at product-strategy level, this is closer to an **Enterprise AI Operating System** than a point
metering tool — metering is one subsystem among governance, identity, MCP, policy, routing, analytics,
forecasting, and optimization.

## Deployment principle

> Same product, same APIs, different deployment boundary.

The platform must support three deployment models without forking the codebase:
1. **On-premise** — runs inside the customer's firewall, data never leaves their network.
2. **Customer cloud** — runs inside the customer's own AWS/Azure/GCP account (e.g. via Kubernetes/Helm/Terraform).
3. **SaaS** — vendor-hosted, multi-tenant, with tenant isolation, encryption, RBAC, and audit logs.

## Core architectural principle

Everything in the system revolves around one canonical, versioned event: `AIUsageEvent`
(see `specs/event-schema.md`). Metering, billing, governance, ML, dashboards, and forecasting are all
consumers of the same event stream. Don't create parallel data models for the same fact.

## Design principles

- **Documentation first.** Specs are written before code. If Claude finds itself inventing a data model,
  API shape, or governance rule that isn't in `docs/` or `specs/`, stop and write the spec first.
- **Capability-based agent roles, not model names.** Agent/workflow docs describe required capabilities
  ("deep architecture reasoning", "production-quality implementation"), not specific model versions —
  see `.ai/coordinator.md`. Don't hardcode model names into docs; they go stale.
- **Simulation vs demo data are different things.** `docs/04-simulation/` and `simulation/` define *how*
  the enterprise behaves (e.g. "Engineering uses AI 8x more than HR"). `demo-data/` is just the generated
  CSV/JSON output. Never hand-edit `demo-data/` — regenerate it from the simulator.
- **Contracts are immutable from Claude's perspective.** Files under `specs/` should not be changed by
  Claude without being asked — they represent decisions the human owner has made deliberately.

## Things we deliberately avoid

- No premature microservices split — start as modular monolith folders under `backend/`
  (`gateway/`, `metering/`, `governance/`, `intelligence/`, `connectors/`), split into real services later
  if/when it's warranted.
- No hardcoded pricing data expected to stay current — always use clearly-labeled *approximate* per-model
  pricing so the demo doesn't require constant upkeep.
- No real company data. All datasets are synthetic (see `docs/04-simulation/enterprise-profile.md`).

## Terminology

| Term | Meaning |
|---|---|
| AI Usage Event | The canonical fact record of one AI call: who, what model, tokens, cost, latency, outcome |
| Metering | Turning usage events into cost/usage numbers and chargeback |
| Governance | Policy rules that allow/block/flag AI usage based on risk |
| Shadow AI | Unapproved AI tool usage happening outside sanctioned applications |
| MCP Governance | Tracking and controlling which agents can call which MCP servers/tools |
| Digital Twin | A live model of the enterprise's org structure, apps, agents, and budgets — not just raw events |
