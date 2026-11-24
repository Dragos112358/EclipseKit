# Phase 14 — Public API and Ecosystem

## Delivered

- Added `eclipsekit.api` as a curated public integration facade with an explicit
  API contract version and stabilization-candidate status.
- Kept the established package-root imports and the distribution version
  (`0.1.0`) intact; new imports resolve to the same underlying objects.
- Added runtime/environment reporting without importing optional Torch or
  Rasterio modules.
- Added strict JSON conversion and atomic file writing for dataclasses,
  `to_dict()` results, standard values and NumPy data. Unsupported/cyclic or
  non-finite content is rejected rather than silently altered.
- Added explicit entry-point discovery/loading for lunar-limb models and DEM
  readers. Discovery is metadata-only; extension code is loaded only on an
  explicit request. Duplicate providers and load failures are reported.
- Added the PEP 561 `py.typed` marker and included it in wheel build metadata.
- Added API compatibility, plugin ecosystem, migration documentation and a
  standalone external-application example.

## Non-goals / limits

- This phase does not claim the distribution is already a 1.0 release; final
  certification, release versioning and public release gate belong to Phase 15.
- No extension is bundled, downloaded, automatically installed, sandboxed or
  automatically instantiated.
- A Python API compatibility test does not prove numerical accuracy.
- JSON helpers do not serialize arbitrary Skyfield objects or replace
  versioned domain-specific validation reports.

## Assistant-side verification

Record the exact package tests, lint, compile, wheel and smoke-test outcomes in
`INTEGRATION_STATUS.md` before Windows verification. Windows validation remains
pending until the user runs the overlay against the existing project and sends
its log.
