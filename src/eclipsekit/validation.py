"""Independent-reference validation for local and geocentric eclipse timings.

Reference times must be UTC ISO-8601 strings with an explicit timezone. Each
fixture records its source resolution and comparison tolerance; the tool never
silently treats minute-rounded values as millisecond-accurate observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import Observer
from .timeutils import time_to_utc_iso


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite number, not bool")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number")
    return number


def parse_utc_datetime(value: str) -> datetime:
    """Parse an ISO-8601 timestamp that includes an explicit UTC offset."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("UTC timestamp must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Timestamp must include Z or an explicit UTC offset: {value!r}")
    return parsed.astimezone(timezone.utc)


def time_difference_seconds(computed_utc: str, expected_utc: str) -> float:
    """Return signed ``computed - expected`` time difference in seconds."""
    computed = parse_utc_datetime(computed_utc)
    expected = parse_utc_datetime(expected_utc)
    return (computed - expected).total_seconds()


@dataclass(frozen=True, slots=True)
class ReferenceLocalCase:
    case_id: str
    name: str
    event_time_utc: str
    latitude: float
    longitude: float
    elevation_m: float
    expected_contacts_utc: Mapping[str, str]
    contact_tolerance_seconds: float
    source_url: str
    source_precision_seconds: float
    source_notes: str = ""
    expected_eclipse_type: str | None = None
    expected_maximum_utc: str | None = None
    maximum_tolerance_seconds: float | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReferenceLocalCase":
        required = (
            "case_id", "name", "event_time_utc", "latitude", "longitude",
            "expected_contacts_utc", "contact_tolerance_seconds", "source_url",
            "source_precision_seconds",
        )
        if not isinstance(value, Mapping):
            raise ValueError("Each local reference case must be a JSON object")
        missing = [key for key in required if key not in value]
        if missing:
            raise ValueError(f"Reference case is missing fields: {', '.join(missing)}")
        parse_utc_datetime(str(value["event_time_utc"]))
        raw_contacts = value["expected_contacts_utc"]
        if not isinstance(raw_contacts, Mapping):
            raise ValueError("expected_contacts_utc must be a JSON object")
        contacts = dict(raw_contacts)
        if not contacts:
            raise ValueError("expected_contacts_utc must contain at least one contact")
        for key, timestamp in contacts.items():
            if key not in {"C1", "C2", "C3", "C4"}:
                raise ValueError(f"Unsupported contact name: {key!r}")
            parse_utc_datetime(str(timestamp))
        expected_maximum = value.get("expected_maximum_utc")
        if expected_maximum:
            parse_utc_datetime(str(expected_maximum))
        latitude = _finite_number(value["latitude"], "latitude")
        longitude = _finite_number(value["longitude"], "longitude")
        elevation = _finite_number(value.get("elevation_m", 0.0), "elevation_m")
        if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
            raise ValueError("Reference observer coordinates are outside WGS84 bounds")
        tolerance = _finite_number(value["contact_tolerance_seconds"], "contact_tolerance_seconds")
        precision = _finite_number(value["source_precision_seconds"], "source_precision_seconds")
        if tolerance < 0 or precision <= 0:
            raise ValueError("Tolerances must be non-negative and precision must be positive")
        for key in ("case_id", "name", "source_url"):
            if not str(value[key]).strip():
                raise ValueError(f"Reference case field {key!r} must be non-empty")
        expected_type = value.get("expected_eclipse_type")
        if expected_type is not None and str(expected_type).casefold() not in {
            "total", "annular", "partial"
        }:
            raise ValueError("expected_eclipse_type must be total, annular, partial, or omitted")
        maximum_tolerance = value.get("maximum_tolerance_seconds")
        if maximum_tolerance is not None:
            maximum_tolerance = _finite_number(maximum_tolerance, "maximum_tolerance_seconds")
            if maximum_tolerance < 0:
                raise ValueError("maximum_tolerance_seconds must be non-negative")
        return cls(
            case_id=str(value["case_id"]),
            name=str(value["name"]),
            event_time_utc=str(value["event_time_utc"]),
            latitude=latitude,
            longitude=longitude,
            elevation_m=elevation,
            expected_contacts_utc=contacts,
            contact_tolerance_seconds=tolerance,
            source_url=str(value["source_url"]),
            source_precision_seconds=precision,
            source_notes=str(value.get("source_notes", "")),
            expected_eclipse_type=(
                str(expected_type).casefold() if expected_type else None
            ),
            expected_maximum_utc=(str(expected_maximum) if expected_maximum else None),
            maximum_tolerance_seconds=maximum_tolerance,
        )


