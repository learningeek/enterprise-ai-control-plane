# Scripts

Setup/build scripts (environment bootstrap, running generators, running migrations) go here as they're
written.

- `generate_demo_dashboard_data.py` — populates a demo DuckDB store (`demo-data/dashboard_demo.duckdb`)
  for `backend/metering/report.py`'s dashboard, since no live vendor credentials are available in this
  environment. Sample data, not a real connector pull — see the module docstring.
