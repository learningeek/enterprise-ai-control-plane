"""Static HTML dashboard: per-API-key/per-user AI usage and cost, across providers.

Reads from a DuckDBEventSink-populated store (`duckdb_store.usage_summary`) and renders a
self-contained HTML file — no server, no build step, so a platform team can regenerate and open it
locally. Color assignment follows a fixed per-provider order (never reassigned based on which providers
happen to be present in a given store), per the categorical-color rule in the project's dataviz skill.

The `user_id` column is exactly what upstream connectors wrote — a real employee id only where an org
has done the API-key/deployment ownership-mapping setup (see
docs/02-architecture/connector-framework.md); otherwise a synthetic `api_key:<id>`/`deployment:<name>`
id. This dashboard does not paper over that distinction — see the banner in `render_html`.
"""

from __future__ import annotations

import html
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from backend.metering.duckdb_store import usage_summary

# Fixed categorical order — never reassigned based on which providers are present in a given store.
# Slots per the project's dataviz skill reference palette (references/palette.md).
PROVIDER_COLOR_ORDER = [
    ("Anthropic", "#2a78d6", "#3987e5"),  # slot 1 — blue
    ("OpenAI", "#008300", "#008300"),  # slot 2 — green
    ("Azure OpenAI", "#e87ba4", "#d55181"),  # slot 3 — magenta
    ("Google Gemini", "#eda100", "#c98500"),  # slot 4 — yellow (not yet built, reserved)
    ("AWS Bedrock", "#1baf7a", "#199e70"),  # slot 5 — aqua (not yet built, reserved)
    ("GitHub Copilot", "#eb6834", "#d95926"),  # slot 6 — orange (not yet built, reserved)
]
_PROVIDER_LIGHT = {name: light for name, light, _dark in PROVIDER_COLOR_ORDER}
_PROVIDER_DARK = {name: dark for name, _light, dark in PROVIDER_COLOR_ORDER}
_FALLBACK_LIGHT, _FALLBACK_DARK = "#898781", "#898781"  # muted ink — an unrecognized provider, not an error

TOP_KEYS_LIMIT = 10


def _fmt_money(value: Decimal) -> str:
    return f"${value:,.2f}"


def _fmt_int(value: int) -> str:
    return f"{value:,}"


def _provider_color(provider: str, dark: bool) -> str:
    table = _PROVIDER_DARK if dark else _PROVIDER_LIGHT
    fallback = _FALLBACK_DARK if dark else _FALLBACK_LIGHT
    return table.get(provider, fallback)


def _aggregate_by_provider(rows: list[dict]) -> list[tuple[str, Decimal]]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in rows:
        totals[row["provider"]] += row["total_cost"]
    # fixed provider order first (only those present), anything unrecognized appended at the end
    known_order = [name for name, _l, _d in PROVIDER_COLOR_ORDER if name in totals]
    other = sorted(name for name in totals if name not in dict((n, 1) for n, _l, _d in PROVIDER_COLOR_ORDER))
    ordered = known_order + other
    return [(name, totals[name]) for name in ordered]


def _bar_row(label: str, value: Decimal, max_value: Decimal, color: str, sublabel: str = "") -> str:
    width_pct = float(value / max_value * 100) if max_value > 0 else 0
    safe_label = html.escape(label)
    safe_sub = html.escape(sublabel)
    return f"""
    <div class="bar-row">
      <div class="bar-label">{safe_label}{f'<span class="bar-sublabel">{safe_sub}</span>' if safe_sub else ''}</div>
      <div class="bar-track">
        <div class="bar-fill" style="width:{width_pct:.2f}%;background:{color}" title="{safe_label}: {_fmt_money(value)}"></div>
        <span class="bar-value">{_fmt_money(value)}</span>
      </div>
    </div>"""


