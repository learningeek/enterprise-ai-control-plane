from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.connectors.base import AIUsageEvent
from backend.metering.duckdb_store import DuckDBEventSink, usage_summary


def make_event(**overrides) -> AIUsageEvent:
    defaults = dict(
        event_id="test:1",
        timestamp=datetime(2026, 6, 15, tzinfo=timezone.utc),
        tenant_id="acme-corp",
        user_id="api_key:key_1",
        department="Engineering",
        application_id="app-1",
        provider="Anthropic",
        model="anthropic-claude-sonnet-4",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=800,
        request_cost=Decimal("0.0012"),
        data_classification="internal",
        outcome="success",
    )
    defaults.update(overrides)
    return AIUsageEvent(**defaults)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "usage.duckdb"


def test_emit_returns_count_of_newly_inserted_events(db_path):
    sink = DuckDBEventSink(db_path)
    assert sink.emit([make_event(event_id="a"), make_event(event_id="b")]) == 2


def test_emit_is_idempotent_on_event_id(db_path):
    sink = DuckDBEventSink(db_path)
    sink.emit([make_event(event_id="a"), make_event(event_id="b")])
    second = sink.emit([make_event(event_id="a"), make_event(event_id="c")])
    assert second == 1  # only "c" is new; "a" is a duplicate re-pull and correctly not double-counted


def test_reopening_the_same_db_path_preserves_prior_inserts(db_path):
    DuckDBEventSink(db_path).emit([make_event(event_id="a")])
    second_sink = DuckDBEventSink(db_path)
    assert second_sink.emit([make_event(event_id="a"), make_event(event_id="b")]) == 1


def test_usage_summary_aggregates_by_user_department_provider_model(db_path):
    sink = DuckDBEventSink(db_path)
    sink.emit(
        [
            make_event(event_id="a", user_id="api_key:key_1", prompt_tokens=100, completion_tokens=50,
                       request_cost=Decimal("0.01")),
            make_event(event_id="b", user_id="api_key:key_1", prompt_tokens=200, completion_tokens=100,
                       request_cost=Decimal("0.02")),
            make_event(event_id="c", user_id="api_key:key_2", provider="OpenAI", model="openai-gpt-4o",
                       prompt_tokens=50, completion_tokens=25, request_cost=Decimal("0.005")),
        ]
    )

    summary = usage_summary(db_path)

    key_1_row = next(row for row in summary if row["user_id"] == "api_key:key_1")
    assert key_1_row["request_count"] == 2
    assert key_1_row["total_prompt_tokens"] == 300
    assert key_1_row["total_completion_tokens"] == 150
    assert key_1_row["total_cost"] == Decimal("0.030000")
    assert key_1_row["provider"] == "Anthropic"

    key_2_row = next(row for row in summary if row["user_id"] == "api_key:key_2")
    assert key_2_row["provider"] == "OpenAI"
    assert key_2_row["request_count"] == 1


def test_usage_summary_tracks_first_and_last_seen(db_path):
    sink = DuckDBEventSink(db_path)
    earlier = datetime(2026, 6, 1, tzinfo=timezone.utc)
    later = earlier + timedelta(days=10)
    sink.emit([make_event(event_id="a", timestamp=earlier), make_event(event_id="b", timestamp=later)])

    summary = usage_summary(db_path)

    assert summary[0]["first_seen"] == earlier
    assert summary[0]["last_seen"] == later


def test_usage_summary_on_empty_store_returns_empty_list(db_path):
    DuckDBEventSink(db_path)
    assert usage_summary(db_path) == []


def test_usage_summary_on_a_db_path_never_touched_by_the_sink_returns_empty_list_not_an_error(db_path):
    """Regression test: running `report` before ever running `sync` must not crash with a raw
    DuckDB CatalogException — usage_summary() must create the table itself if missing."""
    assert not db_path.exists()
    assert usage_summary(db_path) == []
