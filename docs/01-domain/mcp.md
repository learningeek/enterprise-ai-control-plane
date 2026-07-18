# MCP governance

MCP governance is a key differentiator for this product: tracking and controlling AI agent access to
MCP servers and tools, not just model usage.

Chain tracked: `User -> AI Agent -> MCP Server -> Tool Call -> Data Access -> Cost`.

What's governed:
- Which agents can use which tools
- Which data sources agents access via which MCP servers
- MCP server usage volume (e.g. "the GitHub MCP server was called 1.2M times this month")
- Tool-level cost attribution

MCP inventory dataset: `server_id`, `owner`, `tool_count`, `authentication`, `sensitivity`.
Example servers: GitHub, Jira, Confluence, ServiceNow, Slack, SAP, Salesforce, Snowflake MCP.

MCP tool call event: `timestamp`, `agent`, `server`, `tool`, `duration_ms`, `records_accessed`, `success`.
