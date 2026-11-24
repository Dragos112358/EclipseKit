"""Reproducible software-release and scientific-evidence gate for EclipseKit.

The command deliberately separates passing software checks from scientific
certification. A clean test suite is necessary but not sufficient for a 1.0.0
scientific release.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.parser import Parser
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence
import zipfile

from . import __version__
from .api import API_CONTRACT_VERSION, API_STATUS
from .reference_matrix import audit_reference_matrix
from .regression import run_scientific_regression_suite

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_TEST_SUMMARY_RE = re.compile(r"(?P<passed>\d+) passed(?:, (?P<failed>\d+) failed)?(?:, (?P<errors>\d+) error)?")
_EXCLUDED_PARTS = {
    ".git", ".venv", "venv", "data", "models", "reports", "results", "dist",
    "build", ".pytest_cache", ".ruff_cache", ".mypy_cache", "__pycache__", ".tox",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON report root must be an object: {source}")
    return payload


def source_tree_fingerprint(source_root: str | Path) -> dict[str, Any]:
    """Hash the distributable source, tests and docs while excluding local data.

    Local DEMs, kernels, reports, virtual environments and caches never enter
    this fingerprint or the release overlay.
    """
    root = Path(source_root).expanduser().resolve()
    if not (root / "pyproject.toml").is_file():
        raise FileNotFoundError(f"Not an EclipseKit source root: {root}")

    include_roots = ("src", "tests", "docs", "examples", "scripts", ".github")
    top_level = (
        "pyproject.toml", "README.md", "CHANGELOG.md", "LICENSE.md",
        "SECURITY.md", "CITATION.cff", "PHASE15_APPLY.md",
    )
    files: list[Path] = []
    for name in include_roots:
        directory = root / name
        if directory.is_dir():
            for path in directory.rglob("*"):
                if not path.is_file():
                    continue
                relative = path.relative_to(root)
                if any(part in _EXCLUDED_PARTS for part in relative.parts):
                    continue
                if path.suffix in {".pyc", ".pyo"}:
                    continue
                files.append(path)
    files.extend(root / name for name in top_level if (root / name).is_file())
    files = sorted(set(files), key=lambda item: item.relative_to(root).as_posix())

    digest = hashlib.sha256()
    entries: list[dict[str, Any]] = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        file_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\n")
        entries.append({"path": relative, "sha256": file_digest, "size_bytes": path.stat().st_size})
    return {
        "algorithm": "sha256",
        "digest": digest.hexdigest(),
        "file_count": len(entries),
        "files": entries,
        "excluded_local_data": sorted(_EXCLUDED_PARTS),
    }


def audit_api_manifest(manifest_path: str | Path) -> dict[str, Any]:
    """Compare the checked-in API manifest with the live curated API."""
    from . import api

    payload = _read_json(manifest_path)
    declared = payload.get("exports")
    errors: list[str] = []
    if payload.get("module") != "eclipsekit.api":
        errors.append("manifest module must be eclipsekit.api")
    if payload.get("api_contract_version") != API_CONTRACT_VERSION:
        errors.append("API contract version differs from manifest")
    if payload.get("status") != API_STATUS:
        errors.append("API status differs from manifest")
    if not isinstance(declared, list) or any(not isinstance(item, str) for item in declared):
        errors.append("manifest exports must be an array of strings")
        declared = []
    if payload.get("export_count") != len(declared):
        errors.append("manifest export_count does not match exports length")
    if declared != list(api.__all__):
        missing = sorted(set(api.__all__) - set(declared))
        extra = sorted(set(declared) - set(api.__all__))
        errors.append(f"export list mismatch (missing={missing}, extra={extra})")
    return {
        "name": "public_api_manifest",
        "status": "FAIL" if errors else "PASS",
        "required": True,
        "details": "; ".join(errors) if errors else "API v1 export manifest matches the installed source tree.",
        "api_contract_version": API_CONTRACT_VERSION,
        "api_status": API_STATUS,
        "export_count": len(api.__all__),
        "manifest_path": str(Path(manifest_path).expanduser()),
    }


def audit_unified_validation_report(path: str | Path | None) -> dict[str, Any]:
    """Check a previously generated Phase 8.4 report without inferring missing data."""
    if path is None:
        return {
            "name": "live_eclipse_path_corridor_eop_validation", "status": "NOT_RUN",
            "required": True, "details": "No Phase 8.4 unified-validation report was supplied.",
        }
    try:
        report = _read_json(path)
    except Exception as exc:
        return {
            "name": "live_eclipse_path_corridor_eop_validation", "status": "ERROR",
            "required": True, "details": f"Could not read unified report: {type(exc).__name__}: {exc}",
        }
    components = report.get("components")
    errors: list[str] = []
    if report.get("schema") != "eclipsekit.phase8_4.unified_validation.v1":
        errors.append("unexpected unified-validation schema")
    if report.get("status") != "PASS":
        errors.append(f"unified-validation status is {report.get('status')!r}, expected 'PASS'")
    if not isinstance(components, list) or not components:
        errors.append("unified report has no component records")
    elif any(not isinstance(item, dict) or item.get("status") != "PASS" for item in components):
        errors.append("one or more unified-validation components are not PASS")
    return {
        "name": "live_eclipse_path_corridor_eop_validation",
        "status": "PASS" if not errors else "FAIL",
        "required": True,
        "details": "; ".join(errors) if errors else "All Phase 8.4 components report PASS.",
        "component_count": len(components) if isinstance(components, list) else 0,
        "report_path": str(Path(path).expanduser()),
        "inputs": report.get("inputs", {}),
    }


def audit_reference_validation_report(
    path: str | Path | None, *, expected_case_ids: Sequence[str] | None = None,
    expected_input_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Require a passing live full-reference run for every manifest local/global/path case."""
    if path is None:
        return {
            "name": "live_published_reference_regressions", "status": "NOT_RUN",
            "required": True, "details": "No full eclipsekit-validate report was supplied.",
        }
    try:
        report = _read_json(path)
    except Exception as exc:
        return {
            "name": "live_published_reference_regressions", "status": "ERROR",
            "required": True,
            "details": f"Could not read full reference-validation report: {type(exc).__name__}: {exc}",
        }

    errors: list[str] = []
    if report.get("schema_version") != 1 or report.get("report_schema_version") != 2:
        errors.append("unexpected full reference-validation report schema")
    if report.get("status") != "PASS":
        errors.append(f"full reference-validation status is {report.get('status')!r}, expected 'PASS'")

    groups = {
        "local": report.get("local_cases"),
        "global_maximum": report.get("global_maximum_cases"),
        "global_path": report.get("global_path_cases"),
    }
    observed_ids: set[str] = set()
    group_counts: dict[str, int] = {}
    for group_name, records in groups.items():
        if not isinstance(records, list) or not records:
            errors.append(f"reference-validation report has no {group_name} records")
            group_counts[group_name] = 0
            continue
        group_counts[group_name] = len(records)
        for record in records:
            if not isinstance(record, dict):
                errors.append(f"{group_name} result contains a non-object record")
                continue
            case_id = record.get("case_id")
            if isinstance(case_id, str):
                observed_ids.add(case_id)
            if record.get("status") != "PASS":
                errors.append(f"{group_name} case {case_id!r} status is {record.get('status')!r}")

    expected_ids = set(expected_case_ids or ())
    missing_ids = sorted(expected_ids - observed_ids)
    unexpected_ids = sorted(observed_ids - expected_ids) if expected_ids else []
    if missing_ids:
        errors.append(f"full run is missing manifest cases: {missing_ids}")
    if unexpected_ids:
        errors.append(f"full run contains cases not present in the audited manifest: {unexpected_ids}")

    besselian = report.get("besselian_reference")
    if not isinstance(besselian, dict) or besselian.get("status") != "PASS":
        errors.append("published NASA Besselian regression is not PASS")

    hybrid = [
        item for item in (groups.get("global_maximum") or [])
        if isinstance(item, dict) and item.get("reference_eclipse_type") == "hybrid"
    ]
    if not hybrid:
        errors.append("full run does not contain the published hybrid global-maximum case")
    elif any(item.get("status") != "PASS" for item in hybrid):
        errors.append("published hybrid global-maximum comparison did not pass")

    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if summary.get("failed", 0) or summary.get("errors", 0):
        errors.append("full validation summary records failed or error cases")
    if summary.get("not_run_groups"):
        errors.append(f"full validation omitted groups: {summary.get('not_run_groups')}")

    inputs = report.get("inputs") if isinstance(report.get("inputs"), dict) else {}
    asset_hashes = inputs.get("reference_asset_sha256")
    if not isinstance(asset_hashes, dict):
        asset_hashes = {}
    for input_name, expected_hash in (expected_input_hashes or {}).items():
        actual_hash = asset_hashes.get(input_name)
        if actual_hash != expected_hash:
            errors.append(
                f"reference-validation input fingerprint {input_name!r} does not match the current manifest matrix"
            )

    environment = report.get("environment") if isinstance(report.get("environment"), dict) else {}
    if not environment.get("kernel"):
        errors.append("validation report does not record the ephemeris kernel")
    if not environment.get("time_scale_mode"):
        errors.append("validation report does not record the Earth-orientation/time-scale mode")

    return {
        "name": "live_published_reference_regressions",
        "status": "PASS" if not errors else "FAIL",
        "required": True,
        "details": "; ".join(errors) if errors else (
            "All manifest local, global-maximum and path cases passed, including the hybrid greatest-eclipse time and NASA Besselian regression."
        ),
        "report_path": str(Path(path).expanduser()),
        "group_counts": group_counts,
        "case_count": len(observed_ids),
        "expected_case_count": len(expected_ids),
        "kernel": environment.get("kernel"),
        "time_scale_mode": environment.get("time_scale_mode"),
        "hybrid_case_ids": [item.get("case_id") for item in hybrid],
    }


