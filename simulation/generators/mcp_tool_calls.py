"""Generates mcp_tool_calls.csv per docs/01-domain/mcp.md.

Field list per mcp.md: timestamp, agent, server, tool, duration_ms,
records_accessed, success. We add call_id/tenant_id/user_id/department/cost so
the full governance chain (User -> AI Agent -> MCP Server -> Tool Call -> Data
Access -> Cost, per docs/01-domain/mcp.md) is actually traceable in the data,
and so this table can be reconciled against monthly_costs.csv rather than
floating free of the rest of the dataset.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from simulation.behavior import BEHAVIOR_RULES
from simulation.generators.base import get_rng, sample_timestamps

SENSITIVITY_COST_MULTIPLIER = {"Low": 1.0, "Medium": 1.3, "High": 1.8}


def generate(profile, users_df: pd.DataFrame, mcp_servers_df: pd.DataFrame) -> pd.DataFrame:
    rng = get_rng(profile, "mcp_tool_calls")

    end = pd.Timestamp(profile.simulation_end_date)
    start = (end - pd.DateOffset(months=profile.event_period_months - 1)).replace(day=1)

    agent_weight = {
        (agent, dept): BEHAVIOR_RULES[dept].mcp_affinity for agent, dept in profile.agent_roster
    }
    total_weight = sum(agent_weight.values())
    agent_call_counts = {
        key: int(round(profile.mcp_tool_call_count * w / total_weight)) for key, w in agent_weight.items()
    }
    drift = profile.mcp_tool_call_count - sum(agent_call_counts.values())
    if drift != 0:
        largest = max(agent_call_counts, key=agent_call_counts.get)
        agent_call_counts[largest] += drift

    users_by_dept = {dept: grp["user_id"].to_numpy() for dept, grp in users_df.groupby("department")}
    servers_by_owner = {dept: grp for dept, grp in mcp_servers_df.groupby("owner")}

    frames = []
    call_counter = 1
    for (agent, dept), n in agent_call_counts.items():
        if n == 0:
            continue
        rule = BEHAVIOR_RULES[dept]

        candidate_servers = servers_by_owner.get(dept, mcp_servers_df)
        if len(candidate_servers) == 0:
            candidate_servers = mcp_servers_df
        chosen = candidate_servers.sample(n=n, replace=True, random_state=rng.integers(0, 2**31 - 1))

        tools = [rng.choice(row.tools.split(";")) for row in chosen.itertuples()]
        timestamps = sample_timestamps(rng, n, start, end)
        user_ids = rng.choice(users_by_dept[dept], size=n)

        duration_ms = rng.lognormal(mean=np.log(400), sigma=0.7, size=n).astype(int)
        records_accessed = rng.lognormal(mean=np.log(40), sigma=1.0, size=n).astype(int)
        records_accessed = np.clip(records_accessed, 0, None)

        sensitivity_mult = chosen["sensitivity"].map(SENSITIVITY_COST_MULTIPLIER).to_numpy()
        cost = (0.001 + duration_ms * 0.00002 + records_accessed * 0.0001) * sensitivity_mult

        fail_prob = np.clip(rule.error_rate + rule.blocked_rate * 0.3, 0.0, 0.5)
        success = rng.random(n) >= fail_prob

        call_ids = [f"MCPC{call_counter + i:08d}" for i in range(n)]
        call_counter += n

        frames.append(
            pd.DataFrame(
                {
                    "call_id": call_ids,
                    "tenant_id": profile.tenant_id,
                    "timestamp": timestamps.to_numpy(),
                    "user_id": user_ids,
                    "department": dept,
                    "agent": agent,
                    "server": chosen["server_id"].to_numpy(),
                    "tool": tools,
                    "duration_ms": duration_ms,
                    "records_accessed": records_accessed,
                    "success": success,
                    "cost": cost.round(6),
                }
            )
        )

    calls = pd.concat(frames, ignore_index=True)
    calls = calls.sort_values("timestamp").reset_index(drop=True)
    return calls
