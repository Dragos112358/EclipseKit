# EclipseKit Phase 7.2 — solver, validation, and lunar-limb hardening

## Scope

Phase 7.2 follows the user's Windows-verified Phase 7.1 baseline. It focuses on
error contracts and branch coverage in the root solver, reference validation,
validation reporting, and lunar-limb providers. It does not add a new public
feature, change the public API signatures, alter numerical defaults, or add a
runtime dependency.

The ephemeris loader and main engine workflows already received broad mocked
and deterministic coverage in Phase 7.1. Phase 7.2 keeps those regression tests
in the complete suite; it does not rewrite the engine or ephemeris implementation.

## Production-code hardening

The only production-code change in this overlay is in `src/eclipsekit/contacts.py`:

- `solve_root()` now validates boolean flags, integer-valued iteration/sample
  options, finite positive tolerances, expansion factors, and span limits before
  evaluating the residual function. Boolean values are not accepted as numeric
  iteration counts or tolerances.
- Tangent-candidate refinement now checks every residual evaluation. A callable
  exception or non-finite value encountered during refinement is returned as a
  structured `RootResult` with `status="function_error"` and a diagnostic
  message, rather than escaping from the solver.
- `golden_section_minimize()` validates its finite interval, positive finite
  tolerance, and positive integer iteration limit. Non-finite objective values
  raise a clear `ValueError`; exceptions from the objective remain visible to
  callers.
- The legacy `bisect_root()` contract remains `float | None` for an invalid or
  failed bracket. `solve_root()` remains the diagnostic API.

No root-solving algorithm or astronomy default was intentionally changed.

## Test additions

Four new test modules extend the suite:

- `test_contacts_phase72.py`: malformed option types, NaN/Inf inputs, endpoints,
  bisection/Brent error paths, iteration limits, scan and expansion failures,
  sampled roots, tangent-refinement errors, and minimizer contracts.
- `test_validation_phase72.py`: malformed local/global reference records,
  parser failures, skipped/error states, tolerance evaluation, and Markdown
  report branches.
- `test_validation_framework_phase72.py`: manifest and path-reference edge
  cases, provenance/path containment, Besselian regression outcomes, path-runner
  errors, diagnostic states, overall status accounting, and CLI/report failures.
- `test_lunar_limb_phase72.py`: metadata/query/prediction contracts, gridded and
  angular provider validation, loader failures, lazy neural-model loading, and
  coordinate/prediction adapter errors.

The new tests use deterministic fakes and temporary files. They do not download
kernels, require an internet connection, or claim to validate lunar topography.

## Assistant-side verification

Environment: Python 3.13.5, Linux, pytest + pytest-cov. Ruff and Skyfield are not
installed in this isolated environment.

With the local `CountryPoints.csv` temporarily available:

- **476 tests passed**
- **94% total statement coverage** (3,755 statements; 215 missed)
- `python -m compileall -q src tests examples` passed

Without that local catalogue asset:

- **475 passed, 1 skipped**
- The skipped test is the supplied 8,133-row city catalogue test. The asset was
  removed after verification and is not part of this overlay.

### Module coverage

| Module | Coverage |
|---|---:|
| `__init__.py` | 100% |
| `ephemeris.py` | 100% |
| `engine.py` | 96% |
| `validation_framework.py` | 97% |
| `contacts.py` | 97% |
| `limb.py` | 97% |
| `path_validation.py` | 97% |
| `cities.py` | 97% |
| `validation.py` | 96% |
| `timeutils.py` | 98% |
| `earth_orientation.py` | 98% |
| `models.py` | 92% |
| `config.py` | 91% |
| `besselian.py` | 88% |
| `exports.py` | 88% |
| `limb_validation.py` | 86% |
| `geometry.py` | 85% |

Coverage percentages are statement coverage from this test run, not a measure of
scientific prediction accuracy. The remaining misses are listed by pytest-cov
and should be addressed based on meaningful reachable branches rather than by
adding exclusions or tests that merely execute lines.

## Windows verification still required

The overlay must be checked in the user's existing Windows 11 / Python 3.12.10
virtual environment. Ruff was not available in the assistant-side environment.
Run the commands in `PHASE7_2_APPLY.md`. In particular, verify the complete suite
with the local `CountryPoints.csv`, Ruff, and `examples/full_api_check.py`.

The next work package is Phase 7.3 (Global Shadow Corridor V2), but it should
start after this overlay passes on Windows.
