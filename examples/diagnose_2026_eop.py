"""Compare EclipseKit's default Skyfield time scale with current IERS EOP data.

The NASA 2026 path page labels its table times "Universal Time" and states
Delta-T = 71.4 s. This diagnostic therefore reports both interpretations of
the CSV clock labels (UTC and UT1), and separately reports the Skyfield time
scale's Delta-T and DUT1. It does not alter project files or engine defaults.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from skyfield.api import Loader

from eclipsekit import EclipseEngine
from eclipsekit.path_validation import (
    great_circle_distance_km,
    interpolate_shadow_position,
    load_path_reference,
)


def reference_tt(engine: EclipseEngine, value: str, *, as_ut1: bool) -> float:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Reference timestamp needs a timezone: {value}")

    if as_ut1:
        # NASA's table header says "Universal Time" and supplies a Delta-T
        # assumption; treat the table clock labels as UT1 for this comparison.
        seconds = parsed.second + parsed.microsecond / 1_000_000.0
        time = engine.ts.ut1(
            parsed.year,
            parsed.month,
            parsed.day,
            parsed.hour,
            parsed.minute,
            seconds,
        )
    else:
        # Reproduce the current path_validation.py interpretation of the
        # time_utc column: parse the clock labels as civil UTC.
        time = engine.time(parsed)
    return float(time.tt)


def run_case(
    label: str,
    engine: EclipseEngine,
    rows: list[dict],
    *,
    samples: int,
) -> None:
    utc_probe = engine.ts.utc(2026, 8, 12, 18, 30, 0)
    print(f"\n--- {label} ---")
    print(f"Skyfield Delta-T at 2026-08-12 18:30 UTC: {float(utc_probe.delta_t):.6f} s")
    print(f"Skyfield DUT1 at 2026-08-12 18:30 UTC:    {float(utc_probe.dut1):+.6f} s")

    points = engine.global_path_for_eclipse(
        "2026-08-12", search_radius_hours=4.0, samples=samples
    )
    print(f"Computed path points: {len(points)} (samples={samples})")

    for interpretation, as_ut1 in (("NASA clock labels interpreted as UT1", True),
                                   ("clock labels interpreted as UTC (current validator)", False)):
        errors = []
        print(f"{interpretation}:")
        for row in rows:
            reference_label = str(row.get("time_ut1") or row.get("time_utc"))
            target_tt = reference_tt(engine, reference_label, as_ut1=as_ut1)
            lat, lon = interpolate_shadow_position(points, target_tt)
            error = great_circle_distance_km(
                lat,
                lon,
                float(row["latitude_deg"]),
                float(row["longitude_deg"]),
            )
            errors.append(error)
            print(
                f"  {reference_label}: {error:7.3f} km "
                f"(computed {lat:.6f}, {lon:.6f})"
            )
        mean_error = sum(errors) / len(errors)
        rms_error = (sum(value * value for value in errors) / len(errors)) ** 0.5
        print(
            f"  mean={mean_error:.3f} km; RMS={rms_error:.3f} km; "
            f"max={max(errors):.3f} km"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare default Skyfield time scale with IERS observed Earth-orientation data"
    )
    parser.add_argument("--kernel", default="de440s")
    parser.add_argument(
        "--reference",
        default="data/validation/global_path_2026-08-12.csv",
    )
    parser.add_argument("--samples", type=int, default=1201)
    args = parser.parse_args()

    if args.samples < 3:
        parser.error("--samples must be >= 3")

    cache_dir = Path.home() / ".eclipsekit" / "ephemerides"
    loader = Loader(str(cache_dir), verbose=False)
    rows = load_path_reference(args.reference)

    default_engine = EclipseEngine.from_jpl(args.kernel, cache_dir=cache_dir)
    run_case("Skyfield built-in time scale", default_engine, rows, samples=args.samples)

    print("\nLoading IERS finals2000A.all (requires internet on first run)...")
    try:
        iers_timescale = loader.timescale(builtin=False)
        iers_engine = EclipseEngine.from_jpl(
            args.kernel,
            cache_dir=cache_dir,
            timescale=iers_timescale,
        )
    except Exception as exc:
        print(f"[WARN] Could not load IERS data: {type(exc).__name__}: {exc}")
        print("The built-in Skyfield result above is still available.")
        return 0

    run_case("IERS finals2000A time scale", iers_engine, rows, samples=args.samples)
    print("\nDiagnostic finished. No project source files were modified.")
    print(
        "Note: NASA's published 2026 path page states Delta-T=71.4 s and "
        "uses VSOP87/ELP2000-85; these results are a comparison, not a claim "
        "that DE440s must reproduce that older prediction exactly."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
