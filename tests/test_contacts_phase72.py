"""Phase 7.2 edge and failure-contract tests for root/minimum solvers."""
from __future__ import annotations

import math

import numpy as np
import pytest

from eclipsekit.contacts import bisect_root, brent_root, golden_section_minimize, solve_root


@pytest.mark.parametrize("start, end", [(1.0, 1.0), (2.0, 1.0), (float("nan"), 2.0), (0.0, float("inf"))])
def test_solver_rejects_invalid_intervals(start, end):
    with pytest.raises(ValueError):
        solve_root(lambda x: x, start, end)


def test_interval_validator_normalizes_numeric_endpoints():
    result = solve_root(lambda x: x - 1.0, "0", "2")
    assert result.converged
    assert result.root == pytest.approx(1.0)


@pytest.mark.parametrize("kwargs, message", [
    ({"method": "newton"}, "method must"),
    ({"tolerance_days": 0}, "tolerance_days"),
    ({"tolerance_days": float("nan")}, "tolerance_days"),
    ({"tolerance_days": True}, "tolerance_days"),
    ({"value_tolerance": -1}, "value_tolerance"),
    ({"value_tolerance": "bad"}, "value_tolerance"),
    ({"max_iterations": 0}, "at least 1"),
    ({"max_iterations": 1.5}, "integer"),
    ({"max_iterations": True}, "integer"),
    ({"scan_samples": 2}, "at least 3"),
    ({"scan_samples": 3.5}, "integer"),
    ({"tangent_samples": 2}, "at least 3"),
    ({"tangent_samples": False}, "integer"),
    ({"expansion_factor": 1.0}, "expansion_factor"),
    ({"expansion_factor": float("inf")}, "expansion_factor"),
    ({"max_expansions": -1}, ">= 0"),
    ({"max_expansions": 1.2}, "integer"),
    ({"max_span_days": 0}, "max_span_days"),
    ({"max_span_days": float("nan")}, "max_span_days"),
    ({"tangent_value_tolerance": -0.1}, "tangent_value_tolerance"),
    ({"auto_expand": 1}, "bool values"),
    ({"detect_tangent": None}, "bool values"),
])
def test_solve_root_rejects_invalid_options(kwargs, message):
    with pytest.raises(ValueError, match=message):
        solve_root(lambda x: x - 0.5, 0.0, 1.0, **kwargs)


def test_solve_root_accepts_numpy_integer_iteration_options():
    result = solve_root(
        lambda x: x - 0.5, 0.0, 1.0,
        max_iterations=np.int64(50), scan_samples=np.int64(9),
        tangent_samples=np.int64(9), max_expansions=np.int64(2),
    )
    assert result.converged


def test_bisection_endpoint_roots_and_internal_failures():
    left = solve_root(lambda x: x, 0.0, 1.0, method="bisection")
    right = solve_root(lambda x: x - 1.0, 0.0, 1.0, method="bisection")
    assert left.status == right.status == "endpoint_root"
    assert left.root == 0.0 and right.root == 1.0

    def broken_midpoint(x):
        if x == 0.5:
            raise RuntimeError("midpoint unavailable")
        return x - 0.5

    failed = solve_root(broken_midpoint, 0.0, 1.0, method="bisection")
    assert failed.status == "function_error"
    assert "midpoint unavailable" in failed.message

    non_finite = solve_root(lambda x: float("nan") if x == 0.5 else x - 0.4,
                            0.0, 1.0, method="bisection")
    assert non_finite.status == "non_finite"


def test_bisection_max_iteration_limit_is_reported():
    result = solve_root(lambda x: x - math.sqrt(2), 0.0, 2.0,
                        method="bisection", max_iterations=1,
                        tolerance_days=1e-15, value_tolerance=1e-30)
    assert result.converged is False
    assert result.status == "max_iterations"
    assert result.iterations == 1


def test_brent_endpoint_roots_and_mid_iteration_errors():
    assert brent_root(lambda x: x, 0.0, 1.0).status == "endpoint_root"
    assert brent_root(lambda x: x - 1.0, 0.0, 1.0).status == "endpoint_root"

    def broken(x):
        if 0.5 < x < 0.9:
            raise LookupError("missing ephemeris segment")
        return x - 0.8

    result = solve_root(broken, 0.0, 1.0, method="brent")
    assert result.status == "function_error"
    assert "missing ephemeris segment" in result.message


def test_brent_reports_non_finite_internal_value_and_iteration_limit():
    result = solve_root(lambda x: float("nan") if 0.5 < x < 0.9 else x - 0.8,
                       0.0, 1.0, method="brent")
    assert result.status == "non_finite"
    limited = solve_root(lambda x: x**3 - math.sqrt(3), 0.0, 2.0,
                         method="brent", max_iterations=1,
                         tolerance_days=1e-15, value_tolerance=1e-30)
    assert limited.status == "max_iterations"
    assert limited.converged is False


