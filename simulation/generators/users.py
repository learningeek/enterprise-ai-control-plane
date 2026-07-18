"""Generates users.csv per docs/01-domain/users.md.

Users are synced from SSO in the real product (not manually managed) — here that
just means each user gets an identity_provider group assignment that
simulation/generators/sso_groups.py later aggregates into sso_groups.csv.
"""

from __future__ import annotations

import pandas as pd

from simulation.generators.base import get_faker, get_rng, weighted_choice
from simulation.generators.departments import DEPARTMENT_CODES

TIER_WEIGHTS = {"IC": 0.80, "Manager": 0.15, "Director/VP": 0.05}

TITLE_POOL = {
    "IC": ["Analyst", "Senior Analyst", "Specialist", "Associate", "Senior Associate"],
    "Manager": ["Manager", "Senior Manager"],
    "Director/VP": ["Director", "VP"],
}


def _titles_for(dept: str, tier: str, rng) -> str:
    role = rng.choice(TITLE_POOL[tier])
    return f"{role}, {dept}"


def generate(profile, departments_df: pd.DataFrame) -> pd.DataFrame:
    rng = get_rng(profile, "users")
    faker = get_faker(profile, "users")

    rows = []
    uid = 1
    for _, dept_row in departments_df.iterrows():
        dept = dept_row["department_name"]
        code = DEPARTMENT_CODES[dept]
        n = int(dept_row["employee_count"])

        tiers = weighted_choice(rng, TIER_WEIGHTS, n)
        countries = weighted_choice(rng, profile.countries, n)

        dept_user_ids = []
        head_assigned = False
        for i in range(n):
            user_id = f"U{uid:06d}"
            uid += 1
            tier = tiers[i]
            # First Director/VP encountered per department becomes the head,
            # reporting to nobody (top of that department's hierarchy).
            if tier == "Director/VP" and not head_assigned:
                tier_label = "Head"
                manager_placeholder = ""
                head_assigned = True
            else:
                tier_label = tier
                manager_placeholder = None  # resolved in a second pass below

            title = (
                f"Head of {dept}" if tier_label == "Head" else _titles_for(dept, tier, rng)
            )

            rows.append(
                {
                    "user_id": user_id,
                    "name": faker.name(),
                    "department": dept,
                    "title": title,
                    "tier": tier_label,
                    "manager": manager_placeholder,
                    "country": countries[i],
                    "cost_center": f"CC-{code}",
                    "identity_provider": f"EntraID:{code}-AllStaff",
                }
            )
            dept_user_ids.append(user_id)

        # Second pass: assign managers within this department now that the
        # full roster (and its tiers) is known. Everyone but the head reports
        # to a randomly chosen manager-tier colleague (or the head itself).
        dept_rows = rows[-n:]
        manager_pool = [r["user_id"] for r in dept_rows if r["tier"] in ("Head", "Manager", "Director/VP")]
        for r in dept_rows:
            if r["tier"] == "Head":
                continue
            candidates = [m for m in manager_pool if m != r["user_id"]] or [dept_rows[0]["user_id"]]
            r["manager"] = rng.choice(candidates)

    df = pd.DataFrame(rows)

    # Cross-cutting SSO groups layered on top of the per-department group,
    # consumed by simulation/generators/sso_groups.py.
    power_user_mask = rng.random(len(df)) < 0.05
    mcp_admin_mask = rng.random(len(df)) < 0.01
    leadership_mask = df["tier"].isin(["Head", "Director/VP"])

    extra_groups = []
    for pu, mcp, lead in zip(power_user_mask, mcp_admin_mask, leadership_mask):
        groups = []
        if pu:
            groups.append("AI-Power-Users")
        if mcp:
            groups.append("MCP-Admins")
        if lead:
            groups.append("Executive-Leadership")
        extra_groups.append(";".join(groups))
    df["additional_groups"] = extra_groups

    return df.drop(columns=["tier"])
