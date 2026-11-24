"""Independent lunar DEM control-point validation.

The validator compares a declared control-point set with the bilinearly sampled
height from any EclipseKit lunar DEM reader. It never assumes that a dataset is
independent: the source manifest must explicitly state that it was withheld
from and not used to generate the DEM under test.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Literal

import numpy as np

from .lunar_coordinates import (
    LunarCoordinateTransform,
    LunarFrameTransform,
    LunarReferenceSphereTransform,
)

ValueInterpretation = Literal["height", "radius"]


def _finite_number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise TypeError(f"{name} must be a numeric value")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if positive and result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def _normalise_frame(value: str) -> str:
    """Normalise only documented aliases for the two built-in lunar frames."""
    key = "".join(character for character in value.casefold() if character.isalnum())
    aliases = {
        "moonpade440": "MOON_PA_DE440",
        "de440pa": "MOON_PA_DE440",
        "de440principalaxes": "MOON_PA_DE440",
        "moonprincipalaxesde440": "MOON_PA_DE440",
        "moonmede421": "MOON_ME_DE421",
        "de421me": "MOON_ME_DE421",
        "meanearthpoleraxisofde421": "MOON_ME_DE421",
        "meanearthpolaraxisofde421": "MOON_ME_DE421",
        "meanearthmeanrotationofde421": "MOON_ME_DE421",
        "de421meanearth": "MOON_ME_DE421",
    }
    return aliases.get(key, key)


@dataclass(frozen=True, slots=True)
class LunarControlPoint:
    """A single independently measured lunar surface control point."""

    point_id: str
    latitude_deg: float
    longitude_deg: float
    reference_height_m: float
    uncertainty_1sigma_m: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.point_id, str) or not self.point_id.strip():
            raise ValueError("point_id must be a non-empty string")
        object.__setattr__(self, "point_id", self.point_id.strip())
        latitude = _finite_number(self.latitude_deg, "latitude_deg")
        longitude = _finite_number(self.longitude_deg, "longitude_deg")
        height = _finite_number(self.reference_height_m, "reference_height_m")
        if not -90.0 <= latitude <= 90.0:
            raise ValueError("latitude_deg must be within [-90, 90]")
        object.__setattr__(self, "latitude_deg", latitude)
        object.__setattr__(self, "longitude_deg", longitude)
        object.__setattr__(self, "reference_height_m", height)
        if self.uncertainty_1sigma_m is not None:
            uncertainty = _finite_number(
                self.uncertainty_1sigma_m, "uncertainty_1sigma_m", positive=True
            )
            object.__setattr__(self, "uncertainty_1sigma_m", uncertainty)

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_id": self.point_id,
            "latitude_deg": self.latitude_deg,
            "longitude_deg": self.longitude_deg,
            "reference_height_m": self.reference_height_m,
            "uncertainty_1sigma_m": self.uncertainty_1sigma_m,
        }


@dataclass(frozen=True, slots=True)
class LunarControlPointSet:
    """Validated control-point dataset and its declared provenance.

    ``points`` always store heights above ``reference_radius_m``. The JSON
    loader converts raw radial-distance values to heights when the source file
    declares ``value_interpretation: radius``; direct constructors should pass
    already-normalised heights.
    """

    dataset_id: str
    title: str
    source_name: str
    source_uri: str
    source_doi: str | None
    independent_of_test_dem: bool
    independence_statement: str
    coordinate_system_name: str
    latitude_type: str
    longitude_direction: str
    longitude_domain: str
    vertical_datum: str
    reference_radius_m: float
    value_interpretation: ValueInterpretation
    points: tuple[LunarControlPoint, ...]
    source_sha256: str | None = None

    def __post_init__(self) -> None:
        text_fields = (
            "dataset_id", "title", "source_name", "source_uri",
            "independence_statement", "coordinate_system_name", "vertical_datum",
        )
        for field_name in text_fields:
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
            object.__setattr__(self, field_name, value.strip())
        if self.source_doi is not None and (
            not isinstance(self.source_doi, str) or not self.source_doi.strip()
        ):
            raise ValueError("source_doi must be None or a non-empty string")
        if not isinstance(self.independent_of_test_dem, bool):
            raise TypeError("independent_of_test_dem must be a boolean")
        if self.latitude_type != "planetocentric":
            raise ValueError("latitude_type must be 'planetocentric'; planetographic input is unsupported")
        if self.longitude_direction.casefold() != "east":
            raise ValueError("longitude_direction must be 'east'")
        if self.longitude_domain not in {"0_360", "-180_180"}:
            raise ValueError("longitude_domain must be '0_360' or '-180_180'")
        if self.value_interpretation not in {"height", "radius"}:
            raise ValueError("value_interpretation must be 'height' or 'radius'")
        radius = _finite_number(self.reference_radius_m, "reference_radius_m", positive=True)
        object.__setattr__(self, "reference_radius_m", radius)
        if not self.points:
            raise ValueError("control-point dataset must contain at least one point")
        if len({point.point_id for point in self.points}) != len(self.points):
            raise ValueError("control-point ids must be unique")
        if any(point.reference_height_m + radius <= 0.0 for point in self.points):
            raise ValueError("control-point absolute lunar-centre radius must be positive")
        for point in self.points:
            if self.longitude_domain == "0_360" and not 0.0 <= point.longitude_deg <= 360.0:
                raise ValueError(f"point {point.point_id!r} longitude is outside declared 0_360 domain")
            if self.longitude_domain == "-180_180" and not -180.0 <= point.longitude_deg <= 180.0:
                raise ValueError(f"point {point.point_id!r} longitude is outside declared -180_180 domain")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "dataset_id": self.dataset_id,
            "title": self.title,
            "source": {
                "name": self.source_name,
                "uri": self.source_uri,
                "doi": self.source_doi,
                "independent_of_test_dem": self.independent_of_test_dem,
                "independence_statement": self.independence_statement,
                "sha256": self.source_sha256,
            },
            "coordinates": {
                "coordinate_system_name": self.coordinate_system_name,
                "latitude_type": self.latitude_type,
                "longitude_direction": self.longitude_direction,
                "longitude_domain": self.longitude_domain,
                "vertical_datum": self.vertical_datum,
                "reference_radius_m": self.reference_radius_m,
                "value_interpretation": "height",
                "value_unit": "m",
            },
            "points": [point.to_dict() for point in self.points],
        }


def load_lunar_control_points(path: str | Path) -> LunarControlPointSet:
    """Load a version-1 JSON control-point set, hashing its original bytes."""
    source_path = Path(path).expanduser().resolve()
    raw_bytes = source_path.read_bytes()
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid UTF-8 JSON control-point file: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("control-point file must be a JSON object with schema_version=1")
    source = payload.get("source")
    coordinates = payload.get("coordinates")
    raw_points = payload.get("points")
    if not isinstance(source, dict) or not isinstance(coordinates, dict):
        raise ValueError("control-point file requires source and coordinates objects")
    if not isinstance(raw_points, list):
        raise ValueError("control-point file requires a points array")
    if coordinates.get("value_unit") != "m":
        raise ValueError("control-point values must explicitly use value_unit='m'")
    interpretation = coordinates.get("value_interpretation")
    if interpretation not in {"height", "radius"}:
        raise ValueError("coordinates.value_interpretation must be 'height' or 'radius'")
    reference_radius = _finite_number(
        coordinates.get("reference_radius_m"), "coordinates.reference_radius_m", positive=True
    )
    points: list[LunarControlPoint] = []
    for index, raw in enumerate(raw_points):
        if not isinstance(raw, dict):
            raise ValueError(f"points[{index}] must be an object")
        value = _finite_number(raw.get("value_m"), f"points[{index}].value_m")
        if interpretation == "radius":
            if value <= 0.0:
                raise ValueError(f"points[{index}].value_m must be a positive lunar-centre radius")
            value -= reference_radius
        points.append(
            LunarControlPoint(
                point_id=raw.get("point_id"),
                latitude_deg=raw.get("latitude_deg"),
                longitude_deg=raw.get("longitude_deg"),
                reference_height_m=value,
                uncertainty_1sigma_m=raw.get("uncertainty_1sigma_m"),
            )
        )
    return LunarControlPointSet(
        dataset_id=payload.get("dataset_id"),
        title=payload.get("title"),
        source_name=source.get("name"),
        source_uri=source.get("uri"),
        source_doi=source.get("doi"),
        independent_of_test_dem=source.get("independent_of_test_dem"),
        independence_statement=source.get("independence_statement"),
        coordinate_system_name=coordinates.get("coordinate_system_name"),
        latitude_type=coordinates.get("latitude_type"),
        longitude_direction=coordinates.get("longitude_direction"),
        longitude_domain=coordinates.get("longitude_domain"),
        vertical_datum=coordinates.get("vertical_datum"),
        reference_radius_m=reference_radius,
        value_interpretation=interpretation,
        points=tuple(points),
        source_sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )


@dataclass(frozen=True, slots=True)
class LunarControlPointRow:
    point_id: str
    latitude_deg: float
    longitude_deg: float
    reference_height_m: float
    dem_height_m: float | None
    residual_m: float | None
    uncertainty_1sigma_m: float | None
    standardized_residual: float | None
    status: str
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_id": self.point_id,
            "latitude_deg": self.latitude_deg,
            "longitude_deg": self.longitude_deg,
            "reference_height_m": self.reference_height_m,
            "dem_height_m": self.dem_height_m,
            "residual_dem_minus_reference_m": self.residual_m,
            "uncertainty_1sigma_m": self.uncertainty_1sigma_m,
            "standardized_residual": self.standardized_residual,
            "status": self.status,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class LunarDEMControlPointReport:
    status: str
    dataset_id: str
    dataset_title: str
    independent_of_test_dem: bool
    independence_statement: str
    tolerance_m: float
    source_sha256: str
    control_source: dict[str, Any]
    dem: dict[str, Any]
    coordinate_transform: dict[str, Any] | None
    rows: tuple[LunarControlPointRow, ...]
    metrics: dict[str, float | int | None]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        counts = {
            key: sum(row.status == key for row in self.rows)
            for key in ("PASS", "FAIL", "OUT_OF_COVERAGE", "ERROR")
        }
        return {
            "status": self.status,
            "dataset_id": self.dataset_id,
            "dataset_title": self.dataset_title,
            "independent_of_test_dem": self.independent_of_test_dem,
            "independence_statement": self.independence_statement,
            "tolerance_m": self.tolerance_m,
            "control_point_count": len(self.rows),
            "counts": counts,
            "control_source": self.control_source,
            "control_source_sha256": self.source_sha256,
            "dem": self.dem,
            "coordinate_transform": self.coordinate_transform,
            "metrics": self.metrics,
            "rows": [row.to_dict() for row in self.rows],
            "limitations": list(self.limitations),
        }


def _dem_metadata(dem: Any) -> tuple[str, str, float, dict[str, Any]]:
    info = getattr(dem, "product_info", None)
    if info is None:
        raise TypeError("dem must expose product_info metadata")
    frame = getattr(info, "coordinate_system_name", None)
    if frame is None:
        raise ValueError("DEM metadata does not declare coordinate_system_name")
    datum = getattr(info, "vertical_datum", None)
    if datum is None:
        metadata = getattr(dem, "metadata", None)
        datum = getattr(metadata, "vertical_datum", None)
    if not isinstance(datum, str) or not datum.strip():
        raise ValueError("DEM metadata does not declare a vertical datum")
    radius = _finite_number(getattr(info, "reference_radius_m", None), "DEM reference_radius_m", positive=True)
    if hasattr(info, "to_dict"):
        info_dict = info.to_dict()
    else:
        info_dict = {
            "coordinate_system_name": str(frame),
            "vertical_datum": datum,
            "reference_radius_m": radius,
        }
    return str(frame), datum, radius, info_dict


def _check_transform_metadata(
    control_points: LunarControlPointSet,
    dem_frame: str,
    dem_datum: str,
    dem_radius: float,
    coordinate_transform: LunarCoordinateTransform | None,
) -> None:
    if coordinate_transform is None:
        if _normalise_frame(control_points.coordinate_system_name) != _normalise_frame(dem_frame):
            raise ValueError(
                "control-point and DEM coordinate frames differ; supply an explicit LunarCoordinateTransform"
            )
        if control_points.vertical_datum.strip().casefold() != dem_datum.strip().casefold():
            raise ValueError(
                "control-point and DEM vertical datums differ; supply an explicit spherical datum transform"
            )
        if not math.isclose(control_points.reference_radius_m, dem_radius, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError(
                "control-point and DEM reference radii differ; supply an explicit spherical datum transform"
            )
        return

    if not isinstance(coordinate_transform, LunarCoordinateTransform):
        raise TypeError("coordinate_transform must be a LunarCoordinateTransform")
    frame_transform = coordinate_transform.frame_transform
    vertical_transform = coordinate_transform.vertical_transform
    if _normalise_frame(control_points.coordinate_system_name) != _normalise_frame(frame_transform.source_frame):
        raise ValueError("control-point frame does not match coordinate_transform source_frame")
    if _normalise_frame(dem_frame) != _normalise_frame(frame_transform.target_frame):
        raise ValueError("DEM frame does not match coordinate_transform target_frame")
    if not math.isclose(
        control_points.reference_radius_m,
        vertical_transform.source_reference_radius_m,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise ValueError("control-point reference radius does not match vertical transform source radius")
    if not math.isclose(
        dem_radius,
        vertical_transform.target_reference_radius_m,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise ValueError("DEM reference radius does not match vertical transform target radius")
    if control_points.vertical_datum.strip().casefold() != vertical_transform.source_vertical_datum.strip().casefold():
        raise ValueError("control-point vertical datum does not match transform source datum")
    if dem_datum.strip().casefold() != vertical_transform.target_vertical_datum.strip().casefold():
        raise ValueError("DEM vertical datum does not match transform target datum")


def validate_lunar_dem_control_points(
    dem: Any,
    control_points: LunarControlPointSet,
    *,
    tolerance_m: float,
    coordinate_transform: LunarCoordinateTransform | None = None,
) -> LunarDEMControlPointReport:
    """Compare independently measured heights with a DEM at the same points.

    Residual sign is ``DEM - reference``. The tolerance is explicit and does
    not get relaxed by the supplied uncertainty; uncertainties are reported as
    standardized residuals only.
    """
    tolerance = _finite_number(tolerance_m, "tolerance_m", positive=True)
    if not isinstance(control_points, LunarControlPointSet):
        raise TypeError("control_points must be a LunarControlPointSet")
    dem_frame, dem_datum, dem_radius, dem_info = _dem_metadata(dem)
    if not callable(getattr(dem, "predict_altitude_m", None)):
        raise TypeError("dem must provide predict_altitude_m(latitude_deg, longitude_deg)")
    _check_transform_metadata(control_points, dem_frame, dem_datum, dem_radius, coordinate_transform)

    rows: list[LunarControlPointRow] = []
    residuals: list[float] = []
    standardized: list[float] = []
    for point in control_points.points:
        latitude = point.latitude_deg
        longitude = point.longitude_deg
        reference_height = point.reference_height_m
        if coordinate_transform is not None:
            transformed = coordinate_transform.transform_point(latitude, longitude, reference_height)
            latitude = float(transformed.latitude_deg)
            longitude = float(transformed.longitude_deg)
            reference_height = float(transformed.height_above_reference_m)
        try:
            dem_height = _finite_number(
                dem.predict_altitude_m(latitude, longitude), f"DEM height at {point.point_id}"
            )
        except (ValueError, IndexError) as exc:
            message = f"{type(exc).__name__}: {exc}"
            message_lower = str(exc).casefold()
            sample_status = (
                "OUT_OF_COVERAGE"
                if "outside" in message_lower and "coverage" in message_lower
                else "ERROR"
            )
            rows.append(
                LunarControlPointRow(
                    point_id=point.point_id,
                    latitude_deg=latitude,
                    longitude_deg=longitude,
                    reference_height_m=reference_height,
                    dem_height_m=None,
                    residual_m=None,
                    uncertainty_1sigma_m=point.uncertainty_1sigma_m,
                    standardized_residual=None,
                    status=sample_status,
                    message=message,
                )
            )
            continue
        except Exception as exc:  # Preserve a per-point error rather than losing the whole report.
            rows.append(
                LunarControlPointRow(
                    point_id=point.point_id,
                    latitude_deg=latitude,
                    longitude_deg=longitude,
                    reference_height_m=reference_height,
                    dem_height_m=None,
                    residual_m=None,
                    uncertainty_1sigma_m=point.uncertainty_1sigma_m,
                    standardized_residual=None,
                    status="ERROR",
                    message=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        residual = dem_height - reference_height
        z_score = residual / point.uncertainty_1sigma_m if point.uncertainty_1sigma_m else None
        residuals.append(residual)
        if z_score is not None:
            standardized.append(z_score)
        rows.append(
            LunarControlPointRow(
                point_id=point.point_id,
                latitude_deg=latitude,
                longitude_deg=longitude,
                reference_height_m=reference_height,
                dem_height_m=dem_height,
                residual_m=residual,
                uncertainty_1sigma_m=point.uncertainty_1sigma_m,
                standardized_residual=z_score,
                status="PASS" if abs(residual) <= tolerance else "FAIL",
            )
        )

    values = np.asarray(residuals, dtype=np.float64)
    if values.size:
        absolute = np.abs(values)
        median = float(np.median(values))
        mad = float(np.median(np.abs(values - median)))
        metrics: dict[str, float | int | None] = {
            "evaluated_points": int(values.size),
            "mean_bias_m": float(np.mean(values)),
            "mean_absolute_error_m": float(np.mean(absolute)),
            "root_mean_square_error_m": float(np.sqrt(np.mean(values**2))),
            "median_absolute_error_m": float(np.median(absolute)),
            "normalised_median_absolute_deviation_m": float(1.4826 * mad),
            "percentile_95_absolute_error_m": float(np.percentile(absolute, 95)),
            "maximum_absolute_error_m": float(np.max(absolute)),
            "mean_absolute_standardized_residual": (
                float(np.mean(np.abs(standardized))) if standardized else None
            ),
        }
    else:
        metrics = {
            "evaluated_points": 0,
            "mean_bias_m": None,
            "mean_absolute_error_m": None,
            "root_mean_square_error_m": None,
            "median_absolute_error_m": None,
            "normalised_median_absolute_deviation_m": None,
            "percentile_95_absolute_error_m": None,
            "maximum_absolute_error_m": None,
            "mean_absolute_standardized_residual": None,
        }
    if not control_points.independent_of_test_dem:
        status = "NOT_INDEPENDENT"
    elif any(row.status == "FAIL" for row in rows):
        status = "FAIL"
    elif not rows or any(row.status in {"OUT_OF_COVERAGE", "ERROR"} for row in rows):
        status = "PARTIAL"
    else:
        status = "PASS"

    return LunarDEMControlPointReport(
        status=status,
        dataset_id=control_points.dataset_id,
        dataset_title=control_points.title,
        independent_of_test_dem=control_points.independent_of_test_dem,
        independence_statement=control_points.independence_statement,
        tolerance_m=tolerance,
        source_sha256=control_points.source_sha256 or "not-available",
        control_source={
            "name": control_points.source_name,
            "uri": control_points.source_uri,
            "doi": control_points.source_doi,
            "coordinate_system_name": control_points.coordinate_system_name,
            "latitude_type": control_points.latitude_type,
            "longitude_direction": control_points.longitude_direction,
            "longitude_domain": control_points.longitude_domain,
            "vertical_datum": control_points.vertical_datum,
            "reference_radius_m": control_points.reference_radius_m,
            "value_interpretation": control_points.value_interpretation,
        },
        dem={"product_info": dem_info, "coordinate_system_name": dem_frame,
             "vertical_datum": dem_datum, "reference_radius_m": dem_radius},
        coordinate_transform=coordinate_transform.to_dict() if coordinate_transform else None,
        rows=tuple(rows),
        metrics=metrics,
        limitations=(
            "A PASS is valid only if the control source is genuinely independent of the DEM under test; "
            "the independence declaration is supplied by the dataset curator and is not inferred by EclipseKit.",
            "The tolerance is a caller-supplied acceptance threshold and must be justified from the "
            "control-source uncertainty, DEM resolution and intended application.",
            "DEM values are bilinearly interpolated; footprint mismatch, slope-dependent sampling, "
            "co-registration error and temporal surface changes are not separately corrected.",
            "Provided 1-sigma uncertainties are used only to report standardized residuals; they do "
            "not change the absolute acceptance tolerance.",
            "The validator compares point elevations only. It does not assess full-raster completeness, "
            "horizontal accuracy, geoid/ellipsoid differences or temporal lunar orientation.",
        ),
    )


def write_lunar_dem_control_point_report(
    report: LunarDEMControlPointReport, output_dir: str | Path
) -> tuple[Path, Path]:
    directory = Path(output_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "lunar-dem-control-point-validation.json"
    markdown_path = directory / "lunar-dem-control-point-validation.md"
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    counts = report.to_dict()["counts"]
    lines = [
        "# EclipseKit independent lunar DEM control-point validation",
        "",
        f"**Status:** {report.status}",
        f"**Control dataset:** `{report.dataset_id}` — {report.dataset_title}",
        f"**Independent of test DEM:** {report.independent_of_test_dem}",
        f"**Acceptance tolerance:** {report.tolerance_m:.6f} m",
        f"**Points:** {len(report.rows)} total; {counts['PASS']} PASS / {counts['FAIL']} FAIL / "
        f"{counts['OUT_OF_COVERAGE']} OUT_OF_COVERAGE / {counts['ERROR']} ERROR",
        "",
        "## Vertical residual metrics",
        "",
        "Residual = DEM − reference; positive values indicate the DEM is higher.",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, label in (
        ("mean_bias_m", "Mean bias (m)"),
        ("mean_absolute_error_m", "Mean absolute error (m)"),
        ("root_mean_square_error_m", "RMSE (m)"),
        ("median_absolute_error_m", "Median absolute error (m)"),
        ("normalised_median_absolute_deviation_m", "Normalised MAD (m)"),
        ("percentile_95_absolute_error_m", "95th percentile absolute error (m)"),
        ("maximum_absolute_error_m", "Maximum absolute error (m)"),
    ):
        value = report.metrics[key]
        lines.append(f"| {label} | {'not available' if value is None else f'{value:.6f}'} |")
    lines.extend(
        [
            "",
            "## Point-by-point results",
            "",
            "| Point | Latitude (°) | Longitude (°) | Reference (m) | DEM (m) | Residual (m) | Status |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in report.rows:
        dem_value = "—" if row.dem_height_m is None else f"{row.dem_height_m:.4f}"
        residual = "—" if row.residual_m is None else f"{row.residual_m:.4f}"
        lines.append(
            f"| {row.point_id} | {row.latitude_deg:.6f} | {row.longitude_deg:.6f} | "
            f"{row.reference_height_m:.4f} | {dem_value} | {residual} | {row.status} |"
        )
    lines.extend(["", "## Source and provenance", "", f"- Source: {report.control_source['name']}"])
    if report.control_source.get("doi"):
        lines.append(f"- DOI: {report.control_source['doi']}")
    lines.extend(
        [
            f"- Source URI: {report.control_source['uri']}",
            f"- SHA-256 of control file: `{report.source_sha256}`",
            f"- Independence statement: {report.independence_statement}",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report.limitations)
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def _make_builtin_transform(
    point_set: LunarControlPointSet,
    dem: Any,
    choice: str,
) -> LunarCoordinateTransform | None:
    if choice == "none":
        return None
    dem_frame, dem_datum, dem_radius, _ = _dem_metadata(dem)
    if choice == "de440-pa-to-de421-me":
        frame_transform = LunarFrameTransform.de440_pa_to_de421_me()
    elif choice == "de421-me-to-de440-pa":
        frame_transform = LunarFrameTransform.de440_pa_to_de421_me().inverse()
    else:
        raise ValueError(f"Unsupported frame transform: {choice}")
    # Metadata compatibility is verified by the validator before any samples run.
    del dem_frame
    vertical_transform = LunarReferenceSphereTransform(
        source_reference_radius_m=point_set.reference_radius_m,
        target_reference_radius_m=dem_radius,
        source_vertical_datum=point_set.vertical_datum,
        target_vertical_datum=dem_datum,
    )
    return LunarCoordinateTransform(frame_transform, vertical_transform)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a lunar DEM against an independently sourced control-point set."
    )
    parser.add_argument("--format", choices=("pds3", "pds4", "geotiff", "jp2"), required=True)
    parser.add_argument("--dem", required=True, help="DEM image/raster path")
    parser.add_argument("--label", help="Detached PDS3 label or PDS4 XML label")
    parser.add_argument("--control-points", required=True, help="Version-1 JSON control-point dataset")
    parser.add_argument("--tolerance-m", type=float, required=True)
    parser.add_argument(
        "--frame-transform",
        choices=("none", "de440-pa-to-de421-me", "de421-me-to-de440-pa"),
        default="none",
    )
    parser.add_argument("--coordinate-system-name")
    parser.add_argument("--reference-radius-m", type=float)
    parser.add_argument("--vertical-datum")
    parser.add_argument("--value-interpretation", choices=("height", "radius"))
    parser.add_argument("--value-unit")
    parser.add_argument("--bounds", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--coordinates-in-degrees", action="store_true")
    parser.add_argument("--tile-size", type=int, default=512)
    parser.add_argument("--cache-tiles", type=int, default=8)
    parser.add_argument("--output-dir", default="reports/phase9_4")
    args = parser.parse_args(argv)

    from .topography import open_pds3_lunar_dem
    from .topography_formats import open_geotiff_lunar_dem, open_jp2_lunar_dem, open_pds4_lunar_dem

    dem = None
    try:
        points = load_lunar_control_points(args.control_points)
        if args.format == "pds3":
            dem = open_pds3_lunar_dem(
                args.dem, args.label, expected_reference_radius_m=None,
                tile_shape=args.tile_size, cache_tiles=args.cache_tiles,
            )
        elif args.format == "pds4":
            label_path = args.label or args.dem
            image_path = None if label_path == args.dem else args.dem
            dem = open_pds4_lunar_dem(
                label_path, image_path, expected_reference_radius_m=None,
                tile_shape=args.tile_size, cache_tiles=args.cache_tiles,
            )
        else:
            kwargs = {
                "coordinate_system_name": args.coordinate_system_name,
                "reference_radius_m": args.reference_radius_m,
                "vertical_datum": args.vertical_datum,
                "value_interpretation": args.value_interpretation,
                "value_unit": args.value_unit,
                "bounds": tuple(args.bounds) if args.bounds else None,
                "coordinates_in_degrees": args.coordinates_in_degrees,
                "tile_shape": args.tile_size,
                "cache_tiles": args.cache_tiles,
            }
            dem = (
                open_geotiff_lunar_dem(args.dem, **kwargs)
                if args.format == "geotiff"
                else open_jp2_lunar_dem(args.dem, **kwargs)
            )
        transform = _make_builtin_transform(points, dem, args.frame_transform)
        report = validate_lunar_dem_control_points(
            dem, points, tolerance_m=args.tolerance_m, coordinate_transform=transform
        )
        json_path, markdown_path = write_lunar_dem_control_point_report(report, args.output_dir)
    except (OSError, ImportError, TypeError, ValueError) as exc:
        parser.exit(2, f"Lunar DEM control-point validation could not complete: {type(exc).__name__}: {exc}\n")
    finally:
        if dem is not None:
            dem.close()

    counts = report.to_dict()["counts"]
    print(f"Status: {report.status}")
    print(
        f"Points: {len(report.rows)} total; {counts['PASS']} PASS / {counts['FAIL']} FAIL / "
        f"{counts['OUT_OF_COVERAGE']} OUT_OF_COVERAGE / {counts['ERROR']} ERROR"
    )
    print(f"RMSE: {report.metrics['root_mean_square_error_m']}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