@dataclass(frozen=True, slots=True)
class ReferenceGlobalMaximumCase:
    case_id: str
    name: str
    event_time_utc: str
    expected_maximum_utc: str
    tolerance_seconds: float
    source_url: str
    source_notes: str = ""
    expected_eclipse_type: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReferenceGlobalMaximumCase":
        if not isinstance(value, Mapping):
            raise ValueError("Each global-maximum reference case must be a JSON object")
        required = ("case_id", "name", "event_time_utc", "expected_maximum_utc", "tolerance_seconds", "source_url")
        missing = [key for key in required if key not in value]
        if missing:
            raise ValueError(f"Global maximum case is missing fields: {', '.join(missing)}")
        parse_utc_datetime(str(value["event_time_utc"]))
        parse_utc_datetime(str(value["expected_maximum_utc"]))
        tolerance = _finite_number(value["tolerance_seconds"], "tolerance_seconds")
        if tolerance < 0:
            raise ValueError("Global maximum tolerance must be non-negative")
        for key in ("case_id", "name", "source_url"):
            if not str(value[key]).strip():
                raise ValueError(f"Global reference field {key!r} must be non-empty")
        expected_type = value.get("expected_eclipse_type")
        if expected_type is not None and str(expected_type).casefold() not in {
            "total", "annular", "partial", "hybrid"
        }:
            raise ValueError(
                "global expected_eclipse_type must be total, annular, partial, hybrid, or omitted"
            )
        return cls(
            case_id=str(value["case_id"]), name=str(value["name"]),
            event_time_utc=str(value["event_time_utc"]),
            expected_maximum_utc=str(value["expected_maximum_utc"]),
            tolerance_seconds=tolerance, source_url=str(value["source_url"]),
            source_notes=str(value.get("source_notes", "")),
            expected_eclipse_type=(str(expected_type).casefold() if expected_type else None),
        )


def load_reference_cases(filename: str | Path) -> tuple[list[ReferenceLocalCase], list[ReferenceGlobalMaximumCase]]:
    """Load local-contact and global-maximum reference cases from JSON."""
    path = Path(filename).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Reference case file not found: {path}")
    with path.open("r", encoding="utf-8") as stream:
        document = json.load(stream)
    if not isinstance(document, Mapping):
        raise ValueError("Reference file root must be a JSON object")
    if document.get("schema_version") != 1:
        raise ValueError("Unsupported reference-case schema_version; expected 1")
    raw_local = document.get("local_cases", [])
    raw_global = document.get("global_maximum_cases", [])
    if not isinstance(raw_local, list) or not isinstance(raw_global, list):
        raise ValueError("local_cases and global_maximum_cases must be JSON arrays")
    local = [ReferenceLocalCase.from_mapping(item) for item in raw_local]
    global_cases = [
        ReferenceGlobalMaximumCase.from_mapping(item)
        for item in raw_global
    ]
    identifiers = [case.case_id for case in (*local, *global_cases)]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Reference case_id values must be unique across the fixture")
    if not local and not global_cases:
        raise ValueError("Reference file contains no local or global cases")
    return local, global_cases


def _compare_time(
    label: str, computed: Any | None, expected_utc: str, tolerance_seconds: float
) -> dict[str, Any]:
    computed_utc = time_to_utc_iso(computed) if computed is not None else None
    delta = time_difference_seconds(computed_utc, expected_utc) if computed_utc else None
    passed = delta is not None and abs(delta) <= tolerance_seconds
    return {
        "label": label,
        "expected_utc": expected_utc,
        "computed_utc": computed_utc,
        "delta_seconds": delta,
        "absolute_error_seconds": abs(delta) if delta is not None else None,
        "tolerance_seconds": tolerance_seconds,
        "passed": passed,
    }


def run_local_reference_cases(engine: Any, cases: Iterable[ReferenceLocalCase]) -> list[dict[str, Any]]:
    """Run local circumstances for each fixture and compare expected contacts."""
    results: list[dict[str, Any]] = []
    for case in cases:
        observer = Observer(
            case.latitude, case.longitude, case.elevation_m,
            name=case.name, country=None,
        )
        try:
            local = engine.calculate_local(
                observer, case.event_time_utc,
                search_window_hours=6.0,
                find_next_if_none=False,
                include_sunrise_sunset=False,
                include_shadow_metrics=False,
                include_planets=False,
            )
        except Exception as exc:
            results.append({
                "case_id": case.case_id,
                "name": case.name,
                "status": "ERROR",
                "reason": f"Calculation raised {type(exc).__name__}: {exc}",
                "source_url": case.source_url,
                "source_notes": case.source_notes,
                "checks": [],
            })
            continue
        if local is None:
            results.append({
                "case_id": case.case_id,
                "name": case.name,
                "status": "FAIL",
                "reason": "No local solar eclipse was returned for this reference case.",
                "source_url": case.source_url,
                "source_notes": case.source_notes,
                "checks": [],
            })
            continue

        actual_contacts = local.contacts.as_dict()
        checks = [
            _compare_time(
                contact, actual_contacts.get(contact), expected,
                case.contact_tolerance_seconds,
            )
            for contact, expected in case.expected_contacts_utc.items()
        ]
        type_check = None
        if case.expected_eclipse_type:
            type_check = {
                "expected": case.expected_eclipse_type,
                "computed": local.eclipse_type.casefold(),
                "passed": local.eclipse_type.casefold() == case.expected_eclipse_type,
            }
        maximum_check = None
        if case.expected_maximum_utc:
            maximum_check = _compare_time(
                "Maximum", local.maximum, case.expected_maximum_utc,
                case.maximum_tolerance_seconds
                if case.maximum_tolerance_seconds is not None
                else case.contact_tolerance_seconds,
            )
        passed = all(item["passed"] for item in checks)
        if type_check is not None:
            passed = passed and bool(type_check["passed"])
        if maximum_check is not None:
            passed = passed and bool(maximum_check["passed"])
        results.append({
            "case_id": case.case_id,
            "name": case.name,
            "status": "PASS" if passed else "FAIL",
            "computed_eclipse_type": local.eclipse_type,
            "source_url": case.source_url,
            "source_precision_seconds": case.source_precision_seconds,
            "source_notes": case.source_notes,
            "checks": checks,
            "type_check": type_check,
            "maximum_check": maximum_check,
            "warnings": list(local.warnings),
        })
    return results


