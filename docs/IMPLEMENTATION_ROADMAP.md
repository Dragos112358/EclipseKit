# EclipseKit implementation roadmap

This roadmap tracks the six original engineering milestones and the subsequent quality/feature expansion work. Work is delivered in
small, testable overlays to avoid replacing a working numerical engine with an
unverified rewrite.

| # | Milestone | Status | Scope |
|---:|---|---|---|
| 1 | Configuration API | Implemented | Immutable public configs for ephemeris/EOP, contact radii, solver tolerances, atmosphere; legacy constructor retained. |
| 2 | Contact Solver V2 | Implemented | Safeguarded Brent-Dekker and bisection, optional symmetric bracket expansion, tangent-candidate detection, detailed convergence diagnostics. |
| 3 | Contact Event Model | Implemented | Structured C1/C2/maximum/C3/C4 events with UTC/UT1/TT, topocentric geometry, root diagnostics, visibility, optional limb metadata, and explicitly unquantified uncertainty. |
| 4 | Besselian backend | Implemented and Windows smoke-tested | Explicit Besselian-element input, polynomial evaluation, local C1-C4 solver, geocentric maximum and central-line ground track. Phase 6 will expand the independent validation matrix. |
| 5 | Lunar Limb framework | Implemented and Windows smoke-tested | Provider protocol; zero-relief baseline; gridded DEM and tabulated apparent-limb profile adapters; neural checkpoint adapter; per-contact provenance and optional altitude uncertainty. |
| 6 | Validation framework | Implemented and Windows-verified | Combined local/geocentric references, sparse NASA central-axis path comparisons, published NASA Besselian regression, direct-vs-Besselian diagnostic, auditable JSON/Markdown reports, and a separate independent lunar-limb benchmark CLI. Additional USNO/SVS/Swiss Ephemeris adapters and broader path-boundary/limb datasets remain future extensions. |

## Compatibility policy

- Existing 0.1.x calls remain supported while the new configuration API is
  introduced.
- Numerical defaults are not silently changed by a refactor.
- An option is not exposed as configurable until it has an implementation and
  tests.
- A PASS is always tied to a named reference source, clock scale, tolerance,
  and the assumptions under which that reference was produced.
- Experimental neural limb corrections are never presented as independent
  topographic truth without DEM-based validation.


## Phase 7 — Quality, coverage and scientific expansion

| # | Work package | Status | Scope |
|---:|---|---|---|
| 7.1 | Coverage expansion | Implemented and Windows-verified | Expanded deterministic unit/integration tests across ephemeris, engine, city catalogue, time, path validation, lunar-limb providers and benchmark CLI. The user's Windows run reported 287 passing tests and 88% statement coverage. |
| 7.2 | Solver, validation and lunar-limb hardening | Implemented and Windows-verified | Expanded edge/error-contract tests for contacts, validation, validation framework and lunar-limb providers. Hardened root/minimizer option validation and tangent-refinement diagnostics. User's Windows run: 476 tests passed and 94% total statement coverage. |
| 7.3 | Global shadow corridor V2 | Implemented and Windows-verified | WGS84 cone intersections, track-relative boundaries, cross-track widths, along-track chords, corrected local bearing/duration estimates, NASA 2017 regression, GeoJSON/KML/CSV. User's corrected live NASA check: 3/3 rows PASS at original tolerances. |
| 7.4 | Eclipse observation planner | Implemented and Windows-verified | Multi-observer local circumstances, transparent weighted scores, deterministic rankings, Sun-altitude threshold, per-site no-event/error statuses, optional limb provider, CSV/JSON/Markdown outputs. |
| 7.5 | Uncertainty propagation | Implemented and Windows-verified | Explicit covariance budgets, finite-difference Jacobians, first-order and Monte Carlo propagation, implicit contact-time sensitivity, lunar-limb altitude-to-time conversion and contact-estimate helpers, and auditable JSON/CSV/Markdown reports. User's Windows run: 574 passed, 93% coverage, Ruff and compileall clean. Only caller-supplied defensible uncertainties are quantified. |
| 7.6 | Real lunar topography integration | Implemented; Windows real-raster sample validation PASS; full-suite result pending | Lazy read-only PDS3 IMG reader for simple-cylindrical lunar DEMs, label/frame/datum/storage validation, reference-sphere height conversion, bilinear samples, metadata provenance, deterministic sample validator and JSON/Markdown reports. First target: NASA LOLA/SELENE SLDEM2015. User Windows run: 9/9 real-raster sample checks PASS. No download, JP2/PDS4 decoder, reprojection or frame transform. |
| 7.7 | Performance and regression hardening | Implemented; live Windows verification pending | Reproducible micro-benchmarks and optional cProfile output; baseline comparison guarded by runtime identity; numerical stress anchors for WGS84, root solving and uncertainty propagation; NASA 1999 Besselian regression gate; optional real-DEM checks; CI smoke integration. Full live DE440s path/corridor validation remains an explicit separate run. |

