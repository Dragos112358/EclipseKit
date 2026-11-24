"""Phase 6: end-to-end scientific validation orchestration.

The framework combines independently sourced local circumstances, geocentric
maximum times, sparse global-path tables, and a published Besselian-element
regression. It records provenance and model/time-scale assumptions in every
report. A validation PASS applies only to the configured fixtures and limits.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.metadata
import hashlib
import json
import math
from pathlib import Path
import platform
from typing import Any, Iterable, Mapping

from .validation import (
    ReferenceGlobalMaximumCase,
    ReferenceLocalCase,
    load_reference_cases,
    parse_utc_datetime,
    run_validation_suite,
)


@dataclass(frozen=True, slots=True)
class PathReferenceCase:
    """One NASA path-table subset and the limits used to screen it."""

    case_id: str
    name: str
    event_time_utc: str
    reference_file: Path
    search_radius_hours: float
    tolerance_km: float
    source_url: str
    source_time_step_seconds: float
    source_coordinate_resolution_arcmin: float
    source_notes: str = ""

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any], *, base_dir: str | Path
    ) -> "PathReferenceCase":
        required = (
            "case_id", "name", "event_time_utc", "reference_file",
            "search_radius_hours", "tolerance_km", "source_url",
            "source_time_step_seconds", "source_coordinate_resolution_arcmin",
        )
        if not isinstance(value, Mapping):
            raise ValueError("Each path reference case must be a JSON object")
        missing = [key for key in required if key not in value]
        if missing:
            raise ValueError(f"Path reference case is missing fields: {', '.join(missing)}")
        parse_utc_datetime(str(value["event_time_utc"]))
        search_radius = _finite_number(value["search_radius_hours"], "search_radius_hours")
        tolerance = _finite_number(value["tolerance_km"], "tolerance_km")
        time_step = _finite_number(value["source_time_step_seconds"], "source_time_step_seconds")
        coordinate_resolution = _finite_number(
            value["source_coordinate_resolution_arcmin"],
            "source_coordinate_resolution_arcmin",
        )
        if search_radius <= 0 or tolerance <= 0 or time_step <= 0 or coordinate_resolution <= 0:
            raise ValueError("Path search radius, tolerances, and source resolutions must be positive")
        for key in ("case_id", "name", "source_url", "reference_file"):
            if not str(value[key]).strip():
                raise ValueError(f"Path reference field {key!r} must be non-empty")
        base_path = Path(base_dir).expanduser().resolve()
        reference_path = (base_path / str(value["reference_file"])).resolve()
        if not reference_path.is_relative_to(base_path):
            raise ValueError("reference_file must remain inside the manifest directory")
        return cls(
            case_id=str(value["case_id"]),
            name=str(value["name"]),
            event_time_utc=str(value["event_time_utc"]),
            reference_file=reference_path.resolve(),
            search_radius_hours=search_radius,
            tolerance_km=tolerance,
            source_url=str(value["source_url"]),
            source_time_step_seconds=time_step,
            source_coordinate_resolution_arcmin=coordinate_resolution,
            source_notes=str(value.get("source_notes", "")),
        )


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number, not bool")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def load_path_reference_cases(filename: str | Path) -> list[PathReferenceCase]:
    """Load the versioned manifest describing NASA central-line subsets."""
    path = Path(filename).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Path reference manifest not found: {path}")
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
        raise ValueError("Unsupported path-reference manifest; expected schema_version 1")
    raw_cases = payload.get("path_cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Path reference manifest must contain a non-empty path_cases list")
    cases = [PathReferenceCase.from_mapping(item, base_dir=path.parent) for item in raw_cases]
    identifiers = [case.case_id for case in cases]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Path reference case_id values must be unique")
    for case in cases:
        if not case.reference_file.is_file():
            raise FileNotFoundError(
                f"Path reference file for {case.case_id!r} not found: {case.reference_file}"
            )
    return cases


def run_path_reference_cases(
    engine: Any,
    cases: Iterable[PathReferenceCase],
    *,
    samples: int = 301,
) -> list[dict[str, Any]]:
    """Compare the engine central axis to every configured published path subset.

    The source NASA path tables label their clock as Universal Time. The CSV
    fixtures use ``time_ut1`` to preserve that convention; the path comparator
    converts those rows through the engine's UT1 time scale.
    """
    if isinstance(samples, bool) or int(samples) != samples or samples < 3:
        raise ValueError("samples must be an integer >= 3")
    from .path_validation import compare_shadow_path, load_path_reference

    results: list[dict[str, Any]] = []
    for case in cases:
        try:
            reference = load_path_reference(case.reference_file)
            computed = engine.global_path_for_eclipse(
                case.event_time_utc,
                search_radius_hours=case.search_radius_hours,
                samples=int(samples),
            )
            comparison = compare_shadow_path(
                engine, computed, reference, reference_clock="auto"
            )
            maximum_error = comparison["max_error_km"]
            passed = (
                comparison["error_count"] == 0
                and comparison["successful_comparisons"] == comparison["reference_count"]
                and maximum_error is not None
                and maximum_error <= case.tolerance_km
            )
            result = {
                "case_id": case.case_id,
                "name": case.name,
                "status": "PASS" if passed else "FAIL",
                "event_time_utc": case.event_time_utc,
                "reference_file": str(case.reference_file),
                "source_url": case.source_url,
                "source_notes": case.source_notes,
                "source_time_step_seconds": case.source_time_step_seconds,
                "source_coordinate_resolution_arcmin": case.source_coordinate_resolution_arcmin,
                "computed_path_points": len(computed),
                "tolerance_km": case.tolerance_km,
                **comparison,
            }
        except Exception as exc:
            result = {
                "case_id": case.case_id,
                "name": case.name,
                "status": "ERROR",
                "event_time_utc": case.event_time_utc,
                "reference_file": str(case.reference_file),
                "source_url": case.source_url,
                "source_notes": case.source_notes,
                "reason": f"{type(exc).__name__}: {exc}",
                "comparisons": [],
            }
        results.append(result)
    return results


def _interpolate_reference_track(
    samples: list[Mapping[str, Any]], target_offset_seconds: float
) -> tuple[float, float]:
    if len(samples) < 2:
        raise ValueError("Besselian reference track requires at least two samples")
    ordered = sorted(samples, key=lambda item: _finite_number(item["offset_seconds"], "offset_seconds"))
    offsets = [_finite_number(item["offset_seconds"], "offset_seconds") for item in ordered]
    if any(right <= left for left, right in zip(offsets, offsets[1:])):
        raise ValueError("Besselian reference track offsets must be strictly increasing")
    for left, right in zip(ordered, ordered[1:]):
        t0 = _finite_number(left["offset_seconds"], "offset_seconds")
        t1 = _finite_number(right["offset_seconds"], "offset_seconds")
        if t0 <= target_offset_seconds <= t1:
            if t1 <= t0:
                raise ValueError("Besselian reference track offsets must be increasing")
            fraction = (target_offset_seconds - t0) / (t1 - t0)
            lat0 = _finite_number(left["latitude_deg"], "latitude_deg")
            lat1 = _finite_number(right["latitude_deg"], "latitude_deg")
            lon0 = _finite_number(left["longitude_deg"], "longitude_deg")
            lon1 = _finite_number(right["longitude_deg"], "longitude_deg")
            if not -90.0 <= lat0 <= 90.0 or not -90.0 <= lat1 <= 90.0:
                raise ValueError("Besselian reference latitude is outside [-90, 90]")
            if not -180.0 <= lon0 <= 180.0 or not -180.0 <= lon1 <= 180.0:
                raise ValueError("Besselian reference longitude is outside [-180, 180]")
            latitude = lat0 + fraction * (lat1 - lat0)
            delta_lon = (lon1 - lon0 + 180.0) % 360.0 - 180.0
            longitude = (lon0 + fraction * delta_lon + 180.0) % 360.0 - 180.0
            return latitude, longitude
    raise ValueError("Besselian reference track does not bracket the comparison epoch")


def run_besselian_reference_validation(filename: str | Path) -> dict[str, Any]:
    """Validate the Besselian polynomial backend against NASA's 1999 path data.

    The expected greatest-eclipse epoch is published in TDT/TT. The path table
    is labelled Universal Time, so the comparison epoch is converted using the
    same published ΔT and linearly interpolated between adjacent one-minute
    central-line rows. Position tolerance includes the path-table coordinate
    rounding and the fundamental-plane/ground-track reduction.
    """
    from .besselian import BesselianElements, BesselianSolver
    from .models import Observer
    from .path_validation import great_circle_distance_km

    path = Path(filename).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Besselian reference fixture not found: {path}")
    with path.open("r", encoding="utf-8") as stream:
        reference = json.load(stream)
    if not isinstance(reference, Mapping) or reference.get("schema_version") != 1:
        raise ValueError("Unsupported Besselian validation reference; expected schema_version 1")

    raw_elements_file = reference.get("elements_file")
    if not isinstance(raw_elements_file, str) or not raw_elements_file.strip():
        raise ValueError("Besselian reference must name an elements_file")
    base_dir = path.parent.resolve()
    elements_file = (base_dir / raw_elements_file).resolve()
    if not elements_file.is_relative_to(base_dir):
        raise ValueError("elements_file must remain inside the reference directory")
    elements = BesselianElements.from_json(elements_file)
    delta_t = _finite_number(reference["delta_t_seconds"], "delta_t_seconds")
    expected_offset = _finite_number(
        reference["expected_maximum_offset_seconds"], "expected_maximum_offset_seconds"
    )
    offset_tolerance = _finite_number(
        reference["maximum_offset_tolerance_seconds"], "maximum_offset_tolerance_seconds"
    )
    position_tolerance = _finite_number(
        reference["central_line_position_tolerance_km"], "central_line_position_tolerance_km"
    )
    if offset_tolerance < 0.0 or position_tolerance <= 0.0:
        raise ValueError("Besselian maximum tolerance must be non-negative and position tolerance positive")
    if not isinstance(reference.get("central_line_reference_samples"), list):
        raise ValueError("central_line_reference_samples must be a JSON array")
    raw_observer = reference.get("local_observer")
    if not isinstance(raw_observer, Mapping):
        raise ValueError("local_observer must be a JSON object")
    expected_type = str(reference.get("expected_eclipse_type", "")).casefold()
    if expected_type not in {"total", "annular", "partial"}:
        raise ValueError("expected_eclipse_type must be total, annular, or partial")
    solver = BesselianSolver()
    maximum_jd_tt = solver.find_global_maximum(elements)
    actual_offset = (maximum_jd_tt - elements.epoch_tt_jd) * 86400.0
    offset_error = actual_offset - expected_offset
    maximum_check = {
        "expected_offset_seconds_from_epoch_tt": expected_offset,
        "computed_offset_seconds_from_epoch_tt": actual_offset,
        "delta_seconds": offset_error,
        "tolerance_seconds": offset_tolerance,
        "passed": abs(offset_error) <= offset_tolerance,
    }

    central_line_check: dict[str, Any]
    point = solver.central_line_point(
        elements, maximum_jd_tt, delta_t_seconds=delta_t
    )
    if point is None:
        central_line_check = {
            "passed": False,
            "reason": "Besselian shadow axis does not intersect WGS84 at greatest eclipse.",
        }
    else:
        # The path-table clock is UT1; the element epoch is TT/TDT.
        expected_ut1_offset = actual_offset - delta_t
        raw_track = reference.get("central_line_reference_samples")
        if not isinstance(raw_track, list):
            raise ValueError("central_line_reference_samples must be a JSON array")
        expected_latitude, expected_longitude = _interpolate_reference_track(
            raw_track, expected_ut1_offset
        )
        error_km = great_circle_distance_km(
            point.latitude, point.longitude, expected_latitude, expected_longitude
        )
        central_line_check = {
            "computed_latitude_deg": point.latitude,
            "computed_longitude_deg": point.longitude,
            "reference_latitude_deg": expected_latitude,
            "reference_longitude_deg": expected_longitude,
            "position_error_km": error_km,
            "tolerance_km": position_tolerance,
            "reference_clock": "UT1",
            "computed_clock_conversion": "TT minus published Delta-T",
            "passed": error_km <= position_tolerance,
        }

    observer = Observer(
        float(raw_observer["latitude_deg"]),
        float(raw_observer["longitude_deg"]),
        float(raw_observer.get("elevation_m", 0.0)),
        name=str(raw_observer.get("name", "Besselian reference observer")),
    )
    local = solver.calculate_local(elements, observer, delta_t_seconds=delta_t)
    type_check = {
        "expected": expected_type,
        "computed": local.eclipse_type.casefold(),
        "passed": local.eclipse_type.casefold() == expected_type,
    }
    expected_duration = _finite_number(
        reference["expected_central_phase_duration_seconds"],
        "expected_central_phase_duration_seconds",
    )
    duration_tolerance = _finite_number(
        reference["central_phase_duration_tolerance_seconds"],
        "central_phase_duration_tolerance_seconds",
    )
    if duration_tolerance < 0.0:
        raise ValueError("central_phase_duration_tolerance_seconds must be non-negative")
    actual_duration = local.central_phase_duration_seconds
    duration_error = (
        actual_duration - expected_duration if actual_duration is not None else None
    )
    duration_check = {
        "expected_seconds": expected_duration,
        "computed_seconds": actual_duration,
        "delta_seconds": duration_error,
        "tolerance_seconds": duration_tolerance,
        "passed": duration_error is not None and abs(duration_error) <= duration_tolerance,
    }
    contacts = sorted(local.contacts.values(), key=lambda contact: contact.jd_tt)
    contacts_ordered = all(
        contacts[index].jd_tt < contacts[index + 1].jd_tt
        for index in range(len(contacts) - 1)
    )
    contacts_check = {
        "required_count": 4,
        "computed_names": [contact.name for contact in contacts],
        "all_roots_converged": bool(contacts) and all(
            contact.root_result.converged for contact in contacts
        ),
        "chronological": contacts_ordered,
        "passed": (
            set(local.contacts) == {"C1", "C2", "C3", "C4"}
            and len(contacts) == 4
            and all(contact.root_result.converged for contact in contacts)
            and contacts_ordered
        ),
    }
    checks = {
        "greatest_eclipse_epoch": maximum_check,
        "central_line_position": central_line_check,
        "local_eclipse_type": type_check,
        "central_duration": duration_check,
        "local_contacts": contacts_check,
    }
    passed = all(item.get("passed", False) for item in checks.values())
    case_id = str(reference.get("case_id", "besselian-reference")).strip()
    case_name = str(reference.get("name", "NASA 1999 Besselian regression")).strip()
    source_url = str(reference.get("source_url", "")).strip()
    if not case_id or not case_name or not source_url:
        raise ValueError("Besselian reference must include non-empty case_id, name, and source_url")
    return {
        "case_id": case_id,
        "name": case_name,
        "status": "PASS" if passed else "FAIL",
        "source_url": source_url,
        "source_notes": str(reference.get("source_notes", "")),
        "elements_file": str(elements_file),
        "elements_source": elements.source,
        "elements_ephemeris": elements.ephemeris,
        "delta_t_seconds": delta_t,
        "checks": checks,
        "warnings": list(local.warnings),
    }



def run_direct_besselian_diagnostic(
    engine: Any, filename: str | Path
) -> dict[str, Any]:
    """Compare the active direct engine with the published-element Besselian path.

    This is a diagnostic, not an acceptance test. The Besselian fixture uses
    NASA's VSOP87/ELP2000-82 coefficients and fixed published ΔT, while the
    direct engine may use DE440s and a different Earth-orientation source.
    Differences therefore quantify cross-model divergence; they are not
    automatically failures or estimates of either model's true error.
    """
    from .besselian import BesselianElements, BesselianSolver
    from .models import Observer

    path = Path(filename).expanduser()
    with path.open("r", encoding="utf-8") as stream:
        reference = json.load(stream)
    if not isinstance(reference, Mapping):
        raise ValueError("Besselian reference root must be a JSON object")
    if not hasattr(engine, "calculate_local") or not hasattr(engine, "ts"):
        return {
            "status": "NOT_AVAILABLE",
            "reason": "Engine must expose calculate_local() and a Skyfield timescale.",
        }

    elements_path = (path.parent.resolve() / str(reference["elements_file"])).resolve()
    if not elements_path.is_relative_to(path.parent.resolve()):
        raise ValueError("Besselian elements file must remain inside the reference directory")
    elements = BesselianElements.from_json(elements_path)
    delta_t = _finite_number(reference["delta_t_seconds"], "delta_t_seconds")
    observer_data = reference["local_observer"]
    observer = Observer(
        float(observer_data["latitude_deg"]),
        float(observer_data["longitude_deg"]),
        float(observer_data.get("elevation_m", 0.0)),
        name=str(observer_data.get("name", "Besselian comparison observer")),
    )
    config = getattr(engine, "config", None)
    solver_config = getattr(engine, "solver_config", None)
    besselian_solver = BesselianSolver(
        config=getattr(config, "besselian", None),
        solver_config=solver_config,
    )
    besselian_local = besselian_solver.calculate_local(
        elements, observer, delta_t_seconds=delta_t
    )
    if besselian_local.maximum_jd_tt is None:
        return {
            "status": "NOT_COMPARABLE",
            "reason": "The Besselian backend did not return a local maximum for this observer.",
            "observer": observer.to_dict() if hasattr(observer, "to_dict") else {
                "latitude_deg": observer.latitude,
                "longitude_deg": observer.longitude,
                "elevation_m": observer.elevation_m,
            },
        }

    center_time = engine.ts.tt_jd(float(besselian_local.maximum_jd_tt))
    direct_local = engine.calculate_local(
        observer,
        center_time,
        search_window_hours=6.0,
        find_next_if_none=False,
        include_sunrise_sunset=False,
        include_shadow_metrics=False,
        include_planets=False,
    )
    if direct_local is None:
        return {
            "status": "NOT_COMPARABLE",
            "reason": "The direct engine returned no local event for the Besselian comparison observer.",
        }

    direct_contacts = direct_local.contacts.as_dict()
    contact_deltas: dict[str, Any] = {}
    for name in ("C1", "C2", "C3", "C4"):
        besselian_contact = besselian_local.contacts.get(name)
        direct_contact = direct_contacts.get(name)
        if besselian_contact is None or direct_contact is None:
            contact_deltas[name] = {
                "status": "NOT_COMMON",
                "besselian_present": besselian_contact is not None,
                "direct_present": direct_contact is not None,
                "delta_direct_minus_besselian_seconds": None,
            }
        else:
            contact_deltas[name] = {
                "status": "COMPARED",
                "besselian_jd_tt": float(besselian_contact.jd_tt),
                "direct_jd_tt": float(direct_contact.tt),
                "delta_direct_minus_besselian_seconds": (
                    float(direct_contact.tt) - float(besselian_contact.jd_tt)
                ) * 86400.0,
            }

    direct_maximum_jd_tt = float(direct_local.maximum.tt)
    besselian_maximum_jd_tt = float(besselian_local.maximum_jd_tt)
    direct_duration = direct_local.central_phase_duration_seconds
    besselian_duration = besselian_local.central_phase_duration_seconds
    duration_delta = (
        float(direct_duration) - float(besselian_duration)
        if direct_duration is not None and besselian_duration is not None else None
    )
    return {
        "status": "DIAGNOSTIC",
        "observer": {
            "latitude_deg": observer.latitude,
            "longitude_deg": observer.longitude,
            "elevation_m": observer.elevation_m,
            "name": observer.name,
        },
        "besselian_source_ephemeris": elements.ephemeris,
        "besselian_delta_t_seconds": delta_t,
        "direct_time_scale_mode": getattr(engine, "time_scale_mode", "not exposed"),
        "direct_configuration": config.to_dict() if config is not None and hasattr(config, "to_dict") else None,
        "eclipse_type": {
            "besselian": besselian_local.eclipse_type,
            "direct": direct_local.eclipse_type,
            "matches": besselian_local.eclipse_type == direct_local.eclipse_type,
        },
        "maximum": {
            "besselian_jd_tt": besselian_maximum_jd_tt,
            "direct_jd_tt": direct_maximum_jd_tt,
            "delta_direct_minus_besselian_seconds": (
                direct_maximum_jd_tt - besselian_maximum_jd_tt
            ) * 86400.0,
        },
        "contacts": contact_deltas,
        "central_duration": {
            "besselian_seconds": besselian_duration,
            "direct_seconds": direct_duration,
            "delta_direct_minus_besselian_seconds": duration_delta,
        },
        "interpretation": (
            "Diagnostic only: differing source ephemerides, lunar/solar radii, "
            "Earth-orientation assumptions, and geometric definitions may produce "
            "real differences. No pass/fail tolerance is applied."
        ),
    }

def _file_sha256(path: str | Path | None) -> str | None:
    if path is None:
        return None
    digest = hashlib.sha256()
    with Path(path).expanduser().open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _engine_metadata(engine: Any) -> dict[str, Any]:
    try:
        version = importlib.metadata.version("eclipsekit")
    except importlib.metadata.PackageNotFoundError:
        version = "source-tree"
    metadata: dict[str, Any] = {
        "eclipsekit_version": version,
        # Compatibility alias for historical validation reports.
        "pyeclipse_version": version,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }
    if hasattr(engine, "time_scale_mode"):
        metadata["time_scale_mode"] = str(engine.time_scale_mode)
    context = getattr(engine, "context", None)
    eop_provenance = getattr(context, "earth_orientation_provenance", None)
    if eop_provenance is not None:
        metadata["earth_orientation_provenance"] = dict(eop_provenance)
    config = getattr(engine, "config", None)
    if config is not None and hasattr(config, "to_dict"):
        metadata["configuration"] = config.to_dict()
        ephemeris = getattr(config, "ephemeris", None)
        if ephemeris is not None:
            metadata["kernel"] = str(getattr(ephemeris, "kernel", "unknown"))
    return metadata


def run_full_validation_suite(
    engine: Any,
    local_cases: Iterable[ReferenceLocalCase],
    global_cases: Iterable[ReferenceGlobalMaximumCase],
    *,
    path_cases: Iterable[PathReferenceCase] = (),
    path_samples: int = 301,
    besselian_reference: str | Path | None = None,
) -> dict[str, Any]:
    """Run all selected reference checks and build one auditable report."""
    report = run_validation_suite(engine, local_cases, global_cases)
    report["report_schema_version"] = 2
    report["generated_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report["environment"] = _engine_metadata(engine)
    report["global_path_cases"] = run_path_reference_cases(
        engine, path_cases, samples=path_samples
    )
    if besselian_reference is not None:
        try:
            report["besselian_reference"] = run_besselian_reference_validation(
                besselian_reference
            )
        except Exception as exc:
            report["besselian_reference"] = {
                "name": "Besselian reference regression",
                "status": "ERROR",
                "reason": f"{type(exc).__name__}: {exc}",
                "checks": {},
            }
    else:
        report["besselian_reference"] = None

    if besselian_reference is not None:
        try:
            report["direct_vs_besselian_diagnostic"] = run_direct_besselian_diagnostic(
                engine, besselian_reference
            )
        except Exception as exc:
            report["direct_vs_besselian_diagnostic"] = {
                "status": "DIAGNOSTIC_ERROR",
                "reason": f"{type(exc).__name__}: {exc}",
            }
    else:
        report["direct_vs_besselian_diagnostic"] = None

    besselian = report.get("besselian_reference")
    not_run_groups = []
    if not report.get("local_cases"):
        not_run_groups.append("local")
    if not report.get("global_maximum_cases"):
        not_run_groups.append("global_maximum")
    if not report.get("global_path_cases"):
        not_run_groups.append("global_path")
    if besselian is None:
        not_run_groups.append("besselian")
    case_statuses = [
        item["status"]
        for group in (
            report.get("local_cases", []),
            report.get("global_maximum_cases", []),
            report.get("global_path_cases", []),
        )
        for item in group
    ]
    if besselian is not None:
        case_statuses.append(besselian["status"])
    errors = case_statuses.count("ERROR")
    failures = case_statuses.count("FAIL")
    passes = case_statuses.count("PASS")
    report["summary"] = {
        "total_cases": len(case_statuses),
        "passed": passes,
        "failed": failures,
        "errors": errors,
        "not_run_groups": not_run_groups,
        "by_group": {
            "local": len(report.get("local_cases", [])),
            "global_maximum": len(report.get("global_maximum_cases", [])),
            "global_path": len(report.get("global_path_cases", [])),
            "besselian": 1 if besselian is not None else 0,
        },
    }
    report["status"] = (
        "ERROR" if errors or not case_statuses else ("FAIL" if failures else "PASS")
    )
    if not case_statuses:
        report["summary"]["reason"] = "No acceptance cases were selected; no scientific validation was performed."
    report["interpretation"] = (
        "PASS applies only to the configured fixtures, source resolutions, tolerances, "
        "ephemeris and Earth-orientation assumptions. It is not a universal accuracy claim."
    )
    return report


def render_full_validation_markdown(report: Mapping[str, Any]) -> str:
    """Render the full suite as a concise, auditable Markdown report."""
    summary = report.get("summary", {})
    lines = [
        "# EclipseKit Phase 6 scientific validation report",
        "",
        f"**Overall status:** {report.get('status', 'UNKNOWN')}",
        f"**Generated (UTC):** {report.get('generated_utc', 'not recorded')}",
        "",
        "## Run metadata",
        "",
    ]
    environment = report.get("environment", {})
    if environment:
        for key in ("eclipsekit_version", "pyeclipse_version", "python_version", "platform", "kernel", "time_scale_mode"):
            if key in environment:
                lines.append(f"- **{key}:** {environment[key]}")
    provenance = environment.get("earth_orientation_provenance")
    if isinstance(provenance, Mapping):
        lines.extend([
            f"- **EOP source:** {provenance.get('source', 'not recorded')}",
            f"- **EOP reproducibility:** {provenance.get('reproducibility_level', 'not recorded')}",
            f"- **Skyfield version:** {provenance.get('skyfield_version') or 'not recorded'}",
        ])
        if provenance.get("sha256"):
            lines.append(f"- **EOP SHA-256:** `{provenance['sha256']}`")
    inputs = report.get("inputs", {})
    if inputs:
        lines.extend(["", "## Input fixtures and options", ""])
        for key, value in inputs.items():
            lines.append(f"- **{key}:** {value if value is not None else 'not selected'}")
    lines.extend([
        "",
        "## Summary",
        "",
        f"- Total acceptance cases: {summary.get('total_cases', 0)}",
        f"- Passed: {summary.get('passed', 0)}",
        f"- Failed: {summary.get('failed', 0)}",
        f"- Errors: {summary.get('errors', 0)}",
        f"- Groups not run: {', '.join(summary.get('not_run_groups', [])) or 'none'}",
    ])
    if summary.get("reason"):
        lines.append(f"- **Note:** {summary['reason']}")
    lines.extend([
        "",
        "## Local circumstances and geocentric maximum",
        "",
        "| Case | Status | Failed checks | Source |",
        "|---|---|---|---|",
    ])
    for group in (report.get("local_cases", []), report.get("global_maximum_cases", [])):
        for case in group:
            checks = case.get("checks", [])
            if not checks and case.get("check") is not None:
                checks = [case["check"]]
            failed = [item.get("label", "check") for item in checks if not item.get("passed", False)]
            if case.get("type_check") is not None and not case["type_check"].get("passed", False):
                failed.append("eclipse type")
            if case.get("maximum_check") is not None and not case["maximum_check"].get("passed", False):
                failed.append("maximum")
            lines.append(
                f"| {case.get('name', case.get('case_id', 'unknown'))} | "
                f"{case.get('status', 'UNKNOWN')} | {', '.join(failed) or '—'} | "
                f"{case.get('source_url', '')} |"
            )
    lines.extend([
        "",
        "## Global shadow paths",
        "",
        "| Event | Status | Samples | Mean error (km) | RMS error (km) | Max error (km) | Limit (km) |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    for case in report.get("global_path_cases", []):
        lines.append(
            f"| {case.get('name', case.get('case_id', 'unknown'))} | {case.get('status', 'UNKNOWN')} | "
            f"{case.get('successful_comparisons', 0)}/{case.get('reference_count', 0)} | "
            f"{_fmt(case.get('mean_error_km'))} | {_fmt(case.get('rms_error_km'))} | "
            f"{_fmt(case.get('max_error_km'))} | {_fmt(case.get('tolerance_km'))} |"
        )
    lines.extend(["", "## Besselian reference regression", ""])
    besselian = report.get("besselian_reference")
    if besselian is None:
        lines.append("Not run.")
    else:
        lines.append(f"**Status:** {besselian.get('status', 'UNKNOWN')}")
        lines.append("")
        lines.append("| Check | Status | Result |")
        lines.append("|---|---|---|")
        for name, check in besselian.get("checks", {}).items():
            passed = "PASS" if check.get("passed") else "FAIL"
            value = check.get("delta_seconds", check.get("position_error_km", check.get("computed")))
            units = "s" if "delta_seconds" in check else ("km" if "position_error_km" in check else "")
            lines.append(f"| {name} | {passed} | {_fmt(value)} {units} |")
        if besselian.get("reason"):
            lines.append(f"\nError: {besselian['reason']}")
    diagnostic = report.get("direct_vs_besselian_diagnostic")
    lines.extend(["", "## Direct engine vs Besselian diagnostic", ""])
    if diagnostic is None:
        lines.append("Not run.")
    else:
        lines.append(f"**Status:** {diagnostic.get('status', 'UNKNOWN')}")
        if diagnostic.get("reason"):
            lines.append(diagnostic["reason"])
        if diagnostic.get("maximum"):
            lines.append(
                f"- Maximum difference (direct − Besselian): "
                f"{_fmt(diagnostic['maximum'].get('delta_direct_minus_besselian_seconds'))} s"
            )
        for name, item in diagnostic.get("contacts", {}).items():
            delta = item.get("delta_direct_minus_besselian_seconds")
            lines.append(f"- {name}: {_fmt(delta)} s ({item.get('status', 'UNKNOWN')})")
        duration = diagnostic.get("central_duration", {})
        if duration:
            lines.append(
                f"- Central duration difference: "
                f"{_fmt(duration.get('delta_direct_minus_besselian_seconds'))} s"
            )
        if diagnostic.get("interpretation"):
            lines.append(diagnostic["interpretation"])
    lines.extend([
        "",
        "> A passing suite is limited to the included fixtures and their stated "
        "precision, coordinates, ephemerides, ΔT/Earth-orientation conventions, "
        "and tolerances. Path-table subsets do not validate path boundaries or "
        "width. No lunar-limb model is scientifically certified unless separately "
        "benchmarked against an independent, documented profile dataset.",
        "",
    ])
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def main(argv: list[str] | None = None) -> int:
    """Run the complete Phase 6 suite and write JSON + Markdown artifacts."""
    parser = argparse.ArgumentParser(
        description="Run EclipseKit scientific reference, path and Besselian validation"
    )
    parser.add_argument("--references", default="data/validation/reference_cases.json")
    parser.add_argument(
        "--path-manifest", default="data/validation/path_reference_manifest.json",
        help="Manifest for NASA central-line path subsets",
    )
    parser.add_argument(
        "--besselian-reference", default="data/validation/besselian_1999_reference.json",
        help="NASA 1999 Besselian regression descriptor",
    )
    parser.add_argument("--kernel", default="de440s", help="JPL BSP kernel name or local path")
    parser.add_argument("--cache-dir", default=None, help="Explicit Skyfield ephemeris/EOP cache directory")
    parser.add_argument("--time-scale-mode", choices=("builtin", "iers", "fixed_delta_t"), default="builtin")
    parser.add_argument("--delta-t-seconds", type=float, default=None)
    parser.add_argument("--path-samples", type=int, default=301)
    parser.add_argument("--skip-paths", action="store_true")
    parser.add_argument("--skip-besselian", action="store_true")
    parser.add_argument("--json-out", default="reports/phase6-validation.json")
    parser.add_argument("--markdown-out", default="reports/phase6-validation.md")
    args = parser.parse_args(argv)

    if args.path_samples < 3:
        parser.error("--path-samples must be >= 3")
    if args.time_scale_mode == "fixed_delta_t" and args.delta_t_seconds is None:
        parser.error("--delta-t-seconds is required with --time-scale-mode fixed_delta_t")
    if args.time_scale_mode != "fixed_delta_t" and args.delta_t_seconds is not None:
        parser.error("--delta-t-seconds can only be used with fixed_delta_t mode")

    try:
        local_cases, global_cases = load_reference_cases(args.references)
        path_cases = [] if args.skip_paths else load_path_reference_cases(args.path_manifest)
        besselian_reference = None if args.skip_besselian else args.besselian_reference
        from .earth_orientation import EarthOrientationConfig
        from .engine import EclipseEngine

        orientation = (
            EarthOrientationConfig.fixed(args.delta_t_seconds)
            if args.time_scale_mode == "fixed_delta_t"
            else EarthOrientationConfig(mode=args.time_scale_mode)
        )
        engine = EclipseEngine.from_jpl(
            args.kernel, earth_orientation=orientation, cache_dir=args.cache_dir
        )
        report = run_full_validation_suite(
            engine,
            local_cases,
            global_cases,
            path_cases=path_cases,
            path_samples=args.path_samples,
            besselian_reference=besselian_reference,
        )
        reference_asset_hashes: dict[str, str] = {}
        reference_root = Path(args.references).expanduser().resolve().parent
        reference_asset_hashes[Path(args.references).name] = _file_sha256(args.references) or ""
        if not args.skip_paths:
            path_manifest_path = Path(args.path_manifest).expanduser().resolve()
            reference_asset_hashes[path_manifest_path.relative_to(reference_root).as_posix()] = (
                _file_sha256(path_manifest_path) or ""
            )
            for path_case in path_cases:
                relative_path = path_case.reference_file.resolve().relative_to(reference_root).as_posix()
                reference_asset_hashes[relative_path] = _file_sha256(path_case.reference_file) or ""
        if besselian_reference is not None:
            besselian_path = Path(besselian_reference).expanduser().resolve()
            reference_asset_hashes[besselian_path.relative_to(reference_root).as_posix()] = (
                _file_sha256(besselian_path) or ""
            )
            descriptor = json.loads(besselian_path.read_text(encoding="utf-8"))
            elements_path = (besselian_path.parent / descriptor["elements_file"]).resolve()
            reference_asset_hashes[elements_path.relative_to(reference_root).as_posix()] = (
                _file_sha256(elements_path) or ""
            )
        report["inputs"] = {
            "reference_cases": str(Path(args.references).expanduser()),
            "reference_manifest_sha256": _file_sha256(args.references),
            "reference_asset_sha256": reference_asset_hashes,
            "path_manifest": (
                str(Path(args.path_manifest).expanduser()) if not args.skip_paths else None
            ),
            "path_manifest_sha256": _file_sha256(args.path_manifest) if not args.skip_paths else None,
            "besselian_reference": (
                str(Path(besselian_reference).expanduser()) if besselian_reference else None
            ),
            "besselian_reference_sha256": _file_sha256(besselian_reference),
            "path_samples": int(args.path_samples),
            "kernel_argument": str(args.kernel),
            "cache_dir": str(args.cache_dir) if args.cache_dir else None,
            "time_scale_mode": args.time_scale_mode,
            "delta_t_seconds": args.delta_t_seconds,
        }
    except Exception as exc:
        parser.exit(2, f"Could not run scientific validation: {type(exc).__name__}: {exc}\n")

    json_path = Path(args.json_out).expanduser()
    markdown_path = Path(args.markdown_out).expanduser()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown = render_full_validation_markdown(report)
    markdown_path.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"\nJSON report: {json_path.resolve()}")
    print(f"Markdown report: {markdown_path.resolve()}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
