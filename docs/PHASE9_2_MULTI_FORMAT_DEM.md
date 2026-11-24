# Phase 9.2 — Multi-format Lunar DEM support

## Scope

Phase 9.2 extends the Phase 9.1 tiled access pattern to three additional
source formats while leaving the existing PDS3 reader intact:

1. **PDS4**: a strict reader for two-dimensional `Array_2D_Image` products with
   a regular simple-cylindrical/equirectangular grid.
2. **GeoTIFF**: an optional Rasterio/GDAL-backed reader for north-up geographic
   lunar rasters.
3. **JPEG 2000 (JP2)**: the same optional backend for GDAL JP2OpenJPEG-capable
   images. Non-georeferenced JP2 is accepted only with explicit degree bounds.

All three readers expose `predict`, `predict_altitude_m`, `read_window`,
`iter_tiles`, `cache_info`, `clear_tile_cache`, `close` and context-manager
support. Reads are windowed and an LRU cache bounds retained float64 tile
payload. The PDS4 binary source uses a read-only NumPy memory map; GeoTIFF/JP2
uses Rasterio window reads.

## Metadata and safety rules

The readers do not infer planetary identity, lunar frame, vertical datum or
sample interpretation from a filename. PDS4 must declare the necessary
metadata; GeoTIFF/JP2 must provide it in tags or explicit constructor options.
The coordinate frame must identify the intended Moon-fixed reference frame,
the reference radius must be spherical within tolerance, and sample values
must be explicitly interpreted as either:

- `height`: already expressed above the declared reference sphere; or
- `radius`: radial distance from the lunar centre, from which the reference
  radius is subtracted after unit and scale conversion.

Only east-positive longitude, regular geographic/simple-cylindrical grids and
north-up unrotated Rasterio grids are supported. Projected, rotated, sheared,
non-regular or non-spherical data are rejected instead of silently warped.
No PDS3/PDS4 format conversion, reprojection or DE421/DE440 frame conversion is
performed.

## Optional dependency

The PDS4 path uses the Python standard library and NumPy already required by
EclipseKit. GeoTIFF/JP2 requires the optional Rasterio/GDAL dependency:

```powershell
python -m pip install -e ".[raster]"
```

## API examples

PDS4:

```python
from eclipsekit import open_pds4_lunar_dem

with open_pds4_lunar_dem(
    "data/lunar_dem.xml",
    expected_coordinate_system="MEAN EARTH/POLAR AXIS OF DE421",
    tile_shape=512,
    cache_tiles=8,
) as dem:
    h_m = dem.predict_altitude_m(-10.0, 25.0)
    window = dem.read_window(100, 200, 500, 700)
```

GeoTIFF:

```python
from eclipsekit import open_geotiff_lunar_dem

with open_geotiff_lunar_dem(
    "data/lunar_dem.tif",
    coordinate_system_name="MEAN EARTH/POLAR AXIS OF DE421",
    reference_radius_m=1_737_400.0,
    vertical_datum="radial height relative to the DE421 sphere",
    value_interpretation="height",
    value_unit="m",
) as dem:
    h_m = dem.predict_altitude_m(-10.0, 25.0)
```

JP2 uses `open_jp2_lunar_dem` and the same provenance arguments. For an image
without CRS/geotransform, additionally provide `bounds=(west, south, east,
north)` and `coordinates_in_degrees=True`.

## Validation CLI

```powershell
eclipsekit-validate-dem-format --format pds4 --input "data\lunar_dem.xml" `
  --expected-coordinate-system "MEAN EARTH/POLAR AXIS OF DE421" `
  --sample-grid 5 --tile-size 512 --cache-tiles 8 `
  --output-dir "reports\phase9_2"
```

For GeoTIFF/JP2 provide `--coordinate-system-name`, `--reference-radius-m`,
`--vertical-datum`, `--value-interpretation` and `--value-unit` (unless supplied
by raster tags/band metadata). For an unreferenced JP2 use `--bounds WEST SOUTH
EAST NORTH --coordinates-in-degrees`.

## Validation meaning and limitations

A report with `PASS` confirms that the file can be read in the supported subset,
that the required provenance/geometry has been validated, and that selected
interpolation samples are finite. It does not establish independent vertical
accuracy, full-product completeness or eclipse-contact accuracy. Coordinate
frame transformations and independent lunar control-point validation are
planned separately in Phase 9.3 and Phase 9.4.
