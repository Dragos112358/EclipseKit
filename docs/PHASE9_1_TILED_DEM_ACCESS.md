# Phase 9.1 — Tiled PDS3 lunar DEM access

## Scope

Phase 9.1 adds bounded, reusable access patterns for large PDS3 IMG lunar DEMs.
The source IMG remains a read-only NumPy memory map. It is not loaded as a
whole into RAM. Interpolation now uses an LRU cache of converted float64 tiles;
callers can also read a rectangular window or stream the image tile by tile.

This phase continues to support the validated PDS3 simple-cylindrical image
subset. It does not add PDS4, GeoTIFF, JP2, mosaicking, reprojection, or
conversion between body-fixed reference frames. The PDS label's coordinate
system and vertical datum remain authoritative metadata and must be checked by
the calling workflow.

## Public API

```python
from eclipsekit import open_pds3_lunar_dem

with open_pds3_lunar_dem(
    "data/SLDEM2015_128_60S_60N_000_360_FLOAT.IMG",
    "data/SLDEM2015_128_60S_60N_000_360_FLOAT.LBL",
    expected_coordinate_system="MEAN EARTH/POLAR AXIS OF DE421",
    tile_shape=(512, 512),
    cache_tiles=8,
) as dem:
    # Existing point interpolation remains compatible.
    height_m = dem.predict_altitude_m(-10.0, 25.0)

    # Read a zero-based, half-open image window. Heights are metres above
    # the spherical reference radius in the PDS3 label.
    window = dem.read_window(100, 200, 500, 700)
    print(window.height_above_reference_m.shape)

    # Stream the source in bounded windows without loading the full image.
    for tile in dem.iter_tiles((256, 256)):
        print(tile.row_start, tile.column_start, tile.shape)
        # Process this tile, then allow it to be released before the next one.

    print(dem.cache_info().to_dict())
```

`read_window(row_start, row_stop, column_start, column_stop)` uses zero-based,
half-open bounds and returns an independent read-only `LunarDEMWindow`. Its
`height_above_reference_m` array preserves missing source samples as NaN.
Window coordinates do not wrap around the global longitude seam; the caller
must split a seam-crossing request into two windows.

`iter_tiles(tile_shape=None)` streams non-overlapping windows in row-major
order. Edge windows may be smaller than the requested shape.

## Cache policy and memory bound

- Default tile size: 512 × 512 pixels.
- Default maximum retained tiles: 8.
- Tile values are converted to float64 metres above the labelled reference
  sphere once when loaded into the cache.
- Cache eviction is least-recently-used (LRU).
- `cache_tiles=0` disables caching.
- `cache_info()` reports hits, misses, evictions, current tiles, actual cached
  bytes, and the maximum cache-byte bound.
- `clear_tile_cache()` releases cached tiles; by default it also resets stats.
- `close()` releases cached arrays and closes the read-only memory map.

With defaults, the cache's maximum payload is 16 MiB (`8 × 512 × 512 × 8`).
This excludes small Python object overhead. The memory-mapped source file is
still backed by the OS page cache; memory mapping avoids eagerly copying the
entire multi-gigabyte IMG into Python-managed memory, but does not promise that
the operating system will keep every page out of physical memory.

## Validation

The topography validator now accepts `--tile-size` and `--cache-tiles` and
records cache behaviour in JSON/Markdown. For the user's SLDEM2015 product:

```powershell
eclipsekit-validate-topography `
  --image "data\SLDEM2015_128_60S_60N_000_360_FLOAT.IMG" `
  --label "data\SLDEM2015_128_60S_60N_000_360_FLOAT.LBL" `
  --expected-coordinate-system "MEAN EARTH/POLAR AXIS OF DE421" `
  --sample-grid 5 `
  --tile-size 512 `
  --cache-tiles 8 `
  --output-dir "reports\phase9_1"
```

A PASS confirms PDS3 structure, file layout and selected interpolation samples.
It does not independently certify the DEM's global vertical accuracy, its
registration to DE440s, or eclipse-contact accuracy. Phase 9.3 is intended to
address explicit frame/datum transformations; it must not be assumed here.
