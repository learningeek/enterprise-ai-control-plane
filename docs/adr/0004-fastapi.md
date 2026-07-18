# ADR 0004: FastAPI for the backend API

**Status:** accepted

**Decision:** Use FastAPI (Python) for the REST API layer.

**Rationale:** Matches the Python-heavy ML/data stack (pandas, scikit-learn, ChromaDB), strong typing via
Pydantic aligns well with the event-schema-first approach in this project.
