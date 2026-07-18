"""Generates sso_groups.csv per docs/01-domain/users.md (`identity_provider` attribute).

Derived from users.csv rather than sampled independently, so member_count always
matches the number of users actually assigned to each group — one department
group per department (from `users.identity_provider`) plus the cross-cutting
groups assigned in simulation/generators/users.py (`additional_groups`).
"""

from __future__ import annotations

import pandas as pd

from simulation.generators.departments import DEPARTMENT_CODES


def generate(users_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    idx = 1

    dept_group_counts = users_df["identity_provider"].value_counts()
    for dept, code in DEPARTMENT_CODES.items():
        group_name = f"{code}-AllStaff"
        identity_provider_value = f"EntraID:{group_name}"
        rows.append(
            {
                "group_id": f"SSO{idx:03d}",
                "group_name": group_name,
                "identity_provider": "Entra ID",
                "department": dept,
                "member_count": int(dept_group_counts.get(identity_provider_value, 0)),
            }
        )
        idx += 1

    cross_cutting = users_df["additional_groups"].fillna("").str.split(";")
    all_tags = sorted({tag for tags in cross_cutting for tag in tags if tag})
    for tag in all_tags:
        member_count = cross_cutting.apply(lambda tags: tag in tags).sum()
        rows.append(
            {
                "group_id": f"SSO{idx:03d}",
                "group_name": tag,
                "identity_provider": "Entra ID",
                "department": "",
                "member_count": int(member_count),
            }
        )
        idx += 1

    return pd.DataFrame(rows)
