"""Generates ai_events.csv — the AIUsageEvent fact table — per specs/event-schema.md.

Respects docs/04-simulation/behavior-model.md via simulation/behavior/behavior_rules.py:
department usage volume, token/context shape, task-category mix, provider affinity,
and governance strictness are all read from BEHAVIOR_RULES rather than hardcoded here.

Generation is department-by-department (10 iterations) with vectorized numpy
sampling within each department, rather than a 100K-500K row Python loop.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from simulation.behavior import BEHAVIOR_RULES
from simulation.generators.base import get_rng, sample_timestamps, weighted_choice
from simulation.generators.models import MODEL_SELECTION_WEIGHT

CATEGORY_TOKEN_MULTIPLIERS = {
    "code generation": {"prompt": 1.1, "completion": 1.3},
    "document summarization": {"prompt": 1.6, "completion": 1.1},
    "translation": {"prompt": 1.0, "completion": 1.0},
    "email drafting": {"prompt": 0.7, "completion": 0.8},
    "SQL generation": {"prompt": 0.6, "completion": 0.5},
    "customer support": {"prompt": 0.5, "completion": 0.6},
}

# Providers reachable directly over the public internet (vs. an enterprise-controlled
# deployment) — used only to weight the "confidential doc uploaded to a public model"
# incident signal. See simulation/generators/incidents.py.
PUBLIC_PROVIDERS = {"OpenAI", "Anthropic"}

DATA_CLASSIFICATIONS = ("public", "internal", "confidential")

def _sample_outcome(rng: np.random.Generator, blocked_prob: np.ndarray, error_prob: np.ndarray) -> np.ndarray:
    draw = rng.random(len(blocked_prob))
    outcome = np.where(
        draw < blocked_prob,
        "blocked",
        np.where(draw < blocked_prob + error_prob, "error", "success"),
    )
    return outcome


def generate(profile, users_df: pd.DataFrame, applications_df: pd.DataFrame, models_df: pd.DataFrame,
             mcp_servers_df: pd.DataFrame) -> pd.DataFrame:
    rng = get_rng(profile, "ai_events")

    # Month-aligned window (not a rolling N-day window) so monthly_costs.py can
    # reconcile its most recent months exactly against these events.
    end = pd.Timestamp(profile.simulation_end_date)
    start = (end - pd.DateOffset(months=profile.event_period_months - 1)).replace(day=1)

    models_by_provider: dict[str, list[str]] = {}
    model_pricing: dict[str, tuple[float, float]] = {}
    model_context: dict[str, int] = {}
    model_approved: dict[str, bool] = {}
    for _, m in models_df.iterrows():
        models_by_provider.setdefault(m["provider"], []).append(m["model_id"])
        model_pricing[m["model_id"]] = (m["input_cost_per_1M"], m["output_cost_per_1M"])
        model_context[m["model_id"]] = m["max_context"]
        model_approved[m["model_id"]] = bool(m["approved"])

    mcp_by_owner: dict[str, pd.DataFrame] = {
        dept: grp for dept, grp in mcp_servers_df.groupby("owner")
    }

    # Department event-volume shares: headcount x behavior usage_multiplier.
    dept_counts = users_df.groupby("department").size()
    dept_weight = {
        dept: dept_counts[dept] * BEHAVIOR_RULES[dept].usage_multiplier for dept in dept_counts.index
    }
    total_weight = sum(dept_weight.values())
    dept_event_counts = {
        dept: int(round(profile.ai_event_count * w / total_weight)) for dept, w in dept_weight.items()
    }
    drift = profile.ai_event_count - sum(dept_event_counts.values())
    if drift != 0:
        largest = max(dept_event_counts, key=dept_event_counts.get)
        dept_event_counts[largest] += drift

    frames = []
    event_counter = 1

    for dept, n in dept_event_counts.items():
        if n == 0:
            continue
        rule = BEHAVIOR_RULES[dept]
        dept_users = users_df.loc[users_df["department"] == dept, "user_id"].to_numpy()

        # Per-user activity heterogeneity within a department (not everyone is equally active).
        activity = rng.lognormal(mean=0.0, sigma=0.6, size=len(dept_users))
        activity = activity / activity.sum()
        user_ids = rng.choice(dept_users, size=n, p=activity)

        timestamps = sample_timestamps(rng, n, start, end)

        task_categories = weighted_choice(rng, rule.task_weights, n)
        providers = weighted_choice(rng, rule.provider_affinity, n)

        model_ids = np.empty(n, dtype=object)
        for provider in np.unique(providers):
            mask = providers == provider
            count = int(mask.sum())
            candidates = models_by_provider[provider]
            weights = {mid: MODEL_SELECTION_WEIGHT[mid] for mid in candidates}
            model_ids[mask] = weighted_choice(rng, weights, count)

        prompt_mult = np.array([CATEGORY_TOKEN_MULTIPLIERS[c]["prompt"] for c in task_categories])
        completion_mult = np.array([CATEGORY_TOKEN_MULTIPLIERS[c]["completion"] for c in task_categories])

        prompt_tokens = rng.lognormal(
            mean=np.log(rule.avg_prompt_tokens * prompt_mult), sigma=0.4
        ).astype(int)
        completion_tokens = rng.lognormal(
            mean=np.log(rule.avg_completion_tokens * completion_mult), sigma=0.4
        ).astype(int)
        prompt_tokens = np.clip(prompt_tokens, 20, None)
        completion_tokens = np.clip(completion_tokens, 10, None)

        # Never let prompt+completion exceed the chosen model's context window.
        max_ctx = np.array([model_context[m] for m in model_ids])
        total_tokens = prompt_tokens + completion_tokens
        over = total_tokens > (max_ctx * 0.9)
        if over.any():
            scale = (max_ctx[over] * 0.9) / total_tokens[over]
            prompt_tokens[over] = (prompt_tokens[over] * scale).astype(int)
            completion_tokens[over] = (completion_tokens[over] * scale).astype(int)

        input_cost = np.array([model_pricing[m][0] for m in model_ids])
        output_cost = np.array([model_pricing[m][1] for m in model_ids])
        request_cost = (prompt_tokens / 1_000_000) * input_cost + (completion_tokens / 1_000_000) * output_cost

        latency_base = 200 + completion_tokens * 2.5
        latency_ms = rng.lognormal(mean=np.log(latency_base), sigma=0.3).astype(int)

        conf_rate = rule.confidential_rate
        classification_weights = np.column_stack(
            [
                np.full(n, 0.4 * (1 - conf_rate)),  # public
                np.full(n, 0.6 * (1 - conf_rate)),  # internal
                np.full(n, conf_rate),  # confidential
            ]
        )
        classification_idx = np.array(
            [rng.choice(3, p=classification_weights[i] / classification_weights[i].sum()) for i in range(n)]
        )
        data_classification = np.array(DATA_CLASSIFICATIONS)[classification_idx]

        # Applications: company-wide apps are usable by every department; otherwise
        # restricted to apps this department owns.
        dept_apps = applications_df.loc[
            (applications_df["owner_team"] == dept) | (applications_df["company_wide"]), "app_id"
        ].to_numpy()
        if len(dept_apps) == 0:
            dept_apps = applications_df["app_id"].to_numpy()
        application_ids = rng.choice(dept_apps, size=n)

        # MCP tool usage on the event itself (distinct from the mcp_tool_calls fact
        # table, which is agent-centric) — see specs/event-schema.md `mcp_tool_used`.
        mcp_prob = np.clip(0.06 * rule.mcp_affinity, 0.0, 0.35)
        uses_mcp = rng.random(n) < mcp_prob
        mcp_tool_used = np.full(n, None, dtype=object)
        candidate_servers = mcp_by_owner.get(dept, mcp_servers_df)
        if len(candidate_servers) == 0:
            candidate_servers = mcp_servers_df
        if uses_mcp.any():
            chosen_rows = candidate_servers.sample(
                n=int(uses_mcp.sum()), replace=True, random_state=rng.integers(0, 2**31 - 1)
            )
            tool_choices = [
                f"{row.service_type}:{rng.choice(row.tools.split(';'))}" for row in chosen_rows.itertuples()
            ]
            mcp_tool_used[uses_mcp] = tool_choices

        not_approved = np.array([not model_approved[m] for m in model_ids])
        is_public_confidential = (data_classification == "confidential") & np.isin(providers, list(PUBLIC_PROVIDERS))
        blocked_prob = np.full(n, rule.blocked_rate) + np.where(not_approved, 0.05, 0.0) + np.where(
            is_public_confidential, 0.03, 0.0
        )
        error_prob = np.full(n, rule.error_rate)
        outcome = _sample_outcome(rng, blocked_prob, error_prob)

        event_ids = [f"EVT{event_counter + i:08d}" for i in range(n)]
        event_counter += n

        frames.append(
            pd.DataFrame(
                {
                    "event_id": event_ids,
                    "schema_version": 1,
                    "timestamp": timestamps.to_numpy(),
                    "tenant_id": profile.tenant_id,
                    "user_id": user_ids,
                    "department": dept,
                    "application_id": application_ids,
                    "provider": providers,
                    "model": model_ids,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "latency_ms": latency_ms,
                    "request_cost": request_cost.round(6),
                    "data_classification": data_classification,
                    "mcp_tool_used": mcp_tool_used,
                    "outcome": outcome,
                }
            )
        )

    events = pd.concat(frames, ignore_index=True)
    events = events.sort_values("timestamp").reset_index(drop=True)
    return events
