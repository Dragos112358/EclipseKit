"""Find and report lunar eclipses with EclipseKit's geocentric shadow engine."""

from __future__ import annotations

import argparse
import json

from eclipsekit import EclipseEngine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", default="de440s", help="JPL BSP kernel name or local path")
    parser.add_argument(
        "--start", default="2025-01-01",
        help="Inclusive start date/time; date-only values begin at civil midnight",
    )
    parser.add_argument(
        "--end", default="2026-01-01",
        help="Exclusive end date/time; date-only values begin at civil midnight",
    )
    parser.add_argument(
        "--calendar", choices=("historical", "julian", "gregorian"), default="historical",
        help="Civil calendar used for naive input dates and result formatting",
    )
    parser.add_argument(
        "--next", action="store_true", help="Find only the next eclipse after --start"
    )
    parser.add_argument(
        "--shadow-model", choices=("herald_sinnott", "circular"), default="herald_sinnott",
        help="Shadow prescription; Herald--Sinnott is the recommended default",
    )
    parser.add_argument(
        "--nel-height-km", type=float, default=87.0,
        help="Herald--Sinnott notional eclipse-forming atmospheric layer in km",
    )
    parser.add_argument(
        "--flattening-coefficient", type=float, default=0.003353,
        help="Herald--Sinnott Earth oblateness coefficient",
    )
    parser.add_argument(
        "--shadow-enlargement", type=float, default=1.0,
        help="Additional shadow scale; keep 1.0 for the standard 87 km NEL model",
    )
    parser.add_argument(
        "--contact-step-seconds", type=float, default=300.0,
        help="Coarse contact-bracketing step; final roots are refined numerically",
    )
    parser.add_argument(
        "--contact-tolerance-seconds", type=float, default=0.05,
        help="Numerical contact-root tolerance in seconds",
    )
    parser.add_argument(
        "--boundary-samples", type=int, default=96,
        help="Angular samples used to seed closest-point refinement on the shadow edge",
    )
    args = parser.parse_args()

    engine = EclipseEngine(args.kernel)
    solve_options = {
        "calendar": args.calendar,
        "shadow_model": args.shadow_model,
        "atmospheric_nel_height_km": args.nel_height_km,
        "flattening_coefficient": args.flattening_coefficient,
        "shadow_enlargement": args.shadow_enlargement,
        "contact_step_seconds": args.contact_step_seconds,
        "contact_tolerance_seconds": args.contact_tolerance_seconds,
        "boundary_samples": args.boundary_samples,
    }
    if args.next:
        event = engine.find_next_lunar_eclipse(args.start, **solve_options)
        events = [] if event is None else [event]
    else:
        events = engine.find_lunar_eclipses(args.start, args.end, **solve_options)

    payload = [event.to_dict(calendar=args.calendar) for event in events]
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
