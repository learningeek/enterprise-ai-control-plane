# Metering

Metering turns raw `AIUsageEvent` records into cost and usage numbers.

Responsibilities:
- Token counting (input/output tokens per event)
- Cost calculation (tokens x per-model pricing)
- Usage aggregation (by user, department, application, model, time period)
- Chargeback allocation (attributing cost to a department/cost center)

Example output: "Engineering: GPT usage $15,000/month, Copilot $5,000/month, internal models $2,000/month."
