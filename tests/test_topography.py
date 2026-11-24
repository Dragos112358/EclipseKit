from __future__ import annotations

import json

import numpy as np
import pytest

from eclipsekit import (
    LunarLimbQuery,
    PDS3LunarDEMModel,
    validate_pds3_lunar_dem,
    write_pds3_topography_validation_report,
)


def _write_label(
    path,
    *,
    lines=2,
    samples=4,
    ppd=2,
    center_lat=59.0,
    center_lon=11.0,
    line_offset=1.5,
    sample_offset=1.5,
    min_lat=59.0,
    max_lat=60.0,
    west_lon=10.0,
    east_lon=12.0,
    record_bytes=None,
    image_pointer='"dem.img"',
    coordinate_system="MEAN EARTH/POLAR AXIS OF DE421",
    projection="SIMPLE CYLINDRICAL",
    sample_type="PC_REAL",
    sample_bits=32,
    unit="KILOMETER",
    scaling=1.0,
    offset=1737.4,
    radius=1737.4,
):
    if record_bytes is None:
        record_bytes = samples * (sample_bits // 8)
    path.write_text(
        f'''PDS_VERSION_ID = "PDS3"
PRODUCT_ID = "SYNTHETIC_LUNAR_DEM"
DATA_SET_ID = "TEST-LUNAR-DEM"
PRODUCT_VERSION_ID = "V1.0"
TARGET_NAME = MOON
RECORD_BYTES = {record_bytes}
^IMAGE = {image_pointer}
OBJECT = IMAGE
  LINES = {lines}
  LINE_SAMPLES = {samples}
  SAMPLE_TYPE = {sample_type}
  SAMPLE_BITS = {sample_bits}
  UNIT = {unit}
  SCALING_FACTOR = {scaling}
  OFFSET = {offset}
END_OBJECT = IMAGE
OBJECT = IMAGE_MAP_PROJECTION
  MAP_PROJECTION_TYPE = "{projection}"
  A_AXIS_RADIUS = {radius} <km>
  B_AXIS_RADIUS = {radius} <km>
  C_AXIS_RADIUS = {radius} <km>
  MAP_RESOLUTION = {ppd} <pix/deg>
  POSITIVE_LONGITUDE_DIRECTION = "EAST"
  CENTER_LATITUDE = {center_lat}
  CENTER_LONGITUDE = {center_lon}
  LINE_FIRST_PIXEL = 1
  SAMPLE_FIRST_PIXEL = 1
  LINE_PROJECTION_OFFSET = {line_offset}
  SAMPLE_PROJECTION_OFFSET = {sample_offset}
  MAXIMUM_LATITUDE = {max_lat}
  MINIMUM_LATITUDE = {min_lat}
  WESTERNMOST_LONGITUDE = {west_lon}
  EASTERNMOST_LONGITUDE = {east_lon}
  COORDINATE_SYSTEM_TYPE = "BODY-FIXED ROTATING"
  COORDINATE_SYSTEM_NAME = "{coordinate_system}"
END_OBJECT = IMAGE_MAP_PROJECTION
END
''',
        encoding="ascii",
    )


def _regional_dem(tmp_path, *, values=None, image_pointer='"dem.img"', **label_options):
    image = tmp_path / "dem.img"
    label = tmp_path / "dem.lbl"
    if values is None:
        values = np.array(
            [[0.001, 0.002, 0.003, 0.004], [0.005, 0.006, 0.007, 0.008]],
            dtype="<f4",
        )
    values = np.asarray(values, dtype="<f4")
    _write_label(
        label,
        lines=values.shape[0],
        samples=values.shape[1],
        image_pointer=image_pointer,
        **label_options,
    )
    if image_pointer.startswith("("):
        image.write_bytes(b"H" * (values.shape[1] * 4) + values.tobytes())
    else:
        values.tofile(image)
    return image, label


def test_pds3_img_is_lazy_and_converts_height_above_reference_sphere(tmp_path):
    image, label = _regional_dem(tmp_path)
    with PDS3LunarDEMModel.from_pds3_img(image, label) as model:
        assert model.product_info.shape == (2, 4)
        assert model.product_info.product_id == "SYNTHETIC_LUNAR_DEM"
        assert model.product_info.reference_radius_m == pytest.approx(1_737_400.0)
        assert model.product_info.file_size_bytes == image.stat().st_size
        assert model.pixel_center(0, 0) == pytest.approx((59.75, 10.25))
        assert model.predict_altitude_m(59.5, 11.0) == pytest.approx(4.5)
        assert model.metadata.model_type == "pds3_dem"
        assert model.metadata.product_id == "SYNTHETIC_LUNAR_DEM"
        assert model.metadata.reference_radius_m == pytest.approx(1_737_400.0)
        json.dumps(model.metadata.to_dict())
        json.dumps(model.product_info.to_dict())
    assert model.is_closed
    with pytest.raises(RuntimeError, match="closed"):
        model.predict_altitude_m(59.5, 11.0)


def test_pds3_byte_and_record_pointer_is_applied(tmp_path):
    values = np.array(
        [[0.001, 0.002, 0.003, 0.004], [0.005, 0.006, 0.007, 0.008]],
        dtype="<f4",
    )
    image, label = _regional_dem(tmp_path, values=values, image_pointer='("dem.img", 2)')
    with PDS3LunarDEMModel(image, label) as model:
        assert model.product_info.data_offset_bytes == 16
        assert model.predict_altitude_m(59.5, 11.0) == pytest.approx(4.5)


def test_pds3_height_units_and_scale_are_applied_without_double_adding_radius(tmp_path):
    image = tmp_path / "dem.img"
    label = tmp_path / "dem.lbl"
    values = np.array([[10.0, 20.0, 30.0, 40.0], [50.0, 60.0, 70.0, 80.0]], dtype="<f4")
    values.tofile(image)
    _write_label(label, unit="METER", scaling=0.5, offset=1_737_400.0, radius=1737.4)
    with PDS3LunarDEMModel(image, label) as model:
        assert model.predict_altitude_m(59.5, 11.0) == pytest.approx(22.5)


def test_pds3_dem_rejects_reference_radius_or_coordinate_frame_mismatch(tmp_path):
    image, label = _regional_dem(tmp_path)
    with pytest.raises(ValueError, match="reference radius"):
        PDS3LunarDEMModel(image, label, expected_reference_radius_m=1_738_000.0)
    with pytest.raises(ValueError, match="coordinate-system mismatch"):
        PDS3LunarDEMModel(
            image, label, expected_coordinate_system="MEAN EARTH/POLAR AXIS OF DE440"
        )


def test_pds3_dem_rejects_unsupported_projection_and_non_spherical_datum(tmp_path):
    image, label = _regional_dem(tmp_path, projection="POLAR STEREOGRAPHIC")
    with pytest.raises(ValueError, match="map projection"):
        PDS3LunarDEMModel(image, label)
    label_text = label.read_text(encoding="ascii").replace(
        'MAP_PROJECTION_TYPE = "POLAR STEREOGRAPHIC"',
        'MAP_PROJECTION_TYPE = "SIMPLE CYLINDRICAL"',
    ).replace("B_AXIS_RADIUS = 1737.4", "B_AXIS_RADIUS = 1737.3")
    label.write_text(label_text, encoding="ascii")
    with pytest.raises(ValueError, match="spherical lunar reference surface"):
        PDS3LunarDEMModel(image, label)


def test_pds3_dem_rejects_truncated_image_and_missing_interpolation_cells(tmp_path):
    image, label = _regional_dem(tmp_path)
    image.write_bytes(image.read_bytes()[:-4])
    with pytest.raises(ValueError, match="truncated"):
        PDS3LunarDEMModel(image, label)

    values = np.array(
        [[0.001, np.nan, 0.003, 0.004], [0.005, 0.006, 0.007, 0.008]], dtype="<f4"
    )
    image, label = _regional_dem(tmp_path, values=values)
    with PDS3LunarDEMModel(image, label) as model:
        with pytest.raises(ValueError, match="missing elevation"):
            model.predict(LunarLimbQuery(59.75, 10.75, 0.0))


def test_pds3_regional_tile_wraps_longitude_to_nearest_declared_branch(tmp_path):
    image, label = _regional_dem(tmp_path)
    with PDS3LunarDEMModel(image, label) as model:
        assert model.predict_altitude_m(59.5, 371.0) == pytest.approx(
            model.predict_altitude_m(59.5, 11.0)
        )
        with pytest.raises(ValueError, match="outside PDS3 DEM coverage"):
            model.predict_altitude_m(59.5, 5.0)


def test_pds3_global_longitude_seam_interpolates_periodically(tmp_path):
    image = tmp_path / "global.img"
    label = tmp_path / "global.lbl"
    values = np.zeros((2, 720), dtype="<f4")
    values[:, -1] = 0.1
    values.tofile(image)
    _write_label(
        label,
        lines=2,
        samples=720,
        ppd=2,
        center_lat=0.5,
        center_lon=180.0,
        line_offset=0.5,
        sample_offset=359.5,
        min_lat=0.0,
        max_lat=1.0,
        west_lon=0.0,
        east_lon=360.0,
        record_bytes=720 * 4,
    )
    with PDS3LunarDEMModel(image, label) as model:
        assert model.product_info.global_longitude
        assert model.predict_altitude_m(0.75, 0.0) == pytest.approx(50.0)


def test_pds3_topography_validation_and_reports(tmp_path):
    image, label = _regional_dem(tmp_path)
    report = validate_pds3_lunar_dem(
        image, label, sample_grid=2, tile_shape=(1, 2), cache_tiles=4
    )
    assert report.status == "PASS"
    assert report.passed_samples == 4
    assert report.tile_cache is not None
    assert report.tile_cache["max_tiles"] == 4
    assert report.tile_cache["cached_bytes"] <= report.tile_cache["max_bytes"]
    json.dumps(report.to_dict())
    json_path, md_path = write_pds3_topography_validation_report(report, tmp_path / "reports")
    assert json_path.is_file() and md_path.is_file()
    markdown = md_path.read_text(encoding="utf-8")
    assert "PDS3 lunar topography validation" in markdown
    assert "Tile cache" in markdown
    with pytest.raises(ValueError, match="simple filename"):
        write_pds3_topography_validation_report(report, tmp_path / "reports", stem="../bad")


def test_pds3_label_parser_requires_a_pds3_label(tmp_path):
    from eclipsekit.topography import parse_pds3_label

    label = tmp_path / "bad.lbl"
    label.write_text("PDS_VERSION_ID = 'PDS4'\nEND\n", encoding="ascii")
    with pytest.raises(ValueError, match="PDS3"):
        parse_pds3_label(label)


# Phase 9.1 — bounded tile cache and streaming window access.

def test_pds3_tile_cache_reuses_tiles_for_repeated_limb_queries(tmp_path):
    image, label = _regional_dem(tmp_path)
    with PDS3LunarDEMModel(image, label, tile_shape=(1, 2), cache_tiles=8) as model:
        first = model.predict_altitude_m(59.5, 11.0)
        after_first = model.cache_info()
        second = model.predict_altitude_m(59.5, 11.0)
        after_second = model.cache_info()

        assert first == pytest.approx(4.5)
        assert second == pytest.approx(first)
        assert after_first.misses == 4
        assert after_first.current_tiles == 4
        assert after_second.hits == 4
        assert after_second.misses == 4
        assert after_second.max_tiles == 8
        assert after_second.cached_bytes <= after_second.max_bytes
        assert after_second.to_dict()["cached_bytes"] == after_second.cached_bytes


def test_pds3_tile_cache_is_bounded_and_reports_lru_evictions(tmp_path):
    image, label = _regional_dem(tmp_path)
    with PDS3LunarDEMModel(image, label, tile_shape=(1, 1), cache_tiles=1) as model:
        model.predict_altitude_m(59.5, 11.0)
        first = model.cache_info()
        assert first.current_tiles == 1
        assert first.misses == 4
        assert first.evictions == 3
        assert first.cached_bytes <= first.max_bytes

        model.predict_altitude_m(59.5, 11.0)
        second = model.cache_info()
        assert second.current_tiles == 1
        assert second.misses == 8
        assert second.evictions == 7
        assert second.hits == 0


def test_pds3_cache_can_be_disabled_and_cleared(tmp_path):
    image, label = _regional_dem(tmp_path)
    with PDS3LunarDEMModel(image, label, tile_shape=1, cache_tiles=0) as model:
        model.predict_altitude_m(59.5, 11.0)
        model.predict_altitude_m(59.5, 11.0)
        info = model.cache_info()
        assert info.max_tiles == 0
        assert info.current_tiles == 0
        assert info.hits == 0
        assert info.misses == 8

    with PDS3LunarDEMModel(image, label, tile_shape=1, cache_tiles=8) as model:
        model.predict_altitude_m(59.5, 11.0)
        assert model.cache_info().current_tiles > 0
        model.clear_tile_cache()
        cleared = model.cache_info()
        assert cleared.current_tiles == 0
        assert cleared.hits == cleared.misses == cleared.evictions == 0


def test_pds3_read_window_returns_scaled_read_only_heights(tmp_path):
    image, label = _regional_dem(tmp_path)
    with PDS3LunarDEMModel(image, label, tile_shape=(1, 2)) as model:
        window = model.read_window(0, 2, 1, 4)
        assert window.shape == (2, 3)
        assert (window.row_start, window.row_stop) == (0, 2)
        assert (window.column_start, window.column_stop) == (1, 4)
        np.testing.assert_allclose(
            window.height_above_reference_m,
            np.array([[2.0, 3.0, 4.0], [6.0, 7.0, 8.0]]),
        )
        assert not window.height_above_reference_m.flags.writeable
        with pytest.raises(ValueError):
            window.height_above_reference_m[0, 0] = 999.0


def test_pds3_iter_tiles_streams_complete_image_without_gaps(tmp_path):
    image, label = _regional_dem(tmp_path)
    with PDS3LunarDEMModel(image, label, tile_shape=(1, 3)) as model:
        tiles = list(model.iter_tiles())
        assert [tile.shape for tile in tiles] == [(1, 3), (1, 1), (1, 3), (1, 1)]
        rebuilt = np.full(model.product_info.shape, np.nan)
        for tile in tiles:
            rebuilt[
                tile.row_start:tile.row_stop,
                tile.column_start:tile.column_stop,
            ] = tile.height_above_reference_m
        np.testing.assert_allclose(rebuilt, [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]])
        assert all(not tile.height_above_reference_m.flags.writeable for tile in tiles)


