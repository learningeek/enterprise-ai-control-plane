"""Generates mcp_servers.csv per docs/01-domain/mcp.md.

Field list per mcp.md: server_id, owner, tool_count, authentication, sensitivity.
We add server_name/service_type/tools (semicolon-joined tool names) alongside
those — needed so simulation/generators/{ai_events,mcp_tool_calls}.py can
reference real tool names on a real server rather than inventing disconnected
ones (the simulation-engineer agent's "never generate impossible scenarios" rule).
"""

from __future__ import annotations

import pandas as pd

from simulation.generators.base import get_rng, weighted_choice

# service_type -> (tool names, owner department candidates, default sensitivity weights, auth weights)
SERVICE_CATALOG = {
    "GitHub": {
        "tools": ["create_issue", "search_code", "get_pull_request", "merge_pull_request", "list_repositories"],
        "owners": ["Engineering", "IT", "Security", "Engineering"],
        "sensitivity_weights": {"Low": 0.3, "Medium": 0.5, "High": 0.2},
        "auth_weights": {"OAuth2": 0.7, "API Key": 0.2, "Service Account": 0.1},
    },
    "Jira": {
        "tools": ["create_ticket", "search_tickets", "update_ticket", "transition_ticket"],
        "owners": ["Engineering", "IT", "Operations", "Engineering"],
        "sensitivity_weights": {"Low": 0.4, "Medium": 0.5, "High": 0.1},
        "auth_weights": {"OAuth2": 0.6, "API Key": 0.3, "Service Account": 0.1},
    },
    "Confluence": {
        "tools": ["search_pages", "create_page", "update_page"],
        "owners": ["Engineering", "IT", "Legal"],
        "sensitivity_weights": {"Low": 0.3, "Medium": 0.5, "High": 0.2},
        "auth_weights": {"OAuth2": 0.6, "API Key": 0.3, "Service Account": 0.1},
    },
    "ServiceNow": {
        "tools": ["create_incident", "get_ticket", "update_incident", "search_kb"],
        "owners": ["IT", "Operations", "Security"],
        "sensitivity_weights": {"Low": 0.2, "Medium": 0.5, "High": 0.3},
        "auth_weights": {"OAuth2": 0.5, "API Key": 0.2, "Service Account": 0.3},
    },
    "Slack": {
        "tools": ["send_message", "search_messages", "list_channels"],
        "owners": ["IT", "Operations", "HR"],
        "sensitivity_weights": {"Low": 0.4, "Medium": 0.4, "High": 0.2},
        "auth_weights": {"OAuth2": 0.8, "API Key": 0.1, "Service Account": 0.1},
    },
    "SAP": {
        "tools": ["get_invoice", "create_po", "get_vendor_record"],
        "owners": ["Finance", "Procurement", "Finance"],
        "sensitivity_weights": {"Low": 0.05, "Medium": 0.35, "High": 0.6},
        "auth_weights": {"Service Account": 0.6, "OAuth2": 0.2, "API Key": 0.2},
    },
    "Salesforce": {
        "tools": ["get_account", "update_opportunity", "create_lead", "search_accounts"],
        "owners": ["Sales", "Marketing", "Sales", "Sales"],
        "sensitivity_weights": {"Low": 0.1, "Medium": 0.5, "High": 0.4},
        "auth_weights": {"OAuth2": 0.7, "API Key": 0.2, "Service Account": 0.1},
    },
    "Snowflake": {
        "tools": ["run_query", "get_schema", "list_tables"],
        "owners": ["Finance", "Engineering", "Security", "Finance"],
        "sensitivity_weights": {"Low": 0.1, "Medium": 0.4, "High": 0.5},
        "auth_weights": {"Service Account": 0.6, "OAuth2": 0.3, "API Key": 0.1},
    },
    "Workday": {
        "tools": ["get_employee_record", "update_pto", "get_org_chart"],
        "owners": ["HR", "Finance", "HR"],
        "sensitivity_weights": {"Low": 0.05, "Medium": 0.25, "High": 0.7},
        "auth_weights": {"OAuth2": 0.6, "Service Account": 0.4, "API Key": 0.0},
    },
    "Zendesk": {
        "tools": ["create_ticket", "search_tickets", "update_ticket"],
        "owners": ["Operations", "Sales", "Operations"],
        "sensitivity_weights": {"Low": 0.3, "Medium": 0.5, "High": 0.2},
        "auth_weights": {"OAuth2": 0.7, "API Key": 0.3, "Service Account": 0.0},
    },
    "DocuSign": {
        "tools": ["send_for_signature", "get_envelope_status", "void_envelope"],
        "owners": ["Legal", "Procurement", "HR"],
        "sensitivity_weights": {"Low": 0.1, "Medium": 0.3, "High": 0.6},
        "auth_weights": {"OAuth2": 0.6, "API Key": 0.2, "Service Account": 0.2},
    },
    "Tableau": {
        "tools": ["get_dashboard", "run_extract_refresh", "export_view"],
        "owners": ["Finance", "Marketing", "Sales"],
        "sensitivity_weights": {"Low": 0.2, "Medium": 0.5, "High": 0.3},
        "auth_weights": {"OAuth2": 0.5, "API Key": 0.3, "Service Account": 0.2},
    },
}

# Instance counts per service, deterministically summing to profile.mcp_server_count (40).
INSTANCE_COUNTS = {
    "GitHub": 4,
    "Jira": 4,
    "Confluence": 3,
    "ServiceNow": 3,
    "Slack": 3,
    "SAP": 3,
    "Salesforce": 4,
    "Snowflake": 4,
    "Workday": 3,
    "Zendesk": 3,
    "DocuSign": 3,
    "Tableau": 3,
}


def generate(profile) -> pd.DataFrame:
    assert sum(INSTANCE_COUNTS.values()) == profile.mcp_server_count, (
        "mcp_servers INSTANCE_COUNTS must sum to profile.mcp_server_count"
    )
    rng = get_rng(profile, "mcp_servers")

    rows = []
    server_index = 1
    for service, spec in SERVICE_CATALOG.items():
        n = INSTANCE_COUNTS[service]
        owners = spec["owners"]
        for i in range(n):
            owner = owners[i % len(owners)]
            sensitivity = weighted_choice(rng, spec["sensitivity_weights"], 1)[0]
            authentication = weighted_choice(rng, spec["auth_weights"], 1)[0]
            rows.append(
                {
                    "server_id": f"MCP{server_index:03d}",
                    "server_name": f"{service} MCP - {owner}",
                    "service_type": service,
                    "owner": owner,
                    "tool_count": len(spec["tools"]),
                    "tools": ";".join(spec["tools"]),
                    "authentication": authentication,
                    "sensitivity": sensitivity,
                }
            )
            server_index += 1

    return pd.DataFrame(rows)
