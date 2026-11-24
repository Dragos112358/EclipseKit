# Phase 9.6 — coverage-aware lunar DEM mosaic routing

## Purpose

Phases 9.1–9.2 provide native tiled/windowed readers for PDS3, PDS4,
GeoTIFF and JP2. Phase 9.3 adds explicit fixed point-frame and spherical-datum
transforms, Phase 9.4 supplies an independent control-point validator, and
Phase 9.5 exposes a lazy target-frame query view. Phase 9.6 adds a virtual
multi-product DEM model which routes each query to one or more compatible
source readers using declared coverage metadata.

This is a **query-time source router**, not a raster merge, warp, reprojection,
or seam-correction algorithm. Source files remain separate and read-only.

## Compatibility contract

Every source must expose:

- `product_info.coordinate_system_name`;
- `product_info.reference_radius_m`;
- a vertical datum on `product_info.vertical_datum` or
  `model.metadata.vertical_datum`;
- `predict_altitude_m(latitude_deg, longitude_deg)`;
- rectangular latitude/longitude coverage in product metadata, or an explicit
  `LunarDEMCoverage` supplied by the caller.

All sources in one mosaic must use the same coordinate-system label, vertical
datum, and spherical reference radius. The constructor rejects mismatches. It
does not infer frame equivalence or convert between datums. Use
`TransformedLunarDEMModel` from Phase 9.5 first when the source products have
explicitly documented transforms. A transformed view may need an explicit
coverage override because its rotated coverage outline is not generally an
axis-aligned rectangle.

Coverage is inclusive at the bounds with a small numerical tolerance. A
longitude interval may cross the antimeridian by using a continuous branch,
for example `west=170, east=190`. A full 360-degree interval is global in
longitude.

## Strategies

`LunarDEMMosaicModel(..., strategy="priority")` samples only the first source
whose declared coverage contains the query. The given source order is the
priority order.

`strategy="finest"` samples the covering source with the smallest declared
`resolution_m`. Every source must provide a positive resolution; equal
resolutions are resolved by original source order.

`strategy="mean"` samples every covering source and returns the unweighted
arithmetic mean of the returned heights. It is not uncertainty-weighted, does
not estimate a new uncertainty, and should only be used when the products are
known to be compatible and averaging is scientifically appropriate.

The mosaic never catches a source's internal NoData or sampling error and
silently switches to another product. Coverage selection happens before
sampling. If a source fails within its declared coverage, the exception is
reported with the source name. This prevents missing cells, bad labels, or
corrupt data from being disguised as a valid fallback value.

## Python example

```python
from contextlib import ExitStack

from eclipsekit import LunarDEMMosaicModel, open_pds3_lunar_dem

with ExitStack() as stack:
    west = stack.enter_context(
        open_pds3_lunar_dem("west.img", "west.lbl")
    )
    east = stack.enter_context(
        open_pds3_lunar_dem("east.img", "east.lbl")
    )
    mosaic = LunarDEMMosaicModel(
        [west, east],
        strategy="priority",
        name="Regional SLDEM collection",
    )
    print(mosaic.predict_altitude_m(12.0, -45.0))
    print(mosaic.product_info.to_dict())
```

The two products in this example must independently document the same frame,
vertical datum, and reference radius. The coordinate query must be within at
least one product's declared coverage.

For a source whose product metadata does not expose a rectangular coverage
(e.g. a rotated virtual view), pass explicit per-source coverage:

```python
from eclipsekit import LunarDEMCoverage, LunarDEMMosaicModel

mosaic = LunarDEMMosaicModel(
    [target_frame_dem],
    coverage_overrides=[LunarDEMCoverage(-60.0, 60.0, 0.0, 360.0)],
)
```

The override is a caller assertion; it must be derived from the product's
coverage geometry after any coordinate transform. The example bounds above
are illustrative only, not a claim about any particular lunar product.

## Query and lifecycle APIs

- `predict_altitude_m(lat, lon)` returns a scalar target-datum height.
- `predict(LunarLimbQuery(...))` returns a provider-neutral prediction and
  includes the selected source name(s) in `prediction.source`.
- `predict_many(latitudes, longitudes)` accepts broadcast-compatible NumPy
  inputs and returns their broadcast shape.
- `product_info.to_dict()` exposes the common coordinate metadata and each
  source's coverage and product metadata.
- Source readers are not owned by default. `close_sources=True` transfers
  lifecycle ownership; otherwise close the original source readers separately.

## Limitations and validation boundary

- No raster merge, resampling, reprojection, feathering, or seam adjustment.
- Rectangular coverage routing only; complex polygon footprints need a more
  expressive future coverage model or a caller-supplied conservative extent.
- A query inside coverage but on a NoData cell is an error; the mosaic does not
  guess a replacement value.
- `mean` is an unweighted arithmetic mean and does not propagate uncertainty.
- Same-frame/same-datum/same-radius metadata is necessary but does not prove
  horizontal co-registration or independent scientific accuracy.
- Synthetic unit tests establish routing, validation, metadata, and lifecycle
  behaviour. They do not establish accuracy of any lunar DEM collection.