def render_html(rows: list[dict], generated_at: datetime | None = None) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)

    total_cost = sum((row["total_cost"] for row in rows), Decimal("0"))
    total_requests = sum(row["request_count"] for row in rows)
    providers = sorted({row["provider"] for row in rows})
    unique_keys = len({row["user_id"] for row in rows})
    unmapped_keys = len({row["user_id"] for row in rows if row["department"] == "Unknown"})

    provider_totals = _aggregate_by_provider(rows)
    max_provider_cost = max((cost for _name, cost in provider_totals), default=Decimal("0"))

    top_rows = sorted(rows, key=lambda r: r["total_cost"], reverse=True)[:TOP_KEYS_LIMIT]
    max_key_cost = max((row["total_cost"] for row in top_rows), default=Decimal("0"))

    provider_bars_light = "".join(
        _bar_row(name, cost, max_provider_cost, _provider_color(name, dark=False)) for name, cost in provider_totals
    )
    key_bars_light = "".join(
        _bar_row(row["user_id"], row["total_cost"], max_key_cost, _provider_color(row["provider"], dark=False), sublabel=row["provider"])
        for row in top_rows
    )

    legend_items = "".join(
        f'<span class="legend-item"><span class="legend-swatch" style="background:{_provider_color(name, dark=False)}"></span>{html.escape(name)}</span>'
        for name, _cost in provider_totals
    )

    table_rows = "".join(
        f"""
        <tr>
          <td>{html.escape(row['user_id'])}</td>
          <td>{html.escape(row['department'])}</td>
          <td><span class="legend-swatch" style="background:{_provider_color(row['provider'], dark=False)}"></span>{html.escape(row['provider'])}</td>
          <td>{html.escape(row['model'])}</td>
          <td class="num">{_fmt_int(row['request_count'])}</td>
          <td class="num">{_fmt_int(row['total_prompt_tokens'])}</td>
          <td class="num">{_fmt_int(row['total_completion_tokens'])}</td>
          <td class="num">{_fmt_money(row['total_cost'])}</td>
        </tr>"""
        for row in sorted(rows, key=lambda r: r["total_cost"], reverse=True)
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AI Usage &amp; Cost — Tier 1 Connectors</title>
<style>
.viz-root {{
  color-scheme: light;
  --surface-1: #fcfcfb;
  --page: #f9f9f7;
  --text-primary: #0b0b0b;
  --text-secondary: #52514e;
  --text-muted: #898781;
  --gridline: #e1e0d9;
  --border: rgba(11,11,11,0.10);
}}
@media (prefers-color-scheme: dark) {{
  :root:where(:not([data-theme="light"])) .viz-root {{
    color-scheme: dark;
    --surface-1: #1a1a19;
    --page: #0d0d0d;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted: #898781;
    --gridline: #2c2c2a;
    --border: rgba(255,255,255,0.10);
  }}
}}
:root[data-theme="dark"] .viz-root {{
  color-scheme: dark;
  --surface-1: #1a1a19;
  --page: #0d0d0d;
  --text-primary: #ffffff;
  --text-secondary: #c3c2b7;
  --text-muted: #898781;
  --gridline: #2c2c2a;
  --border: rgba(255,255,255,0.10);
}}

* {{ box-sizing: border-box; }}
body {{ margin: 0; }}
.viz-root {{
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--page);
  color: var(--text-primary);
  padding: 32px 24px 64px;
}}
.wrap {{ max-width: 1040px; margin: 0 auto; }}
h1 {{ font-size: 22px; margin: 0 0 4px; }}
.meta {{ color: var(--text-secondary); font-size: 13px; margin-bottom: 20px; }}

.banner {{
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 24px;
  line-height: 1.5;
}}
.banner strong {{ color: var(--text-primary); }}

.stat-grid {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 28px;
}}
.stat-tile {{
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px;
}}
.stat-label {{ font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; }}
.stat-value {{ font-size: 26px; font-weight: 600; }}

.panel {{
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px 20px 8px;
  margin-bottom: 24px;
  overflow-x: auto;
}}
.panel h2 {{ font-size: 15px; margin: 0 0 4px; }}
.panel .sub {{ font-size: 12px; color: var(--text-secondary); margin-bottom: 16px; }}

.legend {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; font-size: 12px; color: var(--text-secondary); }}
.legend-item {{ display: inline-flex; align-items: center; gap: 6px; }}
.legend-swatch {{ width: 10px; height: 10px; border-radius: 3px; display: inline-block; margin-right: 4px; }}

