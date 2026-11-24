"""Independent reference-table checks for global shadow corridors."""
from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .geometry import wgs84_inverse
from .timeutils import time_to_utc_iso


@dataclass(frozen=True, slots=True)
class CorridorReferenceRow:
    time_utc: datetime
    north_latitude_deg: float
    north_longitude_deg: float
    south_latitude_deg: float
    south_longitude_deg: float
    center_latitude_deg: float
    center_longitude_deg: float
    path_width_km: float
    central_duration_seconds: float


@dataclass(frozen=True, slots=True)
class CorridorValidationRow:
    time_utc: str
    matched_time_utc: str | None
    time_offset_seconds: float | None
    center_error_km: float | None
    maximum_boundary_error_km: float | None
    width_error_km: float | None
    duration_error_seconds: float | None
    status: str
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CorridorValidationReport:
    source_id: str
    status: str
    reference_count: int
    passed_count: int
    failed_count: int
    mean_center_error_km: float | None
    maximum_center_error_km: float | None
    mean_boundary_error_km: float | None
    maximum_boundary_error_km: float | None
    mean_width_error_km: float | None
    maximum_width_error_km: float | None
    mean_duration_error_seconds: float | None
    maximum_duration_error_seconds: float | None
    coordinate_tolerance_km: float
    width_tolerance_km: float
    duration_tolerance_seconds: float
    max_time_offset_seconds: float
    rows: tuple[CorridorValidationRow, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rows"] = [row.to_dict() for row in self.rows]
        return payload

    def to_markdown(self) -> str:
        lines = [
            "# Shadow corridor validation", "", f"- **Source:** `{self.source_id}`",
            f"- **Status:** **{self.status}**",
            f"- **Reference rows:** {self.reference_count} ({self.passed_count} PASS / {self.failed_count} FAIL)",
            f"- **Coordinate tolerance:** {self.coordinate_tolerance_km:.2f} km",
            f"- **Width tolerance:** {self.width_tolerance_km:.2f} km",
            f"- **Duration tolerance:** {self.duration_tolerance_seconds:.2f} s",
            f"- **Time matching tolerance:** {self.max_time_offset_seconds:.2f} s", "",
            "| Reference time | Δt (s) | Center error (km) | Max edge error (km) | Width error (km) | Duration error (s) | Status |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
        def fmt(value: float | None, digits: int = 3) -> str:
            return "—" if value is None else f"{value:.{digits}f}"

        for row in self.rows:
            lines.append(
                f"| {row.time_utc} | {fmt(row.time_offset_seconds, 2)} | "
                f"{fmt(row.center_error_km)} | {fmt(row.maximum_boundary_error_km)} | "
                f"{fmt(row.width_error_km)} | {fmt(row.duration_error_seconds)} | {row.status} |"
            )
            if row.message:
                lines.append(f"\n  Note: {row.message}")
        lines += ["", "This sparse reference check does not validate the complete penumbral sunrise/sunset footprint or terrain effects."]
        return "\n".join(lines) + "\n"


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("time_utc must be a non-empty ISO-8601 string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        value_dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 time: {value!r}") from exc
    if value_dt.tzinfo is None or value_dt.utcoffset() is None:
        raise ValueError("reference time must include an explicit UTC offset")
    return value_dt.astimezone(timezone.utc)


def load_corridor_reference_csv(filename: str | Path) -> list[CorridorReferenceRow]:
    required = {
        "time_utc", "north_latitude_deg", "north_longitude_deg", "south_latitude_deg",
        "south_longitude_deg", "center_latitude_deg", "center_longitude_deg",
        "path_width_km", "central_duration_seconds",
    }
    result = []
    with Path(filename).expanduser().open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"reference CSV is missing columns: {', '.join(sorted(missing))}")
        previous = None
        for line, raw in enumerate(reader, start=2):
            try:
                moment = _parse_time(raw["time_utc"])
                if previous is not None and moment <= previous:
                    raise ValueError("timestamps must be strictly increasing")
                values = {name: float(raw[name]) for name in required - {"time_utc"}}
                if not all(math.isfinite(value) for value in values.values()):
                    raise ValueError("numeric fields must be finite")
                for label in ("north", "south", "center"):
                    if not -90 <= values[f"{label}_latitude_deg"] <= 90:
                        raise ValueError(f"{label} latitude is outside WGS84 bounds")
                    if not -180 <= values[f"{label}_longitude_deg"] <= 180:
                        raise ValueError(f"{label} longitude is outside WGS84 bounds")
                if values["path_width_km"] <= 0 or values["central_duration_seconds"] <= 0:
                    raise ValueError("path width and duration must be positive")
                result.append(CorridorReferenceRow(time_utc=moment, **values))
                previous = moment
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f"invalid reference CSV row at line {line}: {exc}") from exc
    if not result:
        raise ValueError("reference CSV contains no data rows")
    return result


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _maximum(values: list[float]) -> float | None:
    return max(values) if values else None


