from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.connectors.azure_openai import AzureOpenAIConnector, AzureOpenAIConnectorConfig
from backend.connectors.base import InMemoryUserDirectory, ListSink

SINCE = datetime(2026, 6, 1, tzinfo=timezone.utc)
UNTIL = datetime(2026, 7, 1, tzinfo=timezone.utc)

DEPLOYMENT_MODEL_ID_MAP = {
    "gpt4o-prod": "openai-gpt-4o",
    "gpt4o-mini-dev": "openai-gpt-4o-mini",
}

COLUMNS = [
    {"name": "time_generated"},
    {"name": "deployment_name"},
    {"name": "prompt_tokens"},
    {"name": "completion_tokens"},
    {"name": "status_code"},
    {"name": "correlation_id"},
    {"name": "duration_ms"},
]

ROWS = [
    ["2026-06-15T10:00:00Z", "gpt4o-prod", 800, 400, 200, "corr-1", 1200],  # success, known deployment owner
    ["2026-06-15T10:05:00Z", "gpt4o-mini-dev", 50, 0, 400, "corr-2", 300],  # blocked, unmapped -> synthetic user
    ["2026-06-15T10:10:00Z", "gpt4o-prod", 20, 0, 500, "corr-3", 5000],  # error
]


class FakeHTTPClient:
    def __init__(self):
        self.calls: list[dict] = []

    def post(self, url, *, json_body, headers):
        self.calls.append({"url": url, "json_body": dict(json_body), "headers": dict(headers)})
        assert headers["Authorization"] == "Bearer aad-token-test"
        assert "query" in json_body
        return {"tables": [{"columns": COLUMNS, "rows": ROWS}]}


@pytest.fixture
def connector():
    config = AzureOpenAIConnectorConfig(
        tenant_id="acme-corp",
        application_id="internal-copilot",
        workspace_id="ws-123",
        deployment_owner={"gpt4o-prod": "U000001"},
        deployment_model_id_map=DEPLOYMENT_MODEL_ID_MAP,
    )
    user_directory = InMemoryUserDirectory(
        {"U000001": "Engineering", "deployment:gpt4o-mini-dev": "Unknown"}
    )
    return AzureOpenAIConnector(
        aad_bearer_token="aad-token-test",
        config=config,
        user_directory=user_directory,
        http_client=FakeHTTPClient(),
    )


def test_pull_posts_kql_query_to_workspace_endpoint(connector):
    list(connector.pull(SINCE, UNTIL))
    assert len(connector._http.calls) == 1
    assert connector._http.calls[0]["url"] == "https://api.loganalytics.io/v1/workspaces/ws-123/query"


def test_pull_maps_all_rows(connector):
    events = list(connector.pull(SINCE, UNTIL))
    assert len(events) == 3


def test_pull_derives_real_latency_and_success_outcome_from_status_code(connector):
    events = list(connector.pull(SINCE, UNTIL))
    success_event = next(e for e in events if e.event_id.endswith("corr-1"))
    assert success_event.outcome == "success"
    assert success_event.latency_ms == 1200  # real per-request value, unlike the aggregate-bucket connectors
    assert success_event.user_id == "U000001"
    assert success_event.department == "Engineering"
    assert success_event.model == "openai-gpt-4o"
    assert success_event.prompt_tokens == 800
    assert success_event.completion_tokens == 400
    assert success_event.provider == "Azure OpenAI"


def test_pull_maps_400_status_to_blocked_outcome_and_falls_back_to_synthetic_user(connector):
    events = list(connector.pull(SINCE, UNTIL))
    blocked_event = next(e for e in events if e.event_id.endswith("corr-2"))
    assert blocked_event.outcome == "blocked"
    assert blocked_event.user_id == "deployment:gpt4o-mini-dev"
    assert blocked_event.department == "Unknown"
    assert blocked_event.model == "openai-gpt-4o-mini"


def test_pull_maps_other_status_codes_to_error_outcome(connector):
    events = list(connector.pull(SINCE, UNTIL))
    error_event = next(e for e in events if e.event_id.endswith("corr-3"))
    assert error_event.outcome == "error"


def test_pull_raises_when_deployment_is_not_in_model_id_map():
    config = AzureOpenAIConnectorConfig(
        tenant_id="acme-corp",
        application_id="internal-copilot",
        workspace_id="ws-123",
        deployment_owner={"gpt4o-prod": "U000001"},
    )
    user_directory = InMemoryUserDirectory({"U000001": "Engineering"})
    connector = AzureOpenAIConnector(
        aad_bearer_token="aad-token-test",
        config=config,
        user_directory=user_directory,
        http_client=FakeHTTPClient(),
    )
    with pytest.raises(KeyError, match="gpt4o-prod"):
        list(connector.pull(SINCE, UNTIL))


def test_pull_raises_when_synthetic_user_is_not_in_directory(connector):
    connector._user_directory = InMemoryUserDirectory({"U000001": "Engineering"})  # missing the mini-dev fallback
    with pytest.raises(KeyError, match="deployment:gpt4o-mini-dev"):
        list(connector.pull(SINCE, UNTIL))


def test_event_id_is_deterministic_for_the_same_underlying_row(connector):
    first_pull = list(connector.pull(SINCE, UNTIL))
    second_pull = list(connector.pull(SINCE, UNTIL))
    assert [e.event_id for e in first_pull] == [e.event_id for e in second_pull]


def test_sync_pulls_then_emits(connector):
    sink = ListSink()
    count = connector.sync(sink, SINCE, UNTIL)
    assert count == 3
    assert len(sink.events) == 3
