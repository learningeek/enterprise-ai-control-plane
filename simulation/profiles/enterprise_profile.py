"""Enterprise profile: the simulation's tunable target parameters.

Implements the numbers in docs/04-simulation/enterprise-profile.md as an editable
config object rather than magic numbers scattered through generator code. Every
generator receives an `EnterpriseProfile` instance and reads its size targets from
here — nothing in simulation/generators/ should hardcode a headcount, app count,
or date range directly.

Note on "12 business units": enterprise-profile.md names 12 business units in
addition to the 10 listed departments, but no domain doc (docs/01-domain/) defines
a `business_unit` entity or attribute — `department` is the only organizational
dimension used by specs/event-schema.md and docs/01-domain/users.md. We record the
count here for fidelity to the profile doc but deliberately do not materialize a
`business_unit` column anywhere, since that would mean inventing an undocumented
data model (see docs/context.md: "documentation first").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class EnterpriseProfile:
    # --- Reproducibility -------------------------------------------------
    seed: int = 42

    # --- Tenant (specs/tenant-model.md: single tenant per deployment) ----
    tenant_id: str = "acme-corp"
    tenant_name: str = "Acme Corporation"

    # --- Org shape (docs/04-simulation/enterprise-profile.md) ------------
    employee_count: int = 25_000
    business_unit_count: int = 12  # descriptive only — see module docstring
    departments: tuple = (
        "Engineering",
        "Finance",
        "Sales",
        "Marketing",
        "HR",
        "Legal",
        "IT",
        "Operations",
        "Security",
        "Procurement",
    )
    # Relative headcount shape across departments. Not a behavior rule (that's
    # usage volume, see simulation/behavior/) — this is org structure. Must sum to 1.0.
    department_headcount_weights: dict = field(
        default_factory=lambda: {
            "Engineering": 0.18,
            "Sales": 0.16,
            "Operations": 0.15,
            "IT": 0.10,
            "Finance": 0.08,
            "Marketing": 0.08,
            "HR": 0.07,
            "Procurement": 0.06,
            "Security": 0.06,
            "Legal": 0.06,
        }
    )

    countries: dict = field(
        default_factory=lambda: {
            "United States": 0.55,
            "United Kingdom": 0.10,
            "India": 0.12,
            "Germany": 0.06,
            "Canada": 0.05,
            "Australia": 0.04,
            "Singapore": 0.03,
            "Brazil": 0.03,
            "Japan": 0.02,
        }
    )

    # --- Applications (docs/01-domain/applications.md) -------------------
    application_count: int = 260  # within the documented 200-300 range
    company_wide_app_fraction: float = 0.05

    # --- Agents & MCP (docs/01-domain/mcp.md) -----------------------------
    agent_count: int = 15
    mcp_server_count: int = 40

    # --- Providers (docs/01-domain/providers.md) --------------------------
    providers: tuple = ("OpenAI", "Azure OpenAI", "Anthropic", "AWS Bedrock", "Internal")

    # --- Events (specs/event-schema.md, docs/04-simulation/event-generator.md)
    ai_event_count: int = 500_000  # top of the documented 100K-500K range
    task_categories: tuple = (
        "code generation",
        "document summarization",
        "translation",
        "email drafting",
        "SQL generation",
        "customer support",
    )

    # --- Governance (docs/01-domain/governance.md) ------------------------
    policy_count: int = 75  # within the documented 50-100 range
    incident_count: int = 650

    # --- MCP tool calls -----------------------------------------------
    mcp_tool_call_count: int = 100_000

    # --- Shadow AI (docs/01-domain/shadow-ai.md) ---------------------------
    shadow_ai_sample_size: int = 900

    # --- Time (docs/04-simulation/forecast-generator.md, cost-model.md) ---
    # Fixed "as-of" date so runs are reproducible regardless of wall-clock time.
    simulation_end_date: date = date(2026, 6, 30)
    history_months: int = 12  # full monthly_costs.csv trend
    event_period_months: int = 3  # window ai_events/mcp_tool_calls are drawn from

    # --- Agent roster (used by mcp_tool_calls / MCP governance chain) -----
    agent_roster: tuple = (
        ("Code Review Agent", "Engineering"),
        ("DevOps Automation Agent", "Engineering"),
        ("Data Pipeline Agent", "IT"),
        ("IT Helpdesk Agent", "IT"),
        ("SQL Query Agent", "Finance"),
        ("Financial Analysis Agent", "Finance"),
        ("Contract Review Agent", "Legal"),
        ("Procurement Sourcing Agent", "Procurement"),
        ("Recruiting Screening Agent", "HR"),
        ("HR Onboarding Agent", "HR"),
        ("Sales Outreach Agent", "Sales"),
        ("Marketing Content Agent", "Marketing"),
        ("Customer Support Agent", "Operations"),
        ("Security Triage Agent", "Security"),
        ("Executive Briefing Agent", "Operations"),
    )


DEFAULT_PROFILE = EnterpriseProfile()