def audit_dem_control_point_report(
    path: str | Path | None, *, minimum_points: int = 10
) -> dict[str, Any]:
    """Require a passing, declared-independent lunar DEM control-point report."""
    if isinstance(minimum_points, bool) or not isinstance(minimum_points, int) or minimum_points < 1:
        raise ValueError("minimum_points must be an integer >= 1")
    if path is None:
        return {
            "name": "independent_lunar_dem_control_points", "status": "NOT_RUN",
            "required": True,
            "details": "No independently sourced lunar DEM control-point report was supplied.",
            "minimum_points": minimum_points,
        }
    try:
        report = _read_json(path)
    except Exception as exc:
        return {
            "name": "independent_lunar_dem_control_points", "status": "ERROR", "required": True,
            "details": f"Could not read control-point report: {type(exc).__name__}: {exc}",
        }

    errors: list[str] = []
    point_count = report.get("control_point_count")
    counts = report.get("counts")
    source_hash = report.get("control_source_sha256")
    if report.get("status") != "PASS":
        errors.append(f"control-point report status is {report.get('status')!r}, expected 'PASS'")
    if report.get("independent_of_test_dem") is not True:
        errors.append("control source is not declared independent of the test DEM")
    if isinstance(point_count, bool) or not isinstance(point_count, int) or point_count < minimum_points:
        errors.append(f"control_point_count must be >= {minimum_points}")
    if not isinstance(source_hash, str) or not _SHA256_RE.fullmatch(source_hash):
        errors.append("control_source_sha256 must be a 64-character SHA-256 fingerprint")
    if not isinstance(counts, dict):
        errors.append("counts object is missing")
    elif (
        counts.get("PASS") != point_count
        or counts.get("FAIL", 0) != 0
        or counts.get("OUT_OF_COVERAGE", 0) != 0
        or counts.get("ERROR", 0) != 0
    ):
        errors.append("point-level counts are incomplete or contain non-PASS rows")
    control_source = report.get("control_source")
    if not isinstance(control_source, dict) or not str(control_source.get("uri", "")).strip():
        errors.append("control source URI is missing")
    if not str(report.get("independence_statement", "")).strip():
        errors.append("independence statement is missing")
    return {
        "name": "independent_lunar_dem_control_points",
        "status": "PASS" if not errors else "FAIL",
        "required": True,
        "details": "; ".join(errors) if errors else (
            "Control-point report passes its declared tolerance and independence metadata. "
            "The curator's independence declaration is not independently verified by this audit."
        ),
        "dataset_id": report.get("dataset_id"),
        "independent_of_test_dem": report.get("independent_of_test_dem"),
        "control_point_count": point_count,
        "minimum_points": minimum_points,
        "control_source_sha256": source_hash,
        "metrics": report.get("metrics", {}),
        "report_path": str(Path(path).expanduser()),
    }


