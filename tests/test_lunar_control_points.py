import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from eclipsekit.lunar_control_points import (
    LunarControlPoint,
    LunarControlPointSet,
    load_lunar_control_points,
    validate_lunar_dem_control_points,
    write_lunar_dem_control_point_report,
)
from eclipsekit.lunar_coordinates import (
    LunarCoordinateTransform,
    LunarFrameTransform,
    LunarReferenceSphereTransform,
)


class _FakeProductInfo:
    def __init__(self, frame="MOON_ME_DE421", datum="sphere-1737400", radius=1_737_400.0):
        self.coordinate_system_name = frame
        self.vertical_datum = datum
        self.reference_radius_m = radius

    def to_dict(self):
        return {
            "coordinate_system_name": self.coordinate_system_name,
            "vertical_datum": self.vertical_datum,
            "reference_radius_m": self.reference_radius_m,
        }


class _FakeDEM:
    def __init__(self, fn, *, frame="MOON_ME_DE421", datum="sphere-1737400", radius=1_737_400.0):
        self.product_info = _FakeProductInfo(frame, datum, radius)
        self._fn = fn

    def predict_altitude_m(self, latitude_deg, longitude_deg):
        return self._fn(latitude_deg, longitude_deg)


def _point_set(*, independent=True, points=None, frame="MOON_ME_DE421", datum="sphere-1737400",
               radius=1_737_400.0, interpretation="height"):
    return LunarControlPointSet(
        dataset_id="test-control-set",
        title="Independent fixture",
        source_name="Synthetic test observations",
        source_uri="https://example.invalid/control-points",
        source_doi=None,
        independent_of_test_dem=independent,
        independence_statement="Synthetic fixtures are held separate from the fake DEM function.",
        coordinate_system_name=frame,
        latitude_type="planetocentric",
        longitude_direction="east",
        longitude_domain="-180_180",
        vertical_datum=datum,
        reference_radius_m=radius,
        value_interpretation=interpretation,
        points=tuple(points or (
            LunarControlPoint("A", 0.0, 0.0, 100.0, 2.0),
            LunarControlPoint("B", 1.0, 2.0, 200.0, 4.0),
        )),
    )


def _json_payload(*, interpretation="height", independent=True, points=None):
    return {
        "schema_version": 1,
        "dataset_id": "test-json",
        "title": "Test control points",
        "source": {
            "name": "Synthetic fixture",
            "uri": "https://example.invalid/control-points",
            "doi": None,
            "independent_of_test_dem": independent,
            "independence_statement": "Synthetic reference values are separate from the DEM fixture.",
        },
        "coordinates": {
            "coordinate_system_name": "MOON_ME_DE421",
            "latitude_type": "planetocentric",
            "longitude_direction": "east",
            "longitude_domain": "-180_180",
            "vertical_datum": "sphere-1737400",
            "reference_radius_m": 1_737_400.0,
            "value_interpretation": interpretation,
            "value_unit": "m",
        },
        "points": points if points is not None else [
            {"point_id": "A", "latitude_deg": 0, "longitude_deg": 0, "value_m": 100.0,
             "uncertainty_1sigma_m": 2.0},
            {"point_id": "B", "latitude_deg": 1, "longitude_deg": 2, "value_m": 200.0},
        ],
    }


