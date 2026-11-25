"""Compare EclipseKit lunar-eclipse predictions with a frozen external reference set.

The reference file records EclipseWise/Herald--Sinnott circumstances. NASA's
catalog type is retained as a separate classification cross-check; its Danjon
shadow model is not used for contact-time or magnitude comparisons.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from eclipsekit import EclipseEngine
from eclipsekit.earth_orientation import EarthOrientationConfig
from eclipsekit.lunar_eclipse import MEAN_MOON_RADIUS_KM

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = ROOT / "tests" / "reference_data" / "lunar_eclipse_eclipsewise_2022_2028.json"
CONTACT_NAMES = ("P1", "U1", "U2", "greatest", "U3", "U4", "P4")
NASA_TYPE_MAP = {"N": "penumbral", "P": "partial", "T": "total"}


def parse_ut1(value: str | None) -> datetime | None:
    """Parse a reference ISO timestamp or EclipseKit's ISO timestamp with UT1 suffix."""
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned.endswith(" UT1"):
        cleaned = cleaned[:-4]
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1]
    return datetime.fromisoformat(cleaned)


def load_reference(path: Path) -> dict[str, Any]:
    """Load and validate the static reference matrix."""
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported lunar reference schema_version")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("reference file must contain a non-empty 'cases' list")
    seen_dates: set[str] = set()
    for case in cases:
        date = case.get("date")
        if not isinstance(date, str) or date in seen_dates:
            raise ValueError(f"invalid or duplicate reference date: {date!r}")
        seen_dates.add(date)
        if case.get("eclipse_type") not in {"penumbral", "partial", "total"}:
            raise ValueError(f"invalid eclipse_type for {date}")
        catalog_type = case.get("nasa_catalog_type", "")
        if not catalog_type or NASA_TYPE_MAP.get(catalog_type[0]) != case["eclipse_type"]:
            raise ValueError(f"NASA catalog classification disagrees for {date}")
        if not case.get("source_url", "").startswith("https://"):
            raise ValueError(f"missing source URL for {date}")
        if set(case.get("contacts_ut1", {})) != set(CONTACT_NAMES):
            raise ValueError(f"contacts_ut1 must define exactly {CONTACT_NAMES} for {date}")
        if case["contacts_ut1"]["greatest"] != case["greatest_ut1"]:
            raise ValueError(f"greatest contact and greatest_ut1 differ for {date}")
    return payload


def reference_moon_radius_overrides(references: dict[str, Any]) -> dict[str, float]:
    """Validate and return per-event Moon radii used only for source reproduction."""
    overrides: dict[str, float] = {}
    for case in references["cases"]:
        raw_radius = case.get("moon_radius_km")
        if raw_radius is None:
            continue
        try:
            radius = float(raw_radius)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"invalid moon_radius_km for {case.get('date', '<unknown>')}"
            ) from exc
        if not math.isfinite(radius) or radius <= 0.0:
            raise ValueError(
                f"moon_radius_km for {case.get('date', '<unknown>')} must be finite and positive"
            )
        overrides[str(case["date"])] = radius
    return overrides


