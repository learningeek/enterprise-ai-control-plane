# Providers

An AI model provider: OpenAI, Azure OpenAI, Anthropic, AWS Bedrock, or an internal/self-hosted model.
The system must be provider-agnostic — usage collection and metering treat all providers uniformly
through the same `AIUsageEvent` schema (see `specs/event-schema.md`).
