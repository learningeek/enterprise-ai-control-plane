"""Anthropic Admin API connector.

Pulls organization-level usage from Anthropic's Admin API and maps it onto `AIUsageEvent`
(specs/event-schema.md), per the Tier 1 pattern in docs/02-architecture/connector-framework.md. Requires
an Admin API key (an `sk-ant-admin...` key, distinct from a normal API key — Admin keys are scoped to
org-level reporting/management endpoints, not to making model calls).

Mapping notes — verify field names against the current Anthropic Admin API docs before pointing this at
a real org; the usage-report API surface has changed before and may again:

- `GET /v1/organizations/usage_report/messages` returns time-bucketed usage rows grouped by
  `workspace_id` / `api_key_id` / `model`, with `uncached_input_tokens`, `cache_creation_input_tokens`,
  `cache_read_input_tokens`, `output_tokens`.
- `prompt_tokens` = uncached + cache_creation + cache_read input tokens (all three are tokens Anthropic
  billed as input for that request).
- `completion_tokens` = `output_tokens`.
- **`request_cost` is not on the usage report.** Anthropic exposes actual dollar cost via a separate
  `GET /v1/organizations/cost_report` endpoint (org-level, may reflect negotiated pricing the public list
  price wouldn't). This connector does not yet join that report (see `TODO` on `AnthropicAdminConnector`)
  — it estimates cost from `CostEstimator`, defaulting to the same approximate per-model catalog
  `simulation/generators/models.py` already uses, so pricing data isn't duplicated in a second place with
  its own numbers (docs/context.md: don't create a parallel model of the same fact). This is a stated
  approximation, not a substitute for the real cost report.
- **`latency_ms` is not reported by an aggregate usage API** (it reports token/request counts per bucket,
  not per-call timing) — set to 0 rather than fabricated.
- **The usage report has no per-human-user field** — it groups by `api_key_id`/`workspace_id`, not a
  `docs/01-domain/users.md`-style `user_id`. Per-user attribution is only recoverable if the org tags API
  keys per user; this connector takes an `api_key_owner` map (`api_key_id -> user_id`) for that case and
  falls back to a synthetic `workspace:<workspace_id>` user_id — with department resolution then failing
  loudly via `UserDirectory`, which is correct: a workspace is not a person, and metering/governance
  should not silently attribute shared-key usage to one individual or an invented department.
- **`application_id`, `data_classification`, `mcp_tool_used` have no source in this API at all** — Anthropic
  has no concept of "which application called this." Populated from static per-connector config, not
  invented per-event; `mcp_tool_used` is always `None` from this connector (MCP tool attribution comes
  from `docs/01-domain/mcp.md`'s own governance path, not the model-provider usage report).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

from backend.connectors.base import AIUsageEvent, Connector, HTTPClient, UrllibHTTPClient, UserDirectory

ANTHROPIC_API_VERSION = "2023-06-01"
USAGE_REPORT_PATH = "/v1/organizations/usage_report/messages"


class CostEstimator(Protocol):
    def estimate(self, model: str, prompt_tokens: int, completion_tokens: int) -> Decimal: ...


class ApproximateCatalogCostEstimator:
    """Estimates cost from the same approximate per-model catalog `simulation/` uses.

    Deliberately reuses `simulation.generators.models.MODEL_CATALOG` rather than a second hardcoded
    price table — see the module docstring. Raises rather than silently returning 0 for an unpriced
    model, since a silent-zero cost would corrupt metering/chargeback without anyone noticing.
    """

    def __init__(self) -> None:
        from simulation.generators.models import MODEL_CATALOG

        self._pricing: dict[str, tuple[Decimal, Decimal]] = {
            model_id: (Decimal(str(input_per_1m)), Decimal(str(output_per_1m)))
            for model_id, _provider, _name, input_per_1m, output_per_1m, _ctx, _approved in MODEL_CATALOG
        }

    def estimate(self, model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
        try:
            input_per_1m, output_per_1m = self._pricing[model]
        except KeyError:
            raise KeyError(
                f"no approximate pricing on record for model={model!r}; add it to "
                "simulation/generators/models.py's MODEL_CATALOG before ingesting its usage"
            ) from None
        return (Decimal(prompt_tokens) * input_per_1m + Decimal(completion_tokens) * output_per_1m) / Decimal(
            1_000_000
        )


@dataclass(frozen=True)
class AnthropicAdminConnectorConfig:
    tenant_id: str
    application_id: str
    default_data_classification: str = "internal"
    base_url: str = "https://api.anthropic.com"
    api_key_owner: Mapping[str, str] = field(default_factory=dict)  # api_key_id -> user_id


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

    def pull(self, since: datetime, until: datetime | None = None) -> Iterator[AIUsageEvent]:
        until = until or datetime.now(timezone.utc)
        page: str | None = None
        while True:
            params = {
                "starting_at": since.isoformat(),
                "ending_at": until.isoformat(),
                "group_by[0]": "workspace_id",
                "group_by[1]": "api_key_id",
                "group_by[2]": "model",
            }
            if page:
                params["page"] = page
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
        api_key_id = row.get("api_key_id", "")
        workspace_id = row.get("workspace_id", "")
        user_id = self._config.api_key_owner.get(api_key_id) or f"workspace:{workspace_id}"

        prompt_tokens = (
            row.get("uncached_input_tokens", 0)
            + row.get("cache_creation_input_tokens", 0)
            + row.get("cache_read_input_tokens", 0)
        )
        completion_tokens = row.get("output_tokens", 0)
        model = row.get("model", "unknown")

        return AIUsageEvent(
            event_id=f"anthropic-admin:{bucket['starting_at']}:{workspace_id}:{api_key_id}:{model}",
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
