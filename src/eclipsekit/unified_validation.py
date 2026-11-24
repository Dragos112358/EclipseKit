"""Run the Phase 6, Phase 8.1, 8.2 and 8.3 checks as one auditable workflow."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Sequence

from . import corridor_cli, earth_orientation, reference_matrix, validation_framework
from .ephemeris import default_ephemeris_cache_dir


def aggregate_component_statuses(statuses: Sequence[str]) -> str:
    """Conservatively aggregate component states; only clean PASS yields PASS."""
    normalized = [str(value).upper() for value in statuses]
    if not normalized:
        return "ERROR"
    if any(value in {"ERROR", "DIAGNOSTIC_ERROR"} for value in normalized):
        return "ERROR"
    if any(value in {"FAIL", "FAILED"} for value in normalized):
        return "FAIL"
    if any(value not in {"PASS"} for value in normalized):
        return "PARTIAL"
    return "PASS"


def _run_component(
    *,
    name: str,
    function: Callable[[list[str]], int],
    arguments: list[str],
    report_path: Path,
) -> dict[str, Any]:
    exit_code: int | None = None
    error = None
    report_path.unlink(missing_ok=True)
    try:
        exit_code = int(function(arguments))
    except SystemExit as exc:
        if isinstance(exc.code, int):
            exit_code = exc.code
        elif exc.code is None:
            exit_code = 0
        else:
            exit_code = 2
            error = str(exc.code).strip() or "Component terminated with SystemExit"
    except Exception as exc:  # preserve later components and write an aggregate report
        error = f"{type(exc).__name__}: {exc}"
        exit_code = 1

    payload = None
    if report_path.is_file():
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as exc:
            error = error or f"Could not read component JSON: {type(exc).__name__}: {exc}"
    if error:
        status = "ERROR"
    elif not isinstance(payload, dict):
        status = "ERROR"
        error = error or "Component did not produce its expected JSON report"
    else:
        status = str(payload.get("status", "UNKNOWN")).upper()
        if status == "UNKNOWN" and isinstance(payload.get("summary"), dict):
            status = str(payload["summary"].get("status", "UNKNOWN")).upper()
        if exit_code not in (0, None) and status == "PASS":
            status = "ERROR"
            error = "Component returned a non-zero exit code despite a PASS report"
    return {
        "name": name,
        "status": status,
        "exit_code": exit_code,
        "report": str(report_path),
        "error": error,
        "summary": payload.get("summary") if isinstance(payload, dict) else None,
    }


def render_unified_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# EclipseKit Phase 8.4 — unified scientific validation",
        "",
        f"**Overall status:** {report['status']}",
        f"**Generated (UTC):** {report['generated_utc']}",
        "",
        "## Component results",
        "",
        "| Component | Status | Exit code | Report |",
        "|---|---|---:|---|",
    ]
    for component in report["components"]:
        lines.append(
            f"| {component['name']} | {component['status']} | "
            f"{component['exit_code']} | `{component['report']}` |"
        )
        if component.get("error"):
            lines.append(f"\n  Error: {component['error']}")
    lines.extend([
        "",
        "## Interpretation",
        "",
        report["interpretation"],
        "",
        "## Scope and limitations",
        "",
    ])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run EclipseKit's scientific reference, shadow-corridor, data-provenance and EOP checks"
    )
    parser.add_argument("--validation-dir", default="data/validation")
    parser.add_argument("--kernel", default="de440s")
    parser.add_argument("--cache-dir", default=str(default_ephemeris_cache_dir()))
    parser.add_argument("--time-scale-mode", choices=("builtin", "iers", "fixed_delta_t"), default="builtin")
    parser.add_argument("--delta-t-seconds", type=float, default=None)
    parser.add_argument("--path-samples", type=int, default=301)
    parser.add_argument("--corridor-start", default="2017-08-21T17:00:00Z")
    parser.add_argument("--corridor-end", default="2017-08-21T17:40:00Z")
    parser.add_argument("--convergence-samples", default="3,11,21,51,101")
    parser.add_argument("--boundary-samples", type=int, default=144)
    parser.add_argument("--eop-at", default="2017-08-21T17:20:00Z")
    parser.add_argument("--output-dir", default="reports/phase8_4")
    args = parser.parse_args(argv)

    if args.time_scale_mode == "fixed_delta_t" and args.delta_t_seconds is None:
        parser.error("--delta-t-seconds is required with --time-scale-mode fixed_delta_t")
    if args.time_scale_mode != "fixed_delta_t" and args.delta_t_seconds is not None:
        parser.error("--delta-t-seconds is only valid with --time-scale-mode fixed_delta_t")
    if args.path_samples < 3:
        parser.error("--path-samples must be >= 3")

    validation_dir = Path(args.validation_dir).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    refs = validation_dir / "reference_cases.json"
    path_manifest = validation_dir / "path_reference_manifest.json"
    besselian = validation_dir / "besselian_1999_reference.json"
    corridor_ref = validation_dir / "global_corridor_2017_nasa.csv"

    phase6_json = output_dir / "phase6-scientific-validation.json"
    phase6_md = output_dir / "phase6-scientific-validation.md"
    phase81_dir = output_dir / "phase8_1_corridor"
    phase81_json = phase81_dir / "unified-shadow-corridor.json"
    phase82_json = output_dir / "phase8_2-reference-matrix.json"
    phase83_json = output_dir / "phase8_3-eop-provenance.json"

    components: list[dict[str, Any]] = []
    common = ["--kernel", args.kernel, "--cache-dir", args.cache_dir,
              "--time-scale-mode", args.time_scale_mode]
    if args.delta_t_seconds is not None:
        common += ["--delta-t-seconds", str(args.delta_t_seconds)]

    components.append(_run_component(
        name="Phase 6 scientific references",
        function=validation_framework.main,
        arguments=[
            "--references", str(refs), "--path-manifest", str(path_manifest),
            "--besselian-reference", str(besselian), *common,
            "--path-samples", str(args.path_samples),
            "--json-out", str(phase6_json), "--markdown-out", str(phase6_md),
        ],
        report_path=phase6_json,
    ))

    phase81_dir.mkdir(parents=True, exist_ok=True)
    components.append(_run_component(
        name="Phase 8.1 shadow corridor",
        function=corridor_cli.main,
        arguments=[
            *common, "--start", args.corridor_start, "--end", args.corridor_end,
            "--reference", str(corridor_ref), "--convergence-samples", args.convergence_samples,
            "--boundary-samples", str(args.boundary_samples),
            "--output-dir", str(phase81_dir), "--stem", "unified-shadow-corridor",
        ],
        report_path=phase81_json,
    ))

    components.append(_run_component(
        name="Phase 8.2 reference matrix and fingerprints",
        function=reference_matrix.main,
        arguments=[
            "--validation-dir", str(validation_dir), "--output-dir", str(output_dir),
            "--stem", "phase8_2-reference-matrix",
        ],
        report_path=phase82_json,
    ))

    eop_arguments = [
        "--mode", args.time_scale_mode, "--cache-dir", args.cache_dir,
        "--at", args.eop_at,
        "--json-out", str(phase83_json),
        "--markdown-out", str(output_dir / "phase8_3-eop-provenance.md"),
    ]
    if args.delta_t_seconds is not None:
        eop_arguments += ["--delta-t-seconds", str(args.delta_t_seconds)]
    components.append(_run_component(
        name="Phase 8.3 Earth-orientation provenance",
        function=earth_orientation.main,
        arguments=eop_arguments,
        report_path=phase83_json,
    ))

    status = aggregate_component_statuses([item["status"] for item in components])
    report = {
        "schema": "eclipsekit.phase8_4.unified_validation.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "status": status,
        "components": components,
        "summary": {
            "component_count": len(components),
            "passed": sum(item["status"] == "PASS" for item in components),
            "failed": sum(item["status"] == "FAIL" for item in components),
            "errors": sum(item["status"] == "ERROR" for item in components),
            "partial_or_unverified": sum(item["status"] not in {"PASS", "FAIL", "ERROR"} for item in components),
        },
        "inputs": {
            "validation_dir": str(validation_dir),
            "kernel": args.kernel,
            "cache_dir": args.cache_dir,
            "time_scale_mode": args.time_scale_mode,
            "delta_t_seconds": args.delta_t_seconds,
            "path_samples": args.path_samples,
            "corridor_start": args.corridor_start,
            "corridor_end": args.corridor_end,
            "convergence_samples": args.convergence_samples,
            "boundary_samples": args.boundary_samples,
            "eop_diagnostic_epoch": args.eop_at,
        },
        "interpretation": (
            "PASS means every selected component completed with a PASS under the recorded inputs and assumptions. "
            "It does not certify eclipses or geometries outside the included reference datasets and stated tolerances."
        ),
        "limitations": [
            "The reference-matrix audit fingerprints inputs; it does not establish the scientific correctness of a source.",
            "The corridor reference fixture contains sparse selected epochs; it is not a dense global-footprint validation.",
            "Built-in Earth-orientation tables are scoped to the recorded Skyfield version; only external IERS bytes receive a file hash.",
            "A PARTIAL status means one or more components were not fully verifiable; inspect the component reports before acceptance.",
        ],
    }
    json_path = output_dir / "unified-validation.json"
    markdown_path = output_dir / "unified-validation.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_unified_markdown(report), encoding="utf-8")
    print(f"Unified scientific validation: {status}")
    print(f"Components: {report['summary']['passed']} PASS / {report['summary']['failed']} FAIL / "
          f"{report['summary']['errors']} ERROR / {report['summary']['partial_or_unverified']} PARTIAL")
    for component in components:
        print(f"  {component['name']}: {component['status']}")
        if component.get("error"):
            print(f"    {component['error']}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
