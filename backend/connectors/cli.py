"""CLI entrypoint for Tier 1 connectors.

This is what turns `backend/connectors/` from library code into something a platform team can actually
run against their own org — see docs/02-architecture/connector-framework.md and
docs/current-state.md's "Next up". Without this, the connectors are correct but nobody outside a Python
REPL can invoke them.

Usage:
    python -m backend.connectors.cli sync --config connectors.toml
    python -m backend.connectors.cli sync --config connectors.toml --since 2026-06-01 --until 2026-07-01

Config format: see `connectors.example.toml` at the repo root. Each connector section accepts a secret
either of two ways — an environment variable name (`admin_api_key_env` / `aad_bearer_token_env`, the
recommended default: nothing sensitive ever touches disk in this file) or a literal value
(`admin_api_key` / `aad_bearer_token`) for enterprises whose internal process is to distribute a
self-contained config through an already-secured channel (their own secrets manager, an encrypted share,
etc.). If both are present, the literal value wins. Whichever form is used, `connectors.toml` itself
stays out of git (see `.gitignore`) — and if it contains a literal secret, `load_config` warns to stderr
if the file's permissions are wider than owner-only, since a shareable config carrying real credentials
is exactly the kind of file worth checking that on.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tomllib
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.connectors.anthropic_admin import AnthropicAdminConnector, AnthropicAdminConnectorConfig
from backend.connectors.azure_openai import AzureOpenAIConnector, AzureOpenAIConnectorConfig
from backend.connectors.base import (
    Connector,
    CSVUserDirectory,
    EventSink,
    HTTPClient,
    PermissiveUserDirectory,
    UserDirectory,
)
from backend.connectors.openai_usage import OpenAIUsageConnector, OpenAIUsageConnectorConfig
from backend.metering.duckdb_store import DuckDBEventSink

DEFAULT_SINCE_DAYS = 30


class _NoUserDirectoryConfigured:
    """Used when no users_csv is configured — fails clearly rather than silently returning 'Unknown'
    for every event, which a PermissiveUserDirectory wrapper would otherwise mask as if it were a real
    per-user lookup miss rather than "the org hasn't set this up at all yet"."""

    def department_for(self, user_id: str) -> str:
        raise KeyError(
            f"no users_csv configured in [global]; cannot resolve department for user_id={user_id!r}"
        )


_SECRET_LITERAL_FIELDS = ("admin_api_key", "aad_bearer_token")


def _contains_literal_secret(config: dict) -> bool:
    return any(
        section.get(field)
        for section in config.get("connectors", {}).values()
        for field in _SECRET_LITERAL_FIELDS
    )


def _warn_if_permissions_are_too_open(path: Path) -> None:
    try:
        mode = path.stat().st_mode
    except OSError:
        return
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        print(
            f"warning: {path} contains a literal credential and is readable beyond its owner "
            f"(mode {oct(mode & 0o777)}) — consider `chmod 600 {path}`",
            file=sys.stderr,
        )


def load_config(path: Path) -> dict:
    with path.open("rb") as f:
        config = tomllib.load(f)
    if _contains_literal_secret(config):
        _warn_if_permissions_are_too_open(path)
    return config


def _resolve_secret(cfg: dict, connector_name: str, direct_field: str, env_field: str) -> str:
    """Resolves a secret from a literal config value or a named env var — literal wins if both are set.

    Prefer the env-var form (`{env_field}`) where possible; the literal form (`{direct_field}`) exists
    for enterprises whose own process already handles distributing a config file with real credentials
    securely — see this module's docstring.
    """
    literal = cfg.get(direct_field)
    if literal:
        return literal
    env_var_name = cfg.get(env_field)
    if env_var_name:
        return _require_env(env_var_name, connector_name)
    raise SystemExit(
        f"[connectors.{connector_name}] needs either {direct_field!r} (a literal value) or "
        f"{env_field!r} (an environment variable name) — neither is set"
    )


def build_user_directory(config: dict) -> UserDirectory:
    global_config = config.get("global", {})
    users_csv = global_config.get("users_csv")
    if users_csv:
        try:
            directory: UserDirectory = CSVUserDirectory(Path(users_csv))
        except FileNotFoundError:
            raise SystemExit(f"[global] users_csv={users_csv!r} does not exist") from None
    else:
        directory = _NoUserDirectoryConfigured()
    if global_config.get("permissive_directory", True):
        directory = PermissiveUserDirectory(directory)
    return directory


def _require_env(env_var: str, connector_name: str) -> str:
    value = os.environ.get(env_var, "")
    if not value:
        raise SystemExit(f"missing env var {env_var!r}, required by [connectors.{connector_name}]")
    return value


def build_connectors(
    config: dict,
    user_directory: UserDirectory,
    http_client_factory: Callable[[], HTTPClient] | None = None,
) -> dict[str, Connector]:
    """Builds one Connector per enabled [connectors.*] section.

    Calls `http_client_factory()` separately for each connector (not once, shared) — a factory producing
    a stateful client (e.g. a test fake that records calls) must not have its state silently shared
    across unrelated vendors just because they happened to be enabled in the same run.
    """
    tenant_id = config["global"]["tenant_id"]
    connectors_config = config.get("connectors", {})
    built: dict[str, Connector] = {}

    anthropic_cfg = connectors_config.get("anthropic", {})
    if anthropic_cfg.get("enabled"):
        api_key = _resolve_secret(anthropic_cfg, "anthropic", "admin_api_key", "admin_api_key_env")
        built["anthropic"] = AnthropicAdminConnector(
            admin_api_key=api_key,
            config=AnthropicAdminConnectorConfig(
                tenant_id=tenant_id,
                application_id=anthropic_cfg["application_id"],
                default_data_classification=anthropic_cfg.get("default_data_classification", "internal"),
                api_key_owner=anthropic_cfg.get("api_key_owner", {}),
                model_id_map=anthropic_cfg.get("model_id_map", {}),
            ),
            user_directory=user_directory,
            http_client=http_client_factory() if http_client_factory else None,
        )

    openai_cfg = connectors_config.get("openai", {})
    if openai_cfg.get("enabled"):
        api_key = _resolve_secret(openai_cfg, "openai", "admin_api_key", "admin_api_key_env")
        built["openai"] = OpenAIUsageConnector(
            admin_api_key=api_key,
            config=OpenAIUsageConnectorConfig(
                tenant_id=tenant_id,
                application_id=openai_cfg["application_id"],
                default_data_classification=openai_cfg.get("default_data_classification", "internal"),
                openai_user_owner=openai_cfg.get("openai_user_owner", {}),
                model_id_map=openai_cfg.get("model_id_map", {}),
            ),
            user_directory=user_directory,
            http_client=http_client_factory() if http_client_factory else None,
        )

    azure_cfg = connectors_config.get("azure_openai", {})
    if azure_cfg.get("enabled"):
        token = _resolve_secret(azure_cfg, "azure_openai", "aad_bearer_token", "aad_bearer_token_env")
        built["azure_openai"] = AzureOpenAIConnector(
            aad_bearer_token=token,
            config=AzureOpenAIConnectorConfig(
                tenant_id=tenant_id,
                application_id=azure_cfg["application_id"],
                workspace_id=azure_cfg["workspace_id"],
                default_data_classification=azure_cfg.get("default_data_classification", "internal"),
                deployment_owner=azure_cfg.get("deployment_owner", {}),
                deployment_model_id_map=azure_cfg.get("deployment_model_id_map", {}),
            ),
            user_directory=user_directory,
            http_client=http_client_factory() if http_client_factory else None,
        )

    return built


def sync_all(connectors: dict[str, Connector], sink: EventSink, since: datetime, until: datetime) -> int:
    """Runs sync() on every connector; one connector's failure doesn't block the others."""
    total = 0
    for name, connector in connectors.items():
        try:
            count = connector.sync(sink, since, until)
        except Exception as exc:  # noqa: BLE001 - report and continue, don't let one vendor outage kill the run
            print(f"{name}: FAILED — {exc}", file=sys.stderr)
            continue
        print(f"{name}: {count} new event(s)")
        total += count
    return total


def _parse_iso_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def run_sync(
    config_path: Path,
    since_arg: str | None,
    until_arg: str | None,
    http_client_factory: Callable[[], HTTPClient] | None = None,
) -> int:
    config = load_config(config_path)
    global_config = config.get("global", {})

    until = _parse_iso_utc(until_arg) if until_arg else datetime.now(timezone.utc)
    since_days = global_config.get("since_days", DEFAULT_SINCE_DAYS)
    since = _parse_iso_utc(since_arg) if since_arg else until - timedelta(days=since_days)

    user_directory = build_user_directory(config)
    connectors = build_connectors(config, user_directory, http_client_factory=http_client_factory)
    if not connectors:
        print("no connectors enabled in [connectors.*]", file=sys.stderr)
        return 0

    sink = DuckDBEventSink(global_config["duckdb_path"])
    return sync_all(connectors, sink, since, until)


def run_report(config_path: Path, output_path: Path) -> None:
    from backend.metering.report import generate_report

    config = load_config(config_path)
    generate_report(config["global"]["duckdb_path"], output_path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Tier 1 connector CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="pull usage from configured connectors into DuckDB")
    sync_parser.add_argument("--config", type=Path, default=Path("connectors.toml"))
    sync_parser.add_argument("--since", type=str, default=None, help="ISO date/datetime, default: N days ago")
    sync_parser.add_argument("--until", type=str, default=None, help="ISO date/datetime, default: now")

    report_parser = subparsers.add_parser("report", help="regenerate the HTML usage/cost dashboard")
    report_parser.add_argument("--config", type=Path, default=Path("connectors.toml"))
    report_parser.add_argument("--output", type=Path, default=Path("ai_usage_report.html"))

    args = parser.parse_args(argv)

    if args.command == "sync":
        total = run_sync(args.config, args.since, args.until)
        print(f"total: {total} new event(s)")
    elif args.command == "report":
        run_report(args.config, args.output)
        print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
