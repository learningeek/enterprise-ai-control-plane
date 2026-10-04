# Competitive landscape

**Source note:** this file summarizes external research conducted by a different AI system (ChatGPT), not
independently verified by Claude — vendor names, customer counts, and case-study figures below should be
treated as reported-but-unconfirmed, not fact, until someone checks them directly. Reviewed 2026-08-20.
Update or correct this file as real information becomes available; don't treat it as load-bearing for
product decisions on its own.

## Adjacent players

| Company | What they solve | Enterprise-wide | Non-disruptive (no app changes) |
|---|---|---|---|
| CloudZero | AI/cloud cost & allocation, from the financial/billing side | High | High |
| Datadog | AI infrastructure/application observability, broad enterprise penetration | High | Medium |
| Helicone | LLM observability/metering, developer/application-centric, can sit as a gateway | Medium | Low |
| Langfuse | LLM traces/evals/cost, open source, self-hostable, application-centric | Medium | Low |
| AI gateways (LiteLLM, Portkey, etc.) | Routing + metering + control, in the request path | Medium-High | Low |

**CloudZero** is the closest match to this project's Tier 1 wedge: connects to AWS/Azure/GCP and AI
provider (Anthropic, OpenAI) billing/usage data, markets "AI cost intelligence that doesn't require
perfect tagging." Reportedly has meaningful enterprise traction ingesting AI spend this way — reported,
not independently confirmed. This is validation that the "connect to existing telemetry, don't sit in
the request path" approach is commercially viable, not just architecturally reasonable — see
`docs/02-architecture/connector-framework.md`'s Tier 1 design, which converged on the same shape
independently.

**Helicone / Langfuse** solve a different, narrower question — "how is my AI application behaving"
(request-level traces, latency, per-call cost) — rather than "how much AI is my entire enterprise
consuming, attributed to whom." Useful signal that there's a real market for LLM observability, but not
directly competitive with this project's enterprise-wide, org-structure-aware scope.

**Datadog** validates enterprise willingness to pay for AI observability at very large contract sizes, but
its scope is broader infrastructure/app monitoring, not specifically an AI financial/governance control
plane — consistent with this project's own `docs/00-product/non-goals.md` ("not competing with Datadog
broadly").

## The gap this project is positioned in

None of the above combine, in one product: org-structure-aware cost *attribution* (not just cost
aggregation), MCP/agent-level governance, and a deployment story (on-prem/customer-cloud/SaaS) aimed at
the same buyer. That combination — not "another AI cost dashboard" — is the actual differentiation. See
`docs/00-product/vision.md`'s "Enterprise Digital Twin" framing, which already points at this; this file
adds market evidence, not a new direction.

## Positioning implication

Don't lead with "we meter AI models" — every adjacent player already does token/cost aggregation
reasonably well. Lead with **attribution completeness**: what fraction of AI spend can be tied to a known
owner, application, or agent, and what can't. The "Unknown" bucket is the sharper hook than the total
spend number — see `docs/00-product/goals.md`'s "attributable to department/app/user" goal, and the
dashboard's existing `(N unmapped)` stat tile in `backend/metering/report.py`, which already surfaces this
without having been built in response to this research — a convergent signal, not a new requirement.
