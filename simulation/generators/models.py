"""Generates models.csv and pricing.csv per docs/01-domain/models.md.

Pricing is deliberately approximate and clearly labeled as such (see
docs/04-simulation/cost-model.md and specs/pricing-model.md) — the numbers below
are illustrative USD per 1M tokens, not a live price feed, so the demo never goes
stale. `approved=False` marks a couple of preview/legacy models governance hasn't
cleared yet, giving the incident generator a "non-approved model used" signal to
sample from (docs/04-simulation/incident-generator.md).
"""

from __future__ import annotations

import pandas as pd

# (model_id, provider, model_name, input_cost_per_1M, output_cost_per_1M, max_context, approved)
MODEL_CATALOG = [
    ("openai-gpt-4o", "OpenAI", "GPT-4o", 2.50, 10.00, 128_000, True),
    ("openai-gpt-4o-mini", "OpenAI", "GPT-4o mini", 0.15, 0.60, 128_000, True),
    ("openai-o1-mini", "OpenAI", "o1-mini (preview)", 3.00, 12.00, 128_000, False),
    ("azure-gpt-4o", "Azure OpenAI", "Azure GPT-4o", 2.50, 10.00, 128_000, True),
    ("azure-gpt-4-turbo", "Azure OpenAI", "Azure GPT-4 Turbo", 10.00, 30.00, 128_000, True),
    ("anthropic-claude-opus-4", "Anthropic", "Claude Opus 4", 15.00, 75.00, 200_000, True),
    ("anthropic-claude-sonnet-4", "Anthropic", "Claude Sonnet 4", 3.00, 15.00, 200_000, True),
    ("anthropic-claude-haiku-4", "Anthropic", "Claude Haiku 4", 0.80, 4.00, 200_000, True),
    ("bedrock-claude-sonnet", "AWS Bedrock", "Claude Sonnet (Bedrock)", 3.00, 15.00, 200_000, True),
    ("bedrock-llama3-70b", "AWS Bedrock", "Llama 3 70B (Bedrock)", 0.72, 0.72, 8_000, True),
    ("bedrock-titan-text", "AWS Bedrock", "Titan Text (Bedrock, preview)", 0.20, 0.60, 32_000, False),
    ("internal-llm-v1", "Internal", "Internal LLM v1", 0.10, 0.20, 32_000, True),
    ("internal-llm-v2", "Internal", "Internal LLM v2", 0.15, 0.30, 64_000, True),
]

# Selection weight within a provider's model list once a provider is chosen —
# non-approved (preview) models are rarely used but not never.
MODEL_SELECTION_WEIGHT = {row[0]: (0.15 if not row[6] else 1.0) for row in MODEL_CATALOG}


def generate_models() -> pd.DataFrame:
    return pd.DataFrame(
        MODEL_CATALOG,
        columns=[
            "model_id",
            "provider",
            "model_name",
            "input_cost_per_1M",
            "output_cost_per_1M",
            "max_context",
            "approved",
        ],
    )


def generate_pricing(models_df: pd.DataFrame) -> pd.DataFrame:
    return models_df[
        ["model_id", "provider", "input_cost_per_1M", "output_cost_per_1M"]
    ].copy()
