# Phase 7.5 — Uncertainty Propagation

Phase 7.5 introduces an explicit, provenance-aware uncertainty layer. It does
not infer physical uncertainty from root-solver residuals, convergence
thresholds, or the number of iterations. Existing calculations remain
unchanged unless a caller explicitly supplies an uncertainty budget and asks
for propagation.

## Public API

```python
from eclipsekit import (
    UncertaintyBudget,
    propagate_uncertainty,
    estimate_contact_time_uncertainty,
    apply_contact_uncertainties,
    altitude_uncertainty_to_time_seconds,
)
```

### Input covariance budget

`UncertaintyBudget` stores the names, units, covariance matrix, and source
notes for uncertain input parameters. Off-diagonal covariance is preserved.
For independent inputs, the matrix is diagonal.

```python
budget = UncertaintyBudget.from_standard_deviations(
    ("observer_latitude", "observer_longitude"),
    (0.002, 0.003),
    units=("deg", "deg"),
    correlation=((1.0, 0.2), (0.2, 1.0)),
    source_descriptions=("Survey metadata, document ID XYZ",),
)
```

All values must use consistent, explicitly declared units. The software does
not convert units or decide whether an input uncertainty is scientifically
credible. A budget with a non-symmetric or non-positive-semidefinite covariance
matrix is rejected.

### General propagation

For a forward model `y = f(x)`, linear propagation uses

\[
\Sigma_y = J\,\Sigma_x\,J^T,
\]

where `J` is calculated by central finite differences. This is a local,
first-order approximation. Use `method="monte_carlo"` for a correlated
multivariate-normal input distribution when nonlinear effects matter. Monte
Carlo requires at least 100 samples, has a reproducible seed, and fails rather
than silently dropping non-finite or failed model evaluations.

```python
result = propagate_uncertainty(
    model_function,
    mean_parameters,
    budget,
    output_names=("contact_offset", "shadow_width"),
    output_units=("s", "km"),
    method="linear",  # or "monte_carlo"
    confidence_level=0.95,
)
```

`PropagationResult` reports output means, one-sigma standard deviations,
confidence bounds, output covariance, the Jacobian when locally available, the
original input covariance, method, sample count, and provenance notes. Monte
Carlo does not require a Jacobian; for non-differentiable or failed local
perturbations its diagnostic Jacobian is `None`. JSON, CSV, and Markdown reports
are written with `write_uncertainty_report()`.

### Global shadow-path position uncertainty

`propagate_shadow_path_position_uncertainty()` is the path-specific adapter. Its
caller-supplied model must return east/north offsets in kilometres in one fixed
local tangent frame centred on the nominal path point. This avoids treating
longitude degrees as a constant distance or mishandling the antimeridian. The
returned 2×2 covariance retains correlation between the east and north errors.
The caller must recompute the path point from the uncertain inputs for each
model evaluation; the adapter does not manufacture an uncertainty for the
existing deterministic `ShadowPathPoint`.

### Implicit contact-time uncertainty

For a contact defined by a signed geometric residual `g(t, p) = 0`,

\[
\frac{\partial t}{\partial p_i}
= -\frac{\partial g/\partial p_i}{\partial g/\partial t},
\qquad
\sigma_t^2 = \nabla_p t\;\Sigma_p\;(\nabla_p t)^T.
\]

`estimate_contact_time_uncertainty()` evaluates these derivatives by central
finite differences. The caller must provide the actual signed contact residual
and the parameter covariance. The time coordinate is seconds from a caller-
defined epoch; it is not silently converted to UTC.

The function rejects a near-zero time derivative. Tangential or near-tangent
contacts are ill-conditioned for first-order timing propagation and should be
studied with a nonlinear forward solver and Monte Carlo sampling instead.

`apply_contact_uncertainties()` attaches explicit estimates to matching
`ContactEvent` objects using the existing `uncertainty_seconds` and
`uncertainty_note` fields. Existing estimates are preserved unless
`overwrite=True`. Missing contacts are not fabricated.

### Lunar-limb altitude uncertainty

`altitude_uncertainty_to_time_seconds(sigma_h, dh_dt)` implements

\[
\sigma_t = \frac{\sigma_h}{|dh/dt|}.
\]

`estimate_lunar_limb_contact_time_uncertainty()` packages that result as an
attachable `ContactTimeUncertainty`. The altitude uncertainty must come from a
model/provider with documented uncertainty, and `dh/dt` must be evaluated at
the relevant contact in m/s. The existing lunar-limb prediction's altitude
uncertainty is not automatically converted to time because the engine does not
yet retain a validated local contact-altitude rate for every event. The helper
makes the necessary assumption explicit instead of guessing the rate.

## Scope and scientific limitations

- Only supplied input uncertainties are propagated. Missing ephemeris,
  Earth-orientation, Delta-T/UT1, observer survey, atmospheric, topographic, or
  model uncertainties remain excluded and must be listed as limitations.
- The linear method assumes local differentiability and first-order adequacy.
- Monte Carlo assumes a multivariate-normal input distribution. It does not
  model heavy tails, bounded distributions, discrete model choices, or
  conditional correlations unless the caller encodes them in a suitable model.
- A small root residual is a numerical convergence diagnostic, not a physical
  prediction uncertainty.
- The new API is opt-in and does not change existing eclipse results or
  numerical defaults.

## Verification

Run `python examples/uncertainty_propagation.py` after installing the project
and development dependencies. The sample inputs are deliberately synthetic;
they demonstrate the API and must not be cited as uncertainty estimates for a
real eclipse.
