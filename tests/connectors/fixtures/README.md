# Real vendor-published example fixtures

These JSON files are **literal example responses copied verbatim from each vendor's own public
documentation** — not hand-rolled test data. They exist because no live admin account was available in
this environment to pull a real response from, and these are the closest substitute: authentic,
vendor-published, schema-accurate examples, as opposed to another layer of this project's own guesses
about what the API returns.

- `anthropic_usage_report_example.json` — from
  https://platform.claude.com/docs/en/api/beta/organization/usage_report/retrieve_messages (fetched
  2026-10-19), their "Example Response (200)" block, unmodified.
- `openai_usage_completions_example.json` — the single result object from
  https://developers.openai.com/cookbook/examples/completions_usage_api (fetched 2026-10-19), wrapped in
  the documented bucket envelope (`data[].start_time`/`end_time`/`results[]`) using the `start_time` value
  shown elsewhere on the same page's curl example (`1730419200`) — the cookbook shows the result object
  and the bucket envelope separately, not pre-combined, so this fixture combines them exactly as
  documented rather than inventing new values.

See `tests/connectors/test_real_fixtures.py` for what these are used to confirm.
