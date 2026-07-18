"""Generates monthly_costs.csv per docs/04-simulation/forecast-generator.md and cost-model.md.

12 months of department-level cost history with a plausible growth trend (e.g.
$210K -> $225K -> $240K...). The most recent `profile.event_period_months` months
are *not* independently invented — they're the actual aggregated cost of
ai_events.csv + mcp_tool_calls.csv for that month/department, so the forecasting
input reconciles with the granular fact tables instead of floating free of them
(no "cost without tokens", per the simulation-engineer agent's consistency rule).
The remaining earlier months are backfilled with a smooth month-over-month growth
trend that lands on the first reconciled month's total.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from simulation.generators.base import get_rng

MONTHLY_GROWTH_RATE = 0.035
GROWTH_NOISE_SIGMA = 0.02


def generate(profile, ai_events_df: pd.DataFrame, mcp_tool_calls_df: pd.DataFrame,
             departments_df: pd.DataFrame) -> pd.DataFrame:
    rng = get_rng(profile, "monthly_costs")

    end_period = pd.Timestamp(profile.simulation_end_date).to_period("M")
    all_months = pd.period_range(end=end_period, periods=profile.history_months, freq="M")
    reconciled_months = all_months[-profile.event_period_months:]
    synthetic_months = all_months[: -profile.event_period_months]

    departments = list(departments_df["department_name"])

    # --- Reconciled months: actual aggregated spend from the fact tables. ---
    events = ai_events_df.copy()
    events["month"] = pd.to_datetime(events["timestamp"]).dt.to_period("M")
    event_cost = events.groupby(["month", "department"])["request_cost"].sum()

    calls = mcp_tool_calls_df.copy()
    calls["month"] = pd.to_datetime(calls["timestamp"]).dt.to_period("M")
    call_cost = calls.groupby(["month", "department"])["cost"].sum()

    rows = []
    reconciled_totals = {}
    for month in reconciled_months:
        month_total = 0.0
        for dept in departments:
            cost = event_cost.get((month, dept), 0.0) + call_cost.get((month, dept), 0.0)
            month_total += cost
            rows.append({"month": str(month), "department": dept, "total_cost": round(float(cost), 2)})
        reconciled_totals[month] = month_total

    # --- Synthetic backfill: smooth growth trend leading into the first reconciled month. ---
    # Department cost-share must come from *actual* reconciled spend, not from
    # event-volume weights (headcount x usage_multiplier) — cost-per-event varies
    # a lot by department (e.g. Operations is high-volume but short/cheap prompts),
    # so a volume-weighted share would put a visible discontinuity right at the
    # synthetic/reconciled boundary instead of a smooth trend line.
    first_reconciled_month = reconciled_months[0]
    first_month_dept_cost = {
        dept: event_cost.get((first_reconciled_month, dept), 0.0)
        + call_cost.get((first_reconciled_month, dept), 0.0)
        for dept in departments
    }
    total_first_month_cost = sum(first_month_dept_cost.values())
    dept_share = {dept: c / total_first_month_cost for dept, c in first_month_dept_cost.items()}

    first_reconciled_total = reconciled_totals[reconciled_months[0]]
    running_total = first_reconciled_total
    synthetic_totals = {}
    for month in reversed(synthetic_months):
        noise = rng.normal(1.0, GROWTH_NOISE_SIGMA)
        running_total = running_total / (1 + MONTHLY_GROWTH_RATE) * noise
        synthetic_totals[month] = running_total

    for month in synthetic_months:
        month_total = synthetic_totals[month]
        for dept in departments:
            share_noise = rng.normal(1.0, 0.03)
            cost = month_total * dept_share[dept] * share_noise
            rows.append({"month": str(month), "department": dept, "total_cost": round(float(cost), 2)})

    df = pd.DataFrame(rows)
    df["month"] = pd.Categorical(df["month"], categories=[str(m) for m in all_months], ordered=True)
    df = df.sort_values(["month", "department"]).reset_index(drop=True)
    df["month"] = df["month"].astype(str)
    return df
