# EclipseKit Phase 15 — Alpha software release profile

## Purpose

The `alpha` profile is intended for a clearly labelled GitHub software
pre-release of the current `0.1.0` package. It separates software/package
readiness from scientific certification for a `1.0.0` release.

It does **not** remove the scientific requirements from EclipseKit or mark
missing evidence as passed. It only makes four gates non-blocking for the
Alpha software-release decision:

1. `public_api_maturity` — API status may remain `stabilization-candidate`.
2. `independent_lunar_dem_control_points` — no independent checkpoint report
   is required to publish the software Alpha.
3. `independent_scientific_peer_review` — external scientific review may still
   be pending.
4. `distribution_version_1_0_0` — the Alpha package remains version `0.1.0`.

All four retain their real `PARTIAL` or `NOT_RUN` status in the JSON/Markdown
report, with `required_for_scientific_certification=true` and
`required_for_alpha_release=false`.

## What remains mandatory for Alpha

The profile continues to require the software checks (Ruff, compileall, full
pytest, `pip check`, wheel build/content checks and `pip-audit` when requested),
the API manifest consistency check, reference-matrix/fingerprint checks, the
live published-reference report, numerical anchors, NASA Besselian regression,
real PDS3 DEM structural/sample validation, and the Phase 8.4 unified report.

The user's passing SLDEM2015 PDS3 structural/sample validation and published
reference regressions remain part of the Alpha gate. NASA/mission provenance
is recorded as input provenance. It is not treated as an independent
measurement campaign of absolute lunar DEM accuracy; the separate control
point requirement is deferred for Alpha, not falsely passed.

## PowerShell command

Run from the project root with the virtual environment active:

```powershell
eclipsekit-certify `
  --source-root . `
  --validation-dir data/validation `
  --reference-report reports/phase15/references/reference-validation.json `
  --unified-report reports/phase15/unified/unified-validation.json `
  --dem-image data/SLDEM2015_128_60S_60N_000_360_FLOAT.IMG `
  --dem-label data/SLDEM2015_128_60S_60N_000_360_FLOAT.LBL `
  --expected-coordinate-system "MEAN EARTH/POLAR AXIS OF DE421" `
  --run-pip-audit `
  --release-profile alpha `
  --output-dir reports/phase15/certification-alpha
```

Expected successful decision:

- `EclipseKit release check (alpha): ALPHA_RELEASE_READY`
- `Software readiness: PASS`
- `Scientific certification: NOT_CERTIFIED`
- Exit code `0`

If a mandatory Alpha gate fails, the decision is `REJECTED` or `NOT_READY` and
the Alpha release must not be treated as ready.

## GitHub release wording

Use the package-matching tag `v0.1.0` and mark the GitHub release as a
pre-release. State clearly that it is a software Alpha. Do not label it
`1.0.0`, scientifically certified, or independently validated for absolute
lunar DEM accuracy.

## Future scientific 1.0.0 release

Use the default `scientific` profile. The four gates become mandatory again.
Supply actual independent control measurements and provenance, obtain an
external review bound to the exact source-tree SHA-256, deliberately stabilize
the public API, and only then promote the distribution to `1.0.0` and rerun
the scientific certification profile.
