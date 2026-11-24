# Phase 15 — Scientific certification and 1.0 release gate

## Purpose

Phase 15 adds an evidence-gated release audit. It does **not** convert a passing
unit-test suite into a claim of universal scientific accuracy. The command
`eclipsekit-certify` brings together software quality, API stability, published
reference regressions, live ephemeris validation, lunar DEM checks, independent
control-point evidence and external review records.

The package remains at `0.1.0` until the required evidence is complete. The
release target is `1.0.0`; this phase deliberately does not bump the version
while required gates are missing.

## What is now covered

- Stable API contract v1, with the exact export list pinned in
  `docs/API_MANIFEST_V1.json`.
- SHA-256 fingerprints of the project source, tests and documentation. Local
  `data`, kernels, models, virtual environments, caches and reports are excluded.
- Ruff, `compileall`, the complete pytest suite, `pip check`, wheel construction
  and wheel-content inspection, including the PEP 561 `py.typed` marker.
- Optional dependency vulnerability audit through `pip-audit`.
- Existing numerical regression anchors and the NASA 1999 Besselian reference.
- Existing Phase 8.4 unified dynamic validation report for local/global paths,
  shadow corridor and Earth-orientation provenance.
- PDS3 lunar DEM structural/sample validation when real IMG/LBL paths are
  supplied.
- Independent lunar DEM control-point report validation and a peer-review
  record tied to the exact source-tree SHA-256.
- Reference coverage accounting for total, annular, partial and hybrid eclipse
  classes. Missing classes are shown as gaps rather than inferred. The hybrid
  fixture is a NASA-published geocentric greatest-eclipse epoch comparison; it
  does not claim full hybrid-path or local-contact validation.

## Added partial-eclipse reference

The local reference manifest now includes London for the 2022-10-25 partial
eclipse. The local timetable is published by *Sky & Telescope* and given in
BST; the fixture explicitly converts the contact and maximum times to UTC.
The event classification and global greatest-eclipse epoch are cross-checked
against NASA's GSFC Solar Eclipse Search Engine. The city coordinates are
approximate London-centre coordinates, not a survey-grade observing station.

Sources:

- https://skyandtelescope.org/stargazing-and-observing/solar-and-lunar-eclipses-in-2022/
- https://eclipse.gsfc.nasa.gov/SEsearch/SEdata.php?Ecl=+20221025

The reference manifest also includes the NASA GSFC hybrid eclipse of
2023-04-20. NASA publishes greatest eclipse at 04:16:44.8 UT and provides
Besselian elements for the event. The fixture compares the geocentric
greatest-eclipse time and records the event's hybrid classification. It does
not compare every local contact or the complete central-path transition from
annular to total; that limitation is explicit in the certification report.

The merge helper adds both the London partial local case and the hybrid global
maximum case. The Phase 15 type-coverage gate becomes complete once that merge
has been performed and the reference matrix is re-audited.

## Update the local reference manifest safely

The overlay does not contain the user's `data` directory. Before running the
final reference tests, merge the new partial-eclipse case into the existing
local manifest. The helper is idempotent, preserves every existing record,
refuses conflicting IDs, and creates
`data/validation/reference_cases.json.phase15.bak` before the first change:

```powershell
python scripts/merge_phase15_partial_reference.py
```

If the backup already exists, inspect it first. The helper stops rather than
overwriting an earlier backup. The supplied case uses approximate London
city-centre coordinates and minute-rounded contact times; its tolerances are
recorded in the manifest.

## Run the full published-reference regression suite

Before the final audit, evaluate every local, geocentric-maximum and sparse
central-path reference against DE440s, alongside the published NASA 1999
Besselian regression:

```powershell
eclipsekit-validate `
  --references data/validation/reference_cases.json `
  --path-manifest data/validation/path_reference_manifest.json `
  --besselian-reference data/validation/besselian_1999_reference.json `
  --kernel de440s `
  --cache-dir "$env:LOCALAPPDATA\EclipseKit\kernels" `
  --time-scale-mode builtin `
  --path-samples 301 `
  --json-out reports/phase15/references/reference-validation.json `
  --markdown-out reports/phase15/references/reference-validation.md
