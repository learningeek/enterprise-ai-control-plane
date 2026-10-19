"""Anthropic Admin API connector.

Pulls organization-level usage from Anthropic's Admin API and maps it onto `AIUsageEvent`
(specs/event-schema.md), per the Tier 1 pattern in docs/02-architecture/connector-framework.md. Requires
an Admin API key (`sk-ant-admin01-...`, distinct from a normal API key — Admin keys, an OAuth token with
`org:admin` scope, or a workspace-unscoped personal/service account key are the only credentials that
work; workspace-scoped API keys don't).

**This connector targets Claude Console (Claude Platform) orgs only.** Claude Enterprise (claude.ai team
plans) organizations don't appear in Claude Console and carry no Admin API keys at all — they use a
separate "Claude Enterprise Analytics API" with its own "Analytics API key" credential type and likely a
different response shape. If pointing this at a claude.ai Enterprise org specifically, that's the wrong
API entirely; a separate connector would be needed. (This directly resolves an earlier open question
from this project's session history about whether claude.ai usage is trackable the same way — it isn't,
via this endpoint.)

Mapping notes — **verified against platform.claude.com's published docs as of 2026-10-19**, which is a
step up from "unverified since writing" but is still not the same as verifying against a live org's
actual response; documented behavior and real behavior can still diverge:

- `GET /v1/organizations/usage_report/messages` returns time-bucketed usage rows grouped by whichever
  `group_by[]` dimensions are requested (this connector: `workspace_id`, `api_key_id`, `model`), with
  `uncached_input_tokens`, `cache_read_input_tokens`, `output_tokens`, and a *nested* `cache_creation`
  object (`{"ephemeral_1h_input_tokens": N, "ephemeral_5m_input_tokens": N}`) — **not** a flat
  `cache_creation_input_tokens` field. An earlier version of this connector assumed the flat field name
  and silently undercounted `prompt_tokens`/cost whenever cache creation occurred, since
  `row.get("cache_creation_input_tokens", 0)` returned `0` for a key that no longer exists rather than
  erroring — a real, confirmed-by-docs bug, fixed by summing both nested sub-fields instead.
- `prompt_tokens` = uncached + (cache_creation's two ephemeral sub-fields summed) + cache_read input
  tokens — all disjoint pools Anthropic bills as input for that request.
- `completion_tokens` = `output_tokens`.
- **Array query parameters use repeated `group_by[]=x&group_by[]=y` keys**, confirmed directly from
  official docs' examples (e.g. `group_by[]=inference_geo&group_by[]=model`) — not indexed
  `group_by[0]=x&group_by[1]=y`, which an earlier version of this connector sent and which doesn't match
  this API's documented convention. See `base.HTTPClient`'s `params` type for why this requires a list of
  tuples, not a dict.
- **`api_key_id` and `workspace_id` can be an explicit JSON `null`, not just absent** — confirmed:
  `api_key_id` is `null` for Console/Workbench playground usage (not tied to any API key); `workspace_id`
  is `null` for usage attributed to the default workspace. `row.get("api_key_id", "")`'s default only
  applies when the key is *missing*, not when it's present with value `None` — an earlier version of this
  connector had this bug, which would have produced a `user_id` of literally `"api_key:None"` for
  playground usage. Fixed via `row.get("api_key_id") or ""`.
- **`request_cost` is not on the usage report.** Anthropic exposes actual dollar cost via a separate
  `GET /v1/organizations/cost_report` endpoint (daily granularity only; may reflect negotiated pricing the
  public list price wouldn't). This connector does not yet join that report (see `TODO` on
  `AnthropicAdminConnector`) — it estimates cost from `CostEstimator`, defaulting to the same approximate
  per-model catalog `simulation/generators/models.py` already uses, so pricing data isn't duplicated in a
  second place with its own numbers (docs/context.md: don't create a parallel model of the same fact).
  This is a stated approximation, not a substitute for the real cost report.
- **`latency_ms` is not reported by an aggregate usage API** (it reports token/request counts per bucket,
  not per-call timing) — set to 0 rather than fabricated.
- **The usage report has no per-human-user field for ordinary API-key-based calls** — it groups by
  `api_key_id`/`workspace_id`, not a `docs/01-domain/users.md`-style `user_id`. There is an `account_id`
  field ("ID of the user account that made the request"), but it's documented as `null` "for non-OAuth
  requests" — i.e. it's only populated for OAuth-authenticated calls (e.g. Claude Code's own login flow),
  not the typical enterprise pattern of API-key-per-service or API-key-per-team. Worth revisiting as a
  potential real per-human signal if `account_id` turns out to be populated for a given org's actual
  traffic, but not assumed here since its availability is conditional and unconfirmed against live data.
  Per-user attribution otherwise is only recoverable if the org tags API keys per user; this connector
  takes an `api_key_owner` map (`api_key_id -> user_id`) for that case and falls back to a synthetic
  `api_key:<api_key_id>` user_id — with department resolution then failing loudly via `UserDirectory` (or
  resolving to "Unknown" via a permissive one — see `base.PermissiveUserDirectory`), which is correct: an
  API key is not a person, and metering/governance should not silently attribute shared-key usage to one
  individual or an invented department. The fallback is keyed by `api_key_id` rather than the coarser
  `workspace_id`, deliberately — the usage report gives real per-key granularity even without an owner
  mapping, and collapsing multiple keys in one workspace into a single synthetic id would throw that away
  for no reason.
- **`application_id`, `data_classification`, `mcp_tool_used` have no source in this API at all** — Anthropic
  has no concept of "which application called this." Populated from static per-connector config, not
  invented per-event; `mcp_tool_used` is always `None` from this connector (MCP tool attribution comes
  from `docs/01-domain/mcp.md`'s own governance path, not the model-provider usage report).
- **The API's `model` string is a dated snapshot** (e.g. `"claude-sonnet-4-20250514"`), not this
  platform's catalog `model_id` (e.g. `"anthropic-claude-sonnet-4"` in
  `simulation/generators/models.py`'s `MODEL_CATALOG`) — `specs/event-schema.md` requires the latter.
  Resolved via a connector-supplied `model_id_map` (see `base.ModelIdResolver`); an unmapped snapshot
  fails loudly rather than either writing a non-catalog string into `AIUsageEvent.model` or crashing
  cost estimation with a confusing catalog KeyError.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.connectors.base import (
    AIUsageEvent,
    ApproximateCatalogCostEstimator,
    Connector,
    CostEstimator,
    HTTPClient,
    ModelIdResolver,
    UrllibHTTPClient,
    UserDirectory,
)

ANTHROPIC_API_VERSION = "2023-06-01"
USAGE_REPORT_PATH = "/v1/organizations/usage_report/messages"


@dataclass(frozen=True)
class AnthropicAdminConnectorConfig:
    tenant_id: str
    application_id: str
    default_data_classification: str = "internal"
    base_url: str = "https://api.anthropic.com"
    api_key_owner: Mapping[str, str] = field(default_factory=dict)  # api_key_id -> user_id
    model_id_map: Mapping[str, str] = field(default_factory=dict)  # vendor model snapshot -> catalog model_id


class AnthropicAdminConnector(Connector):
    """Tier 1 connector for Anthropic. See module docstring for mapping caveats.

    TODO: join `GET /v1/organizations/cost_report` for actual dollar cost instead of the approximate
    catalog estimate, once that endpoint's response shape has been verified against a real org.
    """

    provider = "Anthropic"

    def __init__(
        self,
        admin_api_key: str,
        config: AnthropicAdminConnectorConfig,
        user_directory: UserDirectory,
        cost_estimator: CostEstimator | None = None,
        http_client: HTTPClient | None = None,
    ) -> None:
        self._admin_api_key = admin_api_key
        self._config = config
        self._user_directory = user_directory
        self._cost_estimator = cost_estimator or ApproximateCatalogCostEstimator()
        self._http = http_client or UrllibHTTPClient()
        self._model_resolver = ModelIdResolver(config.model_id_map)

    def pull(self, since: datetime, until: datetime | None = None) -> Iterator[AIUsageEvent]:
        until = until or datetime.now(timezone.utc)
        page: str | None = None
        while True:
            params: list[tuple[str, str]] = [
                ("starting_at", since.isoformat()),
                ("ending_at", until.isoformat()),
                ("group_by[]", "workspace_id"),
                ("group_by[]", "api_key_id"),
                ("group_by[]", "model"),
            ]
            if page:
                params.append(("page", page))
            body = self._http.get(
                f"{self._config.base_url}{USAGE_REPORT_PATH}",
                params=params,
                headers={
                    "x-api-key": self._admin_api_key,
                    "anthropic-version": ANTHROPIC_API_VERSION,
                },
            )
            for bucket in body.get("data", []):
                for row in bucket.get("results", []):
                    yield self._to_event(bucket, row)
            page = body.get("next_page")
            if not page:
                break

    def _to_event(self, bucket: dict, row: dict) -> AIUsageEvent:
        # .get(key) or "" (not .get(key, "")) because api_key_id/workspace_id can be an explicit JSON
        # null (playground usage, default workspace) — a key present with value None still needs this
        # fallback, which .get(key, default) alone does not provide. See module docstring.
        api_key_id = row.get("api_key_id") or ""
        workspace_id = row.get("workspace_id") or ""
        user_id = self._config.api_key_owner.get(api_key_id) or f"api_key:{api_key_id}"

        cache_creation = row.get("cache_creation") or {}
        cache_creation_tokens = cache_creation.get("ephemeral_1h_input_tokens", 0) + cache_creation.get(
            "ephemeral_5m_input_tokens", 0
        )
        prompt_tokens = (
            row.get("uncached_input_tokens", 0) + cache_creation_tokens + row.get("cache_read_input_tokens", 0)
        )
        completion_tokens = row.get("output_tokens", 0)
        vendor_model = row.get("model", "unknown")
        model = self._model_resolver.resolve(vendor_model)

        return AIUsageEvent(
            event_id=f"anthropic-admin:{bucket['starting_at']}:{workspace_id}:{api_key_id}:{vendor_model}",
            timestamp=datetime.fromisoformat(bucket["starting_at"]),
            tenant_id=self._config.tenant_id,
            user_id=user_id,
            department=self._user_directory.department_for(user_id),
            application_id=self._config.application_id,
            provider=self.provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=0,  # not reported by the aggregate usage API — see module docstring
            request_cost=self._cost_estimator.estimate(model, prompt_tokens, completion_tokens),
            data_classification=self._config.default_data_classification,
            mcp_tool_used=None,
            outcome="success",  # the usage report only reports completed, billed requests
        )
