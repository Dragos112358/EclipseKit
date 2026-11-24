"""Auditable uncertainty propagation for eclipse predictions (Phase 7.5).

This module deliberately keeps uncertainty propagation separate from numerical
solver diagnostics.  It only produces physical uncertainty estimates when the
caller supplies defensible input standard deviations/covariances or a model
that maps those uncertain inputs to outputs.

All standard deviations and covariance entries use the units declared by the
caller.  The library does not silently convert units or invent uncertainties
for ephemerides, Earth orientation, observer coordinates, or lunar topography.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any, Callable, Mapping, Sequence

import numpy as np

ArrayLike = Sequence[float] | np.ndarray
ScalarOrVectorFunction = Callable[[np.ndarray], ArrayLike | float]
ContactResidualFunction = Callable[[float, np.ndarray], float]


def _finite_float(value: Any, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and result < minimum:
        if minimum == 0.0:
            raise ValueError(f"{name} must be non-negative")
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def _names(values: Sequence[str], name: str, expected: int | None = None) -> tuple[str, ...]:
    result = tuple(values)
    if expected is not None and len(result) != expected:
        raise ValueError(f"{name} must contain exactly {expected} entries")
    if any(not isinstance(item, str) or not item.strip() for item in result):
        raise ValueError(f"{name} entries must be non-empty strings")
    if len(set(result)) != len(result):
        raise ValueError(f"{name} entries must be unique")
    return tuple(item.strip() for item in result)


def _matrix(value: Any, name: str, *, square: bool = False) -> np.ndarray:
    try:
        result = np.asarray(value, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a numeric matrix") from exc
    if result.ndim != 2 or (square and result.shape[0] != result.shape[1]):
        expected = "square 2-D" if square else "2-D"
        raise ValueError(f"{name} must be a {expected} matrix")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain only finite values")
    return result


def _covariance_matrix(value: Any, dimension: int, name: str = "covariance") -> np.ndarray:
    matrix = _matrix(value, name, square=True)
    if matrix.shape != (dimension, dimension):
        raise ValueError(f"{name} must have shape ({dimension}, {dimension})")
    scale = max(1.0, float(np.max(np.abs(matrix))))
    tolerance = 1.0e-12 * scale
    if not np.allclose(matrix, matrix.T, rtol=1.0e-10, atol=tolerance):
        raise ValueError(f"{name} must be symmetric")
    matrix = (matrix + matrix.T) * 0.5
    eigenvalues = np.linalg.eigvalsh(matrix)
    if float(np.min(eigenvalues)) < -1.0e-10 * scale:
        raise ValueError(f"{name} must be positive semidefinite")
    # Remove tiny negative eigenvalue artefacts without changing material values.
    if float(np.min(eigenvalues)) < 0.0:
        eigenvalues, eigenvectors = np.linalg.eigh(matrix)
        matrix = (eigenvectors * np.maximum(eigenvalues, 0.0)) @ eigenvectors.T
        matrix = (matrix + matrix.T) * 0.5
    return matrix


def _as_output_vector(value: ArrayLike | float, name: str = "function output") -> np.ndarray:
    try:
        result = np.asarray(value, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if result.ndim == 0:
        result = result.reshape(1)
    if result.ndim != 1 or result.size == 0:
        raise ValueError(f"{name} must be a scalar or a non-empty 1-D vector")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain only finite values")
    return result


def _tuple_matrix(matrix: np.ndarray) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(value) for value in row) for row in matrix)


@dataclass(frozen=True, slots=True)
class UncertaintyBudget:
    """Covariance budget for uncertain model inputs.

    ``covariance[i][j]`` is expressed in ``units[i] * units[j]``.  Off-diagonal
    entries preserve correlations; a diagonal matrix means independent inputs.
    ``source_descriptions`` records provenance/assumptions and is never inferred.
    """

    parameter_names: tuple[str, ...]
    covariance: tuple[tuple[float, ...], ...]
    units: tuple[str, ...] = ()
    source_descriptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        names = _names(self.parameter_names, "parameter_names")
        if not names:
            raise ValueError("parameter_names must not be empty")
        matrix = _covariance_matrix(self.covariance, len(names))
        units = tuple(self.units) if self.units else tuple("unspecified" for _ in names)
        if len(units) != len(names) or any(not isinstance(unit, str) or not unit.strip() for unit in units):
            raise ValueError("units must contain one non-empty string per parameter")
        descriptions = tuple(self.source_descriptions)
        if any(not isinstance(item, str) or not item.strip() for item in descriptions):
            raise ValueError("source_descriptions must contain non-empty strings")
        object.__setattr__(self, "parameter_names", names)
        object.__setattr__(self, "covariance", _tuple_matrix(matrix))
        object.__setattr__(self, "units", tuple(unit.strip() for unit in units))
        object.__setattr__(self, "source_descriptions", tuple(item.strip() for item in descriptions))

    @classmethod
    def from_standard_deviations(
        cls,
        parameter_names: Sequence[str],
        standard_deviations: Sequence[float],
        *,
        units: Sequence[str] = (),
        correlation: ArrayLike | None = None,
        source_descriptions: Sequence[str] = (),
    ) -> "UncertaintyBudget":
        names = _names(parameter_names, "parameter_names")
        deviations = np.asarray(standard_deviations, dtype=float)
        if deviations.ndim != 1 or deviations.size != len(names):
            raise ValueError("standard_deviations must contain one value per parameter")
        if not np.all(np.isfinite(deviations)) or np.any(deviations < 0.0):
            raise ValueError("standard_deviations must be finite and non-negative")
        if correlation is None:
            corr = np.eye(len(names), dtype=float)
        else:
            corr = _matrix(correlation, "correlation", square=True)
            if corr.shape != (len(names), len(names)):
                raise ValueError("correlation must have one row and column per parameter")
            if not np.allclose(corr, corr.T, rtol=1.0e-10, atol=1.0e-12):
                raise ValueError("correlation must be symmetric")
            if not np.allclose(np.diag(corr), 1.0, rtol=0.0, atol=1.0e-10):
                raise ValueError("correlation diagonal entries must equal 1")
            if np.any(np.abs(corr) > 1.0 + 1.0e-10):
                raise ValueError("correlation entries must be between -1 and 1")
            corr = _covariance_matrix(corr, len(names), "correlation")
        covariance = np.outer(deviations, deviations) * corr
        return cls(
            parameter_names=names,
            covariance=_tuple_matrix(covariance),
            units=tuple(units),
            source_descriptions=tuple(source_descriptions),
        )

    @property
    def standard_deviations(self) -> tuple[float, ...]:
        matrix = np.asarray(self.covariance, dtype=float)
        return tuple(float(value) for value in np.sqrt(np.maximum(np.diag(matrix), 0.0)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_names": list(self.parameter_names),
            "units": list(self.units),
            "standard_deviations": list(self.standard_deviations),
            "covariance": [list(row) for row in self.covariance],
            "source_descriptions": list(self.source_descriptions),
            "covariance_convention": "covariance[i][j] uses units[i] × units[j]",
        }


@dataclass(frozen=True, slots=True)
class PropagationResult:
    """Result of first-order or Monte Carlo uncertainty propagation."""

    output_names: tuple[str, ...]
    output_units: tuple[str, ...]
    mean: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    standard_deviations: tuple[float, ...]
    jacobian: tuple[tuple[float, ...], ...] | None
    input_names: tuple[str, ...]
    input_units: tuple[str, ...]
    input_covariance: tuple[tuple[float, ...], ...]
    method: str
    sample_count: int
    confidence_level: float
    lower_bounds: tuple[float, ...]
    upper_bounds: tuple[float, ...]
    source_descriptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        output_count = len(self.mean)
        input_names = _names(self.input_names, "input_names")
        input_count = len(input_names)
        output_names = _names(self.output_names, "output_names", output_count)
        if output_count < 1 or input_count < 1:
            raise ValueError("PropagationResult must contain at least one input and output")
        if len(self.output_units) != output_count or any(
            not isinstance(unit, str) or not unit.strip() for unit in self.output_units
        ):
            raise ValueError("output_units must contain one non-empty string per output")
        if len(self.input_units) != input_count or any(
            not isinstance(unit, str) or not unit.strip() for unit in self.input_units
        ):
            raise ValueError("input_units must contain one non-empty string per input")
        vectors = {
            "mean": self.mean,
            "standard_deviations": self.standard_deviations,
            "lower_bounds": self.lower_bounds,
            "upper_bounds": self.upper_bounds,
        }
        for name, values in vectors.items():
            if len(values) != output_count:
                raise ValueError(f"{name} must match the output dimension")
            for value in values:
                _finite_float(value, name, minimum=0.0 if name == "standard_deviations" else None)
        if any(low > high for low, high in zip(self.lower_bounds, self.upper_bounds)):
            raise ValueError("lower_bounds must not exceed upper_bounds")
        if self.jacobian is not None:
            jacobian = _matrix(self.jacobian, "jacobian")
            if jacobian.shape != (output_count, input_count):
                raise ValueError("jacobian dimensions do not match inputs and outputs")
        _covariance_matrix(self.covariance, output_count, "output covariance")
        _covariance_matrix(self.input_covariance, input_count, "input covariance")
        if self.method not in {"linear", "monte_carlo"}:
            raise ValueError("method must be 'linear' or 'monte_carlo'")
        if (
            isinstance(self.sample_count, bool)
            or not isinstance(self.sample_count, (int, np.integer))
            or self.sample_count < 0
        ):
            raise ValueError("sample_count must be a non-negative integer")
        level = _finite_float(self.confidence_level, "confidence_level")
        if not 0.0 < level < 1.0:
            raise ValueError("confidence_level must be between 0 and 1")
        descriptions = tuple(self.source_descriptions)
        if any(not isinstance(item, str) or not item.strip() for item in descriptions):
            raise ValueError("source_descriptions must contain non-empty strings")
        object.__setattr__(self, "input_names", input_names)
        object.__setattr__(self, "output_names", output_names)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "sample_count": self.sample_count,
            "confidence_level": self.confidence_level,
            "outputs": [
                {
                    "name": self.output_names[index],
                    "unit": self.output_units[index],
                    "mean": self.mean[index],
                    "standard_deviation": self.standard_deviations[index],
                    "lower_bound": self.lower_bounds[index],
                    "upper_bound": self.upper_bounds[index],
                }
                for index in range(len(self.mean))
            ],
            "output_covariance": [list(row) for row in self.covariance],
            "jacobian": [list(row) for row in self.jacobian] if self.jacobian is not None else None,
            "input_budget": {
                "parameter_names": list(self.input_names),
                "units": list(self.input_units),
                "covariance": [list(row) for row in self.input_covariance],
                "source_descriptions": list(self.source_descriptions),
            },
            "limitations": [
                "Uncertainty is conditional on the supplied input covariance and forward model.",
                "Unspecified error sources are not included.",
                "Linear propagation is first-order; Monte Carlo results depend on the stated input distribution.",
            ],
        }


@dataclass(frozen=True, slots=True)
class ContactTimeUncertainty:
    """One-sigma uncertainty of a solved contact time from an implicit equation.

    For ``g(t, p) = 0``, the local sensitivity is ``dt/dp = -g_p / g_t``.
    ``contact_time_seconds`` is the caller's time coordinate, normally seconds
    from an explicitly documented epoch; it is not converted to UTC here.
    """

    contact_name: str
    contact_time_seconds: float
    residual_rate_per_second: float
    parameter_names: tuple[str, ...]
    time_sensitivity_seconds_per_unit: tuple[float, ...]
    uncertainty_seconds: float
    method: str = "implicit_linear"
    source_descriptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.contact_name, str) or not self.contact_name.strip():
            raise ValueError("contact_name must be a non-empty string")
        for field_name in ("contact_time_seconds", "residual_rate_per_second", "uncertainty_seconds"):
            _finite_float(getattr(self, field_name), field_name, minimum=0.0 if field_name == "uncertainty_seconds" else None)
        if self.residual_rate_per_second == 0.0:
            raise ValueError("residual_rate_per_second must not be zero")
        names = _names(self.parameter_names, "parameter_names")
        if len(names) != len(self.time_sensitivity_seconds_per_unit):
            raise ValueError("time sensitivities must match parameter_names")
        sensitivities = tuple(
            _finite_float(value, "time sensitivity")
            for value in self.time_sensitivity_seconds_per_unit
        )
        if not isinstance(self.method, str) or not self.method.strip():
            raise ValueError("method must be a non-empty string")
        descriptions = tuple(self.source_descriptions)
        if any(not isinstance(item, str) or not item.strip() for item in descriptions):
            raise ValueError("source_descriptions must contain non-empty strings")
        object.__setattr__(self, "contact_name", self.contact_name.strip())
        object.__setattr__(self, "parameter_names", names)
        object.__setattr__(self, "time_sensitivity_seconds_per_unit", sensitivities)
        object.__setattr__(self, "source_descriptions", descriptions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contact_name": self.contact_name,
            "contact_time_seconds": self.contact_time_seconds,
            "residual_rate_per_second": self.residual_rate_per_second,
            "parameter_names": list(self.parameter_names),
            "time_sensitivity_seconds_per_unit": list(self.time_sensitivity_seconds_per_unit),
            "uncertainty_seconds_1sigma": self.uncertainty_seconds,
            "method": self.method,
            "source_descriptions": list(self.source_descriptions),
        }


def finite_difference_jacobian(
    function: ScalarOrVectorFunction,
    values: ArrayLike,
    *,
    steps: ArrayLike | None = None,
) -> np.ndarray:
    """Calculate a central-difference Jacobian with scale-aware step sizes."""
    point = np.asarray(values, dtype=float)
    if point.ndim != 1 or point.size == 0 or not np.all(np.isfinite(point)):
        raise ValueError("values must be a non-empty finite 1-D vector")
    if steps is None:
        delta = np.cbrt(np.finfo(float).eps) * np.maximum(np.abs(point), 1.0)
    else:
        delta = np.asarray(steps, dtype=float)
        if delta.shape != point.shape or not np.all(np.isfinite(delta)) or np.any(delta <= 0.0):
            raise ValueError("steps must be finite, positive, and match values")
    baseline = _as_output_vector(function(point.copy()))
    jacobian = np.empty((baseline.size, point.size), dtype=float)
    for index in range(point.size):
        plus = point.copy()
        minus = point.copy()
        plus[index] += delta[index]
        minus[index] -= delta[index]
        high = _as_output_vector(function(plus), "function output at positive perturbation")
        low = _as_output_vector(function(minus), "function output at negative perturbation")
        if high.shape != baseline.shape or low.shape != baseline.shape:
            raise ValueError("function output dimension changed during finite differencing")
        jacobian[:, index] = (high - low) / (2.0 * delta[index])
    if not np.all(np.isfinite(jacobian)):
        raise ValueError("finite-difference Jacobian contains non-finite values")
    return jacobian


def propagate_covariance(jacobian: ArrayLike, covariance: ArrayLike) -> np.ndarray:
    """Propagate covariance with ``Sigma_y = J Sigma_x J.T``."""
    derivative = _matrix(jacobian, "jacobian")
    if derivative.shape[0] < 1 or derivative.shape[1] < 1:
        raise ValueError("jacobian must have at least one input and output")
    input_covariance = _covariance_matrix(covariance, derivative.shape[1])
    output_covariance = derivative @ input_covariance @ derivative.T
    output_covariance = (output_covariance + output_covariance.T) * 0.5
    # Numerical round-off can produce tiny negative diagonal values.
    diagonal = np.maximum(np.diag(output_covariance), 0.0)
    np.fill_diagonal(output_covariance, diagonal)
    return output_covariance


def propagate_uncertainty(
    function: ScalarOrVectorFunction,
    mean: ArrayLike,
    budget: UncertaintyBudget,
    *,
    output_names: Sequence[str] | None = None,
    output_units: Sequence[str] | None = None,
    method: str = "linear",
    samples: int = 10000,
    seed: int | None = 20261122,
    confidence_level: float = 0.95,
    finite_difference_steps: ArrayLike | None = None,
) -> PropagationResult:
    """Propagate an input covariance through a user-supplied forward model.

    ``linear`` uses central finite differences and first-order covariance
    propagation. ``monte_carlo`` draws correlated multivariate-normal inputs
    using the full covariance matrix and reports empirical output quantiles.
    Any failed/non-finite sample is an error rather than being silently dropped.
    """
    point = np.asarray(mean, dtype=float)
    if point.ndim != 1 or point.size != len(budget.parameter_names) or not np.all(np.isfinite(point)):
        raise ValueError("mean must be a finite vector matching the uncertainty budget")
    level = _finite_float(confidence_level, "confidence_level")
    if not 0.0 < level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")
    if method not in {"linear", "monte_carlo"}:
        raise ValueError("method must be 'linear' or 'monte_carlo'")
    covariance = np.asarray(budget.covariance, dtype=float)
    baseline = _as_output_vector(function(point.copy()))
    names = _names(output_names, "output_names", baseline.size) if output_names is not None else tuple(
        f"output_{index + 1}" for index in range(baseline.size)
    )
    units = tuple(output_units) if output_units else tuple("unspecified" for _ in range(baseline.size))
    if len(units) != baseline.size or any(not isinstance(unit, str) or not unit.strip() for unit in units):
        raise ValueError("output_units must contain one non-empty string per output")
    units = tuple(unit.strip() for unit in units)
    if method == "linear":
        jacobian = finite_difference_jacobian(function, point, steps=finite_difference_steps)
        if jacobian.shape != (baseline.size, point.size):
            raise ValueError("Jacobian dimensions do not match the model inputs and outputs")
        output_mean = baseline
        output_covariance = propagate_covariance(jacobian, covariance)
        standard_deviations = np.sqrt(np.maximum(np.diag(output_covariance), 0.0))
        z_score = NormalDist().inv_cdf((1.0 + level) / 2.0)
        lower = output_mean - z_score * standard_deviations
        upper = output_mean + z_score * standard_deviations
        sample_count = 0
    else:
        if isinstance(samples, bool) or not isinstance(samples, (int, np.integer)) or samples < 100:
            raise ValueError("samples must be an integer >= 100 for Monte Carlo propagation")
        # A Jacobian is diagnostic for Monte Carlo, not required by the sample
        # covariance estimate. Permit non-differentiable forward solvers whose
        # small finite-difference perturbations may fail while sampled solves work.
        try:
            jacobian = finite_difference_jacobian(function, point, steps=finite_difference_steps)
            if jacobian.shape != (baseline.size, point.size):
                jacobian = None
        except Exception:
            jacobian = None
        rng = np.random.default_rng(seed)
        try:
            draws = rng.multivariate_normal(point, covariance, size=int(samples), check_valid="raise")
        except (ValueError, np.linalg.LinAlgError) as exc:
            raise ValueError(f"Could not sample the supplied covariance: {exc}") from exc
        output_samples = np.empty((int(samples), baseline.size), dtype=float)
        for index, draw in enumerate(draws):
            try:
                output = _as_output_vector(function(draw), "Monte Carlo function output")
            except Exception as exc:
                raise ValueError(f"Forward model failed for Monte Carlo sample {index}: {exc}") from exc
            if output.shape != baseline.shape:
                raise ValueError(f"Forward model output dimension changed at Monte Carlo sample {index}")
            output_samples[index] = output
        output_mean = np.mean(output_samples, axis=0)
        output_covariance = np.atleast_2d(np.cov(output_samples, rowvar=False, ddof=1))
        standard_deviations = np.sqrt(np.maximum(np.diag(output_covariance), 0.0))
        tail = (1.0 - level) / 2.0
        lower = np.quantile(output_samples, tail, axis=0)
        upper = np.quantile(output_samples, 1.0 - tail, axis=0)
        sample_count = int(samples)

    return PropagationResult(
        output_names=names,
        output_units=units,
        mean=tuple(float(value) for value in output_mean),
        covariance=_tuple_matrix(output_covariance),
        standard_deviations=tuple(float(value) for value in standard_deviations),
        jacobian=_tuple_matrix(jacobian),
        input_names=budget.parameter_names,
        input_units=budget.units,
        input_covariance=budget.covariance,
        method=method,
        sample_count=sample_count,
        confidence_level=level,
        lower_bounds=tuple(float(value) for value in lower),
        upper_bounds=tuple(float(value) for value in upper),
        source_descriptions=budget.source_descriptions,
    )


def propagate_shadow_path_position_uncertainty(
    position_model: ScalarOrVectorFunction,
    mean_parameters: ArrayLike,
    budget: UncertaintyBudget,
    *,
    method: str = "linear",
    samples: int = 10000,
    seed: int | None = 20261122,
    confidence_level: float = 0.95,
) -> PropagationResult:
    """Propagate input uncertainty into local east/north shadow-position offsets.

    The supplied model must return exactly ``(east_offset_km, north_offset_km)``
    in one fixed local tangent frame centred on the nominal path point. Using a
    local tangent frame avoids longitude wrap and latitude-dependent degree
    scaling in the covariance.
    """
    def checked_model(parameters: np.ndarray) -> np.ndarray:
        output = _as_output_vector(position_model(parameters), "shadow position model output")
        if output.size != 2:
            raise ValueError("shadow position model must return exactly east and north offsets")
        return output

    return propagate_uncertainty(
        checked_model,
        mean_parameters,
        budget,
        output_names=("east_offset", "north_offset"),
        output_units=("km", "km"),
        method=method,
        samples=samples,
        seed=seed,
        confidence_level=confidence_level,
    )


def estimate_contact_time_uncertainty(
    contact_name: str,
    contact_time_seconds: float,
    parameters: ArrayLike,
    budget: UncertaintyBudget,
    residual_function: ContactResidualFunction,
    *,
    parameter_steps: ArrayLike | None = None,
    time_step_seconds: float = 0.01,
    minimum_residual_rate: float = 1.0e-12,
) -> ContactTimeUncertainty:
    """Estimate contact-time uncertainty from the implicit contact equation.

    ``residual_function(time_seconds, parameters)`` must return a signed
    geometric residual whose zero defines the contact. Its parameter and time
    units must be consistent with the covariance budget and ``time_step``.
    Near-tangent contacts with a vanishing time derivative are rejected because
    first-order timing uncertainty becomes ill-conditioned there.
    """
    time_value = _finite_float(contact_time_seconds, "contact_time_seconds")
    point = np.asarray(parameters, dtype=float)
    if point.ndim != 1 or point.size != len(budget.parameter_names) or not np.all(np.isfinite(point)):
        raise ValueError("parameters must be a finite vector matching the uncertainty budget")
    dt = _finite_float(time_step_seconds, "time_step_seconds", minimum=np.finfo(float).tiny)
    min_rate = _finite_float(minimum_residual_rate, "minimum_residual_rate", minimum=0.0)

    def residual(time_arg: float, parameter_arg: np.ndarray) -> float:
        value = _finite_float(residual_function(float(time_arg), parameter_arg.copy()), "contact residual")
        return value

    rate = (residual(time_value + dt, point) - residual(time_value - dt, point)) / (2.0 * dt)
    if abs(rate) <= min_rate:
        raise ValueError(
            "Contact residual has a near-zero time derivative; first-order timing uncertainty "
            "is ill-conditioned (possible tangent contact). Use a nonlinear Monte Carlo solver."
        )

    if parameter_steps is None:
        steps = np.cbrt(np.finfo(float).eps) * np.maximum(np.abs(point), 1.0)
    else:
        steps = np.asarray(parameter_steps, dtype=float)
        if steps.shape != point.shape or not np.all(np.isfinite(steps)) or np.any(steps <= 0.0):
            raise ValueError("parameter_steps must be finite, positive, and match parameters")
    residual_gradient = np.empty(point.size, dtype=float)
    for index in range(point.size):
        plus = point.copy()
        minus = point.copy()
        plus[index] += steps[index]
        minus[index] -= steps[index]
        residual_gradient[index] = (
            residual(time_value, plus) - residual(time_value, minus)
        ) / (2.0 * steps[index])
    time_sensitivity = -residual_gradient / rate
    covariance = np.asarray(budget.covariance, dtype=float)
    variance = float(time_sensitivity @ covariance @ time_sensitivity.T)
    uncertainty = math.sqrt(max(variance, 0.0))
    return ContactTimeUncertainty(
        contact_name=contact_name,
        contact_time_seconds=time_value,
        residual_rate_per_second=float(rate),
        parameter_names=budget.parameter_names,
        time_sensitivity_seconds_per_unit=tuple(float(value) for value in time_sensitivity),
        uncertainty_seconds=uncertainty,
        source_descriptions=budget.source_descriptions,
    )


def altitude_uncertainty_to_time_seconds(
    altitude_uncertainty_m: float,
    contact_altitude_rate_m_s: float,
) -> float:
    """Convert a local altitude sigma to timing sigma using ``sigma_h / |dh/dt|``.

    The rate must be evaluated at the contact and supplied in metres/second.
    A zero or near-zero rate is rejected; no root-solver residual is used as a
    substitute for physical altitude uncertainty.
    """
    sigma_h = _finite_float(altitude_uncertainty_m, "altitude_uncertainty_m", minimum=0.0)
    rate = _finite_float(contact_altitude_rate_m_s, "contact_altitude_rate_m_s")
    if abs(rate) <= 1.0e-12:
        raise ValueError("contact_altitude_rate_m_s must be non-zero and sufficiently large")
    return sigma_h / abs(rate)


def estimate_lunar_limb_contact_time_uncertainty(
    contact_name: str,
    contact_time_seconds: float,
    altitude_uncertainty_m: float,
    contact_altitude_rate_m_s: float,
    *,
    source_description: str,
) -> ContactTimeUncertainty:
    """Build a contact-time estimate from documented lunar-limb altitude sigma.

    This is a local linearization of a signed altitude residual. The caller must
    supply the model's per-contact altitude uncertainty and the derivative of
    that residual with respect to time at the same contact.
    """
    sigma_seconds = altitude_uncertainty_to_time_seconds(
        altitude_uncertainty_m, contact_altitude_rate_m_s
    )
    rate = _finite_float(contact_altitude_rate_m_s, "contact_altitude_rate_m_s")
    if not isinstance(source_description, str) or not source_description.strip():
        raise ValueError("source_description must be a non-empty string")
    return ContactTimeUncertainty(
        contact_name=contact_name,
        contact_time_seconds=_finite_float(contact_time_seconds, "contact_time_seconds"),
        residual_rate_per_second=rate,
        parameter_names=("lunar_limb_altitude",),
        time_sensitivity_seconds_per_unit=(-1.0 / rate,),
        uncertainty_seconds=sigma_seconds,
        method="lunar_limb_altitude_linear",
        source_descriptions=(source_description.strip(),),
    )


def apply_contact_uncertainties(
    local_result: Any,
    estimates: Mapping[str, ContactTimeUncertainty],
    *,
    overwrite: bool = False,
) -> tuple[str, ...]:
    """Attach explicit estimates to existing LocalEclipseResult contact events.

    This helper only updates the already-existing ``uncertainty_seconds`` and
    ``uncertainty_note`` fields. Missing contacts are ignored and reported by
    omission from the returned tuple; existing estimates are preserved unless
    ``overwrite=True``.
    """
    events = getattr(local_result, "contact_events", None)
    if not isinstance(events, Mapping):
        raise TypeError("local_result must expose a contact_events mapping")
    applied: list[str] = []
    for supplied_name, estimate in estimates.items():
        if not isinstance(estimate, ContactTimeUncertainty):
            raise TypeError("estimates values must be ContactTimeUncertainty instances")
        name = str(supplied_name).upper()
        event = events.get(name)
        if event is None:
            continue
        if getattr(event, "uncertainty_seconds", None) is not None and not overwrite:
            continue
        event.uncertainty_seconds = estimate.uncertainty_seconds
        sources = "; ".join(estimate.source_descriptions) or "caller-supplied covariance"
        event.uncertainty_note = (
            f"1-sigma physical timing estimate; method={estimate.method}; "
            f"inputs={', '.join(estimate.parameter_names)}; sources={sources}. "
            "Only listed uncertainty sources are included; numerical solver residuals are excluded."
        )
        applied.append(name)
    return tuple(applied)


def combine_independent_uncertainties(*standard_deviations: float) -> float:
    """Combine independent one-sigma values in quadrature."""
    if not standard_deviations:
        raise ValueError("At least one standard deviation is required")
    values = [_finite_float(value, "standard deviation", minimum=0.0) for value in standard_deviations]
    return math.sqrt(sum(value * value for value in values))


def uncertainty_result_to_markdown(result: PropagationResult) -> str:
    """Render a compact, auditable Markdown report."""
    lines = [
        "# Uncertainty propagation report",
        "",
        f"- Method: **{result.method}**",
        f"- Confidence level: **{result.confidence_level:.3%}**",
        f"- Monte Carlo samples: **{result.sample_count}**",
        "",
        "| Output | Mean | 1σ | Lower bound | Upper bound | Unit |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for index, name in enumerate(result.output_names):
        lines.append(
            f"| {name} | {result.mean[index]:.10g} | {result.standard_deviations[index]:.6g} "
            f"| {result.lower_bounds[index]:.10g} | {result.upper_bounds[index]:.10g} "
            f"| {result.output_units[index]} |"
        )
    lines.extend(["", "## Input budget", "", "| Parameter | 1σ | Unit |", "|---|---:|---|"])
    input_covariance = np.asarray(result.input_covariance, dtype=float)
    for index, name in enumerate(result.input_names):
        sigma = math.sqrt(max(float(input_covariance[index, index]), 0.0))
        lines.append(f"| {name} | {sigma:.8g} | {result.input_units[index]} |")
    lines.extend(["", "## Provenance and limitations", ""])
    if result.source_descriptions:
        lines.extend(f"- {item}" for item in result.source_descriptions)
    else:
        lines.append("- No source descriptions were supplied.")
    lines.extend([
        "- The estimate is conditional on the supplied input covariance and forward model.",
        "- Unspecified ephemeris, Earth-orientation, observer, atmosphere, topography, and model errors are not included.",
        "- Numerical root residuals and convergence tolerances are not physical uncertainty estimates.",
        "",
    ])
    return "\n".join(lines)


def write_uncertainty_report(
    result: PropagationResult,
    output_directory: str | Path,
    *,
    stem: str = "uncertainty-propagation",
) -> dict[str, Path]:
    """Write JSON, CSV and Markdown reports; return their paths."""
    if not isinstance(result, PropagationResult):
        raise TypeError("result must be a PropagationResult")
    if not isinstance(stem, str) or not stem.strip() or Path(stem).name != stem:
        raise ValueError("stem must be a simple non-empty filename stem")
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{stem}.json"
    csv_path = directory / f"{stem}.csv"
    markdown_path = directory / f"{stem}.md"

    json_path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow([
            "output", "unit", "mean", "standard_deviation_1sigma",
            "lower_bound", "upper_bound", "confidence_level", "method",
        ])
        for index, name in enumerate(result.output_names):
            writer.writerow([
                name,
                result.output_units[index],
                result.mean[index],
                result.standard_deviations[index],
                result.lower_bounds[index],
                result.upper_bounds[index],
                result.confidence_level,
                result.method,
            ])
    markdown_path.write_text(uncertainty_result_to_markdown(result), encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "markdown": markdown_path}
