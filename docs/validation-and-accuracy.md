---
description: Understand EclipseKit's scientific validation workflow, reference tolerances, numerical assumptions and known limits before interpreting eclipse calculations.
---

# Validation, accuracy and scientific scope

EclipseKit separates software testing from scientific reference validation.

- Unit tests check software behavior for covered inputs.
- Reference validation compares calculated quantities with published external eclipse predictions using explicitly stated tolerances.
- A successful test suite does not certify every event, location, output field or physical model.

## Run the reference validator

After installing EclipseKit:

```bash
eclipsekit-validate --help
```

A typical project-root validation command is:

```bash
eclipsekit-validate --kernel de440s
```

For the full Windows/PowerShell workflow, fixture schema, report fields and time-scale conventions, see [Scientific validation](SCIENTIFIC_VALIDATION.md).

## What a validation result means

- `PASS` means the computed value lies within the configured reference tolerance.
- `FAIL` means a configured value is outside tolerance or a required result/contact is missing.
- A reference rounded to a minute is not second-level ground truth.
- A limited set of central-axis path points does not validate the full path envelope, path width or every sunrise/sunset limit.
- A regression against one Besselian event does not certify all events or all ephemeris realizations.

## Record assumptions

For meaningful comparisons, include the source URL, published precision, time convention, observer coordinates, ephemeris, Earth-orientation data, adopted radii, solver settings and any lunar-limb correction.

Do not reduce tolerances merely to force a passing result. Keep reference-convention reproductions distinct from standard physical defaults.

## More detail

- [Scientific validation](SCIENTIFIC_VALIDATION.md)
- [Validation framework](VALIDATION_FRAMEWORK.md)
- [Performance and regression](PERFORMANCE_AND_REGRESSION.md)
- [Uncertainty propagation](UNCERTAINTY_PROPAGATION.md)
- [Data provenance](DATA_PROVENANCE.md)
