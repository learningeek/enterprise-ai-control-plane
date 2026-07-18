"""Generates shadow_ai.csv per docs/01-domain/shadow-ai.md.

Dataset shape: employee, tool, approved. Sampling weight per department is
BEHAVIOR_RULES[department].shadow_ai_affinity — departments the behavior model
marks as less AI-governance-aware (Sales, Marketing, HR) show up more often,
security-conscious departments (Security, Legal) less often.
"""

from __future__ import annotations

import pandas as pd

from simulation.behavior import BEHAVIOR_RULES
from simulation.generators.base import get_rng, weighted_choice

UNSANCTIONED_TOOLS = {
    "ChatGPT (personal account)": 0.35,
    "Claude.ai (personal account)": 0.20,
    "Google Gemini (personal account)": 0.15,
    "Perplexity": 0.10,
    "DeepSeek": 0.08,
    "Character.AI": 0.05,
    "Personal Midjourney account": 0.04,
    "Unapproved browser extension AI assistant": 0.03,
}

# Most shadow usage is unapproved by construction; a small slice has an
# exception approval on file (e.g. a time-boxed pilot).
APPROVED_WEIGHTS = {"no": 0.90, "yes": 0.10}


def generate(profile, users_df: pd.DataFrame) -> pd.DataFrame:
    rng = get_rng(profile, "shadow_ai")

    weights = users_df["department"].map(lambda d: BEHAVIOR_RULES[d].shadow_ai_affinity).to_numpy(dtype=float)
    weights = weights / weights.sum()

    n = profile.shadow_ai_sample_size
    sampled_idx = rng.choice(users_df.index.to_numpy(), size=n, replace=False, p=weights)
    sampled = users_df.loc[sampled_idx]

    tools = weighted_choice(rng, UNSANCTIONED_TOOLS, n)
    approved = weighted_choice(rng, APPROVED_WEIGHTS, n)

    return pd.DataFrame(
        {
            "employee": sampled["user_id"].to_numpy(),
            "employee_name": sampled["name"].to_numpy(),
            "department": sampled["department"].to_numpy(),
            "tool": tools,
            "approved": approved,
        }
    )
