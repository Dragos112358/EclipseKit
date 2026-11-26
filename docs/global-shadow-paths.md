---
description: Generate solar-eclipse global shadow paths and central shadow corridors with EclipseKit using JPL ephemerides and WGS84 geometry.
---

# Global solar-eclipse shadow paths and corridors

EclipseKit provides global shadow-geometry methods that sample the central and penumbral shadow cones against the WGS84 reference ellipsoid.

## Sample a shadow corridor

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

geojson = shadow_corridor_to_geojson(corridor)
write_geojson(geojson, "global-corridor.geojson")
write_shadow_corridor_csv(corridor, "global-corridor.csv")
write_shadow_corridor_kml(corridor, "global-corridor.kml")
```

For an event-centred search, the engine also provides `global_shadow_corridor_for_eclipse()`.

## What a corridor sample contains

Depending on valid intersections and boundary coverage, a sample can include:

- Central-axis location.
- Left and right central and penumbral boundaries.
- Central and penumbral cross-track widths.
- Along-track cone chords and a local bearing.
- Instantaneous central-axis ground speed.
- First-order phase-duration estimates.
- Boundary-hit coverage fractions.

Left and right are defined relative to the direction of travel, not as fixed north/south labels.

## Important limitations

The corridor model uses apparent Earth-fixed Sun and Moon centre vectors, spherical Sun/Moon radii and intersections with the WGS84 reference ellipsoid. It does not model lunar topography, atmospheric refraction, terrain height or terrain occultation.

The duration values in corridor samples are first-order estimates derived from along-track chords and instantaneous ground speed. They are not root-solved local C1–C4 contact times. Use `calculate_local()` for local contact calculations.

The method returns slices when the shadow axis intersects Earth; it does not represent the complete partial-eclipse penumbral footprint out to all sunrise/sunset limits.

## Validation example

The repository includes an end-to-end example comparing a small 2017 corridor sample with selected NASA/GSFC reference rows:

[examples/shadow_corridor_2017.py](https://github.com/Dragos112358/EclipseKit/blob/main/examples/shadow_corridor_2017.py)

See [Shadow Corridor V2](SHADOW_CORRIDOR_V2.md) for geometry, exports, reference data and interpretation details.
