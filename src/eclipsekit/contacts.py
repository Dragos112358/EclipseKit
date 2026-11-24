"""Numerical root finding for eclipse contacts.

The public :func:`bisect_root` keeps its original ``float | None`` contract.
New code can use :func:`solve_root` for Brent/bisection, automatic bracketing,
tangent-contact candidates, and structured diagnostics.

The independent variable in the eclipse engine is TT Julian Date.  The solver
therefore applies a lower bound based on floating-point spacing at the supplied
Julian Date; requesting a tolerance below the representable spacing cannot
produce additional physical precision.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
import math
from numbers import Integral
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class RootResult:
    """Detailed result from a scalar root search.

    ``root`` is expressed in the same units as the input independent variable
    (TT Julian Date for EclipseKit contact calculations). A tangency is reported
    as ``status='tangent_contact'`` and ``tangent=True`` when the refined
    minimum absolute residual is within the configured threshold. It is not
    silently represented as an ordinary sign-changing root.
    """

    root: float | None
    converged: bool
    status: str
    method: str
    iterations: int
    function_calls: int
    bracket_start: float | None
    bracket_end: float | None
    residual: float | None
    tangent: bool = False
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly diagnostic record."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class _Bracket:
    left: float
    right: float
    f_left: float
    f_right: float


def _validate_interval(start: float, end: float) -> tuple[float, float]:
    a, b = float(start), float(end)
    if not (math.isfinite(a) and math.isfinite(b)):
        raise ValueError("root interval endpoints must be finite")
    if not a < b:
        raise ValueError("start must be smaller than end")
    return a, b


def _x_tolerance(x: float, tolerance_days: float) -> float:
    """Respect both the requested tolerance and float spacing near ``x``."""
    return max(float(tolerance_days), 2.0 * math.ulp(float(x)))


def _evaluate(function: Callable[[float], float], x: float) -> tuple[float, Exception | None]:
    try:
        value = float(function(float(x)))
    except Exception as exc:  # diagnostics retain the cause instead of hiding it
        return math.nan, exc
    return value, None


def _failure(
    *, method: str, status: str, message: str, calls: int, start: float,
    end: float, iterations: int = 0, residual: float | None = None,
) -> RootResult:
    return RootResult(
        root=None, converged=False, status=status, method=method,
        iterations=iterations, function_calls=calls,
        bracket_start=start, bracket_end=end, residual=residual,
        tangent=False, message=message,
    )


def _solve_bisection(
    function: Callable[[float], float], bracket: _Bracket, *,
    tolerance_days: float, value_tolerance: float, max_iterations: int,
) -> RootResult:
    a, b, fa, fb = bracket.left, bracket.right, bracket.f_left, bracket.f_right
    calls = 0
    if abs(fa) <= value_tolerance:
        return RootResult(a, True, "endpoint_root", "bisection", 0, 0, a, b, fa,
                          message="The left endpoint satisfies the residual tolerance.")
    if abs(fb) <= value_tolerance:
        return RootResult(b, True, "endpoint_root", "bisection", 0, 0, a, b, fb,
                          message="The right endpoint satisfies the residual tolerance.")
    if fa * fb > 0.0:
        return _failure(method="bisection", status="no_bracket",
                        message="The interval endpoints do not have opposite signs.",
                        calls=0, start=a, end=b)

    for iteration in range(1, max_iterations + 1):
        midpoint = a + (b - a) * 0.5
        fm, error = _evaluate(function, midpoint)
        calls += 1
        if error is not None:
            return _failure(method="bisection", status="function_error",
                            message=f"Function evaluation failed: {type(error).__name__}: {error}",
                            calls=calls, start=a, end=b, iterations=iteration)
        if not math.isfinite(fm):
            return _failure(method="bisection", status="non_finite",
                            message="Function returned a non-finite value.",
                            calls=calls, start=a, end=b, iterations=iteration)
        if abs(fm) <= value_tolerance or (b - a) <= _x_tolerance(midpoint, tolerance_days):
            return RootResult(midpoint, True, "converged", "bisection", iteration,
                              calls + 2, a, b, fm,
                              message="Bisection converged within the configured tolerance.")
        if fa * fm <= 0.0:
            b, fb = midpoint, fm
        else:
            a, fa = midpoint, fm

    root = a if abs(fa) <= abs(fb) else b
    residual = fa if root == a else fb
    return RootResult(root, False, "max_iterations", "bisection", max_iterations,
                      calls + 2, a, b, residual,
                      message="Maximum bisection iterations reached before convergence.")


def _solve_brent(
    function: Callable[[float], float], bracket: _Bracket, *,
    tolerance_days: float, value_tolerance: float, max_iterations: int,
) -> RootResult:
    """Safeguarded Brent-Dekker solver (inverse quadratic/secant + bisection).

    A candidate is accepted only inside the central 80% of the current
    sign-changing bracket. This conservative safeguard avoids the unstable
    interpolation steps that can occur for steep or poorly scaled residuals.
    """
    left, right = bracket.left, bracket.right
    f_left, f_right = bracket.f_left, bracket.f_right
    calls = 0

    if abs(f_left) <= value_tolerance:
        return RootResult(left, True, "endpoint_root", "brent", 0, 0,
                          left, right, f_left,
                          message="The left endpoint satisfies the residual tolerance.")
    if abs(f_right) <= value_tolerance:
        return RootResult(right, True, "endpoint_root", "brent", 0, 0,
                          left, right, f_right,
                          message="The right endpoint satisfies the residual tolerance.")
    if f_left * f_right > 0.0:
        return _failure(method="brent", status="no_bracket",
                        message="The interval endpoints do not have opposite signs.",
                        calls=0, start=left, end=right)

    # The third point is the endpoint discarded by the previous bracket update.
    third_x: float | None = None
    third_f: float | None = None

    for iteration in range(1, max_iterations + 1):
        width = right - left
        x_tol = _x_tolerance((left + right) * 0.5, tolerance_days)
        if width <= x_tol:
            root = left if abs(f_left) <= abs(f_right) else right
            residual = f_left if root == left else f_right
            return RootResult(root, True, "converged", "brent", iteration - 1,
                              calls + 2, left, right, residual,
                              message="Brent-Dekker bracket reached the configured x tolerance.")

        candidate: float | None = None
        if third_x is not None and third_f is not None:
            vals = (f_left, f_right, third_f)
            if len({round(value, 30) for value in vals}) == 3:
                # Inverse quadratic interpolation through the three latest points.
                try:
                    candidate = (
                        left * f_right * third_f / ((f_left - f_right) * (f_left - third_f))
                        + right * f_left * third_f / ((f_right - f_left) * (f_right - third_f))
                        + third_x * f_left * f_right / ((third_f - f_left) * (third_f - f_right))
                    )
                except ZeroDivisionError:
                    candidate = None

        if candidate is None or not math.isfinite(candidate):
            # Secant interpolation from the active bracket.
            denominator = f_right - f_left
            if denominator != 0.0:
                candidate = right - f_right * (right - left) / denominator

        # Safeguard interpolation; otherwise fall back to bisection.
        lower_guard = left + 0.1 * width
        upper_guard = right - 0.1 * width
        if candidate is None or not (lower_guard < candidate < upper_guard):
            candidate = left + 0.5 * width

        f_candidate, error = _evaluate(function, candidate)
        calls += 1
        if error is not None:
            return _failure(method="brent", status="function_error",
                            message=f"Function evaluation failed: {type(error).__name__}: {error}",
                            calls=calls, start=left, end=right, iterations=iteration)
        if not math.isfinite(f_candidate):
            return _failure(method="brent", status="non_finite",
                            message="Function returned a non-finite value.",
                            calls=calls, start=left, end=right, iterations=iteration)
        if abs(f_candidate) <= value_tolerance:
            return RootResult(candidate, True, "converged", "brent", iteration,
                              calls + 2, left, right, f_candidate,
                              message="Brent-Dekker interpolation reached the residual tolerance.")

        # Replace the endpoint with the same sign; retain the discarded endpoint
        # as the third point for the next inverse-quadratic interpolation step.
        if f_left * f_candidate < 0.0:
            third_x, third_f = right, f_right
            right, f_right = candidate, f_candidate
        else:
            third_x, third_f = left, f_left
            left, f_left = candidate, f_candidate

    root = left if abs(f_left) <= abs(f_right) else right
    residual = f_left if root == left else f_right
    return RootResult(root, False, "max_iterations", "brent", max_iterations,
                      calls + 2, left, right, residual,
                      message="Maximum Brent iterations reached before convergence.")


def _scan_for_bracket(
    function: Callable[[float], float], start: float, end: float, *,
    samples: int, target: float,
) -> tuple[_Bracket | None, int, str | None]:
    calls = 0
    previous_x = start
    previous_f, error = _evaluate(function, previous_x)
    calls += 1
    if error is not None:
        return None, calls, f"Function evaluation failed: {type(error).__name__}: {error}"
    if not math.isfinite(previous_f):
        return None, calls, "Function returned a non-finite value during bracket scan."
    brackets: list[_Bracket] = []
    if previous_f == 0.0:
        return _Bracket(previous_x, previous_x, previous_f, previous_f), calls, None

    for index in range(1, samples):
        x = start + (end - start) * index / (samples - 1)
        value, error = _evaluate(function, x)
        calls += 1
        if error is not None:
            return None, calls, f"Function evaluation failed: {type(error).__name__}: {error}"
        if not math.isfinite(value):
            previous_x, previous_f = x, value
            continue
        if value == 0.0:
            return _Bracket(x, x, value, value), calls, None
        if math.isfinite(previous_f) and previous_f * value < 0.0:
            brackets.append(_Bracket(previous_x, x, previous_f, value))
        previous_x, previous_f = x, value

    if not brackets:
        return None, calls, None
    chosen = min(brackets, key=lambda item: abs((item.left + item.right) * 0.5 - target))
    return chosen, calls, None


def _find_tangent_candidate(
    function: Callable[[float], float], start: float, end: float, *,
    samples: int, residual_tolerance: float, tolerance_days: float,
    max_iterations: int, target: float,
) -> tuple[float | None, float | None, int, int, str | None]:
    """Find a near-zero local minimum of ``abs(function)`` without sign change.

    Function errors during refinement are returned to :func:`solve_root` as
    diagnostics instead of escaping from the root solver unexpectedly.
    """
    xs = [start + (end - start) * i / (samples - 1) for i in range(samples)]
    values: list[float] = []
    calls = 0
    for x in xs:
        value, error = _evaluate(function, x)
        calls += 1
        if error is not None or not math.isfinite(value):
            values.append(math.inf)
        else:
            values.append(abs(value))

    candidates: list[tuple[float, float, int]] = []
    local_intervals: list[tuple[float, float]] = []
    if values[0] <= values[1]:
        local_intervals.append((xs[0], xs[1]))
    if values[-1] <= values[-2]:
        local_intervals.append((xs[-2], xs[-1]))
    for index in range(1, samples - 1):
        if values[index] <= values[index - 1] and values[index] <= values[index + 1]:
            local_intervals.append((xs[index - 1], xs[index + 1]))

    def evaluate_absolute(x: float) -> tuple[float, str | None]:
        nonlocal calls
        value, error = _evaluate(function, x)
        calls += 1
        if error is not None:
            return math.inf, f"Function evaluation failed: {type(error).__name__}: {error}"
        if not math.isfinite(value):
            return math.inf, "Function returned a non-finite value during tangent refinement."
        return abs(value), None

    for lo, hi in local_intervals:
        # Golden-section minimization of absolute residual in this local cell.
        ratio = (math.sqrt(5.0) - 1.0) / 2.0
        a, b = lo, hi
        c = b - ratio * (b - a)
        d = a + ratio * (b - a)
        fc, error = evaluate_absolute(c)
        if error is not None:
            return None, None, calls, 0, error
        fd, error = evaluate_absolute(d)
        if error is not None:
            return None, None, calls, 0, error
        iteration = 0
        for iteration in range(max_iterations):
            if b - a <= _x_tolerance((a + b) * 0.5, tolerance_days):
                break
            if fc <= fd:
                b, d, fd = d, c, fc
                c = b - ratio * (b - a)
                fc, error = evaluate_absolute(c)
            else:
                a, c, fc = c, d, fd
                d = a + ratio * (b - a)
                fd, error = evaluate_absolute(d)
            if error is not None:
                return None, None, calls, iteration + 1, error
        root = (a + b) * 0.5
        residual_value, error = evaluate_absolute(root)
        if error is not None:
            return None, None, calls, iteration + 1, error
        candidates.append((residual_value, root, iteration + 1))

    if not candidates:
        return None, None, calls, 0, None
    residual_abs, root, iterations = min(
        candidates, key=lambda item: (item[0], abs(item[1] - target))
    )
    residual, error = _evaluate(function, root)
    calls += 1
    if error is not None:
        return None, None, calls, iterations, f"Function evaluation failed: {type(error).__name__}: {error}"
    if not math.isfinite(residual):
        return None, None, calls, iterations, "Function returned a non-finite value at tangent candidate."
    if residual_abs <= residual_tolerance:
        return root, residual, calls, iterations, None
    return None, residual, calls, iterations, None


def solve_root(
    function: Callable[[float], float], start: float, end: float, *,
    method: Literal["bisection", "brent"] = "brent",
    tolerance_days: float = 1e-10,
    value_tolerance: float = 1e-10,
    max_iterations: int = 100,
    auto_expand: bool = False,
    expansion_factor: float = 1.8,
    max_expansions: int = 6,
    max_span_days: float = 0.25,
    scan_samples: int = 81,
    detect_tangent: bool = False,
    tangent_samples: int = 101,
    tangent_value_tolerance: float = 1e-8,
) -> RootResult:
    """Solve a scalar root and return convergence diagnostics.

    ``auto_expand`` symmetrically expands the initial interval and scans each
    expanded interval for sign-changing brackets. If multiple roots are found,
    the bracket nearest the original interval midpoint is selected. Tangent
    detection is a separate near-zero-minimum search and is never confused with
    an ordinary sign-changing root.
    """
    a, b = _validate_interval(start, end)
    if method not in {"bisection", "brent"}:
        raise ValueError("method must be 'bisection' or 'brent'")
    if not isinstance(auto_expand, bool) or not isinstance(detect_tangent, bool):
        raise ValueError("auto_expand and detect_tangent must be bool values")

    for name, value in (("max_iterations", max_iterations),
                        ("scan_samples", scan_samples),
                        ("tangent_samples", tangent_samples),
                        ("max_expansions", max_expansions)):
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise ValueError(f"{name} must be an integer")
    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")
    if scan_samples < 3 or tangent_samples < 3:
        raise ValueError("scan_samples and tangent_samples must be at least 3")
    if max_expansions < 0:
        raise ValueError("max_expansions must be >= 0")

    def finite_float(value: Any, name: str, *, minimum: float, strict: bool = False) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a finite number")
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a finite number") from exc
        if not math.isfinite(numeric) or (numeric <= minimum if strict else numeric < minimum):
            qualifier = "greater than" if strict else "at least"
            raise ValueError(f"{name} must be finite and {qualifier} {minimum}")
        return numeric

    tolerance_days = finite_float(tolerance_days, "tolerance_days", minimum=0.0, strict=True)
    value_tolerance = finite_float(value_tolerance, "value_tolerance", minimum=0.0, strict=True)
    expansion_factor = finite_float(expansion_factor, "expansion_factor", minimum=1.0, strict=True)
    max_span_days = finite_float(max_span_days, "max_span_days", minimum=0.0, strict=True)
    tangent_value_tolerance = finite_float(
        tangent_value_tolerance, "tangent_value_tolerance", minimum=0.0
    )

    target = (a + b) * 0.5
    fa, error_a = _evaluate(function, a)
    fb, error_b = _evaluate(function, b)
    calls = 2
    if error_a is not None or error_b is not None:
        error = error_a or error_b
        return _failure(method=method, status="function_error",
                        message=f"Function evaluation failed: {type(error).__name__}: {error}",
                        calls=calls, start=a, end=b)
    if not (math.isfinite(fa) and math.isfinite(fb)):
        return _failure(method=method, status="non_finite",
                        message="Function returned a non-finite endpoint value.",
                        calls=calls, start=a, end=b)
    if abs(fa) <= value_tolerance:
        return RootResult(a, True, "endpoint_root", method, 0, calls, a, b, fa,
                          message="The left endpoint satisfies the residual tolerance.")
    if abs(fb) <= value_tolerance:
        return RootResult(b, True, "endpoint_root", method, 0, calls, a, b, fb,
                          message="The right endpoint satisfies the residual tolerance.")

    bracket: _Bracket | None = None
    search_start, search_end = a, b
    if fa * fb < 0.0:
        bracket = _Bracket(a, b, fa, fb)
    else:
        bracket, scan_calls, scan_error = _scan_for_bracket(
            function, a, b, samples=scan_samples, target=target
        )
        calls += scan_calls
        if scan_error:
            return _failure(method=method, status="function_error", message=scan_error,
                            calls=calls, start=search_start, end=search_end)

    if bracket is None and auto_expand:
        center = target
        initial_half_width = (b - a) * 0.5
        half_width = initial_half_width
        expansion_limit = max(initial_half_width, max_span_days * 0.5)
        for _ in range(max_expansions):
            next_half_width = min(half_width * expansion_factor, expansion_limit)
            if next_half_width <= half_width:
                break
            half_width = next_half_width
            search_start = center - half_width
            search_end = center + half_width
            bracket, scan_calls, scan_error = _scan_for_bracket(
                function, search_start, search_end, samples=scan_samples, target=target
            )
            calls += scan_calls
            if scan_error:
                return _failure(method=method, status="function_error", message=scan_error,
                                calls=calls, start=search_start, end=search_end)
            if bracket is not None or half_width >= expansion_limit:
                break

    if bracket is not None:
        # Handle a sampled exact root (zero-width bracket) without entering a solver.
        if bracket.left == bracket.right:
            if detect_tangent:
                local_step = (search_end - search_start) / (scan_samples - 1)
                left_probe = max(search_start, bracket.left - local_step)
                right_probe = min(search_end, bracket.right + local_step)
                f_left_probe, err_left = _evaluate(function, left_probe)
                f_right_probe, err_right = _evaluate(function, right_probe)
                calls += 2
                is_tangent = (
                    err_left is None and err_right is None
                    and math.isfinite(f_left_probe) and math.isfinite(f_right_probe)
                    and f_left_probe * f_right_probe > 0.0
                    and abs(bracket.f_left) <= tangent_value_tolerance
                )
                if is_tangent:
                    return RootResult(
                        bracket.left, True, "tangent_contact", method, 0, calls,
                        left_probe, right_probe, bracket.f_left, tangent=True,
                        message=("A sampled zero has equal-sign residuals on either side; "
                                 "it is classified as a tangent contact."),
                    )
            return RootResult(bracket.left, True, "sampled_root", method, 0,
                              calls, bracket.left, bracket.right, bracket.f_left,
                              message="A sampled point satisfies the root equation exactly.")
        result = (
            _solve_bisection(function, bracket, tolerance_days=tolerance_days,
                             value_tolerance=value_tolerance, max_iterations=max_iterations)
            if method == "bisection"
            else _solve_brent(function, bracket, tolerance_days=tolerance_days,
                              value_tolerance=value_tolerance, max_iterations=max_iterations)
        )
        return RootResult(
            root=result.root, converged=result.converged, status=result.status,
            method=result.method, iterations=result.iterations,
            function_calls=result.function_calls + calls - 2,
            bracket_start=result.bracket_start, bracket_end=result.bracket_end,
            residual=result.residual, tangent=result.tangent, message=result.message,
        )

    if detect_tangent:
        tangent_root, tangent_residual, tangent_calls, tangent_iterations, tangent_error = _find_tangent_candidate(
            function, search_start, search_end, samples=tangent_samples,
            residual_tolerance=tangent_value_tolerance,
            tolerance_days=tolerance_days, max_iterations=max_iterations,
            target=target,
        )
        calls += tangent_calls
        if tangent_error is not None:
            return _failure(
                method=method, status="function_error", message=tangent_error,
                calls=calls, start=search_start, end=search_end,
                iterations=tangent_iterations,
            )
        if tangent_root is not None:
            return RootResult(
                tangent_root, True, "tangent_contact", method, tangent_iterations,
                calls, search_start, search_end, tangent_residual, tangent=True,
                message=("A near-zero local minimum was found without a sign change; "
                         "this is classified as a tangent-contact candidate."),
            )
        if tangent_residual is not None:
            return RootResult(
                None, False, "no_tangent_within_tolerance", method,
                tangent_iterations, calls, search_start, search_end,
                tangent_residual, tangent=False,
                message=("No sign-changing root or tangent candidate met the configured "
                         "residual tolerance."),
            )

    status = "bracket_not_found" if auto_expand else "no_bracket"
    message = (
        "No sign-changing bracket was found after the configured expansion attempts."
        if auto_expand else "No sign-changing bracket was found inside the supplied interval."
    )
    return _failure(method=method, status=status, message=message,
                    calls=calls, start=search_start, end=search_end)


def brent_root(
    function: Callable[[float], float], start: float, end: float, *,
    tolerance_days: float = 1e-10, value_tolerance: float = 1e-10,
    max_iterations: int = 100,
) -> RootResult:
    """Solve a sign-changing bracket with Brent-Dekker and return diagnostics."""
    return solve_root(
        function, start, end, method="brent", tolerance_days=tolerance_days,
        value_tolerance=value_tolerance, max_iterations=max_iterations,
    )


def bisect_root(function: Callable[[float], float], start: float, end: float,
                *, tolerance_days: float = 1e-10, value_tolerance: float = 1e-10,
                max_iterations: int = 80) -> float | None:
    """Backward-compatible endpoint-bracketed bisection API.

    As in the original helper, the supplied endpoints must have opposite signs
    (or satisfy the residual tolerance). The numeric root is returned, or
    ``None`` when that endpoint bracket is invalid. Use :func:`solve_root` for
    interval scanning, automatic expansion, tangencies, or diagnostics.
    """
    a, b = _validate_interval(start, end)
    fa, error_a = _evaluate(function, a)
    fb, error_b = _evaluate(function, b)
    if error_a is not None or error_b is not None:
        return None
    if not (math.isfinite(fa) and math.isfinite(fb)):
        return None
    if abs(fa) <= value_tolerance:
        return a
    if abs(fb) <= value_tolerance:
        return b
    if fa * fb > 0.0:
        return None
    result = _solve_bisection(
        function, _Bracket(a, b, fa, fb), tolerance_days=tolerance_days,
        value_tolerance=value_tolerance, max_iterations=max_iterations,
    )
    return result.root if result.converged else None


def golden_section_minimize(function: Callable[[float], float], start: float, end: float,
                            *, tolerance_days: float = 1e-9,
                            max_iterations: int = 100) -> tuple[float, float]:
    """Minimize a unimodal scalar function over a bounded finite interval.

    Invalid intervals/tolerances/iteration counts and non-finite objective
    values fail explicitly instead of allowing NaNs to contaminate the result.
    Function exceptions are allowed to propagate unchanged.
    """
    a, b = _validate_interval(start, end)
    if isinstance(tolerance_days, bool):
        raise ValueError("tolerance_days must be finite and positive")
    try:
        tolerance_days = float(tolerance_days)
    except (TypeError, ValueError) as exc:
        raise ValueError("tolerance_days must be finite and positive") from exc
    if not math.isfinite(tolerance_days) or tolerance_days <= 0.0:
        raise ValueError("tolerance_days must be finite and positive")
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, Integral):
        raise ValueError("max_iterations must be an integer")
    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")

    def evaluate(x: float) -> float:
        value = float(function(x))
        if not math.isfinite(value):
            raise ValueError("objective function returned a non-finite value")
        return value

    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    c = b - ratio * (b - a)
    d = a + ratio * (b - a)
    fc, fd = evaluate(c), evaluate(d)
    for _ in range(max_iterations):
        if b - a <= max(tolerance_days, 2.0 * math.ulp((a + b) * 0.5)):
            break
        if fc <= fd:
            b, d, fd = d, c, fc
            c = b - ratio * (b - a)
            fc = evaluate(c)
        else:
            a, c, fc = c, d, fd
            d = a + ratio * (b - a)
            fd = evaluate(d)
    x = (a + b) / 2.0
    return x, evaluate(x)
