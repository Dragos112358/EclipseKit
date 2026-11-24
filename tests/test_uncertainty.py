from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from eclipsekit.uncertainty import (
    ContactTimeUncertainty,
    UncertaintyBudget,
    altitude_uncertainty_to_time_seconds,
    apply_contact_uncertainties,
    combine_independent_uncertainties,
    estimate_contact_time_uncertainty,
    estimate_lunar_limb_contact_time_uncertainty,
    finite_difference_jacobian,
    propagate_covariance,
    propagate_shadow_path_position_uncertainty,
    propagate_uncertainty,
    uncertainty_result_to_markdown,
    write_uncertainty_report,
)


def test_budget_from_standard_deviations_preserves_correlation_and_units():
    budget = UncertaintyBudget.from_standard_deviations(
        ("longitude", "latitude"),
        (0.02, 0.01),
        units=("deg", "deg"),
        correlation=((1.0, 0.5), (0.5, 1.0)),
        source_descriptions=("survey specification",),
    )
    assert budget.standard_deviations == pytest.approx((0.02, 0.01))
    assert budget.covariance[0][1] == pytest.approx(0.0001)
    assert budget.units == ("deg", "deg")
    assert budget.to_dict()["source_descriptions"] == ["survey specification"]


def test_budget_rejects_bad_shape_asymmetry_and_non_psd_covariance():
    with pytest.raises(ValueError, match="shape"):
        UncertaintyBudget(("x", "y"), ((1.0,),))
    with pytest.raises(ValueError, match="symmetric"):
        UncertaintyBudget(("x", "y"), ((1.0, 0.2), (0.1, 1.0)))
    with pytest.raises(ValueError, match="positive semidefinite"):
        UncertaintyBudget(("x", "y"), ((1.0, 2.0), (2.0, 1.0)))


def test_budget_rejects_invalid_standard_deviation_and_correlation():
    with pytest.raises(ValueError, match="non-negative"):
        UncertaintyBudget.from_standard_deviations(("x",), (-1.0,))
    with pytest.raises(ValueError, match="diagonal"):
        UncertaintyBudget.from_standard_deviations(("x",), (1.0,), correlation=((0.9,),))
    with pytest.raises(ValueError, match="positive semidefinite"):
        UncertaintyBudget.from_standard_deviations(
            ("x", "y", "z"), (1.0, 1.0, 1.0),
            correlation=((1, 0.9, -0.9), (0.9, 1, 0.9), (-0.9, 0.9, 1)),
        )


def test_finite_difference_jacobian_matches_analytic_derivative():
    jacobian = finite_difference_jacobian(
        lambda x: np.array([x[0] ** 2 + 3.0 * x[1], x[0] * x[1]]),
        (2.0, 4.0),
    )
    assert np.allclose(jacobian, ((4.0, 3.0), (4.0, 2.0)), rtol=1.0e-6)


def test_finite_difference_jacobian_rejects_invalid_steps_and_dynamic_shape():
    with pytest.raises(ValueError, match="steps"):
        finite_difference_jacobian(lambda x: x[0], (1.0,), steps=(0.0,))
    with pytest.raises(ValueError, match="dimension changed"):
        finite_difference_jacobian(lambda x: x if x[0] > 1.0 else (1.0, 2.0), (1.0,))


def test_propagate_covariance_uses_full_correlated_matrix():
    result = propagate_covariance(((2.0, -1.0),), ((0.04, 0.01), (0.01, 0.09)))
    # 4*.04 + 1*.09 + 2*2*(-1)*.01 = .21
    assert result[0, 0] == pytest.approx(0.21)


def test_linear_propagation_reports_sigma_interval_and_jacobian():
    budget = UncertaintyBudget.from_standard_deviations(("a", "b"), (0.2, 0.4))
    result = propagate_uncertainty(
        lambda x: (x[0] + 2.0 * x[1], x[0] * x[1]),
        (3.0, 5.0),
        budget,
        output_names=("sum", "product"),
        output_units=("unit", "unit2"),
        confidence_level=0.95,
    )
    assert result.mean == pytest.approx((13.0, 15.0))
    assert result.standard_deviations == pytest.approx(
        ((0.2**2 + (2 * 0.4)**2) ** 0.5, (5.0**2 * 0.2**2 + 3.0**2 * 0.4**2) ** 0.5)
    )
    assert np.allclose(result.jacobian, ((1.0, 2.0), (5.0, 3.0)), rtol=1.0e-6)
    assert result.lower_bounds[0] < result.mean[0] < result.upper_bounds[0]
    assert result.method == "linear"
    json.dumps(result.to_dict())


