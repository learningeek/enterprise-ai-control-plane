# Non-goals

- We are not building an AI model provider or hosting inference ourselves.
- We are not building a general-purpose observability platform (e.g. not competing with Datadog broadly)
  — scope is specifically AI/agent/MCP usage.
- We are not replacing enterprise IAM/SSO — we integrate with Okta/Entra, we don't replace them.
- We are not attempting real-time policy enforcement inside third-party model providers in v1 — v1 is
  observability + governance + advisory blocking at the gateway layer we control.
