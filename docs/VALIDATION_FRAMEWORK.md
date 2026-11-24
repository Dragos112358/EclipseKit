# EclipseKit Phase 6 — Validation Framework

## Purpose

Phase 6 provides one reproducible runner for the reference checks that are
actually supported by the current repository. It does not turn a finite set of
regression cases into a universal accuracy guarantee.

The default suite contains:

1. Three local-circumstance cases (León 2026, Dallas 2024, Albuquerque 2023),
   using published local times rounded to the minute and explicitly recorded
   city-coordinate/tolerance caveats.
2. One NASA geocentric greatest-eclipse time check for 12 August 2026.
3. Four sparse WGS 84 central-axis path comparisons (2017 total, 2019 total,
   2020 annular, 2026 total). Each is compared at the timestamps preserved in
   the fixture's `time_ut1` column.
4. One pure Besselian regression using NASA's published 11 August 1999
   coefficients, checked against the coefficient epoch/max time, interpolated
   NASA central-line coordinates, total-eclipse classification, totality
   duration, and convergence/order of C1-C4.

The default run therefore reports nine top-level acceptance cases. The Besselian case
contains five internal checks. In addition, the runner records a **direct-engine vs
Besselian diagnostic** at the NASA 1999 local observer. This is deliberately
reported as `DIAGNOSTIC`, not counted as a pass/fail acceptance case, because
the direct engine and published Besselian elements use different ephemeris and
Earth-orientation realizations.

## Run the complete suite

Run from the project root in the active Windows virtual environment:

```powershell
python -m pip install -e ".[dev,limb]"
python -m ruff check src tests examples
python -m eclipsekit.validation_framework --kernel de440s
```

The installed console command is equivalent:

```powershell
eclipsekit-validate --kernel de440s
```

The command writes:

- `reports/phase6-validation.json` — complete machine-readable results,
  per-reference metrics, source provenance, runtime/platform/kernel/time-scale
  metadata, configured tolerances, and errors;
- `reports/phase6-validation.md` — a human-readable summary.

Exit code `0` means all selected checks passed. Exit code `1` means at least one
scientific comparison failed or raised a runtime error. Exit code `2` indicates
the runner could not load its configuration or initialize the ephemeris/time
scale.

### Options

```powershell
eclipsekit-validate --help
```

- `--references PATH`: local and geocentric reference fixture.
- `--path-manifest PATH`: global central-axis comparison manifest.
- `--besselian-reference PATH`: NASA 1999 Besselian regression descriptor.
- `--kernel NAME_OR_PATH`: Skyfield/JPL kernel; defaults to `de440s`.
- `--time-scale-mode builtin|iers|fixed_delta_t`: Earth-orientation mode.
- `--delta-t-seconds VALUE`: required only for `fixed_delta_t` mode.
- `--path-samples N`: number of generated global-path samples; default `301`.
- `--skip-paths` / `--skip-besselian`: omit optional groups for diagnosis.
- `--json-out PATH` / `--markdown-out PATH`: report destinations.

Do not run the whole multi-event manifest with a single fixed ΔT merely to
reproduce the 2026 NASA path table. The NASA 2026 table documents a historical
prediction realization using ΔT=71.4 s and VSOP87/ELP2000-85; that is not the
observed Earth-orientation value for all four events. The default suite uses
the engine's configured `builtin` time-scale source and records it in the
report. A specific 2026 fixed-ΔT reproduction should use a one-event manifest
and should be labelled as a reproduction experiment, not operational EOP.

## Results and interpretation

Top-level statuses:

- `PASS`: all tested reference rows/checks satisfy the tolerance stored with
  that reference case.
- `FAIL`: a comparison completed but exceeded a tolerance, the expected event
  type/contact was absent, or not all reference rows were compared.
- `ERROR`: the calculation or an individual reference could not be evaluated.

Every time tolerance is interpreted in seconds and compared as an absolute
signed-time difference. Every path tolerance is in kilometres and is applied to
the maximum great-circle distance among the fixture's reference samples. A path
case fails if even one reference point cannot be evaluated.

`PASS` is always scoped to the specific input fixtures, observer coordinates,
source precision, model, ephemeris, Earth-orientation mode, and limits recorded
in the report. In particular:

- NASA local circumstance tables are minute-rounded; their listed city
  coordinates are not necessarily the exact observer coordinates used by the
  engine.
- The path fixtures contain seven sparse sample points from published NASA
  central-line tables. They do not validate the entire continuous path, path
  boundaries, width, umbral depth, shadow speed, or sunrise/sunset.
- The 2026 NASA path solution uses a different prediction realization from the
  default operational EOP run. Its wider 15 km tolerance is a broad regression
  screen, not a precision specification.
- The 1999 Besselian case validates the Besselian evaluator/reduction against
  the published NASA coefficient set and a small segment of its path table. It
  is not an independently derived Besselian solution and is not a multi-epoch
  benchmark.
- The default suite does not certify any lunar-limb model or its corrected
  contact times. Use the separate limb benchmark below with independent data.

