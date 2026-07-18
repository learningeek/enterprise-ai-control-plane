"""Azure OpenAI connector.

Pulls per-request usage from an Azure Log Analytics workspace that the Azure OpenAI resource's diagnostic
settings export to, and maps it onto `AIUsageEvent` (specs/event-schema.md), per the Tier 1 pattern in
docs/02-architecture/connector-framework.md.

**This connector's integration shape is genuinely different from `anthropic_admin.py`/`openai_usage.py`,
not just a copy with renamed fields** — worth reading before assuming symmetry:

- Azure OpenAI has no equivalent of Anthropic's/OpenAI's aggregate usage-report REST endpoint. Usage data
  comes from whatever the org's Azure Monitor **diagnostic settings** export for the Azure OpenAI
  resource, queried via the Log Analytics Query API
  (`POST https://api.loganalytics.io/v1/workspaces/{workspace_id}/query` with a KQL query body) — a POST
  carrying a query string, not a paginated GET.
- **The exact raw log schema depends entirely on the org's diagnostic settings configuration** (which log
  categories are enabled, whether export lands in the legacy `AzureDiagnostics` table or a
  resource-specific table) — unlike Anthropic's/OpenAI's nominally-stable public usage-report shape, this
  isn't something a connector can assume correctly without seeing a real org's setup. So rather than
  guess a specific table/column layout and calling it done, this connector defines a **required output
  contract** instead: `kql_query_template` must `project` these columns, however the org's actual schema
  maps to them — `time_generated`, `deployment_name`, `prompt_tokens`, `completion_tokens`, `status_code`,
  `correlation_id`, and optionally `end_user` / `duration_ms`. `DEFAULT_KQL_QUERY_TEMPLATE` below is an
  illustrative starting point against the commonly-documented `AzureDiagnostics` table — explicitly not
  guaranteed to match a given org's export configuration, and should be replaced via
  `AzureOpenAIConnectorConfig.kql_query_template` once it is.
- **Per-request granularity, not aggregate buckets.** Diagnostic logs are one row per request, so unlike
  the other two connectors this one *can* report a real `latency_ms` (from an optional `duration_ms`
  column, if the org's schema captures request duration) and a real `outcome` derived from `status_code`
  (2xx -> success; 400 -> blocked, since Azure OpenAI's content filtering commonly surfaces as HTTP 400 —
  not distinguished here from any other 400 without the org's query surfacing the specific content-filter
  error code; anything else -> error) — instead of the aggregate-bucket "always success, always
  `latency_ms=0`" assumption the other two connectors make because their source APIs genuinely have no
  per-request data.
- **No pagination.** The Log Analytics Query API's synchronous endpoint returns the full matching result
  set in one response (subject to a row/size cap). A window likely to exceed that cap should be split
  into multiple narrower `pull()` calls by the caller — not handled internally here (see `TODO`).
- **Deployment name, not a model version string, is the grouping key.** An org names an Azure OpenAI
  deployment arbitrarily (e.g. `"gpt4o-prod"`), independent of the underlying model. `ModelIdResolver` is
  keyed by `deployment_name -> catalog model_id` here, not by a raw vendor model string like the other
  two connectors use.
- **Generally no per-human-user field.** Azure resource logs report the calling identity (a service
  principal / API key), not an enterprise employee, unless the calling application explicitly passes the
  OpenAI API's optional `user` field *and* the org's diagnostic export surfaces it as `end_user`. Falls
  back to a synthetic `deployment:<name>` id otherwise, which then correctly fails department resolution
  via `UserDirectory` rather than guessing.
- **`request_cost` is estimated**, same approach and caveat as the other two connectors — Azure's actual
  billed cost lives in Azure Cost Management, a third, separate API this connector does not join (see
  `TODO`).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

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

QUERY_PATH_TEMPLATE = "/v1/workspaces/{workspace_id}/query"

# Illustrative only — verify against the org's actual diagnostic settings export before use. Must project
# exactly: time_generated, deployment_name, prompt_tokens, completion_tokens, status_code, correlation_id
# (optionally end_user, duration_ms). See module docstring.
DEFAULT_KQL_QUERY_TEMPLATE = """
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COGNITIVESERVICES" and Category == "RequestResponse"
| where TimeGenerated >= datetime({since_iso}) and TimeGenerated < datetime({until_iso})
| project
    time_generated = TimeGenerated,
    deployment_name = tostring(properties_deploymentName_s),
    prompt_tokens = toint(properties_promptTokens_d),
    completion_tokens = toint(properties_completionTokens_d),
    status_code = toint(ResultSignature),
    correlation_id = tostring(CorrelationId),
    duration_ms = toint(DurationMs)
