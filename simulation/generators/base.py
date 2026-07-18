"""Shared utilities for simulation/generators/*.

Centralizes deterministic seeding, weighted sampling, and output I/O so each
generator module only contains the modeling logic that's specific to it.
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from faker import Faker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_DATA_DIR = PROJECT_ROOT / "demo-data"


def _sub_seed(seed: int, name: str) -> int:
    """Derive a stable, independent sub-seed from a base seed + a dataset name.

    Uses crc32 (not the builtin hash()) because str hashing is randomized
    per-process unless PYTHONHASHSEED is fixed — this keeps runs reproducible
    regardless of call order or process.
    """
    return (seed + zlib.crc32(name.encode("utf-8"))) % (2**31 - 1)


def get_rng(profile, name: str) -> np.random.Generator:
    return np.random.default_rng(_sub_seed(profile.seed, name))


def get_faker(profile, name: str) -> Faker:
    f = Faker()
    Faker.seed(_sub_seed(profile.seed, name))
    return f


def normalize_weights(weights: dict) -> tuple[list, np.ndarray]:
    keys = list(weights.keys())
    values = np.array([weights[k] for k in keys], dtype=float)
    values = values / values.sum()
    return keys, values


def weighted_choice(rng: np.random.Generator, weights: dict, size: int) -> np.ndarray:
    keys, probs = normalize_weights(weights)
    return rng.choice(keys, size=size, p=probs)


def save_csv(df: pd.DataFrame, filename: str) -> Path:
    DEMO_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DEMO_DATA_DIR / filename
    df.to_csv(path, index=False)
    return path


def save_json(records: Iterable, filename: str) -> Path:
    DEMO_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DEMO_DATA_DIR / filename
    with path.open("w") as f:
        json.dump(list(records), f, indent=2, default=str)
    return path


def make_ids(prefix: str, n: int, width: int = 6) -> list[str]:
    return [f"{prefix}{i + 1:0{width}d}" for i in range(n)]


# Business-hours-weighted (UTC-normalized) hour-of-day distribution, shared by
# every generator that places events on a timeline (ai_events, mcp_tool_calls).
HOUR_WEIGHTS = np.array(
    [0.2, 0.15, 0.1, 0.1, 0.15, 0.3, 0.6, 1.2, 2.0, 2.4, 2.4, 2.2, 1.8, 2.2, 2.4, 2.3, 2.0, 1.5,
     1.0, 0.7, 0.5, 0.4, 0.3, 0.25]
)
HOUR_WEIGHTS = HOUR_WEIGHTS / HOUR_WEIGHTS.sum()


def sample_timestamps(rng: np.random.Generator, n: int, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Sample n timestamps in [start, end], weighted toward weekdays and business hours."""
    total_days = (end - start).days
    day_offsets = np.arange(total_days + 1)
    dates = [start + pd.Timedelta(days=int(d)) for d in day_offsets]
    weekday_weight = np.array([1.0 if d.weekday() < 5 else 0.3 for d in dates])
    weekday_weight = weekday_weight / weekday_weight.sum()

    chosen_days = rng.choice(day_offsets, size=n, p=weekday_weight)
    chosen_hours = rng.choice(np.arange(24), size=n, p=HOUR_WEIGHTS)
    chosen_minutes = rng.integers(0, 60, size=n)
    chosen_seconds = rng.integers(0, 60, size=n)

    timestamps = [
        start
        + pd.Timedelta(days=int(d))
        + pd.Timedelta(hours=int(h), minutes=int(m), seconds=int(s))
        for d, h, m, s in zip(chosen_days, chosen_hours, chosen_minutes, chosen_seconds)
    ]
    return pd.Series(timestamps)
