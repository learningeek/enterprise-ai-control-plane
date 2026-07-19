"""DuckDB-backed EventSink and query layer for AI usage events.

First real slice of `backend/metering/` (docs/context.md's terminology: "Metering | Turning usage events
into cost/usage numbers and chargeback"). Uses DuckDB per ADR 0003 ("fast local analytical queries over
large event volumes without standing up a separate data warehouse for early-stage deployments") —
deliberately not the eventual Postgres-backed system of record (`backend/gateway`, ADR 0002); this is the
local/single-tenant analytics store that lets Tier 1 connector output actually be queried today, without
waiting on the gateway.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import duckdb

from backend.connectors.base import AIUsageEvent

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ai_usage_events (
    event_id VARCHAR PRIMARY KEY,
    schema_version INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    tenant_id VARCHAR NOT NULL,
    user_id VARCHAR NOT NULL,
    department VARCHAR NOT NULL,
    application_id VARCHAR NOT NULL,
    provider VARCHAR NOT NULL,
    model VARCHAR NOT NULL,
    prompt_tokens BIGINT NOT NULL,
    completion_tokens BIGINT NOT NULL,
    latency_ms BIGINT NOT NULL,
    request_cost DECIMAL(18, 6) NOT NULL,
    data_classification VARCHAR NOT NULL,
    mcp_tool_used VARCHAR,
    outcome VARCHAR NOT NULL
)
"""

_INSERT_SQL = """
INSERT INTO ai_usage_events VALUES (
    $event_id, $schema_version, $timestamp, $tenant_id, $user_id, $department, $application_id,
    $provider, $model, $prompt_tokens, $completion_tokens, $latency_ms, $request_cost,
    $data_classification, $mcp_tool_used, $outcome
)
ON CONFLICT (event_id) DO NOTHING
RETURNING event_id
"""

_USAGE_SUMMARY_SQL = """
SELECT
    user_id,
    department,
    provider,
    model,
    COUNT(*) AS request_count,
    SUM(prompt_tokens) AS total_prompt_tokens,
    SUM(completion_tokens) AS total_completion_tokens,
    SUM(request_cost) AS total_cost,
    MIN(timestamp) AS first_seen,
    MAX(timestamp) AS last_seen
FROM ai_usage_events
GROUP BY user_id, department, provider, model
ORDER BY total_cost DESC
"""


class DuckDBEventSink:
    """EventSink that persists AIUsageEvents to a local DuckDB file, idempotent on event_id.

    `emit()` returns the count of *newly inserted* events, not the count attempted — re-running a
    connector `sync()` over an overlapping `[since, until)` window is safe and reports 0 for rows
    already on record, rather than double-counting. This puts `Connector.pull()`'s "must be idempotent
    on event_id" requirement to actual use, rather than just asserting it in a test.
    """

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE_SQL)

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(self._db_path)

    def emit(self, events: Iterable[AIUsageEvent]) -> int:
        inserted = 0
        with self._connect() as conn:
            for event in events:
                result = conn.execute(
                    _INSERT_SQL,
                    {
                        "event_id": event.event_id,
                        "schema_version": event.schema_version,
                        "timestamp": event.timestamp,
                        "tenant_id": event.tenant_id,
                        "user_id": event.user_id,
                        "department": event.department,
                        "application_id": event.application_id,
                        "provider": event.provider,
                        "model": event.model,
                        "prompt_tokens": event.prompt_tokens,
                        "completion_tokens": event.completion_tokens,
                        "latency_ms": event.latency_ms,
                        "request_cost": event.request_cost,
                        "data_classification": event.data_classification,
                        "mcp_tool_used": event.mcp_tool_used,
                        "outcome": event.outcome,
                    },
                )
                if result.fetchone() is not None:
                    inserted += 1
        return inserted


def usage_summary(db_path: str | Path) -> list[dict]:
    """One row per (user_id, department, provider, model): totals, cost, and first/last-seen timestamps.

    `user_id` here is whatever a connector wrote — a real employee id if the org configured the
    ownership mapping, otherwise a connector's synthetic per-API-key/deployment id (see
    `anthropic_admin.py`/`openai_usage.py`/`azure_openai.py`) — so this is accurately a per-API-key
    breakdown until an org does that mapping work, not silently a per-employee one.
    """
    with duckdb.connect(str(db_path)) as conn:
        rows = conn.execute(_USAGE_SUMMARY_SQL).fetchall()
        columns = [description[0] for description in conn.description]
    return [dict(zip(columns, row)) for row in rows]
