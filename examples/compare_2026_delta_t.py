"""Controlled comparison of EclipseKit's default Delta-T with NASA's 2026 path-table assumption.

This is a diagnostic only. It does not modify the EclipseKit source or defaults.
NASA GSFC's 2026 Aug 12 path table states Delta-T = 71.4 s and labels the
path timestamps Universal Time. The comparison therefore interprets reference
clock labels as UT1 and converts them through each tested Skyfield timescale.
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


def target_tt_from_ut1(engine: EclipseEngine, value: str) -> float:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Reference timestamp must include a timezone: {value}")
    # NASA's table header is "Universal Time" and supplies Delta-T; treat its
    # clock labels as UT1 for a like-for-like comparison.
    seconds = parsed.second + parsed.microsecond / 1_000_000.0
    t = engine.ts.ut1(parsed.year, parsed.month, parsed.day,
                      parsed.hour, parsed.minute, seconds)
    return float(t.tt)


def run_case(label: str, engine: EclipseEngine, rows: list[dict], samples: int) -> None:
    probe = engine.ts.utc(2026, 8, 12, 18, 30, 0)
    print(f"\n=== {label} ===")
    print(f"Delta-T at 18:30 UTC: {float(probe.delta_t):.6f} s")
    print(f"DUT1 at 18:30 UTC:   {float(probe.dut1):+.6f} s")

    points = engine.global_path_for_eclipse(
        "2026-08-12", search_radius_hours=4.0, samples=samples
    )
    print(f"Computed path points: {len(points)} (samples={samples})")

    errors: list[float] = []
    for row in rows:
        reference_label = str(row.get("time_ut1") or row.get("time_utc"))
        target_tt = target_tt_from_ut1(engine, reference_label)
        lat, lon = interpolate_shadow_position(points, target_tt)
        error = great_circle_distance_km(
            lat, lon,
            float(row["latitude_deg"]), float(row["longitude_deg"]),
        )
        errors.append(error)
        print(
            f"{reference_label}: {error:7.3f} km "
            f"(computed {lat:.6f}, {lon:.6f})"
        )

    mean = sum(errors) / len(errors)
    rms = (sum(e * e for e in errors) / len(errors)) ** 0.5
    print(f"Mean error: {mean:.3f} km")
    print(f"RMS error:  {rms:.3f} km")
    print(f"Max error:  {max(errors):.3f} km")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare default Delta-T with NASA's 71.4-second 2026 path-table assumption"
    )
    parser.add_argument("--kernel", default="de440s")
    parser.add_argument("--samples", type=int, default=1201)
    parser.add_argument(
        "--reference",
        default="data/validation/global_path_2026-08-12.csv",
    )
    args = parser.parse_args()
    if args.samples < 3:
        parser.error("--samples must be >= 3")

    cache_dir = Path.home() / ".eclipsekit" / "ephemerides"
    loader = Loader(str(cache_dir), verbose=False)
    rows = load_path_reference(args.reference)

    default_ts = loader.timescale()
    default_engine = EclipseEngine.from_jpl(
        args.kernel, cache_dir=cache_dir, timescale=default_ts
    )
    run_case("EclipseKit default Skyfield timescale", default_engine, rows, args.samples)

    nasa_ts = loader.timescale(delta_t=71.4)
    nasa_engine = EclipseEngine.from_jpl(
        args.kernel, cache_dir=cache_dir, timescale=nasa_ts
    )
    run_case("Controlled NASA path-table Delta-T = 71.4 s", nasa_engine, rows, args.samples)

    print("\nDiagnostic only: the 71.4 s run reproduces NASA's stated historical prediction assumption.")
    print("It is not a recommendation to replace current observed Earth-orientation data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