def _write_json(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_control_points_parses_metadata_hashes_source_and_values(tmp_path):
    path = _write_json(tmp_path / "points.json", _json_payload())
    dataset = load_lunar_control_points(path)
    assert dataset.dataset_id == "test-json"
    assert dataset.points[0].reference_height_m == 100.0
    assert dataset.source_sha256 and len(dataset.source_sha256) == 64
    assert dataset.independent_of_test_dem is True


def test_load_control_points_converts_planetary_radius_to_sphere_height(tmp_path):
    payload = _json_payload(interpretation="radius", points=[
        {"point_id": "A", "latitude_deg": 0, "longitude_deg": 0, "value_m": 1_737_500.0}
    ])
    dataset = load_lunar_control_points(_write_json(tmp_path / "radius.json", payload))
    assert dataset.points[0].reference_height_m == pytest.approx(100.0)


@pytest.mark.parametrize("payload, message", [
    ({}, "schema_version=1"),
    ({"schema_version": 1, "source": [], "coordinates": {}, "points": []}, "source and coordinates"),
    ({"schema_version": 1, "source": {}, "coordinates": {}, "points": {}}, "points array"),
])
def test_load_control_points_rejects_bad_document_shapes(tmp_path, payload, message):
    with pytest.raises(ValueError, match=message):
        load_lunar_control_points(_write_json(tmp_path / "bad.json", payload))


def test_load_control_points_requires_explicit_metre_unit(tmp_path):
    payload = _json_payload()
    payload["coordinates"]["value_unit"] = "km"
    with pytest.raises(ValueError, match="value_unit='m'"):
        load_lunar_control_points(_write_json(tmp_path / "bad-unit.json", payload))


def test_load_control_points_rejects_duplicate_ids(tmp_path):
    payload = _json_payload(points=[
        {"point_id": "same", "latitude_deg": 0, "longitude_deg": 0, "value_m": 1},
        {"point_id": "same", "latitude_deg": 1, "longitude_deg": 1, "value_m": 2},
    ])
    with pytest.raises(ValueError, match="unique"):
        load_lunar_control_points(_write_json(tmp_path / "duplicate.json", payload))


def test_control_point_rejects_invalid_latitude_and_uncertainty():
    with pytest.raises(ValueError, match="latitude_deg"):
        LunarControlPoint("bad", 91, 0, 0)
    with pytest.raises(ValueError, match="uncertainty_1sigma_m"):
        LunarControlPoint("bad", 0, 0, 0, 0)


def test_control_point_set_rejects_non_independent_metadata_type():
    with pytest.raises(TypeError, match="boolean"):
        _point_set(independent="yes")


def test_control_point_set_requires_explicit_planetocentric_coordinates():
    with pytest.raises(ValueError, match="planetocentric"):
        LunarControlPointSet(
            dataset_id="x", title="x", source_name="x", source_uri="x",
            source_doi=None, independent_of_test_dem=True, independence_statement="x",
            coordinate_system_name="MOON_ME_DE421", latitude_type="planetographic",
            longitude_direction="east", longitude_domain="-180_180", vertical_datum="x",
            reference_radius_m=1_737_400, value_interpretation="height",
            points=(LunarControlPoint("x", 0, 0, 0),),
        )


def test_validation_reports_bias_mae_rmse_and_standardized_residuals():
    points = _point_set()
    dem = _FakeDEM(lambda lat, lon: 101.0 if lat == 0 else 198.0)
    report = validate_lunar_dem_control_points(dem, points, tolerance_m=3.0)
    assert report.status == "PASS"
    assert [row.status for row in report.rows] == ["PASS", "PASS"]
    assert report.metrics["mean_bias_m"] == pytest.approx(-0.5)
    assert report.metrics["mean_absolute_error_m"] == pytest.approx(1.5)
    assert report.metrics["root_mean_square_error_m"] == pytest.approx(np.sqrt(2.5))
    assert report.rows[0].standardized_residual == pytest.approx(0.5)


def test_validation_fails_when_any_point_exceeds_absolute_tolerance():
    points = _point_set()
    report = validate_lunar_dem_control_points(
        _FakeDEM(lambda lat, lon: 110.0), points, tolerance_m=5.0
    )
    assert report.status == "FAIL"
    assert sum(row.status == "FAIL" for row in report.rows) == 2


def test_validation_is_not_pass_when_control_set_declares_non_independence():
    points = _point_set(independent=False)
    report = validate_lunar_dem_control_points(
        _FakeDEM(lambda lat, lon: 100.0 if lat == 0 else 200.0), points, tolerance_m=1.0
    )
    assert report.status == "NOT_INDEPENDENT"
    assert all(row.status == "PASS" for row in report.rows)


def test_validation_marks_out_of_coverage_as_partial():
    def sample(lat, lon):
        if lat > 0.5:
            raise ValueError("outside DEM coverage")
        return 100.0

    report = validate_lunar_dem_control_points(
        _FakeDEM(sample), _point_set(), tolerance_m=1.0
    )
    assert report.status == "PARTIAL"
    assert report.rows[1].status == "OUT_OF_COVERAGE"
    assert report.metrics["evaluated_points"] == 1


def test_validation_records_unexpected_sample_error_without_losing_report():
    def sample(lat, lon):
        if lat == 0:
            raise RuntimeError("synthetic read error")
        return 200.0

    report = validate_lunar_dem_control_points(
        _FakeDEM(sample), _point_set(), tolerance_m=1.0
    )
    assert report.status == "PARTIAL"
    assert report.rows[0].status == "ERROR"
    assert report.rows[1].status == "PASS"


def test_validation_refuses_frame_mismatch_without_transform():
    dem = _FakeDEM(lambda lat, lon: 100.0, frame="MOON_PA_DE440")
    with pytest.raises(ValueError, match="coordinate frames differ"):
        validate_lunar_dem_control_points(dem, _point_set(), tolerance_m=1.0)


def test_validation_accepts_frame_and_radius_transform_with_explicit_provenance():
    source_datum = "source sphere"
    target_datum = "target sphere"
    points = _point_set(frame="MOON_PA_DE440", datum=source_datum, radius=1_737_400.0)
    frame = LunarFrameTransform.de440_pa_to_de421_me()
    vertical = LunarReferenceSphereTransform(
        1_737_400.0, 1_737_000.0, source_datum, target_datum
    )
    transform = LunarCoordinateTransform(frame, vertical)
    dem = _FakeDEM(lambda lat, lon: -300.0, frame="MEAN EARTH/POLAR AXIS OF DE421",
                   datum=target_datum, radius=1_737_000.0)
    report = validate_lunar_dem_control_points(
        dem, points, tolerance_m=1000.0, coordinate_transform=transform
    )
    assert report.status == "PASS"
    assert report.coordinate_transform["frame_transform"]["source_frame"] == "MOON_PA_DE440"
    assert all(row.latitude_deg != points.points[index].latitude_deg or
               row.longitude_deg != points.points[index].longitude_deg
               for index, row in enumerate(report.rows))


def test_validation_rejects_transform_wrong_source_frame():
    points = _point_set(frame="MOON_PA_DE440", datum="source")
    frame = LunarFrameTransform.de440_pa_to_de421_me()
    wrong_frame = LunarFrameTransform(
        source_frame="OTHER", target_frame=frame.target_frame,
        rotation_matrix=frame.rotation_matrix, provenance="test", reference_url="https://example.invalid",
    )
    vertical = LunarReferenceSphereTransform(1_737_400, 1_737_400, "source", "sphere-1737400")
    with pytest.raises(ValueError, match="source_frame"):
        validate_lunar_dem_control_points(
            _FakeDEM(lambda lat, lon: 0.0), points, tolerance_m=1.0,
            coordinate_transform=LunarCoordinateTransform(wrong_frame, vertical),
        )


def test_validation_rejects_datum_mismatch_without_explicit_transform():
    with pytest.raises(ValueError, match="vertical datums differ"):
        validate_lunar_dem_control_points(
            _FakeDEM(lambda lat, lon: 100.0, datum="other sphere"),
            _point_set(), tolerance_m=1.0,
        )


@pytest.mark.parametrize("tolerance", [0, -1, float("nan"), True])
def test_validation_rejects_invalid_tolerance(tolerance):
    with pytest.raises((TypeError, ValueError), match="tolerance_m"):
        validate_lunar_dem_control_points(
            _FakeDEM(lambda lat, lon: 100.0), _point_set(), tolerance_m=tolerance
        )


def test_validation_requires_dem_product_metadata_and_predict_method():
    with pytest.raises(TypeError, match="product_info"):
        validate_lunar_dem_control_points(object(), _point_set(), tolerance_m=1.0)
    with pytest.raises(TypeError, match="predict_altitude_m"):
        validate_lunar_dem_control_points(
            SimpleNamespace(product_info=_FakeProductInfo()), _point_set(), tolerance_m=1.0
        )


def test_control_point_report_writes_strict_json_and_markdown(tmp_path):
    report = validate_lunar_dem_control_points(
        _FakeDEM(lambda lat, lon: 101.0 if lat == 0 else 201.0),
        _point_set(), tolerance_m=2.0,
    )
    json_path, markdown_path = write_lunar_dem_control_point_report(report, tmp_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["counts"]["PASS"] == 2
    text = markdown_path.read_text(encoding="utf-8")
    assert "Residual = DEM − reference" in text
    assert "Limitations" in text


def test_control_point_api_is_exported_from_package_root():
    import eclipsekit

    assert eclipsekit.LunarControlPoint is LunarControlPoint
    assert eclipsekit.LunarControlPointSet is LunarControlPointSet
    assert callable(eclipsekit.load_lunar_control_points)
    assert callable(eclipsekit.validate_lunar_dem_control_points)
    assert callable(eclipsekit.write_lunar_dem_control_point_report)


def test_validation_does_not_misclassify_missing_cells_as_out_of_coverage():
    def sample(lat, lon):
        raise ValueError("interpolation touches missing elevation cells")

    report = validate_lunar_dem_control_points(
        _FakeDEM(sample), _point_set(), tolerance_m=1.0
    )
    assert report.status == "PARTIAL"
    assert all(row.status == "ERROR" for row in report.rows)
