"""Generates departments.csv.

Department headcount is an org-structure fact (simulation/profiles), distinct
from usage behavior (simulation/behavior) — see the module docstrings on each.
"""

from __future__ import annotations

import pandas as pd

DEPARTMENT_CODES = {
    "Engineering": "ENG",
    "Finance": "FIN",
    "Sales": "SAL",
    "Marketing": "MKT",
    "HR": "HR",
    "Legal": "LEG",
    "IT": "IT",
    "Operations": "OPS",
    "Security": "SEC",
    "Procurement": "PRO",
}


def generate(profile) -> pd.DataFrame:
    departments = list(profile.departments)
    weights = profile.department_headcount_weights

    counts = {dept: round(profile.employee_count * weights[dept]) for dept in departments}
    # Reconcile rounding drift against the exact target headcount.
    drift = profile.employee_count - sum(counts.values())
    if drift != 0:
        largest = max(counts, key=counts.get)
        counts[largest] += drift

    rows = []
    for dept in departments:
        code = DEPARTMENT_CODES[dept]
        rows.append(
            {
                "department_id": code,
                "department_name": dept,
                "employee_count": counts[dept],
                "cost_center": f"CC-{code}",
            }
        )
    return pd.DataFrame(rows)
