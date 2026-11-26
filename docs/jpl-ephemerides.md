---
description: Configure JPL planetary SPK/BSP ephemerides in EclipseKit using named kernels or local ephemeris files for reproducible eclipse calculations.
---

# JPL ephemerides and reproducibility

EclipseKit uses an explicitly selected ephemeris for calculations. The chosen kernel is part of the numerical configuration and should be recorded with any result or validation report.

## Select a named JPL kernel

```python
from eclipsekit import EclipseEngine

engine = EclipseEngine.from_jpl("de440s")
```

The examples also demonstrate named kernels such as `de432s`, `de440` and `de441`.

## Use a local SPK/BSP file

If you already have a supported local kernel file:

```python
from eclipsekit import EclipseEngine

engine = EclipseEngine("path/to/ephemeris.bsp")
```

Ensure that the file is accessible at the supplied path. Kernel size and coverage vary; a kernel must cover the event dates being calculated.

## Record the calculation environment

For reproducibility, record:

- EclipseKit version.
- Kernel name or local file identifier.
- Skyfield and NumPy versions.
- Observer coordinates and elevation.
- Time-scale and Earth-orientation configuration.
- Adopted radii, solver settings and any model overrides.

## Avoid mixing reference conventions

Two results for the same eclipse can differ because they use different ephemerides, Earth-orientation data, ΔT assumptions, body radii or published-reference conventions. When comparing with external predictions, record those assumptions rather than treating all published values as interchangeable.

Related pages:

- [Configuration API](CONFIGURATION_API.md)
- [Earth orientation and time scales](EARTH_ORIENTATION.md)
- [Data provenance](DATA_PROVENANCE.md)
- [Scientific validation](SCIENTIFIC_VALIDATION.md)
