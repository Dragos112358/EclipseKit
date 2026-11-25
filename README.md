# EclipseKit

**A modular Python engine for local and global solar- and lunar-eclipse circumstances.**

## Install

After the Alpha release is published on PyPI, install the core library with:

```bash
python -m pip install --pre eclipsekit
```

The core install includes the numerical engine and its required NumPy/Skyfield
dependencies. Optional extras are available for raster DEM readers and neural
lunar-limb integration; the latter installs PyTorch and does not bundle a model
checkpoint:

```bash
python -m pip install --pre "eclipsekit[raster]"
python -m pip install --pre "eclipsekit[limb]"
```


This is an initial extraction/refactoring of the supplied Eclipse Simulator 3D
Python source. It separates numerical astronomy from Unreal/UDP runtime code,
uses explicit ephemeris selection, returns structured Python objects, and keeps
large external datasets out of the installed package.

> **Scientific status: alpha / validation pending.** The project is a usable
> development foundation, not yet a claim of publication-grade accuracy. In
> particular, the inherited shadow-width/depth and neural lunar-limb methods
> need comparison against independent reference solutions before being used as
> authoritative predictions.

## Design goals

- A small wheel: no DE432s/DE440/DE441 kernel, city database, or neural checkpoint
  is bundled in the package.
- Ephemeris independence: use a local BSP/SPK file or select a JPL kernel by name.
- Local circumstances: C1–C4, maximum, magnitude, exact disc-overlap obscuration,
  Sun altitude/azimuth, optional sunrise/sunset, visible planets, and shadow metrics.
- Global circumstances: sample the direct ephemeris-based umbral/antumbral axis
  on the WGS84 ellipsoid, with optional Phase 7.3 central and penumbral corridor
  boundaries, widths, local duration estimates, and GIS exports.
- Independent Besselian backend: import published polynomial elements and solve
  local C1-C4 circumstances, geocentric closest approach, and central-line
  ground tracks without deriving those elements from the active JPL kernel.
- Country/city searches: use a user-provided CSV and vectorized batch processing.
- Geocentric lunar-eclipse analysis using the default Herald--Sinnott oblate-Earth
  shadow prescription, with penumbral/umbral classification, P1/U1/U2/maximum/
  U3/U4/P4 contacts, separate UTC/UT1/TT output, and per-phase city visibility.
- Modular lunar-limb framework: spherical baseline, caller-supplied gridded DEM, tabulated apparent-limb profile, and optional neural checkpoint adapter.
- Import safety: importing `eclipsekit` does not download data, open a socket,
  start a thread, or load a neural model.

## Install in PyCharm

1. Create/open a project folder in PyCharm.
2. Set the project interpreter to Python 3.10+ (3.12 is a good choice).
3. Open PyCharm's Terminal and run:

```bash
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Install the project and development tools:

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

For the optional lunar neural network:

```bash
pip install -e ".[limb,dev]"
```


## Lunar-eclipse calculations (experimental)

EclipseKit includes a geocentric lunar-eclipse solver. It searches full-moon
phases, evaluates the Moon against the angle-dependent Herald--Sinnott
oblate-Earth shadow model (87 km notional eclipse-forming layer), classifies
penumbral, partial, and total eclipses, and solves the P1/U1/U2/maximum/U3/U4/P4
contacts where applicable. Local city visibility is evaluated separately from
the geocentric contacts.

```python
from eclipsekit import EclipseEngine

engine = EclipseEngine("de440s")
event = engine.find_next_lunar_eclipse("2025-01-01")
if event is not None:
    print(event.eclipse_type)
    print(event.to_dict())

# Search a date interval and choose the civil calendar explicitly.
events = engine.find_lunar_eclipses(
    "1500-01-01", "1501-01-01", calendar="julian"
)
```

The default `calendar="historical"` uses the Julian calendar through
1582-10-04 and the Gregorian calendar from 1582-10-15; the skipped dates
1582-10-05 through 1582-10-14 are rejected. `calendar="julian"` and
`calendar="gregorian"` select proleptic calendars. Time-zone-qualified timestamps
are absolute instants and are not reinterpreted as civil-calendar fields.
Internal event calculations remain on TT Julian dates.

`find_lunar_eclipses(start, end)` uses a half-open interval (`start` included,
`end` excluded). Date-only boundaries begin at civil midnight, so
`find_lunar_eclipses("2025-03-14", "2025-03-15")` searches all of 14 March.
This interval convention is separate from `EclipseEngine.time("YYYY-MM-DD")`,
which continues to return 12:00 for date-only single-event calculations.

The default lunar shadow model is the **Herald--Sinnott oblate-Earth prescription**:
it uses an 87 km notional eclipse-forming atmospheric layer and angle-dependent
umbra/penumbra boundaries that account for Earth's flattening. Contact times are
refined against the full non-circular boundaries. The older circular-cone
approximation remains available with `shadow_model="circular"` for reproducing
legacy Alpha results.

Results remain experimental until independently validated with matching
ephemeris, Earth-orientation and Delta-T inputs. The 87 km atmospheric layer is
an empirical global prescription, not a resolved atmospheric-opacity model.
The result serializer reports UTC, UT1 and TT separately. Local phase visibility
is evaluated topocentrically at each geocentric contact; it does not replace
geocentric contact times with moonrise/moonset.

See [docs/LUNAR_ECLIPSES.md](docs/LUNAR_ECLIPSES.md) for model equations,
calendar semantics, time-scale assumptions and examples. For a reproducible
16-event external regression matrix (2022–2028), see
[docs/LUNAR_REFERENCE_VALIDATION_2022_2028.md](docs/LUNAR_REFERENCE_VALIDATION_2022_2028.md)
and run `python scripts/validate_lunar_references.py --kernel de440s`.

## Configuration API (recommended for new code)

EclipseKit 0.1.x retains the original constructor keywords for compatibility, but
new applications should group numerical assumptions into immutable configuration
objects. This makes the ephemeris, Earth-orientation source, contact radii,
solver tolerances, and atmospheric refraction assumptions explicit and
serializable:

```python
from eclipsekit import (
    EclipseEngine, EclipseConfig, EphemerisConfig, EarthOrientationConfig,
    ContactModelConfig, SolverConfig, AtmosphereConfig, Observer,
)

config = EclipseConfig(
    ephemeris=EphemerisConfig.jpl(
        "de440s", earth_orientation=EarthOrientationConfig.iers()
    ),
    contacts=ContactModelConfig(),  # current spherical-disc radii
    solver=SolverConfig(
        root_tolerance_seconds=1e-5,
        root_max_iterations=100,
        minimum_tolerance_seconds=0.05,
    ),
    atmosphere=AtmosphereConfig(
        refraction_enabled=True, pressure_mbar=1013.25, temperature_c=15.0
    ),
)

