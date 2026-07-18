from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.connectors.anthropic_admin import (
    AnthropicAdminConnector,
    AnthropicAdminConnectorConfig,
    ApproximateCatalogCostEstimator,
)
from backend.connectors.base import InMemoryUserDirectory, ListSink

SINCE = datetime(2026, 6, 1, tzinfo=timezone.utc)
UNTIL = datetime(2026, 7, 1, tzinfo=timezone.utc)


class FakeHTTPClient:
    """Serves two pages of one usage bucket each, keyed off the `page` param."""

    def __init__(self):
        self.requests: list[dict] = []

    def get(self, url, *, params, headers):
        self.requests.append({"url": url, "params": dict(params), "headers": dict(headers)})
        assert headers["x-api-key"] == "sk-ant-admin-test"
        page = params.get("page")
        if page is None:
            return {
                "data": [
                    {
                        "starting_at": "2026-06-15T00:00:00Z",
                        "results": [
                            {
                                "workspace_id": "wk_eng",
                                "api_key_id": "key_alice",
                                "model": "anthropic-claude-sonnet-4",
                                "uncached_input_tokens": 800,
                                "cache_creation_input_tokens": 0,
                                "cache_read_input_tokens": 200,
                                "output_tokens": 500,
                            }
                        ],
                    }
                ],
                "next_page": "page-2",
            }
        if page == "page-2":
            return {
                "data": [
                    {
                        "starting_at": "2026-06-16T00:00:00Z",
                        "results": [
                            {
                                "workspace_id": "wk_shared",
                                "api_key_id": "key_unmapped",
                                "model": "anthropic-claude-haiku-4",
                                "uncached_input_tokens": 100,
                                "cache_creation_input_tokens": 0,
                                "cache_read_input_tokens": 0,
                                "output_tokens": 50,
                            }
                        ],
                    }
                ],
                "next_page": None,
            }
        raise AssertionError(f"unexpected page {page!r}")


@pytest.fixture
def connector():
    config = AnthropicAdminConnectorConfig(
        tenant_id="acme-corp",
        application_id="claude-code",
        api_key_owner={"key_alice": "U000001"},
    )
    user_directory = InMemoryUserDirectory({"U000001": "Engineering", "workspace:wk_shared": "Unknown"})
    return AnthropicAdminConnector(
        admin_api_key="sk-ant-admin-test",
        config=config,
        user_directory=user_directory,
        http_client=FakeHTTPClient(),
    )


def test_pull_follows_pagination_and_maps_all_rows(connector):
    events = list(connector.pull(SINCE, UNTIL))
    assert len(events) == 2
    assert connector._http.requests[1]["params"]["page"] == "page-2"


def test_pull_maps_known_api_key_to_configured_user(connector):
    events = list(connector.pull(SINCE, UNTIL))
    alice_event = next(e for e in events if e.user_id == "U000001")
    assert alice_event.department == "Engineering"
    assert alice_event.prompt_tokens == 800 + 0 + 200  # uncached + cache_creation + cache_read
    assert alice_event.completion_tokens == 500
    assert alice_event.model == "anthropic-claude-sonnet-4"
    assert alice_event.provider == "Anthropic"
    assert alice_event.application_id == "claude-code"
    assert alice_event.tenant_id == "acme-corp"
    assert alice_event.outcome == "success"
    assert alice_event.mcp_tool_used is None
    assert alice_event.latency_ms == 0  # not reported by the aggregate usage API


def test_pull_falls_back_to_synthetic_workspace_user_for_unmapped_api_key(connector):
    events = list(connector.pull(SINCE, UNTIL))
    shared_event = next(e for e in events if e.user_id == "workspace:wk_shared")
    assert shared_event.department == "Unknown"


def test_pull_raises_when_workspace_user_is_not_in_directory():
    config = AnthropicAdminConnectorConfig(tenant_id="acme-corp", application_id="claude-code")
    empty_directory = InMemoryUserDirectory({})
    connector = AnthropicAdminConnector(
        admin_api_key="sk-ant-admin-test",
        config=config,
        user_directory=empty_directory,
        http_client=FakeHTTPClient(),
    )
    with pytest.raises(KeyError):
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


def test_cost_estimator_matches_shared_pricing_catalog():
    estimator = ApproximateCatalogCostEstimator()
    cost = estimator.estimate("anthropic-claude-sonnet-4", prompt_tokens=1000, completion_tokens=500)
    assert cost == Decimal("1000") * Decimal("3.00") / Decimal("1_000_000") + Decimal("500") * Decimal(
        "15.00"
    ) / Decimal("1_000_000")


def test_cost_estimator_raises_for_unpriced_model():
    estimator = ApproximateCatalogCostEstimator()
    with pytest.raises(KeyError, match="no-such-model"):
        estimator.estimate("no-such-model", prompt_tokens=1, completion_tokens=1)
