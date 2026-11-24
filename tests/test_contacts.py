import math

import pytest
from eclipsekit.contacts import bisect_root, golden_section_minimize


def test_bisection_root():
    root = bisect_root(lambda x: x*x - 2.0, 0.0, 2.0)
    assert root == pytest.approx(2**0.5, abs=1e-8)


def test_bisection_no_bracket():
    assert bisect_root(lambda x: x*x + 1.0, -1.0, 1.0) is None


def test_golden_section_minimum():
    x, y = golden_section_minimize(lambda z: (z - 3.25)**2 + 2.0, 0.0, 10.0)
    assert x == pytest.approx(3.25, abs=1e-6)
    assert y == pytest.approx(2.0, abs=1e-8)


def test_brent_root_reports_convergence_and_diagnostics():
    from eclipsekit.contacts import brent_root

    result = brent_root(lambda x: x * x - 2.0, 0.0, 2.0)
    assert result.converged is True
    assert result.status == "converged"
    assert result.root == pytest.approx(2**0.5, abs=1e-8)
    assert result.residual == pytest.approx(0.0, abs=1e-8)
    assert result.function_calls >= result.iterations
    assert result.bracket_start <= result.root <= result.bracket_end


def test_brent_root_rejects_non_bracketing_interval_with_status():
    from eclipsekit.contacts import brent_root

    result = brent_root(lambda x: x * x + 1.0, -1.0, 1.0)
    assert result.converged is False
    assert result.status == "no_bracket"
    assert result.root is None


def test_solve_root_auto_expands_and_finds_nearest_root():
    from eclipsekit.contacts import solve_root

    result = solve_root(
        lambda x: x - 5.0,
        0.0,
        1.0,
        method="brent",
        auto_expand=True,
        expansion_factor=2.0,
        max_expansions=6,
        max_span_days=16.0,
    )
    assert result.converged is True
    assert result.root == pytest.approx(5.0, abs=1e-8)
    assert result.bracket_start <= 5.0 <= result.bracket_end


def test_solve_root_detects_tangent_contact_without_sign_change():
    from eclipsekit.contacts import solve_root

    result = solve_root(
        lambda x: (x - 0.25) ** 2,
        0.0,
        1.0,
        method="brent",
        detect_tangent=True,
        tangent_value_tolerance=1e-10,
    )
    assert result.converged is True
    assert result.status == "tangent_contact"
    assert result.tangent is True
    assert result.root == pytest.approx(0.25, abs=1e-6)
    assert abs(result.residual) <= 1e-10


def test_tangent_candidate_above_residual_threshold_is_not_accepted():
    from eclipsekit.contacts import solve_root

    result = solve_root(
        lambda x: (x - 0.25) ** 2 + 1e-3,
        0.0,
        1.0,
        method="brent",
        detect_tangent=True,
        tangent_value_tolerance=1e-8,
    )
    assert result.converged is False
    assert result.status == "no_tangent_within_tolerance"


def test_solve_root_reports_non_finite_function_values():
    from eclipsekit.contacts import solve_root

    result = solve_root(lambda x: float("nan"), 0.0, 1.0)
    assert result.converged is False
    assert result.status == "non_finite"


def test_solver_diagnostics_are_json_friendly():
    import json
    from eclipsekit.contacts import solve_root

    result = solve_root(lambda x: x - 2.0, 0.0, 4.0, method="brent")
    encoded = json.dumps(result.to_dict())
    assert '"status": "converged"' in encoded


def test_solve_root_reports_function_exception():
    from eclipsekit.contacts import solve_root

    def broken(_x):
        raise RuntimeError("synthetic ephemeris failure")

    result = solve_root(broken, 0.0, 1.0)
    assert result.converged is False
    assert result.status == "function_error"
    assert "synthetic ephemeris failure" in result.message


def test_tangent_detection_refines_minimum_near_interval_edge():
    from eclipsekit.contacts import solve_root

    root_expected = 0.998
    result = solve_root(
        lambda x: (x - root_expected) ** 2,
        0.0,
        1.0,
        detect_tangent=True,
        tangent_value_tolerance=1e-10,
    )
    assert result.converged is True
    assert result.status == "tangent_contact"
    assert result.root == pytest.approx(root_expected, abs=1e-6)


def test_brent_root_handles_julian_date_scale_values():
    from eclipsekit.contacts import brent_root

    expected = 2461265.123456789
    result = brent_root(lambda jd: jd - expected, expected - 1e-3, expected + 1e-3)
    assert result.converged is True
    assert result.root == pytest.approx(expected, abs=2 * math.ulp(expected))


def test_legacy_bisection_keeps_endpoint_sign_bracket_contract():
    # Both endpoints are positive, despite two roots inside the interval.
    assert bisect_root(lambda x: x * x - 0.25, -1.0, 1.0) is None
