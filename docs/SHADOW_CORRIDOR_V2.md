# Global Shadow Corridor V2

Phase 7.3 adds direct-engine sampling of the central (umbra/antumbra) and outer
penumbral cone boundaries against the WGS84 reference ellipsoid.

## API

```python
corridor = engine.global_shadow_corridor(
    "2017-08-21T17:00:00Z",
    "2017-08-21T19:00:00Z",
    samples=121,
    boundary_samples=144,
)

corridor = engine.global_shadow_corridor_for_eclipse(
    "2017-08-21T18:26:00Z",
    search_radius_hours=2.0,
    samples=121,
    boundary_samples=144,
)
```

Each `ShadowCorridorSample` contains the central-axis location; the left/right
central and penumbral boundaries; cross-track widths; along-track cone chords;
the instantaneous central-axis ground speed; first-order phase-duration
estimates; local bearing; and boundary-hit coverage fractions. Left/right is
defined relative to the direction of travel, not as a fixed north/south
designation. This is important for polar
tracks and when the path curves or reverses its geographic orientation.

`central_width_km` is the cross-track span between the central cone's two
WGS84 intersections. It represents the totality path width for an umbral event
or the annularity path width for an antumbral event. `penumbral_width_km` is the
outer penumbral span on the same time slice.

`central_track_chord_km` and `penumbral_track_chord_km` are the cone-boundary intersections with the local ground-track line through
the central-axis point. The duration
fields are first-order local estimates computed as the corresponding along-track
chord divided by instantaneous central-axis ground speed. They are not
root-solved local contact times and should not be presented with the precision
of C1-C4 from `calculate_local()`. The local track bearing is derived from a
short symmetric time difference around each sample, not from the spacing of the
requested samples; this avoids a large bearing bias when a sparse requested
track curves between samples.

## Geometry and limitations

The geometry uses apparent Earth-fixed Sun and Moon center vectors and spherical
Sun/Moon radii. The cone slopes are `(Rsun - Rmoon) / distance` for the central
umbra/antumbra boundary and `(Rsun + Rmoon) / distance` for the penumbral
boundary. Each cone generatrix starts at a point on the lunar limb and is
intersected with the WGS84 reference ellipsoid.

The method does not model lunar topography, atmospheric refraction, terrain
height, or terrain occultation. It returns time slices only when the shadow axis
intersects Earth; consequently it does not yet include the entire partial-eclipse
penumbral footprint out to all sunrise/sunset limits. Boundary coverage below
1.0 records that only part of a sampled cone ring intersected the ellipsoid.

This model is independent of the existing local topocentric contact solver but
shares the engine's selected ephemeris and Earth-orientation configuration. It
is a geometric approximation intended for path visualization and comparison,
not a substitute for published high-precision eclipse path tables.

## GIS exports

- `shadow_corridor_to_geojson()` returns the central axis, left/right limit lines,
and corridor polygons when complete side boundaries are available. Lines and
polygon rings are split at the antimeridian.
- `write_shadow_corridor_csv()` stores time, center, limits, widths, velocity,
duration estimates, along-track chords, local bearing and boundary coverage.
- `shadow_corridor_to_kml()` / `write_shadow_corridor_kml()` create a Google Earth
compatible KML document.

All GeoJSON coordinates follow RFC 7946 longitude/latitude order. CSV and KML
are UTF-8.

## Independent reference sample

`data/validation/global_corridor_2017_nasa.csv` contains three rows (17:00,
17:20, 17:40) transcribed from NASA/GSFC's 2017-08-21 total-eclipse path table.
The page publishes WGS 84 northern/southern limits, central-line coordinates,
path widths and central-line durations at two-minute intervals. The fixture
stores the three selected rows as decimal degrees and seconds; original
published coordinates are rounded to 0.1 arcminute. Its `time_utc` values
preserve the table's “Universal Time” labels; treat the time precision and clock
convention as part of the reference, not as sub-second truth.

Run the end-to-end comparison using the configured DE440s kernel:

```powershell
python .\examples\shadow_corridor_2017.py
```

The example writes GeoJSON, CSV, KML, and a Markdown validation report under
`reports/phase7_3/`. The selected 8 km / 10 s thresholds are explicit screening
tolerances for a small sparse check set, not a claim of global path accuracy.
A failed check is a real regression to investigate; the thresholds must not be
relaxed simply to produce a passing report.

Reference: https://eclipse.gsfc.nasa.gov/SEpath/SEpath2001/SE2017Aug21Tpath.html
