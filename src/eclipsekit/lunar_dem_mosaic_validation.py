"""Overlap-consistency audit for virtual lunar DEM mosaics.

This module compares independent source readers inside their declared overlap.
It never edits source products, blends elevations, or implies that agreement
between two products proves absolute accuracy or co-registration.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import itertools
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .lunar_dem_mosaic import LunarDEMCoverage, LunarDEMMosaicModel


def _positive_finite(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise TypeError(f"{name} must be a numeric value")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return result


def _longitude_interval(coverage: LunarDEMCoverage) -> tuple[float, float, bool]:
    """Return an unwrapped [0, 360) start, span, and global flag."""
    span = coverage.east_longitude_deg - coverage.west_longitude_deg
    global_longitude = math.isclose(span, 360.0, rel_tol=0.0, abs_tol=1e-6)
    return coverage.west_longitude_deg % 360.0, span, global_longitude


def _canonical_longitude(longitude_360: float) -> float:
    result = longitude_360 % 360.0
    if result > 180.0:
        result -= 360.0
    return 0.0 if abs(result) < 1e-12 else result


def _overlap_regions(
    first: LunarDEMCoverage, second: LunarDEMCoverage
) -> tuple[tuple[float, float, float, float], ...]:
    south = max(first.south_latitude_deg, second.south_latitude_deg)
    north = min(first.north_latitude_deg, second.north_latitude_deg)
    if north <= south:
        return ()
    start_a, span_a, global_a = _longitude_interval(first)
    start_b, span_b, global_b = _longitude_interval(second)
    if global_a and global_b:
        return ((south, north, 0.0, 360.0),)
    if global_a:
        return ((south, north, start_b, start_b + span_b),)
    if global_b:
        return ((south, north, start_a, start_a + span_a),)

    # Compare one interval against three adjacent 360-degree branches of the
    # other. This keeps a footprint such as -10..10 as one continuous region
    # rather than splitting its sample grid at the 0/360 representation seam.
    intervals: list[tuple[float, float, float, float]] = []
    seen: set[tuple[float, float]] = set()
    for shift in (-360.0, 0.0, 360.0):
        west = max(start_a, start_b + shift)
        east = min(start_a + span_a, start_b + shift + span_b)
        if east - west <= 1e-10:
            continue
        key = (round(west % 360.0, 10), round(east - west, 10))
        if key not in seen:
            seen.add(key)
            intervals.append((south, north, west, east))
    return tuple(intervals)


@dataclass(frozen=True, slots=True)
class LunarDEMOverlapSample:
    latitude_deg: float
    longitude_deg: float
    altitude_a_m: float | None
    altitude_b_m: float | None
    difference_b_minus_a_m: float | None
    absolute_difference_m: float | None
    status: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "latitude_deg": self.latitude_deg,
            "longitude_deg": self.longitude_deg,
            "altitude_a_m": self.altitude_a_m,
            "altitude_b_m": self.altitude_b_m,
            "difference_b_minus_a_m": self.difference_b_minus_a_m,
            "absolute_difference_m": self.absolute_difference_m,
            "status": self.status,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class LunarDEMOverlapPairResult:
    source_a: str
    source_b: str
    status: str
    overlap_regions: tuple[dict[str, float], ...]
    samples_requested: int
    valid_samples: int
    failed_samples: int
    error_samples: int
    bias_m: float | None
    mae_m: float | None
    rmse_m: float | None
    median_absolute_difference_m: float | None
    percentile_95_absolute_difference_m: float | None
    maximum_absolute_difference_m: float | None
    samples: tuple[LunarDEMOverlapSample, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_a": self.source_a,
            "source_b": self.source_b,
            "status": self.status,
            "overlap_regions": list(self.overlap_regions),
            "samples_requested": self.samples_requested,
            "valid_samples": self.valid_samples,
            "failed_samples": self.failed_samples,
            "error_samples": self.error_samples,
            "metrics": {
                "bias_m": self.bias_m,
                "mae_m": self.mae_m,
                "rmse_m": self.rmse_m,
                "median_absolute_difference_m": self.median_absolute_difference_m,
                "percentile_95_absolute_difference_m": self.percentile_95_absolute_difference_m,
                "maximum_absolute_difference_m": self.maximum_absolute_difference_m,
            },
            "samples": [sample.to_dict() for sample in self.samples],
        }


@dataclass(frozen=True, slots=True)
class LunarDEMMosaicOverlapReport:
    status: str
    mosaic_product_id: str
    coordinate_system_name: str
    vertical_datum: str
    reference_radius_m: float
    samples_per_axis: int
    absolute_tolerance_m: float
    compared_pairs: int
    passed_pairs: int
    failed_pairs: int
    error_pairs: int
    no_overlap_pairs: int
    pair_results: tuple[LunarDEMOverlapPairResult, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "status": self.status,
            "mosaic": {
                "product_id": self.mosaic_product_id,
                "coordinate_system_name": self.coordinate_system_name,
                "vertical_datum": self.vertical_datum,
                "reference_radius_m": self.reference_radius_m,
            },
            "sampling": {
                "samples_per_axis": self.samples_per_axis,
                "absolute_tolerance_m": self.absolute_tolerance_m,
            },
            "summary": {
                "compared_pairs": self.compared_pairs,
                "passed_pairs": self.passed_pairs,
                "failed_pairs": self.failed_pairs,
                "error_pairs": self.error_pairs,
                "no_overlap_pairs": self.no_overlap_pairs,
            },
            "pairs": [pair.to_dict() for pair in self.pair_results],
            "limitations": list(self.limitations),
        }


def _sample_points(
    regions: tuple[tuple[float, float, float, float], ...], samples_per_axis: int
) -> tuple[tuple[float, float], ...]:
    points: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for south, north, west, east in regions:
        latitudes = np.linspace(south, north, samples_per_axis, dtype=np.float64)
        longitudes = np.linspace(west, east, samples_per_axis, dtype=np.float64)
        for latitude in latitudes:
            for longitude in longitudes:
                canonical = _canonical_longitude(float(longitude))
                key = (round(float(latitude), 10), round(canonical, 10))
                if key not in seen:
                    seen.add(key)
                    points.append((float(latitude), canonical))
    return tuple(points)


def _audit_pair(
    source_a: Any,
    source_b: Any,
    regions: tuple[tuple[float, float, float, float], ...],
    *,
    samples_per_axis: int,
    tolerance_m: float,
) -> LunarDEMOverlapPairResult:
    source_points = _sample_points(regions, samples_per_axis)
    sample_rows: list[LunarDEMOverlapSample] = []
    residuals: list[float] = []
    failed = 0
    errors = 0
    for latitude, longitude in source_points:
        altitude_a: float | None = None
        altitude_b: float | None = None
        sample_errors: list[str] = []
        try:
            altitude_a = _positive_or_finite_altitude(
                source_a.model.predict_altitude_m(latitude, longitude), source_a.name
            )
        except Exception as exc:
            sample_errors.append(f"{source_a.name}: {type(exc).__name__}: {exc}")
        try:
            altitude_b = _positive_or_finite_altitude(
                source_b.model.predict_altitude_m(latitude, longitude), source_b.name
            )
        except Exception as exc:
            sample_errors.append(f"{source_b.name}: {type(exc).__name__}: {exc}")
        if sample_errors:
            errors += 1
            sample_rows.append(
                LunarDEMOverlapSample(
                    latitude, longitude, altitude_a, altitude_b, None, None, "ERROR",
                    "; ".join(sample_errors),
                )
            )
            continue
        assert altitude_a is not None and altitude_b is not None
        difference = altitude_b - altitude_a
        absolute = abs(difference)
        status = "PASS" if absolute <= tolerance_m else "FAIL"
        failed += status == "FAIL"
        residuals.append(difference)
        sample_rows.append(
            LunarDEMOverlapSample(
                latitude, longitude, altitude_a, altitude_b, difference, absolute, status
            )
        )
    if errors:
        status = "ERROR"
    elif failed:
        status = "FAIL"
    else:
        status = "PASS"
    metrics: dict[str, float | None]
    if residuals:
        values = np.asarray(residuals, dtype=np.float64)
        absolute_values = np.abs(values)
        metrics = {
            "bias_m": float(np.mean(values)),
            "mae_m": float(np.mean(absolute_values)),
            "rmse_m": float(np.sqrt(np.mean(values**2))),
            "median_absolute_difference_m": float(np.median(absolute_values)),
            "percentile_95_absolute_difference_m": float(np.percentile(absolute_values, 95)),
            "maximum_absolute_difference_m": float(np.max(absolute_values)),
        }
    else:
        metrics = {
            "bias_m": None,
            "mae_m": None,
            "rmse_m": None,
            "median_absolute_difference_m": None,
            "percentile_95_absolute_difference_m": None,
            "maximum_absolute_difference_m": None,
        }
    region_rows_list: list[dict[str, float]] = []
    for south, north, west, east in regions:
        global_longitude = math.isclose(east - west, 360.0, rel_tol=0.0, abs_tol=1e-8)
        region_rows_list.append(
            {
                "south_latitude_deg": south,
                "north_latitude_deg": north,
                "west_longitude_deg": 0.0 if global_longitude else _canonical_longitude(west),
                "east_longitude_deg": 360.0 if global_longitude else _canonical_longitude(east),
                "longitude_branch_west_0_360_deg": west,
                "longitude_branch_east_0_360_deg": east,
            }
        )
    region_rows = tuple(region_rows_list)
    return LunarDEMOverlapPairResult(
        source_a=source_a.name,
        source_b=source_b.name,
        status=status,
        overlap_regions=region_rows,
        samples_requested=len(source_points),
        valid_samples=len(residuals),
        failed_samples=int(failed),
        error_samples=errors,
        samples=tuple(sample_rows),
        **metrics,
    )


def _positive_or_finite_altitude(value: Any, source_name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise TypeError(f"DEM source {source_name!r} returned a non-numeric altitude")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"DEM source {source_name!r} returned a non-finite altitude")
    return result


def audit_lunar_dem_mosaic_overlaps(
    mosaic: LunarDEMMosaicModel,
    *,
    samples_per_axis: int = 5,
    absolute_tolerance_m: float = 100.0,
) -> LunarDEMMosaicOverlapReport:
    """Compare every source pair on a deterministic grid within declared overlap.

    A pair with no positive-area overlap is recorded as ``NO_OVERLAP`` and is
    not counted as a failure. The overall result is ``NOT_COMPARABLE`` when no
    source pair has any overlap. All comparisons query the original readers,
    not the mosaic's priority/finest/mean output.
    """
    if not isinstance(mosaic, LunarDEMMosaicModel):
        raise TypeError("mosaic must be a LunarDEMMosaicModel")
    if isinstance(samples_per_axis, bool) or not isinstance(samples_per_axis, int):
        raise TypeError("samples_per_axis must be an integer")
    if not 2 <= samples_per_axis <= 101:
        raise ValueError("samples_per_axis must be between 2 and 101")
    tolerance = _positive_finite(absolute_tolerance_m, "absolute_tolerance_m")
    mosaic._ensure_open()
    pair_results: list[LunarDEMOverlapPairResult] = []
    for source_a, source_b in itertools.combinations(mosaic.sources, 2):
        regions = _overlap_regions(source_a.coverage, source_b.coverage)
        if not regions:
            pair_results.append(
                LunarDEMOverlapPairResult(
                    source_a=source_a.name,
                    source_b=source_b.name,
                    status="NO_OVERLAP",
                    overlap_regions=(),
                    samples_requested=0,
                    valid_samples=0,
                    failed_samples=0,
                    error_samples=0,
                    bias_m=None,
                    mae_m=None,
                    rmse_m=None,
                    median_absolute_difference_m=None,
                    percentile_95_absolute_difference_m=None,
                    maximum_absolute_difference_m=None,
                    samples=(),
                )
            )
        else:
            pair_results.append(
                _audit_pair(
                    source_a, source_b, regions,
                    samples_per_axis=samples_per_axis,
                    tolerance_m=tolerance,
                )
            )
    compared = [pair for pair in pair_results if pair.status != "NO_OVERLAP"]
    passed = sum(pair.status == "PASS" for pair in pair_results)
    failed = sum(pair.status == "FAIL" for pair in pair_results)
    errors = sum(pair.status == "ERROR" for pair in pair_results)
    no_overlap = sum(pair.status == "NO_OVERLAP" for pair in pair_results)
    if not compared:
        status = "NOT_COMPARABLE"
    elif errors:
        status = "ERROR"
    elif failed:
        status = "FAIL"
    else:
        status = "PASS"
    info = mosaic.product_info
    return LunarDEMMosaicOverlapReport(
        status=status,
        mosaic_product_id=info.product_id,
        coordinate_system_name=info.coordinate_system_name,
        vertical_datum=info.vertical_datum,
        reference_radius_m=info.reference_radius_m,
        samples_per_axis=samples_per_axis,
        absolute_tolerance_m=tolerance,
        compared_pairs=len(compared),
        passed_pairs=passed,
        failed_pairs=failed,
        error_pairs=errors,
        no_overlap_pairs=no_overlap,
        pair_results=tuple(pair_results),
        limitations=(
            "The audit compares source elevations only inside declared positive-area coverage overlaps.",
            "Agreement between two products does not establish absolute lunar elevation accuracy.",
            "Rectangular coverage and matching metadata do not prove horizontal co-registration.",
            "No seam correction, blending, raster resampling, reprojection, or source-file modification is performed.",
            "The deterministic regular grid is a diagnostic sample, not an exhaustive comparison of every raster cell.",
            "Products without overlap cannot be compared by this audit; use independent tie points or a documented overlap strip.",
        ),
    )


def write_lunar_dem_mosaic_overlap_report(
    report: LunarDEMMosaicOverlapReport, output_dir: str | Path
) -> tuple[Path, Path]:
    directory = Path(output_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "lunar-dem-mosaic-overlap-audit.json"
    markdown_path = directory / "lunar-dem-mosaic-overlap-audit.md"
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# EclipseKit lunar DEM mosaic overlap audit",
        "",
        f"**Overall status:** {report.status}",
        f"**Mosaic:** `{report.mosaic_product_id}`",
        f"**Coordinate system:** `{report.coordinate_system_name}`",
        f"**Vertical datum:** `{report.vertical_datum}`",
        f"**Reference radius:** {report.reference_radius_m:.3f} m",
        f"**Sampling:** {report.samples_per_axis} × {report.samples_per_axis} per overlap region",
        f"**Absolute point tolerance:** {report.absolute_tolerance_m:.3f} m",
        "",
        "## Pair results",
        "",
        "| Source A | Source B | Status | Valid samples | Failed | Errors | Bias (m) | MAE (m) | RMSE (m) | Max abs (m) |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for pair in report.pair_results:
        def fmt(value):
            return "—" if value is None else f"{value:.3f}"
    lines.append(
            f"| {pair.source_a} | {pair.source_b} | {pair.status} | {pair.valid_samples} | "
            f"{pair.failed_samples} | {pair.error_samples} | {fmt(pair.bias_m)} | "
            f"{fmt(pair.mae_m)} | {fmt(pair.rmse_m)} | {fmt(pair.maximum_absolute_difference_m)} |"
        )
    lines.extend(["", "## Interpretation", ""])
    lines.extend(f"- {item}" for item in report.limitations)
    lines.extend(["", "## Sample-level records", ""])
    for pair in report.pair_results:
        if not pair.samples:
            continue
        lines.extend([f"### {pair.source_a} vs {pair.source_b}", ""])
        lines.extend(
            [
                "| Latitude (°) | Longitude (°) | A (m) | B (m) | B − A (m) | Status |",
                "|---:|---:|---:|---:|---:|---|",
            ]
        )
        for sample in pair.samples:
            values = (sample.altitude_a_m, sample.altitude_b_m, sample.difference_b_minus_a_m)
            formatted = ["—" if value is None else f"{value:.3f}" for value in values]
            lines.append(
                f"| {sample.latitude_deg:.6f} | {sample.longitude_deg:.6f} | "
                f"{formatted[0]} | {formatted[1]} | {formatted[2]} | {sample.status} |"
            )
            if sample.error:
                lines.append(f"\n  Error: `{sample.error}`\n")
        lines.append("")
    markdown_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return json_path, markdown_path


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid manifest JSON: {exc}") from exc
    version = document.get("schema_version") if isinstance(document, dict) else None
    if isinstance(version, bool) or version != 1:
        raise ValueError("manifest must be an object with schema_version=1")
    sources = document.get("sources")
    if not isinstance(sources, list) or len(sources) < 2:
        raise ValueError("manifest sources must be an array with at least two entries")
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit altitude consistency between lunar DEMs in their declared overlap."
    )
    parser.add_argument("--manifest", required=True, help="Versioned JSON manifest of PDS3 sources")
    parser.add_argument("--samples-per-axis", type=int, default=5)
    parser.add_argument("--tolerance-m", type=float, default=100.0)
    parser.add_argument("--output-dir", default="reports/phase9_7")
    args = parser.parse_args(argv)
    manifest_path = Path(args.manifest).expanduser().resolve()
    try:
        document = _load_manifest(manifest_path)
        from contextlib import ExitStack
        from .topography import open_pds3_lunar_dem

        with ExitStack() as stack:
            models = []
            names = []
            coverage_overrides = []
            for index, entry in enumerate(document["sources"]):
                if not isinstance(entry, dict):
                    raise ValueError(f"source entry {index} must be an object")
                image_value = entry.get("image_path")
                if not isinstance(image_value, str) or not image_value.strip():
                    raise ValueError(f"source entry {index} must declare image_path")
                image_path = Path(image_value).expanduser()
                if not image_path.is_absolute():
                    image_path = manifest_path.parent / image_path
                label_value = entry.get("label_path")
                label_path = None
                if label_value is not None:
                    if not isinstance(label_value, str) or not label_value.strip():
                        raise ValueError(f"source entry {index} label_path must be a non-empty string")
                    label_path = Path(label_value).expanduser()
                    if not label_path.is_absolute():
                        label_path = manifest_path.parent / label_path
                reader_kwargs: dict[str, Any] = {}
                for key in ("expected_coordinate_system", "expected_reference_radius_m"):
                    if key in entry and entry[key] is not None:
                        reader_kwargs[key] = entry[key]
                models.append(stack.enter_context(open_pds3_lunar_dem(image_path, label_path, **reader_kwargs)))
                names.append(entry.get("name", f"source-{index + 1}"))
                coverage = entry.get("coverage")
                if coverage is None:
                    coverage_overrides.append(None)
                elif isinstance(coverage, dict):
                    expected = {
                        "south_latitude_deg", "north_latitude_deg",
                        "west_longitude_deg", "east_longitude_deg",
                    }
                    if set(coverage) != expected:
                        raise ValueError(
                            f"source entry {index} coverage must contain exactly {sorted(expected)}"
                        )
                    coverage_overrides.append(
                        LunarDEMCoverage(**{key: coverage[key] for key in expected})
                    )
                else:
                    raise ValueError(f"source entry {index} coverage must be an object or null")
            mosaic = LunarDEMMosaicModel(
                models,
                strategy="priority",
                source_names=names,
                coverage_overrides=coverage_overrides,
                close_sources=False,
                name=str(document.get("name", "Lunar DEM overlap audit")),
                product_id=str(document.get("product_id", "eclipsekit-lunar-dem-overlap-audit")),
            )
            report = audit_lunar_dem_mosaic_overlaps(
                mosaic,
                samples_per_axis=args.samples_per_axis,
                absolute_tolerance_m=args.tolerance_m,
            )
            json_path, markdown_path = write_lunar_dem_mosaic_overlap_report(report, args.output_dir)
    except (OSError, TypeError, ValueError, KeyError, RuntimeError) as exc:
        parser.exit(2, f"Lunar DEM overlap audit could not complete: {type(exc).__name__}: {exc}\n")
    print(f"Status: {report.status}")
    print(
        f"Pairs: {report.compared_pairs} compared / {report.passed_pairs} PASS / "
        f"{report.failed_pairs} FAIL / {report.error_pairs} ERROR / "
        f"{report.no_overlap_pairs} without overlap"
    )
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
