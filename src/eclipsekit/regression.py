"""Deterministic scientific and numerical regression checks for EclipseKit."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
from typing import Any, Sequence

import numpy as np

from . import __version__
from .contacts import brent_root, solve_root
from .geometry import ecef_to_geodetic, wgs84_geodetic_to_ecef, wgs84_inverse
from .topography_validation import validate_pds3_lunar_dem
from .uncertainty import (
    UncertaintyBudget,
    propagate_uncertainty,
)
from .validation_framework import run_besselian_reference_validation


def _check(
    name: str,
    passed: bool,
    *,
    expected: Any = None,
    actual: Any = None,
    tolerance: Any = None,
    details: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "status": "PASS" if passed else "FAIL",
        "expected": expected,
        "actual": actual,
        "tolerance": tolerance,
        "details": details,
    }


def _run_numerical_checks() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    distance, azimuth = wgs84_inverse(0.0, 0.0, 0.0, 1.0)
    expected_distance = 111.31949079327357
    checks.append(_check(
        "wgs84_equatorial_one_degree",
        abs(distance - expected_distance) <= 1.0e-8 and abs(azimuth - 90.0) <= 1.0e-10,
        expected={"distance_km": expected_distance, "initial_azimuth_deg": 90.0},
        actual={"distance_km": distance, "initial_azimuth_deg": azimuth},
        tolerance={"distance_km": 1.0e-8, "initial_azimuth_deg": 1.0e-10},
        details="WGS84 inverse solution along the equator.",
    ))

    anti_distance, anti_azimuth = wgs84_inverse(0.0, 179.0, 0.0, -179.0)
    anti_expected = 222.638981586547
    checks.append(_check(
        "wgs84_antimeridian_two_degrees",
        abs(anti_distance - anti_expected) <= 1.0e-7 and abs(anti_azimuth - 90.0) <= 1.0e-8,
        expected={"distance_km": anti_expected, "initial_azimuth_deg": 90.0},
        actual={"distance_km": anti_distance, "initial_azimuth_deg": anti_azimuth},
        tolerance={"distance_km": 1.0e-7, "initial_azimuth_deg": 1.0e-8},
        details="Short geodesic crossing the ±180-degree longitude seam.",
    ))

    original = (44.40372, -121.62166, 1250.0)
    xyz = wgs84_geodetic_to_ecef(*original)
    recovered = ecef_to_geodetic(*xyz)
    lat_error = abs(recovered[0] - original[0])
    lon_delta = (recovered[1] - original[1] + 180.0) % 360.0 - 180.0
    lon_error = abs(lon_delta)
    height_error = abs(recovered[2] - original[2])
    checks.append(_check(
        "wgs84_ecef_geodetic_round_trip",
        lat_error <= 1.0e-10 and lon_error <= 1.0e-10 and height_error <= 1.0e-5,
        expected={"latitude_deg": original[0], "longitude_deg": original[1], "elevation_m": original[2]},
        actual={"latitude_deg": recovered[0], "longitude_deg": recovered[1], "elevation_m": recovered[2]},
        tolerance={"latitude_deg": 1.0e-10, "longitude_deg": 1.0e-10, "elevation_m": 1.0e-5},
        details="Forward/inverse WGS84 coordinate conversion.",
    ))

    root = brent_root(lambda value: value**3 - 2.0, 0.0, 2.0)
    residual = abs(root.root**3 - 2.0) if root.root is not None else math.inf
    checks.append(_check(
        "brent_root_cubic_reference",
        root.converged and root.root is not None and residual <= 1.0e-10,
        expected={"root": 2.0 ** (1.0 / 3.0), "absolute_residual_max": 1.0e-10},
        actual={"root": root.root, "absolute_residual": residual, "iterations": root.iterations},
        tolerance={"absolute_residual": 1.0e-10},
        details="Safeguarded Brent solver against a closed-form cubic root.",
    ))

    tangent = solve_root(
        lambda value: (value - 0.25) ** 2,
        -1.0, 1.0, method="brent", detect_tangent=True,
        tangent_value_tolerance=1.0e-10,
    )
    tangent_error = abs(tangent.root - 0.25) if tangent.root is not None else math.inf
    checks.append(_check(
        "root_solver_tangent_contact_case",
        tangent.converged and tangent.root is not None and tangent_error <= 1.0e-5,
        expected={"root": 0.25, "absolute_root_error_max": 1.0e-5},
        actual={"root": tangent.root, "absolute_root_error": tangent_error, "status": tangent.status},
        tolerance={"absolute_root_error": 1.0e-5},
        details="Near-tangent zero without a sign change; exercises tangent detection.",
    ))

    polar_distance, polar_azimuth = wgs84_inverse(89.9, -45.0, -89.9, 135.0)
    checks.append(_check(
        "wgs84_near_antipodal_fallback_stability",
        math.isfinite(polar_distance) and math.isfinite(polar_azimuth)
        and 0.0 < polar_distance < 21_000.0 and 0.0 <= polar_azimuth < 360.0,
        expected="finite distance in (0, 21000) km and azimuth in [0, 360)",
        actual={"distance_km": polar_distance, "initial_azimuth_deg": polar_azimuth},
        details="Near-antipodal high-latitude stress case; checks stable finite fallback behaviour.",
    ))

    julian_epoch = 2_460_000.5034567
    julian_root = brent_root(
        lambda value: (value - julian_epoch) * 86400.0,
        2_460_000.49, 2_460_000.51,
        tolerance_days=1.0e-9, value_tolerance=1.0e-7,
    )
    julian_error_seconds = (
        abs(julian_root.root - julian_epoch) * 86400.0
        if julian_root.root is not None else math.inf
    )
    checks.append(_check(
        "root_solver_julian_day_scale",
        julian_root.converged and julian_root.root is not None and julian_error_seconds <= 1.0e-4,
        expected={"root_jd": julian_epoch, "absolute_time_error_seconds_max": 1.0e-4},
        actual={"root_jd": julian_root.root, "absolute_time_error_seconds": julian_error_seconds},
        tolerance={"absolute_time_error_seconds": 1.0e-4},
        details="Root solver at Julian-day magnitude to guard floating-point time-scale regressions.",
    ))

    budget = UncertaintyBudget.from_standard_deviations(
        ("x", "y"), (0.2, 0.3), units=("m", "s"),
        correlation=((1.0, 0.25), (0.25, 1.0)),
        source_descriptions=("synthetic regression inputs",),
    )
    linear = propagate_uncertainty(
        lambda values: (2.0 * values[0] + values[1], values[0] - values[1]),
        (1.0, 2.0), budget,
    )
    expected_covariance = np.array([[0.31, -0.025], [-0.025, 0.10]])
    actual_covariance = np.asarray(linear.covariance, dtype=float)
    covariance_error = float(np.max(np.abs(actual_covariance - expected_covariance)))
    checks.append(_check(
        "uncertainty_correlated_linear_covariance",
        covariance_error <= 1.0e-10,
        expected=expected_covariance.tolist(), actual=actual_covariance.tolist(),
        tolerance=1.0e-10,
        details="Linear transform with a non-zero input correlation; full covariance retained.",
    ))

    monte_a = propagate_uncertainty(
        lambda values: (values[0] ** 2,), (1.5,),
        UncertaintyBudget.from_standard_deviations(("x",), (0.1,)),
        method="monte_carlo", samples=4000, seed=20261122,
    )
    monte_b = propagate_uncertainty(
        lambda values: (values[0] ** 2,), (1.5,),
        UncertaintyBudget.from_standard_deviations(("x",), (0.1,)),
        method="monte_carlo", samples=4000, seed=20261122,
    )
    reproducible = monte_a.mean == monte_b.mean and monte_a.covariance == monte_b.covariance
    checks.append(_check(
        "monte_carlo_seed_reproducibility",
        reproducible,
        expected="identical means and covariance for identical seed and inputs",
        actual={"mean": monte_a.mean, "covariance": monte_a.covariance},
        details="Fixed synthetic inputs and fixed seed; not a claim about physical uncertainty accuracy.",
    ))
    return checks


def run_scientific_regression_suite(
    *,
    reference_file: str | Path | None = None,
    dem_image: str | Path | None = None,
    dem_label: str | Path | None = None,
    expected_coordinate_system: str | None = None,
) -> dict[str, Any]:
    """Run reproducible numerical anchors and the published NASA Besselian case.

    A supplied DEM is subjected to the PDS3 structural/sample validator. Live
    ephemeris path/corridor comparisons are deliberately not run here because
    they require an independently selected BSP kernel and explicit EOP policy.
    """
    checks = _run_numerical_checks()
    base_dir = Path.cwd()
    if reference_file is None:
        candidate = base_dir / "data" / "validation" / "besselian_1999_reference.json"
        reference_path = candidate if candidate.is_file() else None
    else:
        reference_path = Path(reference_file).expanduser()
    if reference_path is None:
        checks.append({
            "name": "nasa_1999_besselian_reference",
            "status": "NOT_RUN",
            "details": "Reference fixture is not available; supply --reference-file.",
        })
    else:
        try:
            result = run_besselian_reference_validation(reference_path)
            checks.append({
                "name": "nasa_1999_besselian_reference",
                "status": result["status"],
                "details": "Published NASA 1999 Besselian-elements regression.",
                "source_url": result.get("source_url"),
                "checks": result.get("checks", {}),
                "warnings": result.get("warnings", []),
            })
        except Exception as exc:
            checks.append({
                "name": "nasa_1999_besselian_reference",
                "status": "ERROR",
                "details": f"{type(exc).__name__}: {exc}",
            })

    if (dem_image is None) != (dem_label is None):
        checks.append({
            "name": "real_lunar_dem_structural_validation",
            "status": "ERROR",
            "details": "Both --dem-image and --dem-label must be provided together.",
        })
    elif dem_image is not None and dem_label is not None:
        try:
            dem_report = validate_pds3_lunar_dem(
                dem_image, dem_label,
                expected_coordinate_system=expected_coordinate_system,
            )
            checks.append({
                "name": "real_lunar_dem_structural_validation",
                "status": dem_report.status,
                "details": "PDS3 label, binary-layout and deterministic interpolation sample checks only.",
                "passed_samples": dem_report.passed_samples,
                "failed_samples": dem_report.failed_samples,
                "product_info": dem_report.product_info,
                "notes": list(dem_report.notes),
            })
        except Exception as exc:
            checks.append({
                "name": "real_lunar_dem_structural_validation",
                "status": "ERROR",
                "details": f"{type(exc).__name__}: {exc}",
            })
    else:
        checks.append({
            "name": "real_lunar_dem_structural_validation",
            "status": "NOT_RUN",
            "details": "No real DEM paths supplied; synthetic PDS3 parser tests remain in the unit suite.",
        })

    checks.append({
        "name": "live_de440s_path_and_shadow_corridor_regressions",
        "status": "NOT_RUN",
        "details": (
            "Requires an explicitly selected local BSP kernel, Earth-orientation data policy, "
            "and separate path/corridor reference tolerances. This command does not infer them."
        ),
    })
    statuses = [item["status"] for item in checks]
    if any(status in {"FAIL", "ERROR"} for status in statuses):
        overall = "FAIL"
    elif any(status == "NOT_RUN" for status in statuses):
        overall = "PARTIAL"
    else:
        overall = "PASS"
    return {
        "schema_version": 1,
        "suite": "EclipseKit Phase 7.7 scientific regression",
        "status": overall,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "eclipsekit_version": __version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "checks": checks,
        "summary": {
            "passed": sum(status == "PASS" for status in statuses),
            "failed": sum(status in {"FAIL", "ERROR"} for status in statuses),
            "not_run": sum(status == "NOT_RUN" for status in statuses),
        },
        "limitations": [
            "The NASA 1999 case validates one published-element event, not every eclipse.",
            "Live DE440s global-path and 2017 corridor regressions require an explicit BSP/EOP setup.",
            "A PDS3 DEM PASS validates product structure and selected interpolation samples, not global accuracy.",
            "Synthetic uncertainty checks validate numerical propagation and repeatability, not input uncertainty provenance.",
        ],
    }


def regression_report_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# EclipseKit Phase 7.7 scientific regression",
        "",
        f"- **Status:** **{report['status']}**",
        f"- **Generated (UTC):** `{report['generated_utc']}`",
        f"- **EclipseKit:** `{report['eclipsekit_version']}`",
        f"- **Python:** `{report['python_version']}`",
        f"- **Platform:** `{report['platform']}`",
        f"- **Summary:** {report['summary']['passed']} PASS / {report['summary']['failed']} FAIL / {report['summary']['not_run']} NOT RUN",
        "",
        "| Check | Status | Details |",
        "|---|---|---|",
    ]
    for item in report["checks"]:
        detail = str(item.get("details", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {item['name']} | {item['status']} | {detail} |")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report.get("limitations", []))
    nasa = next((item for item in report["checks"] if item.get("name") == "nasa_1999_besselian_reference"), None)
    if nasa and nasa.get("checks"):
        lines.extend(["", "## NASA 1999 Besselian detail", "", "| Sub-check | Status |", "|---|---|"])
        for name, item in nasa["checks"].items():
            lines.append(f"| {name} | {'PASS' if item.get('passed') else 'FAIL'} |")
    return "\n".join(lines) + "\n"


def write_regression_report(report: dict[str, Any], output_dir: str | Path, *, stem: str = "regression") -> tuple[Path, Path]:
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise ValueError("report must be a schema_version 1 regression report")
    if not stem or Path(stem).name != stem or stem in {".", ".."}:
        raise ValueError("stem must be a simple filename without directory components")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{stem}.json"
    markdown_path = directory / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    markdown_path.write_text(regression_report_to_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run EclipseKit numerical and scientific regression checks.")
    parser.add_argument("--reference-file", type=Path)
    parser.add_argument("--dem-image", type=Path)
    parser.add_argument("--dem-label", type=Path)
    parser.add_argument("--expected-coordinate-system")
    parser.add_argument("--output-dir", type=Path, default=Path("reports/phase7_7"))
    parser.add_argument("--stem", default="scientific-regression")
    args = parser.parse_args(argv)
    try:
        report = run_scientific_regression_suite(
            reference_file=args.reference_file,
            dem_image=args.dem_image,
            dem_label=args.dem_label,
            expected_coordinate_system=args.expected_coordinate_system,
        )
        json_path, markdown_path = write_regression_report(report, args.output_dir, stem=args.stem)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"EclipseKit regression suite could not complete: {exc}\n")
    print(f"Scientific regression: {report['status']}")
    print(
        f"Checks: {report['summary']['passed']} PASS / {report['summary']['failed']} FAIL / "
        f"{report['summary']['not_run']} NOT RUN"
    )
    for item in report["checks"]:
        print(f"{item['status']}: {item['name']}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
