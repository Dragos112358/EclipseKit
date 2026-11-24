# Phase 9.7 — Lunar DEM mosaic overlap-consistency audit

## Purpose

Phase 9.6 routes queries among compatible DEM products. Phase 9.7 adds a
repeatable diagnostic for the places where declared source footprints overlap.
It samples each original reader directly at the same deterministic grid points
and reports the vertical difference `source_b - source_a`.

This is a source-to-source consistency check. It does not use the mosaic's
`priority`, `finest`, or `mean` output as a reference, and it never changes a
source raster.

## API

```python
from eclipsekit import (
    LunarDEMMosaicModel,
    audit_lunar_dem_mosaic_overlaps,
    write_lunar_dem_mosaic_overlap_report,
)

mosaic = LunarDEMMosaicModel([west_dem, east_dem], strategy="priority")
report = audit_lunar_dem_mosaic_overlaps(
    mosaic,
    samples_per_axis=11,
    absolute_tolerance_m=100.0,
)
json_path, markdown_path = write_lunar_dem_mosaic_overlap_report(
    report, "reports/phase9_7"
)
```

Each source pair is compared over the positive-area intersection of its
explicit rectangular coverage. Longitude intervals are aligned on a continuous
360-degree branch so footprints crossing 0/360 or the antimeridian are handled
without splitting one ordinary overlap into artificial pieces. Duplicate
samples at equivalent 0/360 endpoints are removed.

The `samples_per_axis` parameter is an integer from 2 through 101. The grid
includes the overlap-region boundary and interior points. Each point is
compared against the absolute vertical-difference tolerance. Metrics include
signed bias (`B - A`), MAE, RMSE, median absolute difference, 95th percentile,
and maximum absolute difference. Per-point values and source-read errors are
retained in the report.

## Status semantics

- `PASS`: every sample in every compared source pair is finite and within the
  configured absolute tolerance.
- `FAIL`: at least one finite sample exceeds the tolerance and no source-read
  error occurred in the pair.
- `ERROR`: at least one source read or returned value failed at a sampled point.
  A successfully read value from the other source is still retained in the row.
- `NO_OVERLAP`: the pair has no positive-area declared coverage intersection;
  no source is sampled for that pair.
- `NOT_COMPARABLE`: no source pair had an overlap that could be sampled.

A non-overlapping pair does not turn an otherwise valid overlap audit into a
failure. If all pairs are adjacent but non-overlapping, the overall result is
`NOT_COMPARABLE`, not `PASS`.

## PDS3 command-line workflow

The standalone command reads PDS3 products from a version-1 JSON manifest.
Paths are absolute or relative to the manifest's directory. The product labels
must declare compatible coordinate-system names, vertical datums, and
spherical reference radii, as required by the Phase 9.6 mosaic.

Example manifest (`examples/lunar_dem_mosaic_overlap_manifest.template.json`):

```json
{
  "schema_version": 1,
  "name": "Regional overlap audit",
  "product_id": "regional-overlap-audit",
  "sources": [
    {
      "name": "west tile",
      "image_path": "../data/west.img",
      "label_path": "../data/west.lbl"
    },
    {
      "name": "east tile",
      "image_path": "../data/east.img",
      "label_path": "../data/east.lbl"
    }
  ]
}
```

If a source has no rectangular coverage in product metadata (for example, a
Phase 9.5 transformed view), an explicit `coverage` object with
`south_latitude_deg`, `north_latitude_deg`, `west_longitude_deg`, and
`east_longitude_deg` must be supplied. Such overrides must come from
independently established source geometry, not guesses.

```powershell
eclipsekit-audit-dem-mosaic `
  --manifest "examples\my_lunar_dem_overlap_manifest.json" `
  --samples-per-axis 11 `
  --tolerance-m 100 `
  --output-dir "reports\phase9_7"
```

The CLI currently opens PDS3 IMG/LBL products. The Python API accepts any
reader already usable with `LunarDEMMosaicModel`, including supported PDS4,
GeoTIFF, JP2 and transformed virtual readers.

## Interpretation and limitations

Matching product frame/datum/radius metadata is necessary but does not prove
horizontal co-registration. Differences can reflect vertical offsets,
resolution, interpolation, registration, source processing, or mismatched
horizontal geometry. Agreement does not establish absolute lunar elevation
accuracy. The regular sample grid is diagnostic, not exhaustive; it does not
compare every DEM pixel. Products without overlap require independent tie
points or a documented overlap strip if they are to be compared.

The audit does not blend, feather, adjust, shift, resample, reproject, or rewrite
any raster. It does not infer a correct product from a pairwise difference.
An apparent seam is reported, not repaired.
