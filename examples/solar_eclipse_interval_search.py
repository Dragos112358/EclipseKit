"""Search a date interval for solar eclipses at a small explicit observer set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eclipsekit import EclipseEngine, Observer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="inclusive UTC start date/time")
    parser.add_argument("--end", required=True, help="inclusive UTC end date/time")
    parser.add_argument("--kernel", default="de440s", help="local BSP path or Skyfield kernel name")
    parser.add_argument("--output", default="reports/phase11-eclipse-search.json")
    parser.add_argument("--min-magnitude", type=float, default=0.01)
    args = parser.parse_args()

    observers = [
        Observer(44.4268, 26.1025, name="Bucharest", country="Romania"),
        Observer(40.4168, -3.7038, name="Madrid", country="Spain"),
        Observer(30.0444, 31.2357, name="Cairo", country="Egypt"),
        Observer(-33.8688, 151.2093, name="Sydney", country="Australia"),
    ]

    engine = EclipseEngine(args.kernel)
    result = engine.search_solar_eclipses(
        args.start,
        args.end,
        observers,
        min_magnitude=args.min_magnitude,
    )
    destination = Path(args.output).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "events_found": result.event_count,
        "location_events_found": result.location_event_count,
        "new_moons_examined": result.new_moons_examined,
        "output": str(destination),
    }, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised as a script
    raise SystemExit(main())
