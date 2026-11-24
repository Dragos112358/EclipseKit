# Phase 8.2 — Scientific Reference Matrix and Data Fingerprinting

Phase 8.2 audits the small validation reference set already supplied with the
project. It validates reference-case and manifest schemas, checks that every
referenced file exists and is parseable, inventories source identifiers, and
records SHA-256 fingerprints for all assets used by the matrix.

## Run

```powershell
eclipsekit-audit-references `
  --validation-dir "data\validation" `
  --output-dir "reports\phase8_2"
```

Outputs:

- `reports/phase8_2/reference-matrix.json`
- `reports/phase8_2/reference-matrix.md`

The asset inventory includes the local/global reference manifest, the path
manifest and all referenced path CSVs, the Besselian descriptor and elements,
and the 2017 shadow-corridor reference CSV. Each asset is stored as a relative
path, byte size, role list, and SHA-256 digest.

## Interpretation

`PASS` means the reference inputs were structurally valid, all expected files
were present and parseable, and their bytes were fingerprinted. It is an input
integrity/provenance audit, not a scientific-accuracy PASS. Missing eclipse
class coverage is reported as a gap; the tool does not infer a missing total,
annular, or partial event from a filename or event date.

The validation dataset is intentionally external to the wheel. Do not place the
multi-gigabyte lunar DEM or BSP kernel in `data/validation` merely to satisfy
this audit; those are separate runtime products and are not reference fixtures.
