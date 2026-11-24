## Unreleased — Phase 15 Alpha software-release profile

- Added an explicit `--release-profile alpha` mode to `eclipsekit-certify`.
- The Alpha profile makes only four scientific-1.0 release gates non-blocking:
  stable public API maturity, independent lunar DEM control points, external
  scientific peer review, and the distribution version 1.0.0 requirement.
- Those four gates remain visible with their actual `PARTIAL`/`NOT_RUN` status
  and are still required for the separate scientific-certification decision.
- Core QA, package/wheel integrity, vulnerability audit, published reference
  regressions, Phase 8.4 unified validation and real DEM structural/sample
  validation remain blocking for Alpha readiness.
- The Alpha decision is `ALPHA_RELEASE_READY`, not scientific certification;
  `scientific_certification_status` remains `NOT_CERTIFIED` until all evidence
  requirements are genuinely satisfied. No DEM accuracy or peer-review claim
  is inferred from NASA provenance alone.

## Unreleased — Phase 14: public API and ecosystem

- Added the curated `eclipsekit.api` import surface with an explicit API
  contract version/status while retaining existing package-root imports and
  the current distribution version.
- Added `get_runtime_info()` to report package, Python, required dependency and
  optional Torch/Rasterio versions without importing optional modules.
- Added strict JSON conversion and atomic writing for documented Python,
  dataclass, result-model, date/path and NumPy values. Cycles, unsupported
  values, non-string keys and non-finite numbers are rejected.
- Added explicit, metadata-only entry-point discovery and opt-in loading for
  lunar-limb-model and DEM-reader factories, including duplicate/missing/load
  error types and security documentation.
- Added the PEP 561 `py.typed` marker, wheel inclusion metadata, public API
  compatibility policy, migration guide, ecosystem docs and integration example.
- No numerical algorithms, defaults, core runtime dependencies or report schema
  versions were changed. Third-party extensions are not auto-loaded.

## Unreleased — Phase 13: performance and scalability

- Added precomputed immutable country index arrays to `CityCatalog`, with
  `index_cache_info()` diagnostics and batched read-only index views via
  `iter_index_batches()`.
- Added `EclipseEngine.iter_search_cities()` to stream magnitude-screened city
  hits batch by batch. Existing `search_cities()` keeps its magnitude-sorted
  list return contract and defaults.
- Extended `eclipsekit-benchmark` with country index scan/cache comparisons,
  index-batch iteration and synthetic serial-versus-threaded NumPy batch tests.
- Did not ship a production thread-pool switch: the representative four-thread
  batch benchmark was slower than serial in the measured development container.
  Parallelisation remains deferred pending target-platform end-to-end evidence.
- No astronomy algorithms, numerical defaults, or runtime dependencies changed.

## Unreleased — Phase 11: advanced interval and multi-observer solar-eclipse search

- Added `EclipseEngine.search_solar_eclipses(start, end, observers, ...)` to
  search a bounded UTC interval across explicit observer locations.
- Uses new-moon phase events to discover candidates, refines geocentric maximum,
  and independently calculates local maximum and C1–C4 circumstances per site.
- Returns grouped `SolarEclipseSearchResult`, `SolarEclipseSearchEvent`, and
  `SolarEclipseLocationHit` objects with event counts and JSON-friendly
  serialization. Local maxima are filtered to the requested interval and the
  next-eclipse fallback is disabled during the search.
- Added a multi-location command-line example and focused deterministic tests.
- This does not scan unlisted locations, alter physical models, or independently
  certify eclipse-prediction accuracy.

## Unreleased — Phase 9.5: frame-aware lunar DEM query access

- Added `TransformedLunarDEMModel`, a lazy virtual view that accepts target-frame
  queries, inverse-transforms them for native source DEM sampling, and converts
  returned heights between explicitly declared spherical reference radii.
- Added target-frame `product_info`/limb metadata that retain source product and
  transform provenance and integrate with Phase 9.4 control-point validation.
