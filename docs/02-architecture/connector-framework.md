# Connector framework

`backend/connectors/` hosts integrations to enterprise systems, each behind a common connector interface:

- **Identity/SSO** — Okta, Microsoft Entra ID
- **Billing** — SAP or equivalent finance system, for chargeback reconciliation
- **ITSM** — ServiceNow, for incident/policy-violation ticketing
- **Data platforms** — Snowflake, Salesforce (as MCP-governed data sources)
- **AI provider admin APIs** — Anthropic Admin API, OpenAI org usage API, Azure OpenAI diagnostics,
  AWS Bedrock (via CloudTrail), GitHub Copilot Business/Enterprise admin API, Google Gemini/Vertex AI
  (via Cloud Billing export + Cloud Logging — same "no aggregate usage-report API" shape as Azure OpenAI,
  not the OpenAI/Anthropic shape; see "How AI usage reaches the platform" below).
- **Existing LLM proxies as a Tier 1 source** — if an org already runs an LLM gateway (LiteLLM, Portkey,
  etc.) with per-employee virtual keys, ingest *from its spend-tracking API* as one more Tier 1 connector
  rather than building a competing proxy. This is deliberately not this platform's own interception layer
  — see "Positioning relative to LLM proxies" below.

New connectors should implement the interface defined in `specs/api-contract.md` /
`docs/02-architecture/connector-framework.md` rather than being bespoke one-offs.

## How AI usage reaches the platform

Usage collection has three tiers, ordered by integration friction, applied in this order — each tier
exists only to cover what the tier above it can't see. Interception coverage is not the goal; minimizing
new workflows for end users is.

1. **Pull from vendor admin APIs (preferred, no client-side change).** For sanctioned AI vendors that
   expose enterprise usage/admin APIs — Anthropic, OpenAI, Azure OpenAI, Google Gemini/Vertex AI,
   AWS Bedrock, GitHub Copilot — ingest usage as a `backend/connectors/` integration, the same pattern as
   the Okta/SAP/ServiceNow connectors above. This requires no change to how engineers or business users
   work; it's purely a platform-side API key configuration. This tier alone should cover most sanctioned
   usage and is sufficient for metering/visibility, since it's read-only observability, not real-time
   enforcement.
2. **Proxy, scoped to the gap.** For raw SDK/CLI usage with no admin API, redirect via client-side base
   URL configuration (e.g. `ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL`) pushed through existing IT channels
   (MDM shell profile, CI secrets) rather than a code change per tool. Use this only where Tier 1 doesn't
   cover, and only when real-time policy enforcement (blocking a call, not just observing it after the
   fact) is actually required — that's the one thing Tier 1 structurally cannot do, since it reports
   usage after it already happened.
3. **Piggyback on existing CASB/SASE for shadow AI.** For unsanctioned web AI usage outside any connector
   or proxy, integrate with the enterprise's existing CASB/SASE tooling (e.g. Zscaler, Netskope) as a
   data source for `docs/04-simulation/`'s shadow-AI signal, rather than deploying a new browser
   extension or agent. Lower fidelity (domain/timestamp/bytes, not tokens/cost) but zero new rollout.

## Positioning relative to LLM proxies (LiteLLM, Portkey, etc.)

This platform does not build or operate its own network proxy/gateway in front of AI provider calls.
That's a deliberate choice, not an oversight: `docs/00-product/non-goals.md` already scopes v1 away from
real-time enforcement inside third-party providers, and a proxy is exactly the product LiteLLM/Portkey/
Helicone already are — unified API, routing, fallback, spend tracking for whatever traffic is routed
through them. Building a competing proxy means taking on their operational risk profile (added latency
in the production call path, a new single point of failure, an ongoing obligation to track every
provider's API changes) to re-solve a problem that's already a commodity in the OSS ecosystem.

The one thing a network proxy genuinely does better than a Tier 1 admin-API connector is **attribution
accuracy** — it can capture real per-call identity at the moment of the call, instead of reconstructing
it after the fact from a vendor usage report that may not carry it at all (see `anthropic_admin.py`'s and
`azure_openai.py`'s docstrings). The resolution is not to build that proxy ourselves: if an org already
runs one with per-employee virtual keys, **ingest from its spend-tracking API as an additional Tier 1
connector**, the same pattern as any vendor admin API. That inherits proxy-quality attribution when it
exists, without owning the proxy, its latency cost, or the "why not just use the thing I already have"
objection an enterprise running LiteLLM would reasonably raise against a second one.

## Connector interface (Tier 1: AI provider admin APIs)

Every Tier 1 connector implements the same three-part shape, so a new vendor is a new module, not a new
pattern:

- **`Connector`** — one per vendor. Exposes `pull(since, until) -> Iterator[AIUsageEvent]`, which calls
  the vendor's admin/usage API and maps each vendor-native usage record onto `specs/event-schema.md`'s
  `AIUsageEvent` fields exactly (no invented fields, no vendor-specific extensions). Pulling is
  idempotent — re-pulling an overlapping `[since, until)` window must not duplicate events downstream
  (dedupe on `event_id`). Not every vendor's source is a paginated REST usage-report endpoint reached
  with a `GET` — e.g. `azure_openai.py` queries a Log Analytics workspace via KQL over `POST`, with no
  pagination at all — so `HTTPClient` supports both `get` and `post`; a `Connector` uses whichever its
  vendor's actual API requires rather than forcing every vendor through one HTTP shape.
- **`UserDirectory`** — a lookup (`user_id -> department`, `cost_center`, etc.) that a Tier 1 connector
  depends on to fill `AIUsageEvent.department`, per `docs/01-domain/users.md`: "users are synced from the
  customer's SSO, not manually managed." An AI-provider connector never invents department data itself —
  it resolves it from whatever already synced the org roster (the identity/SSO connector, ultimately). For
  local dev/demo, a directory backed by `demo-data/users.csv` stands in for a real Okta/Entra sync.
- **`EventSink`** — where mapped events go. `specs/api-contract.md`'s `POST /v1/events` (the gateway) is
  the intended production sink once `backend/gateway` exists, but the connector itself is not coupled to
  it — sinks are pluggable (e.g. a JSONL file sink for local dev/tests) so connector work isn't blocked on
  gateway work, and vice versa.
- **`ModelIdResolver`** — every vendor usage API reports its own raw model string (a dated snapshot, an
  alias, whatever that vendor calls it) — never `docs/01-domain/models.md`'s catalog `model_id` that
  `specs/event-schema.md`'s `model` field actually requires. A connector must map vendor string ->
  catalog `model_id` explicitly (connector-supplied config, not a guessed prefix/suffix match, since
  vendor model strings drift); an unmapped model fails the pull loudly rather than writing a non-catalog
  string into `AIUsageEvent.model` or corrupting cost estimation.

Vendor APIs also differ in ways that must not be papered over by a shared abstraction: which token-count
fields are disjoint pools to sum vs. an already-inclusive total with a cached subset reported separately,
whether the API exposes any per-human-user field at all, and whether cost is on the usage report or needs
a separate cost-report join. Document these per-connector-module, not in this shared file.

Vendor-specific mapping notes (e.g. how an Anthropic Admin API usage record's fields line up with
`AIUsageEvent`) belong in each connector module's docstring, not here — this file stays about the shared
shape, not per-vendor detail.
