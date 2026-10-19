"""Parses real, vendor-published example responses (see fixtures/README.md) through the actual
connectors — not another layer of this project's own guesses about response shape. This is the closest
substitute available in this environment to testing against a live account: these are authentic
examples copied verbatim from each vendor's current public docs, not hand-rolled by anyone on this
project.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.connectors.anthropic_admin import AnthropicAdminConnector, AnthropicAdminConnectorConfig
from backend.connectors.base import InMemoryUserDirectory
from backend.connectors.openai_usage import OpenAIUsageConnector, OpenAIUsageConnectorConfig

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SINCE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


class _StaticHTTPClient:
    """Returns the same fixture response for the first page, empty thereafter (stops pagination)."""

    def __init__(self, first_response: dict):
        self._first_response = first_response
        self._served = False

    def get(self, url, *, params, headers):
        if self._served:
            return {"data": [], "has_more": False, "next_page": None}
        self._served = True
        return self._first_response


# --- Anthropic: real example from platform.claude.com's API reference page -------------------------


def test_anthropic_real_example_parses_into_a_correct_event():
    fixture = _load_fixture("anthropic_usage_report_example.json")
    config = AnthropicAdminConnectorConfig(
        tenant_id="acme-corp",
        application_id="claude-code",
        # "claude-opus-5-5" is the literal model string in the real example; map it so resolution
        # succeeds — not a claim that this exact snapshot is in simulation/'s MODEL_CATALOG.
        model_id_map={"claude-opus-5-5": "anthropic-claude-opus-4"},
    )
    connector = AnthropicAdminConnector(
        admin_api_key="sk-ant-admin-test",
        config=config,
        user_directory=InMemoryUserDirectory({"api_key:apikey_01Rj2N8SVvo6BePZj99NhmiT": "Engineering"}),
        http_client=_StaticHTTPClient(fixture),
    )

    events = list(connector.pull(since=SINCE))

    assert len(events) == 1
    event = events[0]
    # uncached (1500) + cache_creation's two ephemeral sub-fields (0 + 0) + cache_read (200)
    assert event.prompt_tokens == 1500 + 0 + 200
    assert event.completion_tokens == 500
    assert event.model == "anthropic-claude-opus-4"
    assert event.user_id == "api_key:apikey_01Rj2N8SVvo6BePZj99NhmiT"
    assert event.department == "Engineering"
    assert event.timestamp.isoformat() == "2025-08-01T00:00:00+00:00"


def test_anthropic_real_example_fails_loudly_on_an_unmapped_model():
    """The real example's model ("claude-opus-5-5") isn't in simulation/'s catalog by default — confirms
    an authentic vendor response for a model this connector hasn't been configured for still fails
    loudly rather than silently miscounting cost, exactly as it would for a hand-rolled test row."""
    fixture = _load_fixture("anthropic_usage_report_example.json")
    config = AnthropicAdminConnectorConfig(tenant_id="acme-corp", application_id="claude-code")
    connector = AnthropicAdminConnector(
        admin_api_key="sk-ant-admin-test",
        config=config,
        user_directory=InMemoryUserDirectory({}),
        http_client=_StaticHTTPClient(fixture),
    )
    with pytest.raises(KeyError, match="claude-opus-5-5"):
        list(connector.pull(since=SINCE))


# --- OpenAI: real example from developers.openai.com's cookbook, ungrouped -------------------------


def test_openai_real_ungrouped_example_has_every_dimension_null():
    """Sanity-check the fixture itself matches what OpenAI's docs actually show, before testing what the
    connector does with it — every grouping field is null because this example isn't grouped by anything."""
    fixture = _load_fixture("openai_usage_completions_example.json")
    result = fixture["data"][0]["results"][0]
    assert result["project_id"] is None
    assert result["user_id"] is None
    assert result["api_key_id"] is None
    assert result["model"] is None


def test_openai_real_ungrouped_example_fails_loudly_rather_than_crashing_on_null_model():
    """Regression test for a bug this exact real fixture caught: row.get("model", "unknown") does not
    apply its default to an explicit null, only a missing key. Confirms the fix (.get("model") or
    "unknown") turns a real ungrouped response into a clear 'unmapped model' KeyError instead of
    something more confusing (e.g. a crash inside ModelIdResolver on a None key, or a non-obvious
    downstream error)."""
    fixture = _load_fixture("openai_usage_completions_example.json")
    config = OpenAIUsageConnectorConfig(tenant_id="acme-corp", application_id="internal-copilot")
    connector = OpenAIUsageConnector(
        admin_api_key="sk-openai-admin-test",
        config=config,
        user_directory=InMemoryUserDirectory({}),
        http_client=_StaticHTTPClient(fixture),
    )
    with pytest.raises(KeyError, match="unknown"):
        list(connector.pull(since=SINCE))


def test_openai_real_ungrouped_example_falls_back_to_synthetic_user_without_crashing():
    """With a model_id_map covering the "unknown" fallback, confirms every null grouping field in this
    real example resolves to the correct synthetic api_key: fallback rather than "api_key:None"."""
    fixture = _load_fixture("openai_usage_completions_example.json")
    config = OpenAIUsageConnectorConfig(
        tenant_id="acme-corp", application_id="internal-copilot", model_id_map={"unknown": "openai-gpt-4o"}
    )
    connector = OpenAIUsageConnector(
        admin_api_key="sk-openai-admin-test",
        config=config,
        user_directory=InMemoryUserDirectory({"api_key:": "Unknown"}),
        http_client=_StaticHTTPClient(fixture),
    )
    events = list(connector.pull(since=SINCE))
    assert len(events) == 1
    event = events[0]
    assert event.user_id == "api_key:"
    assert event.prompt_tokens == 141201
    assert event.completion_tokens == 9756
