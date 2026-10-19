"""OpenAI organization usage API connector.

Pulls organization-level usage from OpenAI's Usage API and maps it onto `AIUsageEvent`
(specs/event-schema.md), per the Tier 1 pattern in docs/02-architecture/connector-framework.md. Requires
an org admin API key (an owner-role key on the organization, not a per-project key — usage/cost reporting
endpoints are org-scoped).

Mapping notes — **partially verified against OpenAI's published docs/cookbook as of 2026-10-19**:

- `GET /v1/organization/usage/completions` returns time-bucketed usage rows (`start_time`/`end_time` as
  unix seconds, not ISO8601 — unlike Anthropic's usage report), with `input_tokens`, `input_cached_tokens`,
  `output_tokens`, `num_model_requests`, and grouping/context fields `project_id` / `user_id` /
  `api_key_id` / `model` / `batch`. **Confirmed** directly from OpenAI's own cookbook example JSON.
- `prompt_tokens` = `input_tokens` directly. Unlike Anthropic's usage report — where uncached/
  cache-creation/cache-read are three *disjoint* pools that must be summed — OpenAI's `input_tokens` is
  already the total, and `input_cached_tokens` is a *subset* of it reported separately only so cost can
  be split by cache-hit discount. Adding them here would double-count; this is a real, easy-to-get-wrong
  difference between the two vendors' APIs, not an oversight.
- `completion_tokens` = `output_tokens`.
- **`project_id`/`api_key_id` can plausibly be an explicit JSON `null`** when not grouping by that
  dimension (confirmed as the behavior for Anthropic's equivalent fields; OpenAI's docs say ungrouped
  dimensions "return as null" too) — `row.get(key) or ""`, not `row.get(key, "")`, handles both the
  missing-key and the explicit-null case; only the former actually hits the default in a plain
  `.get(key, default)` call.
- **The `group_by` query parameter's exact encoding for *multiple* simultaneous values is genuinely
  unconfirmed** — this is the single most important thing to verify against a live account before
  trusting this connector's grouping. Secondary sources disagree: one says comma-separated
  (`group_by=model,project_id`), the Python cookbook passes a list (which `requests`'s default encoder
  would serialize as repeated `group_by=model&group_by=project_id` keys, no brackets), and a third,
  unofficial, source claims `api_key_id` and `user_id` cannot be grouped together in the same request at
  all (each only combines with `model` individually). None of these were confirmed from an unambiguous,
  directly-quoted official example showing >1 group_by value. This connector currently sends a single
  comma-joined `group_by` value as its best guess — **if a live call 400s, this parameter is the first
  thing to check**, and splitting into separate per-dimension calls may be required if the
  api_key_id/user_id mutual-exclusivity claim turns out to be real.
- **`request_cost` is not on the usage report.** OpenAI exposes actual dollar cost via a separate
  `GET /v1/organization/costs` endpoint. Not yet joined here (see `TODO` on `OpenAIUsageConnector`) —
  cost is estimated via the shared `ApproximateCatalogCostEstimator`
  (`simulation/generators/models.py`'s `MODEL_CATALOG`), same approach and same caveat as
  `anthropic_admin.py`.
- **`latency_ms` is not reported** by an aggregate usage API (bucketed counts, not per-call timing) — set
  to 0 rather than fabricated.
- **User attribution is better than Anthropic's but still not free.** OpenAI's usage rows can carry a
  `user_id`, which — when the org follows OpenAI's own recommended practice of one API key per member —
  identifies an OpenAI organization member, not this platform's `docs/01-domain/users.md`-style
  `user_id`. It still needs a join (`openai_user_owner: openai user_id -> this platform's user_id`,
  keyed by either the OpenAI user id or the `api_key_id`). Rows with no `user_id` (shared/service API
  keys) fall back to a synthetic `api_key:<api_key_id>` id — keyed by the finer-grained `api_key_id`
  rather than `project_id`, since the usage report gives real per-key granularity even unmapped and
  collapsing to project level would throw that away — which then correctly fails department resolution
  via `UserDirectory` rather than guessing.
- **`application_id`, `data_classification`, `mcp_tool_used` have no source in this API** — populated
  from static per-connector config, not invented per-event; `mcp_tool_used` is always `None` (MCP
  attribution comes from `docs/01-domain/mcp.md`'s own governance path).
- **The API's `model` string is a raw vendor name/snapshot** (e.g. `"gpt-4o-2024-08-06"`), not this
  platform's catalog `model_id` (e.g. `"openai-gpt-4o"` in `simulation/generators/models.py`'s
  `MODEL_CATALOG`) — `specs/event-schema.md` requires the latter. Resolved via a connector-supplied
  `model_id_map` (see `base.ModelIdResolver`); an unmapped name fails loudly rather than either writing
  a non-catalog string into `AIUsageEvent.model` or crashing cost estimation with a confusing catalog
  KeyError.
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

USAGE_REPORT_PATH = "/v1/organization/usage/completions"


@dataclass(frozen=True)
class OpenAIUsageConnectorConfig:
    tenant_id: str
    application_id: str
    default_data_classification: str = "internal"
    base_url: str = "https://api.openai.com"
    openai_user_owner: Mapping[str, str] = field(default_factory=dict)  # openai user_id -> user_id
    model_id_map: Mapping[str, str] = field(default_factory=dict)  # vendor model name -> catalog model_id


class OpenAIUsageConnector(Connector):
    """Tier 1 connector for OpenAI. See module docstring for mapping caveats.

    TODO: join `GET /v1/organization/costs` for actual dollar cost instead of the approximate catalog
    estimate, once that endpoint's response shape has been verified against a real org.
    """

    provider = "OpenAI"

    def __init__(
        self,
        admin_api_key: str,
        config: OpenAIUsageConnectorConfig,
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
            # group_by's multi-value encoding is unconfirmed — see module docstring. A single
            # comma-joined value is this connector's best guess among conflicting secondary sources.
            params: list[tuple[str, str]] = [
                ("start_time", str(int(since.timestamp()))),
                ("end_time", str(int(until.timestamp()))),
                ("bucket_width", "1d"),
                ("group_by", "project_id,user_id,api_key_id,model"),
            ]
            if page:
                params.append(("page", page))
            body = self._http.get(
                f"{self._config.base_url}{USAGE_REPORT_PATH}",
                params=params,
                headers={"Authorization": f"Bearer {self._admin_api_key}"},
            )
            for bucket in body.get("data", []):
                for row in bucket.get("results", []):
                    yield self._to_event(bucket, row)
            if not body.get("has_more"):
                break
            page = body.get("next_page")
            if not page:
                break

    def _to_event(self, bucket: dict, row: dict) -> AIUsageEvent:
        # .get(key) or "" (not .get(key, "")) because an ungrouped dimension can be an explicit JSON
        # null, not just absent — see module docstring.
        project_id = row.get("project_id") or ""
        openai_user_id = row.get("user_id")
        api_key_id = row.get("api_key_id") or ""
        user_id = (
            (openai_user_id and self._config.openai_user_owner.get(openai_user_id))
            or self._config.openai_user_owner.get(api_key_id)
            or f"api_key:{api_key_id}"
        )

        prompt_tokens = row.get("input_tokens", 0)  # already includes input_cached_tokens; see docstring
        completion_tokens = row.get("output_tokens", 0)
        # .get("model") or "unknown" — confirmed via OpenAI's own cookbook example: model is an explicit
        # null, not absent, for any ungrouped dimension. This connector always includes "model" in
        # group_by, so this is defensive, not expected to trigger — see anthropic_admin.py's identical fix.
        vendor_model = row.get("model") or "unknown"
        model = self._model_resolver.resolve(vendor_model)

        return AIUsageEvent(
            event_id=f"openai-usage:{bucket['start_time']}:{project_id}:{openai_user_id or api_key_id}:{vendor_model}",
            timestamp=datetime.fromtimestamp(bucket["start_time"], tz=timezone.utc),
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
