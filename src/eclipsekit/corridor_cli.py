"""Command-line runner for Phase 8 shadow-corridor scientific validation."""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from . import __version__
from .earth_orientation import EarthOrientationConfig
from .engine import EclipseEngine
from .exports import (
    shadow_corridor_to_geojson,
    write_geojson,
    write_shadow_corridor_csv,
    write_shadow_corridor_kml,
)
from .shadow_corridor_validation import (
    compare_shadow_corridor_resolutions,
    validate_shadow_corridor_reference,
)


def parse_sample_counts(value: str) -> list[int]:
    """Parse nested corridor sample resolutions from a comma-separated value."""
    if not isinstance(value, str) or not value.strip():
        raise argparse.ArgumentTypeError("sample counts must be a non-empty comma-separated list")
    parts = value.split(",")
    if any(not part.strip() for part in parts):
        raise argparse.ArgumentTypeError("sample counts cannot contain empty items")
    try:
        counts = [int(part.strip()) for part in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "sample counts must be comma-separated integers"
        ) from exc
    if len(counts) < 2:
        raise argparse.ArgumentTypeError("provide at least two sample counts")
    if any(count < 2 for count in counts):
        raise argparse.ArgumentTypeError("each sample count must be >= 2")
    if counts != sorted(set(counts)):
        raise argparse.ArgumentTypeError(
            "sample counts must be unique and strictly increasing"
        )
    finest_intervals = counts[-1] - 1
    invalid = [
        count for count in counts[:-1]
        if finest_intervals % (count - 1) != 0
    ]
    if invalid:
        raise argparse.ArgumentTypeError(
            "sample counts must form nested uniform grids; each (count - 1) "
            "must divide (finest_count - 1)"
        )
    return counts


