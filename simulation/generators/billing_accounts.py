"""Generates billing_accounts.csv per docs/01-domain/billing.md.

One account per (provider, department-cost-center) pair that actually has
material spend with that provider — avoids inventing accounts for combinations
nobody uses. `monthly_budget` is sized off that pair's real average monthly
spend in ai_events.csv (with headroom), so budget-vs-actual dashboards show a
mix of comfortably-under-budget and over-budget accounts rather than arbitrary
numbers.
"""

from __future__ import annotations

import pandas as pd

from simulation.behavior import BEHAVIOR_RULES
from simulation.generators.base import get_rng

# Minimum provider_affinity weight for a department to warrant its own billing account.
AFFINITY_THRESHOLD = 0.10
BUDGET_HEADROOM = 1.20


def generate(profile, ai_events_df: pd.DataFrame, departments_df: pd.DataFrame) -> pd.DataFrame:
    rng = get_rng(profile, "billing_accounts")

    events = ai_events_df.copy()
    events["month"] = pd.to_datetime(events["timestamp"]).dt.to_period("M")
    n_months = events["month"].nunique() or profile.event_period_months
    spend = events.groupby(["provider", "department"])["request_cost"].sum() / n_months

    dept_cost_center = dict(zip(departments_df["department_name"], departments_df["cost_center"]))

    rows = []
    idx = 1
    for dept, rule in BEHAVIOR_RULES.items():
        for provider, weight in rule.provider_affinity.items():
            if weight < AFFINITY_THRESHOLD:
                continue
            avg_monthly_spend = float(spend.get((provider, dept), 0.0))
            if avg_monthly_spend <= 0:
                continue
            budget_noise = rng.normal(1.0, 0.08)
            monthly_budget = round(avg_monthly_spend * BUDGET_HEADROOM * budget_noise, 2)
            rows.append(
                {
                    "account_id": f"BILL{idx:04d}",
                    "provider": provider,
                    "account": f"{provider.replace(' ', '-').lower()}-{dept_cost_center[dept].lower()}",
                    "cost_center": dept_cost_center[dept],
                    "department": dept,
                    "monthly_budget": monthly_budget,
                }
            )
            idx += 1

    return pd.DataFrame(rows)
