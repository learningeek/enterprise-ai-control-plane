from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.connectors.anthropic_admin import AnthropicAdminConnector
from backend.connectors.azure_openai import AzureOpenAIConnector
from backend.connectors.base import InMemoryUserDirectory, ListSink, PermissiveUserDirectory
from backend.connectors.cli import (
    build_connectors,
    build_user_directory,
    load_config,
    run_report,
    run_sync,
    sync_all,
)
from backend.connectors.openai_usage import OpenAIUsageConnector

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CONFIG = REPO_ROOT / "connectors.example.toml"

SINCE = datetime(2026, 6, 1, tzinfo=timezone.utc)
UNTIL = datetime(2026, 7, 1, tzinfo=timezone.utc)


class FakeHTTPClient:
    def get(self, url, *, params, headers):
        return {"data": [], "next_page": None}

    def post(self, url, *, json_body, headers):
        return {"tables": []}


# --- build_user_directory -------------------------------------------------


def test_build_user_directory_wraps_in_permissive_by_default(tmp_path):
    users_csv = tmp_path / "users.csv"
    users_csv.write_text("user_id,name,department,title,manager,country,cost_center,identity_provider,additional_groups\nU1,A,Eng,,,,,,\n")
    config = {"global": {"users_csv": str(users_csv)}}
    directory = build_user_directory(config)
    assert isinstance(directory, PermissiveUserDirectory)
    assert directory.department_for("unknown-user") == "Unknown"
    assert directory.department_for("U1") == "Eng"


def test_build_user_directory_can_disable_permissive_wrapping(tmp_path):
    users_csv = tmp_path / "users.csv"
    users_csv.write_text("user_id,name,department,title,manager,country,cost_center,identity_provider,additional_groups\nU1,A,Eng,,,,,,\n")
    config = {"global": {"users_csv": str(users_csv), "permissive_directory": False}}
    directory = build_user_directory(config)
    with pytest.raises(KeyError):
        directory.department_for("unknown-user")


def test_build_user_directory_without_users_csv_fails_clearly_when_not_permissive():
    config = {"global": {"permissive_directory": False}}
    directory = build_user_directory(config)
    with pytest.raises(KeyError, match="no users_csv configured"):
        directory.department_for("anyone")


def test_build_user_directory_without_users_csv_is_permissive_by_default():
    config = {"global": {}}
    directory = build_user_directory(config)
    assert directory.department_for("anyone") == "Unknown"


# --- build_connectors -------------------------------------------------