- Added strict checks for the source product frame label, source vertical datum,
  source reference radius, query values, and reader lifecycle ownership.
- Added scalar/provider and broadcast-array query APIs plus a PDS3 example and
  deterministic tests. This does not warp/rewrite a raster, infer frame identity,
  supply an uncertainty, or validate real lunar DEM accuracy.
- Assistant-side full suite: **716 passed, 1 skipped**; the skip is the optional
  local `CountryPoints.csv` catalogue fixture absent from this build snapshot.
  `compileall` and Ruff remain to be run in the user's Windows environment; Ruff
  could not be installed in the isolated build environment because network access
  was unavailable.

## Unreleased — Phase 9.1: tiled lunar DEM access

- Kept PDS3 IMG files read-only and memory-mapped, while adding a configurable
  bounded LRU cache of converted height tiles for repeated interpolation.
- Added `LunarDEMWindow`, `read_window()`, and streaming `iter_tiles()` APIs;
  returned window arrays are independent, read-only float64 metre arrays and
  preserve missing values as NaN.
- Added cache statistics (hits, misses, evictions, resident bytes and byte
  ceiling), explicit cache clearing, and deterministic cache release on close.
- Extended `eclipsekit-validate-topography` with tile-size/cache controls and
  JSON/Markdown cache diagnostics.
- PDS4, GeoTIFF, JP2, mosaicking, reprojection and body-fixed frame conversions
  remain out of scope. No independent DEM accuracy or DE421-to-DE440 transform
  is claimed by this phase.

## Phase 7.6 — Real Lunar Topography Integration

- Added lazy, read-only PDS3 IMG ingestion for simple-cylindrical lunar DEMs.
- Added strict validation of target, projection, east-positive longitude,
  coordinate frame, pixel registration, sample type, dimensions, map geometry,
  spherical reference radius, record pointers and binary file length.
- Added PDS scale/unit/offset conversion to radial height above the labelled
  sphere in metres; the reference radius is not added twice.
- Added metadata provenance to the common lunar-limb model metadata and contact
  serialization, plus deterministic interpolation checks and JSON/Markdown
  validation reports.
- Added the `eclipsekit-validate-topography` CLI and a local PDS3 usage example.
  No NASA source data are bundled or downloaded.
- JP2/PDS4 decoding, frame transformations, tile mosaicking and independent
  topographic accuracy validation remain out of scope. Windows verification is
  pending.

## Phase 7.5 — Uncertainty Propagation

- Added explicit `UncertaintyBudget` records with named parameters, units,
  source descriptions, full covariance matrices, correlation support, and
  positive-semidefinite validation.
- Added central finite-difference Jacobians, first-order covariance propagation,
  and seeded Monte Carlo propagation of correlated multivariate-normal inputs.
- Added implicit contact-time uncertainty from the signed contact equation,
  local east/north shadow-path position covariance, parameter sensitivities, and
  a near-tangent conditioning guard.
- Added opt-in attachment of quantified estimates to existing `ContactEvent`
  fields, plus lunar-limb altitude-to-time conversion and contact-estimate
  helpers that require a supplied local contact rate.
- Added JSON/CSV/Markdown reports, a reproducible synthetic example, and tests.
  Synthetic inputs are not real-eclipse uncertainty data. Windows verification
  remains pending.

## Phase 7.3 — Global Shadow Corridor V2 (Windows-verified)

- Added direct-engine central and penumbral cone intersections against WGS84,
  track-relative boundaries, geodesic cross-track widths, along-track
  centerline chords, local tangent bearings, and first-order duration estimates.
- Added antimeridian-aware GeoJSON/KML and CSV exports, sparse NASA/GSFC 2017
  reference data, and a named-tolerance validator.
- Corrected the duration estimate to use the along-track centerline chord rather
  than cross-track width, and corrected bearing estimation to use a symmetric
  local time difference rather than sparse requested samples.
