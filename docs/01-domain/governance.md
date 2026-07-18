# Governance

Governance is the policy layer that allows, blocks, or flags AI usage based on risk.

A policy example:
```json
{
  "policy": "Finance users cannot upload confidential spreadsheets to public AI models",
  "severity": "High",
  "action": "Block"
}
```

A realistic enterprise has 50-100 such policies. Governance also covers **MCP governance** — see
`docs/01-domain/mcp.md` — and **shadow AI detection** — see `docs/01-domain/shadow-ai.md`.

Risk detection example: a Finance employee uploading confidential documents to an unapproved AI service
should be flagged as a High severity incident (see `docs/04-simulation/incident-generator.md`).
