"""Spec for the maintenance readout — the card that claims we MEASURED your
expenditure rather than guessed it.

The claim is the product. These tests exist so we can only make it when it is
actually true.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.tdee import (
    BAND_MAX_PCT,
    BAND_MIN_PCT,
    KCAL_PER_KG_TISSUE,
    estimate_expenditure,
    maintenance_history,
    maintenance_readout,
    trend_weight_series,
)

START = date(2026, 1, 1)


def _series(days: int, start_kg: float, kg_per_week: float):
    """Daily weigh-ins on a clean linear trend, run through the real EWMA."""
    entries = [
        (START + timedelta(days=i), start_kg + kg_per_week * i / 7.0)
        for i in range(days)
    ]
    return trend_weight_series(entries)


def _intake(days: int, kcal: float) -> dict[date, float]:
    return {START + timedelta(days=i): kcal for i in range(days)}


def _measured(days=60, intake=2400.0, kg_per_week=-0.3, prior=2600.0):
    return estimate_expenditure(
        intake_by_day=_intake(days, intake),
        trend_series=_series(days, 80.0, kg_per_week),
        tdee_prior=prior,
    )


# ---------------------------------------------------------------------------
# The claim
# ---------------------------------------------------------------------------


def test_with_no_data_we_do_not_claim_to_have_measured_anything():
    r = estimate_expenditure(
        intake_by_day={}, trend_series=[], tdee_prior=2600.0
    )
    m = maintenance_readout(r)
    assert m.is_data_driven is False
    assert m.vs_calculator is None
    assert m.maintenance_kcal == 2600
    assert "calculator's guess" in m.source_line


def test_the_no_data_line_says_what_would_unlock_the_measurement():
    """'Not enough data' with no path forward is a useless sentence."""
    r = estimate_expenditure(
        intake_by_day={}, trend_series=[], tdee_prior=2600.0
    )
    m = maintenance_readout(r, total_weigh_ins=2, total_logged_days=1)
    assert "more weigh-ins" in m.source_line
    assert "more logged days" in m.source_line


def test_with_real_data_the_card_reports_a_measurement():
    m = maintenance_readout(_measured())
    assert m.is_data_driven is True
    assert m.vs_calculator is not None
    assert "I measured" in m.source_line


def test_the_delta_against_the_calculator_is_the_pitch():
    """Losing 0.3 kg/wk on 2,400 kcal means burning ~2,730, not the 2,600 a
    formula predicted. That gap is the entire reason the app exists."""
    m = maintenance_readout(_measured(intake=2400.0, kg_per_week=-0.3, prior=2600.0))
    assert m.observed_kcal is not None
    assert m.observed_kcal > 2600
    assert m.vs_calculator is not None and m.vs_calculator > 0


# ---------------------------------------------------------------------------
# The band
# ---------------------------------------------------------------------------


def test_the_band_never_collapses_to_a_confident_point():
    """True daily expenditure moves with NEAT and water. +/-1% would be a lie."""
    m = maintenance_readout(_measured(days=365))
    assert m.band_pct >= BAND_MIN_PCT
    assert m.band_high > m.band_low
    assert m.dialed_pct < 100


def test_the_band_is_widest_when_we_know_nothing():
    r = estimate_expenditure(intake_by_day={}, trend_series=[], tdee_prior=2600.0)
    m = maintenance_readout(r)
    assert m.band_pct == pytest.approx(BAND_MAX_PCT)
    assert m.dialed_pct == 0


def test_more_evidence_narrows_the_band():
    thin = maintenance_readout(_measured(days=25))
    thick = maintenance_readout(_measured(days=120))
    assert thick.band_pct < thin.band_pct
    assert thick.dialed_pct > thin.dialed_pct


def test_the_band_brackets_the_number_it_describes():
    m = maintenance_readout(_measured())
    assert m.band_low < m.maintenance_kcal < m.band_high


def test_dialed_and_the_band_can_never_disagree_on_screen():
    """They are two renderings of one fact, so one is derived from the other."""
    m = maintenance_readout(_measured(days=90))
    expected = (BAND_MAX_PCT - m.band_pct) / (BAND_MAX_PCT - BAND_MIN_PCT)
    assert m.dialed_pct == int(round(expected * 100))


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


def test_eating_under_maintenance_projects_weight_loss():
    m = maintenance_readout(_measured(), recent_intake_kcal=2000.0)
    assert m.eating_delta is not None and m.eating_delta < 0
    assert m.expected_rate_kg_per_week is not None
    assert m.expected_rate_kg_per_week < 0


def test_the_projected_rate_is_the_energy_balance_and_nothing_else():
    m = maintenance_readout(_measured(), recent_intake_kcal=2000.0)
    expected = round(
        (2000.0 - m.maintenance_kcal) * 7 / KCAL_PER_KG_TISSUE, 2
    )
    assert m.expected_rate_kg_per_week == expected


def test_no_intake_means_no_projection_rather_than_a_zero():
    """'0.00 kg/wk' and 'we cannot say' are different claims."""
    m = maintenance_readout(_measured())
    assert m.expected_rate_kg_per_week is None
    assert m.eating_delta is None


# ---------------------------------------------------------------------------
# The history chart
# ---------------------------------------------------------------------------


def test_history_is_empty_before_there_is_anything_to_plot():
    assert maintenance_history(
        intake_by_day={}, trend_series=[], tdee_prior=2600.0
    ) == []


def test_history_shows_the_band_actually_narrowing():
    """The chart must be a re-run of the estimator, not a decorative taper."""
    pts = maintenance_history(
        intake_by_day=_intake(120, 2400.0),
        trend_series=_series(120, 80.0, -0.3),
        tdee_prior=2600.0,
    )
    assert len(pts) > 5
    first_width = pts[0]["high"] - pts[0]["low"]
    last_width = pts[-1]["high"] - pts[-1]["low"]
    assert last_width < first_width


def test_history_always_ends_on_the_most_recent_day():
    """Strided sampling must not drop today off the end of the chart."""
    days = 137
    pts = maintenance_history(
        intake_by_day=_intake(days, 2400.0),
        trend_series=_series(days, 80.0, -0.3),
        tdee_prior=2600.0,
    )
    assert pts[-1]["date"] == (START + timedelta(days=days - 1)).isoformat()


def test_history_is_capped_so_a_phone_does_not_render_a_year_of_pixels():
    pts = maintenance_history(
        intake_by_day=_intake(400, 2400.0),
        trend_series=_series(400, 80.0, -0.2),
        tdee_prior=2600.0,
        max_points=60,
    )
    assert len(pts) <= 62  # cap, plus the forced final point


def test_every_history_point_brackets_its_own_estimate():
    pts = maintenance_history(
        intake_by_day=_intake(90, 2400.0),
        trend_series=_series(90, 80.0, -0.3),
        tdee_prior=2600.0,
    )
    assert all(p["low"] < p["kcal"] < p["high"] for p in pts)
