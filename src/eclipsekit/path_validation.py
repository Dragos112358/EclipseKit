"""Compare a computed solar-eclipse shadow axis with a published path table.

The comparison interpolates the computed central-axis coordinates in time and
reports great-circle position errors at the reference table timestamps.
It does not validate northern/southern path limits, shadow width, duration,
or lunar-limb corrections.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from .engine import EclipseEngine
from .earth_orientation import EarthOrientationConfig

EARTH_MEAN_RADIUS_KM = 6371.0088


def _parse_reference_time(engine: Any, value: str, clock: str = "utc") -> float:
    """Return an explicit-timezone reference timestamp as a Skyfield TT JD.

    NASA path tables commonly label their time axis ``Universal Time``; for
    those tables use ``clock="ut1"``. Civil/local timestamps normalized to UTC
    must use ``clock="utc"``. Keeping this distinction explicit prevents
    silently mixing UT1 and UTC.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Reference time must be a non-empty ISO-8601 string")
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Reference time must include Z or an offset: {value!r}")
    parsed = parsed.astimezone(timezone.utc)
    seconds = parsed.second + parsed.microsecond / 1_000_000.0
    if clock == "utc":
        normalized = parsed.isoformat().replace("+00:00", "Z")
        return float(engine.time(normalized).tt)
    if clock == "ut1":
        if hasattr(engine, "time_from_ut1"):
            time = engine.time_from_ut1(
                parsed.year, parsed.month, parsed.day,
                parsed.hour, parsed.minute, seconds,
            )
        else:
            time = engine.ts.ut1(
                parsed.year, parsed.month, parsed.day,
                parsed.hour, parsed.minute, seconds,
            )
        return float(time.tt)
    raise ValueError("reference clock must be 'utc' or 'ut1'")


def interpolate_shadow_position(
    points: Iterable[Any], target_tt: float
) -> tuple[float, float]:
    """Interpolate latitude/longitude of a sampled shadow path at TT JD.

    Longitude interpolation follows the shorter angular arc, so a path crossing
    the antimeridian does not interpolate through Greenwich.
    """
    ordered = sorted(points, key=lambda point: float(point.time.tt))
    if len(ordered) < 2:
        raise ValueError("At least two computed shadow-path points are required")

    times = [float(point.time.tt) for point in ordered]
    if target_tt < times[0] or target_tt > times[-1]:
        raise ValueError("Reference time falls outside the computed shadow path")

    for index in range(len(ordered) - 1):
        left, right = ordered[index], ordered[index + 1]
        t0, t1 = times[index], times[index + 1]
        if t0 <= target_tt <= t1:
            if t1 <= t0:
                raise ValueError("Computed shadow path contains duplicate/non-increasing times")
            fraction = (target_tt - t0) / (t1 - t0)
            latitude = float(left.latitude) + fraction * (
                float(right.latitude) - float(left.latitude)
            )
            lon0, lon1 = float(left.longitude), float(right.longitude)
            delta_lon = (lon1 - lon0 + 180.0) % 360.0 - 180.0
            longitude = lon0 + fraction * delta_lon
            longitude = (longitude + 180.0) % 360.0 - 180.0
            return latitude, longitude

    raise ValueError("Could not bracket reference time in computed shadow path")


