from __future__ import annotations

import json
from pathlib import Path
import zipfile

from eclipsekit.certification import (
    audit_api_manifest,
    audit_dem_control_point_report,
    audit_peer_review_record,
    audit_reference_validation_report,
    audit_unified_validation_report,
    audit_wheel,
    _run_command,
    run_certification_audit,
    run_software_checks,
    source_tree_fingerprint,
    write_certification_report,
)
from eclipsekit import __version__


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_api_manifest_matches_frozen_v1_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    result = audit_api_manifest(root / "docs" / "API_MANIFEST_V1.json")
    assert result["status"] == "PASS"
    assert result["api_status"] == "stabilization-candidate"
    assert result["export_count"] > 100


def test_api_manifest_mismatch_fails(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / "docs" / "API_MANIFEST_V1.json").read_text(encoding="utf-8"))
    payload["exports"] = payload["exports"][:-1]
    payload["export_count"] = len(payload["exports"])
    path = _write_json(tmp_path / "api.json", payload)
    result = audit_api_manifest(path)
    assert result["status"] == "FAIL"
    assert "export list mismatch" in result["details"]


def test_unified_report_is_not_run_when_missing() -> None:
    result = audit_unified_validation_report(None)
    assert result["status"] == "NOT_RUN"
    assert result["required"] is True


def test_unified_report_requires_every_component_to_pass(tmp_path: Path) -> None:
    payload = {
        "schema": "eclipsekit.phase8_4.unified_validation.v1",
        "status": "PASS",
        "components": [{"name": "one", "status": "PASS"}, {"name": "two", "status": "FAIL"}],
    }
    path = _write_json(tmp_path / "unified.json", payload)
    result = audit_unified_validation_report(path)
    assert result["status"] == "FAIL"


def test_unified_report_accepts_clean_components(tmp_path: Path) -> None:
    payload = {
        "schema": "eclipsekit.phase8_4.unified_validation.v1",
        "status": "PASS",
        "components": [{"name": "one", "status": "PASS"}],
    }
    path = _write_json(tmp_path / "unified.json", payload)
    assert audit_unified_validation_report(path)["status"] == "PASS"


def _reference_run_payload() -> dict:
    return {
        "schema_version": 1,
        "report_schema_version": 2,
        "status": "PASS",
        "local_cases": [{"case_id": "local-1", "status": "PASS"}],
        "global_maximum_cases": [{
            "case_id": "hybrid-1", "status": "PASS",
            "reference_eclipse_type": "hybrid",
        }],
        "global_path_cases": [{"case_id": "path-1", "status": "PASS"}],
        "besselian_reference": {"status": "PASS"},
        "summary": {"failed": 0, "errors": 0, "not_run_groups": []},
        "environment": {"kernel": "de440s", "time_scale_mode": "builtin"},
        "inputs": {
            "reference_asset_sha256": {
                "reference_cases.json": "a" * 64,
                "path_reference_manifest.json": "b" * 64,
                "besselian_1999_reference.json": "c" * 64,
            },
        },
    }


def test_full_reference_validation_report_requires_all_manifest_cases(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "reference-validation.json", _reference_run_payload())
    result = audit_reference_validation_report(
        path, expected_case_ids=["local-1", "hybrid-1", "path-1"],
        expected_input_hashes={
            "reference_cases.json": "a" * 64,
            "path_reference_manifest.json": "b" * 64,
            "besselian_1999_reference.json": "c" * 64,
        },
    )
    assert result["status"] == "PASS"
    assert result["hybrid_case_ids"] == ["hybrid-1"]


def test_full_reference_validation_report_rejects_missing_or_failed_hybrid(tmp_path: Path) -> None:
    payload = _reference_run_payload()
    payload["global_maximum_cases"][0]["status"] = "FAIL"
    path = _write_json(tmp_path / "reference-validation.json", payload)
    result = audit_reference_validation_report(
        path, expected_case_ids=["local-1", "hybrid-1", "path-1", "missing-case"],
    )
    assert result["status"] == "FAIL"
    assert "global_maximum case 'hybrid-1' status is 'FAIL'" in result["details"]
    assert "missing manifest cases" in result["details"]


