"""Shared connector contract: AIUsageEvent, Connector, EventSink, UserDirectory, HTTPClient.

This is the shape every Tier 1 (AI-provider admin API) connector implements — see
docs/02-architecture/connector-framework.md ("Connector interface"). A new vendor is a new module
implementing `Connector`, not a new pattern.

`HTTPClient` is a minimal Protocol rather than a dependency on `requests`/`httpx`, so this module has
no third-party dependency beyond pydantic (already used by `simulation/`) — `UrllibHTTPClient` below is
a stdlib-only default adapter; swap in a real client for retries/connection pooling in production.
"""

from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel


class AIUsageEvent(BaseModel):
    """Mirrors specs/event-schema.md exactly. Do not add fields without a spec change first."""

    event_id: str
    schema_version: int = 1
    timestamp: datetime
    tenant_id: str
    user_id: str
    department: str
    application_id: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    request_cost: Decimal
    data_classification: str
    mcp_tool_used: str | None = None
    outcome: Literal["success", "blocked", "error"]


class UserDirectory(Protocol):
    """Resolves a synced-from-SSO user_id to org attributes.

    Tier 1 connectors never invent department data themselves (docs/01-domain/users.md: "users are
    synced from the customer's SSO, not manually managed") — they resolve it from whatever already
    synced the org roster.
    """

    def department_for(self, user_id: str) -> str: ...


class EventSink(Protocol):
    """Where a connector's mapped events go.

    `specs/api-contract.md`'s `POST /v1/events` (the gateway) is the intended production sink once
    `backend/gateway` exists, but connectors are not coupled to it — sinks are pluggable so connector
    work isn't blocked on gateway work, and vice versa.
    """

    def emit(self, events: Iterable[AIUsageEvent]) -> int: ...


class HTTPClient(Protocol):
    def get(self, url: str, *, params: Mapping[str, str], headers: Mapping[str, str]) -> dict: ...

    def post(self, url: str, *, json_body: Mapping[str, object], headers: Mapping[str, str]) -> dict: ...


class CostEstimator(Protocol):
    def estimate(self, model: str, prompt_tokens: int, completion_tokens: int) -> Decimal: ...


class ModelIdResolver:
    """Maps a vendor-native model name/version string to this platform's canonical model_id.

    `specs/event-schema.md`'s `model` field "references docs/01-domain/models.md" — i.e. it must be one
    of `simulation/generators/models.py`'s `MODEL_CATALOG` ids (e.g. `"openai-gpt-4o"`), not the raw
    string a vendor's usage API reports (e.g. `"gpt-4o-2024-08-06"`). Vendor model strings drift often
    (dated snapshots, aliases), so this is an explicit, connector-supplied map rather than a guessed
    prefix/suffix match — an unmapped model fails loudly rather than silently misattributing cost to the
    wrong catalog entry (or bypassing the catalog check entirely).
    """

    def __init__(self, vendor_to_catalog_id: Mapping[str, str]):
        self._vendor_to_catalog_id = dict(vendor_to_catalog_id)

    def resolve(self, vendor_model_name: str) -> str:
        try:
            return self._vendor_to_catalog_id[vendor_model_name]
        except KeyError:
            raise KeyError(
                f"no catalog model_id mapped for vendor model {vendor_model_name!r}; add it to this "
                "connector's model_id_map config (see docs/01-domain/models.md)"
            ) from None