def _safe_stem(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", value) or value in {".", ".."}:
        raise argparse.ArgumentTypeError(
            "stem must contain 1-80 letters, numbers, dots, underscores or hyphens"
        )
    return value


def _render_markdown(payload: dict) -> str:
    validation = payload["validation"]
    convergence = payload["convergence"]
    environment = payload["environment"]
    inputs = payload["inputs"]
    lines = [
        "# EclipseKit Phase 8.1 — shadow-corridor validation",
        "",
        f"**Overall status:** {payload['status']}",
        f"**Generated (UTC):** {payload['generated_utc']}",
        "",
        "## Run metadata",
        "",
        f"- **EclipseKit version:** {environment['eclipsekit_version']}",
        f"- **Kernel argument:** `{environment['kernel_argument']}`",
        f"- **Kernel source:** `{environment['kernel_source']}`",
        f"- **Time-scale mode:** `{environment['time_scale_mode']}`",
        f"- **Delta-T:** {environment['time_scale']['delta_t_seconds']:.6f} s",
        f"- **DUT1:** {environment['time_scale']['dut1_seconds']:+.6f} s",
        f"- **EOP reproducibility:** {(environment.get('earth_orientation_provenance') or {}).get('reproducibility_level', 'not recorded')}",
        f"- **Skyfield version:** {(environment.get('earth_orientation_provenance') or {}).get('skyfield_version') or 'not recorded'}",
        f"- **EOP SHA-256:** {(environment.get('earth_orientation_provenance') or {}).get('sha256') or 'not applicable / not found'}",
        "",
        "## Inputs",
        "",
        f"- **Start:** {inputs['start_utc']}",
        f"- **End:** {inputs['end_utc']}",
        f"- **Reference:** `{inputs['reference_file']}`",
        f"- **Source ID:** {inputs['source_id']}",
        f"- **Boundary samples per time slice:** {inputs['boundary_samples']}",
        f"- **Time resolutions:** {', '.join(map(str, inputs['convergence_sample_counts']))}",
        "",
        "## NASA reference comparison",
        "",
        f"- **Status:** {validation['status']}",
        f"- **Rows:** {validation['passed_count']} PASS / {validation['failed_count']} FAIL",
        f"- **Maximum center error:** {validation['maximum_center_error_km']}",
        f"- **Maximum boundary error:** {validation['maximum_boundary_error_km']}",
        f"- **Maximum width error:** {validation['maximum_width_error_km']}",
        f"- **Maximum duration error:** {validation['maximum_duration_error_seconds']}",
        "",
        validation["markdown"],
        "",
        "## Sampling convergence diagnostic",
        "",
        "The finest requested resolution is a numerical comparison baseline, not independent truth.",
        "This section measures sensitivity to time sampling; it does not establish physical accuracy.",
        "",
        "| Samples | Valid points | Path-length difference (km) | Mean-width difference (km) | Max-width difference (km) | Mean-duration difference (s) | Status |",
        "|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in convergence["comparisons"]:
        def fmt(value):
            return "—" if value is None else f"{value:.6f}"
        lines.append(
            f"| {item['sample_count']} | {item['summary']['valid_sample_count']} | "
            f"{fmt(item['absolute_differences_from_finest']['centerline_length_difference_km'])} | "
            f"{fmt(item['absolute_differences_from_finest']['mean_central_width_difference_km'])} | "
            f"{fmt(item['absolute_differences_from_finest']['maximum_central_width_difference_km'])} | "
            f"{fmt(item['absolute_differences_from_finest']['mean_central_duration_estimate_difference_seconds'])} | "
            f"{item['status']} |"
        )
    lines.extend([
        "",
        "## Geometry scope and caveats",
        "",
        f"- **Geometry model:** {payload['corridor']['geometry_model']}",
        *[f"- {note}" for note in payload["corridor"].get("notes", [])],
        "- Sparse reference matches validate only the documented rows and tolerances.",
        "- Sampling convergence is not a substitute for independent reference data.",
        "- The current corridor geometry does not include terrain, atmosphere, or lunar-limb relief.",
        "",
    ])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run DE440s-backed global shadow-corridor validation, "
            "sampling-convergence diagnostics and GIS exports."
        )
    )
    parser.add_argument("--kernel", default="de440s", help="JPL kernel name or local BSP path")
    parser.add_argument("--cache-dir", default=None, help="Explicit Skyfield ephemeris/EOP cache directory")
    parser.add_argument("--start", default="2017-08-21T17:00:00Z", help="Start UTC time")
    parser.add_argument("--end", default="2017-08-21T17:40:00Z", help="End UTC time")
    parser.add_argument(
        "--reference", default="data/validation/global_corridor_2017_nasa.csv",
        help="CSV containing independent central-corridor reference rows",
    )
    parser.add_argument(
        "--source-id",
        default="NASA/GSFC 2017-08-21 path table; selected 17:00/17:20/17:40 UT rows",
    )
    parser.add_argument(
        "--convergence-samples", type=parse_sample_counts, default=parse_sample_counts("3,11,21,51,101"),
        help="Nested time-sampling resolutions, e.g. 3,11,21,51,101",
    )
    parser.add_argument("--boundary-samples", type=int, default=144,
                        help="Cone-boundary azimuth samples per time slice (>=16)")
    parser.add_argument("--time-scale-mode", choices=("builtin", "iers", "fixed_delta_t"),
                        default="builtin")
    parser.add_argument("--delta-t-seconds", type=float, default=None,
                        help="Required only with --time-scale-mode fixed_delta_t")
    parser.add_argument("--coordinate-tolerance-km", type=float, default=8.0)
    parser.add_argument("--width-tolerance-km", type=float, default=8.0)
    parser.add_argument("--duration-tolerance-seconds", type=float, default=10.0)
    parser.add_argument("--max-time-offset-seconds", type=float, default=65.0)
    parser.add_argument("--output-dir", default="reports/phase8_1")
    parser.add_argument("--stem", type=_safe_stem, default="shadow-corridor-2017")
    args = parser.parse_args(argv)

    if args.boundary_samples < 16:
        parser.error("--boundary-samples must be >= 16")
    if args.time_scale_mode == "fixed_delta_t" and args.delta_t_seconds is None:
        parser.error("--delta-t-seconds is required with --time-scale-mode fixed_delta_t")
    if args.time_scale_mode != "fixed_delta_t" and args.delta_t_seconds is not None:
        parser.error("--delta-t-seconds can only be used with fixed_delta_t mode")
    for name in (
        "coordinate_tolerance_km", "width_tolerance_km", "duration_tolerance_seconds",
        "max_time_offset_seconds",
    ):
        value = getattr(args, name)
        if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            parser.error(f"--{name.replace('_', '-')} must be finite and positive")

    reference_path = Path(args.reference).expanduser()
    if not reference_path.is_file():
        parser.error(f"reference CSV not found: {reference_path}")

    orientation = (
        EarthOrientationConfig.fixed(args.delta_t_seconds)
        if args.time_scale_mode == "fixed_delta_t"
        else EarthOrientationConfig(mode=args.time_scale_mode)
    )
    try:
        engine = EclipseEngine.from_jpl(
            args.kernel, earth_orientation=orientation, cache_dir=args.cache_dir
        )
        corridors = {
            count: engine.global_shadow_corridor(
                args.start,
                args.end,
                samples=count,
                boundary_samples=args.boundary_samples,
            )
            for count in args.convergence_samples
        }
        finest_count = args.convergence_samples[-1]
        finest_corridor = corridors[finest_count]
        convergence = compare_shadow_corridor_resolutions(corridors)
        validation = validate_shadow_corridor_reference(
            finest_corridor,
            reference_path,
            source_id=args.source_id,
            coordinate_tolerance_km=args.coordinate_tolerance_km,
            width_tolerance_km=args.width_tolerance_km,
            duration_tolerance_seconds=args.duration_tolerance_seconds,
            max_time_offset_seconds=args.max_time_offset_seconds,
        )
        time_scale = engine.time_scale_diagnostics(args.start)
    except Exception as exc:
        parser.exit(2, f"Could not run corridor validation: {type(exc).__name__}: {exc}\n")

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": output_dir / f"{args.stem}.json",
        "markdown": output_dir / f"{args.stem}.md",
        "geojson": output_dir / f"{args.stem}.geojson",
        "csv": output_dir / f"{args.stem}.csv",
        "kml": output_dir / f"{args.stem}.kml",
    }
    kernel_source = getattr(getattr(engine, "context", None), "kernel_source", args.kernel)
    payload = {
        "schema": "eclipsekit.phase8_1.shadow_corridor_validation.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "status": validation.status,
        "environment": {
            "eclipsekit_version": __version__,
            "kernel_argument": args.kernel,
            "kernel_source": str(kernel_source),
            "time_scale_mode": args.time_scale_mode,
            "time_scale": time_scale,
            "earth_orientation_provenance": getattr(
                getattr(engine, "context", None), "earth_orientation_provenance", None
            ),
            "cache_dir": str(args.cache_dir) if args.cache_dir else None,
        },
        "inputs": {
            "start_utc": args.start,
            "end_utc": args.end,
            "reference_file": str(reference_path),
            "source_id": args.source_id,
            "convergence_sample_counts": args.convergence_samples,
            "boundary_samples": args.boundary_samples,
            "coordinate_tolerance_km": args.coordinate_tolerance_km,
            "width_tolerance_km": args.width_tolerance_km,
            "duration_tolerance_seconds": args.duration_tolerance_seconds,
            "max_time_offset_seconds": args.max_time_offset_seconds,
            "delta_t_seconds": args.delta_t_seconds,
        },
        "validation": {
            **validation.to_dict(),
            "markdown": validation.to_markdown(),
        },
        "convergence": convergence,
        "corridor": finest_corridor.to_dict(),
        "artifacts": {key: str(value) for key, value in paths.items()},
    }
    paths["json"].write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    paths["markdown"].write_text(_render_markdown(payload), encoding="utf-8")
    if len(finest_corridor.samples) >= 2:
        write_geojson(shadow_corridor_to_geojson(finest_corridor), paths["geojson"])
        write_shadow_corridor_csv(finest_corridor, paths["csv"])
        write_shadow_corridor_kml(finest_corridor, paths["kml"])
    else:
        for key in ("geojson", "csv", "kml"):
            paths[key] = None
        payload["artifacts"] = {key: (str(value) if value is not None else None)
                                for key, value in paths.items()}
        paths["json"].write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        paths["markdown"].write_text(_render_markdown(payload), encoding="utf-8")

    print(f"Shadow corridor validation: {validation.status}")
    print(f"Reference rows: {validation.passed_count} PASS / {validation.failed_count} FAIL")
    print(f"Kernel: {args.kernel} ({kernel_source})")
    print(f"Time-scale mode: {args.time_scale_mode}")
    print(f"Valid samples at finest resolution: {len(finest_corridor.samples)} / {finest_count}")
    print("Sampling convergence (diagnostic):")
    for item in convergence["comparisons"]:
        differences = item["absolute_differences_from_finest"]
        print(
            f"  {item['sample_count']} vs {finest_count}: "
            f"path-length Δ={differences['centerline_length_difference_km']} km, "
            f"mean-width Δ={differences['mean_central_width_difference_km']} km"
        )
    for key, value in paths.items():
        if value is not None:
            print(f"{key.upper()}: {value}")
    if time_scale.get("warning"):
        print(f"WARNING: {time_scale['warning']}")
    return 0 if validation.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
