from __future__ import annotations

from dataclasses import dataclass
import json
from types import SimpleNamespace

import pytest

from eclipsekit.lunar_dem_mosaic import LunarDEMMosaicModel
from eclipsekit.lunar_dem_mosaic_validation import (
    audit_lunar_dem_mosaic_overlaps,
    main,
    write_lunar_dem_mosaic_overlap_report,
)


@dataclass
class ProductInfo:
    product_id: str
    coordinate_system_name: str = "MOON_PA_DE440"
    vertical_datum: str = "sphere-1737400"
    reference_radius_m: float = 1_737_400.0
    south_latitude_deg: float = -10.0
    north_latitude_deg: float = 10.0
    west_longitude_deg: float = -10.0
    east_longitude_deg: float = 10.0
    resolution_m: float = 100.0

    def to_dict(self):
        return {
            "product_id": self.product_id,
            "coordinate_system_name": self.coordinate_system_name,
            "vertical_datum": self.vertical_datum,
            "reference_radius_m": self.reference_radius_m,
        }


class FakeDEM:
    def __init__(self, product_id: str, function, info: ProductInfo | None = None):
        self.product_info = info or ProductInfo(product_id)
        self.metadata = SimpleNamespace(
            name=product_id,
            vertical_datum=self.product_info.vertical_datum,
            resolution_m=self.product_info.resolution_m,
        )
        self.function = function
        self.calls: list[tuple[float, float]] = []
        self.closed = False

    def predict_altitude_m(self, latitude_deg, longitude_deg):
        self.calls.append((latitude_deg, longitude_deg))
        return self.function(latitude_deg, longitude_deg)

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback
        self.close()


def make_mosaic(first: FakeDEM, second: FakeDEM):
    return LunarDEMMosaicModel([first, second], source_names=["A", "B"])


def test_overlap_audit_reports_metrics_for_consistent_products():
    first = FakeDEM("first", lambda latitude, longitude: 100.0 + latitude + longitude)
    second = FakeDEM("second", lambda latitude, longitude: 102.0 + latitude + longitude)
    report = audit_lunar_dem_mosaic_overlaps(
        make_mosaic(first, second), samples_per_axis=3, absolute_tolerance_m=2.1
    )

    assert report.status == "PASS"
    assert report.compared_pairs == report.passed_pairs == 1
    pair = report.pair_results[0]
    assert pair.samples_requested == pair.valid_samples == 9
    assert pair.bias_m == pytest.approx(2.0)
    assert pair.mae_m == pytest.approx(2.0)
    assert pair.rmse_m == pytest.approx(2.0)
    assert pair.maximum_absolute_difference_m == pytest.approx(2.0)
    assert first.calls and second.calls


def test_overlap_audit_fails_when_vertical_difference_exceeds_tolerance():
    report = audit_lunar_dem_mosaic_overlaps(
        make_mosaic(
            FakeDEM("first", lambda latitude, longitude: 0.0),
            FakeDEM("second", lambda latitude, longitude: 150.0),
        ),
        samples_per_axis=2,
        absolute_tolerance_m=100.0,
    )

    assert report.status == "FAIL"
    assert report.failed_pairs == 1
    assert report.pair_results[0].failed_samples == 4
    assert report.pair_results[0].maximum_absolute_difference_m == 150.0


def test_non_overlapping_products_are_not_comparable_not_a_failure():
    west = FakeDEM(
        "west", lambda latitude, longitude: 1.0,
        ProductInfo("west", west_longitude_deg=-40.0, east_longitude_deg=-20.0),
    )
    east = FakeDEM(
        "east", lambda latitude, longitude: 1.0,
        ProductInfo("east", west_longitude_deg=20.0, east_longitude_deg=40.0),
    )
    report = audit_lunar_dem_mosaic_overlaps(make_mosaic(west, east), samples_per_axis=3)

    assert report.status == "NOT_COMPARABLE"
    assert report.compared_pairs == 0
    assert report.no_overlap_pairs == 1
    assert report.pair_results[0].status == "NO_OVERLAP"
    assert west.calls == east.calls == []