```

The JSON report must be `PASS`. The certification runner verifies that each
case ID in the current reference matrix appears in the report and passed, that
the Besselian regression is PASS, that the hybrid global-maximum record was
actually evaluated, and that the source manifest SHA-256 fingerprints match
the current validation inputs. The hybrid fixture verifies the greatest-eclipse time
only, not the entire path transition or every local circumstance.

## Run the release audit

Install the development, lunar-limb and security tools:

```powershell
python -m pip install -e ".[dev,limb,security]"
```

Run the unified direct/Besselian, corridor, reference-matrix and EOP workflow
first. Use the same kernel and cache policy used by the project regression run:

```powershell
eclipsekit-validate-all `
  --validation-dir data/validation `
  --kernel de440s `
  --cache-dir "$env:LOCALAPPDATA\EclipseKit\kernels" `
  --output-dir reports/phase15/unified
```

Then run the evidence gate, including the real PDS3 product already used by the
project's topography checks:

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
  --output-dir reports/phase15/certification
```

The command runs lint, compilation, tests, `pip check`, wheel build and wheel
inspection. It then writes `phase15-certification.json` and
`phase15-certification.md`. Its exit code is `0` only for a complete
`CERTIFIED_WITHIN_DECLARED_SCOPE` decision; missing evidence returns `2` and
failed checks are listed in the report.

## Independent lunar DEM evidence

The release gate expects a real control-point validation report, not the
synthetic sample used by unit tests. Use a published data source that was not
used to generate or tune the DEM under test. The template
`examples/independent_lunar_control_points.template.json` is a schema guide
only; its coordinates and values are placeholders and must not be used as
measurements.

After preparing a genuine dataset, run the existing validator, for example:

```powershell
eclipsekit-validate-dem-control `
  --format pds3 `
  --dem data/SLDEM2015_128_60S_60N_000_360_FLOAT.IMG `
  --label data/SLDEM2015_128_60S_60N_000_360_FLOAT.LBL `
  --control-points data/validation/independent_lunar_control_points.json `
  --tolerance-m 100 `
  --output-dir reports/phase15/control-points
```

The default Phase 15 project policy asks for at least 10 independently declared
control points. This is an administrative minimum, **not** a universal
scientific sufficiency threshold. The tolerance must be justified for the
source uncertainty, DEM resolution and intended application. The tool checks
the dataset's declaration and report metrics; it cannot prove that the source
was genuinely withheld from DEM generation.

Pass the resulting JSON report to `--control-point-report` on the next audit.

## Independent review record

An external reviewer should inspect the algorithms, assumptions, source
provenance, acceptance tolerances and observed residuals. The review record
must refer to the exact `source_tree_sha256` emitted by the certification
report. A template is available at
`examples/phase15_peer_review_record.template.json`.

The record must identify the reviewer, declare independence, state the scope,
record an explicit UTC review date, report an accepted outcome, and disposition
each finding. The record is an external declaration; EclipseKit cannot
cryptographically verify the reviewer's identity or independence.

Pass it to `--peer-review-record` on the next audit.

## Current known blockers to a 1.0.0 scientific certification

- No independent lunar DEM control-point dataset/report has been supplied in
the source tree. Local control-point fixtures are not a substitute.
- No independent external scientific peer-review record has been supplied.
- The full DE440s reference-validation report, including the hybrid global
  maximum comparison and exact input fingerprints, has not yet been supplied.
- The live Phase 8.4 unified-validation report and real DEM validation need to
  be attached to the certification run for the exact local environment.
- The distribution version remains `0.1.0`; it is not changed to `1.0.0` until
  the evidence gates pass and the final wheel is built and re-audited.

These are explicit evidence gaps, not hidden failures. They prevent the tool
from claiming scientific certification prematurely.

## Continuous integration and citation

`.github/workflows/ci.yml` runs the lint, compilation, complete test suite and
wheel/PEP 561 checks across Windows, macOS and Linux for Python 3.10 and 3.12,
and performs a dependency audit in a separate job. `SECURITY.md` describes the
reporting policy. `CITATION.cff` identifies the currently released pre-1.0.0
software version; update it as part of the eventual 1.0.0 release.

## Interpretation

A complete pass certifies only the explicitly listed software, reference,
independent-control and review scope and declared tolerances. It does not
certify all epochs, all observer locations, every eclipse geometry, all lunar
surface products, or every possible third-party extension.