def validate_shadow_corridor_reference(
    corridor: Any,
    reference_csv: str | Path,
    *,
    source_id: str,
    coordinate_tolerance_km: float = 8.0,
    width_tolerance_km: float = 8.0,
    duration_tolerance_seconds: float = 10.0,
    max_time_offset_seconds: float = 65.0,
) -> CorridorValidationReport:
    """Compare centerline, two core boundaries, width and central duration.

    Left/right sides are paired to source north/south limits by minimum total
    geodesic error; their labels are not assumed to have a fixed compass sense.
    """
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id must be a non-empty provenance identifier")
    limits = {}
    for name, value in {
        "coordinate_tolerance_km": coordinate_tolerance_km,
        "width_tolerance_km": width_tolerance_km,
        "duration_tolerance_seconds": duration_tolerance_seconds,
        "max_time_offset_seconds": max_time_offset_seconds,
    }.items():
        if isinstance(value, bool):
            raise ValueError(f"{name} must be finite and positive")
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ValueError(f"{name} must be finite and positive")
        limits[name] = number

    references = load_corridor_reference_csv(reference_csv)
    samples = list(corridor.samples)
    sample_times = [_parse_time(time_to_utc_iso(sample.time)) for sample in samples]
    rows = []
    center_errors: list[float] = []
    edge_errors_all: list[float] = []
    width_errors: list[float] = []
    duration_errors: list[float] = []
    for reference in references:
        if not samples:
            rows.append(CorridorValidationRow(reference.time_utc.isoformat(), None, None, None, None, None, None, "FAIL", "corridor is empty"))
            continue
        index = min(range(len(samples)), key=lambda i: abs((sample_times[i] - reference.time_utc).total_seconds()))
        sample = samples[index]
        offset = abs((sample_times[index] - reference.time_utc).total_seconds())
        matched = time_to_utc_iso(sample.time)
        if offset > limits["max_time_offset_seconds"]:
            rows.append(CorridorValidationRow(reference.time_utc.isoformat(), matched, offset,
                                              None, None, None, None, "FAIL", "no sample within time tolerance"))
            continue
        center_error = wgs84_inverse(reference.center_latitude_deg, reference.center_longitude_deg,
                                     sample.center.latitude, sample.center.longitude)[0]
        center_errors.append(center_error)
        edges = (sample.central_left, sample.central_right)
        edge_max = None
        if all(edge is not None for edge in edges):
            north = (reference.north_latitude_deg, reference.north_longitude_deg)
            south = (reference.south_latitude_deg, reference.south_longitude_deg)
            direct = (wgs84_inverse(edges[0].latitude, edges[0].longitude, *north)[0],
                      wgs84_inverse(edges[1].latitude, edges[1].longitude, *south)[0])
            swapped = (wgs84_inverse(edges[0].latitude, edges[0].longitude, *south)[0],
                       wgs84_inverse(edges[1].latitude, edges[1].longitude, *north)[0])
            selected = min((direct, swapped), key=sum)
            edge_max = max(selected)
            edge_errors_all.extend(selected)
        width_error = abs(sample.central_width_km - reference.path_width_km) if sample.central_width_km is not None else None
        duration_error = (abs(sample.central_phase_duration_estimate_seconds - reference.central_duration_seconds)
                          if sample.central_phase_duration_estimate_seconds is not None else None)
        if width_error is not None:
            width_errors.append(width_error)
        if duration_error is not None:
            duration_errors.append(duration_error)
        checks = (
            center_error <= limits["coordinate_tolerance_km"],
            edge_max is not None and edge_max <= limits["coordinate_tolerance_km"],
            width_error is not None and width_error <= limits["width_tolerance_km"],
            duration_error is not None and duration_error <= limits["duration_tolerance_seconds"],
        )
        missing = []
        if edge_max is None:
            missing.append("central left/right edge unavailable")
        if width_error is None:
            missing.append("central width unavailable")
        if duration_error is None:
            missing.append("central duration unavailable")
        rows.append(CorridorValidationRow(
            time_utc=reference.time_utc.isoformat().replace("+00:00", "Z"),
            matched_time_utc=matched, time_offset_seconds=offset,
            center_error_km=center_error, maximum_boundary_error_km=edge_max,
            width_error_km=width_error, duration_error_seconds=duration_error,
            status="PASS" if all(checks) else "FAIL", message="; ".join(missing) or None,
        ))
    passed = sum(row.status == "PASS" for row in rows)
    failed = len(rows) - passed
    return CorridorValidationReport(
        source_id=source_id.strip(), status="PASS" if rows and failed == 0 else "FAIL",
        reference_count=len(rows), passed_count=passed, failed_count=failed,
        mean_center_error_km=_mean(center_errors), maximum_center_error_km=_maximum(center_errors),
        mean_boundary_error_km=_mean(edge_errors_all), maximum_boundary_error_km=_maximum(edge_errors_all),
        mean_width_error_km=_mean(width_errors), maximum_width_error_km=_maximum(width_errors),
        mean_duration_error_seconds=_mean(duration_errors), maximum_duration_error_seconds=_maximum(duration_errors),
        coordinate_tolerance_km=limits["coordinate_tolerance_km"],
        width_tolerance_km=limits["width_tolerance_km"],
        duration_tolerance_seconds=limits["duration_tolerance_seconds"],
        max_time_offset_seconds=limits["max_time_offset_seconds"], rows=tuple(rows),
    )




