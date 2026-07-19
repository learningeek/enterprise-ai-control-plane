"""Turning AI usage events into cost/usage numbers — see docs/01-domain/metering.md.

First slice built: `duckdb_store.py`, a local analytics store for Tier 1 connector output. Chargeback,
full cost reconciliation, and the eventual Postgres-backed system of record (`backend/gateway`) are not
built here yet — see docs/current-state.md.
"""
