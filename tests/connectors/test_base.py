from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from backend.connectors.base import (
    AIUsageEvent,
    CSVUserDirectory,
    InMemoryUserDirectory,
    JSONLSink,
    ListSink,
    PermissiveUserDirectory,
)

DEMO_USERS_CSV = Path(__file__).resolve().parents[2] / "demo-data" / "users.csv"


def make_event(**overrides) -> AIUsageEvent:
    defaults = dict(
        event_id="test:1",
        timestamp=datetime.now(timezone.utc),
        tenant_id="acme-corp",
        user_id="U000001",
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


def test_ai_usage_event_rejects_unknown_outcome():
    with pytest.raises(Exception):
        make_event(outcome="not-a-real-outcome")


def test_list_sink_accumulates_across_calls():
    sink = ListSink()
    assert sink.emit([make_event(event_id="a")]) == 1
    assert sink.emit([make_event(event_id="b"), make_event(event_id="c")]) == 2
    assert [e.event_id for e in sink.events] == ["a", "b", "c"]


def test_jsonl_sink_writes_one_json_object_per_line(tmp_path):
    path = tmp_path / "events.jsonl"
    sink = JSONLSink(path)

    sink.emit([make_event(event_id="a"), make_event(event_id="b")])

    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert '"event_id":"a"' in lines[0]
    assert '"event_id":"b"' in lines[1]


def test_in_memory_user_directory_resolves_known_user():
    directory = InMemoryUserDirectory({"U000001": "Engineering"})
    assert directory.department_for("U000001") == "Engineering"


def test_in_memory_user_directory_raises_on_unknown_user():
    directory = InMemoryUserDirectory({"U000001": "Engineering"})
    with pytest.raises(KeyError, match="U999999"):
        directory.department_for("U999999")


@pytest.mark.skipif(not DEMO_USERS_CSV.exists(), reason="demo-data not generated in this environment")
def test_csv_user_directory_resolves_against_real_demo_data():
    directory = CSVUserDirectory(DEMO_USERS_CSV)
    assert directory.department_for("U000001") == "Engineering"


def test_permissive_user_directory_delegates_to_wrapped_directory_when_known():
    wrapped = InMemoryUserDirectory({"U000001": "Engineering"})
    directory = PermissiveUserDirectory(wrapped)
    assert directory.department_for("U000001") == "Engineering"


def test_permissive_user_directory_falls_back_instead_of_raising():
    wrapped = InMemoryUserDirectory({})
    directory = PermissiveUserDirectory(wrapped)
    assert directory.department_for("api_key:unmapped") == "Unknown"


def test_permissive_user_directory_uses_custom_fallback():
    wrapped = InMemoryUserDirectory({})
    directory = PermissiveUserDirectory(wrapped, fallback="Unattributed")
    assert directory.department_for("api_key:unmapped") == "Unattributed"