### Phase 7.1 notes

- Added deterministic tests for JPL ephemeris loader paths using patched Skyfield
  loaders, avoiding network/kernel dependencies in unit tests.
- Expanded engine tests for local contacts, city searches, sunrise/sunset,
  shadow geometry, contact event metadata, Besselian wrappers and lunar-limb
  correction success/failure paths.
- Expanded time, city catalogue, path-reference and lunar-limb benchmark CLI
  tests, including malformed inputs and file/report failures.
- Fixed `compare_shadow_path()` so a row missing both `time_utc` and `time_ut1`
  becomes a recorded row-level error instead of aborting the full comparison.
- No public signatures, default model parameters, ephemeris choices or
  distribution dependencies were changed.
- See `docs/TEST_COVERAGE_7_1.md` for module coverage and remaining priorities.

### Phase 7.2 notes

- Added deterministic edge/error tests for solver input validation, endpoint
  handling, Brent/bisection failures, interval scanning/expansion, tangent
  refinement, and golden-section minimization.
- Hardened `solve_root()` option contracts and reportable tangent-refinement
  errors; hardened `golden_section_minimize()` against invalid/non-finite inputs.
- Added broad failure-path and reporting tests for `validation.py`,
  `validation_framework.py`, and lunar-limb provider/loader interfaces.
- The user's Windows run reported **476 passed**, **94% statement coverage**,
  Ruff clean, `compileall` passed, and `full_api_check.py` completed.
- The assistant-side checkout also reproduced the 476-test suite with its local
  test catalogue present. See `PHASE7_2_APPLY.md` and
  `docs/PHASE7_2_HARDENING.md`.

### Phase 7.3 notes

- Added `EclipseEngine.global_shadow_corridor()` and
  `global_shadow_corridor_for_eclipse()` to sample the central cone and outer
  penumbral cone intersections with the WGS84 reference ellipsoid.
- Added left/right cross-track boundaries relative to track direction, WGS84
  inverse geodesic widths, boundary-hit coverage, ground speed and explicitly
  labelled first-order duration estimates. Initial duration code incorrectly
  used cross-track width / speed; the remediation now uses the along-track cone
  chord / speed. Local tangent bearing is estimated with a short symmetric time
  difference, independent of requested sample spacing.
- Added GeoJSON, CSV and KML corridor exports. GeoJSON lines/polygons and KML
  lines are split at the antimeridian; incomplete boundary runs are not joined
  across missing samples.
- Added a three-row NASA/GSFC 2017 path-table sample and a named-tolerance
  centerline/boundary/width/duration comparison helper.
- Initial assistant-side full suite: **516 passed** with local test assets
  present; **94% statement coverage**. The user's first Windows NASA comparison
  reported **0/3 PASS**. The correction added local track-bearing differentiation
  and along-track chord durations without relaxing the acceptance thresholds.
- The corrected Windows run then reported **3/3 NASA rows PASS** at the original
  tolerances: center errors 0.745–1.585 km, maximum edge errors 1.872–2.111 km,
  width errors 0.391–0.510 km, and duration errors 0.134–0.193 s. The same run
  reported **520 passed**, **94% statement coverage**, and compileall passed.
