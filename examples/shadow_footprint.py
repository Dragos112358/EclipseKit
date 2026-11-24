"""Export an instantaneous global shadow-cone footprint as GeoJSON."""
from __future__ import annotations

import argparse

from eclipsekit import EclipseEngine, write_shadow_footprint_geojson


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", default="de440s")
    parser.add_argument("--date", required=True, help="UTC date/time, e.g. 2026-08-12T17:00:00Z")
    parser.add_argument("--boundary-samples", type=int, default=180)
    parser.add_argument("--output", default="reports/phase12-shadow-footprint.geojson")
    args = parser.parse_args()

    engine = EclipseEngine(args.kernel)
    footprint = engine.calculate_shadow_footprint(
        args.date, boundary_samples=args.boundary_samples
    )
    if footprint is None:
        print("No penumbral cone intersection with WGS84 at the requested instant.")
        return 2
    destination = write_shadow_footprint_geojson(footprint, args.output)
    print(f"GeoJSON: {destination}")
    print(f"Shadow kind: {footprint.shadow_kind}")
    print(f"Axis: {footprint.axis_latitude}, {footprint.axis_longitude}")
    print(f"Track bearing: {footprint.track_bearing_deg} deg")
    print(f"Central boundary coverage: {footprint.central_boundary_coverage:.3f}")
    print(f"Penumbra boundary coverage: {footprint.penumbra_boundary_coverage:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