def test_overlap_audit_handles_antimeridian_crossing_products():
    first = FakeDEM(
        "first", lambda latitude, longitude: 25.0,
        ProductInfo("first", west_longitude_deg=170.0, east_longitude_deg=190.0),
    )
    second = FakeDEM(
        "second", lambda latitude, longitude: 25.0,
        ProductInfo("second", west_longitude_deg=-175.0, east_longitude_deg=-160.0),
    )
    report = audit_lunar_dem_mosaic_overlaps(make_mosaic(first, second), samples_per_axis=3)

    assert report.status == "PASS"
    assert report.pair_results[0].samples_requested == 9
    assert all(-175.0 <= longitude <= -170.0 for _, longitude in first.calls)
    assert all(-175.0 <= longitude <= -170.0 for _, longitude in second.calls)


def test_overlap_audit_records_reader_errors_without_fallback_or_silent_pass():
    def broken(latitude, longitude):
        raise ValueError("synthetic NoData sample")

    first = FakeDEM("first", broken)
    second = FakeDEM("second", lambda latitude, longitude: 10.0)
    report = audit_lunar_dem_mosaic_overlaps(make_mosaic(first, second), samples_per_axis=2)

    assert report.status == "ERROR"
    pair = report.pair_results[0]
    assert pair.error_samples == 4
    assert pair.valid_samples == 0
    assert all(sample.status == "ERROR" for sample in pair.samples)
    assert all("synthetic NoData" in sample.error for sample in pair.samples)


def test_reader_error_preserves_the_value_returned_by_the_other_source():
    def broken(latitude, longitude):
        raise ValueError("synthetic NoData sample")

    first = FakeDEM("first", lambda latitude, longitude: 12.0)
    second = FakeDEM("second", broken)
    report = audit_lunar_dem_mosaic_overlaps(make_mosaic(first, second), samples_per_axis=2)

    assert report.status == "ERROR"
    sample = report.pair_results[0].samples[0]
    assert sample.altitude_a_m == 12.0
    assert sample.altitude_b_m is None
    assert sample.status == "ERROR"
    assert "B: ValueError" in sample.error


def test_global_source_coverage_intersects_local_coverage():
    global_source = FakeDEM(
        "global", lambda latitude, longitude: 3.0,
        ProductInfo("global", west_longitude_deg=0.0, east_longitude_deg=360.0),
    )
    local_source = FakeDEM(
        "local", lambda latitude, longitude: 3.0,
        ProductInfo("local", west_longitude_deg=25.0, east_longitude_deg=45.0),
    )
    report = audit_lunar_dem_mosaic_overlaps(
        make_mosaic(global_source, local_source), samples_per_axis=3
    )

    assert report.status == "PASS"
    assert report.pair_results[0].samples_requested == 9
    assert report.pair_results[0].overlap_regions[0]["west_longitude_deg"] == 25.0
    assert report.pair_results[0].overlap_regions[0]["east_longitude_deg"] == 45.0
    assert all(25.0 <= lon <= 45.0 for _, lon in global_source.calls)


def test_mixed_no_overlap_and_valid_overlap_only_counts_comparable_pairs():
    a = FakeDEM("a", lambda latitude, longitude: 1.0)
    b = FakeDEM("b", lambda latitude, longitude: 1.0)
    c = FakeDEM(
        "c", lambda latitude, longitude: 1.0,
        ProductInfo("c", west_longitude_deg=120.0, east_longitude_deg=140.0),
    )
    model = LunarDEMMosaicModel([a, b, c], source_names=["A", "B", "C"])
    report = audit_lunar_dem_mosaic_overlaps(model, samples_per_axis=2)

    assert report.status == "PASS"
    assert report.compared_pairs == 1
    assert report.passed_pairs == 1
    assert report.no_overlap_pairs == 2


def test_antimeridian_overlap_is_sampled_on_one_continuous_longitude_branch():
    first = FakeDEM(
        "first", lambda latitude, longitude: 1.0,
        ProductInfo("first", west_longitude_deg=350.0, east_longitude_deg=370.0),
    )
    second = FakeDEM(
        "second", lambda latitude, longitude: 1.0,
        ProductInfo("second", west_longitude_deg=-5.0, east_longitude_deg=5.0),
    )
    report = audit_lunar_dem_mosaic_overlaps(make_mosaic(first, second), samples_per_axis=3)

    assert report.status == "PASS"
    assert report.pair_results[0].samples_requested == 9
    assert len({(round(lat, 9), round(lon, 9)) for lat, lon in first.calls}) == 9


