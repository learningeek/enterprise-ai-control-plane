from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.connectors.base import InMemoryUserDirectory, ListSink, ModelIdResolver
from backend.connectors.openai_usage import OpenAIUsageConnector, OpenAIUsageConnectorConfig

SINCE = datetime(2026, 6, 1, tzinfo=timezone.utc)
UNTIL = datetime(2026, 7, 1, tzinfo=timezone.utc)

MODEL_ID_MAP = {
    "gpt-4o-2024-08-06": "openai-gpt-4o",
    "gpt-4o-mini-2024-07-18": "openai-gpt-4o-mini",
}


class FakeHTTPClient:
    """Serves two pages of one usage bucket each, keyed off the `page` param."""

    def __init__(self):
        self.requests: list[dict] = []

    def get(self, url, *, params, headers):
        self.requests.append({"url": url, "params": dict(params), "headers": dict(headers)})
        assert headers["Authorization"] == "Bearer sk-openai-admin-test"
        page = params.get("page")
        if page is None:
            return {
                "data": [
                    {
                        "start_time": 1780000000,
                        "results": [
                            {
                                "project_id": "proj_eng",
                                "user_id": "user_alice_openai",
                                "api_key_id": "key_1",
                                "model": "gpt-4o-2024-08-06",
                                "input_tokens": 1000,
                                "input_cached_tokens": 200,
                                "output_tokens": 400,
                            }
                        ],
                    }
                ],
                "has_more": True,
                "next_page": "page-2",
            }
        if page == "page-2":
            return {
                "data": [
                    {
                        "start_time": 1780086400,
                        "results": [
                            {
                                "project_id": "proj_shared",
                                "user_id": None,
                                "api_key_id": "key_shared",
                                "model": "gpt-4o-mini-2024-07-18",
                                "input_tokens": 100,
                                "input_cached_tokens": 0,
                                "output_tokens": 50,
                            }
                        ],
                    }
                ],
                "has_more": False,
                "next_page": None,
            }
        raise AssertionError(f"unexpected page {page!r}")


@pytest.fixture
def connector():
    config = OpenAIUsageConnectorConfig(
        tenant_id="acme-corp",
        application_id="internal-copilot",
        openai_user_owner={"user_alice_openai": "U000001"},
        model_id_map=MODEL_ID_MAP,
    )
    user_directory = InMemoryUserDirectory({"U000001": "Engineering", "project:proj_shared": "Unknown"})
    return OpenAIUsageConnector(
        admin_api_key="sk-openai-admin-test",
        config=config,
        user_directory=user_directory,
        http_client=FakeHTTPClient(),
    )


def test_pull_follows_pagination_and_maps_all_rows(connector):
    events = list(connector.pull(SINCE, UNTIL))
    assert len(events) == 2
    assert connector._http.requests[1]["params"]["page"] == "page-2"


def test_pull_maps_known_openai_user_to_configured_user(connector):
    events = list(connector.pull(SINCE, UNTIL))
    alice_event = next(e for e in events if e.user_id == "U000001")
    assert alice_event.department == "Engineering"
    assert alice_event.prompt_tokens == 1000  # input_tokens already includes cached — not added again
    assert alice_event.completion_tokens == 400
    assert alice_event.model == "openai-gpt-4o"
    assert alice_event.provider == "OpenAI"
    assert alice_event.application_id == "internal-copilot"
    assert alice_event.tenant_id == "acme-corp"
    assert alice_event.outcome == "success"
    assert alice_event.mcp_tool_used is None
    assert alice_event.latency_ms == 0  # not reported by the aggregate usage API


def test_pull_falls_back_to_synthetic_project_user_when_user_id_is_null(connector):
    events = list(connector.pull(SINCE, UNTIL))
    shared_event = next(e for e in events if e.user_id == "project:proj_shared")
    assert shared_event.department == "Unknown"
    assert shared_event.model == "openai-gpt-4o-mini"


def test_pull_raises_when_project_user_is_not_in_directory():
    config = OpenAIUsageConnectorConfig(
        tenant_id="acme-corp", application_id="internal-copilot", model_id_map=MODEL_ID_MAP
    )
    empty_directory = InMemoryUserDirectory({})
    connector = OpenAIUsageConnector(
        admin_api_key="sk-openai-admin-test",
        config=config,
        user_directory=empty_directory,
        http_client=FakeHTTPClient(),
    )
    with pytest.raises(KeyError, match="project:proj_eng"):
        list(connector.pull(SINCE, UNTIL))


def test_pull_raises_when_vendor_model_is_not_in_model_id_map(connector):
    connector._model_resolver = ModelIdResolver({})
    with pytest.raises(KeyError, match="gpt-4o-2024-08-06"):
        list(connector.pull(SINCE, UNTIL))


def test_event_id_is_deterministic_for_the_same_underlying_row(connector):
    first_pull = list(connector.pull(SINCE, UNTIL))
    second_pull = list(connector.pull(SINCE, UNTIL))
    assert [e.event_id for e in first_pull] == [e.event_id for e in second_pull]


def test_sync_pulls_then_emits(connector):
    sink = ListSink()
    count = connector.sync(sink, SINCE, UNTIL)
    assert count == 2
    assert len(sink.events) == 2