def test_brent_uses_secant_and_inverse_quadratic_interpolation_branches():
    result = solve_root(lambda x: x**3 - 0.123, 0.0, 1.0, method="brent")
    assert result.converged
    assert result.root == pytest.approx(0.123 ** (1 / 3), abs=1e-8)


def test_scan_reports_function_errors_and_skips_non_finite_samples():
    def scan_error(x):
        if x == 0.5:
            raise RuntimeError("scan failure")
        return x * x + 1

    failed = solve_root(scan_error, -1.0, 1.0, scan_samples=5)
    assert failed.status == "function_error"
    assert "scan failure" in failed.message

    no_bracket = solve_root(lambda x: float("nan") if x == 0.0 else x * x + 1,
                            -1.0, 1.0, scan_samples=5)
    assert no_bracket.status == "no_bracket"


def test_auto_expansion_stops_at_limit_and_reports_bracket_not_found():
    result = solve_root(lambda x: x * x + 1, -0.1, 0.1,
                        auto_expand=True, max_expansions=2,
                        expansion_factor=2.0, max_span_days=0.8)
    assert result.status == "bracket_not_found"
    assert result.root is None


def test_auto_expansion_propagates_scan_function_error():
    def broken(x):
        if abs(x) > 0.1:
            raise RuntimeError("expanded scan failed")
        return x * x + 1

    result = solve_root(broken, -0.1, 0.1, auto_expand=True,
                        max_expansions=2, expansion_factor=2.0,
                        max_span_days=1.0, scan_samples=5)
    assert result.status == "function_error"
    assert "expanded scan failed" in result.message


def test_sampled_exact_root_and_sampled_tangent_are_distinguished():
    root = solve_root(lambda x: (x - 0.5) ** 2, 0.0, 1.0, scan_samples=3)
    assert root.status == "sampled_root"
    tangent = solve_root(lambda x: (x - 0.5) ** 2, 0.0, 1.0,
                         scan_samples=3, detect_tangent=True,
                         tangent_value_tolerance=1e-12)
    assert tangent.status == "tangent_contact"
    assert tangent.tangent


def test_tangent_refinement_function_exception_becomes_diagnostic():
    def partly_broken(x):
        if 0.35 < x < 0.65:
            raise ArithmeticError("tangent residual unavailable")
        return (x - 0.5) ** 2 + 0.01

    result = solve_root(partly_broken, 0.0, 1.0, detect_tangent=True,
                        tangent_samples=5, tangent_value_tolerance=1e-8)
    assert result.status in {"function_error", "no_tangent_within_tolerance"}
    if result.status == "function_error":
        assert "tangent residual unavailable" in result.message


def test_tangent_refinement_non_finite_value_becomes_diagnostic():
    def partly_non_finite(x):
        if 0.35 < x < 0.65:
            return float("nan")
        return (x - 0.5) ** 2 + 0.01

    result = solve_root(partly_non_finite, 0.0, 1.0, detect_tangent=True,
                        tangent_samples=5, tangent_value_tolerance=1e-8)
    assert result.status in {"function_error", "no_tangent_within_tolerance"}


def test_legacy_bisection_handles_endpoint_and_function_failures():
    assert bisect_root(lambda x: x, 0.0, 1.0) == 0.0
    assert bisect_root(lambda x: x - 1.0, 0.0, 1.0) == 1.0
    assert bisect_root(lambda x: float("inf"), 0.0, 1.0) is None
    assert bisect_root(lambda x: (_ for _ in ()).throw(RuntimeError("nope")), 0.0, 1.0) is None


def test_golden_section_validates_inputs_and_non_finite_objective():
    with pytest.raises(ValueError, match="smaller"):
        golden_section_minimize(lambda x: x, 1.0, 1.0)
    with pytest.raises(ValueError, match="finite"):
        golden_section_minimize(lambda x: x, float("nan"), 1.0)
    with pytest.raises(ValueError, match="finite and positive"):
        golden_section_minimize(lambda x: x, 0.0, 1.0, tolerance_days=0)
    with pytest.raises(ValueError, match="integer"):
        golden_section_minimize(lambda x: x, 0.0, 1.0, max_iterations=2.5)
    with pytest.raises(ValueError, match="at least 1"):
        golden_section_minimize(lambda x: x, 0.0, 1.0, max_iterations=0)
    with pytest.raises(ValueError, match="non-finite"):
        golden_section_minimize(lambda x: float("nan"), 0.0, 1.0)