- The user's corrected Windows run reported **3/3 NASA reference rows PASS** at
  the original tolerances (center/edge 8 km, width 8 km, duration 10 s); the
  full suite reported **520 passed**, **94% statement coverage**, and
  `compileall` passed.
- The model still does not compute the complete partial-eclipse penumbral
  sunrise/sunset footprint and excludes local terrain, atmosphere, and lunar-limb
  relief.

## Unreleased — Phase 7.2 Solver, Validation and Lunar-Limb Hardening

- Hardened `solve_root()` option validation for booleans, integer counts, finite
  tolerances, bracket expansion factors and span limits.
- Tangent-refinement exceptions and non-finite values now produce structured
  `RootResult(status="function_error")` diagnostics rather than escaping.
- Hardened `golden_section_minimize()` input and objective-value validation while
  preserving propagation of objective exceptions.
- Added four test modules covering root/minimizer edge cases, validation records,
  manifest/path/CLI/report failure branches, and lunar-limb model/provider
  contracts.
- User's Windows verification: 476 tests passed, Ruff clean, 94% statement
  coverage, and `full_api_check.py` completed. Assistant-side test run also
  passed with the local catalogue temporarily present.
- No public API signature, runtime dependency, or astronomy numerical default
  was changed.

## Unreleased — Phase 7.1 Coverage Expansion

- Expanded the automated suite to 287 tests in the assistant-side environment;
  statement coverage rose from 64% at Phase 6 to 88%.
- Added broad deterministic ephemeris, engine, Besselian wrapper, city search,
  local-contact, sunrise/sunset, lunar-limb provider and benchmark CLI tests.
- Increased coverage to 96% in `engine.py`, 100% in `ephemeris.py`, 97% in
  `path_validation.py`, 98% in `timeutils.py`, and 86–97% in the city and
  lunar-limb validation modules.
- Hardened `compare_shadow_path()` to record rows missing both reference time
  columns as row-level errors rather than raising `KeyError`.
- No public API, dependency or numerical-default changes.

## Phase 6 — Validation Framework

- Added a unified reference runner covering local C1-C4/maximum times, geocentric
  greatest eclipse, four NASA sparse central-axis path datasets, and the NASA
  11 August 1999 Besselian coefficient/path regression.
- Added versioned path manifests with source URLs, UT1/UTC clock preservation,
  data-resolution metadata, tolerance enforcement, duplicate-ID checks, file
  existence checks, and relative-path containment.
- Added auditable JSON and Markdown validation reports with software/runtime,
  kernel, time-scale, configuration, source, result, and error metadata.
- Added a direct-engine vs published-Besselian diagnostic for maximum, C1-C4,
  event classification and central duration. It is explicitly non-acceptance
  diagnostic data because the two calculation paths use different realizations.
- Added a separate independent lunar-limb benchmark CLI for user-supplied DEM,
  angular-profile, and neural models, including bias/MAE/RMSE, median/max error,
  optional combined-uncertainty diagnostics, and a clearly labelled spherical
  zero-relief comparator.
- Limb benchmark status is `UNASSESSED` unless explicit acceptance thresholds
  are supplied; a completed numerical evaluation alone is not reported as
  scientific validation.
- Strengthened validation fixture parsing and sample validation. Added tests for
  path manifests, provenance/path traversal, NASA Besselian regression, path
  comparisons, limb benchmark metrics and uncertainty handling.
- Added `pyeclipse-validate` and `pyeclipse-validate-limb` console commands;
  retained `python -m eclipsekit.validation` compatibility. An empty acceptance
  suite is reported as ERROR rather than a false PASS.
- The default suite does not validate full path boundaries/width, velocity,
  umbral depth, or independently certify lunar-limb contact corrections.


# Changelog

## Phase 7.4 — Eclipse Observation Planner

- Added `EclipseEngine.plan_observations()` for multi-observer local-circumstance
  evaluation around a selected epoch. Next-eclipse fallback is disabled so a
  missing local event is recorded as `no_eclipse`.