engine = EclipseEngine(config=config)
result = engine.calculate_local(Observer(42.6, -5.5703), "2026-08-12")
print(config.to_dict())  # JSON-friendly assumptions for reproducibility
```

`EphemerisConfig.local(r"D:/kernels/de440s.bsp")` selects a local kernel.
`ContactModelConfig.iau_mean_moon()` selects one adopted mean lunar radius for
the spherical-disc contacts; this is not a topographic limb model.
`AtmosphereConfig(refraction_enabled=False)` disables refraction in the reported
Sun altitude/azimuth while retaining station pressure as metadata.

`SolverConfig` supports bisection (the backwards-compatible default) and a
safeguarded Brent-Dekker root solver. The detailed contact API also supports
automatic bracket expansion, tangent-contact candidates, and convergence
diagnostics. The engine's internal C1-C4 searches remain bounded to their
physical ingress/egress intervals; only the explicit public detailed solver
expands beyond a supplied interval when requested by configuration. See
[`docs/CONTACT_SOLVER_V2.md`](docs/CONTACT_SOLVER_V2.md) for the semantics and
examples. The old constructor remains valid:

```python
engine = EclipseEngine("de440s", sun_radius_km=696000.0)
```

Do not combine `config=` with legacy constructor overrides.

## Ephemerides: choose any suitable kernel

The core accepts a local `.bsp` file or a JPL kernel name:

```python
from eclipsekit import EclipseEngine

engine = EclipseEngine("de440s")
# or:
engine = EclipseEngine("de432s")
engine = EclipseEngine("de440")
engine = EclipseEngine("de441")
# or a file stored anywhere on disk:
engine = EclipseEngine(r"D:/Astronomy/kernels/de440s.bsp")
# or a direct NAIF/SPK URL for another supported kernel:
engine = EclipseEngine(
    "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp"
)
```

When a common JPL DE kernel name is selected, it is downloaded from the official
NAIF planetary SPK directory into the separate EclipseKit cache
(`~/.eclipsekit/ephemerides`) if not already cached. A local path or explicit HTTP(S)
URL is also accepted. Other named kernels can use Skyfield's own kernel registry;
for an arbitrary/custom kernel, pass its local BSP path or direct download URL.
The wheel does **not** contain the kernel.
DE441 can be several gigabytes; it will not be downloaded unless the user
explicitly selects it. Any custom kernel must expose the Earth, Sun, and Moon
segments under the requested names. Non-standard segment names can be supplied
with `body_names={"earth": ..., "sun": ..., "moon": ...}`.

The default time scale uses Skyfield's bundled tables. The supplied source's
Espenak–Meeus-style Delta-T polynomial is retained for dates outside 1900–2100;
ancient/far-future time conversions are estimates and carry substantial
physical uncertainty. For modern calculations, the engine now exposes explicit
Earth-orientation modes:

```python
from eclipsekit import EclipseEngine, EarthOrientationConfig

# Offline-friendly Skyfield bundled tables (default)
engine_builtin = EclipseEngine("de440s")

# IERS finals2000A.all; first use can require Internet access
engine_iers = EclipseEngine(
    "de440s", earth_orientation=EarthOrientationConfig.iers()
)

# Historical model reproduction only; NOT an operational UTC/EOP setting
engine_nasa_2014 = EclipseEngine(
    "de440s", earth_orientation=EarthOrientationConfig.fixed(71.4)
)

print(engine_iers.time_scale_diagnostics("2026-08-12T18:30:00Z"))
```

`builtin` is the offline-friendly default. `iers` loads IERS `finals2000A.all`
through Skyfield (`Loader.timescale(builtin=False)`). `fixed()` is deliberately
explicit and intended only to reproduce a named published prediction that
specifies a fixed ΔT. A fixed ΔT can imply a synthetic DUT1 outside UTC's normal
±0.9 second range; it must not silently replace observed Earth-orientation data.
For a table whose clock is UT1, use `engine.time_from_ut1(...)`; for civil UTC
strings/datetimes, use `engine.time(...)`. The engine's `time_scale_diagnostics()`
reports the selected mode, ΔT, DUT1, and whether the derived DUT1 is compatible
with the UTC convention.

## 1. Local eclipse circumstances

```python
from eclipsekit import EclipseEngine, Observer