- The current method returns time slices only when the central axis hits Earth;
  it does not yet compute the entire partial-eclipse penumbral footprint to
  global sunrise/sunset limits. The model uses spherical Sun/Moon radii and WGS84
  ellipsoid; local terrain, atmosphere and lunar-limb relief are excluded.

### Phase 7.4 notes

- Added a multi-observer local-circumstances planner exposed as
  `EclipseEngine.plan_observations()`. It disables next-eclipse fallback and
  reports `no_eclipse`, `calculation_error`, and below-minimum-Sun-altitude
  sites separately.
- Added a transparent 0–100 weighted heuristic using obscuration, apparent
  solar altitude at local maximum, and C1–C4 event span. Weights and score caps
  are configurable; tie-breaking is deterministic.
- Added validation for non-finite score inputs, weights, option values, model
  ranks, and plan consistency. Optional Phase 5 limb models are forwarded.
- Added CSV, JSON, and Markdown outputs plus a DE440s multi-site example.
- The user's Windows verification (Python 3.12.10) reported **553 passed**,
  **93% total statement coverage**, Ruff clean, `compileall` passed, and the
  DE440s multi-site example completed with four recommended sites, one site
  below the minimum Sun altitude, zero no-eclipse sites, and zero calculation
  errors. This is a software/example verification, not independent validation
  of the scoring heuristic.
- The planner does not model weather, real skyline/terrain horizon, light
  pollution, safety, access, transport or equipment. Its score is not a success
  probability or an independent accuracy measure.


### Phase 7.5 notes

- Added `UncertaintyBudget` with explicit parameter names, units, full covariance
  matrices, source descriptions, symmetry and positive-semidefinite validation.
- Added central finite-difference Jacobians, first-order covariance propagation,
  and seeded multivariate-normal Monte Carlo propagation. Failed/non-finite
  Monte Carlo model evaluations fail the run and are not silently discarded.
- Added implicit contact-time uncertainty using `dt/dp = -(dg/dp)/(dg/dt)`,
  local east/north shadow-path position covariance, and a guard for near-tangent/
  ill-conditioned contacts. Estimates can be
  attached to existing `ContactEvent` fields without changing the engine's
  numerical calculation path.
- Added explicit lunar-limb altitude-to-time conversion and contact-estimate
  helpers requiring a caller-supplied local altitude rate; no rate or physical uncertainty is
  inferred from root residuals.
- Added JSON/CSV/Markdown uncertainty reports, a synthetic example, and
  deterministic tests. Synthetic inputs are demonstrations, not real-eclipse
  uncertainty claims. The user's Windows run reported 574 tests passed, 93%
  coverage, Ruff clean, and compileall passed.


### Phase 7.6 notes

- The user's Windows run against the downloaded SLDEM2015 128 ppd IMG/LBL reported **Status: PASS, 9 PASS / 0 not PASS** with the expected DE421 mean-Earth/polar-axis coordinate-system value. This verifies PDS3 metadata/storage and the configured nine-point interpolation grid only; it does not establish global DEM accuracy or independent contact-time validation. A complete post-7.6 Windows pytest/Ruff run was not included in that result.

- Added `PDS3LunarDEMModel.from_pds3_img()` as a provider-compatible reader for
  uncompressed PDS3 simple-cylindrical lunar `IMG` products. Data are accessed
  through a read-only memory map; interpolation reads only the four required
  neighbouring cells, including the 360-degree longitude seam.
- Validates the declared target, east-positive longitude, body-fixed frame,
  projection, pixel registration, sample type/size, image dimensions, record
  pointer, spherical reference radius, map bounds and actual image file length.
- Converts PDS digital numbers to radial height above the label's reference
  sphere in metres using scale, unit and offset metadata. For SLDEM2015 IMG,
  `OFFSET` and the reference radius are both 1737.4 km; the net height is
  `DN × 1000 m`, not absolute lunar radius.
- Product ID, coordinate system, reference radius and pixel registration are
  carried in the shared limb-model metadata and therefore in contact provenance.
