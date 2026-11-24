"""Structural validation and provenance reports for PDS3 lunar DEM files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np

from .limb import LunarLimbQuery
from .topography import PDS3LunarDEMModel


@dataclass(frozen=True, slots=True)
class PDS3LunarDEMValidationReport:
    """A storage/metadata/interpolation smoke report, not an accuracy claim."""

    status: str
    product_info: dict[str, Any]
    model_metadata: dict[str, Any]
    sample_checks: tuple[dict[str, Any], ...]
    notes: tuple[str, ...]
    tile_cache: dict[str, Any] | None = None

    @property
    def passed_samples(self) -> int:
        return sum(item.get("status") == "PASS" for item in self.sample_checks)

    @property
    def failed_samples(self) -> int:
        return sum(item.get("status") != "PASS" for item in self.sample_checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "passed_samples": self.passed_samples,
            "failed_samples": self.failed_samples,
            "product_info": self.product_info,
            "model_metadata": self.model_metadata,
            "sample_checks": list(self.sample_checks),
            "tile_cache": self.tile_cache,
            "notes": list(self.notes),
        }

    def to_markdown(self) -> str:
        lines = [
            "# PDS3 lunar topography validation",
            "",
            f"- **Status:** **{self.status}**",
            f"- **Product:** `{self.product_info.get('product_id', 'unknown')}`",
            f"- **Image shape:** `{self.product_info.get('shape')}`",
            f"- **Pixels per degree:** `{self.product_info.get('pixels_per_degree')}`",
            f"- **Reference radius:** `{self.product_info.get('reference_radius_m')} m`",
            f"- **Coordinate system:** `{self.product_info.get('coordinate_system_name')}`",
            f"- **Interpolation samples:** {self.passed_samples} PASS / {self.failed_samples} not PASS",
        ]
        if self.tile_cache is not None:
            lines.extend([
                f"- **Tile shape:** `{self.tile_cache.get('tile_shape')}` pixels",
                f"- **Tile cache:** {self.tile_cache.get('current_tiles')} / {self.tile_cache.get('max_tiles')} tiles",
                f"- **Cached memory:** {self.tile_cache.get('cached_bytes')} / {self.tile_cache.get('max_bytes')} bytes",
                f"- **Cache hits / misses / evictions:** {self.tile_cache.get('hits')} / {self.tile_cache.get('misses')} / {self.tile_cache.get('evictions')}",
            ])
        lines.extend([
            "",
            "| Latitude (deg) | Longitude (deg east) | Height (m) | Status | Detail |",
            "|---:|---:|---:|---|---|",
        ])
        for item in self.sample_checks:
            altitude = item.get("altitude_m")
            altitude_text = "" if altitude is None else f"{altitude:.6f}"
            detail = str(item.get("detail", "")).replace("|", "\\|")
            lines.append(
                f"| {item.get('latitude_deg', '')} | {item.get('longitude_deg', '')} "
                f"| {altitude_text} | {item.get('status')} | {detail} |"
            )
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in self.notes)
        return "\n".join(lines) + "\n"


def validate_pds3_lunar_dem(
    image_path: str | Path,
    label_path: str | Path | None = None,
    *,
    sample_grid: int = 3,
    expected_reference_radius_m: float | None = 1_737_400.0,
    expected_coordinate_system: str | None = None,
    tile_shape: int | tuple[int, int] = 512,
    cache_tiles: int = 8,
) -> PDS3LunarDEMValidationReport:
    """Validate a PDS3 IMG label/storage and sample a deterministic point grid.

    ``PASS`` means the label, binary layout and requested interpolation samples
    passed.  It does not establish global vertical accuracy, completeness, or
    agreement with an independent lunar control dataset.
    """
    if isinstance(sample_grid, bool) or not isinstance(sample_grid, int) or sample_grid < 1:
        raise ValueError("sample_grid must be a positive integer")
    model = PDS3LunarDEMModel.from_pds3_img(
        image_path,
        label_path,
        expected_reference_radius_m=expected_reference_radius_m,
        expected_coordinate_system=expected_coordinate_system,
        tile_shape=tile_shape,
        cache_tiles=cache_tiles,
    )
    try:
        info = model.product_info
        latitudes = np.linspace(
            info.min_latitude_deg + (info.max_latitude_deg - info.min_latitude_deg) / (2 * sample_grid),
            info.max_latitude_deg - (info.max_latitude_deg - info.min_latitude_deg) / (2 * sample_grid),
            sample_grid,
        )
        longitude_span = info.east_longitude_deg - info.west_longitude_deg
        longitudes = np.linspace(
            info.west_longitude_deg + longitude_span / (2 * sample_grid),
            info.east_longitude_deg - longitude_span / (2 * sample_grid),
            sample_grid,
        )
        checks: list[dict[str, Any]] = []
        for latitude in latitudes:
            for longitude in longitudes:
                item: dict[str, Any] = {
                    "latitude_deg": float(latitude),
                    "longitude_deg": float(longitude),
                }
                try:
                    prediction = model.predict(LunarLimbQuery(
                        selenographic_latitude_deg=float(latitude),
                        selenographic_longitude_deg=float(longitude),
                        limb_angle_deg=0.0,
                    ))
                    item.update(
                        status="PASS",
                        altitude_m=prediction.altitude_m,
                        detail="finite interpolated height",
                    )
                except (ValueError, FloatingPointError) as exc:
                    item.update(status="NO_DATA_OR_INVALID", detail=str(exc))
                checks.append(item)
        passed = sum(item["status"] == "PASS" for item in checks)
        if passed == len(checks):
            status = "PASS"
        elif passed > 0:
            status = "PARTIAL"
        else:
            status = "FAIL"
        cache_info = model.cache_info().to_dict()
        notes = (
            "This report checks PDS3 label consistency, binary storage size and a deterministic interpolation sample grid.",
            "Tile-cache memory is bounded by cache_tiles * tile_rows * tile_columns * 8 bytes; the source IMG remains read-only memory-mapped.",
            "A PASS is not an independent vertical-accuracy validation and does not prove complete global coverage.",
            "No coordinate-frame transformation is applied; the product's body-fixed coordinate-system name is retained in provenance.",
            "Pointwise uncertainty is not inferred from a product-wide accuracy statement or from interpolation success.",
        )
        return PDS3LunarDEMValidationReport(
            status=status,
            product_info=info.to_dict(),
            model_metadata=model.metadata.to_dict(),
            sample_checks=tuple(checks),
            notes=notes,
            tile_cache=cache_info,
        )
    finally:
        model.close()


def write_pds3_topography_validation_report(
    report: PDS3LunarDEMValidationReport,
    output_dir: str | Path,
    *,
    stem: str = "lunar-topography-validation",
) -> tuple[Path, Path]:
    """Write JSON and Markdown reports; return their paths."""
    if not isinstance(report, PDS3LunarDEMValidationReport):
        raise TypeError("report must be a PDS3LunarDEMValidationReport")
    if not stem or Path(stem).name != stem or stem in {".", ".."}:
        raise ValueError("stem must be a simple filename without directory components")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{stem}.json"
    markdown_path = directory / f"{stem}.md"
    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(report.to_markdown(), encoding="utf-8")
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a PDS3 simple-cylindrical lunar DEM IMG and label."
    )
    parser.add_argument("--image", required=True, help="Path to the uncompressed PDS3 IMG file")
    parser.add_argument("--label", help="Detached PDS3 LBL file (default: adjacent same-stem label)")
    parser.add_argument("--output-dir", default="reports/phase7_6")
    parser.add_argument("--sample-grid", type=int, default=3)
    parser.add_argument("--tile-size", type=int, default=512, help="Square tile side in pixels")
    parser.add_argument("--cache-tiles", type=int, default=8, help="Maximum cached tiles; 0 disables cache")
    parser.add_argument(
        "--expected-coordinate-system",
        help="Require this exact coordinate-system name from the PDS3 label",
    )
    parser.add_argument(
        "--accept-labelled-radius",
        action="store_true",
        help="Accept the spherical reference radius declared by the label instead of requiring 1737400 m",
    )
    args = parser.parse_args(argv)
    try:
        report = validate_pds3_lunar_dem(
            args.image,
            args.label,
            sample_grid=args.sample_grid,
            expected_reference_radius_m=None if args.accept_labelled_radius else 1_737_400.0,
            expected_coordinate_system=args.expected_coordinate_system,
            tile_shape=args.tile_size,
            cache_tiles=args.cache_tiles,
        )
        json_path, markdown_path = write_pds3_topography_validation_report(
            report, args.output_dir
        )
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"PDS3 topography validation could not complete: {exc}\n")
    print(f"Status: {report.status}")
    print(f"Sample checks: {report.passed_samples} PASS / {report.failed_samples} not PASS")
    if report.tile_cache is not None:
        print(
            "Tile cache: "
            f"{report.tile_cache['current_tiles']}/{report.tile_cache['max_tiles']} tiles, "
            f"{report.tile_cache['cached_bytes']}/{report.tile_cache['max_bytes']} bytes, "
            f"{report.tile_cache['hits']} hits / {report.tile_cache['misses']} misses"
        )
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
