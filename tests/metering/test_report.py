from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.metering.report import PROVIDER_COLOR_ORDER, _aggregate_by_provider, aggregate_attribution, render_html


def make_row(**overrides) -> dict:
    defaults = dict(
        user_id="U000001",
        department="Engineering",
        provider="Anthropic",
        model="anthropic-claude-sonnet-4",
        request_count=2,
        total_prompt_tokens=1000,
        total_completion_tokens=500,
        total_cost=Decimal("1.23"),
        first_seen=datetime(2026, 6, 1, tzinfo=timezone.utc),
        last_seen=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return defaults


def test_aggregate_by_provider_sums_cost_per_provider():
    rows = [
        make_row(provider="Anthropic", total_cost=Decimal("1.00")),
        make_row(provider="Anthropic", total_cost=Decimal("2.00")),
        make_row(provider="OpenAI", total_cost=Decimal("0.50")),
    ]
    totals = dict(_aggregate_by_provider(rows))
    assert totals["Anthropic"] == Decimal("3.00")
    assert totals["OpenAI"] == Decimal("0.50")


def test_aggregate_by_provider_follows_fixed_order_regardless_of_input_order():
    # Azure OpenAI listed first in the input, but PROVIDER_COLOR_ORDER puts Anthropic/OpenAI before it.
    rows = [
        make_row(provider="Azure OpenAI", total_cost=Decimal("5.00")),
        make_row(provider="Anthropic", total_cost=Decimal("1.00")),
        make_row(provider="OpenAI", total_cost=Decimal("2.00")),
    ]
    ordered_names = [name for name, _cost in _aggregate_by_provider(rows)]
    color_order_names = [name for name, _l, _d in PROVIDER_COLOR_ORDER]
    # relative order among present providers must match the fixed color order, not input order
    present_in_fixed_order = [n for n in color_order_names if n in ordered_names]
    assert ordered_names == present_in_fixed_order


def test_aggregate_by_provider_appends_unrecognized_providers_at_the_end():
    rows = [make_row(provider="Some New Vendor", total_cost=Decimal("1.00")), make_row(provider="Anthropic")]
    ordered_names = [name for name, _cost in _aggregate_by_provider(rows)]
    assert ordered_names[-1] == "Some New Vendor"


def test_render_html_includes_totals_and_provider_names():
    rows = [
        make_row(provider="Anthropic", total_cost=Decimal("1.00"), request_count=3),
        make_row(provider="OpenAI", user_id="api_key:key_2", department="Unknown", total_cost=Decimal("2.00"), request_count=1),
    ]
    output = render_html(rows)
    assert "Anthropic" in output
    assert "OpenAI" in output
    assert "$3.00" in output  # total spend stat tile
    assert "api_key:key_2" in output
    assert "<html" in output and "</html>" in output


def test_render_html_flags_unmapped_keys_in_stat_tile():
    rows = [
        make_row(user_id="U000001", department="Engineering"),
        make_row(user_id="api_key:key_unmapped", department="Unknown"),
    ]
    output = render_html(rows)
    assert "(1 unmapped)" in output


def test_render_html_handles_empty_rows_without_crashing():
    output = render_html([])
    assert "<html" in output
    assert "$0.00" in output


def test_render_html_escapes_untrusted_looking_values():
    rows = [make_row(user_id="<script>alert(1)</script>")]
    output = render_html(rows)
    assert "<script>alert(1)</script>" not in output
    assert "&lt;script&gt;" in output


# --- aggregate_attribution ---------------------------------------------------------------------


def test_aggregate_attribution_splits_known_vs_unknown_department():
    rows = [
        make_row(department="Engineering", total_cost=Decimal("3.00")),
        make_row(department="Unknown", total_cost=Decimal("1.00")),
    ]
    attribution = aggregate_attribution(rows)
    assert attribution["attributed_cost"] == Decimal("3.00")
    assert attribution["unattributed_cost"] == Decimal("1.00")
    assert attribution["total_cost"] == Decimal("4.00")
    assert attribution["pct_attributed"] == 75.0


def test_aggregate_attribution_returns_none_pct_when_no_spend():
    assert aggregate_attribution([])["pct_attributed"] is None
    assert aggregate_attribution([])["total_cost"] == Decimal("0")


def test_aggregate_attribution_is_100_percent_when_nothing_is_unattributed():
    rows = [make_row(department="Engineering", total_cost=Decimal("5.00"))]
    attribution = aggregate_attribution(rows)
    assert attribution["pct_attributed"] == 100.0
    assert attribution["unattributed_by_provider"] == []


def test_aggregate_attribution_breaks_down_unattributed_by_provider_in_fixed_order():
    rows = [
        make_row(provider="Azure OpenAI", department="Unknown", total_cost=Decimal("2.00")),
        make_row(provider="Anthropic", department="Unknown", total_cost=Decimal("1.00")),
        make_row(provider="Anthropic", department="Engineering", total_cost=Decimal("9.00")),  # attributed, excluded
    ]
    attribution = aggregate_attribution(rows)
    assert attribution["unattributed_by_provider"] == [
        ("Anthropic", Decimal("1.00")),
        ("Azure OpenAI", Decimal("2.00")),
    ]
    assert attribution["unattributed_cost"] == Decimal("3.00")
    assert attribution["attributed_cost"] == Decimal("9.00")


def test_render_html_shows_attribution_hero_figure():
    rows = [
        make_row(department="Engineering", total_cost=Decimal("3.00")),
        make_row(department="Unknown", total_cost=Decimal("1.00")),
    ]
    output = render_html(rows)
    assert "75.0%" in output
    assert "$3.00 of $4.00" in output


def test_render_html_handles_zero_spend_attribution_without_crashing():
    output = render_html([])
    assert "No spend recorded yet." in output
    assert "—" in output