def compare_case(
    reference: dict[str, Any],
    actual: dict[str, Any],
    *,
    contact_tolerance_seconds: float = 30.0,
    magnitude_tolerance: float = 0.01,
    gamma_tolerance: float = 0.005,
) -> dict[str, Any]:
    """Compare one serialized EclipseKit event with one reference case."""
    date = reference["date"]
    failures: list[str] = []
    actual_date = str(actual.get("maximum_ut1", ""))[:10]
    if actual_date != date:
        failures.append(f"maximum date {actual_date!r} != {date!r}")

    actual_type = actual.get("eclipse_type")
    if actual_type != reference["eclipse_type"]:
        failures.append(
            f"type {actual_type!r} != reference {reference['eclipse_type']!r}"
        )

    time_errors: dict[str, float | None] = {}
    time_deltas: dict[str, float | None] = {}
    contact_details: dict[str, dict[str, Any]] = {}
    actual_contacts = actual.get("contacts_ut1", {})
    for name in CONTACT_NAMES:
        expected_value = reference["contacts_ut1"][name]
        actual_value = actual_contacts.get(name)
        if expected_value is None:
            time_errors[name] = None
            time_deltas[name] = None
            contact_details[name] = {
                "reference_ut1": None,
                "actual_ut1": actual_value,
                "delta_seconds": None,
                "absolute_error_seconds": None,
            }
            if actual_value is not None:
                failures.append(f"{name} should be absent but EclipseKit returned {actual_value!r}")
            continue
        if actual_value is None:
            time_errors[name] = None
            time_deltas[name] = None
            contact_details[name] = {
                "reference_ut1": expected_value,
                "actual_ut1": None,
                "delta_seconds": None,
                "absolute_error_seconds": None,
            }
            failures.append(f"{name} is missing")
            continue
        try:
            expected_time = parse_ut1(expected_value)
            actual_time = parse_ut1(actual_value)
        except (TypeError, ValueError):
            expected_time = None
            actual_time = None
        if expected_time is None or actual_time is None:
            time_errors[name] = None
            time_deltas[name] = None
            contact_details[name] = {
                "reference_ut1": expected_value,
                "actual_ut1": actual_value,
                "delta_seconds": None,
                "absolute_error_seconds": None,
            }
            failures.append(f"{name} contains an invalid time")
            continue
        delta_seconds = (actual_time - expected_time).total_seconds()
        error_seconds = abs(delta_seconds)
        time_errors[name] = error_seconds
        time_deltas[name] = delta_seconds
        contact_details[name] = {
            "reference_ut1": expected_value,
            "actual_ut1": actual_value,
            "delta_seconds": delta_seconds,
            "absolute_error_seconds": error_seconds,
        }
        if error_seconds > contact_tolerance_seconds:
            failures.append(
                f"{name} differs by {error_seconds:.2f}s "
                f"(limit {contact_tolerance_seconds:.2f}s)"
            )

    magnitude_errors: dict[str, float] = {}
    magnitude_deltas: dict[str, float] = {}
    magnitude_details: dict[str, dict[str, float]] = {}
    for field in ("penumbral_magnitude", "umbral_magnitude"):
        try:
            actual_magnitude = float(actual[field])
            reference_magnitude = float(reference[field])
            if not math.isfinite(actual_magnitude) or not math.isfinite(reference_magnitude):
                raise ValueError("magnitude must be finite")
            delta = actual_magnitude - reference_magnitude
            error = abs(delta)
        except (KeyError, TypeError, ValueError):
            failures.append(f"{field} is missing or invalid")
            continue
        magnitude_errors[field] = error
        magnitude_deltas[field] = delta
        magnitude_details[field] = {
            "actual": actual_magnitude,
            "reference": reference_magnitude,
            "delta": delta,
            "absolute_error": error,
        }
        if error > magnitude_tolerance:
            failures.append(
                f"{field} differs by {error:.6f} "
                f"(limit {magnitude_tolerance:.6f})"
            )

    gamma_error: float | None = None
    try:
        # EclipseKit's public gamma is an unsigned axis-distance magnitude.
        # EclipseWise's Gamma is signed, so compare absolute values.
        actual_gamma = float(actual["gamma"])
        reference_gamma = float(reference["gamma_signed"])
        if not math.isfinite(actual_gamma) or not math.isfinite(reference_gamma):
            raise ValueError("gamma must be finite")
        gamma_error = abs(abs(actual_gamma) - abs(reference_gamma))
        if gamma_error > gamma_tolerance:
            failures.append(
                f"|gamma| differs by {gamma_error:.6f} "
                f"(limit {gamma_tolerance:.6f})"
            )
    except (KeyError, TypeError, ValueError):
        failures.append("gamma is missing or invalid")

    finite_time_errors = [value for value in time_errors.values() if value is not None]
    return {
        "date": date,
        "status": "PASS" if not failures else "FAIL",
        "eclipse_type": actual_type,
        "time_errors_seconds": time_errors,
        "time_deltas_seconds": time_deltas,
        "contact_details": contact_details,
        "max_time_error_seconds": max(finite_time_errors, default=None),
        "magnitude_errors": magnitude_errors,
        "magnitude_deltas": magnitude_deltas,
        "magnitude_details": magnitude_details,
        "gamma_abs_error": gamma_error,
        "failures": failures,
        "source_url": reference["source_url"],
        "edge_case": reference.get("edge_case"),
    }


