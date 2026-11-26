---
description: EclipseKit is a Python toolkit for local solar and lunar eclipse calculations, C1–C4 contacts, global WGS84 shadow paths, Besselian methods and scientific validation.
---

# EclipseKit

**A Python toolkit for calculating, analysing, mapping and validating solar and lunar eclipses.**

EclipseKit brings reusable numerical eclipse-astronomy tools to Python applications, research workflows, notebooks and geospatial processing.

[Install from PyPI](https://pypi.org/project/eclipsekit/) ·
[GitHub repository](https://github.com/Dragos112358/EclipseKit) ·
[GitHub Discussions](https://github.com/Dragos112358/EclipseKit/discussions)

> **Alpha release:** The current published release is `0.1.0a1` (Alpha). Numerical results depend on the selected ephemeris, time-scale and Earth-orientation assumptions, adopted radii, solver settings and model conventions. Read the validation and limitations pages before using results in scientific or operational work.

## What can you do with EclipseKit?

### Local solar-eclipse calculations

Calculate local circumstances, maximum eclipse, magnitude, obscuration and C1–C4 contacts where applicable.

[Read the solar-eclipse calculator guide](solar-eclipse-calculator.md).

### Global shadow geometry

Sample central shadow paths and shadow corridors against the WGS84 reference ellipsoid, with GIS-oriented exports.

[Read the global shadow-path guide](global-shadow-paths.md).

### Lunar-eclipse calculations

Find geocentric lunar eclipses, calculate P1/U1/U2/maximum/U3/U4/P4 contacts and evaluate local visibility.

[Read the lunar-eclipse calculator guide](lunar-eclipse-calculator.md).

### Besselian methods

Evaluate explicitly supplied Besselian elements through an independent calculation backend.

[Read the Besselian calculations guide](besselian-calculations.md).

### JPL ephemerides

Configure named JPL kernels or a local SPK/BSP file for reproducible calculations.

[Read the JPL ephemerides guide](jpl-ephemerides.md).

### Scientific validation

Compare calculations with published reference cases and inspect tolerances, assumptions and known limitations.

[Read the validation and accuracy guide](validation-and-accuracy.md).

## Quick start

Install the current pre-release:

```bash
python -m pip install --pre eclipsekit
```

Calculate local circumstances for the 12 August 2026 total solar eclipse near León, Spain:

```python
from eclipsekit import EclipseEngine, Observer

engine = EclipseEngine.from_jpl("de440s")

observer = Observer(
    latitude=42.6,
    longitude=-5.5703,
    name="León",
)

result = engine.calculate_local(observer, "2026-08-12")

if result is not None:
    print(engine.format_report(result))
    print("C1:", result.contacts.c1)
    print("C2:", result.contacts.c2)
    print("C3:", result.contacts.c3)
    print("C4:", result.contacts.c4)
    print("Obscuration:", result.obscuration_percent)
else:
    print("No local eclipse was found in the search horizon.")
```

See [Installation and quick start](getting-started.md) for prerequisites, optional dependencies and validation commands.

## Main capabilities

| Area | Capabilities |
|---|---|
| Solar eclipses | Local circumstances, C1–C4 contacts, magnitude, obscuration, solar altitude and azimuth |
| Global geometry | Central shadow paths, central and penumbral corridors, WGS84 intersections |
| Lunar eclipses | Geocentric classification and P1/U1/U2/maximum/U3/U4/P4 contacts |
| Local lunar visibility | Moonrise/moonset clipping, refraction options and caller-supplied horizon profiles |
| Besselian backend | Local calculations, global maximum and central-line points from explicit published elements |
| Lunar topography | DEM readers/adapters, frame-aware access, mosaics and lunar-limb interfaces |
| Reproducibility | Explicit configurations, ephemerides, Earth-orientation assumptions and validation reports |

## Scientific scope

EclipseKit separates several calculation paths that should not be treated as interchangeable. For example, the direct ephemeris engine and the Besselian backend have different inputs and assumptions; global shadow-corridor samples are not the same as root-solved local C1–C4 contacts; and geocentric lunar contacts are distinct from topocentric visibility at an observing site.

The documentation states model assumptions and known limitations on the relevant pages. Passing software tests or a limited set of reference comparisons is not universal scientific certification.

## Project links

- [PyPI package and release files](https://pypi.org/project/eclipsekit/)
- [Source code on GitHub](https://github.com/Dragos112358/EclipseKit)
- [Examples](https://github.com/Dragos112358/EclipseKit/tree/main/examples)
- [Discussions and questions](https://github.com/Dragos112358/EclipseKit/discussions)
- [Issues and bug reports](https://github.com/Dragos112358/EclipseKit/issues)
- [Citation information](https://github.com/Dragos112358/EclipseKit/blob/main/CITATION.cff)
