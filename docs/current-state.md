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

- **`backend/connectors/`** — Tier 1 connector interface + Anthropic, OpenAI, and Azure OpenAI reference
  connectors, per `docs/02-architecture/connector-framework.md`'s "Connector interface" section. Run
  tests with:
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
    `urllib`-based default adapter with both `get` and `post` — not every vendor source is a paginated
    `GET` usage-report endpoint, so this module adds no dependency beyond `pydantic`),
    `ApproximateCatalogCostEstimator` (reuses `simulation/generators/models.py`'s `MODEL_CATALOG` rather
    than a second hardcoded price table — shared by every connector without a real cost-report join), and
    `ModelIdResolver` (maps a vendor's raw model/deployment string to this platform's catalog `model_id`
    — `specs/event-schema.md` requires the latter; an unmapped vendor model fails loudly rather than
    silently writing a non-catalog string or crashing cost lookup with a confusing error).
  - `backend/connectors/anthropic_admin.py`, `openai_usage.py`, `azure_openai.py` — three fully-worked
    reference connectors, deliberately not identical in mapping logic where the vendor integrations
    genuinely differ (documented per-connector, not glossed over):
    - Anthropic's and OpenAI's usage reports are aggregate, paginated, GET-based, bucketed by time —
      neither reports `latency_ms` or `request_cost` directly (both estimate cost via
      `ApproximateCatalogCostEstimator`; `TODO` to join each vendor's real cost-report endpoint once
      verified against a live org), and both assume `outcome="success"` since the usage report only
      covers completed, billed requests.
    - **Azure OpenAI has no equivalent aggregate usage-report endpoint at all.** It pulls per-request rows
      from whatever the org's Azure Monitor diagnostic settings export to a Log Analytics workspace,
      queried via a KQL string over a single `POST` (no pagination — see `TODO` on `AzureOpenAIConnector`
      for chunking large windows). Being per-request rather than aggregate, it's the one connector that
      *can* report a real `latency_ms` and a real `outcome` (derived from HTTP `status_code`: 2xx ->
      success, 400 -> blocked — Azure OpenAI content filtering commonly surfaces as 400 — else error).
      Since the org's raw diagnostic log schema can't be assumed correctly without seeing a real
      deployment, this connector defines a required output *column contract*
      (`time_generated`/`deployment_name`/`prompt_tokens`/`completion_tokens`/`status_code`/
      `correlation_id`, optionally `end_user`/`duration_ms`) that `AzureOpenAIConnectorConfig.kql_query_template`
      must project to, rather than hardcoding a specific table/column layout as if it were certain to be
      correct — `DEFAULT_KQL_QUERY_TEMPLATE` is explicitly labeled illustrative-only.
    - User attribution differs across all three: Anthropic's usage report has no user field at all (only
      `api_key_id`/`workspace_id` — synthetic `api_key:<api_key_id>` fallback, deliberately keyed by the
      finer-grained API key rather than the coarser workspace, so per-key usage isn't collapsed away);
      OpenAI's carries a real `user_id` when the org follows one-key-per-member practice (same
      `api_key:<api_key_id>` fallback otherwise); Azure's resource logs generally carry only the calling
      service principal, not an employee, unless the caller passes the OpenAI API's `user` field and the
      org's export surfaces it as `end_user` (synthetic `deployment:<name>` fallback — Azure has no
      equivalent per-key concept in the diagnostic log shape this connector targets). All synthetic ids
      then correctly fail department resolution via `UserDirectory` — or resolve to `"Unknown"` via
      `PermissiveUserDirectory`, see below — rather than guessing.
    - Anthropic's input-token fields (`uncached`/`cache_creation`/`cache_read`) are three *disjoint*
      pools that must be summed for `prompt_tokens`. OpenAI's `input_tokens` already includes cached
      tokens — `input_cached_tokens` is a *subset*, not additional — so `prompt_tokens = input_tokens`
      directly. Adding them would double-count; called out explicitly in `openai_usage.py`'s docstring
      since it's an easy mistake to copy-paste past.
    - Model/deployment id mapping is keyed differently: Anthropic/OpenAI map a raw vendor model version
      string (e.g. `"gpt-4o-2024-08-06"`); Azure maps an org-chosen deployment name (e.g. `"gpt4o-prod"`,
      arbitrary per org, independent of the underlying model) via the same `ModelIdResolver`.
    - **Verified against each vendor's current published docs on 2026-10-19** (no live account was
      available to test against — see docstrings for the "docs vs. live behavior can still diverge"
      caveat that remains). Found and fixed three real, confirmed bugs: (1) both Anthropic's and OpenAI's
      connectors sent `group_by[0]=`/`group_by[1]=`-style indexed query keys, which matches neither
      vendor's actual array-param convention (fixed — see `base.HTTPClient`'s new `params` type above);
      (2) Anthropic's connector read a flat `cache_creation_input_tokens` field that no longer exists —
      the real API nests it as `cache_creation: {ephemeral_1h_input_tokens, ephemeral_5m_input_tokens}` —
      silently undercounting `prompt_tokens`/cost whenever cache creation occurred, since the stale key
      name just returned the `.get()` default of `0` instead of erroring; (3) both connectors' null-vs-
      missing handling for `api_key_id`/`workspace_id`/`project_id` was wrong — these fields can be an
      explicit JSON `null` (confirmed: Console/Workbench playground usage, the default workspace,
      ungrouped dimensions), and `row.get(key, "")` only applies its default for a *missing* key, not a
      present key with value `None` — would have produced a literal `"api_key:None"` user_id. All three
      have regression tests. Also updated Azure's default `base_url` to the newly-documented canonical
      host `api.loganalytics.azure.com` (was `api.loganalytics.io`, still Microsoft's own CLI/PowerShell
      example variable name, likely still functional, but no longer the primary documented host).
      **Still genuinely unconfirmed, flagged prominently in `openai_usage.py`'s docstring:** the exact
      encoding for OpenAI's `group_by` with *multiple* simultaneous values — secondary sources disagreed
      (comma-separated vs. repeated keys), and one unofficial source claims `api_key_id`+`user_id` can't
      be grouped together at all. The connector currently guesses comma-separated; if a live call 400s,
      this is the first thing to check. **Also found, not yet acted on:** Anthropic's usage report has an
      `account_id` field that's a real per-human identifier for OAuth-authenticated calls (unlike
      API-key-based calls, which is the typical enterprise pattern) — a potential future attribution
      improvement, noted in `anthropic_admin.py`'s docstring but not implemented since its availability
      for a given org's actual traffic is unconfirmed. **Also found:** Claude Enterprise (claude.ai team
      plans) uses an entirely separate "Analytics API" with its own "Analytics API key" credential type —
      `anthropic_admin.py` targets Claude Console orgs only; a claude.ai Enterprise org would need a
      different connector entirely. This directly resolves an earlier open question from this project's
      session history about whether claude.ai usage is trackable the same way.
  - `backend/connectors/base.py` also has **`PermissiveUserDirectory`** — wraps another `UserDirectory`
    and returns `"Unknown"` instead of raising when department can't be resolved. The strict directories
    still fail loudly by default (correct when accuracy matters); this exists so the CLI/dashboard below
    can run *before* an org has done any roster/ownership-mapping setup, rather than crashing on the
    first unmapped key.
  - `tests/connectors/` — 59 tests, all passing, using a fake `HTTPClient` per connector (no live API
    calls, no network dependency): pagination (or its absence, for Azure), token-field mapping,
    unmapped-user fallback + failure behavior (including that per-API-key granularity is preserved, not
    collapsed to workspace/project level, when unmapped), unmapped-model failure behavior,
    status-code-to-outcome mapping (Azure), event-id determinism (needed for idempotent re-pulls),
    cost-estimator correctness, the `group_by[]`-repeated-key encoding, and the three doc-verification
    regression tests described above (nested `cache_creation` summing, explicit-null field handling for
    both Anthropic and OpenAI).
  - **Not yet built:** AWS Bedrock, GitHub Copilot, Google Gemini/Vertex AI connectors (same interface,
    new module each — the three existing connectors are the references to follow; Gemini/Vertex AI is
    expected to need `azure_openai.py`'s shape, not `anthropic_admin.py`'s/`openai_usage.py`'s — see
    `docs/02-architecture/connector-framework.md`), and an "ingest from an existing LLM proxy"
    connector (LiteLLM/Portkey spend-tracking API as a Tier 1 source — see that doc's "Positioning
    relative to LLM proxies" section for why this isn't this platform building its own proxy). None were
    stubbed as empty files, per `docs/99-meta/repository-evolution.md`'s "avoid resurrecting large empty
    placeholder files."
  - **Not yet built:** the real cost-report/Cost-Management joins (currently estimated, see above), and
    the gateway-backed `EventSink` (waits on `backend/gateway`).

- **`backend/connectors/cli.py`** — the entrypoint that turns the connectors above from library code into
  something a platform team can actually run, per the "immediately useful" pivot in this project's
  session history. Config-driven (TOML — see `connectors.example.toml` at the repo root), secrets read
  from env vars named in the config, never stored in it.
  ```
  cp connectors.example.toml connectors.toml   # then edit: fill in real values, set enabled = true
  export ANTHROPIC_ADMIN_API_KEY=sk-ant-admin-...
  .venv/bin/python -m backend.connectors.cli sync --config connectors.toml
  .venv/bin/python -m backend.connectors.cli report --config connectors.toml
  ```
  `sync` runs every enabled connector into a `DuckDBEventSink`; `report` regenerates the dashboard from
  whatever's in that store. Smoke-tested against the real Anthropic, OpenAI, and Azure Log Analytics
  endpoints with deliberately invalid credentials — all three reached the real API and got a real `401`,
  confirming the request construction (including the new query-encoding and base-URL fixes below) is
  correct, not just internally self-consistent against test fakes.

  **Two more real bugs found in a 2026-10-19 code review pass** (independent of the doc-verification pass
  above): `build_connectors()` was creating one `http_client_factory()` instance and sharing it across
  all enabled connectors rather than one per connector — harmless today since nothing stateful is passed
  in production, but a latent footgun for any future stateful client; fixed to call the factory once per
  connector. And `usage_summary()` (and therefore `report`) crashed with a raw DuckDB
  `CatalogException` if run against a path `sync` had never touched — fixed to create the table first,
  so an uninitialized store returns `[]` cleanly. Also: a misconfigured/typo'd `users_csv` path produced
  a raw `FileNotFoundError` instead of the clear `SystemExit` every other config-misconfiguration case in
  `cli.py` produces — fixed to match. All three have regression tests (80 total across `tests/connectors/`
  and `tests/metering/`).

- **`backend/metering/`** — first real slice built, not just a README anymore:
  - `duckdb_store.py` — `DuckDBEventSink` (`EventSink` implementation, DuckDB per ADR 0003), inserts
    idempotent on `event_id` (`emit()` returns the count of *newly* inserted rows, so re-running `sync`
    over an overlapping window is safe and doesn't double-count — this is `Connector.pull()`'s
    idempotency requirement actually being relied on, not just asserted in a connector test). Plus
    `usage_summary()`, a query helper aggregating by `(user_id, department, provider, model)`.
  - `report.py` — renders `usage_summary()`'s output as a self-contained static HTML dashboard, built per
    this project's dataviz skill (fixed categorical color order by provider — never reassigned based on
    which providers are present in a given store; `html.escape()` on every user-controlled field):
    - **`aggregate_attribution()` + the "AI spend attribution" panel** — the headline metric per
      `docs/00-product/vision.md`'s "cost is the entry point, not the destination" and
      `docs/00-product/competitive-landscape.md`'s finding that attribution completeness, not raw cost
      aggregation, is the sharper differentiator. Leads the dashboard (above the stat grid) with a hero
      figure (`"71.4%"` of spend attributed to a known owner), a meter, and an unattributed-spend-by-
      provider breakdown — not just the existing `(N unmapped)` stat tile buried lower on the page.
      Handles zero-spend (`pct_attributed=None`, renders `"—"` / "No spend recorded yet." rather than
      dividing by zero) and the fully-attributed case (no breakdown bars, explicit "None" message) without
      crashing.
    - Cost-by-provider bar chart, top-API-keys-by-cost bar chart, full sortable table (unchanged from the
      prior pass) — plus the existing attribution-scope banner explaining what `user_id`/`department`
      actually mean (see prior note: real employee only where ownership mapping is configured, otherwise
      synthetic `api_key:<id>`/`deployment:<name>` with `department="Unknown"`).
  - `scripts/generate_demo_dashboard_data.py` — populates a demo DuckDB store with a realistic mix of
    mapped/unmapped users across all three providers, for exercising the dashboard without live vendor
    credentials (none are available in this environment). Labeled clearly as sample data, not a real pull.
  - `tests/metering/` — 19 tests: idempotent-insert behavior, aggregation correctness, fixed
    provider-color ordering (including for a provider not in the fixed list), HTML-escaping of untrusted
    fields, empty-store handling, and `aggregate_attribution()`'s split/percentage/zero-spend/
    fully-attributed/provider-breakdown-ordering behavior.
  - Chargeback, full cost reconciliation, and the eventual Postgres-backed system of record
    (`backend/gateway`) are still not built — this is the local/single-tenant analytics slice only, per
    ADR 0003's intended scope for DuckDB.