def _corridor_resolution_summary(corridor: Any) -> dict[str, float | int | None]:
    samples = list(corridor.samples)
    widths = [float(sample.central_width_km) for sample in samples
              if sample.central_width_km is not None]
    durations = [float(sample.central_phase_duration_estimate_seconds) for sample in samples
                 if sample.central_phase_duration_estimate_seconds is not None]
    coverage = [float(sample.central_boundary_coverage) for sample in samples]
    path_segments = [
        wgs84_inverse(
            first.center.latitude, first.center.longitude,
            second.center.latitude, second.center.longitude,
        )[0]
        for first, second in zip(samples, samples[1:])
    ]
    return {
        "valid_sample_count": len(samples),
        "centerline_length_km": sum(path_segments) if path_segments else None,
        "mean_central_width_km": _mean(widths),
        "minimum_central_width_km": min(widths) if widths else None,
        "maximum_central_width_km": max(widths) if widths else None,
        "mean_central_duration_estimate_seconds": _mean(durations),
        "mean_central_boundary_coverage": _mean(coverage),
    }


def compare_shadow_corridor_resolutions(corridors: dict[int, Any]) -> dict[str, Any]:
    """Compare corridor summary metrics across nested time-sampling resolutions.

    The finest requested run is used as a numerical baseline, not as scientific
    truth. The comparison measures how aggregate path and corridor metrics
    change with sample density; it is not an independent accuracy test.
    """
    if not isinstance(corridors, dict) or len(corridors) < 2:
        raise ValueError("corridors must contain at least two sample-count runs")

    normalized: dict[int, Any] = {}
    for raw_count, corridor in corridors.items():
        if isinstance(raw_count, bool):
            raise ValueError("sample-count keys must be integers >= 2")
        try:
            count = int(raw_count)
        except (TypeError, ValueError) as exc:
            raise ValueError("sample-count keys must be integers >= 2") from exc
        if count < 2 or count != raw_count:
            raise ValueError("sample-count keys must be integers >= 2")
        if count in normalized:
            raise ValueError("sample-count keys must be unique")
        normalized[count] = corridor

    counts = sorted(normalized)
    reference_count = counts[-1]
    reference_intervals = reference_count - 1
    reference_summary = _corridor_resolution_summary(normalized[reference_count])
    comparisons: list[dict[str, Any]] = []
    metrics = (
        "centerline_length_km",
        "mean_central_width_km",
        "minimum_central_width_km",
        "maximum_central_width_km",
        "mean_central_duration_estimate_seconds",
        "mean_central_boundary_coverage",
    )

    for count in counts[:-1]:
        intervals = count - 1
        if reference_intervals % intervals:
            raise ValueError(
                "sample counts must define nested uniform grids; "
                f"{count} is not nested in {reference_count}"
            )
        summary = _corridor_resolution_summary(normalized[count])
        differences = {
            metric.replace("_km", "_difference_km")
                  .replace("_seconds", "_difference_seconds")
                  .replace("_coverage", "_difference"):
                (abs(float(summary[metric]) - float(reference_summary[metric]))
                 if summary[metric] is not None and reference_summary[metric] is not None
                 else None)
            for metric in metrics
        }
        comparisons.append({
            "sample_count": count,
            "reference_sample_count": reference_count,
            "summary": summary,
            "absolute_differences_from_finest": differences,
            "status": (
                "DIAGNOSTIC"
                if summary["valid_sample_count"] and reference_summary["valid_sample_count"]
                else "NO_VALID_SAMPLES"
            ),
        })

    return {
        "status": "DIAGNOSTIC",
        "reference_sample_count": reference_count,
        "reference_summary": reference_summary,
        "comparisons": comparisons,
        "interpretation": (
            "Aggregate centerline length, central-width, duration-estimate and "
            "boundary-coverage metrics are compared with the finest requested "
            "sampling. This measures sampling sensitivity only; it is not an "
            "independent accuracy test and the finest run is not assumed to be truth."
        ),
    }
