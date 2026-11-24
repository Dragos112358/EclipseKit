"""Published-coordinate consistency audit for the DE440 PA / DE421 ME rotation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .lunar_coordinates import LunarFrameTransform

# XYZ values, in metres, transcribed from Table 1 of Park et al. (2021).
# The table is paired with the fixed frame rotation in Equation (19).
_REFERENCE_POINTS = (
    (
        "Apollo 11",
        (1_591_967.049, 690_698.573, 21_004.461),
        (1_591_747.649, 691_222.200, 20_398.110),
    ),
    (
        "Apollo 14",
        (1_652_689.369, -520_998.431, -109_729.869),
        (1_652_818.682, -520_454.587, -110_361.165),
    ),
    (
        "Apollo 15",
        (1_554_678.104, 98_094.498, 765_005.863),
        (1_554_937.504, 98_604.886, 764_412.810),
    ),
    (
        "Lunokhod 2",
        (1_339_363.598, 801_870.995, 756_359.260),
        (1_339_388.213, 802_310.527, 755_849.393),
    ),
    (
        "Lunokhod 1",
        (1_114_291.452, -781_299.273, 1_076_059.049),
        (1_114_958.865, -780_934.127, 1_075_632.692),
    ),
)


@dataclass(frozen=True, slots=True)
class LunarFrameAuditRow:
    point_name: str
    expected_xyz_m: tuple[float, float, float]
    transformed_xyz_m: tuple[float, float, float]
    residual_m: float
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_name": self.point_name,
            "expected_xyz_m": list(self.expected_xyz_m),
            "transformed_xyz_m": list(self.transformed_xyz_m),
            "residual_m": self.residual_m,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class LunarFrameAuditReport:
    status: str
    source_frame: str
    target_frame: str
    tolerance_m: float
    rows: tuple[LunarFrameAuditRow, ...]
    mean_residual_m: float
    rms_residual_m: float
    maximum_residual_m: float
    transform: dict[str, Any]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_frame": self.source_frame,
            "target_frame": self.target_frame,
            "tolerance_m": self.tolerance_m,
            "summary": {
                "reference_points": len(self.rows),
                "passed_points": sum(row.status == "PASS" for row in self.rows),
                "failed_points": sum(row.status != "PASS" for row in self.rows),
                "mean_residual_m": self.mean_residual_m,
                "rms_residual_m": self.rms_residual_m,
                "maximum_residual_m": self.maximum_residual_m,
            },
            "rows": [row.to_dict() for row in self.rows],
            "transform": self.transform,
            "limitations": list(self.limitations),
        }


def validate_de440_pa_to_de421_me(*, tolerance_m: float = 0.01) -> LunarFrameAuditReport:
    """Reconstruct the five published Table 1 reflector coordinates."""
    if isinstance(tolerance_m, bool) or not isinstance(tolerance_m, (int, float)):
        raise TypeError("tolerance_m must be a finite positive number")
    tolerance = float(tolerance_m)
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("tolerance_m must be a finite positive number")

    transform = LunarFrameTransform.de440_pa_to_de421_me()
    rows: list[LunarFrameAuditRow] = []
    residuals: list[float] = []
    for name, source_xyz, expected_xyz in _REFERENCE_POINTS:
        actual = transform.transform_cartesian(source_xyz)
        residual = float(np.linalg.norm(actual - np.asarray(expected_xyz, dtype=np.float64)))
        residuals.append(residual)
        rows.append(
            LunarFrameAuditRow(
                point_name=name,
                expected_xyz_m=expected_xyz,
                transformed_xyz_m=tuple(float(value) for value in actual),
                residual_m=residual,
                status="PASS" if residual <= tolerance else "FAIL",
            )
        )
    residual_array = np.asarray(residuals, dtype=np.float64)
    passed = all(row.status == "PASS" for row in rows)
    return LunarFrameAuditReport(
        status="PASS" if passed else "FAIL",
        source_frame=transform.source_frame,
        target_frame=transform.target_frame,
        tolerance_m=tolerance,
        rows=tuple(rows),
        mean_residual_m=float(np.mean(residual_array)),
        rms_residual_m=float(np.sqrt(np.mean(residual_array**2))),
        maximum_residual_m=float(np.max(residual_array)),
        transform=transform.to_dict(),
        limitations=(
            "This is an implementation-consistency check against the five paired reflector coordinates "
            "published with the fitted rotation; it is not an independent geodetic validation.",
            "The DE440 PA to DE421 ME/MER rotation is fixed and does not model time-dependent lunar libration.",
            "No complete DEM raster is warped, resampled or rewritten by this audit.",
            "Vertical conversion is valid only for explicitly declared spherical reference radii; it does "
            "not convert a lunar geoid or ellipsoidal datum.",
        ),
    )


def write_lunar_frame_audit_report(
    report: LunarFrameAuditReport, output_dir: str | Path
) -> tuple[Path, Path]:
    directory = Path(output_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "lunar-frame-transform-audit.json"
    markdown_path = directory / "lunar-frame-transform-audit.md"
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# EclipseKit lunar frame-transform audit",
        "",
        f"**Status:** {report.status}",
        f"**Transform:** `{report.source_frame}` → `{report.target_frame}`",
        f"**Reference-point tolerance:** {report.tolerance_m:.6f} m",
        f"**Reference points:** {sum(row.status == 'PASS' for row in report.rows)} PASS / "
        f"{sum(row.status != 'PASS' for row in report.rows)} FAIL",
        f"**Mean / RMS / maximum residual:** {report.mean_residual_m:.9f} / "
        f"{report.rms_residual_m:.9f} / {report.maximum_residual_m:.9f} m",
        "",
        "## Published reflector-coordinate reconstruction",
        "",
        "| Point | Residual (m) | Status |",
        "|---|---:|---|",
    ]
    lines.extend(
        f"| {row.point_name} | {row.residual_m:.9f} | {row.status} |" for row in report.rows
    )
    lines.extend(
        [
            "",
            "## Provenance",
            "",
            report.transform["provenance"],
            "",
            f"Reference: {report.transform['reference_url']}",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report.limitations)
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit the published fixed DE440 PA to DE421 ME lunar-frame rotation."
    )
    parser.add_argument("--tolerance-m", type=float, default=0.01)
    parser.add_argument("--output-dir", default="reports/phase9_3")
    args = parser.parse_args(argv)
    try:
        report = validate_de440_pa_to_de421_me(tolerance_m=args.tolerance_m)
        json_path, markdown_path = write_lunar_frame_audit_report(report, args.output_dir)
    except (OSError, TypeError, ValueError) as exc:
        parser.exit(2, f"Lunar frame audit could not complete: {type(exc).__name__}: {exc}\n")
    print(f"Status: {report.status}")
    print(
        f"Reference points: {sum(row.status == 'PASS' for row in report.rows)} PASS / "
        f"{sum(row.status != 'PASS' for row in report.rows)} FAIL"
    )
    print(f"Maximum residual: {report.maximum_residual_m:.9f} m")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
