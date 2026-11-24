# Phase 8.3 — Earth-Orientation and Time-Scale Reproducibility

Phase 8.3 adds explicit provenance for the selected Skyfield time-scale source.
The provenance is attached to `EclipseEngine.time_scale_diagnostics()` and to
the Phase 6, Phase 8.1 and path-validation JSON reports.

## Sources and reproducibility levels

| Mode | Recorded identity | Interpretation |
|---|---|---|
| `builtin` | Skyfield version | Version-scoped reproducibility; Skyfield's bundled tables are not separately hashed. |
| `iers` | SHA-256 and byte size of `finals2000A.all`, or hashes of the complete legacy Skyfield table trio | Content-hashed external source. If no active supported file set is found, status is `UNVERIFIED`. |
| `fixed_delta_t` | Exact numeric ΔT assumption | Reproducible historical assumption, not observed operational UT1-UTC data. |
| Caller-supplied time-scale object | Caller-managed | `UNVERIFIED` unless the caller separately records the object's origin. |

## Standalone audit

```powershell
eclipsekit-eop-audit `
  --mode builtin `
  --cache-dir "$HOME\.eclipsekit\ephemerides" `
  --at "2017-08-21T17:20:00Z"
```

For a content-hashed external run, select `--mode iers`. On first use Skyfield may
retrieve the IERS table into the selected cache directory. The report records
the SHA-256 of `finals2000A.all`, unless the complete three-file legacy table
set is present, in which case each active file is hashed and a composite
fingerprint is recorded. Use the same `--cache-dir` for astronomical
calculations and the audit. Built-in mode does not fetch an external IERS file.

To reproduce a historical calculation that explicitly used fixed ΔT:

```powershell
eclipsekit-eop-audit --mode fixed_delta_t --delta-t-seconds 69.2
```

The resulting `PASS_WITH_EXPLICIT_ASSUMPTION` is intentionally distinct from a
content-hashed IERS source. Fixed ΔT must not be presented as observed DUT1.

Outputs:

- `reports/phase8_3/eop-provenance.json`
- `reports/phase8_3/eop-provenance.md`

The cache-selection helper reuses the historical `.pyeclipse/ephemerides`
folder when the new `.eclipsekit/ephemerides` directory does not yet exist.