def run_global_maximum_reference_cases(
    engine: Any, cases: Iterable[ReferenceGlobalMaximumCase]
) -> list[dict[str, Any]]:
    """Compare geocentric minimum-separation times with published references."""
    results: list[dict[str, Any]] = []
    for case in cases:
        try:
            computed = engine.find_global_maximum(case.event_time_utc, half_window_hours=6.0)
            check = _compare_time(
                "Geocentric maximum", computed, case.expected_maximum_utc, case.tolerance_seconds
            )
            status = "PASS" if check["passed"] else "FAIL"
            reason = None
        except Exception as exc:
            check = None
            status = "ERROR"
            reason = f"Calculation raised {type(exc).__name__}: {exc}"
        results.append({
            "case_id": case.case_id,
            "name": case.name,
            "status": status,
            "reference_eclipse_type": case.expected_eclipse_type,
            "source_url": case.source_url,
            "source_notes": case.source_notes,
            "check": check,
            "reason": reason,
        })
    return results


def run_validation_suite(
    engine: Any,
    local_cases: Iterable[ReferenceLocalCase],
    global_cases: Iterable[ReferenceGlobalMaximumCase],
) -> dict[str, Any]:
    """Run every configured reference case and return a JSON-ready report."""
    local_results = run_local_reference_cases(engine, local_cases)
    global_results = run_global_maximum_reference_cases(engine, global_cases)
    all_results = local_results + global_results
    return {
        "schema_version": 1,
        "status": (
            "PASS" if all_results and all(item["status"] == "PASS" for item in all_results)
            else "FAIL"
        ),
        "local_cases": local_results,
        "global_maximum_cases": global_results,
    }


def render_validation_markdown(report: Mapping[str, Any]) -> str:
    """Render a compact Markdown table for a validation run."""
    lines = [
        "# EclipseKit scientific validation report",
        "",
        f"**Overall status:** {report.get('status', 'UNKNOWN')}",
        "",
        "## Local circumstances",
        "",
        "| Case | Status | Check | Computed UTC | Expected UTC | Error (s) | Tolerance (s) |",
        "|---|---|---|---|---|---:|---:|",
    ]
    for case in report.get("local_cases", []):
        if not case.get("checks"):
            lines.append(
                f"| {case['name']} | {case['status']} | no result | — | — | — | — |"
            )
            continue
        for check in case["checks"]:
            delta = check["delta_seconds"]
            lines.append(
                f"| {case['name']} | {case['status']} | {check['label']} | "
                f"{check['computed_utc'] or '—'} | {check['expected_utc']} | "
                f"{delta if delta is not None else '—'} | {check['tolerance_seconds']} |"
            )
    lines.extend([
        "",
        "## Geocentric maximum",
        "",
        "| Case | Status | Computed UTC | Expected UTC | Error (s) | Tolerance (s) |",
        "|---|---|---|---|---:|---:|",
    ])
    for case in report.get("global_maximum_cases", []):
        check = case.get("check")
        if check is None:
            lines.append(f"| {case['name']} | {case['status']} | — | — | — | — |")
            continue
        delta = check["delta_seconds"]
        lines.append(
            f"| {case['name']} | {case['status']} | {check['computed_utc'] or '—'} | "
            f"{check['expected_utc']} | {delta if delta is not None else '—'} | "
            f"{check['tolerance_seconds']} |"
        )
    lines.extend([
        "",
        "> These comparisons are only as strong as the published references, "
        "their time precision, and the observer coordinates used. They do not "
        "validate every EclipseKit feature or the optional lunar-limb model.",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Compatibility CLI entry point; runs the complete Phase 6 suite."""
    from .validation_framework import main as full_validation_main
    return full_validation_main(argv)


if __name__ == "__main__":  # pragma: no cover - exercised through console entry point
    raise SystemExit(main())