- Added immutable plan/site/weight models, configurable normalized weights, a
  0–100 heuristic based on obscuration, Sun altitude at local maximum, and
  C1–C4 event span, deterministic ranking, minimum-altitude filtering, and
  explicit calculation-error records.
- Added strict local-score validation, overflow-safe weight normalization, and
  optional forwarding of a Phase 5 lunar-limb model. Unrelated sunrise/sunset,
  shadow-metric and planet work is disabled during ranking.
- Added CSV/JSON exporters, Markdown/JSON-friendly plan representations, a
  multi-site DE440s example, API documentation, and additional tests.
- The score is weather-agnostic and is not a probability of clear skies or
  successful observation. Clouds, terrain horizon, light pollution, access,
  travel, and equipment are not modelled.
- Windows verification reported 553 tests passed, 93% total statement coverage,
  Ruff clean, compileall passed, and the five-site DE440s example ran without
  calculation errors.



## Phase 5 — Lunar Limb Framework

- Added a provider-neutral `LunarLimbModel` protocol with query, prediction,
  provenance, status, and optional point-uncertainty records.
- Added a zero-relief spherical baseline, a bilinear gridded selenographic DEM
  provider (CSV/NPZ loaders, explicit coverage errors, optional uncertainty
  propagation), and a periodic tabulated apparent-limb angular profile.
- Added a Phase 5 adapter for the existing PyTorch checkpoint while preserving
  direct use of the legacy `LunarLimbCorrector` interface.
- Added `limb_model=` as the preferred argument to local, city, and country
  calculations; the old `limb_corrector=` argument remains supported.
- Added per-contact model provenance and optional altitude uncertainty to
  serialized limb-correction results. A model validation RMSE is not treated
  as per-contact uncertainty.
- No LOLA/Watts/DEM datasets or model checkpoints are bundled; the providers
  require caller-supplied data with documented provenance.

## Phase 4 — Besselian Backend

- Added validated Besselian polynomial/elements models with explicit TT epoch,
  coefficient units, validity interval, μ convention, source and ephemeris metadata.
- Added independent fundamental-plane observer projection on an oblate Earth,
  local external/internal contact roots, partial/total/annular classification,
  geocentric closest approach and central-axis ground-track calculations.
- Added callable or fixed ΔT support, including an automatic Skyfield TT/UT1
  bridge through `EclipseEngine` opt-in methods.
- Added the NASA/GSFC 11 August 1999 element fixture and a published-case
  regression test for maximum time, central-line location and totality duration.
- Documented the element conventions and explicit limitations; the backend
  does not yet derive elements from SPK data or solve complete path boundaries.

## Phase 3 — Contact Event Model

- Added public `ContactEvent` records for C1-C4 and local maximum, attached to
  `LocalEclipseResult.contact_events` in chronological order.
- Added distinct UTC, TT-JD, and UT1-JD representations and serializable
  topocentric geometry, position/vertex angles, solar visibility, and root
  solver diagnostics.
- Attached per-contact lunar-limb correction metadata when available.
- Added `central_phase_duration_seconds`; partial-only events now express the
  absence of a central phase as `None`, while legacy `duration_seconds`
  semantics are retained.
- Uncertainty remains explicitly unquantified (`None`) rather than inferred
  from numerical root residuals.

## Unreleased — Contact Solver V2 milestone
- Added a safeguarded Brent-Dekker root solver while retaining bisection as the compatibility default.
- Added optional automatic bracket expansion with configurable growth factor, span, scan density, and expansion count.
- Added explicit tangent-contact candidate detection for near-zero local minima without a sign change.
- Added `RootResult` diagnostics (status, convergence, method, iterations, function calls, final bracket, residual, and tangent flag).
- Added `EclipseEngine.solve_contact_detailed()` while preserving the legacy `solve_contact()` return type.
- Kept engine-internal C1-C4 searches constrained to their physical phase intervals to avoid expansion into unrelated contacts.

