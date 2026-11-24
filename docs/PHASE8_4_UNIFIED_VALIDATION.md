# Phase 8.4 — Unified Scientific Validation

Phase 8.4 provides one command that executes the existing scientific
acceptance suite, the Phase 8.1 shadow-corridor comparison, the Phase 8.2
reference-input audit, and the Phase 8.3 Earth-orientation provenance audit.
Each component keeps its own report; the unified report links the results and
applies a conservative aggregate status.

## Run

```powershell
eclipsekit-validate-all `
  --validation-dir "data\validation" `
  --kernel "de440s" `
  --time-scale-mode "builtin" `
  --path-samples 301 `
  --corridor-start "2017-08-21T17:00:00Z" `
  --corridor-end "2017-08-21T17:40:00Z" `
  --convergence-samples "3,11,21,51,101" `
  --boundary-samples 144 `
  --output-dir "reports\phase8_4"
```

An optional `--cache-dir` can select a specific Skyfield cache. By default,
the same cache-selection rule as the engine is used, including reuse of the
legacy PyEclipse cache when appropriate.

## Outputs

- `unified-validation.json` and `unified-validation.md` — aggregate status and
  links to component reports;
- `phase6-scientific-validation.json` and `.md` — local, global maximum, path
  and Besselian acceptance cases;
- `phase8_1_corridor/` — corridor comparison and GIS artifacts;
- `phase8_2-reference-matrix.json` and `.md` — reference asset hashes and
  coverage;
- `phase8_3-eop-provenance.json` and `.md` — time-scale source identity.

## Aggregate status policy

- `PASS`: every component reports `PASS`;
- `FAIL`: at least one component reports `FAIL` and none reports `ERROR`;
- `ERROR`: a component cannot run or produces an unreadable/missing report;
- `PARTIAL`: at least one component is unverified or has an explicitly
  assumed input state (for example, a fixed ΔT assumption).

The unified command does not overwrite source data or modify numerical model
defaults. A PASS is limited to the selected fixtures, source precision,
comparison tolerances, kernel and Earth-orientation assumptions. It does not
certify all eclipses, every point on a shadow corridor, the complete penumbral
footprint, terrain effects, or lunar-limb corrections.
