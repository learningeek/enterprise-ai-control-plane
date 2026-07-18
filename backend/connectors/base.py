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
    """Stdlib-only HTTPClient adapter — sufficient for a handful of authenticated GETs."""

    def get(self, url: str, *, params: Mapping[str, str], headers: Mapping[str, str]) -> dict:
        full_url = f"{url}?{urlencode(params)}" if params else url
        request = Request(full_url, headers=dict(headers))
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