- Added `eclipsekit-validate-topography`, a local PDS3 inspection example,
  deterministic interpolation checks and JSON/Markdown report writers. No NASA
  DEM data are bundled or downloaded.
- The reader does not decode JP2/PDS4, reproject or transform between body-fixed
  frames, mosaic tiles, or infer a pointwise uncertainty from published
  product-wide accuracy. Windows verification and testing with a real local
  SLDEM2015 file remain pending.


### Phase 7.7 notes

- Added `eclipsekit.performance`: repeatable warm-up/batch micro-benchmarks for
  WGS84 inverse geodesics, Brent root solving, solar/lunar disc overlap,
  finite-difference Jacobians, and covariance propagation. Reports include
  median/mean/p95 latency, throughput, optional traced peak memory, environment
  metadata, and optional cProfile output.
- Added environment-aware benchmark comparison. A comparison is marked
  incomparable rather than failed when Python implementation/version, OS, or
  machine identity differs. Benchmarks do not impose absolute timing gates.
- Added `eclipsekit.regression`: deterministic numerical anchors for WGS84
  equatorial/antimeridian/polar cases, ECEF round-trip, root solving at ordinary
  and Julian-day scales, correlated covariance propagation, seeded Monte Carlo
  repeatability, and the published NASA 1999 Besselian reference case. A real
  PDS3 DEM can optionally be included in this report.
- Added CI smoke steps for the scientific regression CLI and micro-benchmark
  harness. No numerical defaults, solver algorithms, ephemeris choices, or
  runtime dependencies were changed. No speculative vectorization was applied
  without a representative baseline proving a bottleneck.
- The default regression report deliberately marks live DE440s global-path and
  shadow-corridor validation as NOT RUN; execute the existing `eclipsekit-validate`
  workflow with an explicit BSP/EOP configuration for that acceptance layer.


## Phase 8 — Advanced scientific validation

| # | Work package | Status | Scope |
|---:|---|---|---|
| 8.1 | Reproducible shadow-corridor validation | Implemented; Windows/live NASA run pending | Dedicated DE440s/EOP-aware CLI; independent comparison of selected 2017 NASA central-axis, central boundaries, width and first-order duration rows; nested time-sampling diagnostics; JSON/Markdown reports and GeoJSON/CSV/KML exports. Sampling convergence is diagnostic, not independent accuracy evidence. |
| 8.2 | Broader reference matrix | Planned | Extend independent cases and provenance across total, annular, hybrid and partial eclipses; preserve source clock conventions, coordinate frames, resolution and pre-registered tolerances. |
| 8.3 | Earth-orientation reproducibility | Planned | Audit EOP source/version, DUT1 and ΔT assumptions; add reproducible snapshots/metadata for fixed validation runs. |
| 8.4 | Unified validation gate | Planned | Consolidate status semantics, machine-readable schemas and CI-selectable scientific acceptance profiles without treating NOT_RUN as PASS. |

### Phase 8.1 notes

- The new `eclipsekit-validate-corridor` command wraps the existing corridor
  reference validator and evaluates nested time-sampling resolutions using the
  same selected kernel and Earth-orientation mode.
- The finest time grid is checked against the selected NASA/GSFC 2017 fixture;
  coarse grids are compared using aggregate path-length, width, duration and
  boundary-coverage diagnostics. The diagnostic does not establish accuracy.
- The command writes auditable JSON/Markdown and GIS exports. The user-supplied
  `data/validation/global_corridor_2017_nasa.csv` remains outside the overlay.
- Assistant-side Phase 8.1 checks: new CLI/convergence tests **5 passed** and
  `compileall` passed. The complete existing corridor reference tests could not
  be run in this checkout because the user-supplied `data/validation` fixtures
  were intentionally not included. The user's Windows/live run is still pending.


## Phase 9 — Lunar DEM interoperability and validation