def test_linear_propagation_retains_input_covariance():
    budget = UncertaintyBudget.from_standard_deviations(
        ("x", "y"), (1.0, 2.0), correlation=((1.0, 0.25), (0.25, 1.0))
    )
    result = propagate_uncertainty(lambda values: values[0] + values[1], (0.0, 0.0), budget)
    assert result.standard_deviations[0] == pytest.approx((1.0 + 4.0 + 1.0) ** 0.5)


def test_monte_carlo_is_reproducible_with_seed():
    budget = UncertaintyBudget.from_standard_deviations(("x",), (0.5,))
    #function = lambda values: (values[0] ** 2,)
    def function(values):
        return (values[0] ** 2,)
    first = propagate_uncertainty(function, (2.0,), budget, method="monte_carlo", samples=2000, seed=17)
    second = propagate_uncertainty(function, (2.0,), budget, method="monte_carlo", samples=2000, seed=17)
    assert first.mean == second.mean
    assert first.covariance == second.covariance
    assert first.sample_count == 2000
    assert first.lower_bounds[0] < first.upper_bounds[0]


def test_monte_carlo_rejects_invalid_sample_count_and_forward_model_failures():
    budget = UncertaintyBudget.from_standard_deviations(("x",), (0.1,))
    with pytest.raises(ValueError, match=">= 100"):
        propagate_uncertainty(lambda x: x, (0.0,), budget, method="monte_carlo", samples=10)
    with pytest.raises(ValueError, match="sample"):
        propagate_uncertainty(
            lambda x: (float(x[0]) if abs(float(x[0])) < 1.0e-2 else float("nan"),),
            (0.0,), budget, method="monte_carlo", samples=100, seed=2,
        )


def test_propagation_rejects_invalid_budget_dimensions_and_options():
    budget = UncertaintyBudget.from_standard_deviations(("x",), (0.1,))
    with pytest.raises(ValueError, match="matching"):
        propagate_uncertainty(lambda x: x[0], (1.0, 2.0), budget)
    with pytest.raises(ValueError, match="confidence_level"):
        propagate_uncertainty(lambda x: x[0], (1.0,), budget, confidence_level=1.0)
    with pytest.raises(ValueError, match="method"):
        propagate_uncertainty(lambda x: x[0], (1.0,), budget, method="unscented")


def test_shadow_path_position_uncertainty_returns_local_east_north_covariance():
    budget = UncertaintyBudget.from_standard_deviations(("axis_shift",), (0.5,), units=("km",))
    result = propagate_shadow_path_position_uncertainty(
        lambda x: (2.0 * x[0], -3.0 * x[0]), (0.0,), budget
    )
    assert result.output_names == ("east_offset", "north_offset")
    assert result.output_units == ("km", "km")
    assert np.allclose(result.covariance, ((1.0, -1.5), (-1.5, 2.25)))
    with pytest.raises(ValueError, match="exactly east and north"):
        propagate_shadow_path_position_uncertainty(lambda x: (x[0],), (0.0,), budget)


def test_contact_time_uncertainty_uses_implicit_function_derivative_and_covariance():
    budget = UncertaintyBudget.from_standard_deviations(
        ("p1", "p2"), (0.2, 0.4),
        correlation=((1.0, 0.25), (0.25, 1.0)),
        source_descriptions=("synthetic input budget",),
    )
    # g(t,p) = t - (100 + 2*p1 - 0.5*p2) ; dt/dp = (2, -0.5)
    estimate = estimate_contact_time_uncertainty(
        "C2", 100.0, (0.0, 0.0), budget,
        lambda t, p: t - (100.0 + 2.0 * p[0] - 0.5 * p[1]),
    )
    assert estimate.residual_rate_per_second == pytest.approx(1.0)
    assert estimate.time_sensitivity_seconds_per_unit == pytest.approx((2.0, -0.5), rel=1.0e-6)
    assert estimate.uncertainty_seconds == pytest.approx(0.4)
    assert estimate.contact_name == "C2"
    json.dumps(estimate.to_dict())


