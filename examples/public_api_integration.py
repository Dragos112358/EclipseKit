"""Minimal third-party application integration through the curated API."""

from __future__ import annotations

import argparse
from pathlib import Path

from eclipsekit.api import (
    EclipseConfig,
    EclipseEngine,
    EphemerisConfig,
    Observer,
    dumps_json,
    get_runtime_info,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", default="de440s", help="JPL SPK kernel name or local BSP path")
    parser.add_argument("--date", default="2026-08-12T17:00:00Z", help="UTC instant/date")
    parser.add_argument("--latitude", type=float, default=44.4268, help="Observer latitude")
    parser.add_argument("--longitude", type=float, default=26.1025, help="East-positive longitude")
    parser.add_argument("--output", type=Path, default=Path("reports/public-api-result.json"))
    args = parser.parse_args()

    config = EclipseConfig(ephemeris=EphemerisConfig.jpl(args.kernel))
    observer = Observer(args.latitude, args.longitude, name="API integration observer")
    engine = EclipseEngine(config=config)
    result = engine.calculate_local(observer, args.date)
    payload = {
        "runtime": get_runtime_info(),
        "result": result,
    }
    write_json(payload, args.output)
    print(dumps_json({"output": str(args.output), "api_contract": "1"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
