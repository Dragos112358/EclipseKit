# EclipseKit Phase 7.1 — test coverage expansion

## Scope

Phase 7.1 expands the automated test suite without changing the public API or
altering the numerical defaults. The only production-code change in this
overlay is improved row-level error handling in `compare_shadow_path()` when a
reference row has neither `time_utc` nor `time_ut1`.

The tests use deterministic astronomy fakes where a JPL kernel or a live
Skyfield integration is unnecessary. Independent reference tests from Phase 6
remain unchanged and continue to provide the scientific acceptance layer.

## Assistant-side result

Environment: Python 3.13.5, Linux, pytest + pytest-cov. With the local
`data/CountryPoints.csv` temporarily available:

- **287 tests passed**
- **88% total statement coverage**
- `python -m compileall -q src tests examples` passed

The user's Windows environment uses Python 3.12.10. Re-run the commands in
`PHASE7_1_APPLY.md` there; its exact coverage percentage can differ slightly
between Python versions and coverage.py releases.

## Module coverage

| Module | Coverage |
|---|---:|
| `__init__.py` | 100% |
| `ephemeris.py` | 100% |
| `engine.py` | 96% |
| `path_validation.py` | 97% |
| `cities.py` | 97% |
| `timeutils.py` | 98% |
| `earth_orientation.py` | 98% |
| `models.py` | 92% |
| `config.py` | 91% |
| `besselian.py` | 88% |
| `exports.py` | 88% |
| `limb.py` | 87% |
| `limb_validation.py` | 86% |
| `geometry.py` | 85% |
| `contacts.py` | 85% |
| `validation.py` | 79% |
| `validation_framework.py` | 68% |

Total statement coverage: **88%**.

## Test additions

- Ephemeris loading: named/cached/local kernels, custom bodies, optional-body
  handling, missing paths, invalid combinations, and IERS/fixed-Delta-T paths.
- Engine: scalar/time-scale helpers, geometric residuals, solver adapters,
  global shadow geometry, city searches, local eclipse branches, partial events,
  failed roots, optional diagnostics, limb-correction success/failure, sunrise
  and sunset, Besselian wrappers, and contact event metadata.
- Time and path tools: calendar boundaries, timezone normalization, UT1
  conversion, malformed reference rows, interpolation boundaries, and CLI
  outcomes.
- Lunar limb: safe checkpoint loading behaviour, neural prediction plumbing,
  angular/libration geometry, benchmark model selection, CLI argument checks,
  report generation, and failure handling.
- City catalog: missing/empty files, column aliases, delimiters, invalid rows,
  and index selection.

The neural checkpoint test uses synthetic metadata and a mocked state-dict load
so it tests the Python/PyTorch integration path. It does **not** validate the
accuracy of the user's supplied neural model or any lunar topography dataset.

## Known remaining coverage gaps

The next coverage iterations should focus on:

1. `validation_framework.py` — path manifest handling, Besselian/reference
   comparison failures, report branches, and CLI orchestration.
2. `validation.py` — malformed reference records, per-contact tolerances,
   skipped/error cases, and report rendering.
3. `contacts.py` — less common non-finite, endpoint, bracket expansion, and
   tangent-candidate branches.
4. Remaining low-frequency branches in `limb.py`, `geometry.py`, and
   `exports.py`.

Do not exclude scientific or numerical code merely to increase the reported
percentage. A branch should be marked excluded only when it is demonstrably
unreachable or platform-specific, with a reason documented next to the code.
