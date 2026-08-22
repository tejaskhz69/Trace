"""Spec for the metered nutrition provider.

These are mostly COST tests, not feature tests. The adapter is easy; what
turns a $50/mo line item into an unbounded one is calling the API when we
didn't have to, and every test here pins one of the guards that stops that.

The one correctness test that matters as much as the cost ones is the
per-serving scaling: Nutritionix reports per SERVING and we store per 100 g,
and getting that wrong is silently wrong in every direction at once.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models import FoodSource
from app.services import paid_sources
from app.services.paid_sources import (
    PaidBudgetExhausted,
    _Budget,
    to_resolved,
)


def _food(**over):
    """A Nutritionix `foods[]` object, in its per-serving shape."""
    base = {
        "food_name": "greek yogurt",
        "brand_name": "Fage",
        "serving_qty": 1,
        "serving_unit": "container",
        "serving_weight_grams": 200.0,
        "nf_calories": 200.0,
        "nf_protein": 20.0,
        "nf_total_carbohydrate": 14.0,
        "nf_total_fat": 8.0,
        "nf_dietary_fiber": 0.0,
        "nf_sugars": 12.0,
        "nf_saturated_fat": 5.0,
        "nf_sodium": 80.0,
        "nix_item_id": "abc123",
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# The scaling step — the one that is silently wrong if you get it wrong
# ---------------------------------------------------------------------------


def test_per_serving_values_are_scaled_to_per_100g():
    """Nutritionix reports per SERVING; we store per 100 g. Storing its
    numbers as-is is wrong by whatever the serving happened to weigh."""
    r = to_resolved(_food(serving_weight_grams=200.0, nf_calories=200.0))
    assert r is not None
    assert r.calories == pytest.approx(100.0)
    assert r.protein_g == pytest.approx(10.0)


def test_a_small_serving_scales_up_not_down():
    """A 30 g serving stored unscaled would UNDER-report by 3.3x."""
    r = to_resolved(_food(serving_weight_grams=30.0, nf_calories=150.0))
    assert r.calories == pytest.approx(500.0)


def test_a_food_with_no_serving_weight_is_refused():
    """Per-serving numbers with no serving weight cannot be put on a per-100 g
    basis. Assuming 100 g would be a fabrication."""
    assert to_resolved(_food(serving_weight_grams=0)) is None
    assert to_resolved(_food(serving_weight_grams=None)) is None


def test_the_spoken_portion_is_kept_as_the_default_serving():
    r = to_resolved(_food(serving_qty=1, serving_unit="container"))
    assert r.serving_sizes[0]["name"] == "1 container"
    assert r.serving_sizes[0]["grams"] == pytest.approx(200.0)
    assert r.serving_sizes[0]["is_default"] is True


def test_nutrients_can_come_from_the_attribute_id_list():
    """Both shapes appear depending on endpoint and plan. Reading only the
    flat fields is how an integration works in testing and returns zeros in
    production."""
    r = to_resolved(
        {
            "food_name": "apple",
            "serving_weight_grams": 100.0,
            "full_nutrients": [
                {"attr_id": 208, "value": 52.0},
                {"attr_id": 203, "value": 0.3},
                {"attr_id": 205, "value": 14.0},
            ],
        }
    )
    assert r is not None
    assert r.calories == pytest.approx(52.0)
    assert r.protein_g == pytest.approx(0.3)


def test_a_zero_calorie_row_is_refused_rather_than_stored():
    """A name-only hit is worse than a miss: the user logs it and silently
    banks 0 kcal."""
    assert to_resolved(_food(nf_calories=0, full_nutrients=[])) is None


def test_an_unnamed_food_is_refused():
    assert to_resolved(_food(food_name="")) is None


def test_rows_are_tagged_with_their_source():
    assert to_resolved(_food()).source is FoodSource.nutritionix


def test_paid_data_ranks_below_usda_and_above_crowdsourced():
    """Paying for a row is not evidence it was measured in a lab."""
    r = to_resolved(_food())
    assert 0.7 < r.data_quality < 0.9


# ---------------------------------------------------------------------------
# The budget — this is what stops a runaway loop becoming an invoice
# ---------------------------------------------------------------------------


def test_the_budget_stops_spending_at_the_limit():
    b = _Budget()
    for _ in range(3):
        b.spend(3)
    with pytest.raises(PaidBudgetExhausted):
        b.spend(3)


def test_the_budget_resets_on_a_new_day():
    b = _Budget(day=date.today() - timedelta(days=1), used=999)
    b.spend(5)  # must not raise
    assert b.snapshot(5)["used"] == 1


def test_the_budget_reports_what_is_left():
    b = _Budget()
    b.spend(10)
    b.spend(10)
    assert b.snapshot(10) == {
        "date": date.today().isoformat(),
        "used": 2,
        "limit": 10,
        "remaining": 8,
    }


def test_a_stale_counter_does_not_report_yesterdays_spend():
    b = _Budget(day=date.today() - timedelta(days=1), used=400)
    assert b.snapshot(500)["used"] == 0


# ---------------------------------------------------------------------------
# Unconfigured is a supported state, not an error
# ---------------------------------------------------------------------------


async def test_nothing_is_called_when_no_key_is_set(monkeypatch):
    """No key must mean the tier does not exist -- not an exception on every
    search, and not a warning logged per request."""
    monkeypatch.setattr(paid_sources, "available", lambda: False)
    assert await paid_sources.lookup_barcode("123") is None
    assert await paid_sources.search("chicken") == []
    assert await paid_sources.parse_meal("two rotis") == []


async def test_health_check_says_so_plainly_when_unconfigured(monkeypatch):
    monkeypatch.setattr(paid_sources, "available", lambda: False)
    res = await paid_sources.health_check()
    assert res["configured"] is False
    assert res["ok"] is False


async def test_an_empty_query_never_costs_a_call(monkeypatch):
    """Guard against a client firing a billed request on every keystroke,
    including the one that cleared the box."""
    monkeypatch.setattr(paid_sources, "available", lambda: True)
    calls = []
    monkeypatch.setattr(paid_sources, "_get", lambda *a, **k: calls.append(1))
    assert await paid_sources.search("   ") == []
    assert await paid_sources.parse_meal("") == []
    assert calls == []
