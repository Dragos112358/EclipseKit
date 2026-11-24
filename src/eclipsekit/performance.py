"""Reproducible micro-benchmarks for EclipseKit's numerical building blocks.

Benchmark results are descriptive, not pass/fail performance guarantees. Compare
runs only on equivalent machines and software environments; never use absolute
wall-clock thresholds in the unit-test suite.
"""

from __future__ import annotations

import argparse
import cProfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
import statistics
import time
import tracemalloc
from typing import Any, Callable, Sequence

import numpy as np

from . import __version__
from .cities import CityCatalog
from .contacts import brent_root
from .engine import _evaluate_city_search_batch
from .geometry import circle_overlap_fraction, wgs84_inverse
from .models import City
from .uncertainty import finite_difference_jacobian, propagate_covariance


@dataclass(frozen=True, slots=True)
class BenchmarkCaseResult:
    """Timing distribution for one callable, measured over repeated batches."""

    name: str
    iterations_per_repeat: int
    warmups: int
    repeats: int
    samples_seconds: tuple[float, ...]
    median_seconds_per_call: float
    mean_seconds_per_call: float
    stdev_seconds_per_call: float
    min_seconds_per_call: float
    max_seconds_per_call: float
    p95_seconds_per_call: float
    calls_per_second: float
    peak_traced_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "iterations_per_repeat": self.iterations_per_repeat,
            "warmups": self.warmups,
            "repeats": self.repeats,
            "samples_seconds_per_call": list(self.samples_seconds),
            "median_seconds_per_call": self.median_seconds_per_call,
            "mean_seconds_per_call": self.mean_seconds_per_call,
            "stdev_seconds_per_call": self.stdev_seconds_per_call,
            "min_seconds_per_call": self.min_seconds_per_call,
            "max_seconds_per_call": self.max_seconds_per_call,
            "p95_seconds_per_call": self.p95_seconds_per_call,
            "calls_per_second": self.calls_per_second,
            "peak_traced_bytes": self.peak_traced_bytes,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkSuiteResult:
    """A versioned benchmark run with enough environment data for comparison."""

    generated_utc: str
    eclipsekit_version: str
    python_version: str
    python_implementation: str
    platform_system: str
    platform_release: str
    machine: str
    processor: str
    numpy_version: str
    warmups: int
    repeats: int
    iterations: int
    memory_tracking: bool
    cases: tuple[BenchmarkCaseResult, ...]
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_utc": self.generated_utc,
            "environment": {
                "eclipsekit_version": self.eclipsekit_version,
                "python_version": self.python_version,
                "python_implementation": self.python_implementation,
                "platform_system": self.platform_system,
                "platform_release": self.platform_release,
                "machine": self.machine,
                "processor": self.processor,
                "numpy_version": self.numpy_version,
            },
            "settings": {
                "warmups": self.warmups,
                "repeats": self.repeats,
                "iterations": self.iterations,
                "memory_tracking": self.memory_tracking,
            },
            "cases": [case.to_dict() for case in self.cases],
            "interpretation": (
                "Micro-benchmark timings are environment-specific and are not scientific "
                "accuracy metrics or universal performance guarantees."
            ),
        }


