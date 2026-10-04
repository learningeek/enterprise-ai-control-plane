# Product vision

Enterprises are adopting AI faster than they can measure, govern, or control it. Every business unit is
independently adopting models, copilots, and agents; finance has no visibility into spend; security has
no visibility into data exposure; nobody can answer "what is our AI actually doing?"

The Enterprise AI Control Plane gives enterprises a single place to answer:

- Who is using which AI models, tools, and agents, and how much does it cost?
- Is usage compliant with policy? Where is risk concentrated?
- What will AI spend look like next quarter, and where can it be optimized?
- Which MCP servers and agents have access to which data, and is that appropriate?

The differentiator is not another dashboard — it's an **Enterprise Digital Twin** of AI usage: a live
model of departments, employees, applications, agents, MCP servers, models, budgets, and policies, that
can answer "what if" questions (e.g. "what happens if Engineering switches from GPT-5 to a smaller model?").

**Cost is the entry point, not the destination.** Token/cost aggregation alone is a commodity — vendor
dashboards, cloud FinOps tools, and LLM gateways already do that reasonably well (see
`docs/00-product/competitive-landscape.md`). What none of them do is attribute AI spend to a real owner
inside the org and account for what's *not* attributable. The sharpest question this product should be
able to answer isn't "what did we spend on AI" — it's "of that spend, how much can we explain, and how
much is unowned, unregistered, or unaccounted for." That "Unknown" fraction is the differentiator and the
urgency driver, not the total.