def validate_events(
    references: dict[str, Any],
    actual_events: list[dict[str, Any]],
    *,
    contact_tolerance_seconds: float = 30.0,
    magnitude_tolerance: float = 0.01,
    gamma_tolerance: float = 0.005,
) -> dict[str, Any]:
    """Match event payloads by greatest-eclipse civil date and compare all cases."""
    actual_by_date: dict[str, list[dict[str, Any]]] = {}
    for event in actual_events:
        date = str(event.get("maximum_ut1", ""))[:10]
        actual_by_date.setdefault(date, []).append(event)

    rows: list[dict[str, Any]] = []
    expected_dates: set[str] = set()
    for reference in references["cases"]:
        date = reference["date"]
        expected_dates.add(date)
        matches = actual_by_date.get(date, [])
        if not matches:
            rows.append({
                "date": date,
                "status": "FAIL",
                "failures": ["event not found in EclipseKit output"],
                "source_url": reference["source_url"],
                "edge_case": reference.get("edge_case"),
            })
            continue
        if len(matches) > 1:
            rows.append({
                "date": date,
                "status": "FAIL",
                "failures": [f"expected one event on date, found {len(matches)}"],
                "source_url": reference["source_url"],
                "edge_case": reference.get("edge_case"),
            })
            continue
        rows.append(compare_case(
            reference,
            matches[0],
            contact_tolerance_seconds=contact_tolerance_seconds,
            magnitude_tolerance=magnitude_tolerance,
            gamma_tolerance=gamma_tolerance,
        ))

    unexpected = sorted(set(actual_by_date) - expected_dates)
    passed = sum(row["status"] == "PASS" for row in rows)
    failed = len(rows) - passed
    checked_times = [
        value
        for row in rows
        for value in row.get("time_errors_seconds", {}).values()
        if value is not None
    ]
    checked_magnitudes = [
        value for row in rows for value in row.get("magnitude_errors", {}).values()
    ]
    return {
        "reference_title": references.get("title"),
        "reference_site": references.get("reference_site"),
        "reference_method": references.get("reference_method"),
        "reference_ephemeris": references.get("reference_ephemeris"),
        "independent_catalog": references.get("independent_catalog"),
        "tolerances": {
            "contact_seconds": contact_tolerance_seconds,
            "magnitude": magnitude_tolerance,
            "gamma_absolute": gamma_tolerance,
        },
        "summary": {
            "cases": len(rows),
            "passed": passed,
            "failed": failed,
            "unexpected_actual_events": unexpected,
            "maximum_contact_error_seconds": max(checked_times, default=None),
            "maximum_magnitude_error": max(checked_magnitudes, default=None),
            "all_passed": failed == 0 and not unexpected,
        },
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", default="de440s", help="JPL BSP kernel name or local path")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--start", default="2022-01-01", help="Inclusive start date")
    parser.add_argument("--end", default="2029-01-01", help="Exclusive end date")
    parser.add_argument("--contact-tolerance-seconds", type=float, default=30.0)
    parser.add_argument("--magnitude-tolerance", type=float, default=0.01)
    parser.add_argument("--gamma-tolerance", type=float, default=0.005)
    parser.add_argument(
        "--boundary-samples", type=int, default=96,
        help="Angular samples used to locate the closest point on the shadow boundary",
    )
    parser.add_argument(
        "--contact-step-seconds", type=float, default=300.0,
        help="Coarse time step used to bracket each contact root",
    )
    parser.add_argument(
        "--solver-tolerance-seconds", type=float, default=0.05,
        help="Bisection tolerance used when refining contact roots",
    )
    parser.add_argument(
        "--delta-t-seconds", type=float,
        help="Optional fixed Delta-T in seconds for reproducing a specific reference page",
    )
    parser.add_argument(
        "--use-reference-moon-radii", action="store_true",
        help="Use explicitly stored per-event lunar radii to reproduce rounded source semidiameters",
    )
    parser.add_argument(
        "--json-output", type=Path, help="Optional path for a machine-readable report"
    )
    args = parser.parse_args()

    for name, value in (
        ("contact tolerance", args.contact_tolerance_seconds),
        ("magnitude tolerance", args.magnitude_tolerance),
        ("gamma tolerance", args.gamma_tolerance),
        ("contact step", args.contact_step_seconds),
        ("solver tolerance", args.solver_tolerance_seconds),
    ):
        if not math.isfinite(value) or value < 0.0:
            parser.error(f"{name} must be finite and non-negative")
        if name in {"contact step", "solver tolerance"} and value == 0.0:
            parser.error(f"{name} must be greater than zero")

    if args.boundary_samples < 24:
        parser.error("boundary samples must be at least 24")
    if args.delta_t_seconds is not None and not math.isfinite(args.delta_t_seconds):
        parser.error("Delta-T must be finite")

    try:
        references = load_reference(args.reference)
        selected_cases = [
            case for case in references["cases"] if args.start <= case["date"] < args.end
        ]
        if not selected_cases:
            parser.error("the selected date interval contains no reference cases")
        selected_references = {**references, "cases": selected_cases}

        earth_orientation = (
            EarthOrientationConfig.fixed(args.delta_t_seconds)
            if args.delta_t_seconds is not None
            else EarthOrientationConfig.builtin()
        )
        engine = EclipseEngine(args.kernel, earth_orientation=earth_orientation)
        events = engine.find_lunar_eclipses(
            args.start,
            args.end,
            calendar="gregorian",
            shadow_model="herald_sinnott",
            shadow_enlargement=float(references["reference_shadow_enlargement"]),
            contact_step_seconds=args.contact_step_seconds,
            contact_tolerance_seconds=args.solver_tolerance_seconds,
            boundary_samples=args.boundary_samples,
        )
        radius_overrides = (
            reference_moon_radius_overrides(selected_references)
            if args.use_reference_moon_radii else {}
        )
        payloads = []
        for event in events:
            initial_payload = event.to_dict(calendar="gregorian")
            event_date = str(initial_payload["maximum_ut1"])[:10]
            reference_radius = radius_overrides.get(event_date)
            if reference_radius is not None:
                # Greatest eclipse is based on the shadow axis and does not depend
                # on lunar-disc radius. Re-solve contacts/magnitudes at this TT epoch.
                event = engine.calculate_lunar_eclipse(
                    event.maximum,
                    calendar="gregorian",
                    search_half_window_hours=18.0,
                    contact_search_half_window_hours=8.0,
                    contact_step_seconds=args.contact_step_seconds,
                    contact_tolerance_seconds=args.solver_tolerance_seconds,
                    moon_radius_km=reference_radius,
                    shadow_enlargement=float(references["reference_shadow_enlargement"]),
                    shadow_model="herald_sinnott",
                    boundary_samples=args.boundary_samples,
                )
                if event is None:
                    raise RuntimeError(
                        f"event {event_date} disappeared when applying its reference Moon radius"
                    )
            payloads.append(event.to_dict(calendar="gregorian"))
        report = validate_events(
            selected_references,
            payloads,
            contact_tolerance_seconds=args.contact_tolerance_seconds,
            magnitude_tolerance=args.magnitude_tolerance,
            gamma_tolerance=args.gamma_tolerance,
        )
        report["run_configuration"] = {
            "kernel": args.kernel,
            "start": args.start,
            "end_exclusive": args.end,
            "boundary_samples": args.boundary_samples,
            "contact_step_seconds": args.contact_step_seconds,
            "solver_tolerance_seconds": args.solver_tolerance_seconds,
            "delta_t_seconds": args.delta_t_seconds,
            "default_moon_radius_km": MEAN_MOON_RADIUS_KM,
            "moon_radius_policy": (
                "reference-specific overrides" if args.use_reference_moon_radii
                else "mean lunar radius"
            ),
            "reference_moon_radius_overrides_km": radius_overrides,
        }
    except Exception as exc:  # keep CLI diagnostics actionable for local runs
        parser.exit(2, f"Validation could not run: {type(exc).__name__}: {exc}\n")

    summary = report["summary"]
    delta_t_label = (
        f"{args.delta_t_seconds:g}s"
        if args.delta_t_seconds is not None
        else "Skyfield builtin"
    )
    print(
        f"Configuration: kernel={args.kernel!s}; boundary_samples={args.boundary_samples}; "
        f"contact_step={args.contact_step_seconds:g}s; "
        f"solver_tolerance={args.solver_tolerance_seconds:g}s; Delta-T={delta_t_label}"
    )
    if args.use_reference_moon_radii:
        print(f"Moon-radius policy: reference-specific overrides {radius_overrides}")
    else:
        print(f"Moon-radius policy: mean lunar radius ({MEAN_MOON_RADIUS_KM:g} km)")
    print(
        f"Lunar reference validation: {summary['passed']}/{summary['cases']} passed; "
        f"{summary['failed']} failed; "
        f"max contact error={summary['maximum_contact_error_seconds']} s; "
        f"max magnitude error={summary['maximum_magnitude_error']}"
    )
    for row in report["results"]:
        max_error = row.get("max_time_error_seconds")
        suffix = f" (max time delta {max_error:.2f}s)" if max_error is not None else ""
        print(f"[{row['status']}] {row['date']} {row.get('eclipse_type', '')}{suffix}")
        for failure in row.get("failures", []):
            print(f"    - {failure}")
        if row.get("status") == "FAIL":
            for field, detail in row.get("magnitude_details", {}).items():
                print(
                    f"      {field}: actual={detail['actual']:.9f}; "
                    f"reference={detail['reference']:.9f}; "
                    f"delta={detail['delta']:+.9f}"
                )
            for name, detail in row.get("contact_details", {}).items():
                delta = detail.get("delta_seconds")
                if delta is not None:
                    print(
                        f"      {name}: actual={detail['actual_ut1']}; "
                        f"reference={detail['reference_ut1']}; delta={delta:+.3f}s"
                    )
    for date in summary["unexpected_actual_events"]:
        print(f"[UNREFERENCED] unexpected EclipseKit event on {date}")

    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"JSON report: {args.json_output}")

    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