## Previous milestone — Configuration API
- Added immutable `EclipseConfig`, `EphemerisConfig`, `ContactModelConfig`, `SolverConfig`, and `AtmosphereConfig` public objects.
- Routed ephemeris, radius, solver-tolerance, and refraction settings through the configuration layer.
- Preserved the EclipseKit 0.1.0 constructor keyword interface as a compatibility bridge.
- Added JSON-friendly configuration summaries and configuration validation tests.


## 0.1.0-alpha — 2026-11-21

- Initial modular package extracted from the solar-eclipse simulator.
- Configurable JPL BSP kernels and Skyfield time handling.
- Local solar-eclipse circumstances, contact solving, and local next-event search.
- Global maximum, WGS84 shadow-axis path, city scans, and country event searches.
- Optional PyTorch lunar-limb correction using the supplied checkpoint architecture.
- Corrected ΔT polynomial branch selection for modern dates.
- Fixed the global path/country search pre-filter and sunrise/sunset observer input.
- Reworked lunar-limb contact root brackets and recalculated terrain at trial times;
  C1–C4 all produced corrected times in the developer's León integration test.
- Added external-reference validation fixtures, GeoJSON/CSV exports, tests, and
  GitHub Actions CI configuration.

This is an alpha release. See `docs/SCIENTIFIC_VALIDATION.md` for the scope and
limits of the current independent reference comparisons.


## Phase 7.7 — Performance and scientific regression hardening

- Added reproducible numerical micro-benchmarks and environment-aware baseline
  comparison with optional memory tracking and cProfile output.
- Added deterministic scientific regression checks covering WGS84 geometry,
  root solving (including Julian-day scale), covariance propagation, seeded
  Monte Carlo repeatability, and the NASA 1999 Besselian reference.
- Added optional PDS3 DEM inclusion in the regression report and CI smoke runs.
- No astronomical numerical defaults or runtime dependencies were changed.

## Phase 8.1 — Reproducible Shadow-Corridor Validation

- Added the `eclipsekit-validate-corridor` CLI for a reproducible DE440s-backed
  comparison of the central shadow axis, its two boundaries, central width and
  first-order duration estimate against the existing NASA/GSFC 2017 fixture.
- Added nested multi-resolution sampling comparisons. These are explicitly
  labelled diagnostics against the finest requested run, not independent truth
  or an additional scientific accuracy claim.
- Added auditable JSON and Markdown reports with kernel, time-scale, input,
  tolerance and geometry metadata, plus GeoJSON/CSV/KML exports from the finest
  requested sampling.
- Added input validation and automated tests for nested grids, convergence
  matching, CLI reporting and generated artifacts.
- No DEM, BSP kernel, optional ML checkpoint or private data catalogue is
  included in the overlay.

## Phase 8.2 — Expanded Scientific Reference Matrix

- Added `eclipsekit-audit-references` to validate the structure of the existing
  local/global, path, Besselian and shadow-corridor reference assets.
- Added a source/case coverage inventory and SHA-256 fingerprints for each
  small referenced input file, including all path tables and Besselian elements.
- Reported missing eclipse-class coverage as an explicit gap rather than
  inferring event type or scientific validity.
- The audit is an input/provenance check, not an independent accuracy claim.

## Phase 8.3 — Earth-Orientation Reproducibility

- Added time-scale source provenance for Skyfield built-in tables, external
  IERS `finals2000A` data, fixed-Delta-T assumptions and caller-supplied scales.
- Recorded Skyfield version for built-in mode and SHA-256/size for a located
  external IERS table; missing fingerprints are explicitly `UNVERIFIED`.
- Included EOP provenance in engine diagnostics and scientific validation
  reports, and added a standalone `eclipsekit-eop-audit` command.
- Added a consistent default cache resolver that can reuse legacy PyEclipse
  ephemeris/EOP cache files.

## Phase 8.4 — Unified Scientific Validation

