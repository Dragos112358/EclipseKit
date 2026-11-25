# EclipseKit

**A modular Python toolkit for calculating, analysing, mapping and validating solar and lunar eclipses.**

<p align="left">
  <a href="https://pypi.org/project/eclipsekit/"><img src="https://img.shields.io/pypi/v/eclipsekit?label=PyPI" alt="PyPI version"></a>
  <a href="https://pypi.org/project/eclipsekit/"><img src="https://img.shields.io/pypi/pyversions/eclipsekit" alt="Python versions"></a>
  <a href="https://github.com/Dragos112358/EclipseKit/actions/workflows/ci.yml"><img src="https://github.com/Dragos112358/EclipseKit/actions/workflows/ci.yml/badge.svg" alt="GitHub Actions CI"></a>
  <a href="LICENSE.md"><img src="https://img.shields.io/badge/License-Apache--2.0-blue.svg" alt="Apache 2.0 License"></a>
</p>

EclipseKit is a Python library for numerical eclipse astronomy. It brings together local solar-eclipse circumstances, geocentric and topocentric lunar-eclipse calculations, direct JPL-ephemeris shadow geometry, Besselian-element calculations, lunar topography interfaces, observation planning, geospatial exports and reproducible scientific-reference validation.

It is intended for use in Python applications, research workflows, notebooks, command-line validation and GIS-oriented processing. The package separates numerical astronomy from application-specific runtime code and exposes structured Python objects rather than requiring users to parse formatted text reports.

