"""Single entry point: regenerates every demo-data/ file from the simulation.

    python -m simulation.generate_all

Deterministic (see simulation/profiles/enterprise_profile.py `seed`) — running
this twice produces byte-identical output. Prints a row-count summary per file
when done, then runs simulation/statistics/consistency_checks.py and reports
pass/fail for each behavior-model assertion.

Never hand-edit demo-data/ — regenerate it from here instead (docs/context.md).
"""

from __future__ import annotations

import sys

import pandas as pd
from faker import Faker

from simulation.generators import (
    ai_events as ai_events_gen,
    applications as applications_gen,
    billing_accounts as billing_accounts_gen,
    departments as departments_gen,
    incidents as incidents_gen,
    mcp_servers as mcp_servers_gen,
    mcp_tool_calls as mcp_tool_calls_gen,
    models as models_gen,
    monthly_costs as monthly_costs_gen,
    policies as policies_gen,
    shadow_ai as shadow_ai_gen,
    sso_groups as sso_groups_gen,
    users as users_gen,
)
from simulation.generators.base import DEMO_DATA_DIR, save_csv, save_json
from simulation.profiles import DEFAULT_PROFILE
from simulation.statistics.consistency_checks import run_all_checks


def generate(profile=DEFAULT_PROFILE) -> dict:
    Faker.seed(profile.seed)

    row_counts: dict[str, int] = {}

    def _save(df: pd.DataFrame, filename: str) -> pd.DataFrame:
        save_csv(df, filename)
        row_counts[filename] = len(df)
        return df

    departments_df = _save(departments_gen.generate(profile), "departments.csv")
    users_df = _save(users_gen.generate(profile, departments_df), "users.csv")
    applications_df = _save(applications_gen.generate(profile), "applications.csv")

    models_df = _save(models_gen.generate_models(), "models.csv")
    pricing_df = _save(models_gen.generate_pricing(models_df), "pricing.csv")

    mcp_servers_df = _save(mcp_servers_gen.generate(profile), "mcp_servers.csv")

    ai_events_df = _save(
        ai_events_gen.generate(profile, users_df, applications_df, models_df, mcp_servers_df), "ai_events.csv"
    )
    mcp_tool_calls_df = _save(
        mcp_tool_calls_gen.generate(profile, users_df, mcp_servers_df), "mcp_tool_calls.csv"
    )
    monthly_costs_df = _save(
        monthly_costs_gen.generate(profile, ai_events_df, mcp_tool_calls_df, departments_df), "monthly_costs.csv"
    )
    billing_accounts_df = _save(
        billing_accounts_gen.generate(profile, ai_events_df, departments_df), "billing_accounts.csv"
    )
    sso_groups_df = _save(sso_groups_gen.generate(users_df), "sso_groups.csv")

    policies = policies_gen.generate(profile)
    save_json(policies, "policies.json")
    row_counts["policies.json"] = len(policies)

    incidents_df = _save(
        incidents_gen.generate(profile, ai_events_df, models_df, monthly_costs_df, billing_accounts_df),
        "incidents.csv",
    )
    shadow_ai_df = _save(shadow_ai_gen.generate(profile, users_df), "shadow_ai.csv")

    return {
        "profile": profile,
        "row_counts": row_counts,
        "departments": departments_df,
        "users": users_df,
        "applications": applications_df,
        "models": models_df,
        "pricing": pricing_df,
        "mcp_servers": mcp_servers_df,
        "ai_events": ai_events_df,
        "mcp_tool_calls": mcp_tool_calls_df,
        "monthly_costs": monthly_costs_df,
        "billing_accounts": billing_accounts_df,
        "sso_groups": sso_groups_df,
        "policies": policies,
        "incidents": incidents_df,
        "shadow_ai": shadow_ai_df,
    }


def load_generated_data() -> dict:
    """Re-load already-generated demo-data/*.csv for standalone consistency checks."""
    return {
        "ai_events": pd.read_csv(DEMO_DATA_DIR / "ai_events.csv"),
        "incidents": pd.read_csv(DEMO_DATA_DIR / "incidents.csv"),
        "users": pd.read_csv(DEMO_DATA_DIR / "users.csv"),
        "applications": pd.read_csv(DEMO_DATA_DIR / "applications.csv"),
        "models": pd.read_csv(DEMO_DATA_DIR / "models.csv"),
        "departments": pd.read_csv(DEMO_DATA_DIR / "departments.csv"),
        "mcp_tool_calls": pd.read_csv(DEMO_DATA_DIR / "mcp_tool_calls.csv"),
        "monthly_costs": pd.read_csv(DEMO_DATA_DIR / "monthly_costs.csv"),
    }


def main() -> int:
    data = generate()

    print("\ndemo-data/ row counts:")
    for filename, count in data["row_counts"].items():
        print(f"  {filename:<24} {count:>10,}")

    print("\nconsistency checks (simulation/statistics/):")
    results = run_all_checks(data)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.name}: {r.detail}")

    if any(not r.passed for r in results):
        print("\nOne or more consistency checks FAILED — see above.")
        return 1

    print("\nAll consistency checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