def test_pds3_window_rejects_invalid_or_out_of_bounds_indices(tmp_path):
    image, label = _regional_dem(tmp_path)
    with PDS3LunarDEMModel(image, label) as model:
        with pytest.raises(TypeError, match="row_start must be an integer"):
            model.read_window(True, 2, 0, 2)
        with pytest.raises(ValueError, match="non-negative"):
            model.read_window(-1, 1, 0, 2)
        with pytest.raises(ValueError, match="greater than start"):
            model.read_window(1, 1, 0, 2)
        with pytest.raises(IndexError, match="beyond image bounds"):
            model.read_window(0, 3, 0, 2)
        with pytest.raises(TypeError, match="tile_shape"):
            list(model.iter_tiles((2, True)))


def test_pds3_model_validates_tile_cache_configuration_and_releases_cache(tmp_path):
    image, label = _regional_dem(tmp_path)
    with pytest.raises(ValueError, match="tile_shape entries must be positive"):
        PDS3LunarDEMModel(image, label, tile_shape=(0, 4))
    with pytest.raises(TypeError, match="cache_tiles must be an integer"):
        PDS3LunarDEMModel(image, label, cache_tiles=True)
    with pytest.raises(ValueError, match="cache_tiles must be non-negative"):
        PDS3LunarDEMModel(image, label, cache_tiles=-1)

    model = PDS3LunarDEMModel(image, label, tile_shape=1, cache_tiles=8)
    model.predict_altitude_m(59.5, 11.0)
    assert model.cache_info().current_tiles > 0
    model.close()
    assert model.is_closed
    with pytest.raises(RuntimeError, match="closed"):
        model.cache_info()