def audit_peer_review_record(
    path: str | Path | None, *, expected_source_digest: str
) -> dict[str, Any]:
    """Validate a reviewer-supplied record bound to the exact source fingerprint."""
    if path is None:
        return {
            "name": "independent_scientific_peer_review", "status": "NOT_RUN",
            "required": True,
            "details": "No independent scientific review record was supplied.",
            "expected_source_tree_sha256": expected_source_digest,
        }
    try:
        report = _read_json(path)
    except Exception as exc:
        return {
            "name": "independent_scientific_peer_review", "status": "ERROR", "required": True,
            "details": f"Could not read peer-review record: {type(exc).__name__}: {exc}",
        }

    errors: list[str] = []
    if report.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not str(report.get("reviewer", "")).strip():
        errors.append("reviewer must be identified")
    if report.get("reviewer_is_independent") is not True:
        errors.append("reviewer_is_independent must be true")
    if report.get("review_outcome") != "accepted":
        errors.append("review_outcome must be 'accepted'")
    if report.get("source_tree_sha256") != expected_source_digest:
        errors.append("reviewed source_tree_sha256 does not match this source tree")
    scope = report.get("scope")
    if not isinstance(scope, list) or not scope or any(not isinstance(item, str) or not item.strip() for item in scope):
        errors.append("scope must be a non-empty list of descriptive strings")
    review_date = report.get("review_date_utc")
    try:
        parsed = datetime.fromisoformat(str(review_date).replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            errors.append("review_date_utc must include an explicit UTC offset")
    except ValueError:
        errors.append("review_date_utc must be an ISO-8601 UTC timestamp")
    findings = report.get("findings", [])
    if not isinstance(findings, list):
        errors.append("findings must be a list")
    elif any(not isinstance(item, dict) or item.get("status") not in {"resolved", "accepted_risk"} for item in findings):
        errors.append("all review findings must be marked resolved or accepted_risk")
    return {
        "name": "independent_scientific_peer_review",
        "status": "PASS" if not errors else "FAIL",
        "required": True,
        "details": "; ".join(errors) if errors else (
            "Reviewer record is complete and bound to the current source fingerprint. "
            "The reviewer's identity and independence remain external declarations."
        ),
        "reviewer": report.get("reviewer"),
        "review_date_utc": review_date,
        "scope": scope,
        "source_tree_sha256": report.get("source_tree_sha256"),
        "finding_count": len(findings) if isinstance(findings, list) else None,
        "record_path": str(Path(path).expanduser()),
    }


def _run_command(
    name: str,
    command: Sequence[str],
    *,
    cwd: Path,
    log_path: Path,
    timeout_seconds: int = 1800,
    separate_stderr: bool = False,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE if separate_stderr else subprocess.STDOUT,
            check=False,
            timeout=timeout_seconds,
        )
        output = completed.stdout or ""
        stderr_output = completed.stderr or "" if separate_stderr else ""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(output, encoding="utf-8")
        result: dict[str, Any] = {
            "name": name,
            "status": "PASS" if completed.returncode == 0 else "FAIL",
            "required": True,
            "exit_code": completed.returncode,
            "command": list(command),
            "log": str(log_path),
        }
        if separate_stderr:
            stderr_log_path = log_path.with_name(f"{log_path.stem}.stderr{log_path.suffix}")
            stderr_log_path.write_text(stderr_output, encoding="utf-8")
            result["stderr_log"] = str(stderr_log_path)
        if name == "pytest":
            matches = list(_TEST_SUMMARY_RE.finditer(output))
            if matches:
                result["test_summary"] = matches[-1].groupdict()
        if completed.returncode != 0:
            combined_output = output + ("\n" + stderr_output if stderr_output else "")
            result["details"] = combined_output[-4000:]
        return result
    except FileNotFoundError as exc:
        return {
            "name": name, "status": "NOT_RUN", "required": True,
            "details": f"Required command is unavailable: {exc}", "command": list(command),
        }
    except subprocess.TimeoutExpired as exc:
        tail = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(tail + "\nTIMEOUT\n", encoding="utf-8")
        return {
            "name": name, "status": "ERROR", "required": True,
            "details": f"Command timed out after {timeout_seconds} seconds", "command": list(command),
            "log": str(log_path),
        }


def audit_wheel(path: str | Path, *, expected_version: str) -> dict[str, Any]:
    """Check wheel metadata, PEP 561 marker and absence of local data payloads."""
    wheel_path = Path(path).expanduser().resolve()
    try:
        with zipfile.ZipFile(wheel_path) as archive:
            names = archive.namelist()
            if archive.testzip() is not None:
                raise ValueError("wheel ZIP CRC verification failed")
            metadata_paths = [name for name in names if name.endswith(".dist-info/METADATA")]
            if len(metadata_paths) != 1:
                raise ValueError("wheel must contain exactly one dist-info/METADATA")
            metadata_text = archive.read(metadata_paths[0]).decode("utf-8")
            metadata = Parser().parsestr(metadata_text)
            if metadata.get("Name", "").casefold() != "eclipsekit":
                raise ValueError("wheel distribution name is not eclipsekit")
            if metadata.get("Version") != expected_version:
                raise ValueError(
                    f"wheel version {metadata.get('Version')!r} differs from source {expected_version!r}"
                )
            if "eclipsekit/py.typed" not in names:
                raise ValueError("wheel is missing eclipsekit/py.typed (PEP 561)")
            if not any(name.startswith("eclipsekit/") and name.endswith(".py") for name in names):
                raise ValueError("wheel contains no eclipsekit Python modules")
            forbidden_prefixes = ("data/", "models/", "reports/", ".venv/", "venv/")
            leaked = [name for name in names if name.startswith(forbidden_prefixes)]
            if leaked:
                raise ValueError(f"wheel contains local-only paths: {leaked[:10]}")
        return {
            "name": "wheel_contents", "status": "PASS", "required": True,
            "wheel": str(wheel_path), "version": expected_version, "file_count": len(names),
            "sha256": hashlib.sha256(wheel_path.read_bytes()).hexdigest(),
            "details": "Wheel metadata, importable modules, PEP 561 marker and local-data exclusions verified.",
        }
    except Exception as exc:
        return {
            "name": "wheel_contents", "status": "FAIL", "required": True,
            "wheel": str(wheel_path), "details": f"{type(exc).__name__}: {exc}",
        }


def run_software_checks(
    source_root: str | Path,
    output_dir: str | Path,
    *,
    run_security_audit: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Run local lint, compile, test, dependency and wheel checks."""
    root = Path(source_root).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    logs = output / "logs"
    basetemp = output / ".pytest_tmp"
    wheel_dir = output / "wheel"
    wheel_dir.mkdir(parents=True, exist_ok=True)
    for previous_wheel in wheel_dir.glob("*.whl"):
        previous_wheel.unlink()

    commands = [
        ("ruff", [sys.executable, "-m", "ruff", "check", "src", "tests", "examples", "scripts"]),
        ("compileall", [sys.executable, "-m", "compileall", "-q", "src", "tests", "examples", "scripts"]),
        ("pytest", [sys.executable, "-m", "pytest", "-q", f"--basetemp={basetemp}"]),
        ("pip_check", [sys.executable, "-m", "pip", "check"]),
        ("wheel_build", [sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(wheel_dir)]),
    ]
    gates = [
        _run_command(name, command, cwd=root, log_path=logs / f"{name}.log")
        for name, command in commands
    ]

    wheel_gate: dict[str, Any] | None = None
    if next((gate for gate in gates if gate["name"] == "wheel_build"), {}).get("status") == "PASS":
        wheels = sorted(wheel_dir.glob("*.whl"))
        if len(wheels) == 1:
            wheel_gate = audit_wheel(wheels[0], expected_version=__version__)
        else:
            wheel_gate = {
                "name": "wheel_contents", "status": "FAIL", "required": True,
                "details": f"Expected exactly one wheel, found {len(wheels)}.",
            }
    else:
        wheel_gate = {
            "name": "wheel_contents", "status": "NOT_RUN", "required": True,
            "details": "Wheel contents cannot be checked because wheel build did not pass.",
        }
    gates.append(wheel_gate)

    if run_security_audit:
        gates.append(_run_command(
            "pip_audit", [sys.executable, "-m", "pip_audit", "--format", "json", "--skip-editable"],
            cwd=root, log_path=logs / "pip_audit.json", timeout_seconds=600, separate_stderr=True,
        ))
    else:
        gates.append({
            "name": "pip_audit", "status": "NOT_RUN", "required": True,
            "details": "Dependency vulnerability audit was not requested; install the security extra and use --run-pip-audit.",
        })
    return gates, wheel_gate


def _add_gate(gates: list[dict[str, Any]], gate: dict[str, Any]) -> None:
    gates.append(gate)


def run_certification_audit(
    *,
    source_root: str | Path,
    validation_dir: str | Path,
    output_dir: str | Path,
    api_manifest: str | Path | None = None,
    unified_report: str | Path | None = None,
    reference_report: str | Path | None = None,
    dem_image: str | Path | None = None,
    dem_label: str | Path | None = None,
    expected_coordinate_system: str | None = None,
    control_point_report: str | Path | None = None,
    peer_review_record: str | Path | None = None,
    minimum_control_points: int = 10,
    run_software: bool = True,
    run_security_audit: bool = False,
    release_profile: str = "scientific",
) -> dict[str, Any]:
    """Build a software-Alpha or scientific-1.0 release evidence report.

    Missing independent evidence is reported as NOT_RUN and prevents a
    scientific certification decision. With ``release_profile='alpha'``,
    API maturity, independent lunar control points, external peer review and
    the 1.0.0 version gate remain visible but do not block an Alpha software
    release. They are never silently treated as scientific passes.
    """
    if release_profile not in {"scientific", "alpha"}:
        raise ValueError("release_profile must be 'scientific' or 'alpha'")
    root = Path(source_root).expanduser().resolve()

    def resolve_project_path(value: str | Path | None) -> Path | None:
        if value is None:
            return None
        candidate = Path(value).expanduser()
        return candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()

    output = resolve_project_path(output_dir)
    validation_path = resolve_project_path(validation_dir)
    assert output is not None and validation_path is not None
    manifest_path = resolve_project_path(api_manifest) or (root / "docs" / "API_MANIFEST_V1.json")
    unified_path = resolve_project_path(unified_report)
    reference_report_path = resolve_project_path(reference_report)
    dem_image_path = resolve_project_path(dem_image)
    dem_label_path = resolve_project_path(dem_label)
    control_report_path = resolve_project_path(control_point_report)
    peer_review_path = resolve_project_path(peer_review_record)

    output.mkdir(parents=True, exist_ok=True)
    gates: list[dict[str, Any]] = []

    fingerprint = source_tree_fingerprint(root)
    _add_gate(gates, {
        "name": "source_tree_fingerprint", "status": "PASS", "required": True,
        "details": "Source, tests and documentation fingerprinted; local DEMs, models, kernels and reports excluded.",
        "sha256": fingerprint["digest"], "file_count": fingerprint["file_count"],
    })

    if run_software:
        software_gates, _ = run_software_checks(root, output / "software", run_security_audit=run_security_audit)
        gates.extend(software_gates)
    else:
        for name in ("ruff", "compileall", "pytest", "pip_check", "wheel_build", "wheel_contents", "pip_audit"):
            gates.append({
                "name": name, "status": "NOT_RUN", "required": True,
                "details": "Software checks were explicitly skipped.",
            })

    try:
        _add_gate(gates, audit_api_manifest(manifest_path))
        _add_gate(gates, {
            "name": "public_api_maturity",
            "status": "PASS" if API_STATUS == "stable" else "PARTIAL",
            "required": True,
            "details": "Public API contract v1 is marked stable." if API_STATUS == "stable" else (
                f"Public API status is {API_STATUS!r}; stable contract is required for 1.0.0."
            ),
        })
    except Exception as exc:
        _add_gate(gates, {
            "name": "public_api_manifest", "status": "ERROR", "required": True,
            "details": f"{type(exc).__name__}: {exc}",
        })

    expected_reference_case_ids: list[str] = []
    expected_reference_hashes: dict[str, str] = {}
    try:
        matrix = audit_reference_matrix(validation_path)
        expected_reference_case_ids = [
            str(item["case_id"]) for item in matrix.get("cases", [])
            if item.get("group") in {"local_circumstances", "global_maximum", "global_path"}
        ]
        expected_reference_hashes = {
            str(asset["path"]): str(asset["sha256"])
            for asset in matrix.get("assets", [])
            if asset.get("path") in {
                "reference_cases.json", "path_reference_manifest.json", "besselian_1999_reference.json"
            } or any(
                str(role).startswith("global_path_reference:") or role == "besselian_elements"
                for role in asset.get("roles", [])
            )
        }
        _add_gate(gates, {
            "name": "reference_matrix_and_fingerprints", "status": matrix.get("status", "ERROR"),
            "required": True,
            "details": "Reference schemas, source identifiers and file fingerprints audited.",
            "summary": matrix.get("summary"),
            "asset_count": len(matrix.get("assets", [])),
        })
        observed_types = set(matrix.get("summary", {}).get("observed_eclipse_types", []))
        required_types = {"total", "annular", "partial", "hybrid"}
        missing_types = sorted(required_types - observed_types)
        _add_gate(gates, {
            "name": "reference_eclipse_type_coverage", "status": "PASS" if not missing_types else "PARTIAL",
            "required": True,
            "details": (
                "Published reference fixtures cover total, annular, partial and hybrid event classes. "
                "The hybrid fixture compares the geocentric greatest-eclipse epoch only; it does not "
                "validate all local contacts or the full hybrid path."
            ) if not missing_types else (
                f"Reference matrix lacks required eclipse-type cases: {', '.join(missing_types)}."
            ),
            "observed_types": sorted(observed_types),
            "required_types": sorted(required_types),
            "missing_types": missing_types,
        })
    except Exception as exc:
        _add_gate(gates, {
            "name": "reference_matrix_and_fingerprints", "status": "ERROR", "required": True,
            "details": f"{type(exc).__name__}: {exc}",
        })

    _add_gate(gates, audit_reference_validation_report(
        reference_report_path, expected_case_ids=expected_reference_case_ids,
        expected_input_hashes=expected_reference_hashes,
    ))

    reference_file = validation_path / "besselian_1999_reference.json"
    try:
        regression = run_scientific_regression_suite(
            reference_file=reference_file,
            dem_image=dem_image_path,
            dem_label=dem_label_path,
            expected_coordinate_system=expected_coordinate_system,
        )
        deterministic = [
            item for item in regression.get("checks", [])
            if item.get("name") not in {
                "real_lunar_dem_structural_validation",
                "live_de440s_path_and_shadow_corridor_regressions",
                "nasa_1999_besselian_reference",
            }
        ]
        numerical_ok = bool(deterministic) and all(item.get("status") == "PASS" for item in deterministic)
        _add_gate(gates, {
            "name": "deterministic_numerical_regression", "status": "PASS" if numerical_ok else "FAIL",
            "required": True,
            "details": f"{sum(item.get('status') == 'PASS' for item in deterministic)} deterministic numerical anchors checked.",
            "checks": deterministic,
        })
        nasa = next((item for item in regression.get("checks", []) if item.get("name") == "nasa_1999_besselian_reference"), None)
        _add_gate(gates, {
            "name": "nasa_1999_besselian_reference",
            "status": nasa.get("status", "NOT_RUN") if nasa else "NOT_RUN",
            "required": True,
            "details": nasa.get("details", "NASA 1999 Besselian reference was not evaluated.") if nasa else "NASA 1999 reference missing.",
            "source_url": nasa.get("source_url") if nasa else None,
        })
        dem_check = next((item for item in regression.get("checks", []) if item.get("name") == "real_lunar_dem_structural_validation"), None)
        _add_gate(gates, {
            "name": "real_lunar_dem_structural_validation",
            "status": dem_check.get("status", "NOT_RUN") if dem_check else "NOT_RUN",
            "required": True,
            "details": dem_check.get("details", "Real DEM structural validation not run.") if dem_check else "Real DEM structural validation not run.",
            "passed_samples": dem_check.get("passed_samples") if dem_check else None,
            "failed_samples": dem_check.get("failed_samples") if dem_check else None,
            "product_info": dem_check.get("product_info") if dem_check else None,
        })
    except Exception as exc:
        _add_gate(gates, {
            "name": "deterministic_numerical_regression", "status": "ERROR", "required": True,
            "details": f"{type(exc).__name__}: {exc}",
        })

    _add_gate(gates, audit_unified_validation_report(unified_path))
    _add_gate(gates, audit_dem_control_point_report(control_report_path, minimum_points=minimum_control_points))
    _add_gate(gates, audit_peer_review_record(peer_review_path, expected_source_digest=fingerprint["digest"]))
    _add_gate(gates, {
        "name": "distribution_version_1_0_0",
        "status": "PASS" if __version__ == "1.0.0" else "NOT_RUN",
        "required": True,
        "details": "Distribution version is 1.0.0." if __version__ == "1.0.0" else (
            f"Current distribution is {__version__}; do not bump to 1.0.0 until all other required evidence gates pass."
        ),
    })

    if run_security_audit:
        security_gate = next((item for item in gates if item.get("name") == "pip_audit"), None)
        if security_gate and security_gate.get("status") == "PASS":
            try:
                audit_payload = json.loads((output / "software" / "logs" / "pip_audit.json").read_text(encoding="utf-8"))
                vulnerabilities = audit_payload if isinstance(audit_payload, list) else audit_payload.get("dependencies", [])
                if any(item.get("vulns") for item in vulnerabilities if isinstance(item, dict)):
                    security_gate["status"] = "FAIL"
                    security_gate["details"] = "pip-audit reported one or more known vulnerabilities."
                else:
                    security_gate["details"] = "pip-audit completed with no reported vulnerabilities."
            except Exception as exc:
                security_gate["status"] = "ERROR"
                security_gate["details"] = f"Could not interpret pip-audit JSON: {type(exc).__name__}: {exc}"

    # Preserve the complete scientific gate state for every profile. The
    # Alpha profile relaxes only four 1.0-scientific-release requirements;
    # it does not turn any of them into PASS and does not skip core tests,
    # published reference regressions, DEM structural checks or Phase 8.4.
    alpha_non_blocking = {
        "public_api_maturity",
        "independent_lunar_dem_control_points",
        "independent_scientific_peer_review",
        "distribution_version_1_0_0",
    }
    for item in gates:
        originally_required = item.get("required") is True
        item["required_for_scientific_certification"] = originally_required
        if release_profile == "alpha" and item.get("name") in alpha_non_blocking:
            item["required"] = False
            item["required_for_alpha_release"] = False
        else:
            item["required_for_alpha_release"] = originally_required

    scientific_required = [
        item for item in gates if item.get("required_for_scientific_certification") is True
    ]
    scientific_failed = [
        item for item in scientific_required if item.get("status") in {"FAIL", "ERROR"}
    ]
    scientific_incomplete = [
        item for item in scientific_required if item.get("status") not in {"PASS", "FAIL", "ERROR"}
    ]
    scientific_certified = (
        not scientific_failed and not scientific_incomplete and __version__ == "1.0.0"
    )

    required = [item for item in gates if item.get("required") is True]
    failed = [item for item in required if item.get("status") in {"FAIL", "ERROR"}]
    incomplete = [item for item in required if item.get("status") not in {"PASS", "FAIL", "ERROR"}]
    software_names = {"ruff", "compileall", "pytest", "pip_check", "wheel_build", "wheel_contents", "pip_audit"}
    software = [item for item in required if item.get("name") in software_names]
    software_ready = bool(software) and all(item.get("status") == "PASS" for item in software)

    alpha_release_ready = release_profile == "alpha" and not failed and not incomplete and software_ready
    if release_profile == "alpha":
        decision = (
            "ALPHA_RELEASE_READY" if alpha_release_ready
            else ("REJECTED" if failed else "NOT_READY")
        )
    else:
        decision = (
            "CERTIFIED_WITHIN_DECLARED_SCOPE" if scientific_certified
            else ("REJECTED" if scientific_failed else "NOT_CERTIFIED")
        )

    scientific_status = (
        "CERTIFIED_WITHIN_DECLARED_SCOPE" if scientific_certified
        else ("REJECTED" if scientific_failed else "NOT_CERTIFIED")
    )
    report = {
        "schema": "eclipsekit.phase15.certification.v1",
        "generated_utc": _utc_now(),
        "status": decision,
        "release_profile": release_profile,
        "alpha_release_readiness": "PASS" if alpha_release_ready else (
            "INCOMPLETE" if release_profile == "alpha" else "NOT_REQUESTED"
        ),
        "scientific_certification_status": scientific_status,
        "software_release_readiness": "PASS" if software_ready else "INCOMPLETE",
        "package_version": __version__,
        "target_release_version": "1.0.0",
        "api_contract_version": API_CONTRACT_VERSION,
        "api_status": API_STATUS,
        "source_tree_sha256": fingerprint["digest"],
        "source_file_count": fingerprint["file_count"],
        "summary": {
            "required_gate_count": len(required),
            "passed": sum(item.get("status") == "PASS" for item in required),
            "failed_or_error": len(failed),
            "not_run_or_partial": len(incomplete),
            "failed_gates": [item.get("name") for item in failed],
            "incomplete_gates": [item.get("name") for item in incomplete],
        },
        "scientific_certification_summary": {
            "required_gate_count": len(scientific_required),
            "passed": sum(item.get("status") == "PASS" for item in scientific_required),
            "failed_or_error": len(scientific_failed),
            "not_run_or_partial": len(scientific_incomplete),
            "incomplete_gates": [item.get("name") for item in scientific_incomplete],
            "failed_gates": [item.get("name") for item in scientific_failed],
        },
        "gates": gates,
        "interpretation": (
            "ALPHA_RELEASE_READY means the configured software, packaging, published-reference, real-DEM structural and unified-validation gates passed. "
            "It is a software Alpha release decision only, not scientific certification. API maturity, independent lunar DEM control points, "
            "external peer review and the 1.0.0 version gate remain visible as non-blocking scientific-release requirements; their PARTIAL/NOT_RUN "
            "states are not treated as passes. Do not describe this artifact as scientifically certified or as version 1.0.0."
        ) if release_profile == "alpha" else (
            "CERTIFIED_WITHIN_DECLARED_SCOPE is only emitted when every required software, scientific, "
            "independent-control, peer-review and 1.0.0 version gate passes. It is not universal certification "
            "for every eclipse, observer, DEM product, or epoch."
        ),
        "limitations": [
            "Published NASA and other reference cases cover only their documented events, epochs and tolerances.",
            "The independence of a lunar control-point source is a curator declaration; this tool checks its metadata and report but cannot prove provenance independently.",
            "A peer-review record is supplied by the reviewer or project owner; reviewer identity and independence are not cryptographically verified.",
            "A PDS3 DEM structural/sample PASS does not establish global vertical or horizontal accuracy.",
            "The hybrid-eclipse reference checks the published geocentric greatest-eclipse epoch only; it does not validate hybrid-path transitions or local contacts.",
            "A passing software suite and wheel audit do not establish scientific correctness outside measured reference cases.",
            "The distribution remains pre-1.0.0 until the required evidence gates pass and a 1.0.0 artifact is built.",
        ],
    }
    return report


def render_certification_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    scientific_summary = report.get("scientific_certification_summary", summary)
    lines = [
        "# EclipseKit Phase 15 — scientific certification and 1.0 release gate",
        "",
        f"**Decision:** `{report['status']}`",
        f"**Release profile:** `{report.get('release_profile', 'scientific')}`",
        f"**Software readiness:** `{report['software_release_readiness']}`",
        f"**Scientific certification:** `{report.get('scientific_certification_status', report['status'])}`",
        f"**Current package:** `{report['package_version']}`",
        f"**Target release:** `{report['target_release_version']}`",
        f"**Source SHA-256:** `{report['source_tree_sha256']}`",
        f"**Generated UTC:** `{report['generated_utc']}`",
        "",
        f"**Required gates:** {summary['passed']} PASS / {summary['failed_or_error']} FAIL or ERROR / {summary['not_run_or_partial']} NOT RUN or PARTIAL",
        "",
        "## Gate results",
        "",
        "| Gate | Status | Required | Details |",
        "|---|---|---:|---|",
    ]
    for gate in report["gates"]:
        details = str(gate.get("details", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {gate.get('name')} | {gate.get('status')} | {gate.get('required', False)} | {details} |")
    lines.extend(["", "## Interpretation", "", report["interpretation"], "", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.extend(["", "## Remaining required gates", ""])
    remaining = summary.get("incomplete_gates", []) + summary.get("failed_gates", [])
    if remaining:
        lines.extend(f"- `{name}`" for name in remaining)
    else:
        lines.append("- None")
    lines.extend(["", "## Scientific certification gates", ""])
    lines.append(
        f"{scientific_summary['passed']} PASS / {scientific_summary['failed_or_error']} FAIL or ERROR / "
        f"{scientific_summary['not_run_or_partial']} NOT RUN or PARTIAL."
    )
    if report.get("release_profile") == "alpha":
        lines.extend([
            "",
            "The following scientific 1.0.0 requirements are non-blocking for this Alpha software release, "
            "but remain mandatory for scientific certification:",
        ])
        optional_pending = [
            gate for gate in report["gates"]
            if gate.get("required_for_scientific_certification") is True
            and gate.get("required_for_alpha_release") is False
            and gate.get("status") != "PASS"
        ]
        if optional_pending:
            lines.extend(f"- `{gate.get('name')}`: {gate.get('status')} — {gate.get('details', '')}" for gate in optional_pending)
        else:
            lines.append("- None")
    return "\n".join(lines) + "\n"


def write_certification_report(report: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    if report.get("schema") != "eclipsekit.phase15.certification.v1":
        raise ValueError("unsupported certification report schema")
    directory = Path(output_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "phase15-certification.json"
    markdown_path = directory / "phase15-certification.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_certification_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run EclipseKit's Alpha software-release or scientific 1.0 evidence audit."
    )
    parser.add_argument("--source-root", default=".")
    parser.add_argument("--validation-dir", default="data/validation")
    parser.add_argument("--output-dir", default="reports/phase15")
    parser.add_argument("--api-manifest")
    parser.add_argument("--unified-report")
    parser.add_argument("--reference-report", help="passing full eclipsekit-validate JSON report")
    parser.add_argument("--dem-image")
    parser.add_argument("--dem-label")
    parser.add_argument("--expected-coordinate-system")
    parser.add_argument("--control-point-report")
    parser.add_argument("--peer-review-record")
    parser.add_argument("--min-control-points", type=int, default=10)
    parser.add_argument("--skip-software-checks", action="store_true")
    parser.add_argument("--run-pip-audit", action="store_true")
    parser.add_argument(
        "--release-profile", choices=("scientific", "alpha"), default="scientific",
        help=("'scientific' enforces all 1.0.0 evidence gates; 'alpha' makes only API maturity, "
              "independent lunar controls, external peer review and 1.0.0 version non-blocking."),
    )
    args = parser.parse_args(argv)

    if (args.dem_image is None) != (args.dem_label is None):
        parser.error("--dem-image and --dem-label must be supplied together")
    if args.min_control_points < 1:
        parser.error("--min-control-points must be >= 1")

    report = run_certification_audit(
        source_root=args.source_root,
        validation_dir=args.validation_dir,
        output_dir=args.output_dir,
        api_manifest=args.api_manifest,
        unified_report=args.unified_report,
        reference_report=args.reference_report,
        dem_image=args.dem_image,
        dem_label=args.dem_label,
        expected_coordinate_system=args.expected_coordinate_system,
        control_point_report=args.control_point_report,
        peer_review_record=args.peer_review_record,
        minimum_control_points=args.min_control_points,
        run_software=not args.skip_software_checks,
        run_security_audit=args.run_pip_audit,
        release_profile=args.release_profile,
    )
    json_path, markdown_path = write_certification_report(report, args.output_dir)
    summary = report["summary"]
    print(f"EclipseKit release check ({report['release_profile']}): {report['status']}")
    print(
        f"Gates: {summary['passed']} PASS / {summary['failed_or_error']} FAIL or ERROR / "
        f"{summary['not_run_or_partial']} NOT RUN or PARTIAL"
    )
    print(f"Software readiness: {report['software_release_readiness']}")
    print(f"Scientific certification: {report['scientific_certification_status']}")
    if report["release_profile"] == "alpha":
        scientific_summary = report["scientific_certification_summary"]
        print(
            "Scientific gates (still required for 1.0.0): "
            f"{scientific_summary['passed']} PASS / {scientific_summary['failed_or_error']} FAIL or ERROR / "
            f"{scientific_summary['not_run_or_partial']} NOT RUN or PARTIAL"
        )
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return 0 if report["status"] in {"CERTIFIED_WITHIN_DECLARED_SCOPE", "ALPHA_RELEASE_READY"} else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