""".strip()


def _parse_log_analytics_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class AzureOpenAIConnectorConfig:
    tenant_id: str
    application_id: str
    workspace_id: str
    default_data_classification: str = "internal"
    base_url: str = "https://api.loganalytics.io"
    deployment_owner: Mapping[str, str] = field(default_factory=dict)  # deployment_name -> user_id
    deployment_model_id_map: Mapping[str, str] = field(default_factory=dict)  # deployment_name -> catalog model_id
    kql_query_template: str = DEFAULT_KQL_QUERY_TEMPLATE


class AzureOpenAIConnector(Connector):
    """Tier 1 connector for Azure OpenAI. See module docstring — integration shape genuinely differs
    from `anthropic_admin.py`/`openai_usage.py`; read before assuming symmetry.

    TODO: join Azure Cost Management for actual dollar cost instead of the approximate catalog estimate.
    TODO: chunk `pull()` internally for windows likely to exceed the Log Analytics single-query row/size
    cap, once a real org's row volume is known.
    """

    provider = "Azure OpenAI"

    def __init__(
        self,
        aad_bearer_token: str,
        config: AzureOpenAIConnectorConfig,
        user_directory: UserDirectory,
        cost_estimator: CostEstimator | None = None,
        http_client: HTTPClient | None = None,
    ) -> None:
        self._aad_bearer_token = aad_bearer_token
        self._config = config
        self._user_directory = user_directory
        self._cost_estimator = cost_estimator or ApproximateCatalogCostEstimator()
        self._http = http_client or UrllibHTTPClient()
        self._model_resolver = ModelIdResolver(config.deployment_model_id_map)

    def pull(self, since: datetime, until: datetime | None = None) -> Iterator[AIUsageEvent]:
        until = until or datetime.now(timezone.utc)
        query = self._config.kql_query_template.format(since_iso=since.isoformat(), until_iso=until.isoformat())
        path = QUERY_PATH_TEMPLATE.format(workspace_id=self._config.workspace_id)
        body = self._http.post(
            f"{self._config.base_url}{path}",
            json_body={"query": query},
            headers={"Authorization": f"Bearer {self._aad_bearer_token}"},
        )
        for row in self._rows(body):
            yield self._to_event(row)

    @staticmethod
    def _rows(body: dict) -> Iterator[dict[str, Any]]:
        """Log Analytics returns {"tables": [{"columns": [...], "rows": [[...], ...]}]} — flatten to dicts."""
        for table in body.get("tables", []):
            column_names = [column["name"] for column in table.get("columns", [])]
            for raw_row in table.get("rows", []):
                yield dict(zip(column_names, raw_row))

    def _to_event(self, row: dict[str, Any]) -> AIUsageEvent:
        deployment_name = row.get("deployment_name", "")
        user_id = (
            self._config.deployment_owner.get(deployment_name)
            or row.get("end_user")
            or f"deployment:{deployment_name}"
        )

        prompt_tokens = row.get("prompt_tokens") or 0
        completion_tokens = row.get("completion_tokens") or 0
        model = self._model_resolver.resolve(deployment_name)

        status_code = row.get("status_code") or 0
        if 200 <= status_code < 300:
            outcome = "success"
        elif status_code == 400:
            outcome = "blocked"  # commonly Azure OpenAI content filtering — see module docstring
        else:
            outcome = "error"

        correlation_id = row.get("correlation_id") or f"{row.get('time_generated')}:{deployment_name}:{user_id}"

        return AIUsageEvent(
            event_id=f"azure-openai:{correlation_id}",
            timestamp=_parse_log_analytics_timestamp(row["time_generated"]),
            tenant_id=self._config.tenant_id,
            user_id=user_id,
            department=self._user_directory.department_for(user_id),
            application_id=self._config.application_id,
            provider=self.provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=row.get("duration_ms") or 0,  # real per-request value, when the org's schema has it
            request_cost=self._cost_estimator.estimate(model, prompt_tokens, completion_tokens),
            data_classification=self._config.default_data_classification,
            mcp_tool_used=None,
            outcome=outcome,
        )