def test_audit_rejects_invalid_sample_grid_and_tolerance():
    model = make_mosaic(
        FakeDEM("first", lambda latitude, longitude: 1.0),
        FakeDEM("second", lambda latitude, longitude: 1.0),
    )
    with pytest.raises(TypeError, match="integer"):
        audit_lunar_dem_mosaic_overlaps(model, samples_per_axis=True)
    with pytest.raises(ValueError, match="between 2 and 101"):
        audit_lunar_dem_mosaic_overlaps(model, samples_per_axis=1)
    with pytest.raises(ValueError, match="finite and positive"):
        audit_lunar_dem_mosaic_overlaps(model, absolute_tolerance_m=float("nan"))
    with pytest.raises(TypeError, match="numeric value"):
        audit_lunar_dem_mosaic_overlaps(model, absolute_tolerance_m=True)


def test_audit_requires_open_mosaic():
    model = make_mosaic(
        FakeDEM("first", lambda latitude, longitude: 1.0),
        FakeDEM("second", lambda latitude, longitude: 1.0),
    )
    model.close()
    with pytest.raises(RuntimeError, match="is closed"):
        audit_lunar_dem_mosaic_overlaps(model)


def test_report_writer_emits_strict_json_and_markdown(tmp_path):
    model = make_mosaic(
        FakeDEM("first", lambda latitude, longitude: 10.0),
        FakeDEM("second", lambda latitude, longitude: 11.0),
    )
    report = audit_lunar_dem_mosaic_overlaps(model, samples_per_axis=2)
    json_path, markdown_path = write_lunar_dem_mosaic_overlap_report(report, tmp_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert payload["status"] == "PASS"
    assert payload["pairs"][0]["metrics"]["mae_m"] == 1.0
    assert "Limitations" in markdown or "Interpretation" in markdown
    assert "No seam correction" in markdown


def test_cli_reads_manifest_and_writes_reports(tmp_path, monkeypatch):
    from eclipsekit import topography

    source_a = FakeDEM("first", lambda latitude, longitude: 4.0)
    source_b = FakeDEM("second", lambda latitude, longitude: 5.0)
    readers = iter([source_a, source_b])
    monkeypatch.setattr(topography, "open_pds3_lunar_dem", lambda *args, **kwargs: next(readers))
    manifest = {
        "schema_version": 1,
        "name": "test mosaic",
        "sources": [
            {"name": "A", "image_path": "a.img", "label_path": "a.lbl"},
            {"name": "B", "image_path": "b.img", "label_path": "b.lbl"},
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "reports"

    code = main([
        "--manifest", str(manifest_path),
        "--samples-per-axis", "2",
        "--tolerance-m", "2",
        "--output-dir", str(output),
    ])

    assert code == 0
    payload = json.loads((output / "lunar-dem-mosaic-overlap-audit.json").read_text())
    assert payload["status"] == "PASS"
    assert source_a.closed and source_b.closed


def test_manifest_requires_two_sources_and_schema_version(tmp_path):
    from eclipsekit.lunar_dem_mosaic_validation import _load_manifest

    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": 2, "sources": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version=1"):
        _load_manifest(path)
    path.write_text(json.dumps({"schema_version": 1, "sources": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="at least two"):
        _load_manifest(path)


def test_overlap_audit_api_is_exported_from_package_root():
    from eclipsekit import (
        LunarDEMMosaicOverlapReport,
        LunarDEMOverlapPairResult,
        LunarDEMOverlapSample,
        audit_lunar_dem_mosaic_overlaps as public_audit,
        write_lunar_dem_mosaic_overlap_report as public_writer,
    )

    assert callable(public_audit)
    assert callable(public_writer)
    assert LunarDEMOverlapSample is not None
    assert LunarDEMOverlapPairResult is not None
    assert LunarDEMMosaicOverlapReport is not None
