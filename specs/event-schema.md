# Spec: AIUsageEvent schema

**Status:** v1 — this is the canonical, immutable event contract. Changes require a new version number,
not an in-place edit of existing fields.

## Fields

| Field | Type | Notes |
|---|---|---|
| `event_id` | string | unique request id |
| `schema_version` | int | starts at 1 |
| `timestamp` | datetime | UTC |
| `tenant_id` | string | required in all deployment models, even single-tenant on-prem |
| `user_id` | string | references `docs/01-domain/users.md` |
| `department` | string | denormalized at write time for query performance |
| `application_id` | string | references `docs/01-domain/applications.md` |
| `provider` | string | e.g. OpenAI, Azure OpenAI, Anthropic, AWS Bedrock, internal |
| `model` | string | references `docs/01-domain/models.md` |
| `prompt_tokens` | int | |
| `completion_tokens` | int | |
| `latency_ms` | int | |
| `request_cost` | decimal | computed from token counts x model pricing |
| `data_classification` | string | e.g. public/internal/confidential — feeds governance |
| `mcp_tool_used` | string, nullable | references `docs/01-domain/mcp.md` if applicable |
| `outcome` | string | success/blocked/error |

## Rules

- Events are immutable once written (append-only).
- Every downstream module (metering, billing, governance, ML, dashboards) reads from this same event
  stream — do not create a parallel table for "the same fact."
- Schema changes are additive and versioned; do not repurpose an existing field's meaning.
