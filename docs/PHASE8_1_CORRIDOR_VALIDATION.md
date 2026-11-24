# Phase 8.1 — Reproducible Shadow-Corridor Validation

Phase 8.1 adds a supported command-line entry point around the existing
independent corridor-reference validator and adds multi-resolution sampling
convergence diagnostics. It does not change the corridor geometry or relax the
Phase 7.3 NASA screening tolerances.

## Command

```powershell
eclipsekit-validate-corridor `
  --kernel de440s `
  --start "2017-08-21T17:00:00Z" `
  --end "2017-08-21T17:40:00Z" `
  --reference "data/validation/global_corridor_2017_nasa.csv" `
  --convergence-samples "3,11,21,51,101" `
  --boundary-samples 144 `
  --time-scale-mode builtin `
  --output-dir "reports/phase8_1"
```

The resolution list must be strictly increasing and nested. For example,
`3,11,21,51,101` is nested because each coarse time grid is a subset of the
101-point grid. Each resolution is evaluated by the same engine and selected
Earth-orientation configuration. The finest run is used for the NASA reference
comparison and GIS exports. The convergence diagnostic compares aggregate
centerline length, width, first-order duration and boundary-coverage metrics
across these runs, so it can reveal sensitivity to time-sampling density. It
does not perform point-by-point comparisons between resolutions.

## Outputs

The default stem is `shadow-corridor-2017`; the command writes:

- `shadow-corridor-2017.json` — inputs, engine/kernel/time-scale metadata,
  reference comparisons, convergence diagnostics and corridor samples;
- `shadow-corridor-2017.md` — human-readable report;
- `shadow-corridor-2017.geojson` — central axis and corridor boundaries;
- `shadow-corridor-2017.csv` — sample-level numerical values;
- `shadow-corridor-2017.kml` — Google Earth export.

If the computed corridor contains fewer than two valid samples, the JSON and
Markdown reports are still written, but GIS exports are omitted.

## Interpretation

The reference validator compares the central axis, both central boundaries,
central width and first-order central-duration estimate against the supplied
reference rows. Left/right edges are paired to north/south reference limits by
minimum total geodesic error.

The convergence section compares aggregate lower-resolution metrics with the
finest requested run. It is a numerical sampling-sensitivity diagnostic only.
The finest run is not treated as independent truth, and convergence does not
establish physical accuracy.

The current corridor model continues to use apparent Earth-fixed Sun/Moon
vectors, spherical Sun/Moon radii and intersections with the WGS84 reference
ellipsoid. It does not include terrain, atmospheric refraction, observer
horizon, lunar-limb relief, or the complete penumbral sunrise/sunset footprint.

The existing NASA fixture contains three selected 2017 reference epochs. A
PASS therefore applies to those rows and configured tolerances only; it is not
full certification of the complete corridor or its boundaries.

## Data

No large DEM, ephemeris kernel, model checkpoint or private catalogue is
included. The command expects the existing small reference file at
`data/validation/global_corridor_2017_nasa.csv` from the user's local project.