def test_full_reference_validation_report_rejects_stale_manifest_fingerprints(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "reference-validation.json", _reference_run_payload())
    result = audit_reference_validation_report(
        path, expected_case_ids=["local-1", "hybrid-1", "path-1"],
        expected_input_hashes={"reference_cases.json": "f" * 64},
    )
    assert result["status"] == "FAIL"
    assert "fingerprint 'reference_cases.json'" in result["details"]


def test_full_reference_validation_report_is_not_run_when_missing() -> None:
    result = audit_reference_validation_report(None)
    assert result["status"] == "NOT_RUN"
    assert result["required"] is True


def _control_point_payload(*, independent: bool = True) -> dict:
    return {
        "status": "PASS",
        "dataset_id": "independent-lunar-check-01",
        "independent_of_test_dem": independent,
        "independence_statement": "Measurements withheld from the DEM production workflow.",
        "control_point_count": 10,
        "counts": {"PASS": 10, "FAIL": 0, "OUT_OF_COVERAGE": 0, "ERROR": 0},
        "control_source_sha256": "a" * 64,
        "control_source": {"uri": "https://example.org/dataset"},
        "metrics": {"evaluated_points": 10, "root_mean_square_error_m": 2.1},
    }


def test_control_point_report_requires_declared_independence(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "control.json", _control_point_payload(independent=False))
    result = audit_dem_control_point_report(path, minimum_points=10)
    assert result["status"] == "FAIL"
    assert "not declared independent" in result["details"]


def test_control_point_report_requires_minimum_count_and_hash(tmp_path: Path) -> None:
    payload = _control_point_payload()
    payload["control_point_count"] = 3
    payload["counts"]["PASS"] = 3
    payload["control_source_sha256"] = "not-available"
    path = _write_json(tmp_path / "control.json", payload)
    result = audit_dem_control_point_report(path, minimum_points=10)
    assert result["status"] == "FAIL"
    assert "control_point_count must be >= 10" in result["details"]
    assert "SHA-256" in result["details"]


def test_control_point_report_passes_declared_independent_valid_evidence(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "control.json", _control_point_payload())
    result = audit_dem_control_point_report(path, minimum_points=10)
    assert result["status"] == "PASS"
    assert result["control_point_count"] == 10


def test_peer_review_requires_exact_source_fingerprint(tmp_path: Path) -> None:
    digest = "b" * 64
    payload = {
        "schema_version": 1,
        "reviewer": "Independent reviewer",
        "reviewer_is_independent": True,
        "review_date_utc": "2026-11-23T12:00:00Z",
        "review_outcome": "accepted",
        "source_tree_sha256": digest,
        "scope": ["solar eclipse algorithms", "lunar DEM validation"],
        "findings": [{"id": "R-1", "status": "resolved"}],
    }
    path = _write_json(tmp_path / "review.json", payload)
    assert audit_peer_review_record(path, expected_source_digest=digest)["status"] == "PASS"
    mismatch = audit_peer_review_record(path, expected_source_digest="c" * 64)
    assert mismatch["status"] == "FAIL"
    assert "does not match" in mismatch["details"]


def test_peer_review_requires_utc_and_independent_reviewer(tmp_path: Path) -> None:
    payload = {
        "schema_version": 1,
        "reviewer": "Reviewer",
        "reviewer_is_independent": False,
        "review_date_utc": "2026-11-23T12:00:00",
        "review_outcome": "accepted",
        "source_tree_sha256": "d" * 64,
        "scope": ["eclipse engine"],
        "findings": [],
    }
    path = _write_json(tmp_path / "review.json", payload)
    result = audit_peer_review_record(path, expected_source_digest="d" * 64)
    assert result["status"] == "FAIL"
    assert "reviewer_is_independent" in result["details"]
    assert "explicit UTC offset" in result["details"]


def test_source_fingerprint_excludes_local_data_and_tracks_source(tmp_path: Path) -> None:
    (tmp_path / "src" / "eclipsekit").mkdir(parents=True)
    (tmp_path / "data").mkdir()
    (tmp_path / "pyproject.toml").write_text("project = true", encoding="utf-8")
    source = tmp_path / "src" / "eclipsekit" / "module.py"
    source.write_text("VALUE = 1", encoding="utf-8")
    local = tmp_path / "data" / "large-dem.img"
    local.write_bytes(b"first")

    first = source_tree_fingerprint(tmp_path)["digest"]
    local.write_bytes(b"different-local-data")
    second = source_tree_fingerprint(tmp_path)["digest"]
    assert first == second
    source.write_text("VALUE = 2", encoding="utf-8")
    third = source_tree_fingerprint(tmp_path)["digest"]
    assert third != second


