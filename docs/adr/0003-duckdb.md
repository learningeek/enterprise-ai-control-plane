# ADR 0003: DuckDB for analytics

**Status:** accepted

**Decision:** Use DuckDB as the analytics/forecasting query engine over historical usage events, separate
from the PostgreSQL transactional store.

**Rationale:** Fast local analytical queries over large event volumes without standing up a separate
data warehouse for early-stage deployments.
