# Simulation

Logic that generates realistic enterprise datasets. See `docs/04-simulation/` for the specs this code
implements. Output goes to `demo-data/`, which should be treated as fully regenerable.

Suggested internal layout as this is built:
```
simulation/
  behavior/      # behavior-model.md implementation
  generators/    # event/policy/incident/forecast/mcp generators
  scenarios/     # named enterprise scenarios (e.g. "acme-corp")
  profiles/      # enterprise-profile.md implementation
  statistics/    # consistency checks against the behavior model
```
