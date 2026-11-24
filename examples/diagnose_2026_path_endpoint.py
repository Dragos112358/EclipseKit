"""Inspect sampling and interpolation near the 2026-08-12 shadow-path endpoint.

Run from the EclipseKit project root:
    python examples/diagnose_2026_path_endpoint.py
"""
from __future__ import annotations

from bisect import bisect_left

from eclipsekit.engine import EclipseEngine

DATE = "2026-08-12"
TARGET_ISO = "2026-08-12T18:30:00Z"
SAMPLE_COUNTS = (101, 201, 301, 401, 501, 601, 801, 1001, 1201)


def main() -> int:
    engine = EclipseEngine.from_jpl("de440s")
    target = engine.time(TARGET_ISO)
    target_tt = float(target.tt)

    print(f"Reference time: {TARGET_ISO}")
    print("All listed times are UTC. Distances in time are seconds from reference.")

    for samples in SAMPLE_COUNTS:
        points = engine.global_path_for_eclipse(
            DATE, search_radius_hours=4.0, samples=samples
        )
        points = sorted(points, key=lambda p: float(p.time.tt))
        times = [float(p.time.tt) for p in points]

        print(f"\n=== samples={samples}; valid_points={len(points)} ===")
        if len(points) < 2:
            print("Not enough valid ground-intersection points.")
            continue

        print("First valid point:", points[0].time.utc_iso(),
              f"({(times[0] - target_tt) * 86400:+.1f} s)")
        print("Last valid point: ", points[-1].time.utc_iso(),
              f"({(times[-1] - target_tt) * 86400:+.1f} s)")

        insertion = bisect_left(times, target_tt)
        lo = max(0, insertion - 3)
        hi = min(len(points), insertion + 3)
        print("Points nearest the reference time:")
        for point in points[lo:hi]:
            dt = (float(point.time.tt) - target_tt) * 86400
            print(
                f"  {point.time.utc_iso()}  dt={dt:+8.1f} s  "
                f"lat={float(point.latitude): .6f}  "
                f"lon={float(point.longitude): .6f}  "
                f"width={float(point.width_km):.2f} km  "
                f"kind={point.shadow_kind}"
            )

        if insertion == 0 or insertion == len(points):
            print("REFERENCE NOT BRACKETED by two computed points.")
        else:
            left, right = points[insertion - 1], points[insertion]
            gap_s = (float(right.time.tt) - float(left.time.tt)) * 86400
            print(f"Reference bracket width: {gap_s:.1f} s")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