## Lunar-limb model benchmarking

A topography-aware model must be checked against a reference profile that is
independent of the model's training and input data. Phase 6 provides a generic
CSV benchmark runner; it does not bundle LOLA, Watts, or other terrain data.

The benchmark CSV requires:

```csv
sample_id,selenographic_latitude_deg,selenographic_longitude_deg,limb_angle_deg,reference_altitude_m,reference_uncertainty_m
```

`sample_id` and `reference_uncertainty_m` are optional. Latitude is in degrees
north, longitude is east-positive in the interval [-180, 180], apparent limb
angle is in degrees, and reference altitude is in metres relative to the
vertical/radial datum that must be documented. `reference_uncertainty_m` is
optional and must be a one-sigma uncertainty in metres if used in the
normalised-residual summary.

For example, to test a caller-supplied DEM against an independent check-point
CSV:

```powershell
eclipsekit-validate-limb `
  --model dem `
  --model-file data/lunar_dem.csv `
  --model-name "LOLA regional DEM vX" `
  --model-source "NASA PDS product ID / release / processing version" `
  --vertical-datum "documented radial reference surface" `
  --benchmark-csv data/lunar_limb_independent_checks.csv `
  --benchmark-source "independent publication/table/product and version" `
  --benchmark-vertical-datum "same radial reference surface" `
  --max-rmse-m 30
```

The DEM CSV has its own schema:

```csv
latitude_deg,longitude_deg,altitude_m,uncertainty_m
```

A spherical baseline can be run as a controlled zero-relief comparison, but it
is not terrain truth. Angular profiles and neural checkpoints are also
supported by `--model angular-profile` and `--model neural`; see
`LUNAR_LIMB_FRAMEWORK.md` for their input formats.

The limb benchmark returns `UNASSESSED` when all samples were evaluated but no
acceptance threshold was supplied. This is intentional: computing MAE/RMSE does
not itself define what accuracy is acceptable. `--max-rmse-m` and
`--max-absolute-error-m` set explicit acceptance limits; only then can a
evaluation receive `PASS` or `FAIL`. Any out-of-coverage or invalid model
predictions are recorded and prevent a pass. The spherical comparator is
reported separately and never used as a substitute for a measured reference.

If both the reference sample and the model provide pointwise uncertainty, the
runner reports combined-sigma residuals and descriptive fractions within 1σ
and 2σ. These fractions are not a calibrated confidence statement unless the
uncertainties are calibrated and the benchmark samples are independent.
A model-wide training `validation_rmse_m` is retained as metadata only; it is
not treated as pointwise uncertainty.

## Extending the reference suite

### Local/geocentric event cases

Add cases to `data/validation/reference_cases.json`. Use the existing schema
and retain a unique `case_id`, an explicit timezone in every timestamp, a real
source URL, source precision, documented observer coordinates, and a tolerance
that reflects the source precision and coordinate uncertainty. Keep event
classification and expected contact names explicit.

### Global path cases

Add a `path_cases` entry to
`data/validation/path_reference_manifest.json` and a CSV with exactly one time
column (`time_utc` or `time_ut1`) plus `latitude_deg,longitude_deg`. Do not
rename a source UT1/Universal Time column to UTC. Record source time spacing,
coordinate rounding, prediction realization, and tolerance. The manifest
loader rejects duplicate identifiers, missing files, non-finite/invalid
thresholds, and reference paths escaping the manifest directory.

### New Besselian cases

Create a separately versioned coefficient JSON with the epoch, all six
polynomials, cone-angle tangents, validity interval, μ convention, source, and
ephemeris. Add a reference descriptor that gives the published ΔT and
comparisons/tolerances. Do not mix element sets from different ephemerides or
silently extend a polynomial beyond its published validity interval.

## Scientific sources used by the starter fixtures

- NASA GSFC 2017 total-eclipse central path: <https://eclipse.gsfc.nasa.gov/SEpath/SEpath2001/SE2017Aug21Tpath.html>
- NASA GSFC 2019 total-eclipse central path: <https://eclipse.gsfc.nasa.gov/SEpath/SEpath2001/SE2019Jul02Tpath.html>
- NASA GSFC 2020 annular-eclipse central path: <https://eclipse.gsfc.nasa.gov/SEpath/SEpath2001/SE2020Jun21Apath.html>
- NASA GSFC 2026 total-eclipse central path and prediction assumptions: <https://eclipse.gsfc.nasa.gov/SEpath/SEpath2001/SE2026Aug12Tpath.html>
- NASA GSFC 1999 Besselian elements: <https://eclipse.gsfc.nasa.gov/SEbeselm/SEbeselm1951/SE1999Aug11Tbeselm.html>
- NASA GSFC 1999 total-eclipse path: <https://eclipse.gsfc.nasa.gov/SEpath/SEpath1951/SE1999Aug11Tpath.html>

The local-circumstance fixture URLs are recorded with each entry in
`reference_cases.json`.
