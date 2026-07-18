# Coordinator

This file answers: which docs should Claude read, which agent role owns a task, what output is expected,
and what should be updated afterward. Read this whenever picking up a new task in this repository.

## How to route a request

1. Read `docs/context.md` and `docs/current-state.md` first, always.
2. Identify the relevant domain/architecture docs for the task (e.g. building the event collector ->
   read `docs/02-architecture/system-overview.md` + `specs/event-schema.md`).
3. Pick the agent role from `.ai/agents/` whose responsibilities match the task.
4. Do the work; update `docs/current-state.md` when done.
5. If the task requires a decision not covered by existing docs/specs, write the spec/doc update first
   (per `docs/99-meta/repository-evolution.md`'s documentation-first policy), then implement.

## Example

```
Request: "Build the AI event collector."
  -> Read: context.md, system-overview.md, event-schema.md
  -> Agent: backend-engineer
  -> Deliver: FastAPI implementation, tests, OpenAPI spec, migration, updated current-state.md
```

## Model/capability selection

Don't hardcode model names into workflows or agent files. Describe **required capabilities** instead:

```yaml
# example capability annotation for a task
required_capabilities:
  - deep architecture reasoning     # -> route to whichever current model is strongest at this
  - long-context consistency
```
vs.
```yaml
required_capabilities:
  - production-quality implementation
  - refactoring
  - unit tests
```

If you want a concrete current mapping, keep it in one place (this file) so it's a one-line update when
model lineups change, rather than scattered across dozens of docs:

```yaml
# current mapping — update here only, as of the date below
# architecture / design-heavy work:      highest-reasoning available model
# day-to-day implementation:             default coding model
# documentation / narrative / UX copy:   a model tuned for writing
# last updated: see git blame
```
