from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.connectors.anthropic_admin import (
    AnthropicAdminConnector,
    AnthropicAdminConnectorConfig,
    ApproximateCatalogCostEstimator,
)
from backend.connectors.base import InMemoryUserDirectory, ListSink, ModelIdResolver

SINCE = datetime(2026, 6, 1, tzinfo=timezone.utc)
UNTIL = datetime(2026, 7, 1, tzinfo=timezone.utc)


class FakeHTTPClient:
    """Serves two pages of one usage bucket each, keyed off the `page` param."""

    def __init__(self):
        self.requests: list[dict] = []

    def get(self, url, *, params, headers):
        params = list(params)
        self.requests.append({"url": url, "params": params, "headers": dict(headers)})
        params_by_key = dict(params)
        assert headers["x-api-key"] == "sk-ant-admin-test"
        page = params_by_key.get("page")
        if page is None:
            return {
                "data": [
                    {
                        "starting_at": "2026-06-15T00:00:00Z",
                        "results": [
                            {
                                "workspace_id": "wk_eng",
                                "api_key_id": "key_alice",
                                "model": "claude-sonnet-4-20250514",
                                "uncached_input_tokens": 800,
                                "cache_creation": {
                                    "ephemeral_1h_input_tokens": 0,
                                    "ephemeral_5m_input_tokens": 0,
                                },
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
                                "model": "claude-haiku-4-20250514",
                                "uncached_input_tokens": 100,
                                "cache_creation": {
                                    "ephemeral_1h_input_tokens": 0,
                                    "ephemeral_5m_input_tokens": 0,
                                },
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
        model_id_map={
            "claude-sonnet-4-20250514": "anthropic-claude-sonnet-4",
            "claude-haiku-4-20250514": "anthropic-claude-haiku-4",
        },
    )
    user_directory = InMemoryUserDirectory({"U000001": "Engineering", "api_key:key_unmapped": "Unknown"})
    return AnthropicAdminConnector(
        admin_api_key="sk-ant-admin-test",
        config=config,
        user_directory=user_directory,
        http_client=FakeHTTPClient(),
    )


def test_pull_follows_pagination_and_maps_all_rows(connector):
    events = list(connector.pull(SINCE, UNTIL))
    assert len(events) == 2
    assert dict(connector._http.requests[1]["params"])["page"] == "page-2"


def test_pull_encodes_group_by_as_repeated_keys_not_indexed(connector):
    """group_by[]=x repeated per official docs, not group_by[0]=x/group_by[1]=y (a real bug this fixes)."""
    list(connector.pull(SINCE, UNTIL))
    group_by_values = [value for key, value in connector._http.requests[0]["params"] if key == "group_by[]"]
    assert group_by_values == ["workspace_id", "api_key_id", "model"]


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


def test_pull_falls_back_to_synthetic_api_key_user_for_unmapped_key(connector):
    events = list(connector.pull(SINCE, UNTIL))
    unmapped_event = next(e for e in events if e.user_id == "api_key:key_unmapped")
    assert unmapped_event.department == "Unknown"


def test_pull_preserves_per_api_key_granularity_even_when_unmapped():
    """Two different unmapped keys in the same workspace must not collapse into one synthetic id."""
    config = AnthropicAdminConnectorConfig(
        tenant_id="acme-corp",
        application_id="claude-code",
        model_id_map={
            "claude-sonnet-4-20250514": "anthropic-claude-sonnet-4",
            "claude-haiku-4-20250514": "anthropic-claude-haiku-4",
        },
    )
    directory = InMemoryUserDirectory({"api_key:key_alice": "Unknown", "api_key:key_unmapped": "Unknown"})
    connector = AnthropicAdminConnector(
        admin_api_key="sk-ant-admin-test",
        config=config,
        user_directory=directory,
        http_client=FakeHTTPClient(),
    )
    events = list(connector.pull(SINCE, UNTIL))
    assert {e.user_id for e in events} == {"api_key:key_alice", "api_key:key_unmapped"}


def test_pull_raises_when_api_key_user_is_not_in_directory():
    config = AnthropicAdminConnectorConfig(
        tenant_id="acme-corp",
        application_id="claude-code",
        model_id_map={
            "claude-sonnet-4-20250514": "anthropic-claude-sonnet-4",
            "claude-haiku-4-20250514": "anthropic-claude-haiku-4",
        },
    )
    empty_directory = InMemoryUserDirectory({})
    connector = AnthropicAdminConnector(
        admin_api_key="sk-ant-admin-test",
        config=config,
        user_directory=empty_directory,
        http_client=FakeHTTPClient(),
    )
    with pytest.raises(KeyError, match="api_key:key_alice"):
        list(connector.pull(SINCE, UNTIL))


def test_pull_raises_when_vendor_model_is_not_in_model_id_map(connector):
    connector._config = AnthropicAdminConnectorConfig(
        tenant_id="acme-corp",
        application_id="claude-code",
        api_key_owner={"key_alice": "U000001"},
    )
    connector._model_resolver = ModelIdResolver({})
    with pytest.raises(KeyError, match="claude-sonnet-4-20250514"):
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


def test_prompt_tokens_sums_nested_cache_creation_sub_fields():
    """Regression test: an earlier version assumed a flat cache_creation_input_tokens field that no
    longer exists in the real API — cache_creation is a nested object with two sub-fields, and silently
    reading the old flat key via .get(key, 0) would undercount prompt_tokens/cost without erroring."""

    class SingleRowHTTPClient:
        def get(self, url, *, params, headers):
            return {
                "data": [
                    {
                        "starting_at": "2026-06-15T00:00:00Z",
                        "results": [
                            {
                                "workspace_id": "wk_eng",
                                "api_key_id": "key_alice",
                                "model": "claude-sonnet-4-20250514",
                                "uncached_input_tokens": 800,
                                "cache_creation": {
                                    "ephemeral_1h_input_tokens": 50,
                                    "ephemeral_5m_input_tokens": 30,
                                },
                                "cache_read_input_tokens": 200,
                                "output_tokens": 500,
                            }
                        ],
                    }
                ],
                "next_page": None,
            }

    config = AnthropicAdminConnectorConfig(
        tenant_id="acme-corp",
        application_id="claude-code",
        api_key_owner={"key_alice": "U000001"},
        model_id_map={"claude-sonnet-4-20250514": "anthropic-claude-sonnet-4"},
    )
    connector = AnthropicAdminConnector(
        admin_api_key="sk-ant-admin-test",
        config=config,
        user_directory=InMemoryUserDirectory({"U000001": "Engineering"}),
        http_client=SingleRowHTTPClient(),
    )
    event = next(iter(connector.pull(SINCE, UNTIL)))
    assert event.prompt_tokens == 800 + (50 + 30) + 200


def test_handles_explicit_null_api_key_id_without_crashing():
    """Regression test: Console/Workbench playground usage has api_key_id: null (present, not missing) —
    row.get("api_key_id", "") doesn't apply its default for an explicit null, only a missing key."""

    class PlaygroundUsageHTTPClient:
        def get(self, url, *, params, headers):
            return {
                "data": [
                    {
                        "starting_at": "2026-06-15T00:00:00Z",
                        "results": [
                            {
                                "workspace_id": None,
                                "api_key_id": None,
                                "model": "claude-sonnet-4-20250514",
                                "uncached_input_tokens": 10,
                                "cache_creation": {"ephemeral_1h_input_tokens": 0, "ephemeral_5m_input_tokens": 0},
                                "cache_read_input_tokens": 0,
                                "output_tokens": 5,
                            }
                        ],
                    }
                ],
                "next_page": None,
            }

    config = AnthropicAdminConnectorConfig(
        tenant_id="acme-corp",
        application_id="claude-code",
        model_id_map={"claude-sonnet-4-20250514": "anthropic-claude-sonnet-4"},
    )
    connector = AnthropicAdminConnector(
        admin_api_key="sk-ant-admin-test",
        config=config,
        user_directory=InMemoryUserDirectory({"api_key:": "Unknown"}),
        http_client=PlaygroundUsageHTTPClient(),
    )
    event = next(iter(connector.pull(SINCE, UNTIL)))
    assert event.user_id == "api_key:"  # not the "api_key:None" bug an earlier version would have produced


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
