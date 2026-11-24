# EclipseKit Configuration API — Phase 1

New applications should construct an immutable `EclipseConfig` and pass it to
`EclipseEngine(config=...)`. The previous constructor keywords are retained as
a compatibility bridge for the 0.1.0-alpha project.

```python
from eclipsekit import (
    EclipseEngine, EclipseConfig, EphemerisConfig, EarthOrientationConfig,
    ContactModelConfig, SolverConfig, AtmosphereConfig,
)

config = EclipseConfig(
    ephemeris=EphemerisConfig.jpl(
        "de440s", earth_orientation=EarthOrientationConfig.iers()
    ),
    contacts=ContactModelConfig(),
    solver=SolverConfig(root_tolerance_seconds=1e-5),
    atmosphere=AtmosphereConfig(refraction_enabled=True),
)
engine = EclipseEngine(config=config)
```

## Configuration groups

- `EphemerisConfig`: kernel/source, cache directory, optional body segment names,
  and Earth-orientation/time-scale source.
- `ContactModelConfig`: adopted solar and lunar radii used by the present
  spherical-disc contact model. This is not a lunar topography model.
- `SolverConfig`: bisection or safeguarded Brent-Dekker roots, golden-section
  minimum refinement, iteration limits, bracket expansion, and tangent-candidate
  detection. See `CONTACT_SOLVER_V2.md` for the detailed solver contract.
- `AtmosphereConfig`: pressure, temperature, and whether refraction is applied
  to reported apparent altitude/azimuth.
- `BesselianConfig`: Earth equatorial radius/flattening, local search window,
  maximum-refinement tolerance, and root-scan density for the independent
  published-element backend.

`EclipseConfig.to_dict()` returns a JSON-friendly summary of the active
assumptions. It intentionally does not serialize arbitrary Skyfield objects or
load external files.

## Backwards compatibility

These calls remain supported:

```python
EclipseEngine("de440s")
EclipseEngine("de440s", earth_orientation=EarthOrientationConfig.iers())
EclipseEngine("de440s", sun_radius_km=696000.0)
EclipseEngine.from_jpl("de440s")
```

Do not mix `config=` with legacy constructor overrides. A future major release
can remove the bridge after a deprecation period; it is not removed in this
milestone.

## Implemented in Contact Solver V2

The configuration now exposes Brent-Dekker root solving, automatic bracket
expansion limits, tangent-contact candidate detection, and diagnostic root
results. Full contact event metadata and the Besselian backend are now implemented.
DEM/Watts lunar-limb profiles and uncertainty propagation remain future
milestones.
