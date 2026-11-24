# Phase 9.4 — Independent lunar DEM control-point validation

## Purpose

Phases 9.1–9.3 added bounded multi-format DEM sampling and explicit point
coordinate/frame/radius transformations. Phase 9.4 adds a reproducible way to
compare a DEM's interpolated surface heights with a separately curated set of
lunar control observations.

This is a **point-height validation** workflow, not a raster reprojection or
full-product quality certification. EclipseKit does not download, select, or
assert the independence of an observation set. The control-data curator must
make that determination and record its basis.

## Control-point dataset format

Use the version-1 JSON format illustrated by
`examples/lunar_control_points_template.json`. That file is deliberately marked
synthetic and `independent_of_test_dem: false`; it is a schema example only and
must not be used as scientific reference data.

The required top-level fields are:

- `schema_version`: exactly `1`;
- `dataset_id`, `title`;
- `source`: name, URI, optional DOI, `independent_of_test_dem` boolean, and an
  `independence_statement`;
- `coordinates`: exact coordinate-system name, planetocentric latitude,
  east-positive longitude and declared longitude domain, vertical datum,
  spherical reference radius in metres, `height` or `radius` interpretation,
  and `value_unit: "m"`;
- `points`: unique point ID, latitude, longitude, `value_m`, and optional
  positive `uncertainty_1sigma_m`.

When `value_interpretation` is `radius`, EclipseKit subtracts the declared
reference radius once to obtain height above that sphere. When it is `height`,
the supplied values are already heights above that sphere. Planetographic
latitudes, west-positive longitudes, non-metre inputs, geoid heights and
ellipsoidal heights are not silently converted.

Every control point set must record `independent_of_test_dem` explicitly. A
false value still allows diagnostic residuals to be computed, but the aggregate
status is `NOT_INDEPENDENT`, never `PASS`. A true value is a curator assertion;
EclipseKit cannot audit the upstream processing history that supports it.

## Reference-data guidance

The NASA/USGS LOLA spot-observation release contains individual LRO Lunar Orbiter
Laser Altimeter returns derived from the LOLA Reduced Data Record (RDR). The
published release describes over 6.3 billion observations from July 2009 to
February 2023, with planetocentric/body-fixed coordinates, east-positive
longitude, and lunar radii. This makes it a useful *candidate source* for
building a point-control set, provided the selected shots were held out from
(and were not used to create) the DEM under test.

The original LOLA RDR is described as one geolocated altimetric record per laser
shot. The LOLA Gridded Data Record (GDRDEM), by contrast, is a binned and
interpolated map derived from LOLA observations. Comparing a LOLA-derived GDR
against another product derived from the same measurements is not an
independent validation. In particular, a DEM whose production incorporated the
same LOLA shots must not be labelled independent unless a genuinely withheld
subset is documented.

Useful source documentation:

1. USGS Astrogeology Analysis Ready Data, *Lunar Orbiter Laser Altimeter (Spot
   Observations)*: <https://stac.astrogeology.usgs.gov/docs/data/moon/lola/>.
   It documents the individual observation cloud, the 1737.4 km reference
   sphere for height conversion, coordinate conventions, and release DOI
   `10.5066/P9V5JIWH`.
2. PDS Geosciences Node, *LRO LOLA Reduced Data Record*: 
   <https://ode.rsl.wustl.edu/moon/pagehelp/Content/Missions_Instruments/Lunar%20Reconnaissance%20Orbiter%20(LRO)/LOLA/RDR.htm>.
   It describes the calibrated, geolocated pulse returns, radii and
   east-positive planetocentric/body-fixed coordinates; DOI `10.17189/1520652`.
3. PDS Geosciences Node, *LOLA Gridded Data Record Shape Map*: 
   <https://ode.rsl.wustl.edu/moon/pagehelp/Content/Missions_Instruments/Lunar%20Reconnaissance%20Orbiter%20(LRO)/LOLA/GDR/GDRDEM.htm>.
   It distinguishes the gridded, interpolated GDRDEM products from shot-level
   RDR observations.

For LOLA RDR radii, set `value_interpretation` to `radius` and `reference_radius_m`
to the reference sphere documented by the source. Obtain the exact frame label
from the product metadata or an authoritative source description. Do not infer
that a given LOLA product is `MOON_ME_DE421` or `MOON_PA_DE440` merely from its
instrument or kernel name. Use a built-in Phase 9.3 frame transform only when
its named source and target frames are actually the frames of the data.

