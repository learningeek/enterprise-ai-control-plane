"""Generates policies.json per specs/governance-rules.md and docs/01-domain/governance.md.

Policy object shape per governance-rules.md: policy_id, policy, severity, action.
We add department (empty string for organization-wide policies) and category so
the governance dashboard can group/filter — additive fields, the three required
ones are unchanged. Department-scoped policies skew toward higher severity for
departments docs/04-simulation/behavior-model.md marks as stricter (Finance,
Legal, Security), consistent with simulation/behavior/behavior_rules.py.
"""

from __future__ import annotations

import pandas as pd

from simulation.generators.base import get_rng

SEVERITIES = ("Low", "Medium", "High")
ACTIONS = ("Allow", "Flag", "Block")

# (description, category, severity, action) — organization-wide.
GLOBAL_TEMPLATES = [
    ("Confidential documents may not be uploaded to public AI models", "data-classification", "High", "Block"),
    ("All AI usage must go through an approved, governed application", "shadow-ai", "Medium", "Flag"),
    ("Non-approved models may not be used in production applications", "model-approval", "High", "Block"),
    ("Personally identifiable information may not be shared with AI models without redaction", "data-classification", "High", "Block"),
    ("AI-generated code must be reviewed before merging to production", "code-review", "Medium", "Flag"),
    ("Source code may not be shared with public AI models outside approved coding assistants", "data-classification", "High", "Block"),
    ("Customer payment card data may not be sent to any AI model", "data-classification", "High", "Block"),
    ("Monthly AI spend exceeding department budget triggers a review", "budget", "Medium", "Flag"),
    ("MCP servers must use OAuth2 or service-account authentication", "mcp-governance", "Medium", "Flag"),
    ("Agents may only call MCP tools explicitly allow-listed for their role", "mcp-governance", "High", "Block"),
    ("Shadow AI tools such as personal ChatGPT or Claude accounts are not approved for company data", "shadow-ai", "Medium", "Flag"),
    ("AI usage logs must be retained for a minimum of 12 months", "compliance", "Low", "Allow"),
    ("New AI applications must complete a security review before go-live", "compliance", "Medium", "Flag"),
    ("Export of AI usage data outside the tenant boundary is prohibited", "data-classification", "High", "Block"),
    ("Contractors and third parties require explicit approval to use sanctioned AI tools", "shadow-ai", "Medium", "Flag"),
]

# (description_template, category, severity, action) — department-scoped.
DEPARTMENT_TEMPLATES = [
    ("{dept} users cannot upload confidential documents to public AI models", "data-classification", "High", "Block"),
    ("{dept} may only use enterprise-approved AI models for departmental data", "model-approval", "Medium", "Flag"),
    ("{dept} AI usage above 2x the department's average is flagged for review", "budget", "Medium", "Flag"),
    ("{dept} agents may only access MCP servers owned by {dept}", "mcp-governance", "Medium", "Flag"),
    ("{dept} confidential documents require Azure OpenAI or internal models only", "data-classification", "High", "Block"),
    ("{dept} employees using AI for external communication must use approved templates", "compliance", "Low", "Flag"),
    ("{dept} may not process data classified above Internal without approval", "data-classification", "High", "Block"),
    ("{dept} MCP tool calls accessing more than 1,000 records require additional logging", "mcp-governance", "Medium", "Flag"),
]

STRICT_DEPARTMENTS = {"Finance", "Legal", "Security"}
_SEVERITY_ESCALATE = {"Low": "Medium", "Medium": "High", "High": "High"}
_ACTION_ESCALATE = {"Allow": "Flag", "Flag": "Block", "Block": "Block"}


def generate(profile) -> list[dict]:
    rng = get_rng(profile, "policies")
    departments = list(profile.departments)

    policies = []
    idx = 1
    for description, category, severity, action in GLOBAL_TEMPLATES:
        policies.append(
            {
                "policy_id": f"POL{idx:03d}",
                "policy": description,
                "severity": severity,
                "action": action,
                "department": "",
                "category": category,
            }
        )
        idx += 1

    remaining = profile.policy_count - len(policies)
    per_dept = max(1, remaining // len(departments))

    for dept in departments:
        n = min(per_dept, len(DEPARTMENT_TEMPLATES))
        chosen = rng.choice(len(DEPARTMENT_TEMPLATES), size=n, replace=False)
        for template_idx in chosen:
            description, category, severity, action = DEPARTMENT_TEMPLATES[template_idx]
            if dept in STRICT_DEPARTMENTS and rng.random() < 0.5:
                severity = _SEVERITY_ESCALATE[severity]
                action = _ACTION_ESCALATE[action]
            policies.append(
                {
                    "policy_id": f"POL{idx:03d}",
                    "policy": description.format(dept=dept),
                    "severity": severity,
                    "action": action,
                    "department": dept,
                    "category": category,
                }
            )
            idx += 1

    # Top up to the exact target count with extra department templates if short.
    dept_cycle = 0
    while len(policies) < profile.policy_count:
        dept = departments[dept_cycle % len(departments)]
        template_idx = dept_cycle % len(DEPARTMENT_TEMPLATES)
        description, category, severity, action = DEPARTMENT_TEMPLATES[template_idx]
        policies.append(
            {
                "policy_id": f"POL{idx:03d}",
                "policy": description.format(dept=dept),
                "severity": severity,
                "action": action,
                "department": dept,
                "category": category,
            }
        )
        idx += 1
        dept_cycle += 1

    return policies[: profile.policy_count]