def test_contact_time_uncertainty_rejects_tangent_or_bad_time_rate():
    budget = UncertaintyBudget.from_standard_deviations(("p",), (0.1,))
    with pytest.raises(ValueError, match="near-zero"):
        estimate_contact_time_uncertainty(
            "C2", 0.0, (0.0,), budget,
            lambda t, p: t * t + p[0],
        )
    with pytest.raises(ValueError, match="time_step_seconds"):
        estimate_contact_time_uncertainty(
            "C2", 1.0, (0.0,), budget,
            lambda t, p: t + p[0], time_step_seconds=0.0,
        )


def test_contact_uncertainty_applies_only_to_matching_events_and_preserves_by_default():
    event = SimpleNamespace(uncertainty_seconds=None, uncertainty_note="Not quantified")
    existing = SimpleNamespace(uncertainty_seconds=4.0, uncertainty_note="Existing value")
    result = SimpleNamespace(contact_events={"C2": event, "C3": existing})
    estimate = ContactTimeUncertainty("C2", 50.0, 1.0, ("p",), (2.0,), 0.2)
    applied = apply_contact_uncertainties(result, {"c2": estimate, "C4": estimate})
    assert applied == ("C2",)
    assert event.uncertainty_seconds == pytest.approx(0.2)
    assert "solver residuals are excluded" in event.uncertainty_note
    assert existing.uncertainty_seconds == 4.0
    assert apply_contact_uncertainties(result, {"C3": estimate}) == ()
    assert apply_contact_uncertainties(result, {"C3": estimate}, overwrite=True) == ("C3",)


def test_apply_contact_uncertainties_rejects_wrong_inputs():
    with pytest.raises(TypeError, match="contact_events"):
        apply_contact_uncertainties(object(), {})
    with pytest.raises(TypeError, match="ContactTimeUncertainty"):
        apply_contact_uncertainties(SimpleNamespace(contact_events={}), {"C1": object()})


def test_altitude_uncertainty_to_time_seconds_uses_local_rate():
    assert altitude_uncertainty_to_time_seconds(80.0, -400.0) == pytest.approx(0.2)
    with pytest.raises(ValueError, match="non-zero"):
        altitude_uncertainty_to_time_seconds(10.0, 0.0)
    with pytest.raises(ValueError, match="non-negative"):
        altitude_uncertainty_to_time_seconds(-1.0, 10.0)


def test_lunar_limb_uncertainty_produces_attachable_contact_estimate():
    estimate = estimate_lunar_limb_contact_time_uncertainty(
        "C2", 120.0, 80.0, -400.0, source_description="DEM sample sigma at contact"
    )
    assert estimate.uncertainty_seconds == pytest.approx(0.2)
    assert estimate.time_sensitivity_seconds_per_unit == pytest.approx((0.0025,))
    assert estimate.method == "lunar_limb_altitude_linear"
    with pytest.raises(ValueError, match="source_description"):
        estimate_lunar_limb_contact_time_uncertainty("C2", 1, 80, 400, source_description=" ")


def test_combine_independent_uncertainties_uses_root_sum_square():
    assert combine_independent_uncertainties(3.0, 4.0) == pytest.approx(5.0)
    with pytest.raises(ValueError, match="At least one"):
        combine_independent_uncertainties()
    with pytest.raises(ValueError, match="non-negative"):
        combine_independent_uncertainties(1.0, -1.0)


def test_report_writer_creates_json_csv_and_markdown(tmp_path):
    budget = UncertaintyBudget.from_standard_deviations(("clock_bias",), (0.25,), units=("s",))
    result = propagate_uncertainty(
        lambda x: (2.0 * x[0],), (1.0,), budget,
        output_names=("contact_offset",), output_units=("s",),
        method="linear",
    )
    paths = write_uncertainty_report(result, tmp_path, stem="phase7_5")
    assert set(paths) == {"json", "csv", "markdown"}
    assert all(path.exists() for path in paths.values())
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["outputs"][0]["standard_deviation"] == pytest.approx(0.5)
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "Unspecified ephemeris" in markdown
    assert "contact_offset" in markdown
    assert "1sigma" not in markdown
    assert "contact_offset" in uncertainty_result_to_markdown(result)


def test_report_writer_rejects_path_traversal_stem(tmp_path):
    budget = UncertaintyBudget.from_standard_deviations(("x",), (0.1,))
    result = propagate_uncertainty(lambda x: x[0], (0.0,), budget)
    with pytest.raises(ValueError, match="stem"):
        write_uncertainty_report(result, tmp_path, stem="../escape")