## Python API

```python
from eclipsekit import (
    load_lunar_control_points,
    open_pds3_lunar_dem,
    validate_lunar_dem_control_points,
    write_lunar_dem_control_point_report,
)

points = load_lunar_control_points("data/independent_lunar_points.json")
with open_pds3_lunar_dem(
    "data/SLDEM2015_128_60S_60N_000_360_FLOAT.IMG",
    "data/SLDEM2015_128_60S_60N_000_360_FLOAT.LBL",
    expected_reference_radius_m=None,
) as dem:
    report = validate_lunar_dem_control_points(
        dem, points, tolerance_m=25.0  # illustrative only; justify for your data
    )
    write_lunar_dem_control_point_report(report, "reports/phase9_4")
```

The Python API accepts any DEM reader with `product_info` metadata and
`predict_altitude_m(latitude_deg, longitude_deg)`. PDS3, PDS4, GeoTIFF and JP2
readers expose this contract. If source and target frame/datum differ, pass an
explicit `LunarCoordinateTransform`; automatic frame inference is not done.

## Command line

PDS3 example:

```powershell
eclipsekit-validate-dem-control `
  --format pds3 `
  --dem "data\SLDEM2015_128_60S_60N_000_360_FLOAT.IMG" `
  --label "data\SLDEM2015_128_60S_60N_000_360_FLOAT.LBL" `
  --control-points "data\independent_lunar_points.json" `
  --tolerance-m 25 `
  --output-dir "reports\phase9_4"
```

The `25 m` threshold above is illustrative, not a recommended tolerance. Select
an acceptance tolerance from the observation uncertainty, DEM resolution,
slope, co-registration and intended use. The CLI requires an explicit
`--tolerance-m` and does not derive one from the point uncertainty.

For PDS4, pass the XML label as `--dem` (and optionally `--label` plus a detached
binary `--dem` path in the Python API). For GeoTIFF and JP2, supply the lunar
metadata arguments required by Phase 9.2, for example
`--coordinate-system-name`, `--reference-radius-m`, `--vertical-datum`,
`--value-interpretation` and `--value-unit`; use `--bounds WEST SOUTH EAST NORTH
--coordinates-in-degrees` for an unreferenced JP2.

For a known DE440 PA / DE421 ME source-target pair, select explicitly:

```powershell
--frame-transform de440-pa-to-de421-me
```

or the inverse `de421-me-to-de440-pa`. The CLI combines the selected fixed
frame rotation with the explicitly declared spherical source and DEM radii and
datum labels. It is not a time-dependent lunar orientation model.

## Metrics and acceptance semantics

Residual sign is `DEM − reference`; positive bias means the DEM is higher than
the control observations. The report includes mean bias, MAE, RMSE, median
absolute error, normalised median absolute deviation (1.4826 × MAD), 95th
percentile absolute error, maximum absolute error and per-point residuals.

Where an observation supplies a 1-sigma uncertainty, the report also gives the
standardised residual `residual / sigma`. That uncertainty is diagnostic only;
it does not loosen the absolute tolerance.

Aggregate status:

- `PASS`: the control set is declared independent and every point is evaluated
  within the caller's tolerance;
- `FAIL`: at least one evaluated independent control point exceeds tolerance;
- `PARTIAL`: one or more points are outside DEM coverage or fail to produce a
  finite elevation, without a separate residual exceeding tolerance;
- `NOT_INDEPENDENT`: the dataset manifest does not assert independence;
- CLI exit status is non-zero for every status other than `PASS`.

Files written:

- `lunar-dem-control-point-validation.json`
- `lunar-dem-control-point-validation.md`

## Explicit limitations

- No real independent point set is bundled. Unit tests use synthetic control
  points and a synthetic DEM sampler; they verify software behaviour only.
- The curator's independence statement is not independently verifiable by the
  software and must be supported by the dataset's processing history.
- The current validation compares vertical heights at sampled point locations.
  It is not a full horizontal-control, slope/aspect, raster completeness,
  geoid, triaxial-ellipsoid, or time-dependent lunar orientation assessment.
- DEM interpolation is bilinear. The validator does not correct for laser-footprint
  size, local slope/roughness, shot-quality screening, temporal change, or
  horizontal co-registration error.
- The fixed DE440 PA / DE421 ME transform is only used when explicitly selected
  and should not be substituted for high-accuracy time-dependent lunar attitude.
