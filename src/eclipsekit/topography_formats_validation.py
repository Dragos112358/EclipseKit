"""Structural and sampling validation for Phase 9.2 lunar DEM formats."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .topography_formats import (
    GeoTiffLunarDEMModel, JP2LunarDEMModel, PDS4LunarDEMModel,
    RasterioLunarDEMModel,
)


@dataclass(frozen=True, slots=True)
class LunarDEMFormatSample:
    latitude_deg: float
    longitude_deg: float
    altitude_m: float | None
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "latitude_deg": self.latitude_deg,
            "longitude_deg": self.longitude_deg,
            "altitude_m": self.altitude_m,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class LunarDEMFormatValidationReport:
    status: str
    format: str
    source: str
    product_info: dict[str, Any]
    model_metadata: dict[str, Any]
    requested_samples: int
    passed_samples: int
    failed_samples: int
    samples: tuple[LunarDEMFormatSample, ...]
    tile_cache: dict[str, Any]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "format": self.format,
            "source": self.source,
            "product_info": self.product_info,
            "model_metadata": self.model_metadata,
            "summary": {
                "requested_samples": self.requested_samples,
                "passed_samples": self.passed_samples,
                "failed_samples": self.failed_samples,
            },
            "samples": [item.to_dict() for item in self.samples],
            "tile_cache": self.tile_cache,
            "limitations": list(self.limitations),
        }


def validate_lunar_dem_format(model: PDS4LunarDEMModel | RasterioLunarDEMModel,
                              *, sample_grid: int = 5) -> LunarDEMFormatValidationReport:
    if isinstance(sample_grid, bool) or not isinstance(sample_grid, int) or sample_grid < 2:
        raise ValueError("sample_grid must be an integer >= 2")
    south, north, west, east = model.coverage
    # Sample away from cell boundaries. This is a structural/interpolation
    # smoke test, not a comparison to independent height ground truth.
    latitudes = np.linspace(south, north, sample_grid + 2)[1:-1]
    longitudes = np.linspace(west, east, sample_grid + 2)[1:-1]
    samples: list[LunarDEMFormatSample] = []
    for latitude in latitudes:
        for longitude in longitudes:
            try:
                value = model.predict_altitude_m(float(latitude), float(longitude))
                if not math.isfinite(value):
                    raise ValueError("interpolated elevation is not finite")
                samples.append(LunarDEMFormatSample(
                    float(latitude), float(longitude), float(value), "PASS"
                ))
            except (ValueError, IndexError, RuntimeError) as exc:
                samples.append(LunarDEMFormatSample(
                    float(latitude), float(longitude), None, f"FAIL: {exc}"
                ))
    passed = sum(item.status == "PASS" for item in samples)
    failed = len(samples) - passed
    cache = model.cache_info().to_dict()
    info = model.product_info.to_dict()
    return LunarDEMFormatValidationReport(
        status="PASS" if passed == len(samples) and passed > 0 else "FAIL",
        format=model.product_info.format,
        source=model.product_info.data_file,
        product_info=info,
        model_metadata=model.metadata.to_dict(),
        requested_samples=len(samples), passed_samples=passed,
        failed_samples=failed, samples=tuple(samples), tile_cache=cache,
        limitations=(
            "PASS validates the declared grid structure, metadata and selected interpolation samples; "
            "it does not certify global DEM vertical accuracy.",
            "No coordinate-frame transformation or reprojection is applied.",
            "Rasterio-backed GeoTIFF/JP2 grids require explicit lunar frame, vertical datum, "
            "reference radius and sample-value interpretation.",
        ),
    )


def write_lunar_dem_format_report(report: LunarDEMFormatValidationReport,
                                  output_dir: str | Path) -> tuple[Path, Path]:
    directory = Path(output_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{report.format.casefold()}-lunar-dem-validation"
    json_path = directory / f"{stem}.json"
    markdown_path = directory / f"{stem}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False,
                                    allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        f"# EclipseKit {report.format} lunar DEM validation",
        "",
        f"**Status:** {report.status}",
        f"**Source:** `{report.source}`",
        f"**Samples:** {report.passed_samples} PASS / {report.failed_samples} FAIL",
        "",
        "## Product metadata",
        "",
        f"- **Product ID:** {report.product_info['product_id']}",
        f"- **Shape:** {report.product_info['shape'][0]} × {report.product_info['shape'][1]}",
        f"- **Coordinate system:** {report.product_info['coordinate_system_name']}",
        f"- **Vertical datum:** {report.product_info['vertical_datum']}",
        f"- **Reference radius:** {report.product_info['reference_radius_m']:.3f} m",
        f"- **Value interpretation:** {report.product_info['value_interpretation']}",
        "",
        "## Sampling results",
        "",
        "| Latitude (deg) | Longitude (deg) | Altitude (m) | Status |",
        "|---:|---:|---:|---|",
    ]
    for sample in report.samples:
        altitude = (f"{sample.altitude_m:.6f}"
                    if sample.altitude_m is not None and math.isfinite(sample.altitude_m) else "—")
        lines.append(
            f"| {sample.latitude_deg:.6f} | {sample.longitude_deg:.6f} | {altitude} | {sample.status} |"
        )
    lines.extend(["", "## Tile cache", "", "```json", json.dumps(report.tile_cache, indent=2), "```", "",
                  "## Limitations", ""])
    lines.extend(f"- {item}" for item in report.limitations)
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a PDS4, GeoTIFF or JP2 lunar DEM using metadata and sample interpolation."
    )
    parser.add_argument("--format", required=True, choices=("pds4", "geotiff", "jp2"))
    parser.add_argument("--input", required=True,
                        help="PDS4 XML label for pds4; raster path for geotiff/jp2")
    parser.add_argument("--image", help="Optional PDS4 binary array file override")
    parser.add_argument("--value-interpretation", choices=("height", "radius"))
    parser.add_argument("--coordinate-system-name")
    parser.add_argument("--reference-radius-m", type=float)
    parser.add_argument("--vertical-datum")
    parser.add_argument("--value-unit")
    parser.add_argument("--bounds", nargs=4, type=float,
                        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
                        help="Required for non-georeferenced JP2; coordinates are degrees")
    parser.add_argument("--coordinates-in-degrees", action="store_true")
    parser.add_argument("--expected-coordinate-system")
    parser.add_argument("--expected-reference-radius-m", type=float, default=1_737_400.0)
    parser.add_argument("--accept-labelled-radius", action="store_true",
                        help="Accept the spherical radius declared by the PDS4 label")
    parser.add_argument("--sample-grid", type=int, default=5)
    parser.add_argument("--tile-size", type=int, default=512)
    parser.add_argument("--cache-tiles", type=int, default=8)
    parser.add_argument("--output-dir", default="reports/phase9_2")
    args = parser.parse_args(argv)

    model: PDS4LunarDEMModel | RasterioLunarDEMModel | None = None
    try:
        common = {
            "expected_coordinate_system": args.expected_coordinate_system,
            "tile_shape": args.tile_size,
            "cache_tiles": args.cache_tiles,
        }
        if args.format == "pds4":
            model = PDS4LunarDEMModel(
                args.input, args.image,
                value_interpretation=args.value_interpretation,
                expected_reference_radius_m=(
                    None if args.accept_labelled_radius else args.expected_reference_radius_m
                ),
                **common,
            )
        else:
            raster_options = {
                "coordinate_system_name": args.coordinate_system_name,
                "reference_radius_m": args.reference_radius_m,
                "vertical_datum": args.vertical_datum,
                "value_interpretation": args.value_interpretation,
                "value_unit": args.value_unit,
                "bounds": tuple(args.bounds) if args.bounds else None,
                "coordinates_in_degrees": args.coordinates_in_degrees,
                "expected_coordinate_system": args.expected_coordinate_system,
                "tile_shape": args.tile_size,
                "cache_tiles": args.cache_tiles,
            }
            model = (GeoTiffLunarDEMModel(args.input, **raster_options)
                     if args.format == "geotiff" else JP2LunarDEMModel(args.input, **raster_options))
        report = validate_lunar_dem_format(model, sample_grid=args.sample_grid)
        json_path, markdown_path = write_lunar_dem_format_report(report, args.output_dir)
    except (OSError, ValueError, TypeError, ImportError, RuntimeError) as exc:
        parser.exit(2, f"Lunar DEM format validation could not complete: {type(exc).__name__}: {exc}\n")
    finally:
        if model is not None:
            model.close()
    print(f"Status: {report.status}")
    print(f"Samples: {report.passed_samples} PASS / {report.failed_samples} FAIL")
    print(f"Tile cache: {report.tile_cache['current_tiles']}/{report.tile_cache['max_tiles']} tiles, "
          f"{report.tile_cache['cached_bytes']}/{report.tile_cache['max_bytes']} bytes, "
          f"{report.tile_cache['hits']} hits / {report.tile_cache['misses']} misses")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