def test_build_connectors_only_builds_enabled_ones(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_ADMIN_API_KEY", "sk-ant-admin-test")
    config = {
        "global": {"tenant_id": "acme-corp"},
        "connectors": {
            "anthropic": {"enabled": True, "admin_api_key_env": "ANTHROPIC_ADMIN_API_KEY", "application_id": "app"},
            "openai": {"enabled": False, "admin_api_key_env": "OPENAI_ADMIN_API_KEY", "application_id": "app"},
        },
    }
    connectors = build_connectors(
        config, InMemoryUserDirectory({}), http_client_factory=lambda: FakeHTTPClient()
    )
    assert set(connectors) == {"anthropic"}
    assert isinstance(connectors["anthropic"], AnthropicAdminConnector)


def test_build_connectors_raises_clearly_on_missing_env_var(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_ADMIN_API_KEY", raising=False)
    config = {
        "global": {"tenant_id": "acme-corp"},
        "connectors": {
            "anthropic": {"enabled": True, "admin_api_key_env": "ANTHROPIC_ADMIN_API_KEY", "application_id": "app"},
        },
    }
    with pytest.raises(SystemExit, match="ANTHROPIC_ADMIN_API_KEY"):
        build_connectors(config, InMemoryUserDirectory({}), http_client_factory=lambda: FakeHTTPClient())


def test_build_connectors_accepts_a_literal_secret_with_no_env_var_set(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_ADMIN_API_KEY", raising=False)
    config = {
        "global": {"tenant_id": "acme-corp"},
        "connectors": {
            "anthropic": {"enabled": True, "admin_api_key": "sk-ant-admin-literal", "application_id": "app"},
        },
    }
    connectors = build_connectors(config, InMemoryUserDirectory({}), http_client_factory=lambda: FakeHTTPClient())
    assert "anthropic" in connectors


def test_build_connectors_prefers_literal_secret_over_env_var(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_ADMIN_API_KEY", "from-env")
    config = {
        "global": {"tenant_id": "acme-corp"},
        "connectors": {
            "anthropic": {
                "enabled": True,
                "admin_api_key": "from-literal",
                "admin_api_key_env": "ANTHROPIC_ADMIN_API_KEY",
                "application_id": "app",
            },
        },
    }
    connectors = build_connectors(config, InMemoryUserDirectory({}), http_client_factory=lambda: FakeHTTPClient())
    assert connectors["anthropic"]._admin_api_key == "from-literal"


def test_build_connectors_raises_clearly_when_neither_secret_form_is_set():
    config = {
        "global": {"tenant_id": "acme-corp"},
        "connectors": {"anthropic": {"enabled": True, "application_id": "app"}},
    }
    with pytest.raises(SystemExit, match="admin_api_key"):
        build_connectors(config, InMemoryUserDirectory({}), http_client_factory=lambda: FakeHTTPClient())


def test_build_connectors_builds_all_three_vendor_types(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_ADMIN_API_KEY", "a")
    monkeypatch.setenv("OPENAI_ADMIN_API_KEY", "b")
    monkeypatch.setenv("AZURE_AAD_TOKEN", "c")
    config = {
        "global": {"tenant_id": "acme-corp"},
        "connectors": {
            "anthropic": {"enabled": True, "admin_api_key_env": "ANTHROPIC_ADMIN_API_KEY", "application_id": "app"},
            "openai": {"enabled": True, "admin_api_key_env": "OPENAI_ADMIN_API_KEY", "application_id": "app"},
            "azure_openai": {
                "enabled": True,
                "aad_bearer_token_env": "AZURE_AAD_TOKEN",
                "application_id": "app",
                "workspace_id": "ws-1",
            },
        },
    }
    connectors = build_connectors(
        config, InMemoryUserDirectory({}), http_client_factory=lambda: FakeHTTPClient()
    )
    assert isinstance(connectors["anthropic"], AnthropicAdminConnector)
    assert isinstance(connectors["openai"], OpenAIUsageConnector)
    assert isinstance(connectors["azure_openai"], AzureOpenAIConnector)


# --- sync_all -------------------------------------------------


class _FakeConnector:
    def __init__(self, count=0, error=None):
        self._count = count
        self._error = error

    def sync(self, sink, since, until):
        if self._error:
            raise self._error
        return self._count


def test_sync_all_sums_counts_across_connectors(capsys):
    connectors = {"a": _FakeConnector(count=3), "b": _FakeConnector(count=5)}
    total = sync_all(connectors, ListSink(), SINCE, UNTIL)
    assert total == 8
    out = capsys.readouterr().out
    assert "a: 3 new event(s)" in out
    assert "b: 5 new event(s)" in out


def test_sync_all_continues_past_one_connectors_failure(capsys):
    connectors = {"broken": _FakeConnector(error=RuntimeError("vendor down")), "ok": _FakeConnector(count=2)}
    total = sync_all(connectors, ListSink(), SINCE, UNTIL)
    assert total == 2
    err = capsys.readouterr().err
    assert "broken: FAILED" in err
    assert "vendor down" in err


# --- example config file -------------------------------------------------


def test_example_config_is_valid_toml():
    load_config(EXAMPLE_CONFIG)  # raises on parse failure


def test_example_config_builds_a_working_directory_and_connector_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_ADMIN_API_KEY", "sk-ant-admin-test")
    config = load_config(EXAMPLE_CONFIG)
    directory = build_user_directory(config)
    connectors = build_connectors(config, directory, http_client_factory=lambda: FakeHTTPClient())
    # example config only enables anthropic; openai/azure_openai are enabled = false
    assert set(connectors) == {"anthropic"}


# --- run_sync (end-to-end against a temp config + fake HTTP, no real network) ---


def test_run_sync_end_to_end_against_a_temp_config(tmp_path, monkeypatch):
    users_csv = tmp_path / "users.csv"
    users_csv.write_text(
        "user_id,name,department,title,manager,country,cost_center,identity_provider,additional_groups\n"
    )
    duckdb_path = tmp_path / "usage.duckdb"
    config_path = tmp_path / "connectors.toml"
    config_path.write_text(f"""
[global]
tenant_id = "acme-corp"
duckdb_path = "{duckdb_path}"
users_csv = "{users_csv}"

[connectors.anthropic]
enabled = true
admin_api_key_env = "ANTHROPIC_ADMIN_API_KEY"
application_id = "app"
""")
    monkeypatch.setenv("ANTHROPIC_ADMIN_API_KEY", "sk-ant-admin-test")

    total = run_sync(
        config_path,
        since_arg="2026-06-01",
        until_arg="2026-07-01",
        http_client_factory=lambda: FakeHTTPClient(),
    )

    assert total == 0  # FakeHTTPClient returns an empty usage report — this proves the wiring runs end
    # to end (config -> connector -> DuckDB) without touching real network, not that real data flows.
    assert duckdb_path.exists()


def test_run_report_reads_duckdb_path_from_config_and_writes_html(tmp_path):
    from backend.connectors.base import AIUsageEvent
    from backend.metering.duckdb_store import DuckDBEventSink
    from decimal import Decimal

    duckdb_path = tmp_path / "usage.duckdb"
    sink = DuckDBEventSink(duckdb_path)
    sink.emit(
        [
            AIUsageEvent(
                event_id="e1",
                timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
                tenant_id="acme-corp",
                user_id="api_key:key_1",
                department="Unknown",
                application_id="app",
                provider="Anthropic",
                model="anthropic-claude-sonnet-4",
                prompt_tokens=100,
                completion_tokens=50,
                latency_ms=0,
                request_cost=Decimal("0.01"),
                data_classification="internal",
                outcome="success",
            )
        ]
    )

    config_path = tmp_path / "connectors.toml"
    config_path.write_text(f'[global]\ntenant_id = "acme-corp"\nduckdb_path = "{duckdb_path}"\n')
    output_path = tmp_path / "report.html"

    run_report(config_path, output_path)

    html = output_path.read_text()
    assert "api_key:key_1" in html
    assert "Anthropic" in html


# --- load_config's permission warning for literal secrets -------------------------------------------


def test_load_config_warns_when_literal_secret_and_permissions_too_open(tmp_path, capsys):
    config_path = tmp_path / "connectors.toml"
    config_path.write_text(
        '[global]\ntenant_id = "acme-corp"\n'
        '[connectors.anthropic]\nenabled = true\nadmin_api_key = "sk-ant-admin-literal"\n'
    )
    config_path.chmod(0o644)  # group/other readable

    load_config(config_path)

    err = capsys.readouterr().err
    assert "readable beyond its owner" in err
    assert str(config_path) in err


def test_load_config_does_not_warn_when_permissions_are_owner_only(tmp_path, capsys):
    config_path = tmp_path / "connectors.toml"
    config_path.write_text(
        '[global]\ntenant_id = "acme-corp"\n'
        '[connectors.anthropic]\nenabled = true\nadmin_api_key = "sk-ant-admin-literal"\n'
    )
    config_path.chmod(0o600)

    load_config(config_path)

    assert capsys.readouterr().err == ""


def test_load_config_does_not_warn_when_no_literal_secret_present(tmp_path, capsys):
    config_path = tmp_path / "connectors.toml"
    config_path.write_text(
        '[global]\ntenant_id = "acme-corp"\n'
        '[connectors.anthropic]\nenabled = true\nadmin_api_key_env = "ANTHROPIC_ADMIN_API_KEY"\n'
    )
    config_path.chmod(0o644)  # world-readable, but no secret literally in the file — nothing to warn about

    load_config(config_path)

    assert capsys.readouterr().err == ""
