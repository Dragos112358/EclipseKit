# Phase 12 — Advanced Geometry and Observation

Phase 12 extends (rather than replaces) the existing C1–C4 contact solver,
local circumstances, central shadow path, and sampled shadow corridor.

## 12.1 Instantaneous global shadow footprint

`EclipseEngine.calculate_shadow_footprint(when, boundary_samples=180)` computes
the central and penumbral shadow-cone generatrices at one instant and
intersects them with the WGS84 reference ellipsoid. The result includes:

- central-axis intersection when the axis itself reaches WGS84;
- signed cone radius and umbral/antumbral classification when the axis hits;
- ordered central and penumbral boundary samples;
- explicit `None` entries for rays that do not intersect the ellipsoid;
- boundary coverage fractions, track bearing, approximate ground speed and
  cross-track width when the central axis is available.

The method returns `None` when no sampled penumbral ray intersects WGS84. A
penumbral footprint can therefore be returned even when the central axis
misses the ellipsoid; its `shadow_kind` is then `axis_misses_earth`. The angular
sample count is bounded to 8–4096.

`shadow_footprint_to_geojson()` and `write_shadow_footprint_geojson()` export
the axis point and boundary linework. The exporter deliberately does not close
partial boundaries into polygons and does not bridge missing samples. Lines
are split at the antimeridian.

## 12.2 Detailed local observation geometry and skyline visibility

`EclipseEngine.calculate_observation_geometry(observer, when, ...)` provides
an arbitrary-time topocentric snapshot containing apparent Sun and Moon
altitude/azimuth, angular radii, separation, position angle, parallactic and
vertex angles, eclipse magnitude, obscuration, and horizon clearances.

Without a supplied profile, the astronomical horizon (0 degrees) is used.
`HorizonProfile` accepts azimuth/altitude pairs in degrees and interpolates
linearly, including across the 0/360-degree seam. The upper and lower solar
limb clearances determine one of three visibility statuses:

- `visible`: the full solar disk is above the supplied skyline;
- `partially_obstructed`: the skyline intersects the solar disk;
- `obstructed`: the entire solar disk is below the skyline.

`calculate_local(..., horizon_profile=...)` applies the same mask to C1, C2,
maximum, C3 and C4 event visibility metadata and attaches the detailed maximum
snapshot to `LocalEclipseResult`. The option defaults to `None`; existing calls
retain the previous above/at/below-horizon statuses.

A horizon profile is supplied by the caller, typically from a measured skyline
or survey. EclipseKit does not derive terrain, trees, buildings, atmospheric
extinction, diffraction or local weather from it. Refraction can be disabled
explicitly in `calculate_observation_geometry`; otherwise the engine's
configured pressure and temperature are used for apparent altitude/azimuth.

## Examples

Detailed local geometry:

```powershell
python examples/advanced_observation_geometry.py `
  --kernel de440s `
  --date 2026-08-12T17:00:00Z `
  --latitude 44.4268 `
  --longitude 26.1025 `
  --horizon-profile examples/horizon_profile.template.json `
  --output reports/phase12-observation.json
```

Instantaneous global footprint:

```powershell
python examples/shadow_footprint.py `
  --kernel de440s `
  --date 2026-08-12T17:00:00Z `
  --boundary-samples 180 `
  --output reports/phase12-shadow-footprint.geojson
```

## Scientific scope and limitations

These additions use the selected ephemeris kernel, spherical Sun/Moon radii,
apparent Earth-fixed vectors and the WGS84 reference ellipsoid. The shadow
footprint is a geometric cone/ellipsoid product, not a terrain-clipped eclipse
map. The track bearing and velocity are finite-difference estimates; the
cross-track width inherits the existing first-order shadow-kinematics model.
The local horizon feature applies a supplied angular skyline mask and does not
model the finite extent of terrain or atmospheric variability. Contact solver
residuals and the geometric outputs are not estimates of physical prediction
uncertainty. NASA reference-regression checks remain the relevant existing
regression guard; a new independent end-to-end scientific certification is not
claimed by synthetic unit tests.