**Current release:** `0.1.0a1` (Alpha)  
**Python:** 3.10 or newer  
**License:** Apache-2.0  
**Distribution:** [Available on PyPI](https://pypi.org/project/eclipsekit/)

<p align="center">
  <a href="https://pypi.org/project/eclipsekit/">PyPI project</a> ·
  <a href="https://pypi.org/project/eclipsekit/0.1.0a1/#files">Download wheel / source archive</a> ·
  <a href="https://github.com/Dragos112358/EclipseKit">GitHub repository</a> ·
  <a href="https://github.com/Dragos112358/EclipseKit/issues">Issues and bug reports</a>
</p>

---

# Table of contents

- [Install EclipseKit](#install-eclipsekit)
- [Download the distribution files](#download-the-distribution-files)
- [Quick start](#quick-start)
- [Observed PyPI smoke-test result](#observed-pypi-smoke-test-result)
- [Project goals and design](#project-goals-and-design)
- [Capabilities at a glance](#capabilities-at-a-glance)
- [Configuration API](#configuration-api-recommended-for-new-code)
- [Ephemerides, caches and time scales](#ephemerides-caches-and-time-scales)
- [Solar-eclipse calculations](#solar-eclipse-calculations)
  - [Local circumstances and contacts](#local-circumstances-and-contacts)
  - [Global shadow path](#global-shadow-path)
  - [Global shadow corridor](#global-shadow-corridor)
  - [City and country searches](#city-and-country-searches)
  - [Observation planner](#observation-planner)
- [Lunar-eclipse calculations](#lunar-eclipse-calculations)
  - [Geocentric contacts and classification](#geocentric-contacts-and-classification)
  - [Local lunar-eclipse visibility](#local-lunar-eclipse-visibility)
- [Independent Besselian backend](#independent-besselian-backend)
- [Lunar-limb correction framework](#lunar-limb-correction-framework)
- [Lunar DEM and topography integration](#lunar-dem-and-topography-integration)
  - [PDS3 and tiled DEM access](#pds3-and-tiled-dem-access)
  - [PDS4, GeoTIFF and JPEG 2000](#pds4-geotiff-and-jpeg-2000)
  - [Coordinate-frame and datum transformations](#coordinate-frame-and-datum-transformations)
  - [Frame-aware DEM access and mosaics](#frame-aware-dem-access-and-mosaics)
  - [Mosaic overlap audit](#mosaic-overlap-audit)
  - [Independent DEM control points](#independent-dem-control-points)
- [Uncertainty propagation](#uncertainty-propagation)
- [Public API, typing and extensions](#public-api-typing-and-extensions)
- [Validation results for version 0.1.0a1](#validation-results-for-version-010a1)
- [Run the bundled reference-validation suite](#run-the-bundled-reference-validation-suite)
- [Other validation and audit commands](#other-validation-and-audit-commands)
- [Performance and regression tools](#performance-and-regression-tools)
- [Exports and GIS integration](#exports-and-gis-integration)
- [Development setup](#development-setup)
- [Tests and continuous integration](#tests-and-continuous-integration)
- [Data, kernels and model assets](#data-kernels-and-model-assets)
- [Scientific scope and limitations](#scientific-scope-and-limitations)
- [Project roadmap and 1.0 release gate](#project-roadmap-and-10-release-gate)
- [What was separated from the original application](#what-was-separated-from-the-original-application)
- [Documentation index](#documentation-index)
- [Contributing, security and citation](#contributing-security-and-citation)

---

# Install EclipseKit

EclipseKit is published on the **Python Package Index (PyPI)**. The recommended installation is:

```bash
python -m pip install --pre eclipsekit
```

The `--pre` option allows pip to select the current Alpha pre-release. To install the exact version documented here:

```bash
python -m pip install eclipsekit==0.1.0a1
```

EclipseKit requires **Python 3.10+**. The core package installs its required numerical dependencies automatically:

- NumPy
- Skyfield

Check the installed distribution:

```bash
python -m pip show eclipsekit
python -m pip check
```

The second command should report that no installed dependency requirements are broken.

## Optional dependencies

The base installation does not install every optional scientific or raster dependency. Install extras only when the corresponding feature is needed:

```bash
# Rasterio/GDAL-backed GeoTIFF and JPEG 2000 DEM adapters
python -m pip install --pre "eclipsekit[raster]"

# Neural lunar-limb integration; installs PyTorch, but not model weights
python -m pip install --pre "eclipsekit[limb]"
```

For development, linting and tests, see [Development setup](#development-setup).

## Command-line entry points

The core package includes a reference-validation command:

```bash
eclipsekit-validate --help
```

Other project tools are installed as console scripts when their corresponding modules are part of the distribution. Examples include:

```text
eclipsekit-validate
eclipsekit-validate-path
eclipsekit-validate-limb
eclipsekit-validate-topography
eclipsekit-validate-dem-format
eclipsekit-audit-lunar-frames
eclipsekit-validate-dem-control
eclipsekit-audit-dem-mosaic
eclipsekit-validate-corridor
eclipsekit-audit-references
eclipsekit-eop-audit
eclipsekit-validate-all
eclipsekit-benchmark
eclipsekit-regression
eclipsekit-certify
```

Use `--help` on an installed command to inspect its exact options.

---

# Download the distribution files

The official PyPI release page contains the published files:

**[Open EclipseKit 0.1.0a1 on PyPI — download files](https://pypi.org/project/eclipsekit/0.1.0a1/#files)**

The release contains the standard Python distribution formats:

| File | Purpose | Recommended use |
|---|---|---|
| `eclipsekit-0.1.0a1-py3-none-any.whl` | Built Python wheel | Recommended for normal installation |
| `eclipsekit-0.1.0a1.tar.gz` | Source distribution | Source inspection or rebuilding |

Install a downloaded wheel:

```bash
python -m pip install ./eclipsekit-0.1.0a1-py3-none-any.whl
```

Or install from the source archive:

```bash
python -m pip install ./eclipsekit-0.1.0a1.tar.gz
```

The wheel is platform-independent (`py3-none-any`). It contains the `eclipsekit` package and its typing marker, not large third-party astronomical or terrain datasets.

---

# Quick start

The following example calculates local circumstances for the **12 August 2026 total solar eclipse** near León, Spain.

```python
from eclipsekit import EclipseEngine, Observer

# A named JPL kernel is downloaded on first use if it is not already cached.
engine = EclipseEngine.from_jpl("de440s")

# Latitude and longitude are in degrees; elevation is in metres.
observer = Observer(
    latitude=42.6,
    longitude=-5.5703,
    name="León",
)

result = engine.calculate_local(observer, "2026-08-12")

if result is None:
    print("No local eclipse was found in the search horizon.")
else:
    # Human-readable report
    print(engine.format_report(result))

    # Structured access
    print("C1:", result.contacts.c1)
    print("C2:", result.contacts.c2)
    print("Obscuration:", result.obscuration_percent)

    # JSON-friendly result representation
    payload = result.to_dict()
    print(payload)
```

A typical result includes:

- eclipse classification;
- local maximum time;
- magnitude and obscuration;
- solar altitude and azimuth;
- external and internal contacts C1–C4, where applicable;
- central and partial phase durations;
- shadow velocity and width fields when available;
- structured contact and time-scale metadata.

A date-only timestamp such as `"2026-08-12"` is interpreted according to the documented engine time convention. For reproducible comparisons, explicitly record the ephemeris, Earth-orientation/time-scale mode, observer coordinates, adopted radii and solver settings.

---

# Observed PyPI smoke-test result

The published `0.1.0a1` package was installed into a clean Python 3.12 virtual environment from the official PyPI index. The imports, console entry point and dependency check were exercised. A direct `EclipseEngine` calculation was also run from the installed package.

For the León observer used in the Quick start example, the direct API smoke test returned:

```text
PASS: Calculul eclipsei a reușit.
Type: total
Maximum: 2026-08-12T18:29:13.651Z
Magnitude: 1.01296
Obscuration: 100.00%
Sun altitude: 9.69°
Sun azimuth: 281.32°
Central-phase duration: 103.3 s
Total event span C1-C4: 6563.6 s
C1: 2026-08-12T17:32:45.001Z
C2: 2026-08-12T18:28:21.896Z
C3: 2026-08-12T18:30:05.193Z
C4: 2026-08-12T19:22:08.560Z
Shadow velocity: 2.552 km/s
Shadow width: 300.4 km
```

This is a recorded smoke-test output for the stated environment, coordinates, kernel and settings. It is an example of a successful package-level calculation, not a claim that the same printed values apply to every ephemeris or Earth-orientation configuration.

---

# Project goals and design

EclipseKit is an extraction and refactoring of the numerical astronomy layer from the supplied Eclipse Simulator 3D Python source. It separates numerical astronomy from Unreal/UDP runtime code, uses explicit ephemeris selection, returns structured Python objects and keeps large external datasets out of the installed package.

The principal design goals are:

1. **A small distributable wheel.** JPL DE kernels, city catalogues, DEM rasters and neural checkpoints are not bundled.
2. **Explicit ephemeris selection.** Use a supported JPL kernel name, a local BSP/SPK path or a direct supported URL.
3. **A reusable Python API.** Calculations return structured result objects and JSON-friendly mappings.
4. **Separate solar and lunar workflows.** Solar local circumstances, global shadow geometry and lunar-eclipse contacts/visibility have distinct interfaces.
5. **Independent calculation paths.** The direct ephemeris engine and supplied Besselian-element solver remain separate so their results can be compared.
6. **Explicit spatial and time conventions.** Observer coordinates, UTC/UT1/TT, ΔT, Earth-orientation sources, reference radii and DEM frames are not silently conflated.
7. **Reproducibility.** Validation reports record inputs, source references, tolerances and numerical configuration.
8. **Import safety.** Importing `eclipsekit` does not download ephemerides, open sockets, start background threads or load a neural model.

# Capabilities at a glance

| Area | Capabilities |
|---|---|
| Solar local circumstances | C1–C4, local maximum, magnitude, disc-overlap obscuration, solar altitude/azimuth |
| Solar event searches | Search local events and date intervals; evaluate explicitly supplied observers |
| Global shadow geometry | WGS84 shadow-axis intersections, central paths and corridor geometry |
| GIS | GeoJSON, CSV and KML export helpers |
| City/country analysis | Caller-supplied city catalogues, vectorized and streaming searches |
| Lunar eclipses | Penumbral/partial/total classification and P1/U1/U2/maximum/U3/U4/P4 contacts |
| Lunar local visibility | Moonrise/moonset clipping, refraction option, horizon profiles and phase visibility |
| Besselian calculations | Explicitly supplied published elements, local contacts, greatest eclipse and central-line points |
| Lunar limb | Spherical, gridded DEM and tabulated apparent-limb models; optional neural adapter |
| Lunar DEM | PDS3/PDS4, optional GeoTIFF/JP2 readers, tiled access and mosaics |
| Coordinate transformations | Explicit frame and spherical reference-radius transformations |
| Observation planning | Compare candidate observing sites using transparent heuristic scores |
| Uncertainty | First-order and seeded Monte Carlo propagation from caller-supplied uncertainty budgets |
| Validation | Reference regression, path comparison, Besselian regression, EOP audit and certification reporting |
| Ecosystem | Curated `eclipsekit.api`, runtime diagnostics, strict JSON helpers and explicit extensions |

The sections below describe the principal interfaces and the current documented scope. The `docs/` directory contains the more detailed mathematical, schema and validation references.

---

# Configuration API (recommended for new code)

EclipseKit retains legacy constructor keywords for compatibility. New applications should group numerical assumptions into immutable configuration objects. This makes ephemeris, Earth-orientation source, contact radii, solver tolerances and atmospheric refraction assumptions explicit and serializable.

```python
from eclipsekit import (
    EclipseEngine,
    EclipseConfig,
    EphemerisConfig,
    EarthOrientationConfig,
    ContactModelConfig,
    SolverConfig,
    AtmosphereConfig,
    Observer,
)

config = EclipseConfig(
    ephemeris=EphemerisConfig.jpl(
        "de440s",
        earth_orientation=EarthOrientationConfig.iers(),
    ),
    contacts=ContactModelConfig(),
    solver=SolverConfig(
        root_tolerance_seconds=1e-5,
        root_max_iterations=100,
        minimum_tolerance_seconds=0.05,
    ),
    atmosphere=AtmosphereConfig(
        refraction_enabled=True,
        pressure_mbar=1013.25,
        temperature_c=15.0,
    ),
)

engine = EclipseEngine(config=config)
result = engine.calculate_local(
    Observer(42.6, -5.5703),
    "2026-08-12",
)

print(config.to_dict())
```

Configuration helpers include:

- `EphemerisConfig.jpl("de440s")` for a named JPL kernel;
- `EphemerisConfig.local(path)` for a local BSP file;
- `EarthOrientationConfig.builtin()` for Skyfield's bundled tables;
- `EarthOrientationConfig.iers()` for the IERS table workflow;
- `EarthOrientationConfig.fixed(delta_t)` for a deliberately fixed historical ΔT assumption;
- `ContactModelConfig()` for the current spherical-disc contact model;
- `ContactModelConfig.iau_mean_moon()` for an explicitly selected adopted mean lunar radius;
- `SolverConfig(...)` for root solver tolerances and iteration settings;
- `AtmosphereConfig(...)` for refraction and station atmosphere assumptions.

`ContactModelConfig.iau_mean_moon()` selects one adopted mean lunar radius for spherical-disc contacts; it is not a topographic lunar-limb model. `AtmosphereConfig(refraction_enabled=False)` disables refraction in the reported solar altitude/azimuth while retaining station pressure as metadata.

`SolverConfig` supports bisection (the backwards-compatible default) and a safeguarded Brent–Dekker root solver. The detailed contact API also supports automatic bracket expansion, tangent-contact candidates and convergence diagnostics. Internal C1–C4 searches remain bounded to their physical ingress/egress intervals; only the explicit public detailed solver expands beyond a supplied interval when requested by configuration.

The older constructor remains available:

```python
engine = EclipseEngine("de440s", sun_radius_km=696000.0)
```

Do not combine `config=` with legacy constructor overrides.

See [`docs/PUBLIC_API.md`](docs/PUBLIC_API.md), [`docs/API_MIGRATION.md`](docs/API_MIGRATION.md) and [`docs/CONTACT_SOLVER_V2.md`](docs/CONTACT_SOLVER_V2.md).

---

# Ephemerides, caches and time scales

EclipseKit uses Skyfield with JPL BSP/SPK ephemerides. The core accepts a supported kernel name, a local `.bsp` file or a direct supported HTTP(S) URL.

```python
from eclipsekit import EclipseEngine

engine = EclipseEngine("de440s")
# Other examples:
engine = EclipseEngine("de432s")
engine = EclipseEngine("de440")
engine = EclipseEngine("de441")

# Local kernel:
engine = EclipseEngine(r"D:/Astronomy/kernels/de440s.bsp")
```

When a common JPL kernel name is selected, the kernel is obtained on first use if it is not already cached. A local path can be used when kernel download and storage must be managed by the application.

The wheel does **not** contain a planetary kernel. DE441 can be several gigabytes and is not downloaded unless explicitly selected. Custom kernels must expose the Earth, Sun and Moon segments under the requested names; non-standard segment names can be supplied through the supported body-name configuration.

The default time scale uses Skyfield's bundled tables. The supplied source's Espenak–Meeus-style ΔT polynomial is retained for dates outside 1900–2100; ancient and far-future conversions are estimates and carry substantial physical uncertainty.

For modern calculations, the engine exposes explicit Earth-orientation modes:

```python
from eclipsekit import EclipseEngine, EarthOrientationConfig

# Offline-friendly Skyfield bundled tables (default)
engine_builtin = EclipseEngine("de440s")

# IERS finals2000A.all; first use may require Internet access
engine_iers = EclipseEngine(
    "de440s",
    earth_orientation=EarthOrientationConfig.iers(),
)

# Historical model reproduction only; not an operational UTC/EOP setting
engine_fixed = EclipseEngine(
    "de440s",
    earth_orientation=EarthOrientationConfig.fixed(71.4),
)

print(engine_iers.time_scale_diagnostics("2026-08-12T18:30:00Z"))
```

The modes have different purposes:

- `builtin` is the offline-friendly default and uses Skyfield's bundled time-scale data.
- `iers` loads IERS `finals2000A.all` through Skyfield (`Loader.timescale(builtin=False)`) and may require a network connection on first use.
- `fixed` is deliberately explicit and intended to reproduce a named published prediction that specifies a fixed ΔT.

A fixed ΔT can imply a synthetic DUT1 outside UTC's normal ±0.9 second range. It must not silently replace observed Earth-orientation data. For a table whose clock is UT1, use `engine.time_from_ut1(...)`; for civil UTC strings or datetimes, use `engine.time(...)`. `time_scale_diagnostics()` reports the selected mode, ΔT, DUT1 and whether the derived DUT1 is compatible with the UTC convention.

For reproducibility, record the kernel name/version, cache and time-scale mode, EOP/ΔT source, UTC/UT1/TT convention and all relevant model settings with the results.

---

# Solar-eclipse calculations

## Local circumstances and contacts

The local solar-eclipse engine calculates circumstances for an explicitly supplied `Observer`.

```python
from eclipsekit import EclipseEngine, Observer

engine = EclipseEngine("de440s")

observer = Observer(
    latitude=42.0,
    longitude=-5.0,
    elevation_m=0.0,
    name="Example observing site",
)

result = engine.calculate_local(observer, "2026-08-12")

if result is None:
    print("No local eclipse found in the search horizon")
else:
    print(engine.format_report(result))
    print(result.contacts.c1)
    print(result.contacts.c2)
    print(result.obscuration_percent)
    print(result.to_dict())
```

A date-only string is interpreted as 12:00 UTC, so the default ±12-hour search window covers the requested civil date. To prevent automatic search for the next event, set `find_next_if_none=False`. Increase `search_window_hours` when searching a longer interval around a known event.

The local circumstances include the available contacts:

- **C1** — first external contact;
- **C2** — second contact, where an annular or total phase begins;
- **maximum** — local greatest eclipse;
- **C3** — third contact, where the central phase ends;
- **C4** — final external contact.

For partial eclipses, C2 and C3 are absent. Contact availability depends on the eclipse type and local geometry.

### Magnitude and obscuration are different

`magnitude` and `obscuration_percent` are not interchangeable. EclipseKit calculates obscuration from the analytic overlap area of two apparent circles; it does not use the shortcut `magnitude * 100`.

`duration_seconds` retains the historical C2–C3 central-phase convention (zero for a non-central eclipse). The explicit `central_phase_duration_seconds` field is `None` when there is no central phase; `partial_phase_duration_seconds` represents C1–C4 when both external contacts are found.

### Structured contact events

The result also exposes `result.contact_events`, a chronological mapping containing structured C1/C2/maximum/C3/C4 records when those events exist. Each `ContactEvent` retains UTC, TT-JD and UT1-JD separately, topocentric geometry, position/vertex angles, solar horizon status and the root-solver diagnostics for contact roots.

Its uncertainty remains `None` until a validated physical uncertainty model is available.

See [`docs/CONTACT_EVENT_MODEL.md`](docs/CONTACT_EVENT_MODEL.md) and [`examples/contact_event_model.py`](examples/contact_event_model.py).

## Global shadow path

The direct ephemeris-based shadow-axis calculation intersects the shadow-axis ray with the WGS84 reference ellipsoid. A point is returned only when the axis intersects the ellipsoid; the engine does not invent a ground track for a central cone that misses Earth.

```python
from eclipsekit import EclipseEngine

engine = EclipseEngine("de440s")

path = engine.global_path_for_eclipse(
    "2026-08-12",
    search_radius_hours=4,
    samples=101,
)

for point in path:
    print(
        point.latitude,
        point.longitude,
        point.width_km,
        point.shadow_kind,
    )
```

For a caller-defined interval, use `global_shadow_path(start, end, samples=...)`.

The path calculation is a geometric central-axis result on the WGS84 ellipsoid. It is not by itself a full terrain-clipped footprint, a path-boundary model or an independent certification of shadow width, velocity or depth.

## Global shadow corridor

The Phase 7.3 corridor API calculates central and penumbral boundaries around the central axis and supports GIS exports.

```python
from eclipsekit import (
    EclipseEngine,
    shadow_corridor_to_geojson,
    write_geojson,
    write_shadow_corridor_csv,
    write_shadow_corridor_kml,
)

engine = EclipseEngine.from_jpl("de440s")

corridor = engine.global_shadow_corridor(
    "2017-08-21T17:00:00Z",
    "2017-08-21T19:00:00Z",
    samples=121,
    boundary_samples=144,
)

write_geojson(
    shadow_corridor_to_geojson(corridor),
    "reports/corridor.geojson",
)
write_shadow_corridor_csv(corridor, "reports/corridor.csv")
write_shadow_corridor_kml(corridor, "reports/corridor.kml")
```

`central_left` and `central_right` are the umbral or antumbral limits relative to track direction; `penumbra_left` and `penumbra_right` are the outer partial-eclipse limits for the same time slice. The two sides are not permanently synonymous with north and south.

Widths are cross-track geodesic spans on the WGS84 reference ellipsoid. Duration fields are first-order estimates (along-track cone chord divided by instantaneous track speed), not root-solved local C1–C4 circumstances. The local track bearing is computed from a short symmetric time difference, independent of the requested sample spacing.

The current method samples only times when the central axis intersects Earth. It does not calculate the full penumbral sunrise/sunset footprint. Terrain height, atmospheric refraction and lunar-limb topography are not included.

The bundled sparse NASA/GSFC 2017 path-table fixture can be compared with `validate_shadow_corridor_reference()`. It is a small regression sample with declared tolerances, not a complete certification of corridor boundaries.

See [`docs/SHADOW_CORRIDOR_V2.md`](docs/SHADOW_CORRIDOR_V2.md), [`docs/PHASE8_1_CORRIDOR_VALIDATION.md`](docs/PHASE8_1_CORRIDOR_VALIDATION.md) and [`examples/shadow_corridor_2017.py`](examples/shadow_corridor_2017.py).

## City and country searches

EclipseKit supports country/city analysis from a caller-supplied CSV catalogue. The catalogue is not bundled with the PyPI wheel because source, version and redistribution rights must be documented.

Add your own file at `data/CountryPoints.csv` or pass a custom path to `CityCatalog.from_csv()`. The expected columns are:

```text
Country,City,Latitude,Longitude,Elevation_m
```

Example:

```python
from pathlib import Path
from eclipsekit import CityCatalog, EclipseEngine

catalog = CityCatalog.from_csv(Path("data") / "CountryPoints.csv")
engine = EclipseEngine("de440s")

# Cities in Romania that see the eclipse around this date
hits = engine.search_cities(
    "2026-08-12",
    catalog,
    country="Romania",
    min_magnitude=0.001,
)

for hit in hits:
    print(
        hit.city.name,
        hit.magnitude,
        hit.obscuration_percent,
        hit.maximum,
    )

# Solar-eclipse events in an interval affecting catalogue points in Spain
events = engine.find_solar_eclipses_by_country(
    "2020-01-01",
    "2030-01-01",
    catalog,
    country="Spain",
    include_contacts=False,
)

for event in events:
    print(event.to_dict())
```

The country search operates on the points in the supplied CSV, not on every square kilometre of a country. Results are therefore limited by catalogue density and coordinate quality.

The vectorized search uses bounded batches to avoid allocating one enormous city×time×coordinate array in memory. Setting `include_contacts=True` runs the local solver for each hit and is slower.

For contact times corrected by a caller-supplied neural lunar-limb model, pass both `include_contacts=True` and `limb_corrector=limb` to `find_solar_eclipses_by_country()` or `search_cities()`. The result then contains geometric contacts and a separate `limb_corrected_contacts` mapping.

### Streaming search

The Phase 13 API includes `EclipseEngine.iter_search_cities()`, which yields each hit as its bounded NumPy batch is processed and preserves catalogue order. `search_cities()` continues to return a complete list sorted by magnitude.

```python
from eclipsekit import CityCatalog, EclipseEngine

catalog = CityCatalog.from_csv("CountryPoints.csv")
engine = EclipseEngine("de440s")

# Streaming: process hits as they arrive
for hit in engine.iter_search_cities(
    "2026-08-12T17:00:00Z",
    catalog,
    country="Romania",
    batch_size=256,
):
    print(hit.city.name, hit.magnitude)

# List API: complete magnitude-sorted collection
hits = engine.search_cities(
    "2026-08-12T17:00:00Z",
    catalog,
    country="Romania",
)
print(catalog.index_cache_info())
```

`batch_size` bounds the city-by-time NumPy working set. Lower values reduce peak temporary memory at the cost of more batches. `iter_search_cities()` emits hits in input catalogue order and is intended for streaming, not global ranking. Use `search_cities()` when a complete magnitude-sorted collection is required.

### Lunar eclipse city visibility

`lunar_eclipse_city_visibility()` evaluates catalogue visibility. Its default `visibility_window="greatest"` retains a fast maximum-only filter; `visibility_window="any"` screens the complete P1–P4 interval and can include locations where the Moon is below the horizon at greatest eclipse.

For precise local moonrise/moonset, refraction, skyline masks and intervals for penumbral/partial/total phases, use `EclipseEngine.lunar_eclipse_local_visibility(observer, when)`.

## Observation planner

The Phase 7.4 observation planner compares candidate observing locations for a selected solar-eclipse epoch. It calculates local circumstances at each supplied `Observer`, retains no-eclipse and calculation-error sites explicitly, and ranks candidate sites with a transparent weather-agnostic score.

```python
from eclipsekit import EclipseEngine, Observer, write_observation_plan_csv

engine = EclipseEngine.from_jpl("de440s")

sites = [
    Observer(42.6000, -5.5703, 837, name="León", country="Spain"),
    Observer(42.3439, -3.6969, 859, name="Burgos", country="Spain"),
]

plan = engine.plan_observations(sites, "2026-08-12T17:45:59Z")
print(plan.to_markdown())

write_observation_plan_csv(plan, "reports/observation-plan.csv")
```

The complete plan is also available through `plan.to_dict()` and can be written with `write_observation_plan_json()`.

The supplied weights emphasize obscuration (50%), Sun altitude (30%) and C1–C4 event span (20%). They are configurable heuristic priorities, not a probability of clear skies or observing success. Cloud cover, detailed terrain horizon, light pollution, access, travel and equipment are not modelled.

See [`docs/OBSERVATION_PLANNER.md`](docs/OBSERVATION_PLANNER.md) and [`examples/observation_planner.py`](examples/observation_planner.py).

---

# Lunar-eclipse calculations

## Geocentric contacts and classification

EclipseKit includes a geocentric lunar-eclipse solver. It searches full-Moon phases, evaluates the Moon against the angle-dependent Herald–Sinnott oblate-Earth shadow model and classifies penumbral, partial and total lunar eclipses.

The default Herald–Sinnott prescription uses an 87 km notional eclipse-forming atmospheric layer and angle-dependent umbra/penumbra boundaries that account for Earth's flattening. Contact times are refined against the full non-circular boundaries. The older circular-cone approximation remains available with `shadow_model="circular"` for reproducing legacy Alpha results.

The solver handles the following contacts where applicable:

- **P1** — first penumbral contact;
- **U1** — first umbral contact;
- **U2** — beginning of totality;
- **maximum** — greatest eclipse;
- **U3** — end of totality;
- **U4** — final umbral contact;
- **P4** — final penumbral contact.

Example:

```python
from eclipsekit import EclipseEngine

engine = EclipseEngine("de440s")

event = engine.find_next_lunar_eclipse("2025-01-01")

if event is not None:
    print(event.eclipse_type)
    print(event.to_dict())

# Search a date interval and choose the civil calendar explicitly.
events = engine.find_lunar_eclipses(
    "1500-01-01",
    "1501-01-01",
    calendar="julian",
)
```

### Calendar semantics

The default `calendar="historical"` uses the Julian calendar through 1582-10-04 and the Gregorian calendar from 1582-10-15. The skipped dates 1582-10-05 through 1582-10-14 are rejected.

`calendar="julian"` and `calendar="gregorian"` select proleptic calendars. Time-zone-qualified timestamps are absolute instants and are not reinterpreted as civil-calendar fields. Internal event calculations remain on TT Julian dates.

`find_lunar_eclipses(start, end)` uses a half-open interval (`start` included, `end` excluded). Date-only boundaries begin at civil midnight, so:

```python
events = engine.find_lunar_eclipses(
    "2025-03-14",
    "2025-03-15",
)
```

searches all of 14 March. This interval convention is separate from `EclipseEngine.time("YYYY-MM-DD")`, which continues to return 12:00 for date-only single-event calculations.

### Model and time-scale interpretation

Results remain numerical astronomy model outputs and should be interpreted with the matching ephemeris, Earth-orientation, ΔT and radius assumptions recorded.

The 87 km atmospheric layer is an empirical global prescription, not a resolved atmospheric-opacity model. The result serializer reports UTC, UT1 and TT separately.

Geocentric eclipse contacts remain unchanged by local circumstances. `lunar_eclipse_local_visibility()` intersects the physical P1–P4, U1–U4 and U2–U3 phase intervals with the selected observer's above-horizon intervals. Moonrise and moonset are therefore local visibility boundaries, not replacements for global eclipse contacts.

See [`docs/LUNAR_ECLIPSES.md`](docs/LUNAR_ECLIPSES.md), [`docs/LUNAR_ECLIPSE_METHODOLOGY.md`](docs/LUNAR_ECLIPSE_METHODOLOGY.md) and [`docs/LUNAR_REFERENCE_VALIDATION_2022_2028.md`](docs/LUNAR_REFERENCE_VALIDATION_2022_2028.md).

## Local lunar-eclipse visibility

A local visibility query handles cases where the Moon rises after P1 or sets before P4. It includes observer elevation, optional atmospheric refraction, a caller-supplied `HorizonProfile`, altitude samples and separate visible intervals for the penumbral, partial and total phases.

```python
from eclipsekit import EclipseEngine, Observer, HorizonProfile

engine = EclipseEngine("de440s")

site = Observer(
    44.4268,
    26.1025,
    elevation_m=80.0,
    name="Bucharest",
)

local = engine.lunar_eclipse_local_visibility(
    site,
    "2027-07-18",
    apply_refraction=True,
    sample_interval_seconds=60,
    horizon_profile=HorizonProfile.flat(
        2.0,
        name="local skyline",
    ),
)

if local is not None:
    print(local["visibility_status"])
    print(local["observable_intervals"])
    print(local["phase_visibility"])
```

The local query can return:

- whether any part of the eclipse is observable;
- observer-specific visible intervals;
- separate penumbral, partial and total phase visibility;
- Moon altitude samples and rise/set clipping information;
- the effect of observer elevation, the selected refraction setting and the supplied horizon profile.

Use `lunar_eclipse_city_visibility(..., visibility_window="any")` for a sampled catalogue screen of cities that see at least part of the eclipse. Use the single-observer method for refined local crossing times.

Moonrise and moonset do not redefine the geocentric P1–P4 contacts. They clip the observer's local visibility interval.

---

# Independent Besselian backend

The Besselian backend is a separate calculation path based on explicitly supplied published polynomial elements. It does not derive its coefficients from the active JPL kernel.

Phase 4 adds `BesselianElements` and `BesselianSolver`. The backend retains source ephemeris, ΔT convention, coefficient epoch and validity interval, and returns TT Julian Dates so time-scale conversion remains explicit.

A reference element set for the 11 August 1999 total solar eclipse is included under `data/validation/`.

Run the pure Besselian example (no JPL kernel is needed):

```powershell
python .\examples\besselian_backend.py
```

To exercise the backend through `EclipseEngine` with the configured Skyfield time-scale source and JPL kernel:

```powershell
python .\examples\besselian_engine_integration.py
```

The full equations, coefficient format, API, scope and known limits are documented in [`docs/BESSELIAN_BACKEND.md`](docs/BESSELIAN_BACKEND.md).

This is a separate calculation path. It does not replace the direct topocentric engine and does not imply that every eclipse prediction is independently validated.

---

# Lunar-limb correction framework

The optional contact correction accepts a provider-neutral `limb_model`. New integrations should prefer this interface over depending directly on one specific model implementation.

Supported conceptual approaches include:

- a spherical baseline;
- caller-supplied gridded lunar DEM data;
- a tabulated apparent-limb profile;
- an optional neural checkpoint adapter.

Example using a caller-supplied gridded DEM:

```python
from eclipsekit import (
    EclipseEngine,
    GriddedLunarLimbModel,
    Observer,
)

dem = GriddedLunarLimbModel.from_csv(
    "lunar_dem.csv",
    name="Regional lunar DEM",
    source="record the product identifier and processing version",
    vertical_datum="record the DEM reference surface",
)

engine = EclipseEngine.from_jpl("de440s")

result = engine.calculate_local(
    Observer(42.6, -5.5703),
    "2026-08-12T18:00:00Z",
    limb_model=dem,
)
```

A tabulated apparent-limb profile can instead be loaded with `TabulatedAngularLunarLimbProfile.from_csv()`.

## Optional neural lunar-limb adapter

The neural model architecture is exposed through `eclipsekit/limb.py`. The optional `[limb]` extra installs PyTorch, but the model checkpoint is not included in the PyPI wheel and is not downloaded automatically.

The legacy integration pattern is:

```python
from eclipsekit import EclipseEngine, LunarLimbCorrector, Observer

engine = EclipseEngine("de440s")

limb = LunarLimbCorrector.from_checkpoint(
    r"models/lunar_altitude_contact_bands_fp16_finetuned.pt"
)

result = engine.calculate_local(
    Observer(41.65, -0.8877, 0),
    "2026-08-12",
    limb_corrector=limb,
)

for contact, correction in result.limb_corrected_contacts.items():
    print(
        contact,
        correction.time,
        correction.delta_seconds,
        correction.predicted_terrain_altitude_m,
    )
```

PyTorch is imported only when loading or using the model. The loader uses `weights_only=True`. If a checkpoint contains custom pickled objects, re-save it as a plain state dictionary plus primitive metadata rather than enabling unsafe arbitrary unpickling by default.

The supplied checkpoint metadata reported `best_val_rmse_m` of about 12.58 m. This is the model's stored validation metric, not a demonstrated 12.58 m global error bound and not a contact-time accuracy guarantee. The model's training-data provenance, geographic/selenographic coverage, independent test set and licence must be documented. Treat neural correction as experimental until checked against an independent lunar-limb profile and observed or published contact timings.

See [`docs/LUNAR_LIMB_FRAMEWORK.md`](docs/LUNAR_LIMB_FRAMEWORK.md) for formats, interpolation rules, compatibility and scientific limitations.

---

# Lunar DEM and topography integration

EclipseKit provides a provider-neutral lunar-limb interface and optional DEM readers. A DEM must be interpreted with its source coordinate frame, longitude convention, reference radius and vertical datum explicitly documented.

The package does not bundle NASA LOLA/SLDEM tiles, Watts profiles, neural weights or other large topography products.

## PDS3 and tiled DEM access

Phase 7.6 adds a reader for documented, uncompressed PDS3 lunar DEM `IMG` files without loading a multi-gigabyte global image into memory. The initial target is the NASA LOLA/SELENE SLDEM2015 simple-cylindrical product.

The reader checks projection, east-positive longitude, body-fixed frame, spherical reference radius, pixel geometry, sample type, binary record layout and file size. Its metadata is retained in each limb-corrected contact.

```python
from eclipsekit import EclipseEngine, Observer, PDS3LunarDEMModel

engine = EclipseEngine.from_jpl("de440s")

with PDS3LunarDEMModel.from_pds3_img(
    "data/SLDEM2015_128_60S_60N_000_360_FLOAT.IMG",
    "data/SLDEM2015_128_60S_60N_000_360_FLOAT.LBL",
    expected_coordinate_system="MEAN EARTH/POLAR AXIS OF DE421",
) as dem:
    result = engine.calculate_local(
        Observer(42.6, -5.5703, elevation_m=800.0),
        "2026-08-12T18:00:00Z",
        limb_model=dem,
    )
```

The PDS `OFFSET`/reference-radius convention is converted to height above the labelled sphere, so the reference radius is not added twice. The reader uses a read-only memory map and bilinear interpolation. It does not download data, reproject coordinates, transform between DE421/DE440 body-fixed frames, decode JP2 or fill missing DEM cells.

The current contact-to-selenographic mapping remains the Phase 5 Meeus-style approximation. Confirm frame compatibility before treating a sampled height as a physical limb correction.

Validate a local source product with:

```powershell
eclipsekit-validate-topography `
  --image "data\SLDEM2015_128_60S_60N_000_360_FLOAT.IMG" `
  --label "data\SLDEM2015_128_60S_60N_000_360_FLOAT.LBL" `
  --expected-coordinate-system "MEAN EARTH/POLAR AXIS OF DE421"
```

The validator writes JSON and Markdown to `reports/phase7_6/`. A successful result is a label/storage/interpolation smoke check, not independent validation of lunar topographic accuracy. SLDEM2015's published typical vertical accuracy is not silently treated as a pointwise uncertainty.

See [`docs/LUNAR_TOPOGRAPHY_PDS3.md`](docs/LUNAR_TOPOGRAPHY_PDS3.md). No NASA topography data are redistributed in the package.

### Phase 9.1 — tiled lunar DEM access

PDS3 lunar DEMs remain read-only memory-mapped and support a bounded LRU cache of converted elevation tiles, rectangular window reads and streaming tile iteration. This lets applications process multi-gigabyte IMG products without eagerly loading the full raster into a Python array.

```python
from eclipsekit import open_pds3_lunar_dem

with open_pds3_lunar_dem(
    "data/SLDEM2015_128_60S_60N_000_360_FLOAT.IMG",
    "data/SLDEM2015_128_60S_60N_000_360_FLOAT.LBL",
    expected_coordinate_system="MEAN EARTH/POLAR AXIS OF DE421",
    tile_shape=512,
    cache_tiles=8,
) as dem:
    height_m = dem.predict_altitude_m(-10.0, 25.0)
    window = dem.read_window(100, 200, 500, 700)

    print(height_m, window.shape, dem.cache_info().to_dict())

    for tile in dem.iter_tiles((256, 256)):
        consume = tile.height_above_reference_m
        # Process one window at a time.
```

The default cache is bounded to at most 16 MiB of float64 tile payload. Use `cache_tiles=0` to disable it, `clear_tile_cache()` to release it, and `cache_info()` to inspect hits, misses, evictions and memory use. `LunarDEMWindow` arrays are independent read-only copies; missing cells remain NaN.

See [`docs/PHASE9_1_TILED_DEM_ACCESS.md`](docs/PHASE9_1_TILED_DEM_ACCESS.md).

## PDS4, GeoTIFF and JPEG 2000

Phase 9.2 adds explicit format adapters:

- **PDS4 `Array_2D_Image`** labels with detached or attached binary arrays. The supported subset is regular 2-D simple-cylindrical/equirectangular lunar grids with declared east-positive longitude, pixel registration, spherical reference radius and explicit sample interpretation (`height` or `radius`).
- **GeoTIFF and JPEG 2000** through the optional Rasterio/GDAL backend.

Install the raster extra:

```bash
python -m pip install --pre "eclipsekit[raster]"
```

The raster must be a north-up geographic grid, or a non-georeferenced JP2 must be supplied with explicit degree bounds.

GeoTIFF/JP2 inputs must declare or be supplied with:

- `coordinate_system_name`;
- `reference_radius_m`;
- `vertical_datum`;
- `value_interpretation` (`height` or `radius`);
- sample `value_unit`.

A generic Earth CRS or unlabelled raster is not silently treated as a Moon-fixed DEM. The Phase 9.2 readers themselves do not apply datum conversion, reprojection or DE421/DE440 frame transformation; the separate point-transform API is documented below.

PDS4 example:

```python
from eclipsekit import open_pds4_lunar_dem

with open_pds4_lunar_dem(
    "data/lunar_dem.xml",
    expected_coordinate_system="MEAN EARTH/POLAR AXIS OF DE421",
    tile_shape=512,
    cache_tiles=8,
) as dem:
    height_m = dem.predict_altitude_m(-10.0, 25.0)
    window = dem.read_window(100, 200, 500, 700)
    print(height_m, window.shape, dem.cache_info().to_dict())
```

GeoTIFF example:

```python
from eclipsekit import open_geotiff_lunar_dem

with open_geotiff_lunar_dem(
    "data/lunar_dem.tif",
    coordinate_system_name="MEAN EARTH/POLAR AXIS OF DE421",
    reference_radius_m=1_737_400.0,
    vertical_datum="radial height relative to the DE421 sphere",
    value_interpretation="height",
    value_unit="m",
) as dem:
    print(dem.predict_altitude_m(-10.0, 25.0))
```

Validate a product and write a JSON/Markdown report:

```powershell
eclipsekit-validate-dem-format --format pds4 --input "data\lunar_dem.xml" `
  --expected-coordinate-system "MEAN EARTH/POLAR AXIS OF DE421" `
  --sample-grid 5 --tile-size 512 --cache-tiles 8 `
  --output-dir "reports\phase9_2"
```

For GeoTIFF/JP2, pass the lunar provenance and value-interpretation options. A JP2 without geographic metadata also needs `--bounds WEST SOUTH EAST NORTH` and `--coordinates-in-degrees`.

A `PASS` confirms metadata and selected interpolation samples only; it is not an independent vertical-accuracy certification.

## Coordinate-frame and datum transformations

Phase 9.3 adds a provenance-carrying point-coordinate transformation layer without silently changing any DEM reader or raster.

The built-in fixed rotation implements the published DE440 principal-axes (`MOON_PA_DE440`) to DE421 mean-Earth/mean-rotation (`MOON_ME_DE421`) relation from Park et al. (2021), Equation (19), using the passive right-handed rotation convention printed in that paper. Its inverse maps DE421 ME coordinates to DE440 PA.

```python
from eclipsekit import (
    LunarCoordinateTransform,
    LunarReferenceSphereTransform,
    de421_me_to_de440_pa_transform,
)

transform = LunarCoordinateTransform(
    frame_transform=de421_me_to_de440_pa_transform(),
    vertical_transform=LunarReferenceSphereTransform(
        source_reference_radius_m=1_737_400.0,
        target_reference_radius_m=1_737_400.0,
        source_vertical_datum="height above the DE421 ME 1,737,400 m sphere",
        target_vertical_datum="height above the DE440 PA 1,737,400 m sphere",
    ),
)

point = transform.transform_point(
    latitude_deg=14.25,
    longitude_deg=-72.5,
    height_m=-1200.0,
)

print(
    point.latitude_deg,
    point.longitude_deg,
    point.height_above_reference_m,
)
```

The vertical conversion preserves centre-of-Moon radius:

```text
h_target = h_source + R_source - R_target
```

The coordinate transform accepts scalar values or broadcast-compatible NumPy arrays. Longitude output is normalized to `[-180, 180)` degrees.

`eclipsekit-audit-lunar-frames` reconstructs the five paired lunar-retroreflector XYZ coordinates printed in Table 1 of Park et al. (2021) and writes JSON/Markdown reports:

```powershell
eclipsekit-audit-lunar-frames --output-dir "reports\phase9_3"
```

The audit is an implementation-consistency check against the reflector points paired with the published fitted rotation; it is not an independent geodetic validation. These APIs transform points only. They do not warp, resample or rewrite PDS3/PDS4/GeoTIFF/JP2 grids, model a lunar geoid or ellipsoidal vertical datum, or replace time-dependent lunar orientation from appropriate SPICE PCK/FK kernels.

See [`docs/PHASE9_3_LUNAR_FRAME_DATUM_TRANSFORMS.md`](docs/PHASE9_3_LUNAR_FRAME_DATUM_TRANSFORMS.md).

## Frame-aware DEM access and mosaics

### Phase 9.4 — independent DEM control-point validation

EclipseKit can compare a PDS3/PDS4/GeoTIFF/JP2 lunar DEM with a separately curated control-point JSON file.

The file must declare:

- source;
- coordinate frame;
- planetocentric/east-positive coordinate convention;
- spherical reference radius;
- value interpretation;
- vertical datum;
- whether observations are independent of the DEM under test.

A non-independent dataset is never reported as an acceptance `PASS`.

See [`docs/PHASE9_4_LUNAR_DEM_CONTROL_POINTS.md`](docs/PHASE9_4_LUNAR_DEM_CONTROL_POINTS.md) and the synthetic-only schema example at [`examples/lunar_control_points_template.json`](examples/lunar_control_points_template.json).

### Phase 9.5 — frame-aware DEM query access

`TransformedLunarDEMModel` wraps any supported lunar DEM reader and presents a virtual view in an explicitly selected target frame and spherical vertical datum.

Each target query is inverse-rotated into the source DEM frame, sampled using the source reader's existing tile/window machinery, and converted to the target reference radius. The source raster remains read-only and is never reprojected, resampled, copied or rewritten.

The constructor requires the source product's exact coordinate-system label, source radius and vertical datum to agree with the explicitly supplied `LunarCoordinateTransform`. The caller must verify from authoritative product documentation that the label maps to the transform's declared source frame; EclipseKit does not infer frames from a kernel name.

The resulting virtual `product_info` reports target metadata and preserves source product and transform provenance. It can be passed to the Phase 9.4 control-point validator when the control observations already use the target frame/datum.

See [`docs/PHASE9_5_FRAME_AWARE_DEM_ACCESS.md`](docs/PHASE9_5_FRAME_AWARE_DEM_ACCESS.md) and [`examples/lunar_dem_frame_adapter.py`](examples/lunar_dem_frame_adapter.py).

### Phase 9.6 — coverage-aware lunar DEM mosaic routing

`LunarDEMMosaicModel` composes multiple compatible lunar DEM readers as a virtual query router. Every source must declare the same coordinate-system label, vertical datum and spherical reference radius. The mosaic routes a point only to products whose declared rectangular coverage contains it.

```python
from eclipsekit import LunarDEMMosaicModel

mosaic = LunarDEMMosaicModel(
    [western_dem, eastern_dem],
    strategy="priority",  # or "finest" / "mean"
)

height_m = mosaic.predict_altitude_m(12.0, -45.0)
```

Strategies:

- `priority` uses the first covering source in supplied order;
- `finest` selects the smallest declared positive ground resolution;
- `mean` returns the unweighted arithmetic mean of all covering products.

`mean` is not an uncertainty-weighted fusion. A source error or NoData condition inside its advertised coverage is reported rather than silently hidden by falling back to another reader. A source with no axis-aligned coverage metadata (including a rotated virtual view) requires an explicit `LunarDEMCoverage` override supplied from independently established geometry.

This phase does not merge or rewrite raster files, reproject grids, blend seams, prove horizontal co-registration or certify DEM accuracy. Its tests use synthetic providers to validate routing, coverage, compatibility checks, error handling and reader lifecycle.

See [`docs/PHASE9_6_LUNAR_DEM_MOSAIC.md`](docs/PHASE9_6_LUNAR_DEM_MOSAIC.md) and [`examples/lunar_dem_mosaic.py`](examples/lunar_dem_mosaic.py).

### Phase 9.7 — lunar DEM mosaic overlap audit

`eclipsekit-audit-dem-mosaic` and `audit_lunar_dem_mosaic_overlaps()` compare source elevations directly inside each pair's declared positive-area coverage overlap.

The audit samples a deterministic grid, reports `source_b - source_a` residuals and bias/MAE/RMSE/median/P95/maximum metrics, and retains per-point errors. Antimeridian and 0/360 longitude-branch overlaps are aligned without splitting ordinary continuous overlap regions into artificial grid fragments.

The audit compares every original source pair directly; it does not compare the selected Phase 9.6 mosaic result against one source. It never edits, blends, shifts, resamples or reprojects source rasters.

`NO_OVERLAP` pairs are not sampled. An overall `NOT_COMPARABLE` result is returned when no pair has an overlap. A `PASS` means only that sampled source-to-source differences are within the chosen absolute tolerance, not that either product is absolutely accurate or horizontally co-registered.

The standalone CLI currently opens PDS3 IMG/LBL sources using a version-1 JSON manifest; the Python API accepts any readers supported by `LunarDEMMosaicModel`.

See [`docs/PHASE9_7_LUNAR_DEM_MOSAIC_OVERLAP_AUDIT.md`](docs/PHASE9_7_LUNAR_DEM_MOSAIC_OVERLAP_AUDIT.md) and [`examples/lunar_dem_mosaic_overlap_manifest.template.json`](examples/lunar_dem_mosaic_overlap_manifest.template.json).

---

# Uncertainty propagation

Phase 7.5 can propagate explicitly supplied parameter uncertainties through a caller-provided forward model. It supports correlated covariance budgets, first-order finite-difference propagation, seeded Monte Carlo sampling and implicit contact-time sensitivity.

It does not infer physical uncertainty from root-solver residuals.

```python
from eclipsekit import UncertaintyBudget, propagate_uncertainty

budget = UncertaintyBudget.from_standard_deviations(
    ("observer_clock_bias", "ephemeris_bias"),
    (0.20, 0.05),
    units=("s", "km"),
    source_descriptions=("Documented input specifications",),
)

result = propagate_uncertainty(
    model_function,
    mean_parameters,
    budget,
    output_names=("contact_time",),
    output_units=("s",),
    method="linear",  # or "monte_carlo"
)

print(result.to_dict())
```

The supplied budget must be scientifically defensible and use consistent units. Only listed input sources are included.

Run the synthetic API demonstration:

```powershell
python .\examples\uncertainty_propagation.py
```

The example's values are not a prediction or uncertainty estimate for a real eclipse.

See [`docs/UNCERTAINTY_PROPAGATION.md`](docs/UNCERTAINTY_PROPAGATION.md).

---

# Public API, typing and extensions

New integrations should import supported interfaces from `eclipsekit.api`. The curated API exposes engine/configuration models, observation and search results, lunar-limb/DEM interfaces, validation helpers, benchmark records, runtime diagnostics, strict JSON interchange and explicit third-party extension loading.

Existing `from eclipsekit import ...` imports remain supported.

```python
from eclipsekit.api import (
    EclipseEngine,
    EclipseConfig,
    EphemerisConfig,
    Observer,
    API_CONTRACT_VERSION,
    get_runtime_info,
)

config = EclipseConfig(
    ephemeris=EphemerisConfig.jpl("de440s"),
)

engine = EclipseEngine(config=config)
result = engine.calculate_local(
    Observer(44.4268, 26.1025),
    "2026-08-12T17:00:00Z",
)

print(API_CONTRACT_VERSION)
print(get_runtime_info().to_dict())
```

`API_CONTRACT_VERSION` identifies the curated Python interface contract. The distribution version and individual report `schema_version` values remain separate.

`get_runtime_info()` reports runtime and optional dependency versions without importing Torch or Rasterio.

`write_json()` atomically writes strict interoperable JSON and rejects unsupported or non-finite values. `discover_extensions()` reads plugin metadata only; `load_extension()` imports a selected trusted factory only when explicitly requested.

The package includes `eclipsekit/py.typed` (PEP 561 marker). This advertises inline typing information; it does not promise that every legacy internal module is fully annotated or that every static type checker produces zero diagnostics.

See [`docs/PUBLIC_API.md`](docs/PUBLIC_API.md), [`docs/EXTENSIONS.md`](docs/EXTENSIONS.md) and [`docs/API_MIGRATION.md`](docs/API_MIGRATION.md).

---

# Validation results for version 0.1.0a1

The published PyPI wheel was installed into a clean Python 3.12 virtual environment from the official PyPI index. The following package-level checks were completed:

- installation from the official PyPI index;
- package version and installation path;
- imports of `EclipseEngine`, `Observer` and `HorizonProfile`;
- `eclipsekit-validate --help`;
- execution from outside the source project folder;
- `pip check`;
- direct local solar-eclipse calculation.

The complete bundled reference-validation command was then run from the repository root with JPL DE440s.

## Full suite: 11/11 acceptance cases passed

Observed run configuration:

| Item | Value |
|---|---|
| Distribution | `eclipsekit 0.1.0a1` |
| Python | 3.12.10 |
| Operating system | Windows 11 |
| Kernel | JPL DE440s |
| Skyfield | 1.55 |
| Time scale | Skyfield bundled tables (`builtin`) |
| Global path sampling | 301 samples |
| Acceptance cases | 11 |
| Passed | 11 |
| Failed | 0 |
| Execution errors | 0 |

### Local circumstances and geocentric maximum

All six cases passed:

| Reference case | Result |
|---|---:|
| León, Spain — total solar eclipse | PASS |
| Dallas, Texas — total solar eclipse | PASS |
| Albuquerque, New Mexico — annular solar eclipse | PASS |
| London, United Kingdom — partial solar eclipse | PASS |
| 12 August 2026 — geocentric greatest eclipse | PASS |
| 20 April 2023 — hybrid eclipse, geocentric greatest eclipse | PASS |

### NASA central-line path comparisons

Each configured path subset compared seven reference samples:

| Event | Compared samples | Mean error | RMS error | Maximum error | Limit | Result |
|---|---:|---:|---:|---:|---:|---:|
| 21 August 2017 — NASA central line | 7/7 | 0.3616 km | 0.3675 km | 0.4795 km | 5 km | PASS |
| 2 July 2019 — NASA central line | 7/7 | 0.5723 km | 0.8684 km | 2.1685 km | 5 km | PASS |
| 21 June 2020 — NASA central line | 7/7 | 0.3099 km | 0.5663 km | 1.4362 km | 5 km | PASS |
| 12 August 2026 — NASA central line | 7/7 | 3.3686 km | 3.4174 km | 4.6340 km | 15 km | PASS |

### NASA 1999 Besselian regression

All configured checks passed:

| Check | Reported difference / result |
|---|---:|
| Greatest-eclipse epoch | −0.0418 s |
| Central-line position | 0.0303 km |
| Local eclipse type | total |
| Central duration | −0.0487 s |
| Local contacts | PASS |

The direct-engine-versus-Besselian comparison is separately labelled diagnostic and has no pass/fail tolerance. The observed diagnostic reported maximum difference in greatest time of −0.0089 s, and local contact differences of approximately one second. Differences between distinct ephemeris, Earth-orientation and geometric realizations must not be interpreted as a determination of which calculation is physically closer.

## Reproduce the full validation run

Run this command from the repository root, where the curated fixtures under `data/validation/` are present:

```powershell
eclipsekit-validate `
  --kernel de440s `
  --cache-dir "$env:LOCALAPPDATA\EclipseKit\kernels" `
  --path-samples 301 `
  --json-out reports/pypi-full-validation.json `
  --markdown-out reports/pypi-full-validation.md
```

The command writes:

```text
reports/
├── pypi-full-validation.json
└── pypi-full-validation.md
```

The `eclipsekit-validate` executable is installed with the package, but the reference fixtures are repository/source-tree assets and are not bundled into the wheel. For validation, use a repository checkout or source archive that contains `data/validation/`.

**Interpretation:** `PASS` applies only to the named fixtures, their source precision, configured tolerances, selected ephemeris and time-scale assumptions. Sparse path points do not validate every path boundary or all shadow-width outputs. These results are not a universal accuracy guarantee, external peer review or scientific certification. Neural lunar-limb corrections and every supported DEM product require their own independent evidence.

See [`docs/SCIENTIFIC_VALIDATION.md`](docs/SCIENTIFIC_VALIDATION.md), [`docs/VALIDATION_FRAMEWORK.md`](docs/VALIDATION_FRAMEWORK.md), [`docs/PHASE8_4_UNIFIED_VALIDATION.md`](docs/PHASE8_4_UNIFIED_VALIDATION.md) and [`docs/PHASE15_ALPHA_RELEASE.md`](docs/PHASE15_ALPHA_RELEASE.md).

---

# Run the bundled reference-validation suite

The Phase 6 validation runner combines independently sourced local circumstances, geocentric maximum times, sparse global-path tables and a published Besselian-element regression. It records provenance and model/time-scale assumptions in every report.

The default inputs are:

```text
data/validation/reference_cases.json
data/validation/path_reference_manifest.json
data/validation/global_path_2017-08-21.csv
data/validation/global_path_2019-07-02.csv
data/validation/global_path_2020-06-21.csv
data/validation/global_path_2026-08-12.csv
data/validation/besselian_1999_reference.json
data/validation/besselian_1999_aug11_nasa.json
```

The command below runs local circumstances, geocentric maxima, path comparisons and the Besselian regression:

```powershell
eclipsekit-validate `
  --references data/validation/reference_cases.json `
  --path-manifest data/validation/path_reference_manifest.json `
  --besselian-reference data/validation/besselian_1999_reference.json `
  --kernel de440s `
  --cache-dir "$env:LOCALAPPDATA\EclipseKit\kernels" `
  --path-samples 301 `
  --json-out reports/phase6-validation.json `
  --markdown-out reports/phase6-validation.md
```

Useful options:

| Option | Purpose |
|---|---|
| `--references` | JSON manifest for local and geocentric reference cases |
| `--path-manifest` | Manifest for NASA central-line path subsets |
| `--besselian-reference` | NASA 1999 Besselian regression descriptor |
| `--kernel` | JPL BSP kernel name or local path |
| `--cache-dir` | Explicit ephemeris/EOP cache directory |
| `--time-scale-mode` | `builtin`, `iers` or `fixed_delta_t` |
| `--delta-t-seconds` | Fixed ΔT; required with `fixed_delta_t` |
| `--path-samples` | Number of computed path samples |
| `--skip-paths` | Skip global path validation |
| `--skip-besselian` | Skip Besselian regression |
| `--json-out` | JSON report destination |
| `--markdown-out` | Markdown report destination |

A quick core-only run can omit paths and Besselian checks:

```powershell
eclipsekit-validate `
  --kernel de440s `
  --cache-dir "$env:LOCALAPPDATA\EclipseKit\kernels" `
  --skip-paths `
  --skip-besselian `
  --json-out reports/core-validation.json `
  --markdown-out reports/core-validation.md
```

The full suite contains six local/geocentric cases, four path subsets and one Besselian regression. It is distinct from a unit-test run.

---

# Other validation and audit commands

## Solar/lunar scientific reference validation

The project includes a separate lunar reference runner for a 16-event external regression matrix (2022–2028). It compares eclipse type, contacts, magnitude and gamma values to the selected reference assumptions.

See [`docs/LUNAR_REFERENCE_VALIDATION_2022_2028.md`](docs/LUNAR_REFERENCE_VALIDATION_2022_2028.md) and run:

```powershell
python scripts/validate_lunar_references.py --kernel de430
```

One grazing penumbral reference is especially sensitive to rounded lunar-radius conventions. Its documented treatment uses the reference-specific radius only when reproducing that source's rounded semidiameter; the engine's general default radius should not be altered to fit a single rounded reference.

## Global corridor validation (Phase 8.1)

The corridor validator runs a 2017 NASA comparison at multiple nested time-sampling resolutions and records convergence diagnostics. The finest run is compared against supplied reference rows; coarser runs are compared with it using aggregate path-length, width, duration and boundary-coverage metrics. Convergence results are diagnostics, not independent accuracy evidence.

```powershell
eclipsekit-validate-corridor `
  --kernel de440s `
  --start "2017-08-21T17:00:00Z" `
  --end "2017-08-21T17:40:00Z" `
  --reference "data/validation/global_corridor_2017_nasa.csv" `
  --convergence-samples "3,11,21,51,101" `
  --boundary-samples 144 `
  --output-dir "reports/phase8_1"
```

See [`docs/PHASE8_1_CORRIDOR_VALIDATION.md`](docs/PHASE8_1_CORRIDOR_VALIDATION.md).

## Reference-data audit

Audit configured reference data (manifests, local/global cases, Besselian assets and corridor rows) and record SHA-256 fingerprints:

```powershell
eclipsekit-audit-references `
  --validation-dir "data\validation" `
  --output-dir "reports\phase8_2"
```

## Earth-orientation audit

Audit the selected Earth-orientation source and time-scale assumptions:

```powershell
eclipsekit-eop-audit `
  --mode builtin `
  --at "2017-08-21T17:20:00Z"
```

For a file-hashed external IERS table use `--mode iers`; the active IERS table must be present in the selected Skyfield cache. If Skyfield uses its complete legacy external table trio, all three files are fingerprinted separately and combined into a deterministic composite fingerprint.

Built-in tables are scoped to the recorded Skyfield version. Fixed ΔT is recorded as an explicit historical assumption and is not equivalent to observed DUT1.

## Unified validation (Phase 8.4)

Run the configured validation components together:

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

The unified status is conservative: every component must report `PASS` for the overall report to be `PASS`. An unverified external EOP source or an explicit fixed-ΔT assumption produces `PARTIAL`, not a false clean pass. Reports fingerprint inputs and document scope; they do not claim universal scientific certification.

See:

- [`docs/PHASE8_2_REFERENCE_MATRIX.md`](docs/PHASE8_2_REFERENCE_MATRIX.md)
- [`docs/PHASE8_3_EOP_REPRODUCIBILITY.md`](docs/PHASE8_3_EOP_REPRODUCIBILITY.md)
- [`docs/PHASE8_4_UNIFIED_VALIDATION.md`](docs/PHASE8_4_UNIFIED_VALIDATION.md)

## Lunar-limb profile validation

An independent lunar-limb profile benchmark is available as `eclipsekit-validate-limb`. It requires user-supplied measured/reference heights that are independent of the model's training and input data.

Without an explicit acceptance threshold, its status is `UNASSESSED`: computing error metrics alone does not certify a model. Full instructions, supported options, CSV schemas, uncertainty interpretation, tolerances and known gaps are in [`docs/VALIDATION_FRAMEWORK.md`](docs/VALIDATION_FRAMEWORK.md).

## DEM validation

The PDS3 structural/sample validator is `eclipsekit-validate-topography`. Format-specific validation is available through `eclipsekit-validate-dem-format`.

Remember: a PASS from metadata, format or sample-interpolation checks does not independently certify absolute lunar topographic accuracy.

---

# Performance and regression tools

Phase 7.7 adds deterministic scientific regression and representative micro-benchmarks.

Install development dependencies and run:

```powershell
python -m pip install -e ".[dev]"
eclipsekit-regression --output-dir reports/phase7_7
eclipsekit-benchmark --warmups 2 --repeats 7 --iterations 100 --output-dir reports/phase7_7
```

Optionally include a downloaded PDS3 DEM in the regression report:

```powershell
eclipsekit-regression `
  --dem-image "data\SLDEM2015_128_60S_60N_000_360_FLOAT.IMG" `
  --dem-label "data\SLDEM2015_128_60S_60N_000_360_FLOAT.LBL" `
  --expected-coordinate-system "MEAN EARTH/POLAR AXIS OF DE421" `
  --output-dir reports/phase7_7
```

Save the first benchmark JSON as a machine-specific baseline. On the same computer and Python runtime, compare a later run with `--baseline-json` and an explicit slowdown allowance, for example `--max-slowdown-ratio 1.25`. Do not compare results from dissimilar hardware or operating systems.

The Phase 13 benchmark suite compares cached country lookup with a full scan and runs a deterministic serial-versus-four-thread NumPy batch workload. The recorded development-container measurement is machine/workload-specific; rerun benchmarks on the target machine before changing concurrency policy.

See [`docs/PERFORMANCE_AND_REGRESSION.md`](docs/PERFORMANCE_AND_REGRESSION.md) and [`docs/PHASE13_PERFORMANCE_SCALABILITY.md`](docs/PHASE13_PERFORMANCE_SCALABILITY.md).

---

# Exports and GIS integration (Geographic Information System)

City visibility hits, global shadow paths and Phase 7.3 shadow corridors can be exported to standard GeoJSON. City hits and corridors can also be exported to CSV, and corridors to KML.

GeoJSON coordinates follow RFC 7946 order (longitude, latitude). Shadow paths crossing the antimeridian are split into separate line segments.

Example:

```powershell
python .\examples\export_results.py
```

Open the resulting `results/*.geojson` files in QGIS or another GeoJSON-capable GIS viewer. The example requires your local `data/CountryPoints.csv`.

Common export helpers include:

- `city_hits_to_geojson(...)`;
- `shadow_path_to_geojson(...)`;
- `shadow_corridor_to_geojson(...)`;
- `shadow_corridor_to_kml(...)`;
- `write_shadow_corridor_csv(...)`;
- `write_shadow_corridor_kml(...)`;
- `write_city_hits_csv(...)`;
- `write_geojson(...)`.

---

# Development setup

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/Dragos112358/EclipseKit.git
cd EclipseKit
python -m venv .venv
```

Activate it:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Install the package in editable mode with development dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

For optional lunar-limb development:

```bash
python -m pip install -e ".[limb,dev]"
```

For raster-reader development:

```bash
python -m pip install -e ".[raster,dev]"
```

For security auditing:

```bash
python -m pip install -e ".[security]"
```

---

# Tests and continuous integration

Run the unit suite:

```powershell
python -m pytest -v --basetemp=".pytest_tmp\pytest-run"
```

Run Ruff:

```powershell
python -m ruff check src tests examples scripts
```

Compile the source, tests, examples and scripts:

```powershell
python -m compileall -q src tests examples scripts
```

Build distributions and inspect metadata:

```bash
python -m build
python -m pip install twine
python -m twine check --strict dist/*
```

The unit suite covers numerical helpers, geometry, catalogue parsing, time utilities, validation-fixture schemas, DEM handling and GeoJSON/CSV exporters. The scientific reference runner is separate from unit tests: passing unit tests demonstrates software behaviour for tested inputs, while reference comparisons measure agreement with the named external sources.

The GitHub Actions CI workflow is configured for:

- Python 3.10, 3.11 and 3.12;
- Ubuntu, Windows and macOS;
- Ruff lint;
- compile checks;
- the pytest suite;
- wheel building;
- PEP 561 `py.typed` marker verification;
- dependency vulnerability auditing.

CI results are available from the [GitHub Actions page](https://github.com/Dragos112358/EclipseKit/actions).

---

# Data, kernels and model assets

EclipseKit deliberately keeps large and externally licensed data out of the PyPI wheel.

| Asset | Package status | User responsibility |
|---|---|---|
| JPL BSP/SPK kernels | Not bundled | Obtain an appropriate kernel and record its version |
| `CountryPoints.csv` city catalogue | Not bundled | Provide source, version, licence and coordinate metadata |
| Lunar DEM rasters | Not bundled | Provide product provenance, frame, radius and vertical datum |
| Neural lunar-limb checkpoint | Not bundled | Obtain checkpoint with usage rights and document provenance |
| Reference fixtures | Small curated subset included in source distribution | Preserve their source references and stated precision |
| Validation reports | Not bundled | Generate and archive for each reproducible run |

The public repository and PyPI distributions use an explicit allow-list. The large local DEM collection, city catalogue, JPL kernels, neural checkpoint, reports, results, virtual environments and caches are not published. The source distribution includes only the curated validation fixtures listed by the build configuration. The wheel contains only the `eclipsekit` package and its typing marker.

Do not redistribute third-party datasets or model weights unless their terms permit it.

See [`docs/DATA_PROVENANCE.md`](docs/DATA_PROVENANCE.md), [`LICENSE.md`](LICENSE.md), [`NOTICE`](NOTICE) and [`SECURITY.md`](SECURITY.md).

---

# Scientific scope and limitations

EclipseKit `0.1.0a1` is an **Alpha software release**. It is suitable for development, reproducible experimentation and evaluation against the documented reference fixtures. Do not interpret a passing test suite as proof that every feature, location, epoch or physical model is independently validated.

Important scope boundaries include:

1. **Reference coverage is finite.** A PASS applies to the fixtures, source precision, tolerances, kernel and time-scale assumptions used in that run.
2. **Published city tables may be rounded.** Minute-rounded times and approximate city-centre coordinates do not support millisecond-accuracy claims.
3. **Global path samples are sparse.** The tested central-line points do not validate every point on every path, the complete penumbral footprint, both corridor boundaries or all shadow-width/depth/velocity outputs.
4. **City searches depend on supplied data.** The library reports the catalogue points supplied by the caller; it does not imply coverage of every location in a country.
5. **Lunar atmospheric shadow is empirical.** The 87 km layer in the Herald–Sinnott prescription is an empirical global model, not a resolved atmospheric-opacity simulation.
6. **Lunar-limb correction is experimental.** Neural and DEM corrections require independent, documented lunar-limb and contact benchmarks.
7. **DEM structural checks are not accuracy certification.** Metadata, file layout and interpolation tests do not establish absolute topographic accuracy.
8. **Coordinate frames matter.** Selecting a DE440s ephemeris does not automatically transform a DEM labelled in a DE421 body-fixed frame.
9. **Uncertainty must be supplied.** Solver residuals are not automatically physical uncertainty estimates. Uncertainty propagation uses an explicit caller-provided budget.
10. **Time scales must match.** UTC, UT1, TT, ΔT and Earth-orientation assumptions must be interpreted consistently with the reference being reproduced.

The project keeps these limits explicit. The future scientific-certification profile for a 1.0.0 release includes additional evidence requirements, including independent lunar DEM control points and external scientific review.

---

# Project roadmap and 1.0 release gate

The project contains multiple development phases. They are documented separately so users can inspect the mathematical conventions, input formats, validation status and known gaps of each subsystem.

| Phase | Area | Main additions |
|---|---|---|
| Core engine | Solar local circumstances | Apparent Sun/Moon geometry, contacts and local reporting |
| Global geometry | Shadow axis and paths | WGS84 ray/ellipsoid intersections, shadow metrics and path outputs |
| Lunar eclipses | Geocentric and topocentric lunar analysis | Herald–Sinnott oblate-Earth model, contacts and local visibility |
| Phase 4 | Besselian backend | Explicit published polynomial elements and independent solution path |
| Phase 5 | Lunar-limb framework | Spherical, gridded and tabulated limb interfaces |
| Phase 6 | Validation framework | Unified local, geocentric, path and Besselian reference runner |
| Phase 7.3 | Shadow corridors | Central/penumbral corridor geometry and GIS exports |
| Phase 7.4 | Observation planner | Candidate-site comparison |
| Phase 7.5 | Uncertainty propagation | Explicit covariance budgets and Monte Carlo propagation |
| Phase 7.6 | PDS3 lunar topography | Memory-mapped SLDEM2015-compatible DEM reader |
| Phase 7.7 | Performance/regression | Deterministic regression and micro-benchmarks |
| Phase 8 | Reproducibility | Reference fingerprints, EOP audit and unified validation |
| Phase 9.1–9.7 | Lunar DEM tooling | Tiling, PDS4/GeoTIFF/JP2, frame transforms, mosaics and overlap audit |
| Phase 11 | Advanced prediction | Interval search over multiple observers |
| Phase 12 | Advanced geometry | Arbitrary-time observation geometry and shadow footprint |
| Phase 13 | Performance and scalability | Streaming city search and country-index cache |
| Phase 14 | Public API and ecosystem | Curated API, runtime information, JSON and extensions |
| Phase 15 | Certification and 1.0 gate | Reproducible evidence audit and Alpha/scientific release profiles |

## Phase 11 — Advanced Eclipse Prediction Engine

`EclipseEngine.search_solar_eclipses(start, end, observers, ...)` searches a UTC interval and evaluates every new-Moon candidate separately at each supplied `Observer`.

A result groups the geocentric maximum with locations where a local eclipse was found, including each location's contacts and circumstances. Local maxima are restricted to the requested interval and the search does not fall forward to a later eclipse.

```python
from eclipsekit import EclipseEngine, Observer

engine = EclipseEngine("de440s")

locations = [
    Observer(44.4268, 26.1025, name="Bucharest"),
    Observer(40.4168, -3.7038, name="Madrid"),
]

search = engine.search_solar_eclipses(
    "2026-01-01",
    "2028-01-01",
    locations,
    min_magnitude=0.01,
)

print(search.to_dict())
```

The API only reports the locations passed to it and does not imply visibility across the surrounding region or globe. The default local search window is ±12 hours from geocentric maximum (configurable up to 24 hours). Batch searches default to excluding optional sunrise/sunset, shadow-metric and planet calculations.

See [`docs/PHASE11_ADVANCED_ECLIPSE_PREDICTION.md`](docs/PHASE11_ADVANCED_ECLIPSE_PREDICTION.md) and [`examples/solar_eclipse_interval_search.py`](examples/solar_eclipse_interval_search.py).

## Phase 12 — Advanced Geometry and Observation

Phase 12 adds `calculate_observation_geometry()` for arbitrary-time topocentric Sun/Moon geometry and an optional caller-supplied `HorizonProfile` for skyline-aware visibility.

It also adds `calculate_shadow_footprint()` for an instantaneous WGS84 central/penumbral shadow-cone footprint, plus GeoJSON linework exports. Existing contact, corridor and interval-search APIs remain available; horizon profiles are opt-in.

The footprint uses spherical solar/lunar radii and the WGS84 reference ellipsoid. It is not a terrain-clipped map.

See [`docs/PHASE12_ADVANCED_GEOMETRY_OBSERVATION.md`](docs/PHASE12_ADVANCED_GEOMETRY_OBSERVATION.md).

## Phase 13 — Performance and scalability

Phase 13 adds a streaming city-search API and precomputed country indexes for repeated catalogue queries.

`EclipseEngine.iter_search_cities()` yields each hit as its bounded NumPy batch is processed and preserves catalogue order. `search_cities()` continues to return a complete list sorted by magnitude. `CityCatalog.iter_index_batches()` yields read-only slices from the precomputed country index without allocating a second full index array. `index_cache_info()` reports country-index cache size.

The benchmark suite compares cached country lookup with a full scan and runs a deterministic serial-versus-four-thread NumPy batch workload. Measurements are machine/workload-specific; rerun benchmarks on the target machine before changing concurrency policy.

Use:

```powershell
eclipsekit-benchmark --warmups 1 --repeats 5 --iterations 5 `
  --track-memory --output-dir reports/phase13 --stem scalability
```

See [`docs/PHASE13_PERFORMANCE_SCALABILITY.md`](docs/PHASE13_PERFORMANCE_SCALABILITY.md).

## Phase 15 — running the Alpha release evidence audit

The Phase 15 certification command produces an evidence report before a software Alpha or scientific 1.0.0 release. It checks the public API manifest, source fingerprint, software tests and lint, wheel contents, published reference regressions, the Phase 8.4 unified-validation report, real PDS3 DEM structure, independent lunar DEM control-point reports and external scientific review evidence.

The `alpha` profile deliberately keeps four future scientific 1.0.0 requirements visible as `PARTIAL` or `NOT_RUN` instead of converting missing evidence into passes:

- public API maturity;
- independent lunar DEM control points;
- independent scientific peer review;
- distribution version 1.0.0.

The Alpha decision can be `ALPHA_RELEASE_READY` while `scientific_certification_status` remains `NOT_CERTIFIED`.

The following is the documented Phase 15 workflow. It assumes that the required local validation assets and SLDEM2015 IMG/LBL product have already been obtained and that their use is permitted:

```powershell
python -m pip install -e ".[dev,limb,security]"

# Safely merge the additional partial-eclipse reference into the local manifest.
# The helper creates a backup and preserves the existing cases.
python scripts/merge_phase15_partial_reference.py

# Run the unified Phase 6 reference runner.
eclipsekit-validate `
  --references data/validation/reference_cases.json `
  --path-manifest data/validation/path_reference_manifest.json `
  --besselian-reference data/validation/besselian_1999_reference.json `
  --kernel de440s `
  --cache-dir "$env:LOCALAPPDATA\\EclipseKit\\kernels" `
  --json-out reports/phase15/references/reference-validation.json `
  --markdown-out reports/phase15/references/reference-validation.md

# Run the Phase 8.4 unified validation.
eclipsekit-validate-all `
  --validation-dir data/validation `
  --kernel de440s `
  --cache-dir "$env:LOCALAPPDATA\\EclipseKit\\kernels" `
  --output-dir reports/phase15/unified

# Run the software Alpha evidence audit.
eclipsekit-certify `
  --validation-dir data/validation `
  --reference-report reports/phase15/references/reference-validation.json `
  --unified-report reports/phase15/unified/unified-validation.json `
  --dem-image data/SLDEM2015_128_60S_60N_000_360_FLOAT.IMG `
  --dem-label data/SLDEM2015_128_60S_60N_000_360_FLOAT.LBL `
  --expected-coordinate-system "MEAN EARTH/POLAR AXIS OF DE421" `
  --output-dir reports/phase15/certification-alpha `
  --run-pip-audit `
  --release-profile alpha
```

The expected successful Alpha decision is `ALPHA_RELEASE_READY`, with software readiness passing and scientific certification remaining `NOT_CERTIFIED`. A mandatory Alpha gate failure must not be described as a ready release.

For the scientific 1.0.0 profile, the independent control-point and peer-review evidence becomes mandatory. The detailed requirements and report interpretation are documented in [`docs/PHASE15_ALPHA_RELEASE.md`](docs/PHASE15_ALPHA_RELEASE.md) and [`docs/PHASE15_SCIENTIFIC_CERTIFICATION_1_0.md`](docs/PHASE15_SCIENTIFIC_CERTIFICATION_1_0.md).

---

## Phase 14 — Public API and ecosystem

New integrations should import supported interfaces from `eclipsekit.api`. The curated API exposes engine/configuration models, observation and search results, lunar-limb/DEM interfaces, validation helpers, benchmark records, runtime diagnostics, strict JSON interchange and explicit third-party extension loading.

The existing `from eclipsekit import ...` imports remain supported. `API_CONTRACT_VERSION` identifies the curated Python interface; distribution versions and report schema versions remain separate.

`get_runtime_info()` reports runtime and optional dependency versions without importing Torch or Rasterio. `write_json()` atomically writes strict interoperable JSON and rejects unsupported/non-finite values. `discover_extensions()` reads plugin metadata only; `load_extension()` imports a selected trusted factory only when explicitly requested.

See [`docs/PUBLIC_API.md`](docs/PUBLIC_API.md), [`docs/EXTENSIONS.md`](docs/EXTENSIONS.md) and [`docs/API_MIGRATION.md`](docs/API_MIGRATION.md).

## Phase 15 — Scientific certification and 1.0 release gate

`eclipsekit-certify` creates a reproducible evidence report before a major release. The audit checks the curated public API manifest, source fingerprint, software tests and lint, wheel contents, published reference regressions, the Phase 8.4 unified-validation report, real PDS3 DEM structure, independent lunar DEM control-point reports and external scientific review evidence.

The default `scientific` profile deliberately reports `NOT_CERTIFIED` when independent evidence required for a scientific 1.0.0 release is missing.

For a software-only Alpha release, `eclipsekit-certify --release-profile alpha` does not block on four future 1.0.0 requirements:

1. stable public API maturity;
2. independent lunar DEM control points;
3. external scientific peer review;
4. distribution version 1.0.0.

These gates remain visible in the report as `PARTIAL` or `NOT_RUN`; they are not converted into passes. The Alpha decision can be `ALPHA_RELEASE_READY`, while `scientific_certification_status` remains `NOT_CERTIFIED`.

The Phase 15 documentation explains the complete acceptance profile, report inputs, evidence requirements and remaining scientific gaps:

- [`docs/PHASE15_ALPHA_RELEASE.md`](docs/PHASE15_ALPHA_RELEASE.md)
- [`docs/PHASE15_SCIENTIFIC_CERTIFICATION_1_0.md`](docs/PHASE15_SCIENTIFIC_CERTIFICATION_1_0.md)

---

# What was separated from the original application

The numerical library retains and reorganizes the following types of functionality from the supplied source:

- apparent topocentric Sun/Moon geometry and angular radii;
- external/internal contact residuals and bisection contact solving;
- new-Moon phase screening for the next local eclipse;
- position angle, Meeus-style optical libration/axis estimate and selenographic limb-point conversion;
- the multi-resolution hash-grid `LunarAltitudeNet` architecture and checkpoint metadata expectations;
- WGS84 ray/ellipsoid shadow-axis intersections, approximate path width, umbral velocity and depth calculations;
- vectorized city ECEF/up-vector catalogue and per-city maximum search;
- optional visible-planet and approximate ecliptic-sector information;
- sunrise/sunset calculations and structured replacement for the old text report;
- ΔT polynomial and astronomical-calendar conversion for extended epochs.

The Unreal UDP protocol, background threads, live HUD packet packing, reverse-geocoding, satellite ephemeris downloads for Jupiter/Saturn/Neptune and import-time initialization were intentionally excluded from the scientific library. They belong in a separate application/integration layer.

---

# Main public API

The following list is an orientation guide to central entry points; see the API reference and module documentation for exact signatures and options.

## Eclipse engine

- `EclipseEngine.calculate_local(...)`
- `EclipseEngine.find_next_local_eclipse(...)`
- `EclipseEngine.solve_contact(...)`
- `EclipseEngine.solve_contact_detailed(...)`
- `EclipseEngine.find_global_maximum(...)`
- `EclipseEngine.global_shadow_path(...)`
- `EclipseEngine.global_path_for_eclipse(...)`
- `EclipseEngine.global_shadow_corridor(...)`
- `EclipseEngine.global_shadow_corridor_for_eclipse(...)`
- `EclipseEngine.search_solar_eclipses(...)`
- `EclipseEngine.search_cities(...)`
- `EclipseEngine.iter_search_cities(...)`
- `EclipseEngine.find_solar_eclipses_by_country(...)`
- `EclipseEngine.plan_observations(...)`
- `EclipseEngine.calculate_observation_geometry(...)`
- `EclipseEngine.calculate_shadow_footprint(...)`
- `EclipseEngine.calculate_lunar_eclipse(...)`
- `EclipseEngine.find_lunar_eclipses(...)`
- `EclipseEngine.find_next_lunar_eclipse(...)`
- `EclipseEngine.lunar_eclipse_city_visibility(...)`
- `EclipseEngine.lunar_eclipse_local_visibility(...)`
- `EclipseEngine.format_report(...)`

## Catalogue, limb, DEM and export utilities

- `CityCatalog.from_csv(...)`
- `LunarLimbCorrector.from_checkpoint(...)`
- `GriddedLunarLimbModel.from_csv(...)`
- `TabulatedAngularLunarLimbProfile.from_csv(...)`
- `PDS3LunarDEMModel.from_pds3_img(...)`
- `open_pds3_lunar_dem(...)`
- `open_pds4_lunar_dem(...)`
- `open_geotiff_lunar_dem(...)`
- `LunarDEMMosaicModel(...)`
- `LunarCoordinateTransform(...)`
- `UncertaintyBudget.from_standard_deviations(...)`
- `propagate_uncertainty(...)`
- `city_hits_to_geojson(...)`
- `shadow_path_to_geojson(...)`
- `shadow_corridor_to_geojson(...)`
- `shadow_corridor_to_kml(...)`
- `write_shadow_corridor_csv(...)`
- `write_shadow_corridor_kml(...)`
- `write_city_hits_csv(...)`
- `write_geojson(...)`
- `write_observation_plan_csv(...)`
- `write_observation_plan_json(...)`

## Validation API

- `eclipsekit.validation.load_reference_cases(...)`
- `run_validation_suite(...)`
- `load_corridor_reference_csv(...)`
- `validate_shadow_corridor_reference(...)`
- `audit_lunar_dem_mosaic_overlaps(...)`
- `get_runtime_info()`
- `write_json(...)`
- `discover_extensions(...)`
- `load_extension(...)`

---

# Documentation index

The README is an overview and usage guide. Detailed equations, data schemas, API contracts, methodology and scientific limits are maintained in the `docs/` directory.

| Subject | Documentation |
|---|---|
| Lunar eclipses, contacts and local visibility | [`LUNAR_ECLIPSES.md`](docs/LUNAR_ECLIPSES.md), [`LUNAR_ECLIPSE_METHODOLOGY.md`](docs/LUNAR_ECLIPSE_METHODOLOGY.md) |
| Lunar external reference matrix | [`LUNAR_REFERENCE_VALIDATION_2022_2028.md`](docs/LUNAR_REFERENCE_VALIDATION_2022_2028.md) |
| Contact solver and contact event model | [`CONTACT_SOLVER_V2.md`](docs/CONTACT_SOLVER_V2.md), [`CONTACT_EVENT_MODEL.md`](docs/CONTACT_EVENT_MODEL.md) |
| Besselian backend | [`BESSELIAN_BACKEND.md`](docs/BESSELIAN_BACKEND.md) |
| Lunar-limb framework | [`LUNAR_LIMB_FRAMEWORK.md`](docs/LUNAR_LIMB_FRAMEWORK.md) |
| PDS3 lunar topography | [`LUNAR_TOPOGRAPHY_PDS3.md`](docs/LUNAR_TOPOGRAPHY_PDS3.md) |
| Lunar DEM frame and datum transforms | [`PHASE9_3_LUNAR_FRAME_DATUM_TRANSFORMS.md`](docs/PHASE9_3_LUNAR_FRAME_DATUM_TRANSFORMS.md) |
| Frame-aware lunar DEM queries | [`PHASE9_5_FRAME_AWARE_DEM_ACCESS.md`](docs/PHASE9_5_FRAME_AWARE_DEM_ACCESS.md) |
| Lunar DEM mosaic routing | [`PHASE9_6_LUNAR_DEM_MOSAIC.md`](docs/PHASE9_6_LUNAR_DEM_MOSAIC.md) |
| Lunar DEM overlap audit | [`PHASE9_7_LUNAR_DEM_MOSAIC_OVERLAP_AUDIT.md`](docs/PHASE9_7_LUNAR_DEM_MOSAIC_OVERLAP_AUDIT.md) |
| Global shadow corridors | [`SHADOW_CORRIDOR_V2.md`](docs/SHADOW_CORRIDOR_V2.md), [`PHASE8_1_CORRIDOR_VALIDATION.md`](docs/PHASE8_1_CORRIDOR_VALIDATION.md) |
| Scientific validation and regression | [`SCIENTIFIC_VALIDATION.md`](docs/SCIENTIFIC_VALIDATION.md), [`VALIDATION_FRAMEWORK.md`](docs/VALIDATION_FRAMEWORK.md) |
| Earth-orientation reproducibility | [`PHASE8_3_EOP_REPRODUCIBILITY.md`](docs/PHASE8_3_EOP_REPRODUCIBILITY.md) |
| Unified validation | [`PHASE8_4_UNIFIED_VALIDATION.md`](docs/PHASE8_4_UNIFIED_VALIDATION.md) |
| Observation planner | [`OBSERVATION_PLANNER.md`](docs/OBSERVATION_PLANNER.md) |
| Uncertainty propagation | [`UNCERTAINTY_PROPAGATION.md`](docs/UNCERTAINTY_PROPAGATION.md) |
| Public API | [`PUBLIC_API.md`](docs/PUBLIC_API.md), [`API_MIGRATION.md`](docs/API_MIGRATION.md) |
| Extension system | [`EXTENSIONS.md`](docs/EXTENSIONS.md) |
| Performance and regression | [`PERFORMANCE_AND_REGRESSION.md`](docs/PERFORMANCE_AND_REGRESSION.md), [`PHASE13_PERFORMANCE_SCALABILITY.md`](docs/PHASE13_PERFORMANCE_SCALABILITY.md) |
| Alpha and scientific 1.0 release requirements | [`PHASE15_ALPHA_RELEASE.md`](docs/PHASE15_ALPHA_RELEASE.md), [`PHASE15_SCIENTIFIC_CERTIFICATION_1_0.md`](docs/PHASE15_SCIENTIFIC_CERTIFICATION_1_0.md) |
| Data provenance | [`DATA_PROVENANCE.md`](docs/DATA_PROVENANCE.md) |

Runnable examples are available in [`examples/`](examples/). Project changes are recorded in [`CHANGELOG.md`](CHANGELOG.md).

---

# Contributing, security and citation

Contributions, bug reports and documentation improvements are welcome.

- Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before submitting a change.
- Open a [GitHub Issue](https://github.com/Dragos112358/EclipseKit/issues) for a reproducible bug report or feature request.
- Use pull requests for code and documentation changes.
- Include relevant tests and document scientific assumptions when changing numerical behaviour.

For security-related reports, follow [`SECURITY.md`](SECURITY.md).

EclipseKit is distributed under the **Apache License 2.0**. See [`LICENSE.md`](LICENSE.md) and [`NOTICE`](NOTICE). Third-party datasets, kernels and model weights may have separate licences; the project licence does not grant redistribution rights to those assets.

For citation metadata, see [`CITATION.cff`](CITATION.cff). A DOI-backed scientific release and external review remain part of the future scientific 1.0 release process.

---

<p align="center">
  <strong>EclipseKit — Python tools for solar and lunar eclipse analysis</strong><br>
  <a href="https://pypi.org/project/eclipsekit/">Install from PyPI</a> ·
  <a href="https://pypi.org/project/eclipsekit/0.1.0a1/#files">Download release files</a> ·
  <a href="https://github.com/Dragos112358/EclipseKit">View source on GitHub</a>
</p>