| # | Work package | Status | Scope |
|---:|---|---|---|
| 9.1 | Tiled DEM access | Implemented and Windows-verified | Bounded LRU tile cache, read windows, streaming tiles and cache diagnostics for PDS3 lunar DEMs. User verified 25/25 real SLDEM2015 sample checks PASS. |
| 9.2 | Multi-format DEM readers | Implemented and Windows-verified | PDS4, GeoTIFF and JP2 readers with explicit lunar provenance and bounded windowed access; user subsequently reported the full suite passed after installing Pillow. |
| 9.3 | Lunar frame and spherical datum point transforms | Implemented and Windows-verified | Fixed DE440 PA / DE421 ME rotation, inverse, spherical reference-radius conversion and five-point published-coordinate audit; user run: 674 passed and 5/5 audit points PASS. |
| 9.4 | Independent DEM control-point validation | Overlay implemented; real independent benchmark pending | Versioned provenance manifest, explicit frame/datum checks, point sampling, vertical residual metrics, uncertainty diagnostics, independence gate and auditable reports. No real control dataset is bundled; user must provide documented independent observations. |
| 9.5 | Frame-aware DEM query adapter | Implemented and Windows-verified | Lazy virtual DEM view that inverse-transforms target queries, samples the source reader in its native frame, converts height to a target spherical radius and reports target metadata with source/transform provenance. User run: 717 tests passed, 14 focused tests passed, Ruff and compileall clean. No raster warp or real accuracy claim. |
| 9.6 | Coverage-aware DEM mosaic routing | Implemented and Windows-verified | Virtual query routing across compatible DEM products with explicit common frame/datum/radius, antimeridian-aware coverage, priority/finest/mean strategies, provenance and explicit error handling. No raster merge, seam blending or scientific accuracy claim. |
| 9.7 | DEM mosaic overlap-consistency audit | Overlay implemented; Windows verification pending | Pairwise deterministic source-to-source altitude checks inside declared overlap, residual metrics, antimeridian branch handling, JSON/Markdown and PDS3 manifest CLI. Diagnostic only: no seam correction or absolute-accuracy claim. |

Phase 9.4 uses LOLA RDR spot observations as one possible source of point
controls, but it does not assume these are independent of any given DEM. A
point set derived from shots used to build the DEM is not independent unless a
withheld subset is documented. See `docs/PHASE9_4_LUNAR_DEM_CONTROL_POINTS.md`.

Phase 9.5 adds query-time adaptation rather than raster reprojection. The
source coordinate-system label must be mapped to the transform source frame by
the caller using authoritative product documentation. See
`docs/PHASE9_5_FRAME_AWARE_DEM_ACCESS.md`.


Phase 9.6 introduces `LunarDEMMosaicModel`, a query-time router over multiple
compatible DEM readers. It selects products using declared rectangular
coverage and explicit priority, finest-resolution, or unweighted-mean policy.
All sources must share a coordinate-system label, spherical reference radius,
and vertical datum. Coverage for rotated virtual views must be supplied by the
caller as an explicit override. The mosaic does not blend seams, merge raster
files, or prove co-registration; a real multi-product acceptance run still
requires documented overlapping/adjacent products and independent control
observations. See `docs/PHASE9_6_LUNAR_DEM_MOSAIC.md`.


Phase 9.7 adds a diagnostic comparison of the underlying DEM readers inside
their declared pairwise overlap, rather than comparing the virtual mosaic output
with one reader. It reports the signed `source_b - source_a` difference and
per-pair residual metrics on a deterministic grid. It reports non-overlapping
pairs as `NO_OVERLAP`; if no pairs overlap, the overall status is
`NOT_COMPARABLE`. No seam correction or blending is attempted. See
`docs/PHASE9_7_LUNAR_DEM_MOSAIC_OVERLAP_AUDIT.md`.


## Phase 11 — Advanced Eclipse Prediction Engine

| # | Work package | Status | Scope |
|---:|---|---|---|
| 11.1 | Bounded interval and multi-observer search | Implemented; Windows verified (754 passed) | New-moon candidate discovery, refined geocentric maximum, independent local circumstances per explicit observer, interval filtering, magnitude threshold and JSON-friendly grouped results. No unlisted-location coverage or independent scientific certification. |

## Phase 12 — Advanced Geometry and Observation