.bar-row {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; min-width: 480px; }}
.bar-label {{ width: 180px; flex-shrink: 0; font-size: 13px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.bar-sublabel {{ display: block; font-size: 11px; color: var(--text-muted); }}
.bar-track {{ flex: 1; position: relative; height: 24px; background: var(--gridline); border-radius: 4px; display: flex; align-items: center; }}
.bar-fill {{ height: 24px; border-radius: 0 4px 4px 0; min-width: 2px; }}
.bar-value {{ margin-left: 8px; font-size: 12px; color: var(--text-secondary); font-variant-numeric: tabular-nums; white-space: nowrap; }}

table {{ width: 100%; border-collapse: collapse; font-size: 13px; min-width: 720px; }}
th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--gridline); }}
th {{ color: var(--text-secondary); font-weight: 500; font-size: 12px; }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
tbody tr:hover {{ background: var(--page); }}

footer {{ color: var(--text-muted); font-size: 12px; margin-top: 24px; }}
</style>
</head>
<body>
<div class="viz-root">
  <div class="wrap">
    <h1>AI Usage &amp; Cost — Tier 1 Connectors</h1>
    <div class="meta">Generated {generated_at.strftime('%Y-%m-%d %H:%M UTC')}</div>

    <div class="banner">
      <strong>Attribution scope:</strong> "User / key" below is a real employee id only where an org has
      configured API-key/deployment ownership mapping — otherwise it's a synthetic
      <code>api_key:&lt;id&gt;</code> / <code>deployment:&lt;name&gt;</code> id from the vendor's own
      usage report, and department shows <strong>Unknown</strong> rather than a guess. This is
      per-API-key visibility, not per-employee attribution, until that mapping work is done — see
      docs/02-architecture/connector-framework.md.
    </div>

    <div class="stat-grid">
      <div class="stat-tile"><div class="stat-label">Total spend</div><div class="stat-value">{_fmt_money(total_cost)}</div></div>
      <div class="stat-tile"><div class="stat-label">Total requests</div><div class="stat-value">{_fmt_int(total_requests)}</div></div>
      <div class="stat-tile"><div class="stat-label">Providers</div><div class="stat-value">{len(providers)}</div></div>
      <div class="stat-tile"><div class="stat-label">Keys/users tracked</div><div class="stat-value">{unique_keys}<span style="font-size:13px;color:var(--text-secondary)"> ({unmapped_keys} unmapped)</span></div></div>
    </div>

    <div class="panel">
      <h2>Cost by provider</h2>
      <div class="sub">Total spend across the current sync window, by AI provider.</div>
      {provider_bars_light}
    </div>

    <div class="panel">
      <h2>Top {min(TOP_KEYS_LIMIT, len(rows))} API keys / users by cost</h2>
      <div class="sub">Highest-spend keys or employees, across all providers.</div>
      <div class="legend">{legend_items}</div>
      {key_bars_light}
    </div>

    <div class="panel">
      <h2>Full breakdown</h2>
      <div class="sub">Every (user/key, department, provider, model) combination on record.</div>
      <table>
        <thead>
          <tr>
            <th>User / key</th><th>Department</th><th>Provider</th><th>Model</th>
            <th class="num">Requests</th><th class="num">Prompt tokens</th>
            <th class="num">Completion tokens</th><th class="num">Cost</th>
          </tr>
        </thead>
        <tbody>{table_rows}</tbody>
      </table>
    </div>

    <footer>Enterprise AI Control Plane — Tier 1 connector usage report. Cost is estimated via the
    approximate catalog pricing in simulation/generators/models.py unless a real cost-report join has
    been wired up (see each connector's module docstring).</footer>
  </div>
</div>
</body>
</html>"""


def generate_report(db_path: str | Path, output_path: str | Path) -> None:
    rows = usage_summary(db_path)
    Path(output_path).write_text(render_html(rows))


if __name__ == "__main__":
    import sys

    db = sys.argv[1] if len(sys.argv) > 1 else "demo-data/dashboard_demo.duckdb"
    out = sys.argv[2] if len(sys.argv) > 2 else "demo-data/dashboard_demo.html"
    generate_report(db, out)
    print(f"wrote {out}")
