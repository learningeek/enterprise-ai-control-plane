"""Generates applications.csv per docs/01-domain/applications.md."""

from __future__ import annotations

import pandas as pd

from simulation.generators.base import get_rng, weighted_choice

APP_NAME_TEMPLATES = [
    "Code Assistant",
    "DevOps Copilot",
    "Data Pipeline Assistant",
    "Code Review Bot",
    "Financial Forecasting Tool",
    "Expense Report Analyzer",
    "Sales Copilot",
    "Lead Qualification Bot",
    "Proposal Generator",
    "Marketing Content Generator",
    "Campaign Analyzer",
    "Social Listening Assistant",
    "HR Assistant",
    "Recruiting Screener",
    "Onboarding Assistant",
    "Legal Document Reviewer",
    "Contract Analyzer",
    "Compliance Checker",
    "IT Helpdesk Bot",
    "Ticket Triage Assistant",
    "Knowledge Base Search",
    "Customer Support Bot",
    "Order Status Assistant",
    "Returns Processing Bot",
    "Security Threat Analyzer",
    "Access Review Assistant",
    "Incident Response Copilot",
    "Procurement Sourcing Bot",
    "Vendor Risk Analyzer",
    "PO Approval Assistant",
    "Meeting Notes Summarizer",
    "Executive Dashboard Assistant",
    "Internal Wiki Search",
    "Translation Assistant",
    "Email Drafting Assistant",
    "SQL Query Helper",
    "Enterprise Chat Assistant",
    "Document Summarizer",
    "Forecast Explainer",
    "Policy Q&A Bot",
]

TEAM_SUFFIXES = [
    "Platform Team",
    "Core Team",
    "EMEA",
    "APAC",
    "Americas",
    "Team Alpha",
    "Team Beta",
    "Pilot",
    "v2",
    "Enterprise",
    "Self-Serve",
    "Internal",
]

ENVIRONMENT_WEIGHTS = {"production": 0.55, "staging": 0.25, "dev": 0.20}

CRITICALITY_WEIGHTS_BY_ENV = {
    "production": {"High": 0.5, "Medium": 0.4, "Low": 0.1},
    "staging": {"Medium": 0.6, "Low": 0.4, "High": 0.0},
    "dev": {"Low": 0.8, "Medium": 0.2, "High": 0.0},
}


def generate(profile) -> pd.DataFrame:
    rng = get_rng(profile, "applications")
    n = profile.application_count

    owner_teams = weighted_choice(rng, profile.department_headcount_weights, n)
    environments = weighted_choice(rng, ENVIRONMENT_WEIGHTS, n)

    rows = []
    used_names = set()
    for i in range(n):
        base = rng.choice(APP_NAME_TEMPLATES)
        suffix = rng.choice(TEAM_SUFFIXES)
        name = f"{base} ({suffix})"
        # Guarantee uniqueness deterministically without changing the RNG stream shape.
        tie_breaker = 2
        original = name
        while name in used_names:
            name = f"{original} #{tie_breaker}"
            tie_breaker += 1
        used_names.add(name)

        env = environments[i]
        crit_weights = {k: v for k, v in CRITICALITY_WEIGHTS_BY_ENV[env].items() if v > 0}
        criticality = weighted_choice(rng, crit_weights, 1)[0]

        rows.append(
            {
                "app_id": f"APP{i + 1:04d}",
                "application_name": name,
                "owner_team": owner_teams[i],
                "environment": env,
                "business_criticality": criticality,
                "company_wide": rng.random() < profile.company_wide_app_fraction,
            }
        )

    return pd.DataFrame(rows)