engine = EclipseEngine("de440s")
observer = Observer(
    latitude=42.0,
    longitude=-5.0,
    elevation_m=0,
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

A date-only string is interpreted as 12:00 UTC, so the default ±12-hour window
covers the requested civil date. To prevent automatic search for the next event,
set `find_next_if_none=False`. Increase `search_window_hours` when searching a
longer interval around a known event.

`magnitude` and `obscuration_percent` are different quantities. EclipseKit
calculates obscuration from the analytic overlap area of two apparent circles;
it does not use the shortcut `magnitude * 100` from the original report code.

`duration_seconds` retains the historical C2–C3 central phase convention
(0 for a non-central eclipse). The explicit `central_phase_duration_seconds`
field is `None` when there is no central phase; `partial_phase_duration_seconds`
is C1–C4 when both external contacts are found.

Phase 3 also exposes `result.contact_events`, a chronological mapping containing
structured C1/C2/maximum/C3/C4 records when those events exist. Each
`ContactEvent` retains UTC, TT-JD, and UT1-JD separately, topocentric geometry,
position/vertex angles, solar horizon status, and the Phase 2 solver diagnostics
for contact roots. Its uncertainty remains `None` until a validated physical
uncertainty model is available. See
[`docs/CONTACT_EVENT_MODEL.md`](docs/CONTACT_EVENT_MODEL.md) and
`examples/contact_event_model.py`.

## 2. Lunar-limb correction with your existing model

The neural model architecture from the supplied server is reproduced in
`eclipsekit/limb.py`. The trained checkpoint was supplied and was successfully
loaded against this architecture during integration. Keep the 66 MB checkpoint
as a local research asset (not inside the wheel): copy it to
`models/lunar_altitude_contact_bands_fp16_finetuned.pt` and use:

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
    print(contact, correction.time, correction.delta_seconds,
          correction.predicted_terrain_altitude_m)
```

PyTorch is imported only when loading/using the model. The loader uses
`weights_only=True`; if the checkpoint contains custom pickled objects, re-save
it as a plain state dictionary plus primitive metadata rather than enabling
unsafe arbitrary unpickling by default.

The supplied checkpoint metadata reports `best_val_rmse_m` of about 12.58 m.
That is the model's stored validation metric, not a demonstrated 12.58 m global
error bound and not a contact-time accuracy guarantee. The model's training-data
provenance, geographic/selenographic coverage, independent test set, and license
still need to be documented. Treat this correction as experimental until checked
against an independent lunar-limb profile and observed/published contact timings.

## 3. Global shadow path

```python
path = engine.global_path_for_eclipse(
    "2026-08-12",
    search_radius_hours=4,
    samples=101,
)

for point in path:
    print(point.latitude, point.longitude, point.width_km, point.shadow_kind)
```

Or provide an exact interval to `global_shadow_path(start, end, samples=...)`.
The calculation intersects the shadow-axis ray with a WGS84 reference ellipsoid.
Points are returned only when the axis intersects the ellipsoid; it does not
invent a ground track for a central cone that misses Earth.

### Reproducible corridor validation (Phase 8.1)

Phase 8.1 adds a CLI that runs the independent 2017 NASA corridor comparison at
multiple nested time-sampling resolutions and records numerical convergence
diagnostics. The finest run is compared against the supplied reference rows;
coarser runs are compared with it using aggregate path-length, width, duration
and boundary-coverage metrics. The convergence results are diagnostics, not
independent accuracy evidence.

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

See [`docs/PHASE8_1_CORRIDOR_VALIDATION.md`](docs/PHASE8_1_CORRIDOR_VALIDATION.md)
for the report schema, interpretation and model limitations.

### Global shadow corridor (Phase 7.3)

For boundary geometry around the central axis, use the Phase 7.3 corridor API:

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

write_geojson(shadow_corridor_to_geojson(corridor), "reports/corridor.geojson")
write_shadow_corridor_csv(corridor, "reports/corridor.csv")
write_shadow_corridor_kml(corridor, "reports/corridor.kml")
```

`central_left`/`central_right` are the umbral or antumbral limits relative to
track direction; `penumbra_left`/`penumbra_right` are the outer partial-eclipse
limits for the same time slice. The two sides are not permanently synonymous
with north and south. Widths are cross-track geodesic spans on the WGS84
reference ellipsoid. Duration fields are explicitly first-order estimates
(along-track cone chord divided by instantaneous track speed), not root-solved
local C1-C4 circumstances. The local track bearing is computed from a short
symmetric time difference, independent of the requested sample spacing. The
current method samples only times when the central axis intersects Earth, so
it does not calculate the full penumbral sunrise/sunset footprint. Terrain height, atmospheric refraction and lunar-limb topography
are not included.

The bundled sparse NASA/GSFC 2017 path-table fixture can be compared with the
result using `validate_shadow_corridor_reference()`. It is a small regression
sample with declared tolerances, not a complete certification of corridor
boundaries. See [`docs/SHADOW_CORRIDOR_V2.md`](docs/SHADOW_CORRIDOR_V2.md) and
run `python .\examples\shadow_corridor_2017.py` for the end-to-end example.

## 4. Country-level/city-level eclipse search

The development copy of `CountryPoints.csv` used during integration contains
8,133 city/locality points across 245 country/territory labels. The catalogue is
not part of the distributable starter repository or PyPI wheel until its source
and redistribution licence are documented. Add your own file at
`data/CountryPoints.csv` or pass a custom path to `CityCatalog.from_csv()`.
The expected columns are `Country,City,Latitude,Longitude,Elevation_m`.

```python
from pathlib import Path
from eclipsekit import CityCatalog, EclipseEngine

catalog = CityCatalog.from_csv(Path("data") / "CountryPoints.csv")
engine = EclipseEngine("de440s")

# Cities in Romania that see the eclipse around this date:
hits = engine.search_cities(
    "2026-08-12",
    catalog,
    country="Romania",
    min_magnitude=0.001,
)
for hit in hits:
    print(hit.city.name, hit.magnitude, hit.obscuration_percent, hit.maximum)

# All solar-eclipse events in a time interval which affect catalogued cities
# in Spain. For exact local contacts at each hit city, use include_contacts=True.
events = engine.find_solar_eclipses_by_country(
    "2020-01-01", "2030-01-01", catalog,
    country="Spain", include_contacts=False,
)
for event in events:
    print(event.to_dict())
```

The country search operates on the points in the supplied CSV, not on every
square kilometre of a country. Results are therefore limited by the density and
quality of that city catalogue. The vectorized search uses bounded batches to
avoid creating one enormous city×time×coordinate array in RAM. Setting
`include_contacts=True` runs the local solver for each hit and is slower.

For contact times corrected by your neural lunar-limb model, pass both
`include_contacts=True` and `limb_corrector=limb` to
`find_solar_eclipses_by_country()` (or `search_cities()`). The result then
contains geometric contacts and a separate `limb_corrected_contacts` mapping.

The function `lunar_eclipse_city_visibility()` evaluates topocentric Moon
altitude at greatest eclipse and at each geocentric P1/U1/U2/U3/U4/P4 contact.
It reports phase visibility for the supplied city catalogue; it does not solve
local moonrise/moonset or replace the geocentric contact instants.


## Validate the supplied local assets

Copy the supplied 66 MB checkpoint to `models/lunar_altitude_contact_bands_fp16_finetuned.pt`.
Then run:

```bash
python examples/validate_assets.py
pytest -q
```

The validation script checks the actual CSV and, when the checkpoint is present,
loads the actual trained model and evaluates a few finite sample predictions.
Neither the checkpoint nor the city CSV is included in the PyPI wheel.

## Main public API

- `EclipseEngine.calculate_local(...)`
- `EclipseEngine.find_next_local_eclipse(...)`
- `EclipseEngine.solve_contact(...)`, `EclipseEngine.solve_contact_detailed(...)`
- `EclipseEngine.find_global_maximum(...)`
- `EclipseEngine.global_shadow_path(...)`
- `EclipseEngine.global_path_for_eclipse(...)`
- `EclipseEngine.global_shadow_corridor(...)`
- `EclipseEngine.global_shadow_corridor_for_eclipse(...)`
- `EclipseEngine.search_cities(...)`
- `EclipseEngine.find_solar_eclipses_by_country(...)`
- `EclipseEngine.calculate_lunar_eclipse(...)`
- `EclipseEngine.find_lunar_eclipses(...)`
- `EclipseEngine.find_next_lunar_eclipse(...)`
- `EclipseEngine.lunar_eclipse_city_visibility(...)`
- `EclipseEngine.format_report(...)`
- `CityCatalog.from_csv(...)`
- `LunarLimbCorrector.from_checkpoint(...)`
- `city_hits_to_geojson(...)`, `shadow_path_to_geojson(...)`, `shadow_corridor_to_geojson(...)`, `shadow_corridor_to_kml(...)`, `write_shadow_corridor_csv(...)`, `write_shadow_corridor_kml(...)`, `write_city_hits_csv(...)`, `write_geojson(...)`
- `load_corridor_reference_csv(...)`, `validate_shadow_corridor_reference(...)`
- `eclipsekit.validation.load_reference_cases(...)`, `run_validation_suite(...)`

## What was reused from the supplied source

- Apparent topocentric Sun/Moon geometry and angular radii.
- External/internal contact residuals and bisection contact solving.
- New-moon phase screening for the next local eclipse.
- Position angle, Meeus-style optical libration/axis estimate, and
  selenographic limb-point conversion.
- Your multi-resolution hash-grid `LunarAltitudeNet` architecture and checkpoint
  metadata expectations.
- WGS84 ray/ellipsoid shadow-axis intersections, approximate path width,
  umbral velocity and depth calculations.
- Vectorized city ECEF/up-vector catalogue and per-city maximum search.
- Optional visible-planet and approximate ecliptic-sector information.
- Sunrise/sunset calculations and structured replacement for the old text report.
- Delta-T polynomial and astronomical-calendar conversion for extended epochs.

The Unreal UDP protocol, background threads, live HUD packet packing,
reverse-geocoding, satellite ephemeris downloads for Jupiter/Saturn/Neptune, and
all import-time initialization were intentionally excluded from the scientific
library. They belong in a separate application/integration layer.

## Tests

```powershell
python -m pytest -v --basetemp=".pytest_tmp\pytest-run"
python -m ruff check src tests examples
```

The unit suite covers numerical helpers, geometry, catalogue parsing, time
utilities, the validation-fixture schema, and GeoJSON/CSV exporters. The separate
scientific-reference runner compares three local solar-eclipse cases and one
global maximum against published NASA tables. These references are not sufficient
to claim publication-grade accuracy for every feature; see the documented
coverage gaps in `docs/SCIENTIFIC_VALIDATION.md`.

## Before a public release

1. Select and add a licence after checking ownership and redistribution rights.
2. Document the exact source/version/licence of any city catalogue and lunar
   training data/checkpoint.
3. Extend independent tests for shadow width/depth/velocity, full global path,
   the neural limb correction, and ancient Delta-T.
4. Run the GitHub Actions workflow on all supported Python versions and archive
   validation reports with kernel/time-scale details.
5. Add a `CITATION.cff` and DOI-backed release when the project is ready for
   scientific citation.


## Scientific reference validation

A separate reference-validation runner compares local contacts and geocentric
maximum time with published NASA values. The first fixture set covers a total
eclipse in León (2026), a total eclipse in Dallas (2024), and an annular eclipse
in Albuquerque (2023). These published city tables are minute-rounded; each
fixture records its timezone conversion, source precision, coordinate caveat,
and tolerance. The suite also checks the NASA geocentric maximum for 12 August
2026. See [`docs/SCIENTIFIC_VALIDATION.md`](docs/SCIENTIFIC_VALIDATION.md).

Run from the project root:

```powershell
python -m pip install -e ".[dev,limb]"
python -m eclipsekit.validation --kernel de440s
```

A successful comparison is evidence for only the configured reference cases.
It does not prove global accuracy for every epoch, location, shadow metric, or
the optional neural lunar-limb model.

## Export maps and tables

City visibility hits, global shadow paths, and Phase 7.3 shadow corridors can be
exported to standard GeoJSON; city hits and corridors can also be exported to
CSV, and corridors to KML. GeoJSON coordinates follow RFC 7946 order
(longitude, latitude), and shadow paths crossing the antimeridian are split
into separate line segments. Example:

```powershell
python .\examples\export_results.py
```

Open the resulting `results/*.geojson` files in QGIS or another GeoJSON-capable
GIS viewer. The example requires your local `data/CountryPoints.csv`.

## GitHub and distribution hygiene

The public repository and PyPI distributions use an explicit allow-list. The
large local DEM collection, `CountryPoints.csv`, JPL kernels, neural checkpoint,
reports, results, virtual environments and caches are not published. Only the
nine small curated reference fixtures under `data/validation/` are allow-listed
for public tests and source distributions. The wheel contains only the
`eclipsekit` package and its typing marker.

The source is distributed under Apache-2.0; third-party datasets and model
weights retain their own licensing and redistribution conditions. See
[`docs/DATA_PROVENANCE.md`](docs/DATA_PROVENANCE.md), [`LICENSE.md`](LICENSE.md),
[`NOTICE`](NOTICE), and [`docs/GITHUB_PUBLISH.md`](docs/GITHUB_PUBLISH.md).

GitHub Actions runs the test and lint matrix. The PyPI workflow uses Trusted
Publishing and is triggered only by a published GitHub Release.

## Independent Besselian backend

Phase 4 adds `BesselianElements` and `BesselianSolver` for explicitly supplied
Besselian coefficients. A reference element set for the 11 August 1999 total
solar eclipse is included under `data/validation/`. The backend retains the
source ephemeris, ΔT convention, coefficient epoch, and validity interval; it
returns TT Julian Dates so time-scale conversion remains explicit.

Run the pure Besselian example (no JPL kernel is needed):

```powershell
python .\examples\besselian_backend.py
```

To exercise the backend through `EclipseEngine` with the configured Skyfield
time-scale source and JPL kernel, run:

```powershell
python .\examples\besselian_engine_integration.py
```

The full equations, coefficient format, API, scope, and known limits are
documented in [`docs/BESSELIAN_BACKEND.md`](docs/BESSELIAN_BACKEND.md).
This backend is a separate calculation path; it does not replace the direct
topocentric engine or imply that all eclipse predictions are yet independently
validated.


## Lunar Limb Framework (Phase 5)

The optional contact correction accepts either the legacy neural corrector or a
provider-neutral `limb_model`. New projects should use the latter:

```python
from eclipsekit import (
    EclipseEngine, GriddedLunarLimbModel, Observer,
)

dem = GriddedLunarLimbModel.from_csv(
    "lunar_dem.csv",
    name="Regional lunar DEM",
    source="record the product identifier and processing version",
    vertical_datum="record the DEM reference surface",
)
engine = EclipseEngine.from_jpl("de440s")
result = engine.calculate_local(
    Observer(42.6, -5.5703), "2026-08-12T18:00:00Z", limb_model=dem
)
```

The DEM must use selenographic latitude/longitude and radial heights in metres.
A tabulated apparent-limb profile can instead be loaded with
`TabulatedAngularLunarLimbProfile.from_csv()`. EclipseKit does not bundle NASA
LOLA tiles, Watts profiles, or neural weights; keep source, vertical datum,
resolution, and any point uncertainties with your supplied data. See
[`docs/LUNAR_LIMB_FRAMEWORK.md`](docs/LUNAR_LIMB_FRAMEWORK.md) for formats,
interpolation rules, compatibility, and scientific limitations.


## Validation Framework (Phase 6)

Phase 6 brings the reference checks into one reproducible runner. The default
suite checks three minute-rounded local event tables, one geocentric maximum,
four sparse NASA central-axis path subsets (2017, 2019, 2020, 2026), and the
NASA 1999 published Besselian-element regression. It records source provenance,
engine/kernel/time-scale configuration, comparison tolerances, and detailed
results in JSON and Markdown.

Run from the project root after installing the development extras and making
the JPL kernel available to Skyfield:

```powershell
python -m pip install -e ".[dev,limb]"
python -m ruff check src tests examples
eclipsekit-validate --kernel de440s
```

The command writes `reports/phase6-validation.json` and
`reports/phase6-validation.md`. The default suite contains nine top-level
acceptance cases and a separately labelled direct-engine-vs-Besselian diagnostic
with no acceptance threshold. A passing result is limited to those named references and tolerances;
it is not a universal accuracy claim. The 2026 NASA path table represents a
historical prediction realization and must not be conflated with observed
Earth-orientation values.

An independent lunar-limb profile benchmark is available as
`eclipsekit-validate-limb`. It requires user-supplied measured/reference heights
that are independent of the model's training and input data. Without an explicit
acceptance threshold, its status is `UNASSESSED`: computing error metrics alone
does not certify a model. Full instructions, supported options, CSV schemas,
uncertainty interpretation, tolerances, and known gaps are in
[`docs/VALIDATION_FRAMEWORK.md`](docs/VALIDATION_FRAMEWORK.md).


## Eclipse Observation Planner (Phase 7.4)

Compare candidate observing locations for a selected solar-eclipse epoch. The
planner calculates local circumstances at each supplied `Observer`, keeps
no-eclipse and calculation-error sites explicit, and ranks recommended sites
with a transparent weather-agnostic score.

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

The complete plan is also available through `plan.to_dict()` and can be written
with `write_observation_plan_json()`. The supplied weights emphasize obscuration
(50%), Sun altitude (30%), and C1–C4 event span (20%). These are configurable
heuristic priorities, not a probability of clear skies or observing success.
Cloud cover, terrain horizon, light pollution, access, travel and equipment are
not modelled. See [`docs/OBSERVATION_PLANNER.md`](docs/OBSERVATION_PLANNER.md)
for scoring details, statuses, output schemas, example instructions and limits.

Run the reproducible example (requires the `de440s` kernel):

```powershell
python .\examples\observation_planner.py
```


## Uncertainty Propagation (Phase 7.5)

EclipseKit can propagate explicitly supplied parameter uncertainties through a
caller-provided forward model. It supports correlated covariance budgets,
first-order finite-difference propagation, seeded Monte Carlo sampling, and
implicit contact-time sensitivity. It does not infer physical uncertainty
from root-solver residuals.

```python
from eclipsekit import UncertaintyBudget, propagate_uncertainty

budget = UncertaintyBudget.from_standard_deviations(
    ("observer_clock_bias", "ephemeris_bias"),
    (0.20, 0.05),
    units=("s", "km"),
    source_descriptions=("Documented input specifications",),
)
result = propagate_uncertainty(
    model_function, mean_parameters, budget,
    output_names=("contact_time",),
    output_units=("s",),
    method="linear",  # or "monte_carlo"
)
print(result.to_dict())
```

The supplied budget must be scientifically defensible and use consistent units.
Only listed input sources are included. See
[`docs/UNCERTAINTY_PROPAGATION.md`](docs/UNCERTAINTY_PROPAGATION.md) for the
mathematical conventions, contact-time workflow, report outputs and limits.
Run `python .\examples\uncertainty_propagation.py` for a synthetic API demo;
its values are not a prediction or uncertainty estimate for a real eclipse.


## Real Lunar Topography Integration (Phase 7.6)

EclipseKit can now read documented, uncompressed PDS3 lunar DEM `IMG` files
without loading a multi-gigabyte global image into memory. The first target is
the NASA LOLA/SELENE SLDEM2015 simple-cylindrical product. The reader checks
projection, east-positive longitude, body-fixed frame, spherical reference
radius, pixel geometry, sample type, binary record layout and file size. Its
metadata is retained in each limb-corrected contact.

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

The PDS `OFFSET`/reference-radius convention is converted to height above the
labelled sphere, so the reference radius is not added twice. The reader uses a
read-only memory map and bilinear interpolation. It does not download data,
reproject coordinates, transform between DE421/DE440 body-fixed frames, decode
JP2, or fill missing DEM cells. The current contact-to-selenographic mapping
remains the Phase 5 Meeus-style approximation; confirm frame compatibility
before treating a sampled height as a physical limb correction.

Validate a local source product with:

```powershell
eclipsekit-validate-topography `
  --image "data\SLDEM2015_128_60S_60N_000_360_FLOAT.IMG" `
  --label "data\SLDEM2015_128_60S_60N_000_360_FLOAT.LBL" `
  --expected-coordinate-system "MEAN EARTH/POLAR AXIS OF DE421"
```

The validator writes JSON and Markdown to `reports/phase7_6/`. The user's
Windows run on the downloaded SLDEM2015 product reported `PASS` with 9/9 sample
checks passing. A `PASS` is a label/storage/interpolation smoke check, not
independent validation of lunar topographic accuracy. SLDEM2015's published typical vertical accuracy is not
silently treated as a pointwise uncertainty. See
[`docs/LUNAR_TOPOGRAPHY_PDS3.md`](docs/LUNAR_TOPOGRAPHY_PDS3.md) for source
references, supported PDS fields, datum conversion, use instructions and
limitations. No NASA topography data are redistributed in the package.


### Phase 7.7 — Performance and scientific regression

Install the development extra, then run the deterministic scientific checks and
representative micro-benchmarks:

```powershell
python -m pip install -e ".[dev,limb]"
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

Save the first benchmark JSON as a machine-specific baseline. On the same
computer and Python runtime, compare a later run with `--baseline-json` and an
explicit slowdown allowance, for example `--max-slowdown-ratio 1.25`. Do not
compare results from dissimilar hardware or operating systems. For full live
DE440s path and corridor acceptance, run the existing `eclipsekit-validate`
command with explicit kernel and Earth-orientation settings; the Phase 7.7
regression CLI marks those live checks NOT RUN rather than inferring their setup.

See [`docs/PERFORMANCE_AND_REGRESSION.md`](docs/PERFORMANCE_AND_REGRESSION.md) for the Phase 7.7 benchmark protocol, reference checks, baseline policy, and scientific limitations.

## Phase 8 — scientific validation, data provenance and reproducibility

The Phase 8 validation tools build on the earlier independent-reference and
shadow-corridor work. They do not change the eclipse geometry or numerical
defaults.

Audit the configured reference data (manifests, local/global cases, Besselian
assets, corridor rows) and record SHA-256 fingerprints:

```powershell
eclipsekit-audit-references --validation-dir "data\validation" --output-dir "reports\phase8_2"
```

Audit the selected Earth-orientation source and time-scale assumptions:

```powershell
eclipsekit-eop-audit --mode builtin --at "2017-08-21T17:20:00Z"
```

For a file-hashed external IERS table use `--mode iers`; the active IERS table
must be present in the selected Skyfield cache. If Skyfield uses its complete
legacy external table trio, all three files are fingerprinted separately and
combined into a deterministic composite fingerprint. Built-in tables are scoped to the
recorded Skyfield version. Fixed ΔT is recorded as an explicit historical
assumption and is not equivalent to observed DUT1.

Run all scientific validation components together:

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

The unified status is conservative: every component must report `PASS` for the
overall report to be `PASS`. An unverified external EOP source or an explicit
fixed-ΔT assumption produces `PARTIAL`, not a false clean pass. The reports
fingerprint the inputs and document their scope; they do not claim universal
scientific certification. See:

- [`docs/PHASE8_2_REFERENCE_MATRIX.md`](docs/PHASE8_2_REFERENCE_MATRIX.md)
- [`docs/PHASE8_3_EOP_REPRODUCIBILITY.md`](docs/PHASE8_3_EOP_REPRODUCIBILITY.md)
- [`docs/PHASE8_4_UNIFIED_VALIDATION.md`](docs/PHASE8_4_UNIFIED_VALIDATION.md)

## Phase 9.1 — tiled lunar DEM access

PDS3 lunar DEMs remain read-only memory-mapped and now support a bounded LRU
cache of converted elevation tiles, rectangular window reads, and streaming
tile iteration. This allows workflows to process multi-gigabyte IMG products
without eagerly loading the full raster into a Python array.

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
        consume = tile.height_above_reference_m  # process one window at a time
```

The default cache is bounded to at most 16 MiB of float64 tile payload. Use
`cache_tiles=0` to disable it, `clear_tile_cache()` to release it, and
`cache_info()` to inspect hits/misses/evictions and memory use. The new
`LunarDEMWindow` arrays are independent read-only copies; missing cells remain
NaN. See [Phase 9.1 tiled DEM access](docs/PHASE9_1_TILED_DEM_ACCESS.md) for
bounds, limitations and a validation command.

Phase 9.2 adds PDS4/GeoTIFF/JP2 support. Coordinate-frame and spherical
reference-radius conversions are described in Phase 9.3 below; merely selecting
a DE440s ephemeris still does not automatically transform a DEM labelled in a
DE421 frame.

## Phase 9.2 — Multi-format lunar DEM readers

EclipseKit keeps the PDS3 SLDEM2015 reader as its built-in, dependency-light
path and adds additional readers through explicit format adapters:

- PDS4 `Array_2D_Image` labels with detached or attached binary arrays; the
  supported subset is regular 2-D, simple-cylindrical/equirectangular lunar
  grids with declared east-positive longitude, pixel registration, a spherical
  reference radius and an explicit sample interpretation (`height` or
  `radius`).
- GeoTIFF and JPEG 2000 through the optional Rasterio/GDAL backend. Install it
  with `python -m pip install -e ".[raster]"` (or `pip install "eclipsekit[raster]"`
  after a package release). The raster must be a north-up geographic grid, or
  a non-georeferenced JP2 must be supplied with explicit degree bounds.

GeoTIFF/JP2 inputs must declare or be supplied with `coordinate_system_name`,
`reference_radius_m`, `vertical_datum`, `value_interpretation` (`height` or
`radius`) and sample `value_unit`. This is intentional: a generic Earth CRS or
an unlabelled raster is not silently treated as a Moon-fixed DEM. The Phase 9.2
readers themselves do not apply datum conversion, reprojection, or DE421/DE440
frame transformation; the separate point-transform API is documented in Phase
9.3 below.

Python example for PDS4:

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

For GeoTIFF/JP2, pass the lunar provenance and value interpretation options.
A JP2 without geographic metadata also needs `--bounds WEST SOUTH EAST NORTH`
and `--coordinates-in-degrees`. A PASS confirms metadata and selected
interpolation samples only; it is not an independent vertical-accuracy
certification.


## Phase 9.3 — explicit lunar frame and vertical-datum transformations

Phase 9.3 adds a provenance-carrying point-coordinate transformation layer
without silently changing any DEM reader or raster. The built-in fixed rotation
implements the published DE440 principal-axes (`MOON_PA_DE440`) to DE421
mean-Earth/mean-rotation (`MOON_ME_DE421`) relation from Park et al. (2021),
Equation (19), using the passive right-handed rotation convention printed in
that paper. Its inverse maps DE421 ME coordinates to DE440 PA.

```python
from eclipsekit import (
    LunarCoordinateTransform,
    LunarReferenceSphereTransform,
    de421_me_to_de440_pa_transform,
)

# Example: transform a DE421 ME DEM point into the DE440 PA frame.
transform = LunarCoordinateTransform(
    frame_transform=de421_me_to_de440_pa_transform(),
    vertical_transform=LunarReferenceSphereTransform(
        source_reference_radius_m=1_737_400.0,
        target_reference_radius_m=1_737_400.0,
        source_vertical_datum="height above the DE421 ME 1,737,400 m sphere",
        target_vertical_datum="height above the DE440 PA 1,737,400 m sphere",
    ),
)
point = transform.transform_point(latitude_deg=14.25, longitude_deg=-72.5, height_m=-1200.0)
print(point.latitude_deg, point.longitude_deg, point.height_above_reference_m)
```

The vertical conversion preserves centre-of-Moon radius: `h_target = h_source +
R_source - R_target`. The coordinate transform accepts scalar values or
broadcast-compatible NumPy arrays. Longitude output is normalized to
`[-180, 180)` degrees. `eclipsekit-audit-lunar-frames` reconstructs the five
paired lunar-retroreflector XYZ coordinates printed in Table 1 of Park et al.
(2021) and writes JSON/Markdown reports:

```powershell
eclipsekit-audit-lunar-frames --output-dir "reports\phase9_3"
```

The audit is an implementation-consistency check against the reflector points
paired with the published fitted rotation; it is not an independent geodetic
validation. These APIs transform points only: they do not warp, resample, or
rewrite PDS3/PDS4/GeoTIFF/JP2 grids, do not model a lunar geoid or ellipsoidal
vertical datum, and do not replace time-dependent lunar orientation from
appropriate SPICE PCK/FK kernels. See
[Phase 9.3 design and limits](docs/PHASE9_3_LUNAR_FRAME_DATUM_TRANSFORMS.md).


## Independent lunar DEM control-point validation (Phase 9.4)

EclipseKit can compare a PDS3/PDS4/GeoTIFF/JP2 lunar DEM with a separately
curated control-point JSON file. The file must declare the source, coordinate
frame, planetocentric/east-positive coordinate convention, spherical reference
radius, value interpretation, vertical datum, and whether the observations are
independent of the DEM under test. A non-independent dataset is never reported
as an acceptance PASS. See `docs/PHASE9_4_LUNAR_DEM_CONTROL_POINTS.md` and the
synthetic-only schema example at `examples/lunar_control_points_template.json`.


## Phase 9.5 — frame-aware DEM query access

`TransformedLunarDEMModel` wraps any supported lunar DEM reader and presents a
virtual view in an explicitly selected target frame and spherical vertical
datum. Each target query is inverse-rotated into the source DEM frame, sampled
using the source reader's existing tile/window machinery, and converted to the
target reference radius. The source raster remains read-only and is never
reprojected, resampled, copied or rewritten.

The constructor requires the source product's exact coordinate-system label,
source radius and vertical datum to agree with the explicitly supplied
`LunarCoordinateTransform`. The caller must verify from authoritative product
documentation that the label maps to the transform's declared source frame;
EclipseKit does not infer frames from a kernel name. The resulting virtual
`product_info` reports target metadata and preserves the source product and
transform provenance, so it can be passed to the Phase 9.4 control-point
validator when the control observations already use the target frame/datum.

See [`docs/PHASE9_5_FRAME_AWARE_DEM_ACCESS.md`](docs/PHASE9_5_FRAME_AWARE_DEM_ACCESS.md)
and [`examples/lunar_dem_frame_adapter.py`](examples/lunar_dem_frame_adapter.py).


## Phase 9.6 — coverage-aware lunar DEM mosaic routing

`LunarDEMMosaicModel` composes multiple compatible lunar DEM readers as a
virtual query router. Every source must declare the same coordinate-system
label, vertical datum, and spherical reference radius. The mosaic routes a
point only to products whose declared rectangular coverage contains it.

```python
from eclipsekit import LunarDEMMosaicModel

mosaic = LunarDEMMosaicModel(
    [western_dem, eastern_dem],
    strategy="priority",  # or "finest" / "mean"
)
height_m = mosaic.predict_altitude_m(12.0, -45.0)
```

`priority` uses the first covering source in the supplied order. `finest`
selects the smallest declared positive ground resolution. `mean` returns the
unweighted arithmetic mean of all covering products and is not an
uncertainty-weighted fusion. A source error or NoData condition inside its
advertised coverage is reported rather than silently hidden by falling back to
another reader. A source with no axis-aligned coverage metadata (including a
rotated virtual view) requires an explicit `LunarDEMCoverage` override supplied
from independently established geometry.

This phase does not merge or rewrite raster files, reproject grids, blend
seams, prove horizontal co-registration, or certify DEM accuracy. Its tests
use synthetic providers to validate routing, coverage, compatibility checks,
error handling, and reader lifecycle. See
[`docs/PHASE9_6_LUNAR_DEM_MOSAIC.md`](docs/PHASE9_6_LUNAR_DEM_MOSAIC.md) and
[`examples/lunar_dem_mosaic.py`](examples/lunar_dem_mosaic.py).


## Phase 9.7 — lunar DEM mosaic overlap-consistency audit

`eclipsekit-audit-dem-mosaic` and `audit_lunar_dem_mosaic_overlaps()` compare
source elevations directly inside each pair's declared positive-area coverage
overlap. The audit samples a deterministic grid, reports `source_b - source_a`
residuals and bias/MAE/RMSE/median/P95/maximum metrics, and retains per-point
errors. Antimeridian and 0/360 longitude-branch overlaps are aligned without
splitting ordinary continuous overlap regions into artificial grid fragments.

The audit does not compare the selected Phase 9.6 mosaic result against a
source; it compares every original source pair directly. It never edits,
blends, shifts, resamples or reprojects source rasters. `NO_OVERLAP` pairs are
not sampled; an overall `NOT_COMPARABLE` result is returned when no pair has
an overlap. A `PASS` means only that sampled source-to-source differences are
within the chosen absolute tolerance, not that either product is absolutely
accurate or horizontally co-registered. The standalone CLI currently opens
PDS3 IMG/LBL sources using a version-1 JSON manifest; the Python API accepts
any readers supported by `LunarDEMMosaicModel`. See
[`docs/PHASE9_7_LUNAR_DEM_MOSAIC_OVERLAP_AUDIT.md`](docs/PHASE9_7_LUNAR_DEM_MOSAIC_OVERLAP_AUDIT.md)
and [`examples/lunar_dem_mosaic_overlap_manifest.template.json`](examples/lunar_dem_mosaic_overlap_manifest.template.json).


## Phase 11 — Advanced Eclipse Prediction Engine

`EclipseEngine.search_solar_eclipses(start, end, observers, ...)` searches a
UTC interval and evaluates every new-moon candidate separately at each supplied
`Observer`. A result groups the geocentric maximum with the locations where a
local eclipse was found, including each location's contacts and circumstances.
Local maxima are restricted to the requested interval and the search does not
fall forward to a later eclipse.

```python
from eclipsekit import EclipseEngine, Observer

engine = EclipseEngine("de440s")
locations = [
    Observer(44.4268, 26.1025, name="Bucharest"),
    Observer(40.4168, -3.7038, name="Madrid"),
]
search = engine.search_solar_eclipses(
    "2026-01-01", "2028-01-01", locations, min_magnitude=0.01
)
print(search.to_dict())
```

The API is intentionally explicit about spatial coverage: it only reports the
locations passed to it and does not imply visibility across the surrounding
region or globe. The default local search window is +/- 12 hours from
geocentric maximum (configurable up to 24 hours). Batch searches default to
excluding optional sunrise/sunset, shadow-metric, and planet calculations. See
[`docs/PHASE11_ADVANCED_ECLIPSE_PREDICTION.md`](docs/PHASE11_ADVANCED_ECLIPSE_PREDICTION.md)
and [`examples/solar_eclipse_interval_search.py`](examples/solar_eclipse_interval_search.py).


## Phase 12 — Advanced Geometry and Observation

Phase 12 adds `calculate_observation_geometry()` for arbitrary-time topocentric
Sun/Moon geometry and an optional caller-supplied `HorizonProfile` for skyline-aware
visibility. It also adds `calculate_shadow_footprint()` for an instantaneous
WGS84 central/penumbral shadow-cone footprint, plus GeoJSON linework exports.
Existing contact, corridor, and interval-search APIs remain available; horizon
profiles are opt-in. The footprint uses spherical solar/lunar radii and the WGS84
reference ellipsoid and is not a terrain-clipped map. See
[`docs/PHASE12_ADVANCED_GEOMETRY_OBSERVATION.md`](docs/PHASE12_ADVANCED_GEOMETRY_OBSERVATION.md)
for assumptions and examples.


## Phase 13 — Performance and Scalability

Phase 13 adds a streaming city-search API and precomputed country indexes for
repeated catalogue queries. `EclipseEngine.iter_search_cities()` yields each
hit as its bounded NumPy batch is processed and preserves catalogue order;
`search_cities()` continues to return a complete list sorted by magnitude, so
existing callers retain their previous result contract. `CityCatalog.iter_index_batches()`
yields read-only slices from the precomputed country index without allocating
a second full index array. `index_cache_info()` reports the country-index
cache's size.

```python
from eclipsekit import CityCatalog, EclipseEngine

catalog = CityCatalog.from_csv("CountryPoints.csv")
engine = EclipseEngine("de440s")

# Streaming: process hits as they arrive; no full result list is retained.
for hit in engine.iter_search_cities(
    "2026-08-12T17:00:00Z", catalog,
    country="Romania", batch_size=256,
):
    print(hit.city.name, hit.magnitude)

# Existing list API remains magnitude-sorted.
hits = engine.search_cities("2026-08-12T17:00:00Z", catalog, country="Romania")
print(catalog.index_cache_info())
```

`batch_size` bounds the city-by-time NumPy working set; lower values reduce
peak temporary memory at the cost of more batches. `iter_search_cities()` emits
hits in input catalogue order and is intended for streaming, not global ranking.
Use `search_cities()` when a complete magnitude-sorted collection is required.

The Phase 13 benchmark suite also compares cached country lookup with a full
scan and runs a deterministic serial-versus-four-thread NumPy batch workload.
In the development-container measurement, the country cache took about
0.0010 ms versus 0.0256 ms for a 2,048-row scan. The threaded synthetic workload
was slower (about 47.4 ms versus 25.0 ms serial), so no production thread-pool
option was added. This result is machine/workload-specific; rerun benchmarks on
the target machine before changing concurrency policy. Use:

```powershell
eclipsekit-benchmark --warmups 1 --repeats 5 --iterations 5 `
   --track-memory --output-dir reports/phase13 --stem scalability
```

See [`docs/PHASE13_PERFORMANCE_SCALABILITY.md`](docs/PHASE13_PERFORMANCE_SCALABILITY.md)
for the measurement protocol and memory/concurrency trade-offs.

## Phase 14 — Public API and Ecosystem

New integrations should import supported interfaces from `eclipsekit.api`.
The curated API exposes the engine/configuration models, observation and search
results, lunar-limb/DEM interfaces, validation helpers, benchmark records,
runtime diagnostics, strict JSON interchange and explicit third-party extension
loading. Existing `from eclipsekit import ...` imports remain supported.

```python
from eclipsekit.api import EclipseEngine, EclipseConfig, EphemerisConfig, Observer

engine = EclipseEngine(config=EclipseConfig(ephemeris=EphemerisConfig.jpl("de440s")))
result = engine.calculate_local(Observer(44.4268, 26.1025), "2026-08-12T17:00:00Z")
```

`API_CONTRACT_VERSION` identifies the stable curated Python interface; the distribution
version and individual report `schema_version` values remain separate.
`get_runtime_info()` reports runtime and optional dependency versions without
importing Torch or Rasterio. `write_json()` atomically writes strict interoperable
JSON and rejects unsupported/non-finite values. `discover_extensions()` reads
plugin metadata only; `load_extension()` imports a selected trusted factory
only when explicitly requested. See
[`docs/PUBLIC_API.md`](docs/PUBLIC_API.md),
[`docs/EXTENSIONS.md`](docs/EXTENSIONS.md) and
[`docs/API_MIGRATION.md`](docs/API_MIGRATION.md).

## Phase 15 — Scientific Certification and 1.0 release gate

EclipseKit now provides `eclipsekit-certify` to create a reproducible evidence
report before a major release. The audit checks the curated public API
manifest, source fingerprint, software tests and lint, wheel contents, existing
published reference regressions, the Phase 8.4 unified-validation report, real
PDS3 DEM structure, independent lunar DEM control-point reports and external
scientific review evidence.

The default `scientific` profile deliberately reports `NOT_CERTIFIED` when
independent evidence required for a scientific 1.0.0 release is missing. For a
software-only GitHub Alpha release, `eclipsekit-certify --release-profile alpha`
does not block on four future 1.0.0 requirements: stable API maturity,
independent lunar DEM control points, external scientific peer review and the
1.0.0 distribution version. These gates remain visible in the report as
`PARTIAL` or `NOT_RUN`; they are not converted into passes. The Alpha decision
is `ALPHA_RELEASE_READY`, while `scientific_certification_status` remains
`NOT_CERTIFIED`. Core software checks, published reference cases, Phase 8.4
unified validation and real PDS3 DEM structural/sample checks remain mandatory.
This permits a clearly labelled `0.1.0` Alpha software release without making
a scientific-certification claim.

The SLDEM2015 product's NASA/mission provenance and its passing structural and
sample checks are useful evidence about the input product. The separate
independent-control-point gate is a stronger accuracy-comparison requirement;
it is deferred for the Alpha profile, not represented as completed. The
reference fixtures include a NASA hybrid-eclipse greatest-time check; it does
not claim full local-contact or central-path validation for hybrid events.
Local `data`, DEMs, models, kernels, virtual environments, caches and reports
are excluded from source fingerprints and Phase overlays.

Install the extra tools, safely merge the new partial-eclipse reference into
your existing local validation manifest, and run the Phase 8.4 workflow before
the certification audit. The merge helper creates a backup and preserves all
existing records; the Phase 15 ZIP does not include or replace `data/`.

```powershell
python -m pip install -e ".[dev,limb,security]"
python scripts/merge_phase15_partial_reference.py
eclipsekit-validate --references data/validation/reference_cases.json `
  --path-manifest data/validation/path_reference_manifest.json `
  --besselian-reference data/validation/besselian_1999_reference.json `
  --kernel de440s --cache-dir "$env:LOCALAPPDATA\EclipseKit\kernels" `
  --json-out reports/phase15/references/reference-validation.json `
  --markdown-out reports/phase15/references/reference-validation.md
eclipsekit-validate-all --validation-dir data/validation --kernel de440s `
  --cache-dir "$env:LOCALAPPDATA\EclipseKit\kernels" `
  --output-dir reports/phase15/unified
eclipsekit-certify --validation-dir data/validation `
  --reference-report reports/phase15/references/reference-validation.json `
  --unified-report reports/phase15/unified/unified-validation.json `
  --dem-image data/SLDEM2015_128_60S_60N_000_360_FLOAT.IMG `
  --dem-label data/SLDEM2015_128_60S_60N_000_360_FLOAT.LBL `
  --expected-coordinate-system "MEAN EARTH/POLAR AXIS OF DE421" `
  --output-dir reports/phase15/certification-alpha --run-pip-audit --release-profile alpha
```

See [`docs/PHASE15_SCIENTIFIC_CERTIFICATION_1_0.md`](docs/PHASE15_SCIENTIFIC_CERTIFICATION_1_0.md)
for real DEM, independent control-point, peer-review and final-wheel instructions.
See [`docs/PHASE15_ALPHA_RELEASE.md`](docs/PHASE15_ALPHA_RELEASE.md) for the
Alpha profile and its explicit scientific-certification limits.
