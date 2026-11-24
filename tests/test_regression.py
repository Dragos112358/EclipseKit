from __future__ import annotations

import json
from pathlib import Path

from eclipsekit.regression import (
    regression_report_to_markdown,
    run_scientific_regression_suite,
    write_regression_report,
)


def test_scientific_regression_suite_passes_deterministic_and_nasa_references():
    root = Path(__file__).resolve().parents[1]
    report = run_scientific_regression_suite(
        reference_file=root / "data" / "validation" / "besselian_1999_reference.json"
    )
    assert report["status"] == "PARTIAL"
    checks = {item["name"]: item for item in report["checks"]}
    assert checks["nasa_1999_besselian_reference"]["status"] == "PASS"
    assert checks["wgs84_equatorial_one_degree"]["status"] == "PASS"
    assert checks["wgs84_antimeridian_two_degrees"]["status"] == "PASS"
    assert checks["wgs84_ecef_geodetic_round_trip"]["status"] == "PASS"
    assert checks["brent_root_cubic_reference"]["status"] == "PASS"
    assert checks["root_solver_tangent_contact_case"]["status"] == "PASS"
    assert checks["uncertainty_correlated_linear_covariance"]["status"] == "PASS"
    assert checks["monte_carlo_seed_reproducibility"]["status"] == "PASS"
    assert checks["real_lunar_dem_structural_validation"]["status"] == "NOT_RUN"


def test_regression_suite_reports_missing_reference_as_error(tmp_path):
    report = run_scientific_regression_suite(reference_file=tmp_path / "missing.json")
    assert report["status"] == "FAIL"
    check = next(item for item in report["checks"] if item["name"] == "nasa_1999_besselian_reference")
    assert check["status"] == "ERROR"


def test_regression_markdown_contains_status_and_limitations():
    report = run_scientific_regression_suite()
    markdown = regression_report_to_markdown(report)
    assert "EclipseKit Phase 7.7 scientific regression" in markdown
    assert "Limitations" in markdown
    assert "live_de440s_path_and_shadow_corridor_regressions" in markdown


def test_regression_report_writes_strict_json_and_markdown(tmp_path):
    report = run_scientific_regression_suite()
    json_path, markdown_path = write_regression_report(report, tmp_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["summary"]["passed"] >= 7
    assert "NOT_RUN" in markdown_path.read_text(encoding="utf-8")


def test_regression_report_rejects_path_traversal_stem(tmp_path):
    report = run_scientific_regression_suite()
    try:
        write_regression_report(report, tmp_path, stem="../unsafe")
    except ValueError as exc:
        assert "simple filename" in str(exc)
    else:
        raise AssertionError("unsafe report stem was accepted")


def test_regression_suite_marks_missing_default_reference_not_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report = run_scientific_regression_suite()
    check = next(item for item in report["checks"] if item["name"] == "nasa_1999_besselian_reference")
    assert check["status"] == "NOT_RUN"
    assert report["status"] == "PARTIAL"


def test_regression_suite_requires_dem_image_and_label_together():
    report = run_scientific_regression_suite(dem_image="one.img")
    check = next(item for item in report["checks"] if item["name"] == "real_lunar_dem_structural_validation")
    assert check["status"] == "ERROR"
    assert report["status"] == "FAIL"


def test_regression_cli_writes_report_and_returns_partial_success(tmp_path):
    from eclipsekit.regression import main

    root = Path(__file__).resolve().parents[1]
    exit_code = main([
        "--reference-file", str(root / "data" / "validation" / "besselian_1999_reference.json"),
        "--output-dir", str(tmp_path),
    ])
    assert exit_code == 0
    assert (tmp_path / "scientific-regression.json").is_file()
    assert (tmp_path / "scientific-regression.md").is_file()
