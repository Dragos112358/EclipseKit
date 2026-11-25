# EclipseKit

**A Python toolkit for calculating, analysing and validating solar and lunar eclipses.**

[![PyPI version](https://img.shields.io/pypi/v/eclipsekit)](https://pypi.org/project/eclipsekit/)
[![Python versions](https://img.shields.io/pypi/pyversions/eclipsekit)](https://pypi.org/project/eclipsekit/)
[![CI](https://github.com/Dragos112358/EclipseKit/actions/workflows/ci.yml/badge.svg)](https://github.com/Dragos112358/EclipseKit/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE.md)

EclipseKit provides a modular numerical engine for local eclipse circumstances, global shadow geometry, lunar-eclipse contacts and visibility, independent Besselian calculations, geospatial exports, and reproducible reference validation. It is designed to be used as a Python library as well as through command-line validation tools.

**Current release: `0.1.0a1` (Alpha)** · **Python 3.10+** · **License: Apache-2.0**

<p align="center">
  <a href="https://pypi.org/project/eclipsekit/">PyPI project</a> ·
  <a href="https://pypi.org/project/eclipsekit/0.1.0a1/#files">Download release files</a> ·
  <a href="https://github.com/Dragos112358/EclipseKit">Source code</a> ·
  <a href="https://github.com/Dragos112358/EclipseKit/issues">Report an issue</a>
</p>

---

## Install EclipseKit

EclipseKit is published on **PyPI**. The recommended installation is:

```bash
python -m pip install --pre eclipsekit
```

The `--pre` option tells pip to include pre-releases such as the current Alpha version. To install this exact release:

```bash
python -m pip install eclipsekit==0.1.0a1
```

### Download the library files

The PyPI release page provides both distributable formats:

- **[Download the wheel (`.whl`) and install it with pip](https://pypi.org/project/eclipsekit/0.1.0a1/#files)** — recommended for most users.
- **[Download the source archive (`.tar.gz`)](https://pypi.org/project/eclipsekit/0.1.0a1/#files)** — for inspecting or building from source.

The wheel is a platform-independent Python distribution (`py3-none-any`). The package requires Python 3.10 or newer and installs its required NumPy and Skyfield dependencies automatically.

### Optional features

Install optional dependencies only when you need the corresponding functionality:

```bash
# Rasterio/GDAL-backed GeoTIFF and JPEG 2000 lunar DEM readers
python -m pip install --pre "eclipsekit[raster]"

# Neural lunar-limb integration (installs PyTorch; no model checkpoint included)
python -m pip install --pre "eclipsekit[limb]"
```

For development and testing, clone the repository and install the development extra; see [Development](#development).

---

## Quick start

This example calculates the local circumstances of the **12 August 2026 total solar eclipse** near León, Spain:

```python
from eclipsekit import EclipseEngine, Observer

# The first use of a named JPL kernel may download it into the EclipseKit cache.
engine = EclipseEngine.from_jpl("de440s")
observer = Observer(42.6, -5.5703, name="León")

result = engine.calculate_local(observer, "2026-08-12")

if result is None:
    print("No local eclipse was found.")
else:
    print(engine.format_report(result))
```

A successful calculation returns structured data that can be inspected in Python or serialized with `result.to_dict()`.

### Example output

The following is an actual smoke-test result from the published PyPI installation, using Python 3.12 and JPL DE440s for the León observer coordinates above. Small numerical differences can occur when the ephemeris, time-scale data, software versions or model assumptions differ.

```text
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

Check the installed package and its command-line interface:

```bash
python -m pip show eclipsekit
eclipsekit-validate --help
```

---

## Main capabilities

### Solar-eclipse circumstances

- Calculate local C1–C4 contacts, greatest local eclipse, magnitude and disc-overlap obscuration.
- Return solar altitude and azimuth, shadow information and optional sunrise/sunset or visible-planet information.
- Search intervals and evaluate multiple explicitly supplied observing locations.
- Keep local circumstances separate from geocentric greatest-eclipse calculations.

### Global shadow geometry and GIS

- Calculate the direct ephemeris-based shadow axis against the WGS84 reference ellipsoid.
- Generate central-axis paths and Phase 7.3 central/penumbral corridor geometry.
- Export supported results to GeoJSON, CSV and KML for use in GIS software such as QGIS.
- Compare configured path subsets against published reference tables.

### Lunar-eclipse calculations and local visibility

- Classify penumbral, partial and total lunar eclipses using the default Herald–Sinnott oblate-Earth shadow prescription.
- Solve P1, U1, U2, greatest eclipse, U3, U4 and P4 contacts where applicable.
- Report UTC, UT1 and TT separately and make time-scale assumptions explicit.
- Calculate topocentric visibility intervals, accounting for observer elevation, optional atmospheric refraction, horizon profiles, moonrise and moonset.

### Independent Besselian backend

- Load explicitly supplied published Besselian elements.
- Calculate local C1–C4 circumstances, greatest eclipse and central-line positions.
- Keep the Besselian calculation path separate from the active JPL-kernel engine so the two approaches can be compared transparently.

### Lunar topography and limb framework

- Provide spherical, gridded-DEM and tabulated apparent-limb interfaces, with an optional neural-model adapter.
- Read supported PDS3/PDS4 lunar DEM products; GeoTIFF and JPEG 2000 support is available through the optional Rasterio extra.
- Support explicit lunar frame and reference-sphere transformations, frame-aware DEM access and coverage-aware DEM mosaics.
- Keep source data read-only and expose provenance and assumptions rather than silently inferring coordinate frames or vertical datums.

### Other tools

- Search user-supplied city catalogues with vectorized processing and streaming results.
- Compare observing sites with the observation planner.
- Propagate explicitly supplied parameter uncertainties through user-provided models.
- Produce reference-validation, regression, performance, Earth-orientation and certification reports.
- Expose a curated typed API through `eclipsekit.api`, while retaining package-root imports for compatibility.

See the [documentation index](#documentation) for detailed guides, model assumptions and examples.

---

## Ephemerides and time scales

EclipseKit uses Skyfield and JPL BSP/SPK ephemerides. You can select a named kernel or provide a local kernel path:

```python
from eclipsekit import EclipseEngine

engine = EclipseEngine.from_jpl("de440s")
# Or use a local BSP file:
engine_local = EclipseEngine.from_jpl(r"D:/Astronomy/kernels/de440s.bsp")
```

Common named kernels include `de432s`, `de440s`, `de440` and `de441`. Large kernels are not bundled in the wheel. A named kernel may be downloaded on first use and cached locally; a local BSP path can be used when you need to manage the ephemeris file yourself. Importing `eclipsekit` alone does not download ephemerides or initialize optional models.

The default time-scale mode uses Skyfield's bundled tables. For modern operational work, the API also exposes IERS Earth-orientation data; an explicit fixed-ΔT mode is available for reproducing a particular historical reference convention. Fixed ΔT is not a substitute for observed Earth-orientation data. Always record the kernel, time-scale mode, ΔT/EOP source, observer coordinates, and relevant radii when comparing predictions.

Configuration objects are recommended for new applications:

```python
from eclipsekit import (
    EclipseConfig,
    EclipseEngine,
    EphemerisConfig,
    EarthOrientationConfig,
    Observer,
)

config = EclipseConfig(
    ephemeris=EphemerisConfig.jpl(
        "de440s",
        earth_orientation=EarthOrientationConfig.iers(),
    ),
)
engine = EclipseEngine(config=config)
result = engine.calculate_local(Observer(44.4268, 26.1025), "2026-08-12")
```

For the full configuration surface, see [`docs/PUBLIC_API.md`](docs/PUBLIC_API.md), [`docs/API_MIGRATION.md`](docs/API_MIGRATION.md) and [`docs/CONTACT_SOLVER_V2.md`](docs/CONTACT_SOLVER_V2.md).

---

## Validation results for `0.1.0a1`

The published wheel was installed from the official PyPI index into a clean Python 3.12 virtual environment. Imports, the `eclipsekit-validate` entry point and `pip check` were verified. The direct API smoke test shown above also completed successfully.

The full bundled reference-validation suite was run from the repository root using **Python 3.12.10**, **Windows 11**, **JPL DE440s**, **Skyfield 1.55**, Skyfield's bundled time-scale data and 301 samples for the global-path comparisons.

<details open>
<summary><strong>Full validation summary: 11 of 11 acceptance cases passed</strong></summary>

| Validation group | Result | Notes |
|---|---:|---|
| Local circumstances and geocentric maxima | **6/6 PASS** | Four local solar-eclipse cases and two geocentric maximum cases |
| NASA central-line path comparisons | **4/4 PASS** | Seven reference points per path subset |
| NASA 1999 Besselian regression | **PASS** | Epoch, central-line position, eclipse type, duration and local contacts |
| **Total** | **11/11 PASS** | **0 failures, 0 execution errors** |

Maximum path residuals reported by the run:

| Reference event | Maximum error | Configured limit |
|---|---:|---:|
| 21 August 2017 | 0.4795 km | 5 km |
| 2 July 2019 | 2.1685 km | 5 km |
| 21 June 2020 | 1.4362 km | 5 km |
| 12 August 2026 | 4.6340 km | 15 km |

The NASA 1999 Besselian checks reported a greatest-eclipse epoch difference of −0.0418 s, central-line position error of 0.0303 km and central-duration difference of −0.0487 s. The direct-engine-versus-Besselian contact comparison is separately labelled diagnostic and has no pass/fail threshold.

</details>

### Reproduce the validation run

Run this command **from the repository root**, where the curated fixtures under `data/validation/` are present:

```powershell
eclipsekit-validate `
  --kernel de440s `
  --cache-dir "$env:LOCALAPPDATA\EclipseKit\kernels" `
  --path-samples 301 `
  --json-out reports/pypi-full-validation.json `
  --markdown-out reports/pypi-full-validation.md
```

The command writes machine-readable JSON and a Markdown report. The `eclipsekit-validate` executable is installed with the package, but the reference fixtures are repository/source-tree assets and are not bundled into the wheel. For validation, use a repository checkout or source archive that contains `data/validation/`.

**Scientific scope:** a `PASS` applies only to the named fixtures, their source precision, configured tolerances, the selected ephemeris and time-scale assumptions. Sparse path points do not validate every path boundary or shadow-width output. These results are not a universal accuracy guarantee, external peer review, or scientific certification. Neural lunar-limb corrections and every supported DEM product require their own independent evidence.

More details: [`docs/SCIENTIFIC_VALIDATION.md`](docs/SCIENTIFIC_VALIDATION.md), [`docs/VALIDATION_FRAMEWORK.md`](docs/VALIDATION_FRAMEWORK.md), [`docs/PHASE8_4_UNIFIED_VALIDATION.md`](docs/PHASE8_4_UNIFIED_VALIDATION.md) and [`docs/PHASE15_ALPHA_RELEASE.md`](docs/PHASE15_ALPHA_RELEASE.md).

---

## Documentation

| Topic | Guide |
|---|---|
| Lunar eclipses, contacts and local visibility | [`docs/LUNAR_ECLIPSES.md`](docs/LUNAR_ECLIPSES.md), [`docs/LUNAR_ECLIPSE_METHODOLOGY.md`](docs/LUNAR_ECLIPSE_METHODOLOGY.md) |
| Solar-eclipse contacts and solver behaviour | [`docs/CONTACT_SOLVER_V2.md`](docs/CONTACT_SOLVER_V2.md), [`docs/CONTACT_EVENT_MODEL.md`](docs/CONTACT_EVENT_MODEL.md) |
| Independent Besselian calculations | [`docs/BESSELIAN_BACKEND.md`](docs/BESSELIAN_BACKEND.md) |
| Lunar-limb interfaces and topography | [`docs/LUNAR_LIMB_FRAMEWORK.md`](docs/LUNAR_LIMB_FRAMEWORK.md), [`docs/LUNAR_TOPOGRAPHY_PDS3.md`](docs/LUNAR_TOPOGRAPHY_PDS3.md) |
| Lunar coordinate frames and DEM adapters | [`docs/PHASE9_3_LUNAR_FRAME_DATUM_TRANSFORMS.md`](docs/PHASE9_3_LUNAR_FRAME_DATUM_TRANSFORMS.md), [`docs/PHASE9_5_FRAME_AWARE_DEM_ACCESS.md`](docs/PHASE9_5_FRAME_AWARE_DEM_ACCESS.md), [`docs/PHASE9_6_LUNAR_DEM_MOSAIC.md`](docs/PHASE9_6_LUNAR_DEM_MOSAIC.md) |
| Global shadow paths and corridors | [`docs/SHADOW_CORRIDOR_V2.md`](docs/SHADOW_CORRIDOR_V2.md), [`docs/PHASE8_1_CORRIDOR_VALIDATION.md`](docs/PHASE8_1_CORRIDOR_VALIDATION.md) |
| Public API and extension loading | [`docs/PUBLIC_API.md`](docs/PUBLIC_API.md), [`docs/EXTENSIONS.md`](docs/EXTENSIONS.md), [`docs/API_MIGRATION.md`](docs/API_MIGRATION.md) |
| Observation planning and uncertainty | [`docs/OBSERVATION_PLANNER.md`](docs/OBSERVATION_PLANNER.md), [`docs/UNCERTAINTY_PROPAGATION.md`](docs/UNCERTAINTY_PROPAGATION.md) |
| Validation and reproducibility | [`docs/SCIENTIFIC_VALIDATION.md`](docs/SCIENTIFIC_VALIDATION.md), [`docs/VALIDATION_FRAMEWORK.md`](docs/VALIDATION_FRAMEWORK.md), [`docs/PHASE8_3_EOP_REPRODUCIBILITY.md`](docs/PHASE8_3_EOP_REPRODUCIBILITY.md) |
| Performance and benchmarks | [`docs/PERFORMANCE_AND_REGRESSION.md`](docs/PERFORMANCE_AND_REGRESSION.md), [`docs/PHASE13_PERFORMANCE_SCALABILITY.md`](docs/PHASE13_PERFORMANCE_SCALABILITY.md) |
| Alpha release scope and 1.0 gate | [`docs/PHASE15_ALPHA_RELEASE.md`](docs/PHASE15_ALPHA_RELEASE.md), [`docs/PHASE15_SCIENTIFIC_CERTIFICATION_1_0.md`](docs/PHASE15_SCIENTIFIC_CERTIFICATION_1_0.md) |
| Data and model provenance | [`docs/DATA_PROVENANCE.md`](docs/DATA_PROVENANCE.md) |

Runnable examples are available in [`examples/`](examples/). The [`CHANGELOG.md`](CHANGELOG.md) records project changes.

---

## Development

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

Install the project in editable mode with development tools and run the checks:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m ruff check src tests examples scripts
python -m compileall -q src tests examples scripts
python -m pytest -q
python -m build
```

The GitHub Actions CI workflow is configured for Python 3.10, 3.11 and 3.12 on Ubuntu, Windows and macOS. It runs lint, compilation, tests, wheel building, typing-marker verification and a dependency vulnerability audit.

Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) before submitting changes. Bug reports and feature requests belong in [GitHub Issues](https://github.com/Dragos112358/EclipseKit/issues).

---

## Data, kernels and optional models

EclipseKit deliberately keeps large and externally licensed data out of the PyPI wheel. In particular, the package does not bundle JPL BSP kernels, city catalogues, lunar DEM rasters or neural-model checkpoints.

- Obtain JPL ephemerides from the appropriate official NAIF/JPL distribution and retain the kernel/version used for each calculation.
- Supply your own city catalogue to `CityCatalog.from_csv()`; the development catalogue is not included in the public package.
- Supply lunar DEM data with documented source, coordinate frame, reference radius and vertical datum.
- The optional neural lunar-limb adapter requires a separately obtained checkpoint. Installing the `[limb]` extra installs PyTorch but does not download or provide model weights.

See [`docs/DATA_PROVENANCE.md`](docs/DATA_PROVENANCE.md) before redistributing third-party data or model assets.

---

## Scientific status and limitations

EclipseKit `0.1.0a1` is an **Alpha software release**. It is suitable for development, reproducible experimentation and evaluation against the documented reference fixtures. Do not interpret a passing test suite as proof that every feature, location, epoch or physical model is independently validated.

Some capabilities have narrower evidence than others. In particular:

- city searches depend on the coverage and accuracy of the caller-supplied catalogue;
- global path fixtures are sparse and do not establish universal accuracy for path boundaries, width, velocity or duration;
- the 87 km layer in the Herald–Sinnott lunar shadow model is an empirical prescription, not a resolved atmospheric-opacity model;
- lunar-limb and neural corrections require independent, documented profile/contact benchmarks;
- DEM format and sample checks are not the same as independent validation of absolute topographic accuracy;
- results depend on ephemeris, Earth-orientation data, ΔT, radius conventions, observer coordinates and solver settings.

The project keeps these limits explicit. The scientific-certification profile for a future 1.0.0 release has additional requirements, including independent lunar DEM control points and external scientific review. See [`docs/PHASE15_ALPHA_RELEASE.md`](docs/PHASE15_ALPHA_RELEASE.md).

---

## License and citation

EclipseKit is distributed under the **Apache License 2.0**. See [`LICENSE.md`](LICENSE.md) and [`NOTICE`](NOTICE). Third-party datasets, kernels and model weights may have separate terms; the project licence does not grant redistribution rights to those assets.

For citation metadata, see [`CITATION.cff`](CITATION.cff). For security-related reports, see [`SECURITY.md`](SECURITY.md).

---

<p align="center">
  <strong>Install</strong> · <a href="https://pypi.org/project/eclipsekit/">PyPI</a> ·
  <strong>Download</strong> · <a href="https://pypi.org/project/eclipsekit/0.1.0a1/#files">Release files</a> ·
  <strong>Contribute</strong> · <a href="https://github.com/Dragos112358/EclipseKit">GitHub</a>
</p>