- Added `eclipsekit-validate-all` to run the Phase 6 scientific reference suite,
  Phase 8.1 corridor validation, Phase 8.2 reference audit and Phase 8.3 EOP
  audit as one repeatable workflow.
- Added conservative aggregate status logic and a unified JSON/Markdown report
  linking every component report.
- Added focused tests and documentation. No eclipse-geometry numerical
  defaults or mandatory runtime dependencies were changed.

## Phase 9.2 — Multi-Format Lunar DEM Support

- Added a strict PDS4 `Array_2D_Image` lunar DEM adapter with read-only memory
  mapping, declared coordinate geometry, unit scaling and bounded tile cache.
- Added optional Rasterio/GDAL adapters for GeoTIFF and JPEG 2000 (JP2), with
  windowed reads and explicit lunar coordinate-frame / vertical-datum metadata.
- Added `eclipsekit-validate-dem-format` for metadata and sample-interpolation
  checks with JSON and Markdown reports.
- Added the optional `raster` dependency extra; core PDS3/PDS4 users do not need
  Rasterio.
- Added format-specific tests and documentation. No coordinate transformation
  or scientific accuracy certification is implied by format-level PASS.


## Phase 9.3 — Explicit lunar frame and vertical-datum transformations

- Added immutable, validated lunar frame rotations with provenance, inverse
  transforms, Cartesian and spherical latitude/longitude conversion.
- Added the published fixed DE440 PA to DE421 ME/MER rotation and its inverse,
  using the passive rotation convention documented by Park et al. (2021).
- Added spherical reference-radius conversion that preserves radius from the
  lunar centre, plus a combined point-transform API for scalar and NumPy inputs.
- Added `eclipsekit-audit-lunar-frames`, which compares all five published
  retroreflector coordinate pairs and writes JSON/Markdown evidence.
- No raster reprojection, resampling, geoid conversion, or time-dependent PCK/FK
  orientation is performed; callers must supply declared frame/datum metadata.


## Phase 9.4 — Independent lunar DEM control-point validation

- Added a versioned JSON control-point manifest with explicit coordinate frame,
  planetocentric/east-positive coordinate convention, spherical reference radius,
  value interpretation (height or radial distance), source URI/DOI and SHA-256.
- Added `validate_lunar_dem_control_points()` for PDS3, PDS4, GeoTIFF and JP2
  readers, including explicit optional DE440 PA / DE421 ME point transforms.
- Added per-point residuals, uncertainty-normalised residuals, bias, MAE, RMSE,
  median absolute error, normalised MAD, 95th-percentile and maximum absolute error.
- Added an explicit independence gate: a dataset not declared independent of the
  DEM under test cannot yield an acceptance `PASS`.
- Added `eclipsekit-validate-dem-control` and JSON/Markdown reports.
- The bundled example control points are synthetic schema fixtures only; no
  independent lunar measurements are bundled and no real DEM accuracy claim is
  made by the unit-test suite.

## Phase 9.5 — frame-aware lunar DEM query access

- Added `TransformedLunarDEMModel`, a virtual view that inverse-transforms
  target-frame queries, samples the original reader in its native frame, and
  converts height to a target spherical reference radius.
- Preserved source-product and transform provenance in target-view metadata.
- Windows verification reported 717 passed, Ruff clean, compileall clean, and
  all 14 Phase 9.5 focused tests passed.
- No raster is warped, copied, resampled or rewritten.

## Phase 9.6 — coverage-aware lunar DEM mosaic routing

- Added `LunarDEMMosaicModel` to route queries across compatible DEM readers
  using declared rectangular coverage in a shared frame, vertical datum, and
  spherical reference radius.
- Added deterministic `priority`, `finest`, and explicit unweighted `mean`
  strategies, per-prediction source provenance, and broadcast `predict_many`.
- Added antimeridian-aware coverage bounds, metadata overrides for sources with
  non-rectangular/virtual coverage, and optional explicit source lifecycle
  ownership.
