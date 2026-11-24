"""Detailed topocentric observation geometry with an optional skyline mask."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from eclipsekit import EclipseEngine, HorizonProfile, Observer


def load_horizon_profile(filename: str | None) -> HorizonProfile | None:
    if filename is None:
        return None
    source = Path(filename)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("horizon profile JSON must be an object with schema_version=1")
    return HorizonProfile(
        points=tuple(tuple(point) for point in payload["points"]),
        name=payload.get("name", source.stem),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", default="de440s")
    parser.add_argument("--date", required=True, help="UTC date/time, e.g. 2026-08-12T17:00:00Z")
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True, help="East-positive degrees")
    parser.add_argument("--elevation-m", type=float, default=0.0)
    parser.add_argument("--name", default=None)
    parser.add_argument("--horizon-profile", default=None, help="Optional schema-v1 skyline JSON")
    parser.add_argument("--no-refraction", action="store_true")
    parser.add_argument("--output", default="reports/phase12-observation-geometry.json")
    args = parser.parse_args()

    profile = load_horizon_profile(args.horizon_profile)
    observer = Observer(
        args.latitude, args.longitude, elevation_m=args.elevation_m, name=args.name
    )
    engine = EclipseEngine(args.kernel)
    result = engine.calculate_observation_geometry(
        observer, args.date, horizon_profile=profile,
        apply_refraction=not args.no_refraction,
    )
    payload = result.to_dict()
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(destination),
        "visibility_status": result.visibility_status,
        "sun_altitude_deg": result.sun_altitude_deg,
        "sun_azimuth_deg": result.sun_azimuth_deg,
        "moon_altitude_deg": result.moon_altitude_deg,
        "separation_deg": result.separation_deg,
        "obscuration_percent": result.obscuration_percent,
    }, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