def test_pds3_topography_cli_reports_bounded_tile_cache(tmp_path):
    from eclipsekit.topography_validation import main

    image, label = _regional_dem(tmp_path)
    output = tmp_path / "phase9_1_reports"
    exit_code = main([
        "--image", str(image),
        "--label", str(label),
        "--sample-grid", "2",
        "--tile-size", "1",
        "--cache-tiles", "3",
        "--output-dir", str(output),
    ])
    assert exit_code == 0
    report = json.loads((output / "lunar-topography-validation.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["tile_cache"]["tile_shape"] == [1, 1]
    assert report["tile_cache"]["max_tiles"] == 3
    assert report["tile_cache"]["cached_bytes"] <= report["tile_cache"]["max_bytes"]


def test_pds3_lunar_dem_accepts_control_point_validation_api(tmp_path):
    from eclipsekit.lunar_control_points import (
        LunarControlPoint,
        LunarControlPointSet,
        validate_lunar_dem_control_points,
    )

    image, label = _regional_dem(tmp_path)
    with PDS3LunarDEMModel(image, label) as dem:
        points = LunarControlPointSet(
            dataset_id="synthetic-pds3-integration",
            title="Synthetic PDS3 control-point integration fixture",
            source_name="Synthetic test fixture",
            source_uri="https://example.invalid/synthetic-fixture",
            source_doi=None,
            independent_of_test_dem=False,
            independence_statement="Values are read from the same synthetic fixture for API integration only.",
            coordinate_system_name=dem.product_info.coordinate_system_name,
            latitude_type="planetocentric",
            longitude_direction="east",
            longitude_domain="-180_180",
            vertical_datum=dem.metadata.vertical_datum,
            reference_radius_m=dem.product_info.reference_radius_m,
            value_interpretation="height",
            points=(
                LunarControlPoint("pixel-00", 59.75, 10.25, 1.0, 0.1),
                LunarControlPoint("pixel-01", 59.75, 10.75, 2.0, 0.1),
            ),
        )
        report = validate_lunar_dem_control_points(dem, points, tolerance_m=0.01)

    assert report.status == "NOT_INDEPENDENT"
    assert [row.status for row in report.rows] == ["PASS", "PASS"]
    assert report.metrics["root_mean_square_error_m"] == pytest.approx(0.0, abs=1e-6)


def test_dem_control_point_cli_runs_on_synthetic_pds3_fixture(tmp_path, capsys):
    import json

    from eclipsekit.lunar_control_points import main as control_point_main

    image, label = _regional_dem(tmp_path)
    with PDS3LunarDEMModel(image, label) as dem:
        datum = dem.metadata.vertical_datum
        frame = dem.product_info.coordinate_system_name
        radius = dem.product_info.reference_radius_m
    control_file = tmp_path / "control-points.json"
    control_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset_id": "synthetic-cli-fixture",
                "title": "Synthetic CLI fixture",
                "source": {
                    "name": "Synthetic test only",
                    "uri": "https://example.invalid/synthetic",
                    "doi": None,
                    "independent_of_test_dem": False,
                    "independence_statement": "Synthetic values from the same test raster.",
                },
                "coordinates": {
                    "coordinate_system_name": frame,
                    "latitude_type": "planetocentric",
                    "longitude_direction": "east",
                    "longitude_domain": "-180_180",
                    "vertical_datum": datum,
                    "reference_radius_m": radius,
                    "value_interpretation": "height",
                    "value_unit": "m",
                },
                "points": [
                    {"point_id": "p00", "latitude_deg": 59.75, "longitude_deg": 10.25,
                     "value_m": 1.0}
                ],
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "reports"
    result = control_point_main(
        [
            "--format", "pds3", "--dem", str(image), "--label", str(label),
            "--control-points", str(control_file), "--tolerance-m", "0.01",
            "--output-dir", str(output_dir),
        ]
    )
    assert result == 1
    assert "Status: NOT_INDEPENDENT" in capsys.readouterr().out
    report = json.loads(
        (output_dir / "lunar-dem-control-point-validation.json").read_text(encoding="utf-8")
    )
    assert report["counts"]["PASS"] == 1
    assert report["independent_of_test_dem"] is False
