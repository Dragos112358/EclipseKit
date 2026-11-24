import json
from pathlib import Path

import pytest

from eclipsekit.reference_matrix import audit_reference_matrix, main


def _make_validation_dir(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "reference_cases.json").write_text(json.dumps({
        "schema_version": 1,
        "local_cases": [{
            "case_id": "local-total", "name": "Synthetic local total", "event_time_utc": "2026-08-12T18:00:00Z",
            "latitude": 40.0, "longitude": -3.0, "elevation_m": 0.0,
            "expected_contacts_utc": {"C1": "2026-08-12T17:00:00Z"},
            "contact_tolerance_seconds": 2.0, "source_url": "https://example.org/local",
            "source_precision_seconds": 1.0, "expected_eclipse_type": "total",
        }],
        "global_maximum_cases": [{
            "case_id": "global-max", "name": "Synthetic maximum", "event_time_utc": "2026-08-12T18:00:00Z",
            "expected_maximum_utc": "2026-08-12T18:00:00Z", "tolerance_seconds": 2.0,
            "source_url": "https://example.org/global",
            "expected_eclipse_type": "hybrid",
        }],
    }), encoding="utf-8")
    (root / "path.csv").write_text(
        "time_utc,latitude_deg,longitude_deg\n2026-08-12T18:00:00Z,1,2\n",
        encoding="utf-8",
    )
    (root / "path_reference_manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "path_cases": [{
            "case_id": "path-1", "name": "Synthetic path", "event_time_utc": "2026-08-12T18:00:00Z",
            "reference_file": "path.csv", "search_radius_hours": 1.0, "tolerance_km": 5.0,
            "source_url": "https://example.org/path", "source_time_step_seconds": 60.0,
            "source_coordinate_resolution_arcmin": 0.1,
        }],
    }), encoding="utf-8")
    (root / "elements.json").write_text(json.dumps({
        "epoch_tt_jd": 2450000.0,
        "coefficients": {name: [value] for name, value in {
            "x": 0.0, "y": 0.0, "d": 0.0, "mu": 0.0, "l1": 1.0, "l2": -0.01,
        }.items()},
        "tan_f1": 0.0047, "tan_f2": 0.0046,
        "validity_start_hours": -2.0, "validity_end_hours": 2.0,
        "mu_convention": "ephemeris", "source": "synthetic fixture", "ephemeris": "synthetic",
    }), encoding="utf-8")
    (root / "besselian_1999_reference.json").write_text(json.dumps({
        "schema_version": 1, "case_id": "besselian-1", "name": "Synthetic Besselian descriptor",
        "source_url": "https://example.org/besselian", "elements_file": "elements.json",
        "expected_eclipse_type": "total",
    }), encoding="utf-8")
    (root / "global_corridor_2017_nasa.csv").write_text(
        "time_utc,north_latitude_deg,north_longitude_deg,south_latitude_deg,south_longitude_deg,"
        "center_latitude_deg,center_longitude_deg,path_width_km,central_duration_seconds\n"
        "2017-08-21T17:00:00Z,40,-100,39,-100,39.5,-100,111,120\n",
        encoding="utf-8",
    )
    return root


def test_reference_matrix_audits_schemas_assets_and_fingerprints(tmp_path):
    root = _make_validation_dir(tmp_path / "validation")
    report = audit_reference_matrix(root)
    assert report["status"] == "PASS"
    assert report["summary"]["groups"]["local_circumstances"] == 1
    assert report["summary"]["groups"]["global_path"] == 1
    assert report["summary"]["asset_count"] == 6
    assert report["summary"]["observed_eclipse_types"] == ["hybrid", "total"]
    assert all(len(asset["sha256"]) == 64 for asset in report["assets"])
    assert {asset["path"] for asset in report["assets"]} == {
        "reference_cases.json", "path_reference_manifest.json", "path.csv",
        "besselian_1999_reference.json", "elements.json", "global_corridor_2017_nasa.csv",
    }


def test_reference_matrix_rejects_path_manifest_escape(tmp_path):
    root = _make_validation_dir(tmp_path / "validation")
    manifest = json.loads((root / "path_reference_manifest.json").read_text(encoding="utf-8"))
    manifest["path_cases"][0]["reference_file"] = "../outside.csv"
    (root / "path_reference_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="inside the manifest directory"):
        audit_reference_matrix(root)


def test_reference_matrix_rejects_besselian_elements_escape(tmp_path):
    root = _make_validation_dir(tmp_path / "validation")
    descriptor = json.loads((root / "besselian_1999_reference.json").read_text(encoding="utf-8"))
    descriptor["elements_file"] = "../outside.json"
    (root / "besselian_1999_reference.json").write_text(json.dumps(descriptor), encoding="utf-8")
    with pytest.raises(ValueError, match="inside validation directory"):
        audit_reference_matrix(root)


def test_reference_matrix_missing_corridor_asset_fails(tmp_path):
    root = _make_validation_dir(tmp_path / "validation")
    (root / "global_corridor_2017_nasa.csv").unlink()
    with pytest.raises(FileNotFoundError):
        audit_reference_matrix(root)


def test_reference_matrix_cli_writes_json_and_markdown(tmp_path):
    root = _make_validation_dir(tmp_path / "validation")
    output = tmp_path / "reports"
    assert main(["--validation-dir", str(root), "--output-dir", str(output)]) == 0
    payload = json.loads((output / "reference-matrix.json").read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert "SHA-256" in (output / "reference-matrix.md").read_text(encoding="utf-8")
