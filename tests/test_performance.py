from __future__ import annotations

import json

import pytest

from eclipsekit.performance import (
    BenchmarkSuiteResult,
    benchmark_callable,
    compare_benchmark_suites,
    run_benchmark_suite,
    profile_benchmark_workloads,
    write_benchmark_report,
)


def test_benchmark_callable_returns_repeat_statistics_and_counts_calls():
    counter = {"calls": 0}

    def workload():
        counter["calls"] += 1

    result = benchmark_callable(
        "counter", workload, iterations=3, warmups=1, repeats=4
    )
    assert result.name == "counter"
    assert len(result.samples_seconds) == 4
    assert result.iterations_per_repeat == 3
    assert result.median_seconds_per_call >= 0.0
    assert result.p95_seconds_per_call >= result.min_seconds_per_call
    assert result.max_seconds_per_call >= result.min_seconds_per_call
    assert counter["calls"] == (1 + 4) * 3


def test_benchmark_callable_can_track_peak_memory():
    result = benchmark_callable(
        "allocation", lambda: bytearray(128), iterations=2,
        warmups=0, repeats=2, track_memory=True,
    )
    assert result.peak_traced_bytes is not None
    assert result.peak_traced_bytes >= 128


@pytest.mark.parametrize(
    "kwargs",
    [
        {"iterations": 0},
        {"iterations": True},
        {"warmups": -1},
        {"repeats": 0},
        {"track_memory": 1},
    ],
)
def test_benchmark_callable_rejects_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        benchmark_callable("invalid", lambda: None, **kwargs)


def test_benchmark_suite_contains_named_deterministic_workloads():
    result = run_benchmark_suite(iterations=2, warmups=0, repeats=2)
    assert isinstance(result, BenchmarkSuiteResult)
    assert {case.name for case in result.cases} == {
        "wgs84_inverse_antimeridian",
        "brent_root_scalar",
        "circle_overlap_fraction",
        "finite_difference_jacobian_2d",
        "covariance_propagation_2x2",
        "city_country_index_scan_2048",
        "city_country_index_cache_2048",
        "city_country_index_batches_2048",
        "city_search_batches_serial_2048",
        "city_search_batches_threads4_2048",
    }
    assert all(case.median_seconds_per_call >= 0.0 for case in result.cases)
    assert result.to_dict()["schema_version"] == 1


def test_benchmark_comparison_detects_slowdown_and_environment_mismatch():
    current = {
        "schema_version": 1,
        "environment": {
            "python_implementation": "CPython", "python_version": "3.12.1",
            "platform_system": "Windows", "machine": "AMD64",
        },
        "cases": [{"name": "case", "median_seconds_per_call": 0.13}],
    }
    baseline = {
        "schema_version": 1,
        "environment": dict(current["environment"]),
        "cases": [{"name": "case", "median_seconds_per_call": 0.1}],
    }
    comparison = compare_benchmark_suites(current, baseline, max_slowdown_ratio=1.2)
    assert comparison["status"] == "FAIL"
    assert comparison["comparisons"][0]["status"] == "REGRESSION"

    current["environment"]["platform_system"] = "Linux"
    comparison = compare_benchmark_suites(current, baseline)
    assert comparison["status"] == "INCOMPARABLE"
    assert comparison["comparisons"][0]["status"] == "INCOMPARABLE_ENVIRONMENT"


def test_benchmark_comparison_marks_missing_baseline_case():
    current = {
        "schema_version": 1,
        "environment": {
            "python_implementation": "CPython", "python_version": "3.12.1",
            "platform_system": "Windows", "machine": "AMD64",
        },
        "cases": [{"name": "new-case", "median_seconds_per_call": 0.13}],
    }
    baseline = {"schema_version": 1, "environment": dict(current["environment"]), "cases": []}
    result = compare_benchmark_suites(current, baseline)
    assert result["status"] == "NO_BASELINE"
    assert result["comparisons"][0]["status"] == "NO_BASELINE"


