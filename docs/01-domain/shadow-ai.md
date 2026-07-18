# Shadow AI

Shadow AI is AI tool usage happening outside sanctioned, governed applications — e.g. an employee using
a personal ChatGPT or Claude.ai account instead of the company-approved integration.

Dataset shape: `employee`, `tool`, `approved` (yes/no). This is a governance-facing dataset used to
demonstrate detection of ungoverned usage, distinct from the metered `AIUsageEvent` stream which only
covers usage the platform can see through sanctioned gateways/connectors.
