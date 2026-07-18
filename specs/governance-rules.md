# Spec: governance rules (v1 draft)

Policy object shape:
```json
{
  "policy_id": "string",
  "policy": "human-readable rule description",
  "severity": "Low | Medium | High",
  "action": "Allow | Flag | Block"
}
```

See `docs/01-domain/governance.md` for the business meaning and `docs/04-simulation/policy-generator.md`
for how a realistic policy set is generated for development/demo purposes.
