# Users

An enterprise employee who may use AI-enabled applications, directly or indirectly.

Attributes: `user_id`, `name`, `department`, `title`, `manager`, `country`, `cost_center`,
`identity_provider` (e.g. Entra ID group membership).

Users are synced from the customer's SSO (see `docs/01-domain/governance.md` and
`docs/02-architecture/identity.md`), not manually managed in this system.