def test_wheel_audit_checks_pep561_version_and_no_local_payload(tmp_path: Path) -> None:
    wheel = tmp_path / "eclipsekit-0.1.0-py3-none-any.whl"
    metadata = (
        "Metadata-Version: 2.1\nName: eclipsekit\nVersion: 0.1.0\n"
        "Requires-Python: >=3.10\n\n"
    )
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("eclipsekit/__init__.py", "__version__ = '0.1.0'\n")
        archive.writestr("eclipsekit/py.typed", "")
        archive.writestr("eclipsekit-0.1.0.dist-info/METADATA", metadata)
    result = audit_wheel(wheel, expected_version="0.1.0")
    assert result["status"] == "PASS"
    assert result["sha256"]


def test_wheel_audit_rejects_leaked_data(tmp_path: Path) -> None:
    wheel = tmp_path / "eclipsekit-0.1.0-py3-none-any.whl"
    metadata = "Metadata-Version: 2.1\nName: eclipsekit\nVersion: 0.1.0\n\n"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("eclipsekit/__init__.py", "")
        archive.writestr("eclipsekit/py.typed", "")
        archive.writestr("data/private.img", b"not allowed")
        archive.writestr("eclipsekit-0.1.0.dist-info/METADATA", metadata)
    result = audit_wheel(wheel, expected_version="0.1.0")
    assert result["status"] == "FAIL"
    assert "local-only" in result["details"]