def _positive_integer(value: Any, name: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer")
    number = int(value)
    if number < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return number


def benchmark_callable(
    name: str,
    function: Callable[[], Any],
    *,
    iterations: int = 100,
    warmups: int = 2,
    repeats: int = 7,
    track_memory: bool = False,
) -> BenchmarkCaseResult:
    """Time a no-argument callable using repeated batches and a warm-up period."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")
    if not callable(function):
        raise TypeError("function must be callable")
    iterations_value = _positive_integer(iterations, "iterations")
    repeats_value = _positive_integer(repeats, "repeats")
    warmups_value = _positive_integer(warmups, "warmups", minimum=0)
    if not isinstance(track_memory, bool):
        raise ValueError("track_memory must be bool")

    for _ in range(warmups_value):
        for _ in range(iterations_value):
            function()

    samples: list[float] = []
    peak_bytes: int | None = None
    if track_memory:
        tracemalloc.start()
    try:
        for _ in range(repeats_value):
            started = time.perf_counter_ns()
            for _ in range(iterations_value):
                function()
            elapsed = (time.perf_counter_ns() - started) / 1_000_000_000
            samples.append(elapsed / iterations_value)
        if track_memory:
            _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        if track_memory and tracemalloc.is_tracing():
            tracemalloc.stop()

    ordered = sorted(samples)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    median = float(statistics.median(samples))
    mean = float(statistics.fmean(samples))
    stdev = float(statistics.stdev(samples)) if len(samples) > 1 else 0.0
    return BenchmarkCaseResult(
        name=name.strip(),
        iterations_per_repeat=iterations_value,
        warmups=warmups_value,
        repeats=repeats_value,
        samples_seconds=tuple(float(value) for value in samples),
        median_seconds_per_call=median,
        mean_seconds_per_call=mean,
        stdev_seconds_per_call=stdev,
        min_seconds_per_call=float(ordered[0]),
        max_seconds_per_call=float(ordered[-1]),
        p95_seconds_per_call=float(ordered[p95_index]),
        calls_per_second=(1.0 / median) if median > 0.0 else 0.0,
        peak_traced_bytes=peak_bytes,
    )


def _benchmark_workloads() -> tuple[tuple[str, Callable[[], Any]], ...]:
    """Return small deterministic hot-path workloads without external assets."""
    def inverse_geodesic() -> Any:
        return wgs84_inverse(44.40372, 179.7, 44.73230, -179.8)

    def root_solve() -> Any:
        return brent_root(lambda value: value * value - 2.0, 0.0, 2.0)

    def disc_overlap() -> Any:
        return circle_overlap_fraction(0.00465, 0.00475, 0.0002)

    def jacobian() -> Any:
        return finite_difference_jacobian(
            lambda values: (values[0] ** 2 + values[1], values[0] * values[1]),
            (1.25, -0.75),
        )

    def covariance_propagation() -> Any:
        return propagate_covariance(
            ((2.0, 1.0), (0.5, -1.0)),
            ((0.04, 0.01), (0.01, 0.09)),
        )

    # Deterministic scalability workload. The city index is built once, like a
    # caller reusing a loaded catalogue across repeated country searches.
    benchmark_cities = [
        City(
            f"Site-{index}", "Benchmarkland",
            float((index % 101) / 25.0 - 2.0),
            float((index % 137) / 34.0 - 2.0),
        )
        for index in range(2048)
    ]
    catalog = CityCatalog(benchmark_cities)

    def cached_country_index() -> Any:
        return catalog.indices_for_country("benchmarkland")

    def scanned_country_index() -> Any:
        return np.flatnonzero(catalog._countries == "benchmarkland")

    def batched_country_indices() -> Any:
        return sum(len(batch) for batch in catalog.iter_index_batches(
            "benchmarkland", batch_size=256
        ))

    # ITRS-like moving position nodes model the shape and dimensions of the
    # vectorised screening workload without requiring an ephemeris or kernel.
    hours = np.linspace(-4.0, 4.0, 21, dtype=np.float64)
    theta = hours * (2.0 * math.pi / 24.0)
    sun_nodes = np.column_stack((149_597_870.7 * np.cos(theta),
                                 149_597_870.7 * np.sin(theta),
                                 np.zeros_like(theta)))
    moon_nodes = np.column_stack((384_400.0 * np.cos(theta + 0.0002),
                                  384_400.0 * np.sin(theta + 0.0002),
                                  np.zeros_like(theta)))
    city_batches = [
        np.arange(offset, min(offset + 256, len(benchmark_cities)), dtype=np.intp)
        for offset in range(0, len(benchmark_cities), 256)
    ]

    def evaluate_city_batch(indices: np.ndarray) -> Any:
        return _evaluate_city_search_batch(
            indices, catalog.ecef, catalog.up, sun_nodes, moon_nodes, hours,
            min_magnitude=0.001, refinement_iterations=8,
            search_radius_hours=4.0, sun_radius_km=695_700.0,
            moon_radius_km=1_737.4,
        )

    def city_batches_serial() -> Any:
        return [evaluate_city_batch(indices) for indices in city_batches]

    def city_batches_threaded() -> Any:
        with ThreadPoolExecutor(max_workers=4) as executor:
            return list(executor.map(evaluate_city_batch, city_batches))

    return (
        ("wgs84_inverse_antimeridian", inverse_geodesic),
        ("brent_root_scalar", root_solve),
        ("circle_overlap_fraction", disc_overlap),
        ("finite_difference_jacobian_2d", jacobian),
        ("covariance_propagation_2x2", covariance_propagation),
        ("city_country_index_scan_2048", scanned_country_index),
        ("city_country_index_cache_2048", cached_country_index),
        ("city_country_index_batches_2048", batched_country_indices),
        ("city_search_batches_serial_2048", city_batches_serial),
        ("city_search_batches_threads4_2048", city_batches_threaded),
    )


def run_benchmark_suite(
    *, iterations: int = 100, warmups: int = 2, repeats: int = 7,
    track_memory: bool = False,
) -> BenchmarkSuiteResult:
    """Run the built-in deterministic micro-benchmark suite."""
    iterations_value = _positive_integer(iterations, "iterations")
    repeats_value = _positive_integer(repeats, "repeats")
    warmups_value = _positive_integer(warmups, "warmups", minimum=0)
    if not isinstance(track_memory, bool):
        raise ValueError("track_memory must be bool")
    cases = tuple(
        benchmark_callable(
            name, function, iterations=iterations_value,
            warmups=warmups_value, repeats=repeats_value,
            track_memory=track_memory,
        )
        for name, function in _benchmark_workloads()
    )
    return BenchmarkSuiteResult(
        generated_utc=datetime.now(timezone.utc).isoformat(),
        eclipsekit_version=__version__,
        python_version=platform.python_version(),
        python_implementation=platform.python_implementation(),
        platform_system=platform.system(),
        platform_release=platform.release(),
        machine=platform.machine(),
        processor=platform.processor() or "unknown",
        numpy_version=np.__version__,
        warmups=warmups_value,
        repeats=repeats_value,
        iterations=iterations_value,
        memory_tracking=track_memory,
        cases=cases,
    )


def compare_benchmark_suites(
    current: BenchmarkSuiteResult | dict[str, Any],
    baseline: dict[str, Any],
    *,
    max_slowdown_ratio: float = 1.25,
) -> dict[str, Any]:
    """Compare medians only when runtime environment identity is compatible."""
    if isinstance(current, BenchmarkSuiteResult):
        current_dict = current.to_dict()
    elif isinstance(current, dict):
        current_dict = current
    else:
        raise TypeError("current must be BenchmarkSuiteResult or dict")
    if not isinstance(baseline, dict) or baseline.get("schema_version") != 1:
        raise ValueError("baseline must be a schema_version 1 benchmark report")
    if current_dict.get("schema_version") != 1:
        raise ValueError("current must be a schema_version 1 benchmark report")
    if isinstance(max_slowdown_ratio, bool):
        raise ValueError("max_slowdown_ratio must be a finite number >= 1")
    try:
        threshold = float(max_slowdown_ratio)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("max_slowdown_ratio must be a finite number >= 1") from exc
    if not math.isfinite(threshold) or threshold < 1.0:
        raise ValueError("max_slowdown_ratio must be a finite number >= 1")

    current_env = current_dict.get("environment", {})
    baseline_env = baseline.get("environment", {})
    comparable_keys = ("python_implementation", "python_version", "platform_system", "machine")
    environment_match = all(
        current_env.get(key) not in (None, "")
        and baseline_env.get(key) not in (None, "")
        and current_env.get(key) == baseline_env.get(key)
        for key in comparable_keys
    )
    base_cases = {item.get("name"): item for item in baseline.get("cases", []) if isinstance(item, dict)}
    comparisons: list[dict[str, Any]] = []
    for item in current_dict.get("cases", []):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        previous = base_cases.get(item["name"])
        if previous is None:
            comparisons.append({"name": item["name"], "status": "NO_BASELINE"})
            continue
        current_median = float(item["median_seconds_per_call"])
        baseline_median = float(previous["median_seconds_per_call"])
        if not environment_match:
            status = "INCOMPARABLE_ENVIRONMENT"
            ratio = None
        elif (
            not math.isfinite(current_median)
            or current_median < 0.0
            or not math.isfinite(baseline_median)
            or baseline_median <= 0.0
        ):
            status = "INCOMPARABLE_BASELINE"
            ratio = None
        else:
            ratio = current_median / baseline_median
            status = "REGRESSION" if ratio > threshold else "PASS"
        comparisons.append({
            "name": item["name"],
            "status": status,
            "current_median_seconds": current_median,
            "baseline_median_seconds": baseline_median,
            "slowdown_ratio": ratio,
            "allowed_slowdown_ratio": threshold,
        })
    known_statuses = {item["status"] for item in comparisons}
    overall = "NO_CASES" if not known_statuses else (
        "FAIL" if "REGRESSION" in known_statuses else (
            "INCOMPARABLE" if known_statuses & {"INCOMPARABLE_ENVIRONMENT", "INCOMPARABLE_BASELINE"}
            else ("NO_BASELINE" if known_statuses == {"NO_BASELINE"} else "PASS")
        )
    )
    return {
        "schema_version": 1,
        "status": overall,
        "environment_compatible": environment_match,
        "max_slowdown_ratio": threshold,
        "comparisons": comparisons,
        "notes": [
            "A performance comparison is valid only for equivalent hardware, Python and runtime settings.",
            "REGRESSION means the observed median exceeds the configured ratio; rerun to assess noise before acting.",
            "Micro-benchmarks do not replace end-to-end profiling of a representative eclipse workload.",
        ],
    }


def profile_benchmark_workloads(output_path: str | Path, *, iterations: int = 100) -> Path:
    """Write a cProfile .pstats file for the same representative workloads.

    Profiling is intentionally kept separate from timing runs because profiler
    instrumentation changes observed latency.
    """
    iterations_value = _positive_integer(iterations, "iterations")
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    profiler = cProfile.Profile()
    profiler.enable()
    try:
        for _, function in _benchmark_workloads():
            for _ in range(iterations_value):
                function()
    finally:
        profiler.disable()
        profiler.dump_stats(str(destination))
    return destination


def benchmark_suite_to_markdown(result: BenchmarkSuiteResult, comparison: dict[str, Any] | None = None) -> str:
    lines = [
        "# EclipseKit performance benchmark",
        "",
        f"- **Generated (UTC):** `{result.generated_utc}`",
        f"- **EclipseKit:** `{result.eclipsekit_version}`",
        f"- **Python:** `{result.python_version}` ({result.python_implementation})",
        f"- **Platform:** `{result.platform_system} {result.platform_release}` / `{result.machine}`",
        f"- **NumPy:** `{result.numpy_version}`",
        f"- **Settings:** {result.warmups} warmups, {result.repeats} repeats, {result.iterations} calls/repeat",
        f"- **Memory tracking:** `{result.memory_tracking}`",
        "",
        "| Workload | Median (ms/call) | Mean (ms/call) | p95 (ms/call) | Calls/s | Peak traced bytes |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for case in result.cases:
        peak = "" if case.peak_traced_bytes is None else str(case.peak_traced_bytes)
        lines.append(
            f"| {case.name} | {case.median_seconds_per_call * 1000:.6f} "
            f"| {case.mean_seconds_per_call * 1000:.6f} "
            f"| {case.p95_seconds_per_call * 1000:.6f} "
            f"| {case.calls_per_second:.2f} | {peak} |"
        )
    if comparison is not None:
        lines.extend([
            "", "## Baseline comparison", "",
            f"- **Status:** `{comparison['status']}`",
            f"- **Environment compatible:** `{comparison['environment_compatible']}`",
            "", "| Workload | Status | Slowdown ratio | Allowed |", "|---|---|---:|---:|",
        ])
        for item in comparison["comparisons"]:
            ratio = "" if item.get("slowdown_ratio") is None else f"{item['slowdown_ratio']:.3f}x"
            allowed = item.get("allowed_slowdown_ratio", "")
            lines.append(f"| {item['name']} | {item['status']} | {ratio} | {allowed} |")
        lines.extend(["", *[f"- {note}" for note in comparison.get("notes", [])]])
    lines.extend([
        "", "## Interpretation", "",
        "These deterministic micro-benchmarks help identify relative changes in selected "
        "numerical primitives. They are not end-to-end eclipse timings, accuracy checks, "
        "or universal performance guarantees. Do not compare reports across different "
        "hardware or materially different Python environments.",
    ])
    return "\n".join(lines) + "\n"


def write_benchmark_report(
    result: BenchmarkSuiteResult,
    output_dir: str | Path,
    *,
    stem: str = "benchmark",
    comparison: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    if not isinstance(result, BenchmarkSuiteResult):
        raise TypeError("result must be a BenchmarkSuiteResult")
    if not stem or Path(stem).name != stem or stem in {".", ".."}:
        raise ValueError("stem must be a simple filename without directory components")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{stem}.json"
    markdown_path = directory / f"{stem}.md"
    payload = result.to_dict()
    if comparison is not None:
        payload["baseline_comparison"] = comparison
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(benchmark_suite_to_markdown(result, comparison), encoding="utf-8")
    return json_path, markdown_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark selected EclipseKit numerical primitives.")
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--track-memory", action="store_true")
    parser.add_argument("--baseline-json", type=Path)
    parser.add_argument("--profile-output", type=Path, help="Optional cProfile .pstats destination")
    parser.add_argument("--max-slowdown-ratio", type=float, default=1.25)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/phase7_7"))
    parser.add_argument("--stem", default="benchmark")
    args = parser.parse_args(argv)
    try:
        result = run_benchmark_suite(
            iterations=args.iterations, warmups=args.warmups,
            repeats=args.repeats, track_memory=args.track_memory,
        )
        comparison = None
        if args.baseline_json is not None:
            baseline = json.loads(args.baseline_json.read_text(encoding="utf-8"))
            comparison = compare_benchmark_suites(
                result, baseline, max_slowdown_ratio=args.max_slowdown_ratio
            )
        json_path, markdown_path = write_benchmark_report(
            result, args.output_dir, stem=args.stem, comparison=comparison
        )
        profile_path = (
            profile_benchmark_workloads(args.profile_output, iterations=args.iterations)
            if args.profile_output is not None else None
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"EclipseKit benchmark could not complete: {exc}\n")
    for case in result.cases:
        print(
            f"{case.name}: median={case.median_seconds_per_call * 1000:.6f} ms/call "
            f"p95={case.p95_seconds_per_call * 1000:.6f} ms/call "
            f"rate={case.calls_per_second:.2f} calls/s"
        )
    if comparison is not None:
        print(f"Baseline comparison: {comparison['status']}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    if profile_path is not None:
        print(f"Profile: {profile_path}")
    return 1 if comparison is not None and comparison["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
