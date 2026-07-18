# Current state

Claude Code: update this file whenever you finish a unit of work. This is how future sessions avoid
re-deriving or re-litigating decisions.

## Implemented

- **`simulation/`** — full enterprise data generator per `docs/04-simulation/*` and `docs/01-domain/*`,
  built by the simulation-engineer agent. Deterministic (fixed seed, see
  `simulation/profiles/enterprise_profile.py`), regenerate anytime with:
  ```
  .venv/bin/python -m simulation.generate_all
  ```
  - `simulation/profiles/enterprise_profile.py` — `docs/04-simulation/enterprise-profile.md` as an
    editable `EnterpriseProfile` dataclass (25,000 employees, 10 departments, 260 apps, 15 agents,
    40 MCP servers, 500,000 ai_events, 75 policies, 12mo cost history) — no magic numbers in generators.
  - `simulation/behavior/behavior_rules.py` — `docs/04-simulation/behavior-model.md` as an explicit
    `BEHAVIOR_RULES` dict keyed by department (usage_multiplier, governance strictness, token/context
    shape, task-category mix, provider affinity, MCP/shadow-AI affinity). Note: behavior-model.md's
    "Customer Support" example rule is mapped onto the `Operations` department, since
    enterprise-profile.md's fixed 10-department list has no separate Support department — documented
    in that file's module docstring.
  - `simulation/generators/` — one module per dataset: `departments`, `users`, `applications`, `models`
    (+ `pricing`), `ai_events`, `mcp_servers`, `mcp_tool_calls`, `monthly_costs`, `billing_accounts`,
    `sso_groups`, `policies`, `incidents`, `shadow_ai`. All read sizing from the profile and shape from
    the behavior rules; nothing is hardcoded per-department in generator logic.
  - `simulation/statistics/consistency_checks.py` — 9 assertions run automatically at the end of
    `generate_all.py` (engineering-vs-HR per-capita usage ratio, Finance/Legal stricter blocked-rate,
    Legal longest context, Operations shortest-prompts/high-volume, incidents reference real events,
    incidents skew toward Finance/Legal/Security, no cost without tokens, full referential integrity,
    monthly_costs reconciles with aggregated ai_events + mcp_tool_calls). All 9 currently pass.
  - `demo-data/` is fully populated (all 14 files listed in `demo-data/README.md`) and reproducible —
    two consecutive runs produce byte-identical CSVs.

### Design notes worth knowing before touching this again

- `ai_events.csv` and `mcp_tool_calls.csv` cover the most recent 3 calendar months (month-aligned, not
  a rolling N-day window) so they can be reconciled exactly against `monthly_costs.csv`'s most recent
  3 months. The earlier 9 months of `monthly_costs.csv` are a synthetic backfill (smooth ~3.5%/month
  growth trend) whose department cost-*share* is derived from the first reconciled month's actual
  spend mix, not from event-volume weights — an earlier version used volume weights and produced a
  visible discontinuity at the synthetic/reconciled boundary (Operations is high-*volume* but
  low-*cost* per event, so volume share != cost share).
- **Known scale gap vs. the illustrative examples in the docs:** `docs/04-simulation/cost-model.md`
  gives "$210K -> $225K -> $240K" as an example monthly trend, and `docs/01-domain/mcp.md` gives "the
  GitHub MCP server was called 1.2M times this month" as an example volume. The generated data's
  company-wide monthly spend is currently ~$1.5K -> ~$2.1K/month, and MCP call volume ~100K/quarter
  total across all 40 servers — both roughly two orders of magnitude below those illustrative numbers.
  This wasn't an oversight: reaching those figures bottom-up (tokens x approximate real per-model
  pricing, at the spec's documented 100K-500K event cap) would require either inflating per-token
  prices past what's realistic/approximate-to-real (violates `specs/pricing-model.md`'s "clearly
  labeled approximate" intent) or pushing per-event token counts into implausible territory for tasks
  behavior-model.md itself calls "short" (customer support, SQL generation). `ai_event_count` and
  `mcp_tool_call_count` are already set to the top of their documented ranges. If a bigger-dollar demo
  is wanted later, the honest levers are: increase `history_months`/event volume beyond the documented
  range (would need a profile/doc update first — see docs/context.md's "documentation first"
  principle), or treat `monthly_costs.csv` as a top-down company invoice figure decoupled from the
  bottom-up `ai_events.csv` sample rather than reconciled with it (a bigger design change than fixing
  this pass).
- Pricing (`models.csv`/`pricing.csv`) is real-world-approximate per `docs/01-domain/models.md` and
  `specs/pricing-model.md` — 13 models across the 5 documented providers, 2 marked `approved=False`
  (preview/legacy) to drive the "non-approved model used" incident type.