def test_golden_section_propagates_objective_exception():
    def broken(_x):
        raise RuntimeError("objective failed")

    with pytest.raises(RuntimeError, match="objective failed"):
        golden_section_minimize(broken, 0.0, 1.0)


def test_private_bisection_solver_endpoint_and_invalid_bracket_contracts():
    from eclipsekit.contacts import _Bracket, _solve_bisection

    left = _solve_bisection(lambda x: x, _Bracket(0.0, 1.0, 0.0, 1.0),
                            tolerance_days=1e-9, value_tolerance=1e-10, max_iterations=10)
    right = _solve_bisection(lambda x: x - 1.0, _Bracket(0.0, 1.0, -1.0, 0.0),
                             tolerance_days=1e-9, value_tolerance=1e-10, max_iterations=10)
    invalid = _solve_bisection(lambda x: x + 1.0, _Bracket(0.0, 1.0, 1.0, 2.0),
                               tolerance_days=1e-9, value_tolerance=1e-10, max_iterations=10)
    assert left.status == right.status == "endpoint_root"
    assert invalid.status == "no_bracket"


def test_private_brent_solver_endpoint_and_invalid_bracket_contracts():
    from eclipsekit.contacts import _Bracket, _solve_brent

    left = _solve_brent(lambda x: x, _Bracket(0.0, 1.0, 0.0, 1.0),
                        tolerance_days=1e-9, value_tolerance=1e-10, max_iterations=10)
    right = _solve_brent(lambda x: x - 1.0, _Bracket(0.0, 1.0, -1.0, 0.0),
                         tolerance_days=1e-9, value_tolerance=1e-10, max_iterations=10)
    invalid = _solve_brent(lambda x: x + 1.0, _Bracket(0.0, 1.0, 1.0, 2.0),
                           tolerance_days=1e-9, value_tolerance=1e-10, max_iterations=10)
    assert left.status == right.status == "endpoint_root"
    assert invalid.status == "no_bracket"


def test_private_scan_handles_start_root_and_selects_nearest_bracket():
    from eclipsekit.contacts import _scan_for_bracket

    root, calls, error = _scan_for_bracket(lambda x: x * (x - 0.5), 0.0, 1.0,
                                          samples=5, target=0.0)
    assert error is None and root is not None
    assert root.left == root.right == 0.0
    assert calls == 1

    chosen, _, error = _scan_for_bracket(
        lambda x: (x - 0.2) * (x - 0.8), 0.0, 1.0,
        samples=5, target=0.9,
    )
    assert error is None and chosen is not None
    assert chosen.left == pytest.approx(0.75)
    assert chosen.right == pytest.approx(1.0)


def test_private_scan_reports_non_finite_first_sample():
    from eclipsekit.contacts import _scan_for_bracket

    bracket, calls, error = _scan_for_bracket(lambda _x: float("nan"), 0.0, 1.0,
                                               samples=5, target=0.5)
    assert bracket is None
    assert calls == 1
    assert "non-finite" in error


def test_auto_expansion_does_not_scan_when_expansion_limit_is_initial_width():
    result = solve_root(lambda x: x * x + 1, -0.5, 0.5, auto_expand=True,
                        max_expansions=4, max_span_days=0.1)
    assert result.status == "bracket_not_found"
    assert result.bracket_start == pytest.approx(-0.5)
    assert result.bracket_end == pytest.approx(0.5)


def test_tangent_refinement_errors_are_reported_as_function_error():
    def broken(x):
        if 0.35 < x < 0.65:
            raise ArithmeticError("tangent model failed")
        return (x - 0.5) ** 2 + 0.01

    result = solve_root(broken, 0.0, 1.0, detect_tangent=True,
                        tangent_samples=5, tangent_value_tolerance=1e-8)
    assert result.status == "function_error"
    assert "tangent model failed" in result.message


def test_tangent_refinement_non_finite_values_are_reported_as_function_error():
    def broken(x):
        if 0.35 < x < 0.65:
            return float("nan")
        return (x - 0.5) ** 2 + 0.01

    result = solve_root(broken, 0.0, 1.0, detect_tangent=True,
                        tangent_samples=5, tangent_value_tolerance=1e-8)
    assert result.status == "function_error"
    assert "non-finite" in result.message


def test_golden_section_rejects_boolean_and_unconvertible_tolerance():
    with pytest.raises(ValueError, match="finite and positive"):
        golden_section_minimize(lambda x: x, 0.0, 1.0, tolerance_days=True)
    with pytest.raises(ValueError, match="finite and positive"):
        golden_section_minimize(lambda x: x, 0.0, 1.0, tolerance_days="bad")
