"""Audit the provenance and structural integrity of EclipseKit's scientific references.

This module inventories the small, independently sourced validation fixtures. It
is deliberately an input-audit tool: a PASS means the configured files are
present, parseable, traceable, and fingerprinted. It does not certify numerical
accuracy; acceptance calculations remain in validation_framework and
corridor_cli.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
from typing import Any, Mapping

from . import __version__
from .validation import load_reference_cases
from .validation_framework import load_path_reference_cases
from .shadow_corridor_validation import load_corridor_reference_csv
from .path_validation import load_path_reference
from .besselian import BesselianElements


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"Reference asset escapes validation directory: {path}") from exc


def _load_besselian_descriptor(path: Path, root: Path) -> tuple[dict[str, Any], Path]:
    if not path.is_file():
        raise FileNotFoundError(f"Besselian reference descriptor not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
        raise ValueError("Unsupported Besselian reference descriptor; expected schema_version 1")
    for field in ("case_id", "name", "source_url", "elements_file"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise ValueError(f"Besselian reference descriptor requires non-empty {field}")
    elements_path = (path.parent / payload["elements_file"]).expanduser().resolve()
    if not elements_path.is_relative_to(root.resolve()):
        raise ValueError("Besselian elements_file must remain inside validation directory")
    if not elements_path.is_file():
        raise FileNotFoundError(f"Besselian elements file not found: {elements_path}")
    # Parse JSON now so that a syntactically corrupt element asset cannot be
    # recorded as a healthy reference merely because its path exists.
    elements_document = json.loads(elements_path.read_text(encoding="utf-8"))
    if not isinstance(elements_document, Mapping):
        raise ValueError("Besselian elements file root must be a JSON object")
    BesselianElements.from_dict(elements_document)
    return dict(payload), elements_path


def audit_reference_matrix(validation_dir: str | Path) -> dict[str, Any]:
    """Validate fixture schemas and create a SHA-256 inventory of source assets."""
    root = Path(validation_dir).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Validation data directory not found: {root}")

    reference_cases_path = root / "reference_cases.json"
    path_manifest_path = root / "path_reference_manifest.json"
    besselian_path = root / "besselian_1999_reference.json"
    corridor_path = root / "global_corridor_2017_nasa.csv"

    local_cases, global_cases = load_reference_cases(reference_cases_path)
    path_cases = load_path_reference_cases(path_manifest_path)
    path_reference_rows = {case.case_id: load_path_reference(case.reference_file) for case in path_cases}
    besselian, besselian_elements_path = _load_besselian_descriptor(besselian_path, root)
    corridor_rows = load_corridor_reference_csv(corridor_path)

    asset_roles: dict[Path, set[str]] = {}

    def add_asset(path: Path, role: str) -> None:
        resolved = path.resolve()
        _relative(resolved, root)
        asset_roles.setdefault(resolved, set()).add(role)

    add_asset(reference_cases_path, "local_and_global_case_manifest")
    add_asset(path_manifest_path, "global_path_manifest")
    add_asset(besselian_path, "besselian_reference_descriptor")
    add_asset(besselian_elements_path, "besselian_elements")
    add_asset(corridor_path, "shadow_corridor_reference")
    for case in path_cases:
        add_asset(case.reference_file, f"global_path_reference:{case.case_id}")

    assets = []
    for path in sorted(asset_roles, key=lambda item: _relative(item, root)):
        stat = path.stat()
        assets.append({
            "path": _relative(path, root),
            "roles": sorted(asset_roles[path]),
            "size_bytes": stat.st_size,
            "sha256": _sha256(path),
        })

    sources: dict[str, dict[str, Any]] = {}
    cases: list[dict[str, Any]] = []
    observed_types: set[str] = set()
    for case in local_cases:
        if case.expected_eclipse_type:
            observed_types.add(case.expected_eclipse_type)
        sources.setdefault(case.source_url, {"url": case.source_url, "case_ids": []})["case_ids"].append(case.case_id)
        cases.append({
            "group": "local_circumstances",
            "case_id": case.case_id,
            "name": case.name,
            "event_time_utc": case.event_time_utc,
            "eclipse_type": case.expected_eclipse_type,
            "source_url": case.source_url,
            "source_precision_seconds": case.source_precision_seconds,
            "acceptance_tolerance_seconds": case.contact_tolerance_seconds,
        })
    for case in global_cases:
        sources.setdefault(case.source_url, {"url": case.source_url, "case_ids": []})["case_ids"].append(case.case_id)
        if case.expected_eclipse_type:
            observed_types.add(case.expected_eclipse_type)
        cases.append({
            "group": "global_maximum",
            "case_id": case.case_id,
            "name": case.name,
            "event_time_utc": case.event_time_utc,
            "eclipse_type": case.expected_eclipse_type,
            "source_url": case.source_url,
            "acceptance_tolerance_seconds": case.tolerance_seconds,
        })
    for case in path_cases:
        sources.setdefault(case.source_url, {"url": case.source_url, "case_ids": []})["case_ids"].append(case.case_id)
        cases.append({
            "group": "global_path",
            "case_id": case.case_id,
            "name": case.name,
            "event_time_utc": case.event_time_utc,
            "source_url": case.source_url,
            "source_time_step_seconds": case.source_time_step_seconds,
            "source_coordinate_resolution_arcmin": case.source_coordinate_resolution_arcmin,
            "acceptance_tolerance_km": case.tolerance_km,
            "reference_file": _relative(case.reference_file, root),
            "reference_rows": len(path_reference_rows[case.case_id]),
        })
    sources.setdefault(str(besselian["source_url"]), {"url": str(besselian["source_url"]), "case_ids": []})["case_ids"].append(str(besselian["case_id"]))
    if besselian.get("expected_eclipse_type"):
        observed_types.add(str(besselian["expected_eclipse_type"]).casefold())
    cases.append({
        "group": "besselian_regression",
        "case_id": str(besselian["case_id"]),
        "name": str(besselian["name"]),
        "eclipse_type": besselian.get("expected_eclipse_type"),
        "source_url": str(besselian["source_url"]),
        "reference_file": _relative(besselian_path, root),
        "elements_file": _relative(besselian_elements_path, root),
    })

    manifest_payload = json.loads(path_manifest_path.read_text(encoding="utf-8"))
    corridor_source = str(manifest_payload.get("corridor_reference_source", "NASA/GSFC selected 2017 corridor rows"))
    corridor_source_url = manifest_payload.get("corridor_reference_url")
    if corridor_source_url:
        sources.setdefault(str(corridor_source_url), {"url": str(corridor_source_url), "case_ids": []})["case_ids"].append("nasa-2017-shadow-corridor")
    cases.append({
        "group": "shadow_corridor",
        "case_id": "nasa-2017-shadow-corridor",
        "name": corridor_source,
        "source_url": str(corridor_source_url) if corridor_source_url else None,
        "reference_file": _relative(corridor_path, root),
        "reference_rows": len(corridor_rows),
    })

    expected_types = {"total", "annular", "partial", "hybrid"}
    missing_types = sorted(expected_types - observed_types)
    groups = {
        "local_circumstances": len(local_cases),
        "global_maximum": len(global_cases),
        "global_path": len(path_cases),
        "besselian_regression": 1,
        "shadow_corridor_rows": len(corridor_rows),
    }
    return {
        "schema": "eclipsekit.phase8_2.reference_matrix.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "status": "PASS",
        "interpretation": (
            "PASS means fixture structure, referenced assets, source identifiers and file fingerprints "
            "were audited. It is not a numerical accuracy result or universal scientific certification."
        ),
        "environment": {"eclipsekit_version": __version__, "python_version": platform.python_version()},
        "validation_directory": str(root),
        "summary": {
            "case_records": len(cases),
            "source_count": len(sources),
            "asset_count": len(assets),
            "groups": groups,
            "observed_eclipse_types": sorted(observed_types),
            "missing_eclipse_type_coverage": missing_types,
        },
        "cases": cases,
        "sources": [sources[key] for key in sorted(sources)],
        "assets": assets,
        "limitations": [
            "File hashes identify the audited bytes but do not establish the scientific correctness of a source.",
            "Sparse path and corridor tables cover only their documented epochs and resolution.",
            "Missing eclipse-type coverage is reported as a gap, not silently inferred.",
        ],
    }


def render_reference_matrix_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# EclipseKit Phase 8.2 — scientific reference matrix",
        "",
        f"**Audit status:** {report['status']}",
        f"**Generated (UTC):** {report['generated_utc']}",
        "",
        "## Coverage summary",
        "",
        f"- Case records: {summary['case_records']}",
        f"- Independent source identifiers: {summary['source_count']}",
        f"- Fingerprinted assets: {summary['asset_count']}",
        f"- Observed eclipse types: {', '.join(summary['observed_eclipse_types']) or 'none'}",
        f"- Missing type coverage: {', '.join(summary['missing_eclipse_type_coverage']) or 'none'}",
        "",
        "| Validation group | Records |",
        "|---|---:|",
    ]
    for name, count in summary["groups"].items():
        lines.append(f"| {name} | {count} |")
    lines.extend(["", "## Reference cases", "", "| Group | Case | Event | Type | Tolerance / detail | Source |", "|---|---|---|---|---|---|"])
    for item in report["cases"]:
        tolerance = item.get("acceptance_tolerance_seconds")
        if tolerance is not None:
            tolerance_text = f"{tolerance:g} s"
        elif item.get("acceptance_tolerance_km") is not None:
            tolerance_text = f"{item['acceptance_tolerance_km']:g} km"
        else:
            tolerance_text = f"{item.get('reference_rows', '—')} reference rows"
        lines.append(
            f"| {item['group']} | {item['name']} | {item.get('event_time_utc', '—')} | "
            f"{item.get('eclipse_type', '—') or '—'} | {tolerance_text} | {item.get('source_url') or 'not recorded'} |"
        )
    lines.extend(["", "## Data fingerprints", "", "| Asset | Bytes | SHA-256 |", "|---|---:|---|"])
    for asset in report["assets"]:
        lines.append(f"| `{asset['path']}` | {asset['size_bytes']} | `{asset['sha256']}` |")
    lines.extend(["", "## Interpretation", "", report["interpretation"], "", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit EclipseKit scientific reference coverage and SHA-256 provenance")
    parser.add_argument("--validation-dir", default="data/validation")
    parser.add_argument("--output-dir", default="reports/phase8_2")
    parser.add_argument("--stem", default="reference-matrix")
    args = parser.parse_args(argv)
    if not args.stem or Path(args.stem).name != args.stem or args.stem in {".", ".."}:
        parser.error("--stem must be a simple non-empty filename stem")
    try:
        report = audit_reference_matrix(args.validation_dir)
    except Exception as exc:
        parser.exit(2, f"Reference matrix audit failed: {type(exc).__name__}: {exc}\n")
    out = Path(args.output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"{args.stem}.json"
    md_path = out / f"{args.stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    md_path.write_text(render_reference_matrix_markdown(report), encoding="utf-8")
    print(f"Reference matrix audit: {report['status']}")
    print(f"Cases: {report['summary']['case_records']}; sources: {report['summary']['source_count']}; assets: {report['summary']['asset_count']}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