def test_benchmark_report_writes_json_and_markdown(tmp_path):
    result = run_benchmark_suite(iterations=1, warmups=0, repeats=1)
    json_path, markdown_path = write_benchmark_report(result, tmp_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert len(payload["cases"]) == 10
    assert "not end-to-end eclipse timings" in markdown_path.read_text(encoding="utf-8")


def test_benchmark_report_rejects_path_traversal_stem(tmp_path):
    result = run_benchmark_suite(iterations=1, warmups=0, repeats=1)
    with pytest.raises(ValueError, match="simple filename"):
        write_benchmark_report(result, tmp_path, stem="../unsafe")


def test_profile_benchmark_workloads_writes_profiler_file(tmp_path):
    path = profile_benchmark_workloads(tmp_path / "profile.pstats", iterations=1)
    assert path.is_file()
    assert path.stat().st_size > 0


def test_benchmark_callable_rejects_empty_name_and_non_callable():
    with pytest.raises(ValueError, match="name"):
        benchmark_callable(" ", lambda: None)
    with pytest.raises(TypeError, match="callable"):
        benchmark_callable("not-callable", None)  # type: ignore[arg-type]


def test_benchmark_suite_rejects_invalid_tracking_and_counts():
    with pytest.raises(ValueError, match="track_memory"):
        run_benchmark_suite(track_memory=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="iterations"):
        run_benchmark_suite(iterations=0)


def test_benchmark_comparison_valid_case_and_invalid_baseline_values():
    environment = {
        "python_implementation": "CPython",
        "python_version": "3.12.10",
        "platform_system": "Windows",
        "machine": "AMD64",
    }
    current = {
        "schema_version": 1,
        "environment": dict(environment),
        "cases": [{"name": "case", "median_seconds_per_call": 0.105}],
    }
    baseline = {
        "schema_version": 1,
        "environment": dict(environment),
        "cases": [{"name": "case", "median_seconds_per_call": 0.1}],
    }
    comparison = compare_benchmark_suites(current, baseline, max_slowdown_ratio=1.1)
    assert comparison["status"] == "PASS"
    baseline["cases"][0]["median_seconds_per_call"] = float("nan")
    comparison = compare_benchmark_suites(current, baseline)
    assert comparison["status"] == "INCOMPARABLE"
    assert comparison["comparisons"][0]["status"] == "INCOMPARABLE_BASELINE"


def test_benchmark_comparison_validates_schema_and_threshold():
    with pytest.raises(ValueError, match="baseline"):
        compare_benchmark_suites({"schema_version": 1}, {"schema_version": 2})
    with pytest.raises(ValueError, match="current"):
        compare_benchmark_suites({"schema_version": 2}, {"schema_version": 1})
    valid = {"schema_version": 1, "environment": {}, "cases": []}
    with pytest.raises(ValueError, match="max_slowdown_ratio"):
        compare_benchmark_suites(valid, valid, max_slowdown_ratio=0.9)
    assert compare_benchmark_suites(valid, valid)["status"] == "NO_CASES"


def test_benchmark_report_includes_baseline_comparison(tmp_path):
    result = run_benchmark_suite(iterations=1, warmups=0, repeats=1)
    baseline = result.to_dict()
    comparison = compare_benchmark_suites(result, baseline)
    json_path, markdown_path = write_benchmark_report(
        result, tmp_path, comparison=comparison
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["baseline_comparison"]["status"] == "PASS"
    assert "Baseline comparison" in markdown_path.read_text(encoding="utf-8")


def test_benchmark_cli_writes_report_and_profile(tmp_path):
    from eclipsekit.performance import main

    exit_code = main([
        "--warmups", "0", "--repeats", "1", "--iterations", "1",
        "--output-dir", str(tmp_path), "--stem", "cli",
        "--profile-output", str(tmp_path / "cli.pstats"),
    ])
    assert exit_code == 0
    assert (tmp_path / "cli.json").is_file()
    assert (tmp_path / "cli.md").is_file()
    assert (tmp_path / "cli.pstats").is_file()
