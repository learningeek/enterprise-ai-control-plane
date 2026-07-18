# Enterprise AI Control Plane

An enterprise platform for metering, governing, and optimizing AI usage across an organization —
think of it as **FinOps + observability + governance for AI**, purpose-built for enterprises running
many models, many AI-enabled applications, and many MCP servers/agents.

## Start here (in order)

1. `docs/context.md` — philosophy, constraints, terminology. Read this first, every session.
2. `docs/current-state.md` — what's built, what's stubbed, what's next.
3. `docs/00-product/` — what we're building and for whom.
4. `docs/01-domain/` — the business language of the system.
5. `docs/02-architecture/` — how it's built.
6. `specs/` — immutable contracts. Implementation must conform to these, not the other way around.
7. `.ai/coordinator.md` — how Claude Code should pick up work in this repo.

## Rule zero

**Documentation and specs are the source of truth. Implementation follows the specs, not the reverse.**
Before writing a new module, check whether the concept already exists in `docs/` or `specs/`. If it
doesn't, update the spec first — don't let architecture emerge ad hoc from code.

## Repository layout

```
docs/            source of truth: product, domain, architecture, ADRs, workflows
specs/           immutable contracts: event schema, API contract, tenant model, pricing, governance
.ai/             Claude Code's operating layer: agent roles, workflows, coordinator
backend/         Python implementation (gateway, metering, governance, intelligence, connectors)
frontend/        React dashboard
simulation/      logic that generates realistic enterprise data
demo-data/       the generated output of simulation/ (gitignored, regenerate as needed)
deployment/      Docker, Kubernetes, Terraform
scripts/         setup/build scripts
tests/
experiments/
```