def great_circle_distance_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return WGS84-sphere great-circle distance using the mean Earth radius."""
    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_lat = math.radians(latitude_b - latitude_a)
    delta_lon = math.radians((longitude_b - longitude_a + 180.0) % 360.0 - 180.0)
    haversine = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * EARTH_MEAN_RADIUS_KM * math.asin(min(1.0, math.sqrt(haversine)))


def load_path_reference(filename: str | Path) -> list[dict[str, Any]]:
    """Load central-line reference rows from a CSV.

    Accepts either ``time_utc`` for civil UTC timestamps or ``time_ut1`` for
    astronomical Universal Time timestamps. The column name carries the time
    scale; do not rename a source column without checking its original table.
    """
    path = Path(filename)
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("Path reference CSV is empty")
    time_columns = {"time_utc", "time_ut1"}.intersection(rows[0])
    if len(time_columns) != 1 or not {"latitude_deg", "longitude_deg"}.issubset(rows[0]):
        raise ValueError(
            "Path reference CSV must contain exactly one of time_utc/time_ut1 "
            "and the latitude_deg,longitude_deg columns"
        )
    time_column = next(iter(time_columns))
    for row in rows:
        value = row.get(time_column, "")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing reference time in column {time_column}")
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f"Reference time must include Z or an offset: {value!r}")
        row["latitude_deg"] = float(row["latitude_deg"])
        row["longitude_deg"] = float(row["longitude_deg"])
        if not -90 <= row["latitude_deg"] <= 90 or not -180 <= row["longitude_deg"] <= 180:
            raise ValueError("Reference path coordinates are outside WGS84 bounds")
    return rows


def compare_shadow_path(
    engine: Any,
    computed_points: Iterable[Any],
    reference_rows: Iterable[Mapping[str, Any]],
    *,
    reference_clock: str = "auto",
) -> dict[str, Any]:
    """Compare computed shadow-axis coordinates with a reference CSV table.

    ``reference_clock="auto"`` follows the CSV header: ``time_utc`` means UTC
    and ``time_ut1`` means UT1. Out-of-range reference times are recorded as
    per-row errors instead of aborting the entire diagnostic.
    """
    if reference_clock not in {"auto", "utc", "ut1"}:
        raise ValueError("reference_clock must be 'auto', 'utc', or 'ut1'")
    points = list(computed_points)
    rows = list(reference_rows)
    if len(points) < 2:
        raise ValueError("Computed path must contain at least two points")
    if not rows:
        raise ValueError("Reference path table is empty")

    details = []
    for row in rows:
        label = str(row.get("time_ut1", row.get("time_utc", "")))
        clock = reference_clock if reference_clock != "auto" else (
            "ut1" if "time_ut1" in row else "utc"
        )
        try:
            if "time_ut1" in row:
                time_column = "time_ut1"
            elif "time_utc" in row:
                time_column = "time_utc"
            else:
                raise ValueError("Reference row has neither time_utc nor time_ut1")
            label = str(row[time_column])
            target_tt = _parse_reference_time(engine, label, clock)
            actual_lat, actual_lon = interpolate_shadow_position(points, target_tt)
            expected_lat = float(row["latitude_deg"])
            expected_lon = float(row["longitude_deg"])
            error_km = great_circle_distance_km(
                actual_lat, actual_lon, expected_lat, expected_lon
            )
            details.append({
                "reference_time": label,
                "reference_clock": clock,
                "status": "PASS",
                "computed_latitude_deg": actual_lat,
                "computed_longitude_deg": actual_lon,
                "reference_latitude_deg": expected_lat,
                "reference_longitude_deg": expected_lon,
                "position_error_km": error_km,
            })
        except (ValueError, KeyError, TypeError) as exc:
            details.append({
                "reference_time": label,
                "reference_clock": clock,
                "status": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
            })

    errors = [item["position_error_km"] for item in details if item["status"] == "PASS"]
    if errors:
        mean_error = sum(errors) / len(errors)
        rms_error = math.sqrt(sum(value * value for value in errors) / len(errors))
        max_error = max(errors)
    else:
        mean_error = rms_error = max_error = None
    clocks = sorted({item["reference_clock"] for item in details})
    return {
        "reference_count": len(details),
        "successful_comparisons": len(errors),
        "error_count": len(details) - len(errors),
        "reference_clocks": clocks,
        "max_error_km": max_error,
        "mean_error_km": mean_error,
        "rms_error_km": rms_error,
        "comparisons": details,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare a computed eclipse shadow axis against a published path table"
    )
    parser.add_argument("--kernel", default="de440s", help="JPL BSP kernel name or local path")
    parser.add_argument("--date", default="2026-08-12", help="Eclipse date or UTC ISO timestamp")
    parser.add_argument(
        "--reference", default="data/validation/global_path_2026-08-12.csv",
        help="CSV with time_utc OR time_ut1,latitude_deg,longitude_deg columns",
    )
    parser.add_argument("--samples", type=int, default=301)
    parser.add_argument("--cache-dir", default=None, help="Explicit Skyfield ephemeris/EOP cache directory")
    parser.add_argument("--search-radius-hours", type=float, default=4.0)
    parser.add_argument("--tolerance-km", type=float, default=25.0)
    parser.add_argument("--reference-clock", choices=("auto", "utc", "ut1"), default="auto",
                        help="Interpret reference timestamps as UTC, UT1, or infer from CSV column")
    parser.add_argument("--time-scale-mode", choices=("builtin", "iers", "fixed_delta_t"),
                        default="builtin", help="Earth-orientation data source")
    parser.add_argument("--delta-t-seconds", type=float, default=None,
                        help="Required only with --time-scale-mode fixed_delta_t; reproduction mode")
    parser.add_argument("--json-out", default="reports/global-path-validation.json")
    args = parser.parse_args(argv)

    if args.samples < 3 or args.search_radius_hours <= 0 or args.tolerance_km < 0:
        parser.error("samples must be >=3, search-radius-hours >0, tolerance-km >=0")
    if args.time_scale_mode == "fixed_delta_t" and args.delta_t_seconds is None:
        parser.error("--delta-t-seconds is required with --time-scale-mode fixed_delta_t")
    if args.time_scale_mode != "fixed_delta_t" and args.delta_t_seconds is not None:
        parser.error("--delta-t-seconds can only be used with --time-scale-mode fixed_delta_t")

    orientation = (
        EarthOrientationConfig.fixed(args.delta_t_seconds)
        if args.time_scale_mode == "fixed_delta_t"
        else EarthOrientationConfig(mode=args.time_scale_mode)
    )
    try:
        engine = EclipseEngine.from_jpl(
            args.kernel, earth_orientation=orientation, cache_dir=args.cache_dir
        )
    except Exception as exc:
        parser.error(f"Could not initialize ephemeris/time scale: {type(exc).__name__}: {exc}")
    points = engine.global_path_for_eclipse(
        args.date,
        search_radius_hours=args.search_radius_hours,
        samples=args.samples,
    )
    reference = load_path_reference(args.reference)
    report = compare_shadow_path(
        engine, points, reference, reference_clock=args.reference_clock
    )
    report.update({
        "event_date": args.date,
        "kernel": args.kernel,
        "computed_path_points": len(points),
        "tolerance_km": args.tolerance_km,
        "time_scale": engine.time_scale_diagnostics(args.date),
        "time_scale_mode": args.time_scale_mode,
        "earth_orientation_provenance": getattr(
            getattr(engine, "context", None), "earth_orientation_provenance", None
        ),
        "cache_dir": str(args.cache_dir) if args.cache_dir else None,
        "reference_file": str(args.reference),
    })
    errors_present = report["error_count"] > 0
    max_error = report["max_error_km"]
    passed = not errors_present and max_error is not None and max_error <= args.tolerance_km
    report["status"] = "PASS" if passed else "FAIL"

    output = Path(args.json_out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Global path validation: {report['status']}")
    print(f"Computed path points: {report['computed_path_points']}")
    print(f"Reference samples: {report['reference_count']}")
    print(f"Successful comparisons: {report['successful_comparisons']}")
    print(f"Reference clock(s): {', '.join(report['reference_clocks'])}")
    print(f"Time-scale mode: {args.time_scale_mode}")
    print(f"Delta-T: {report['time_scale']['delta_t_seconds']:.6f} s")
    print(f"DUT1: {report['time_scale']['dut1_seconds']:+.6f} s")
    if max_error is not None:
        print(f"Mean position error: {report['mean_error_km']:.2f} km")
        print(f"RMS position error: {report['rms_error_km']:.2f} km")
        print(f"Maximum position error: {max_error:.2f} km")
    print(f"Tolerance: {args.tolerance_km:.2f} km")
    print(f"Report: {output}")
    for item in report["comparisons"]:
        if item["status"] == "PASS":
            print(
                f"  {item['reference_time']} [{item['reference_clock']}]: "
                f"{item['position_error_km']:.2f} km "
                f"(computed {item['computed_latitude_deg']:.4f}, "
                f"{item['computed_longitude_deg']:.4f})"
            )
        else:
            print(f"  {item['reference_time']} [{item['reference_clock']}]: ERROR {item['error']}")
    if report["time_scale"].get("warning"):
        print(f"WARNING: {report['time_scale']['warning']}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
