"""Behavior model: how the simulated enterprise actually behaves.

Implements docs/04-simulation/behavior-model.md as an explicit, editable ruleset —
the generators in simulation/generators/ read from BEHAVIOR_RULES rather than
encoding department-specific numbers inline. Extend/adjust the numbers here, not
in generator logic.

Mapping note: behavior-model.md's example rule is written for "Customer Support",
but docs/04-simulation/enterprise-profile.md's fixed 10-department list has no
"Customer Support" department — it has "Operations" instead. We apply the
Customer Support rule (high volume, short prompts) to the Operations department,
since customer support functions typically sit inside Operations in a Fortune 500
org chart. This mapping is called out here rather than silently baked into the
numbers.

All `task_weights` dicts sum to 1.0 across simulation/profiles' `task_categories`.
All `provider_affinity` dicts sum to 1.0 across simulation/profiles' `providers`.
`usage_multiplier` is relative daily-usage-per-employee, HR = 1.0 baseline —
behavior-model.md's example ratio is Engineering ~= 8x HR, which is exact here so
simulation/statistics/consistency_checks.py can assert it directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BehaviorRule:
    # Relative usage volume per employee. HR = 1.0 is the baseline.
    usage_multiplier: float

    # Governance strictness: probability an event's outcome is "blocked"/"error".
    blocked_rate: float
    error_rate: float

    # Relative multiplier applied on top of volume-driven incident sampling —
    # how much more (or less) prone this department is to governance incidents.
    incident_multiplier: float

    # Prompt/completion token shape (e.g. Legal = long documents, Operations = short).
    avg_prompt_tokens: int
    avg_completion_tokens: int

    # Probability an event's data_classification is "confidential" (rest split
    # between "public" and "internal" — see ai_events generator).
    confidential_rate: float

    # Relative likelihood this department's traffic touches an MCP tool.
    mcp_affinity: float

    # Relative likelihood this department's employees use unsanctioned (shadow) AI.
    shadow_ai_affinity: float

    # Distribution over simulation/profiles' task_categories. Must sum to 1.0.
    task_weights: dict = field(default_factory=dict)

    # Distribution over simulation/profiles' providers. Must sum to 1.0.
    provider_affinity: dict = field(default_factory=dict)


BEHAVIOR_RULES: dict[str, BehaviorRule] = {
    "Engineering": BehaviorRule(
        usage_multiplier=8.0,
        blocked_rate=0.015,
        error_rate=0.012,
        incident_multiplier=1.0,
        avg_prompt_tokens=750,
        avg_completion_tokens=550,
        confidential_rate=0.10,
        mcp_affinity=1.8,
        shadow_ai_affinity=0.8,
        task_weights={
            "code generation": 0.55,
            "SQL generation": 0.20,
            "document summarization": 0.10,
            "email drafting": 0.05,
            "translation": 0.02,
            "customer support": 0.08,
        },
        provider_affinity={
            "OpenAI": 0.35,
            "Anthropic": 0.30,
            "Azure OpenAI": 0.10,
            "AWS Bedrock": 0.15,
            "Internal": 0.10,
        },
    ),
    "IT": BehaviorRule(
        usage_multiplier=4.5,
        blocked_rate=0.020,
        error_rate=0.015,
        incident_multiplier=1.3,
        avg_prompt_tokens=500,
        avg_completion_tokens=350,
        confidential_rate=0.12,
        mcp_affinity=1.6,
        shadow_ai_affinity=0.6,
        task_weights={
            "code generation": 0.35,
            "SQL generation": 0.25,
            "customer support": 0.20,
            "document summarization": 0.10,
            "email drafting": 0.05,
            "translation": 0.05,
        },
        provider_affinity={
            "OpenAI": 0.25,
            "Azure OpenAI": 0.30,
            "AWS Bedrock": 0.20,
            "Anthropic": 0.15,
            "Internal": 0.10,
        },
    ),
    "Sales": BehaviorRule(
        usage_multiplier=3.0,
        blocked_rate=0.015,
        error_rate=0.010,
        incident_multiplier=1.0,
        avg_prompt_tokens=300,
        avg_completion_tokens=200,
        confidential_rate=0.08,
        mcp_affinity=1.1,
        shadow_ai_affinity=1.3,
        task_weights={
            "email drafting": 0.40,
            "document summarization": 0.15,
            "translation": 0.10,
            "customer support": 0.20,
            "code generation": 0.05,
            "SQL generation": 0.10,
        },
        provider_affinity={
            "OpenAI": 0.40,
            "Anthropic": 0.25,
            "Azure OpenAI": 0.20,
            "AWS Bedrock": 0.10,
            "Internal": 0.05,
        },
    ),
    "Marketing": BehaviorRule(
        usage_multiplier=2.2,
        blocked_rate=0.015,
        error_rate=0.010,
        incident_multiplier=1.0,
        avg_prompt_tokens=350,
        avg_completion_tokens=280,
        confidential_rate=0.05,
        mcp_affinity=0.7,
        shadow_ai_affinity=1.4,
        task_weights={
            "email drafting": 0.35,
            "translation": 0.20,
            "document summarization": 0.25,
            "customer support": 0.10,
            "code generation": 0.05,
            "SQL generation": 0.05,
        },
        provider_affinity={
            "OpenAI": 0.40,
            "Anthropic": 0.30,
            "Azure OpenAI": 0.15,
            "AWS Bedrock": 0.10,
            "Internal": 0.05,
        },
    ),
    "HR": BehaviorRule(
        usage_multiplier=1.0,  # baseline
        blocked_rate=0.012,
        error_rate=0.010,
        incident_multiplier=1.0,
        avg_prompt_tokens=320,
        avg_completion_tokens=220,
        confidential_rate=0.15,  # PII-heavy
        mcp_affinity=0.6,
        shadow_ai_affinity=1.2,
        task_weights={
            "email drafting": 0.45,
            "document summarization": 0.30,
            "translation": 0.05,
            "customer support": 0.10,
            "code generation": 0.03,
            "SQL generation": 0.07,
        },
        provider_affinity={
            "Azure OpenAI": 0.40,
            "OpenAI": 0.25,
            "Anthropic": 0.15,
            "Internal": 0.15,
            "AWS Bedrock": 0.05,
        },
    ),
    "Legal": BehaviorRule(
        usage_multiplier=0.6,  # fewer requests
        blocked_rate=0.040,  # stricter governance
        error_rate=0.010,
        incident_multiplier=2.5,
        avg_prompt_tokens=3400,  # long documents
        avg_completion_tokens=850,
        confidential_rate=0.35,
        mcp_affinity=0.5,
        shadow_ai_affinity=0.4,
        task_weights={
            "document summarization": 0.55,
            "email drafting": 0.20,
            "translation": 0.10,
            "customer support": 0.05,
            "code generation": 0.02,
            "SQL generation": 0.08,
        },
        provider_affinity={
            "Azure OpenAI": 0.50,
            "Internal": 0.30,
            "Anthropic": 0.12,
            "OpenAI": 0.05,
            "AWS Bedrock": 0.03,
        },
    ),
    "Finance": BehaviorRule(
        usage_multiplier=1.6,
        blocked_rate=0.045,  # stricter governance
        error_rate=0.010,
        incident_multiplier=3.0,
        avg_prompt_tokens=900,
        avg_completion_tokens=400,
        confidential_rate=0.25,
        mcp_affinity=1.0,
        shadow_ai_affinity=0.5,
        task_weights={
            "SQL generation": 0.35,
            "document summarization": 0.30,
            "email drafting": 0.20,
            "code generation": 0.05,
            "translation": 0.02,
            "customer support": 0.08,
        },
        provider_affinity={
            "Azure OpenAI": 0.45,
            "Internal": 0.25,
            "Anthropic": 0.15,
            "OpenAI": 0.10,
            "AWS Bedrock": 0.05,
        },
    ),
    "Operations": BehaviorRule(  # Customer Support mapping — see module docstring
        usage_multiplier=5.5,  # high volume
        blocked_rate=0.010,
        error_rate=0.012,
        incident_multiplier=0.8,
        avg_prompt_tokens=120,  # short prompts
        avg_completion_tokens=140,
        confidential_rate=0.05,
        mcp_affinity=1.3,
        shadow_ai_affinity=0.7,
        task_weights={
            "customer support": 0.55,
            "email drafting": 0.15,
            "document summarization": 0.15,
            "SQL generation": 0.07,
            "code generation": 0.03,
            "translation": 0.05,
        },
        provider_affinity={
            "OpenAI": 0.30,
            "Azure OpenAI": 0.25,
            "AWS Bedrock": 0.20,
            "Anthropic": 0.15,
            "Internal": 0.10,
        },
    ),
    "Security": BehaviorRule(
        usage_multiplier=1.3,
        blocked_rate=0.035,
        error_rate=0.010,
        incident_multiplier=2.0,
        avg_prompt_tokens=700,
        avg_completion_tokens=400,
        confidential_rate=0.30,
        mcp_affinity=1.4,
        shadow_ai_affinity=0.3,
        task_weights={
            "document summarization": 0.35,
            "SQL generation": 0.25,
            "code generation": 0.20,
            "email drafting": 0.10,
            "customer support": 0.05,
            "translation": 0.05,
        },
        provider_affinity={
            "Internal": 0.35,
            "Azure OpenAI": 0.30,
            "AWS Bedrock": 0.15,
            "Anthropic": 0.15,
            "OpenAI": 0.05,
        },
    ),
    "Procurement": BehaviorRule(
        usage_multiplier=0.9,
        blocked_rate=0.020,
        error_rate=0.010,
        incident_multiplier=1.2,
        avg_prompt_tokens=400,
        avg_completion_tokens=280,
        confidential_rate=0.10,
        mcp_affinity=0.9,
        shadow_ai_affinity=0.6,
        task_weights={
            "email drafting": 0.35,
            "document summarization": 0.30,
            "SQL generation": 0.15,
            "customer support": 0.10,
            "code generation": 0.03,
            "translation": 0.07,
        },
        provider_affinity={
            "Azure OpenAI": 0.40,
            "Internal": 0.25,
            "OpenAI": 0.20,
            "Anthropic": 0.10,
            "AWS Bedrock": 0.05,
        },
    ),
}


def get_rule(department: str) -> BehaviorRule:
    return BEHAVIOR_RULES[department]
