"""Generates incidents.csv per docs/04-simulation/incident-generator.md.

Every incident is sampled from real rows in ai_events.csv/monthly_costs.csv —
never fabricated independently — so there's no incident without a matching
event, per the simulation-engineer agent's "never generate impossible
scenarios" rule. Sampling weight is `BEHAVIOR_RULES[department].incident_multiplier`,
so stricter-governance departments (Finance, Legal, Security) really do produce
proportionally more incidents, per docs/04-simulation/behavior-model.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from simulation.behavior import BEHAVIOR_RULES
from simulation.generators.ai_events import PUBLIC_PROVIDERS
from simulation.generators.base import get_rng

STATUS_WEIGHTS = {"Open": 0.25, "Under Review": 0.20, "Resolved": 0.55}

TYPE_SHARE = {
    "Confidential document uploaded to a public AI model": 0.40,
    "Non-approved model used": 0.35,
    "Excessive token usage / budget alert": 0.25,
}


def _weighted_sample_no_replace(rng: np.random.Generator, pool: pd.DataFrame, n: int, weight_col: str) -> pd.DataFrame:
    n = min(n, len(pool))
    if n == 0:
        return pool.iloc[0:0]
    weights = pool[weight_col].to_numpy(dtype=float)
    weights = weights / weights.sum()
    idx = rng.choice(pool.index.to_numpy(), size=n, replace=False, p=weights)
    return pool.loc[idx]


def generate(profile, ai_events_df: pd.DataFrame, models_df: pd.DataFrame,
             monthly_costs_df: pd.DataFrame, billing_accounts_df: pd.DataFrame) -> pd.DataFrame:
    rng = get_rng(profile, "incidents")

    events = ai_events_df.copy()
    events["incident_weight"] = events["department"].map(lambda d: BEHAVIOR_RULES[d].incident_multiplier)

    rows = []
    idx = 1

    # --- Type A: confidential document uploaded to a public AI model (High) ---
    n_a = round(profile.incident_count * TYPE_SHARE["Confidential document uploaded to a public AI model"])
    pool_a = events[
        (events["data_classification"] == "confidential") & (events["provider"].isin(PUBLIC_PROVIDERS))
    ]
    sample_a = _weighted_sample_no_replace(rng, pool_a, n_a, "incident_weight")
    for _, e in sample_a.iterrows():
        rows.append(
            {
                "incident_id": f"INC{idx:06d}",
                "timestamp": e["timestamp"],
                "type": "Confidential document uploaded to a public AI model",
                "severity": "High",
                "department": e["department"],
                "user_id": e["user_id"],
                "related_event_id": e["event_id"],
                "description": (
                    f"User {e['user_id']} sent confidential-classified content to {e['provider']} "
                    f"({e['model']}) via application {e['application_id']}."
                ),
                "status": rng.choice(list(STATUS_WEIGHTS.keys()), p=list(STATUS_WEIGHTS.values())),
            }
        )
        idx += 1

    # --- Type C: non-approved model used (High) ---
    approved_by_model = dict(zip(models_df["model_id"], models_df["approved"]))
    n_c = round(profile.incident_count * TYPE_SHARE["Non-approved model used"])
    pool_c = events[~events["model"].map(approved_by_model)]
    sample_c = _weighted_sample_no_replace(rng, pool_c, n_c, "incident_weight")
    for _, e in sample_c.iterrows():
        rows.append(
            {
                "incident_id": f"INC{idx:06d}",
                "timestamp": e["timestamp"],
                "type": "Non-approved model used",
                "severity": "High",
                "department": e["department"],
                "user_id": e["user_id"],
                "related_event_id": e["event_id"],
                "description": (
                    f"User {e['user_id']} used non-approved model {e['model']} in application "
                    f"{e['application_id']}."
                ),
                "status": rng.choice(list(STATUS_WEIGHTS.keys()), p=list(STATUS_WEIGHTS.values())),
            }
        )
        idx += 1

    # --- Type B: excessive token usage / budget alert (Medium) ---
    n_b = profile.incident_count - len(rows)
    dept_budget = billing_accounts_df.groupby("department")["monthly_budget"].sum()
    monthly = monthly_costs_df.copy()
    monthly["budget"] = monthly["department"].map(dept_budget).fillna(0.0)
    monthly = monthly[monthly["budget"] > 0]
    monthly["usage_ratio"] = monthly["total_cost"] / monthly["budget"]
    monthly["incident_weight"] = (
        monthly["usage_ratio"].clip(lower=0.01)
        * monthly["department"].map(lambda d: BEHAVIOR_RULES[d].incident_multiplier)
    )
    sample_b = _weighted_sample_no_replace(rng, monthly, n_b, "incident_weight")
    for _, m in sample_b.iterrows():
        month_ts = pd.Period(m["month"], freq="M").end_time.floor("s")
        rows.append(
            {
                "incident_id": f"INC{idx:06d}",
                "timestamp": month_ts,
                "type": "Excessive token usage / budget alert",
                "severity": "Medium",
                "department": m["department"],
                "user_id": "",
                "related_event_id": "",
                "description": (
                    f"{m['department']} spent ${m['total_cost']:,.2f} against a ${m['budget']:,.2f} "
                    f"monthly budget in {m['month']} ({m['usage_ratio'] * 100:.0f}% of budget)."
                ),
                "status": rng.choice(list(STATUS_WEIGHTS.keys()), p=list(STATUS_WEIGHTS.values())),
            }
        )
        idx += 1

    df = pd.DataFrame(rows)
    return df.sort_values("timestamp").reset_index(drop=True)