class ApproximateCatalogCostEstimator:
    """Estimates cost from the same approximate per-model catalog `simulation/` uses.

    Shared by every Tier 1 connector whose vendor doesn't (yet) have a real cost-report join wired up —
    see e.g. `anthropic_admin.py`'s and `openai_usage.py`'s module docstrings. Deliberately reuses
    `simulation.generators.models.MODEL_CATALOG` rather than a second hardcoded price table
    (docs/context.md: don't create a parallel model of the same fact). Raises rather than silently
    returning 0 for an unpriced model, since a silent-zero cost would corrupt metering/chargeback
    without anyone noticing.
    """

    def __init__(self) -> None:
        from simulation.generators.models import MODEL_CATALOG

        self._pricing: dict[str, tuple[Decimal, Decimal]] = {
            model_id: (Decimal(str(input_per_1m)), Decimal(str(output_per_1m)))
            for model_id, _provider, _name, input_per_1m, output_per_1m, _ctx, _approved in MODEL_CATALOG
        }

    def estimate(self, model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
        try:
            input_per_1m, output_per_1m = self._pricing[model]
        except KeyError:
            raise KeyError(
                f"no approximate pricing on record for model={model!r}; add it to "
                "simulation/generators/models.py's MODEL_CATALOG before ingesting its usage"
            ) from None
        return (Decimal(prompt_tokens) * input_per_1m + Decimal(completion_tokens) * output_per_1m) / Decimal(
            1_000_000
        )


class Connector(ABC):
    """One per AI-provider admin API."""

    provider: str

    @abstractmethod
    def pull(self, since: datetime, until: datetime | None = None) -> Iterator[AIUsageEvent]:
        """Yield AIUsageEvents observed in [since, until).

        Must be pagination-aware and must derive `event_id` deterministically from the underlying
        vendor record (not e.g. a random uuid), so re-pulling an overlapping window is idempotent —
        downstream de-duplication (the gateway, once it exists) relies on stable event_ids, not on the
        connector never re-pulling the same window.
        """

    def sync(self, sink: EventSink, since: datetime, until: datetime | None = None) -> int:
        """Pull then emit; returns the number of events emitted."""
        return sink.emit(self.pull(since, until))


class UrllibHTTPClient:
    """Stdlib-only HTTPClient adapter — sufficient for a handful of authenticated GETs/POSTs."""

    def get(self, url: str, *, params: Mapping[str, str], headers: Mapping[str, str]) -> dict:
        full_url = f"{url}?{urlencode(params)}" if params else url
        request = Request(full_url, headers=dict(headers))
        with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed https vendor endpoints only
            return json.load(response)

    def post(self, url: str, *, json_body: Mapping[str, object], headers: Mapping[str, str]) -> dict:
        request = Request(
            url,
            data=json.dumps(json_body).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed https vendor endpoints only
            return json.load(response)


class CSVUserDirectory:
    """UserDirectory backed by demo-data/users.csv — stands in for a real Okta/Entra sync in local dev."""

    def __init__(self, users_csv_path: Path):
        self._department_by_user: dict[str, str] = {}
        with users_csv_path.open(newline="") as f:
            for row in csv.DictReader(f):
                self._department_by_user[row["user_id"]] = row["department"]

    def department_for(self, user_id: str) -> str:
        try:
            return self._department_by_user[user_id]
        except KeyError:
            raise KeyError(
                f"no department on record for user_id={user_id!r}; is the SSO sync stale?"
            ) from None


class InMemoryUserDirectory:
    """UserDirectory backed by a plain dict — for tests."""

    def __init__(self, department_by_user: Mapping[str, str]):
        self._department_by_user = dict(department_by_user)

    def department_for(self, user_id: str) -> str:
        try:
            return self._department_by_user[user_id]
        except KeyError:
            raise KeyError(
                f"no department on record for user_id={user_id!r}; is the SSO sync stale?"
            ) from None


class JSONLSink:
    """Local-dev EventSink: appends newline-delimited AIUsageEvent JSON to a file."""

    def __init__(self, path: Path):
        self.path = path

    def emit(self, events: Iterable[AIUsageEvent]) -> int:
        count = 0
        with self.path.open("a") as f:
            for event in events:
                f.write(event.model_dump_json())
                f.write("\n")
                count += 1
        return count


class ListSink:
    """In-memory EventSink for tests."""

    def __init__(self) -> None:
        self.events: list[AIUsageEvent] = []

    def emit(self, events: Iterable[AIUsageEvent]) -> int:
        new = list(events)
        self.events.extend(new)
        return len(new)
