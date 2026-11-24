# Scientific validation

EclipseKit includes a reference-comparison runner. It is deliberately separate
from the unit tests: passing unit tests proves software behaviour for tested
inputs, while a scientific validation run compares calculated astronomy with
published external predictions.

## Run it on Windows / PowerShell

From the repository root and with the project virtual environment active:

```powershell
python -m eclipsekit.validation `
  --kernel de440s `
  --references .\data\validation\reference_cases.json `
  --json-out .\reports\scientific-validation.json `
  --markdown-out .\reports\scientific-validation.md
```

Or, after reinstalling the editable package, use the console command:

```powershell
eclipsekit-validate --kernel de440s
```

The global central-axis path can be checked against sparse NASA path-table
subsets. NASA path-table clock labels are recorded in the fixtures as `time_ut1`
(Universal Time / UT1), while ordinary civil timestamps should use `time_utc`.
The validator supports both and infers the scale from the CSV column unless
`--reference-clock` is explicitly supplied.

Operational comparison using the IERS Earth-orientation file:

```powershell
python -m eclipsekit.path_validation `
  --kernel de440s `
  --time-scale-mode iers `
  --reference .\data\validation\global_path_2026-08-12.csv `
  --samples 1201 `
  --tolerance-km 25
```

To reproduce the specific historical NASA 2026 path-table assumption (not to
model observed Earth rotation), use:

```powershell
python -m eclipsekit.path_validation `
  --kernel de440s `
  --time-scale-mode fixed_delta_t `
  --delta-t-seconds 71.4 `
  --reference-clock ut1 `
  --reference .\data\validation\global_path_2026-08-12.csv `
  --samples 1201 `
  --tolerance-km 5
```

The first mode uses IERS `finals2000A.all` through Skyfield and may need an
internet connection on first run. The second uses a fixed ΔT only to reproduce
a published model; the derived DUT1 can be outside UTC's normal ±0.9 s range,
so it must not be used for operational UTC predictions. The 2026 NASA path page
states ΔT=71.4 s and VSOP87/ELP2000-85. Other NASA products can use different
prediction realizations and must be validated separately.

The path validator reports mean, RMS, maximum great-circle error, per-row
errors, reference clock, ΔT, and DUT1. Out-of-range reference times are saved
as row-level errors instead of aborting the full report. A 25 km threshold is
a broad screening tolerance, not a claim of 25 km scientific accuracy. This
test does not validate path boundaries, width, duration, or lunar-limb corrections.

The tool calculates local circumstances for each reference observer and checks
C1–C4, maximum time when available, event classification, and a geocentric
maximum case. It writes JSON and Markdown reports. A non-zero process exit code
means at least one configured check exceeded its tolerance or no result was
found.

## Current reference fixtures

The initial fixtures use NASA's public city circumstance tables for:

- 12 August 2026 — León, Spain (total);
- 8 April 2024 — Dallas, Texas (total);
- 14 October 2023 — Albuquerque, New Mexico (annular).

NASA gives local times rounded to the minute for these city tables. The fixture
converts those displayed times to UTC using the stated civil timezone. The
observer coordinates are approximate city-centre/catalogue points, not survey
coordinates published by NASA. A 120–180 second tolerance is therefore used.
The 2026 geocentric maximum is compared with NASA's 2026 eclipse catalogue,
which rounds greatest eclipse to 17:46 UT and lists ΔT = 75.4 seconds. The
fixture uses a 30-second tolerance because the published UT value is rounded
to a minute; the project calculates with DE440s/Skyfield. A separate, older
Besselian-elements page gives 17:45:53.8 UT with ΔT = 71.4 seconds, so that
older number is not treated as the current minute-rounded benchmark.

## Interpreting results

- `PASS` means the computed value lies within the fixture's stated tolerance.
- `FAIL` means the value is outside the tolerance or the result/contact is
  missing. Inspect the exact signed and absolute error in the JSON report.
- Reference times rounded to a minute are not second-level truth. Do not report
  millisecond-level accuracy from such comparisons.
- The current suite does not validate the neural lunar-limb correction. The
  limb-corrected C1–C4 values need a separate high-resolution lunar-limb
  reference profile and independent contact calculation.
- The Phase 6 suite compares four sparse central-axis path subsets, each with
  seven reference points. It still does not validate both path boundaries, path
  width, umbral depth, shadow velocity, sunrise/sunset, or every city in the
  catalogue. Add versioned reference fixtures before making claims about those
  outputs.

## Adding a reference case

Add an entry to `local_cases` or `global_maximum_cases` in
`data/validation/reference_cases.json`. Every case must include:

1. A unique `case_id` and an event time in UTC ISO-8601 with `Z` or an offset.
2. WGS84 observer latitude/longitude and elevation.
3. Expected contact or maximum times in UTC.
4. The source URL, published time precision, and comparison tolerance.
5. A note explaining timezone conversion, coordinate uncertainty, ephemeris,
   ΔT assumptions, and whether lunar-limb corrections are included.

Prefer official NASA GSFC, USNO, or other clearly documented astronomical
reference sources. Keep the actual reference precision visible; do not reduce
an error tolerance just to force a passing result.


## Phase 4 Besselian regression case

The independent Besselian backend has a separate regression input for the
11 August 1999 total eclipse. The NASA/GSFC page publishes the polynomial
coefficients, reference epoch 11:00 TDT, source ephemeris VSOP87/ELP2000-82,
and ΔT=63.7 s. The automated checks compare: (1) the geocentric
closest-approach offset from the polynomial epoch, (2) the central-line
intersection coordinates against NASA's rounded greatest-eclipse location,
and (3) the local central duration for an observer coordinate rounded to that
region. See `data/validation/besselian_1999_aug11_nasa.json`.

This test validates the polynomial evaluator and the fundamental-plane
geometry against one published event. It is not a multi-event accuracy claim
and does not test a DE440s-derived set of Besselian elements; those are outside
the Phase 4 explicit-input contract. Phase 6 also records a direct-engine vs
published-Besselian diagnostic at the 1999 local observer. That comparison is
labelled `DIAGNOSTIC` and has no acceptance threshold: it quantifies differences
between distinct ephemeris, Earth-orientation and geometric realizations, but
does not establish which realization is closer to the physical event. The
separate Besselian regression remains the pass/fail check against its own NASA
source references.


## Phase 6 unified validation runner

The unified Phase 6 runner supersedes the earlier local-only runner while
retaining its reference-case schema and compatibility entry point. It adds the
NASA path manifest, the NASA 1999 Besselian regression, environment/configuration
metadata, and JSON plus Markdown reports. See
[`VALIDATION_FRAMEWORK.md`](VALIDATION_FRAMEWORK.md) for the complete command
reference, result semantics, data schemas, provenance notes, and lunar-limb
benchmark workflow.

The default suite has nine top-level checks: three local circumstance cases,
one geocentric maximum, four sparse central-axis paths, and one Besselian
regression containing five internal checks. It does not yet validate the full
continuous path envelope, path boundaries/width, umbral depth/velocity, all
city-catalogue predictions, or scientifically certify lunar-limb corrections.
Those remain explicit validation gaps rather than assumed passes.
