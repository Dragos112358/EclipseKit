# Phase 9.5 — frame-aware lunar DEM query access

## Purpose

Phases 9.1–9.2 provide tiled/windowed native-frame readers for PDS3, PDS4,
GeoTIFF and JP2. Phase 9.3 defines explicit fixed frame and spherical-radius
point transforms. Phase 9.4 validates sampled DEM heights against declared
control observations. Phase 9.5 joins these capabilities at query time: a
`TransformedLunarDEMModel` presents an existing DEM in a caller-selected target
frame and spherical vertical datum without creating a second raster.

This is a **virtual query adapter**, not a raster reprojection. It keeps the
source DEM open and read-only, inverse-transforms each target query into the
source DEM frame, samples the native reader, then converts the sampled height
to the target spherical radius.

## Coordinate and height semantics

The supplied `LunarCoordinateTransform` must map source DEM coordinates to
the target coordinates exposed by the wrapper:

1. The caller requests a target-frame planetocentric latitude/longitude.
2. The adapter applies the inverse frame rotation to obtain source DEM
   latitude/longitude.
3. It calls the original DEM reader's `predict_altitude_m()` at that source
   location.
4. It applies the spherical radius conversion
   `h_target = h_source + R_source - R_target`.

The fixed rotation is a proper rotation and preserves centre-of-Moon radius;
the height shift is therefore independent of latitude and longitude for the
spherical datums supported by Phase 9.3.

## Strict metadata contract

Construction requires:

- a source object with `product_info` and `predict_altitude_m()`;
- a non-empty `source_coordinate_system_name` that matches the exact label in
  the source product metadata (whitespace/case-insensitive comparison only);
- source product `reference_radius_m` matching the transform's source radius;
- source product or model metadata `vertical_datum` matching the transform's
  source datum;
- an explicit `LunarCoordinateTransform` whose frame source/target and
  spherical source/target datums are the intended mapping.

The explicit source-label argument is a caller declaration, not automatic
frame identification. The caller must independently establish from the
product's authoritative label/documentation that its label corresponds to the
symbolic `frame_transform.source_frame`. EclipseKit does not infer DE421/DE440
frames from an ephemeris kernel name or from a partial label.

The wrapper's `product_info` reports the **target view** frame, vertical datum
and reference radius. Its nested `source_product_info` and
`coordinate_transform` preserve the underlying product metadata and transform
provenance. This makes the view usable with the Phase 9.4 control-point
validator when the control-point coordinates are already expressed in the
wrapper's target frame and datum.

## Python example

The following example is valid only when the source product documentation
confirms the DE421 mean-Earth/mean-rotation frame. Do not choose the factory
solely because a DE440 kernel is loaded by the eclipse engine.

```python
from eclipsekit import (
    LunarCoordinateTransform,
    LunarReferenceSphereTransform,
    TransformedLunarDEMModel,
    de421_me_to_de440_pa_transform,
    open_pds3_lunar_dem,
)

with open_pds3_lunar_dem(
    "data/SLDEM2015_128_60S_60N_000_360_FLOAT.IMG",
    "data/SLDEM2015_128_60S_60N_000_360_FLOAT.LBL",
    expected_coordinate_system="MEAN EARTH/POLAR AXIS OF DE421",
) as source_dem:
    transform = LunarCoordinateTransform(
        frame_transform=de421_me_to_de440_pa_transform(),
        vertical_transform=LunarReferenceSphereTransform(
            source_reference_radius_m=source_dem.product_info.reference_radius_m,
            target_reference_radius_m=1_737_400.0,
            source_vertical_datum=source_dem.metadata.vertical_datum,
            target_vertical_datum="radial height above the MOON_PA_DE440 1,737,400 m sphere",
        ),
    )
    target_dem = TransformedLunarDEMModel(
        source_dem,
        transform,
        source_coordinate_system_name=source_dem.product_info.coordinate_system_name,
    )
    print(target_dem.predict_altitude_m(12.0, -45.0))
    print(target_dem.product_info.to_dict())
    # target_dem.close() closes only the virtual view by default.
```

`predict_many(latitude_deg, longitude_deg)` accepts broadcast-compatible NumPy
inputs and returns an array of the broadcast shape. It performs one native DEM
sample per coordinate; repeated/local reads may benefit from the source
reader's existing tile cache.

`predict(query)` implements the provider-neutral lunar-limb interface and
retains the virtual model's target-frame provenance. The wrapper does not
manufacture a per-point uncertainty.

## Lifecycle

The adapter does not own the underlying reader by default. Closing the wrapper
marks only the virtual view as closed. Set `close_source=True` when constructing
it to make `close()` also close the source reader. Use the source reader's
context manager to control native file/memory-map lifetime explicitly.

## Tests and acceptance boundary

The unit tests cover inverse-query transformation, height-radius conversion,
NumPy broadcasting, product metadata validation, prediction provenance,
control-point-validator integration, invalid queries, and source-reader
lifecycle. All fixtures are synthetic. They establish implementation behaviour,
not external lunar DEM accuracy.

No product is automatically reprojected, mosaicked, copied or rewritten. This
adapter does not implement time-dependent lunar attitude, a lunar geoid,
triaxial ellipsoid conversions, horizontal co-registration, or independent
scientific validation. Those require their own metadata, kernels, and
reference datasets.
