# Repository evolution and stewardship

This file is not part of the product. It is instructions to Claude Code on how to evolve the repository
itself over time.

## 1. Vision

The repository should read as a coherent, documentation-led system, not an accumulation of code that
happened to get written. Docs and specs are authoritative; implementation is downstream of them.

## 2. Repository principles

- Group by domain, not by technology, where practical (e.g. `governance/` not `rules-engine/`).
- Prefer moving existing folders over creating duplicates.
- Don't introduce new top-level directories without a clear architectural reason recorded as an ADR.
- Avoid renaming public concepts (entities, module names) without updating all related documentation.

## 3. Current state

See `docs/current-state.md` for the living snapshot of what's implemented vs stubbed vs missing.

## 4. Target repository layout

```
enterprise-ai-control-plane/
README.md
docs/            <- source of truth
specs/           <- immutable contracts
.ai/             <- Claude Code operating layer
backend/         <- Python implementation
frontend/        <- React dashboard
simulation/      <- data-generation logic
demo-data/       <- generated output
deployment/      <- Docker/Kubernetes/Terraform
scripts/
tests/
experiments/
```

## 5. Migration plan

The prior scaffold (`gateway/`, `metering/`, `governance/`, `intelligence/`, `connectors/` at the repo
root, with empty placeholder `.py` files) should be nested under `backend/` rather than discarded — the
domain boundaries were correct, only the placement was premature. Placeholder Python files were already
removed; do not recreate empty stub files. Let implementation emerge from `specs/` and `docs/`.

## 6. Rules for future refactoring

- A folder move/rename is a "breaking organizational change" if it changes a path referenced by an ADR,
  spec, or another doc — update all references in the same change.
- Don't create a new top-level directory casually; propose it via a new ADR first.

## 7. Folder ownership

- `docs/`, `specs/`, `.ai/` — owned by whoever is doing architecture/product work (Claude in "architect"
  role, or the human).
- `backend/`, `frontend/`, `simulation/` — owned by implementation work (Claude in engineer roles).
- `demo-data/` — generated only, never hand-edited, safe to delete and regenerate.

## 8. Documentation-first policy

> Before creating a new implementation module, determine whether the concept already exists in the
> documentation. If not, update the appropriate specification first. Implementation should follow
> approved specifications rather than introducing new architecture.

## 9. Code generation policy

Claude Code should generate code module by module from specs, not generate broad scaffolding ahead of
specs being written. Avoid resurrecting large empty placeholder files "just in case."

## 10. Completion criteria

The repository is "organized" when: docs and code are not drifting apart, there is no duplication of a
concept across two folders, naming is consistent with `docs/01-domain/`, and `docs/current-state.md`
accurately reflects what exists.

## Repository stewardship

This is a standing responsibility, not a one-time task. Periodically (e.g. at the start of a large
session, or when asked to review the repo), Claude should evaluate: Is the repository still organized?
Are docs and code drifting apart? Should modules be split? Is there duplication? Are naming conventions
still consistent? Propose organizational improvements rather than only generating new code.