## Stubbed / planned but not built

- `backend/gateway` — AI usage collector / Postgres-backed system of record (see
  `docs/02-architecture/system-overview.md`); the local DuckDB analytics store above is not a substitute
  for this, see `backend/metering/`'s note in "Implemented"
- `backend/metering` — chargeback and full cost reconciliation beyond the DuckDB analytics slice already
  built (see "Implemented" above)
- `backend/governance` — policy engine
- `backend/intelligence` — forecasting, anomaly detection, recommendations
- `backend/connectors` — Okta/Entra, SAP, ServiceNow, Salesforce, Snowflake, MCP inventory, and the
  remaining Tier 1 AI-provider connectors (Bedrock, GitHub Copilot, Gemini/Vertex AI, existing-LLM-proxy
  ingestion) — Anthropic, OpenAI, and Azure OpenAI are built, see above
- `frontend/` — executive, engineering, and security dashboards (the static HTML dashboard in
  `backend/metering/report.py` is a first cut at the "engineering" slice of this, not a replacement for
  the eventual React app — no interactivity beyond a browser's native scroll/hover)

## Explicitly missing / not decided yet

- Final pricing model numbers (see `specs/pricing-model.md`, flagged as draft)
- Which compliance frameworks to certify against (SOC 2, ISO 27001, etc.) — not yet decided
- Whether SaaS multi-tenancy is pooled or siloed at the database layer — not yet decided

## Next up

The "immediately useful" wedge (Tier 1 connectors -> CLI -> DuckDB -> dashboard, with attribution
completeness as the dashboard's headline metric) is now real end-to-end for Anthropic/OpenAI/Azure
OpenAI — see "Implemented" above. What's left, roughly in order:

1. The cheapest real governance signal before a full policy engine: threshold alerts / non-approved-model
   flags / cost-anomaly detection (e.g. "this key's spend increased 300% week-over-week") off the same
   DuckDB store the dashboard already reads — see `backend/governance`. This is a cheap, concrete
   manifestation of "AI discovery," not just cost display.
2. Widen Tier 1 provider coverage: Bedrock, GitHub Copilot, Google Gemini/Vertex AI, and an
   "ingest from an existing LLM proxy" connector, against the shared interface in
   `backend/connectors/base.py` — each slots into the existing CLI/dashboard automatically once built
   (`cli.py`'s `build_connectors` just needs a new `elif` block per vendor). See
   `docs/02-architecture/connector-framework.md`'s "Connector interface", "Positioning relative to LLM
   proxies", and cloud-billing-export sections. Without this, AWS-heavy/Microsoft-365-heavy/GCP-heavy orgs
   get a confidently presented but materially incomplete picture from the dashboard.
3. A real cost-report join for at least one connector (OpenAI is the best-understood API shape) instead
   of the approximate catalog estimate everywhere — proves that design before repeating it a third/fourth
   time.
4. **Open design question, not decided:** whether the flat `AIUsageEvent` model is sufficient long-term,
   or whether attribution/governance eventually needs an explicit relationship model (employee -> app ->
   agent -> MCP tool/data-source edges, not just per-request facts) — see
   `docs/00-product/competitive-landscape.md`'s "AI asset graph" discussion. This would be a real data-model
   expansion, not an additive tweak — `specs/event-schema.md` is an immutable v1 contract, so this needs a
   deliberate versioned decision from the human owner, not something to build toward speculatively.
5. Stand up `backend/gateway` per `docs/02-architecture/system-overview.md` and `specs/event-schema.md` —
   this is Tier 2 (real-time policy enforcement) and the eventual Postgres-backed system of record,
   deliberately *not* a prerequisite for the visibility wedge above, per this session's "immediately
   useful" pivot. `demo-data/ai_events.csv` remains a source to replay/ingest for local development.
6. `specs/tenant-model.md`'s pooled-vs-siloed decision is a blocking dependency for #5's schema design —
   not yet decided, the human's call.
7. Tier 3 (CASB/SASE integration for shadow-AI detection) — lower priority, evaluate once Tiers 1-2 are
   live and there's a concrete CASB target to integrate against.
8. `simulation/scenarios/` (named enterprise scenarios beyond the single default profile) is listed in
   `simulation/README.md`'s suggested layout but not yet built — only needed if/when a second named
   scenario (not just "acme-corp") is required.
