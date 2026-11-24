import hashlib
from types import SimpleNamespace

from eclipsekit.earth_orientation import (
    EarthOrientationConfig,
    describe_earth_orientation_source,
    describe_time_scale,
)


def test_builtin_eop_provenance_is_scoped_to_skyfield_version():
    result = describe_earth_orientation_source(EarthOrientationConfig.builtin(), skyfield_version="1.55")
    assert result["status"] == "PASS"
    assert result["reproducibility_level"] == "SKYFIELD_VERSION_SCOPED"
    assert result["skyfield_version"] == "1.55"
    assert result["sha256"] is None


def test_iers_eop_provenance_hashes_exact_cache_file(tmp_path):
    table = tmp_path / "finals2000A.all"
    table.write_bytes(b"fixed synthetic IERS table\n")
    result = describe_earth_orientation_source(EarthOrientationConfig.iers(), cache_dir=tmp_path)
    assert result["status"] == "PASS"
    assert result["reproducibility_level"] == "CONTENT_HASHED_IERS_FILE"
    assert result["sha256"] == hashlib.sha256(table.read_bytes()).hexdigest()
    assert result["size_bytes"] == table.stat().st_size


def test_iers_eop_provenance_is_not_verified_without_cached_table(tmp_path):
    result = describe_earth_orientation_source(EarthOrientationConfig.iers(), cache_dir=tmp_path)
    assert result["status"] == "UNVERIFIED"
    assert result["sha256"] is None


def test_fixed_delta_t_provenance_records_exact_explicit_assumption():
    result = describe_earth_orientation_source(EarthOrientationConfig.fixed(69.2))
    assert result["status"] == "PASS_WITH_EXPLICIT_ASSUMPTION"
    assert result["fixed_delta_t_seconds"] == 69.2
    assert result["reproducibility_level"] == "EXPLICIT_NUMERIC_ASSUMPTION"


def test_explicit_timescale_provenance_is_caller_managed():
    result = describe_earth_orientation_source(
        EarthOrientationConfig.builtin(), cache_dir="cache", explicit_timescale=True
    )
    assert result["status"] == "UNVERIFIED"
    assert result["reproducibility_level"] == "CALLER_MANAGED"


def test_time_scale_diagnostics_includes_provenance_warning():
    fake_time = SimpleNamespace(
        delta_t=69.0,
        dut1=0.1,
        utc_iso=lambda: "2017-08-21T17:20:00Z",
    )
    provenance = {"status": "UNVERIFIED", "mode": "iers"}
    result = describe_time_scale(fake_time, "iers", provenance=provenance)
    assert result["provenance"] == provenance
    assert "provenance_warning" in result


def test_eop_audit_cli_writes_report_with_synthetic_skyfield(tmp_path, monkeypatch):
    import json
    import sys
    from types import ModuleType
    from pathlib import Path
    from eclipsekit.earth_orientation import main

    class FakeTime:
        delta_t = 69.0
        dut1 = 0.1

        @staticmethod
        def utc_iso():
            return "2017-08-21T17:20:00Z"

    class FakeTimescale:
        @staticmethod
        def utc(*args):
            return FakeTime()

    class FakeLoader:
        def __init__(self, directory, verbose=False):
            self.directory = Path(directory)

        def timescale(self, **kwargs):
            if kwargs == {"builtin": False}:
                (self.directory / "finals2000A.all").write_bytes(b"mock IERS file")
            return FakeTimescale()

    skyfield = ModuleType("skyfield")
    skyfield_api = ModuleType("skyfield.api")
    skyfield_api.Loader = FakeLoader
    monkeypatch.setitem(sys.modules, "skyfield", skyfield)
    monkeypatch.setitem(sys.modules, "skyfield.api", skyfield_api)

    output = tmp_path / "reports"
    result = main([
        "--mode", "iers", "--cache-dir", str(tmp_path / "cache"),
        "--json-out", str(output / "eop.json"),
        "--markdown-out", str(output / "eop.md"),
    ])
    assert result == 0
    report = json.loads((output / "eop.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["provenance"]["sha256"]
    assert "SHA-256" in (output / "eop.md").read_text(encoding="utf-8")


def test_iers_eop_provenance_hashes_active_legacy_skyfield_table_set(tmp_path):
    legacy_contents = {
        "deltat.data": b"legacy delta-t table\n",
        "deltat.preds": b"legacy delta-t predictions\n",
        "Leap_Second.dat": b"legacy leap-second table\n",
    }
    expected_hashes = {}
    for name, contents in legacy_contents.items():
        path = tmp_path / name
        path.write_bytes(contents)
        expected_hashes[name] = hashlib.sha256(contents).hexdigest()

    result = describe_earth_orientation_source(EarthOrientationConfig.iers(), cache_dir=tmp_path)

    assert result["status"] == "PASS"
    assert result["reproducibility_level"] == "CONTENT_HASHED_LEGACY_SKYFIELD_TABLES"
    assert {item["name"]: item["sha256"] for item in result["data_files"]} == expected_hashes
    assert result["data_file"] is None
    assert result["size_bytes"] == sum(map(len, legacy_contents.values()))
    assert len(result["sha256"]) == 64