| # | Work package | Status | Scope |
|---:|---|---|---|
| 12.1 | Instantaneous shadow footprint | Implemented | Central and penumbral cone intersections at one instant, WGS84 edge sampling, coverage fractions, track orientation and GeoJSON linework. |
| 12.2 | Detailed topocentric observation geometry | Implemented | Sun/Moon alt-azimuth, angular radii, separation, position/parallactic/vertex angles, magnitude, obscuration and horizon clearances. |
| 12.3 | Horizon-aware contact visibility | Implemented | Optional azimuth-dependent skyline profile; visibility at C1/C2/maximum/C3/C4; old no-profile statuses preserved. |



## Phase 13 — Performance and Scalability

| # | Work package | Status | Scope |
|---:|---|---|---|
| 13.1 | Reusable city/country indexing | Implemented | Precomputed immutable country index arrays, defensive-copy lookup API, batched read-only index views, and cache diagnostics. |
| 13.2 | Streaming city search | Implemented | `iter_search_cities()` emits hits after each bounded NumPy batch; existing `search_cities()` retains magnitude-sorted list behaviour. |
| 13.3 | Performance and concurrency evidence | Implemented | Extended deterministic benchmark suite for country scans/cache, streaming index batches and serial/threaded batch workloads. Threads were not enabled in production because the representative test was slower in the measured environment. |

No numerical model defaults or ephemeris/contact algorithms were changed.
The streaming API bounds retained result memory but still computes exact
Skyfield contacts on the calling thread. Batch size is the explicit memory /
throughput control. Parallel execution remains deferred until a representative
end-to-end workload on the target platform demonstrates a repeatable benefit.

## Phase 14 — Public API and Ecosystem

| # | Work package | Status | Scope |
|---:|---|---|---|
| 14.1 | Curated public API contract | Implemented; Windows verified | `eclipsekit.api` facade, explicit API contract version/status, root-import compatibility tests and documented deprecation/change policy. |
| 14.2 | Runtime and JSON interoperability | Implemented; Windows verified | Dependency/runtime inventory, strict JSON conversion, NumPy/date/path/result handling and atomic output. |
| 14.3 | Third-party extension ecosystem | Implemented; Windows verified | Explicit entry-point metadata discovery and opt-in factory loading for lunar-limb models and DEM readers; duplicate/error handling and security guidance. |
| 14.4 | Packaging and integration documentation | Implemented; wheel smoke test pending | PEP 561 marker, wheel inclusion metadata, migration/API/extension docs and standalone external-application example. |

The API contract version is separate from the distribution version and report
schema versions. The API v1 contract is marked `stable`; the distribution remains
pre-1.0.0 until the evidence-gated release process in Phase 15 is complete.

## Phase 15 — Scientific Certification and 1.0

| # | Work package | Status | Scope |
|---:|---|---|---|
| 15.1 | Certification evidence runner | Implemented | `eclipsekit-certify` combines software, API, reference, dynamic-validation, DEM, independent-control and external-review evidence. Missing evidence is `NOT_RUN`; it is never a pass. |
| 15.2 | Reproducible provenance and packaging | Implemented | SHA-256 source-tree fingerprint excluding local data; lint, compile, pytest, dependency consistency, wheel and PEP 561 inspection. |
| 15.3 | Reference coverage | Implemented with scoped limitations | Published total, annular, partial and hybrid classes; the hybrid comparison covers NASA's geocentric greatest-eclipse epoch only. Full local/path validation is limited to the configured cases. |
| 15.4 | External scientific evidence | Pending external inputs | Requires real independent lunar control points and an independent scientific review tied to the exact source fingerprint. |
| 15.5 | Stable 1.0.0 release | Blocked pending evidence | The package remains `0.1.0` until every mandatory gate passes and the final 1.0.0 wheel is built and re-audited. |

Phase 15's report is scoped to declared references and tolerances. A passing
software suite does not establish universal eclipse prediction or DEM
accuracy. Use `docs/PHASE15_SCIENTIFIC_CERTIFICATION_1_0.md` for the release
procedure and outstanding evidence list.
