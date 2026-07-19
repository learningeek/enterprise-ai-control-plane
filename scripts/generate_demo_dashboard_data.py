"""Populates a demo DuckDB store for the Tier 1 usage dashboard.

This is sample data for exercising `backend/metering/report.py`, not a live vendor pull — no admin
credentials are available in this environment to run the real CLI end to end. Events are constructed
directly (bypassing connector HTTP calls entirely) but written through the real `DuckDBEventSink`, so
everything downstream of ingestion (storage, aggregation, the dashboard itself) runs on real product
code, not a mock.

Deliberately mixes real employee user_ids with unmapped `api_key:`/`deployment:` synthetic ids across
all three providers, to show the dashboard exactly as it would look on day one — before an org has done
any ownership-mapping setup work (see docs/02-architecture/connector-framework.md).

Usage:
    .venv/bin/python -m scripts.generate_demo_dashboard_data
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from backend.connectors.base import AIUsageEvent
from backend.metering.duckdb_store import DuckDBEventSink

DEMO_DB_PATH = Path("demo-data/dashboard_demo.duckdb")

BASE_DAY = datetime(2026, 6, 15, tzinfo=timezone.utc)

# (user_id, department, provider, model, application_id, requests, avg_prompt, avg_completion, day_offset)
ROWS = [
    ("U000001", "Engineering", "Anthropic", "anthropic-claude-sonnet-4", "claude-code", 40, 1200, 600, 0),
    ("U000001", "Engineering", "Anthropic", "anthropic-claude-sonnet-4", "claude-code", 35, 1100, 550, 1),
    ("api_key:key_unmapped_1", "Unknown", "Anthropic", "anthropic-claude-haiku-4", "internal-bot", 60, 300, 150, 0),
    ("api_key:key_unmapped_1", "Unknown", "Anthropic", "anthropic-claude-haiku-4", "internal-bot", 55, 320, 140, 2),
    ("U000045", "Sales", "OpenAI", "openai-gpt-4o", "internal-copilot", 25, 900, 400, 0),
    ("U000045", "Sales", "OpenAI", "openai-gpt-4o", "internal-copilot", 30, 950, 420, 3),
    ("api_key:key_unmapped_2", "Unknown", "OpenAI", "openai-gpt-4o-mini", "sales-assistant", 80, 200, 100, 1),
    ("api_key:key_unmapped_2", "Unknown", "OpenAI", "openai-gpt-4o-mini", "sales-assistant", 90, 210, 95, 4),
    ("deployment:gpt4o-prod", "Unknown", "Azure OpenAI", "openai-gpt-4o", "internal-copilot", 45, 1000, 500, 0),
    ("deployment:gpt4o-prod", "Unknown", "Azure OpenAI", "openai-gpt-4o", "internal-copilot", 50, 1050, 480, 2),
    ("U000210", "Finance", "Azure OpenAI", "openai-gpt-4o-mini", "finance-bot", 20, 400, 150, 1),
    ("U000210", "Finance", "Azure OpenAI", "openai-gpt-4o-mini", "finance-bot", 22, 420, 160, 3),
]

# Same approximate per-1M-token pricing as simulation/generators/models.py's MODEL_CATALOG, so the demo
# numbers are internally consistent with the rest of the repo rather than a third set of made-up prices.
PRICE_PER_1M = {
    "anthropic-claude-sonnet-4": (Decimal("3.00"), Decimal("15.00")),
    "anthropic-claude-haiku-4": (Decimal("0.80"), Decimal("4.00")),
    "openai-gpt-4o": (Decimal("2.50"), Decimal("10.00")),
    "openai-gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
}


def build_events() -> list[AIUsageEvent]:
    events = []
    for i, (user_id, department, provider, model, application_id, requests, avg_prompt, avg_completion, day_offset) in enumerate(ROWS):
        input_per_1m, output_per_1m = PRICE_PER_1M[model]
        prompt_tokens = avg_prompt * requests
        completion_tokens = avg_completion * requests
        cost = (Decimal(prompt_tokens) * input_per_1m + Decimal(completion_tokens) * output_per_1m) / Decimal(1_000_000)
        events.append(
            AIUsageEvent(
                event_id=f"demo:{i}",
                timestamp=BASE_DAY + timedelta(days=day_offset),
                tenant_id="acme-corp",
                user_id=user_id,
                department=department,
                application_id=application_id,
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=0 if provider != "Azure OpenAI" else 900,
                request_cost=cost,
                data_classification="internal",
                mcp_tool_used=None,
                outcome="success",
            )
        )
    return events


def main() -> None:
    DEMO_DB_PATH.parent.mkdir(exist_ok=True)
    sink = DuckDBEventSink(DEMO_DB_PATH)
    count = sink.emit(build_events())
    print(f"wrote {count} new event(s) to {DEMO_DB_PATH}")


if __name__ == "__main__":
    main()