def test_phase15_audit_creates_report_and_does_not_claim_certification(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    report = run_certification_audit(
        source_root=root,
        validation_dir=root / "data" / "validation",
        output_dir=tmp_path / "phase15",
        run_software=False,
    )
    assert report["status"] == "NOT_CERTIFIED"
    assert report["package_version"] == __version__
    assert report["target_release_version"] == "1.0.0"
    assert any(item["name"] == "reference_matrix_and_fingerprints" and item["status"] == "PASS" for item in report["gates"])
    assert any(item["name"] == "independent_lunar_dem_control_points" and item["status"] == "NOT_RUN" for item in report["gates"])
    assert any(item["name"] == "live_published_reference_regressions" and item["status"] == "NOT_RUN" for item in report["gates"])
    assert any(item["name"] == "reference_eclipse_type_coverage" and item["status"] == "PASS" for item in report["gates"])
    json_path, markdown_path = write_certification_report(report, tmp_path / "phase15")
    assert json_path.is_file() and markdown_path.is_file()
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["status"] == "NOT_CERTIFIED"


def test_alpha_profile_makes_only_four_scientific_1_0_gates_non_blocking(
    tmp_path: Path, monkeypatch,
) -> None:
    from eclipsekit import certification

    root = Path(__file__).resolve().parents[1]

    def passing_gate(name: str) -> dict:
        return {"name": name, "status": "PASS", "required": True, "details": "test pass"}

    monkeypatch.setattr(
        certification,
        "run_software_checks",
        lambda *args, **kwargs: ([
            passing_gate(name) for name in (
                "ruff", "compileall", "pytest", "pip_check", "wheel_build", "wheel_contents", "pip_audit"
            )
        ], None),
    )
    monkeypatch.setattr(certification, "audit_api_manifest", lambda path: passing_gate("api_manifest"))
    monkeypatch.setattr(
        certification,
        "audit_reference_matrix",
        lambda path: {
            "status": "PASS",
            "summary": {"observed_eclipse_types": ["total", "annular", "partial", "hybrid"]},
            "cases": [],
            "assets": [],
        },
    )
    monkeypatch.setattr(
        certification,
        "audit_reference_validation_report",
        lambda *args, **kwargs: passing_gate("live_published_reference_regressions"),
    )
    monkeypatch.setattr(
        certification,
        "run_scientific_regression_suite",
        lambda **kwargs: {
            "checks": [
                {"name": "deterministic_anchor", "status": "PASS"},
                {"name": "nasa_1999_besselian_reference", "status": "PASS"},
                {"name": "real_lunar_dem_structural_validation", "status": "PASS"},
            ]
        },
    )
    monkeypatch.setattr(
        certification,
        "audit_unified_validation_report",
        lambda path: passing_gate("phase8_4_unified_validation"),
    )

    report = run_certification_audit(
        source_root=root,
        validation_dir=root / "data" / "validation",
        output_dir=tmp_path / "alpha-profile",
        release_profile="alpha",
    )

    assert report["status"] == "ALPHA_RELEASE_READY"
    assert report["alpha_release_readiness"] == "PASS"
    assert report["scientific_certification_status"] == "NOT_CERTIFIED"
    expected_non_blocking = {
        "public_api_maturity",
        "independent_lunar_dem_control_points",
        "independent_scientific_peer_review",
        "distribution_version_1_0_0",
    }
    observed = {item["name"]: item for item in report["gates"]}
    for name in expected_non_blocking:
        assert observed[name]["required"] is False
        assert observed[name]["required_for_scientific_certification"] is True
        assert observed[name]["required_for_alpha_release"] is False
    assert observed["public_api_maturity"]["status"] == "PARTIAL"
    assert observed["independent_lunar_dem_control_points"]["status"] == "NOT_RUN"
    assert observed["independent_scientific_peer_review"]["status"] == "NOT_RUN"
    assert observed["distribution_version_1_0_0"]["status"] == "NOT_RUN"


def test_unknown_release_profile_is_rejected(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    try:
        run_certification_audit(
            source_root=root,
            validation_dir=root / "data" / "validation",
            output_dir=tmp_path / "invalid-profile",
            release_profile="skip-everything",
        )
    except ValueError as exc:
        assert "release_profile" in str(exc)
    else:  # pragma: no cover - defensive contract assertion
        raise AssertionError("invalid release profile should be rejected")


def test_reference_manifest_includes_published_partial_eclipse_case() -> None:
    from eclipsekit.validation import load_reference_cases

    root = Path(__file__).resolve().parents[1]
    local, _ = load_reference_cases(root / "data" / "validation" / "reference_cases.json")
    partial = [case for case in local if case.expected_eclipse_type == "partial"]
    assert len(partial) == 1
    assert partial[0].case_id == "solar-2022-10-25-london-partial"
    assert set(partial[0].expected_contacts_utc) == {"C1", "C4"}
    assert partial[0].source_precision_seconds == 60.0


def test_pip_audit_skips_local_editable_project_and_separates_stderr(
    tmp_path: Path, monkeypatch,
) -> None:
    from eclipsekit import certification

    captured: dict[str, list[str]] = {}
    stderr_separation: dict[str, bool] = {}

    def fake_run_command(
        name, command, *, cwd, log_path, timeout_seconds=300, separate_stderr=False,
    ):
        captured[name] = list(command)
        stderr_separation[name] = separate_stderr
        return {"name": name, "status": "NOT_RUN", "required": True}

    monkeypatch.setattr(certification, "_run_command", fake_run_command)
    run_software_checks(
        tmp_path, tmp_path / "software", run_security_audit=True,
    )

    assert "--skip-editable" in captured["pip_audit"]
    assert "--format" in captured["pip_audit"]
    assert "json" in captured["pip_audit"]
    assert stderr_separation["pip_audit"] is True


def test_run_command_keeps_machine_json_separate_from_stderr(tmp_path: Path) -> None:
    import sys

    log_path = tmp_path / "pip_audit.json"
    result = _run_command(
        "pip_audit",
        [
            sys.executable, "-c",
            "import sys; print('{\"dependencies\": []}'); "
            "print('No known vulnerabilities found', file=sys.stderr)",
        ],
        cwd=tmp_path,
        log_path=log_path,
        separate_stderr=True,
    )

    assert result["status"] == "PASS"
    assert json.loads(log_path.read_text(encoding="utf-8")) == {"dependencies": []}
    stderr_path = tmp_path / "pip_audit.stderr.json"
    assert stderr_path.is_file()
    assert "No known vulnerabilities found" in stderr_path.read_text(encoding="utf-8")
