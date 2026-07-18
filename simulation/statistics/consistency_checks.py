"""Consistency checks: assert the behavior model actually holds in generated data.

Per the simulation-engineer agent (.ai/agents/simulation-engineer.md): "Maintain
statistical consistency... Never generate impossible scenarios." These checks are
not unit tests of generator code paths — they inspect the *output* DataFrames and
fail loudly if the numbers don't actually reflect docs/04-simulation/behavior-model.md
or if referential integrity between datasets is broken.

Run via simulation/generate_all.py after generation, or standalone:
    python -m simulation.statistics.consistency_checks
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from simulation.behavior import BEHAVIOR_RULES


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _check(name: str, condition: bool, detail: str) -> CheckResult:
    return CheckResult(name=name, passed=condition, detail=detail)


def check_engineering_vs_hr_volume(ai_events: pd.DataFrame, departments: pd.DataFrame) -> CheckResult:
    # behavior-model.md's "Engineering uses AI ~8x more than HR" is a per-employee
    # usage claim (that's what usage_multiplier encodes) — raw event-count ratio
    # also carries the headcount ratio between the two departments, so normalize
    # by employee_count to isolate the per-capita signal the rule is actually about.
    counts = ai_events["department"].value_counts()
    headcount = departments.set_index("department_name")["employee_count"]
    eng_per_capita = counts.get("Engineering", 0) / headcount["Engineering"]
    hr_per_capita = counts.get("HR", 0) / headcount["HR"]
    ratio = eng_per_capita / hr_per_capita if hr_per_capita else float("inf")
    expected = BEHAVIOR_RULES["Engineering"].usage_multiplier / BEHAVIOR_RULES["HR"].usage_multiplier
    ok = expected * 0.7 <= ratio <= expected * 1.3
    return _check(
        "engineering_vs_hr_volume",
        ok,
        f"Engineering/HR per-employee event-volume ratio = {ratio:.2f} (behavior model target ~{expected:.1f}x)",
    )

def check_finance_legal_stricter_governance(ai_events: pd.DataFrame) -> CheckResult:
    blocked_rate = ai_events.groupby("department")["outcome"].apply(lambda s: (s == "blocked").mean())
    baseline = blocked_rate.drop(index=["Finance", "Legal"], errors="ignore").mean()
    ok = blocked_rate.get("Finance", 0) > baseline and blocked_rate.get("Legal", 0) > baseline
    return _check(
        "finance_legal_stricter_governance",
        ok,
        f"blocked-rate: Finance={blocked_rate.get('Finance', 0):.4f}, Legal={blocked_rate.get('Legal', 0):.4f}, "
        f"other-dept baseline={baseline:.4f}",
    )


def check_legal_longer_context(ai_events: pd.DataFrame) -> CheckResult:
    avg_prompt = ai_events.groupby("department")["prompt_tokens"].mean()
    legal = avg_prompt.get("Legal", 0)
    others_max = avg_prompt.drop(index=["Legal"], errors="ignore").max()
    ok = legal > others_max
    return _check(
        "legal_longer_context",
        ok,
        f"Legal avg prompt_tokens={legal:.0f}, next-highest department={others_max:.0f}",
    )


def check_operations_high_volume_short_prompts(ai_events: pd.DataFrame) -> CheckResult:
    avg_prompt = ai_events.groupby("department")["prompt_tokens"].mean()
    counts = ai_events["department"].value_counts()
    ops_prompt = avg_prompt.get("Operations", 0)
    ops_rank_volume = counts.rank(ascending=False).get("Operations", 99)
    ok = ops_prompt == avg_prompt.min() and ops_rank_volume <= 3
    return _check(
        "operations_high_volume_short_prompts",
        ok,
        f"Operations avg prompt_tokens={ops_prompt:.0f} (min={avg_prompt.min():.0f}), "
        f"volume rank={int(ops_rank_volume)} of {len(counts)}",
    )


def check_incidents_reference_real_events(ai_events: pd.DataFrame, incidents: pd.DataFrame) -> CheckResult:
    event_ids = set(ai_events["event_id"])
    linked = incidents[incidents["related_event_id"] != ""]
    orphaned = linked[~linked["related_event_id"].isin(event_ids)]
    ok = len(orphaned) == 0
    return _check(
        "incidents_reference_real_events",
        ok,
        f"{len(orphaned)} of {len(linked)} event-linked incidents reference a non-existent event_id",
    )


def check_incidents_correlate_with_strict_departments(incidents: pd.DataFrame, ai_events: pd.DataFrame) -> CheckResult:
    event_share = ai_events["department"].value_counts(normalize=True)
    incident_share = incidents["department"].value_counts(normalize=True)
    # Finance/Legal/Security should be over-represented in incidents relative to
    # their share of raw event volume (that's what incident_multiplier encodes).
    over_represented = [
        dept
        for dept in ("Finance", "Legal", "Security")
        if incident_share.get(dept, 0) > event_share.get(dept, 0)
    ]
    ok = len(over_represented) >= 2
    return _check(
        "incidents_correlate_with_strict_departments",
        ok,
        f"incident-share > event-share for: {over_represented} (need >= 2 of Finance/Legal/Security)",
    )


def check_no_cost_without_tokens(ai_events: pd.DataFrame) -> CheckResult:
    bad = ai_events[(ai_events["request_cost"] > 0) & (ai_events["prompt_tokens"] + ai_events["completion_tokens"] == 0)]
    zero_cost_with_tokens = ai_events[
        (ai_events["request_cost"] == 0) & (ai_events["prompt_tokens"] + ai_events["completion_tokens"] > 0)
    ]
    ok = len(bad) == 0 and len(zero_cost_with_tokens) == 0
    return _check(
        "no_cost_without_tokens",
        ok,
        f"{len(bad)} events have cost with zero tokens; {len(zero_cost_with_tokens)} events have tokens with zero cost",
    )


def check_referential_integrity(
    ai_events: pd.DataFrame, users: pd.DataFrame, applications: pd.DataFrame, models: pd.DataFrame
) -> CheckResult:
    bad_users = ~ai_events["user_id"].isin(users["user_id"]).all()
    bad_apps = ~ai_events["application_id"].isin(applications["app_id"]).all()
    bad_models = ~ai_events["model"].isin(models["model_id"]).all()
    ok = not (bad_users or bad_apps or bad_models)
    return _check(
        "referential_integrity",
        ok,
        f"invalid user_id refs={bad_users}, invalid application_id refs={bad_apps}, invalid model refs={bad_models}",
    )


def check_monthly_costs_reconcile_with_events(
    ai_events: pd.DataFrame, mcp_tool_calls: pd.DataFrame, monthly_costs: pd.DataFrame
) -> CheckResult:
    events = ai_events.copy()
    events["month"] = pd.to_datetime(events["timestamp"]).dt.to_period("M").astype(str)
    calls = mcp_tool_calls.copy()
    calls["month"] = pd.to_datetime(calls["timestamp"]).dt.to_period("M").astype(str)

    reconciled_months = sorted(events["month"].unique())
    event_total = events.groupby("month")["request_cost"].sum()
    call_total = calls.groupby("month")["cost"].sum()
    actual_total = event_total.add(call_total, fill_value=0.0)

    reported = monthly_costs[monthly_costs["month"].isin(reconciled_months)].groupby("month")["total_cost"].sum()

    diffs = {}
    for month in reconciled_months:
        a, r = actual_total.get(month, 0.0), reported.get(month, 0.0)
        diffs[month] = abs(a - r) / a if a else 0.0
    ok = all(d < 0.01 for d in diffs.values())
    return _check(
        "monthly_costs_reconcile_with_events",
        ok,
        f"max relative diff between monthly_costs.csv and aggregated ai_events+mcp_tool_calls = "
        f"{max(diffs.values()) if diffs else 0:.4%}",
    )


def run_all_checks(data: dict) -> list[CheckResult]:
    results = [
        check_engineering_vs_hr_volume(data["ai_events"], data["departments"]),
        check_finance_legal_stricter_governance(data["ai_events"]),
        check_legal_longer_context(data["ai_events"]),
        check_operations_high_volume_short_prompts(data["ai_events"]),
        check_incidents_reference_real_events(data["ai_events"], data["incidents"]),
        check_incidents_correlate_with_strict_departments(data["incidents"], data["ai_events"]),
        check_no_cost_without_tokens(data["ai_events"]),
        check_referential_integrity(data["ai_events"], data["users"], data["applications"], data["models"]),
        check_monthly_costs_reconcile_with_events(
            data["ai_events"], data["mcp_tool_calls"], data["monthly_costs"]
        ),
    ]
    return results


if __name__ == "__main__":
    import sys

    from simulation.generate_all import load_generated_data

    results = run_all_checks(load_generated_data())
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"[{status}] {r.name}: {r.detail}")
    if any(not r.passed for r in results):
        sys.exit(1)
