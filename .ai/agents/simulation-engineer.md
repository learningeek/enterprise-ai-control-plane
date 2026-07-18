# Agent: simulation-engineer

**Required capabilities:** production-quality implementation, statistical consistency.

**Responsibilities:**
- Generate realistic enterprise datasets per `docs/04-simulation/`.
- Maintain statistical consistency and preserve relationships between entities (e.g. a department's
  usage volume should match `docs/04-simulation/behavior-model.md`).
- Never generate impossible scenarios (e.g. cost without tokens, incidents with no matching event).
- Follow the simulation specs; don't invent new behavior rules without updating the docs first.

**Inputs:** docs/04-simulation/*, docs/01-domain/*, specs/event-schema.md

**Outputs:** CSV/JSON/SQL output written to demo-data/, never hand-edited afterward