- **`backend/connectors/`** — Tier 1 connector interface + Anthropic and OpenAI reference connectors, per
  `docs/02-architecture/connector-framework.md`'s "Connector interface" section. Run tests with:
  ```
  .venv/bin/pip install -r backend/requirements.txt
  .venv/bin/python -m pytest tests/connectors/
  ```
  - `backend/connectors/base.py` — the shared contract every Tier 1 connector implements:
    `AIUsageEvent` (pydantic, mirrors `specs/event-schema.md` field-for-field), `Connector` (ABC,
    `pull(since, until) -> Iterator[AIUsageEvent]`), `EventSink` (pluggable — `JSONLSink` for local dev,
    `ListSink` for tests; the gateway's `POST /v1/events` becomes the production sink once
    `backend/gateway` exists, but connector work isn't coupled to or blocked by that), `UserDirectory`
    (`CSVUserDirectory` reads `demo-data/users.csv` as a stand-in for a real Okta/Entra sync —
    connectors resolve `department` from here, they never invent it), `HTTPClient` (a stdlib-only
    `urllib`-based default adapter, so this module adds no dependency beyond `pydantic`),
    `ApproximateCatalogCostEstimator` (reuses `simulation/generators/models.py`'s `MODEL_CATALOG` rather
    than a second hardcoded price table — shared by every connector without a real cost-report join), and
    `ModelIdResolver` (maps a vendor's raw model string, e.g. `"gpt-4o-2024-08-06"`, to this platform's
    catalog `model_id`, e.g. `"openai-gpt-4o"` — `specs/event-schema.md` requires the latter; an unmapped
    vendor model fails loudly rather than silently writing a non-catalog string or crashing cost lookup
    with a confusing error).
  - `backend/connectors/anthropic_admin.py` and `backend/connectors/openai_usage.py` — two fully-worked
    reference connectors, same shape, deliberately not identical in mapping logic where the vendor APIs
    genuinely differ (documented per-connector, not glossed over):
    - Neither API reports `latency_ms` or `request_cost` directly (both estimate cost via
      `ApproximateCatalogCostEstimator`, with a `TODO` to join each vendor's real cost-report endpoint
      once its shape is verified against a live org).
    - Anthropic's usage report has no user field at all — only `api_key_id`/`workspace_id`; falls back to
      a synthetic `workspace:<id>` user_id. OpenAI's does carry a `user_id` (an org member id) when the
      org follows OpenAI's one-key-per-member practice; falls back to a synthetic `project:<id>` user_id
      only when that's null. Both synthetic ids then correctly fail department resolution via
      `UserDirectory` rather than guessing.
    - Anthropic's input-token fields (`uncached`/`cache_creation`/`cache_read`) are three *disjoint*
      pools that must be summed for `prompt_tokens`. OpenAI's `input_tokens` already includes cached
      tokens — `input_cached_tokens` is a *subset*, not additional — so `prompt_tokens = input_tokens`
      directly. Adding them would double-count; this asymmetry is called out explicitly in
      `openai_usage.py`'s docstring since it's an easy mistake to copy-paste past.
    - Field names for both usage-report APIs should be re-verified against current vendor docs before
      pointing either at a real org — noted explicitly in both docstrings as unverified-since-writing.
  - `tests/connectors/` — 22 tests, all passing, using a fake `HTTPClient` per connector (no live API
    calls, no network dependency): pagination, token-field mapping, unmapped-user fallback + failure
    behavior, unmapped-model failure behavior, event-id determinism (needed for idempotent re-pulls), and
    cost-estimator correctness.
  - **Not yet built:** Azure OpenAI, AWS Bedrock, and GitHub Copilot connectors (same interface, new
    module each — `anthropic_admin.py`/`openai_usage.py` are the references to follow). None were stubbed
    as empty files, per `docs/99-meta/repository-evolution.md`'s "avoid resurrecting large empty
    placeholder files."
  - **Not yet built:** the real cost-report joins (currently estimated, see above), and the
    gateway-backed `EventSink` (waits on `backend/gateway`).

## Stubbed / planned but not built

- `backend/gateway` — AI usage collector (see `docs/02-architecture/system-overview.md`)
- `backend/metering` — token counting, cost calculation, chargeback
- `backend/governance` — policy engine
- `backend/intelligence` — forecasting, anomaly detection, recommendations
- `backend/connectors` — Okta/Entra, SAP, ServiceNow, Salesforce, Snowflake, MCP inventory, and the
  remaining Tier 1 AI-provider connectors (Azure OpenAI, Bedrock, GitHub Copilot) — Anthropic and OpenAI
  are built, see above
- `frontend/` — executive, engineering, and security dashboards

## Explicitly missing / not decided yet

- Final pricing model numbers (see `specs/pricing-model.md`, flagged as draft)
- Which compliance frameworks to certify against (SOC 2, ISO 27001, etc.) — not yet decided
- Whether SaaS multi-tenancy is pooled or siloed at the database layer — not yet decided

## Next up

1. Build the remaining Tier 1 AI-provider-admin-API connectors (Azure OpenAI, Bedrock, GitHub Copilot)
   following `backend/connectors/anthropic_admin.py` / `openai_usage.py`'s pattern against the shared
   interface in `backend/connectors/base.py` (see "Implemented" above and
   `docs/02-architecture/connector-framework.md`'s "Connector interface" section). Highest-adoption,
   lowest-friction path to real usage data; doesn't depend on the gateway existing first.
2. Stand up `backend/gateway` per `docs/02-architecture/system-overview.md` and `specs/event-schema.md`,
   using `demo-data/ai_events.csv` as a source to replay/ingest for local development. This now also
   covers Tier 2 (proxy, scoped to raw SDK/CLI usage the admin-API connectors can't see) and is the path
   real-time policy enforcement needs, per `connector-framework.md`.
3. Build the metering engine and a minimal dashboard to close the loop end-to-end, consuming events from
   both the Tier 1 connectors and the Tier 2 gateway.
4. Tier 3 (CASB/SASE integration for shadow-AI detection) — lower priority, evaluate once Tiers 1-2 are
   live and there's a concrete CASB target to integrate against.
5. `simulation/scenarios/` (named enterprise scenarios beyond the single default profile) is listed in
   `simulation/README.md`'s suggested layout but not yet built — only needed if/when a second named
   scenario (not just "acme-corp") is required.
