# Service boundaries

v1 is a **modular monolith**, not microservices. Modules live as folders under `backend/`:
`gateway/`, `metering/`, `governance/`, `intelligence/`, `connectors/`. Each module should have a clean
internal API boundary so it *could* be split into a real service later, but don't build distributed-systems
complexity (message queues, service mesh) until there's a concrete scaling reason to.
