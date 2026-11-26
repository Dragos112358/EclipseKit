---
description: Install EclipseKit from PyPI, select an ephemeris, calculate a first solar eclipse and run the bundled validation command.
---

# Installation and quick start

## Requirements

- Python 3.10 or newer.
- An internet connection on first use when a named JPL kernel or an external Earth-orientation file must be downloaded.
- Enough disk space for the selected ephemeris and optional scientific datasets.

## Install from PyPI

The current published version is an Alpha pre-release. Install pre-releases with:

```bash
python -m pip install --pre eclipsekit
```

To request the release documented by this site explicitly:

```bash
python -m pip install eclipsekit==0.1.0a1
```

Check the installed distribution and dependencies:

```bash
python -m pip show eclipsekit
python -m pip check
```

## Optional dependencies

The core installation does not install every raster or neural-model dependency.

```bash
# Optional Rasterio/GDAL-backed raster adapters
python -m pip install --pre "eclipsekit[raster]"

# Optional PyTorch-based lunar-limb integration
python -m pip install --pre "eclipsekit[limb]"
```

The limb extra installs PyTorch; it does not download model weights.

## First solar-eclipse calculation

```python
from eclipsekit import EclipseEngine, Observer

engine = EclipseEngine.from_jpl("de440s")

observer = Observer(
    latitude=42.6,
    longitude=-5.5703,
    name="León, Spain",
)

result = engine.calculate_local(observer, "2026-08-12")

if result is not None:
    print(engine.format_report(result))
else:
    print("No local eclipse was found.")
```

The observer latitude and longitude are in degrees. Elevation, when supplied, is in metres.

## Command-line validation

The package provides a reference-validation command:

```bash
eclipsekit-validate --help
```

For the full reference-validation workflow, assumptions and result semantics, see [Scientific validation](SCIENTIFIC_VALIDATION.md) and [Validation framework](VALIDATION_FRAMEWORK.md).

## More examples

The repository includes runnable examples for local solar eclipses, lunar eclipses, Besselian calculations, shadow corridors, GIS exports and the curated public API:

[Browse the examples directory](https://github.com/Dragos112358/EclipseKit/tree/main/examples).
