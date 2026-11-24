# EclipseKit Contact Solver V2

The contact solver now supports two sign-changing root methods:

- `bisection`: retained as the compatibility default.
- `brent`: safeguarded Brent-Dekker interpolation (inverse quadratic interpolation / secant steps with bisection fallback).

The detailed API also supports automatic bracket expansion, tangent-contact
candidate detection, and machine-readable diagnostics.

## Configure it

```python
from eclipsekit import EclipseConfig, SolverConfig

config = EclipseConfig(
    solver=SolverConfig(
        root_method="brent",
        root_tolerance_seconds=1e-4,
        root_value_tolerance_deg=1e-10,
        root_max_iterations=100,
        auto_expand_bracket=True,
        bracket_expansion_factor=1.8,
        bracket_max_expansions=8,
        bracket_max_span_seconds=6 * 3600,
        bracket_scan_samples=81,
        detect_tangent_contacts=True,
        tangent_scan_samples=101,
        tangent_value_tolerance_deg=1e-7,
    )
)
```

`root_tolerance_seconds` is a numerical stopping target, not a statement of
astronomical accuracy. When the independent variable is a large TT Julian Date,
IEEE-754 floating-point spacing imposes a lower bound on representable time
steps. The solver honors the larger of the requested tolerance and that bound.

## Detailed public solve

```python
from eclipsekit import EclipseEngine, Observer, time_to_utc_iso

engine = EclipseEngine(config=config)
observer = Observer(42.6, -5.5703, elevation_m=800)

diagnostic = engine.solve_contact_detailed(
    observer,
    "external",  # C1/C4 geometry
    "2026-08-12T17:30:00Z",
    "2026-08-12T17:35:00Z",
)

print(diagnostic.status)
print(diagnostic.method)
print(diagnostic.iterations, diagnostic.function_calls)
print(diagnostic.residual)
print(diagnostic.bracket_start, diagnostic.bracket_end)
if diagnostic.converged and diagnostic.root is not None:
    contact_time = engine.ts.tt_jd(diagnostic.root)
    print(time_to_utc_iso(contact_time))
```

`RootResult.root` is a TT Julian Date. The result also provides:

- `converged` and `status` (`converged`, `endpoint_root`, `sampled_root`,
  `tangent_contact`, `no_bracket`, `bracket_not_found`, `non_finite`,
  `function_error`, `max_iterations`, or `no_tangent_within_tolerance`);
- solver method, iteration count and function-evaluation count;
- final bracket and residual;
- `tangent=True` for a near-zero local minimum found without sign change;
- a human-readable diagnostic message.

## Bracket expansion semantics

Expansion is available on `solve_contact_detailed()` and the compatible
`solve_contact()` wrapper. It expands symmetrically around the midpoint of the
supplied interval, scans the expanded interval for sign changes, and chooses
the bracket whose midpoint is nearest the original interval midpoint. The
maximum expansion span and number of expansions are configurable.

For ambiguous intervals containing multiple contacts, pass a tighter interval
or set `auto_expand=False`; the solver cannot infer which physical contact the
caller intended from an interval containing multiple roots.

The engine's internal C1-C4 searches already use phase-bounded intervals and
therefore do not expand outside those physical phase limits. This prevents a
failed C2 search in a partial eclipse from accidentally finding an unrelated
root outside the central phase.

## Tangent contacts

A tangent contact may touch zero without changing the residual sign. When
`detect_tangent_contacts=True`, the solver samples the interval, refines local
minima of the absolute residual, and returns `status="tangent_contact"` only
when the configured `tangent_value_tolerance_deg` is met. This is explicitly a
near-tangent numerical candidate; physical grazing-event classification still
requires interpreting the local geometry and uncertainty.

## Backwards compatibility

- `bisect_root()` still returns `float | None`.
- `EclipseEngine.solve_contact()` still returns a Skyfield `Time` or `None`.
- Existing engine-internal phase-bounded contact solves remain non-expanding.
- `solve_contact_detailed()` is the new diagnostic interface.