- Source errors inside declared coverage are surfaced rather than hidden by
  silent fallback. No raster merging, seam blending, reprojection, or accuracy
  certification is performed.

## Phase 9.7 — lunar DEM mosaic overlap-consistency audit

- Added `audit_lunar_dem_mosaic_overlaps()` and `eclipsekit-audit-dem-mosaic`
  to compare original source readers directly within declared pairwise overlap.
- Added deterministic regular-grid sampling, strict source-value checks,
  per-point vertical residuals, bias, MAE, RMSE, median absolute difference,
  95th percentile and maximum absolute difference.
- Added unwrapped longitude-branch intersection logic for antimeridian and
  0/360-crossing regions, with duplicate equivalent endpoint samples removed.
- Added explicit `PASS`, `FAIL`, `ERROR`, `NO_OVERLAP`, and `NOT_COMPARABLE`
  semantics, strict JSON/Markdown reporting, and a PDS3 JSON-manifest CLI.
- No seam blending, raster correction, reprojection, or absolute-accuracy
  certification is performed.


## Phase 12 — Advanced Geometry and Observation

- Added `HorizonProfile` with validated azimuth/altitude knots and cyclic linear
  interpolation across 0/360 degrees.
- Added `EclipseEngine.calculate_observation_geometry()` and
  `ObservationGeometry` for detailed topocentric Sun/Moon geometry, apparent
  altitude/azimuth, angular radii, separation, position/parallactic/vertex
  angles, magnitude, obscuration and solar-limb horizon clearances.
- Added optional `horizon_profile` support to `calculate_local()` and contact
  events; existing no-profile visibility status values are preserved.
- Added `EclipseEngine.calculate_shadow_footprint()` and `ShadowFootprint` for
  instantaneous central/penumbral cone intersections with WGS84, including
  partial-coverage semantics, track orientation and kinematic metadata.
- Added antimeridian-aware GeoJSON linework export that preserves missing
  boundary gaps and does not invent polygon closures.
- Added two runnable examples, a skyline-profile JSON template, and the Phase 12
  technical note. Geometric and visibility assumptions are explicitly bounded;
  no terrain clipping or new scientific-certification claim is made.

## Phase 13 — Performance and Scalability

- Added precomputed country indices, read-only index batches and cache
  diagnostics to `CityCatalog`.
- Added bounded streaming city search while preserving the existing sorted-list
  result contract of `search_cities()`.
- Extended benchmarks for cache lookup, streaming batches and serial-versus-
  threaded workloads. No production thread pool was enabled because the
  measured representative threaded workload was slower.

## Phase 14 — Public API and Ecosystem

- Added the curated `eclipsekit.api` import surface and stabilized API contract
  v1 while retaining package-root backwards compatibility.
- Added runtime diagnostics, strict JSON serialization and atomic report writing.
- Added metadata-only extension discovery and explicit loading of trusted DEM
  reader and lunar-limb model entry points.
- Added PEP 561 typing metadata, integration documentation and packaging checks.
- Fixed portable JSON path serialization so Windows paths use `/` separators.

## Phase 15 — Scientific Certification and 1.0 Release Gate

- Added `eclipsekit-certify`, an evidence-gated report for software QA, wheel
  contents, API manifest, reference fingerprints, published numerical
  regressions, unified live validation, real DEM checks, independent control
  points and external review.
- Added deterministic source-tree SHA-256 fingerprints that exclude local DEMs,
  kernels, models, virtual environments, caches and reports.
- Added an explicit partial solar-eclipse reference case for London on
  2022-10-25, with UTC conversion and published source provenance.
- Added the NASA GSFC hybrid eclipse of 2023-04-20 as a global greatest-eclipse
  time reference. The event type is source metadata; this is not a full local
  contact or central-path transition validation.
- Added cross-platform CI workflow, dependency-audit extra, security policy,
  citation metadata and evidence templates.
- The distribution remains `0.1.0`. No `1.0.0` release or scientific
  certification is declared until all mandatory evidence gates pass.
