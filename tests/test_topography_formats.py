from __future__ import annotations

import importlib
import json
import warnings

import numpy as np
import pytest

from eclipsekit import (
    GeoTiffLunarDEMModel,
    JP2LunarDEMModel,
    PDS4LunarDEMModel,
    validate_lunar_dem_format,
    write_lunar_dem_format_report,
)


FRAME = "MEAN EARTH/POLAR AXIS OF DE421"
RADIUS = 1_737_400.0


def _write_pds4(tmp_path, *, values=None, value_interpretation="height",
                coordinate_system=FRAME, data_type="IEEE754LSBSingle",
                data_offset=0, registration="Area", radius_m=RADIUS):
    if values is None:
        values = np.array([[1, 2, 3, 4], [5, 6, 7, 8]], dtype="<f4")
    values = np.asarray(values, dtype="<f4")
    data = tmp_path / "pds4-dem.dat"
    data.write_bytes(b"P" * data_offset + values.tobytes())
    mode = (f"<value_interpretation>{value_interpretation}</value_interpretation>"
            if value_interpretation is not None else "")
    label = tmp_path / "pds4-dem.xml"
    label.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Product_Observational xmlns="http://pds.nasa.gov/pds4/pds/v1">
  <Identification_Area><logical_identifier>urn:test:pds4:moon:dem</logical_identifier></Identification_Area>
  <Observation_Area><Target_Identification>
    <name>Moon</name>
    <a_axis_radius unit="m">{radius_m}</a_axis_radius>
    <b_axis_radius unit="m">{radius_m}</b_axis_radius>
    <c_axis_radius unit="m">{radius_m}</c_axis_radius>
  </Target_Identification></Observation_Area>
  <File_Area_Observational>
    <File><file_name>{data.name}</file_name></File>
    <Array_2D_Image>
      <offset unit="byte">{data_offset}</offset>
      <axes>2</axes><axis_index_order>Last Index Fastest</axis_index_order>
      <Element_Array unit="m"><data_type>{data_type}</data_type>
        <scaling_factor>1</scaling_factor><value_offset>0</value_offset>
      </Element_Array>
      <Axis_Array><axis_name>Line</axis_name><elements>{values.shape[0]}</elements><sequence_number>1</sequence_number></Axis_Array>
      <Axis_Array><axis_name>Sample</axis_name><elements>{values.shape[1]}</elements><sequence_number>2</sequence_number></Axis_Array>
    </Array_2D_Image>
  </File_Area_Observational>
  <Discipline_Area><Cartography>
    <Coordinate_System_Identification><coordinate_system_name>{coordinate_system}</coordinate_system_name></Coordinate_System_Identification>
    <Map_Projection><map_projection_name>Simple Cylindrical</map_projection_name>
      <positive_longitude_direction>East</positive_longitude_direction>
      <pixel_registration>{registration}</pixel_registration>
      <Bounding_Coordinates><west_bounding_coordinate>10</west_bounding_coordinate>
        <east_bounding_coordinate>12</east_bounding_coordinate>
        <south_bounding_coordinate>59</south_bounding_coordinate>
        <north_bounding_coordinate>60</north_bounding_coordinate>
      </Bounding_Coordinates>
    </Map_Projection>
  </Cartography></Discipline_Area>
  {mode}
</Product_Observational>
''', encoding="utf-8")
    return label, data


def test_pds4_array_2d_image_reads_lazily_and_interpolates(tmp_path):
    label, _ = _write_pds4(tmp_path, data_offset=16)
    with PDS4LunarDEMModel(label, expected_coordinate_system=FRAME,
                           tile_shape=2, cache_tiles=2) as model:
        assert model.product_info.shape == (2, 4)
        assert model.product_info.data_offset_bytes == 16
        assert model.metadata.model_type == "pds4_dem"
        assert model.pixel_center(0, 0) == pytest.approx((59.75, 10.25))
        assert model.predict_altitude_m(59.5, 11.0) == pytest.approx(4.5)
        assert model.cache_info().max_bytes == 2 * 2 * 2 * 8
        json.dumps(model.product_info.to_dict())
        json.dumps(model.metadata.to_dict())
    assert model.is_closed
    with pytest.raises(RuntimeError, match="closed"):
        model.predict_altitude_m(59.5, 11.0)


def test_pds4_radius_interpretation_converts_to_height_above_reference(tmp_path):
    values = np.full((2, 4), RADIUS + 125.0, dtype="<f4")
    label, _ = _write_pds4(tmp_path, values=values, value_interpretation="radius")
    with PDS4LunarDEMModel(label) as model:
        assert model.predict_altitude_m(59.5, 11.0) == pytest.approx(125.0)


def test_pds4_requires_unambiguous_value_mode_registration_and_frame(tmp_path):
    label, _ = _write_pds4(tmp_path, value_interpretation=None)
    with pytest.raises(ValueError, match="interpretation is ambiguous"):
        PDS4LunarDEMModel(label)
    with PDS4LunarDEMModel(label, value_interpretation="height") as model:
        assert model.predict_altitude_m(59.5, 11.0) == pytest.approx(4.5)
    label, _ = _write_pds4(tmp_path, coordinate_system="MEAN EARTH/POLAR AXIS OF DE440")
    with pytest.raises(ValueError, match="coordinate-system mismatch"):
        PDS4LunarDEMModel(label, expected_coordinate_system=FRAME)
    label, _ = _write_pds4(tmp_path, registration="Unknown")
    with pytest.raises(ValueError, match="Pixel registration"):
        PDS4LunarDEMModel(label)


def test_pds4_rejects_truncated_and_unsupported_data_types(tmp_path):
    label, data = _write_pds4(tmp_path)
    data.write_bytes(data.read_bytes()[:-4])
    with pytest.raises(ValueError, match="truncated"):
        PDS4LunarDEMModel(label)
    label, _ = _write_pds4(tmp_path, data_type="ComplexMSB8")
    with pytest.raises(ValueError, match="Unsupported PDS4"):
        PDS4LunarDEMModel(label)


def test_format_validator_writes_json_and_markdown(tmp_path):
    label, _ = _write_pds4(tmp_path)
    with PDS4LunarDEMModel(label) as model:
        report = validate_lunar_dem_format(model, sample_grid=3)
        assert report.status == "PASS"
        assert report.passed_samples == 9
        json_path, md_path = write_lunar_dem_format_report(report, tmp_path / "reports")
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        assert saved["status"] == "PASS"
        assert "Limitations" in md_path.read_text(encoding="utf-8")


def _write_geotiff(path, *, crs="EPSG:4326"):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    values = np.array([[1, 2, 3, 4], [5, 6, 7, 8]], dtype=np.float32)
    with rasterio.open(
        path, "w", driver="GTiff", width=4, height=2, count=1,
        dtype="float32", crs=crs,
        transform=from_origin(10.0, 60.0, 0.5, 0.5),
    ) as dataset:
        dataset.write(values, 1)
        dataset.set_band_unit(1, "m")
        dataset.update_tags(
            LUNAR_COORDINATE_SYSTEM=FRAME,
            LUNAR_REFERENCE_RADIUS_M=str(RADIUS),
            LUNAR_VERTICAL_DATUM="radial height relative to DE421 sphere",
            LUNAR_VALUE_INTERPRETATION="height",
        )
    return values


def test_geotiff_reads_windowed_lunar_grid_and_uses_provenance_tags(tmp_path):
    path = tmp_path / "moon.tif"
    _write_geotiff(path)
    with GeoTiffLunarDEMModel(path, tile_shape=2, cache_tiles=2) as model:
        assert model.product_info.format == "GeoTIFF"
        assert model.metadata.model_type == "geotiff_dem"
        assert model.predict_altitude_m(59.5, 11.0) == pytest.approx(4.5)
        assert model.read_window(0, 1, 0, 2).shape == (1, 2)


def test_geotiff_requires_explicit_lunar_provenance_and_geographic_grid(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    path = tmp_path / "moon.tif"
    _write_geotiff(path)
    with GeoTiffLunarDEMModel(path) as model:
        assert model.product_info.coordinate_system_name == FRAME
    pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    projected = tmp_path / "projected.tif"
    with rasterio.open(projected, "w", driver="GTiff", width=4, height=2, count=1,
                       dtype="float32", crs="EPSG:3857",
                       transform=from_origin(0, 1000, 100, 100)) as dataset:
        dataset.write(np.ones((2, 4), dtype=np.float32), 1)
        dataset.set_band_unit(1, "m")
    with pytest.raises(ValueError, match="geographic"):
        GeoTiffLunarDEMModel(
            projected, coordinate_system_name=FRAME, reference_radius_m=RADIUS,
            vertical_datum="test", value_interpretation="height", value_unit="m",
        )


def test_jp2_reader_accepts_explicit_bounds_when_unreferenced(tmp_path):
    pytest.importorskip("rasterio")
    image_module = pytest.importorskip("PIL.Image")
    path = tmp_path / "moon.jp2"
    values = np.array([[1, 2, 3, 4], [5, 6, 7, 8]], dtype=np.uint16)
    try:
        image_module.fromarray(values).save(path, format="JPEG2000")
    except Exception as exc:  # GDAL/Pillow builds may not ship a JP2 codec.
        pytest.skip(f"JPEG 2000 codec unavailable: {exc}")
    from rasterio.errors import NotGeoreferencedWarning
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with JP2LunarDEMModel(
            path, coordinate_system_name=FRAME, reference_radius_m=RADIUS,
            vertical_datum="radial height relative to DE421 sphere",
            value_interpretation="height", value_unit="m",
            bounds=(10, 59, 12, 60), coordinates_in_degrees=True,
        ) as model:
            assert model.product_info.format == "JP2"
            assert model.metadata.model_type == "jp2_dem"
            assert model.predict_altitude_m(59.5, 11.0) == pytest.approx(4.5)


def test_rasterio_optional_dependency_error_is_actionable(tmp_path, monkeypatch):
    import eclipsekit.topography_formats as module
    path = tmp_path / "placeholder.tif"
    path.write_bytes(b"placeholder")
    def missing(name):
        if name == "rasterio":
            raise ImportError("not installed")
        return importlib.import_module(name)
    monkeypatch.setattr(module.importlib, "import_module", missing)
    with pytest.raises(ImportError, match=r"eclipsekit\[raster\]"):
        GeoTiffLunarDEMModel(
            path, coordinate_system_name=FRAME, reference_radius_m=RADIUS,
            vertical_datum="test", value_interpretation="height", value_unit="m",
        )


def test_geotiff_nodata_propagates_as_missing_interpolation(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    path = tmp_path / "nodata.tif"
    values = np.array([[1, -9999, 3, 4], [5, 6, 7, 8]], dtype=np.float32)
    with rasterio.open(path, "w", driver="GTiff", width=4, height=2, count=1,
                       dtype="float32", crs="EPSG:4326",
                       transform=from_origin(10.0, 60.0, 0.5, 0.5), nodata=-9999) as ds:
        ds.write(values, 1)
        ds.set_band_unit(1, "m")
        ds.update_tags(LUNAR_COORDINATE_SYSTEM=FRAME,
                       LUNAR_REFERENCE_RADIUS_M=str(RADIUS),
                       LUNAR_VERTICAL_DATUM="height above sphere",
                       LUNAR_VALUE_INTERPRETATION="height")
    with GeoTiffLunarDEMModel(path) as model:
        with pytest.raises(ValueError, match="missing or invalid"):
            model.predict_altitude_m(59.75, 10.75)


def test_failed_sample_report_is_strict_json(tmp_path):
    values = np.array([[1, np.nan, 3, 4], [5, 6, 7, 8]], dtype="<f4")
    label, _ = _write_pds4(tmp_path, values=values)
    with PDS4LunarDEMModel(label) as model:
        report = validate_lunar_dem_format(model, sample_grid=2)
        assert report.status == "FAIL"
        json_path, _ = write_lunar_dem_format_report(report, tmp_path / "failed-report")
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        assert saved["status"] == "FAIL"


def test_format_validation_cli_writes_report_for_pds4(tmp_path):
    from eclipsekit.topography_formats_validation import main

    label, _ = _write_pds4(tmp_path)
    output = tmp_path / "cli-report"
    result = main([
        "--format", "pds4", "--input", str(label),
        "--expected-coordinate-system", FRAME,
        "--sample-grid", "3", "--tile-size", "2", "--cache-tiles", "2",
        "--output-dir", str(output),
    ])
    assert result == 0
    assert (output / "pds4-lunar-dem-validation.json").is_file()
    assert (output / "pds4-lunar-dem-validation.md").is_file()


def test_pds4_requires_array_byte_offset(tmp_path):
    label, _ = _write_pds4(tmp_path)
    text = label.read_text(encoding="utf-8").replace(
        '<offset unit="byte">0</offset>', "", 1
    )
    label.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="required byte offset"):
        PDS4LunarDEMModel(label)


def test_pds4_rejects_non_moon_target_and_reference_radius_mismatch(tmp_path):
    label, _ = _write_pds4(tmp_path)
    text = label.read_text(encoding="utf-8").replace("<name>Moon</name>", "<name>Mars</name>")
    label.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="target must be explicitly identified as Moon"):
        PDS4LunarDEMModel(label)
    label, _ = _write_pds4(tmp_path)
    with pytest.raises(ValueError, match="reference radius mismatch"):
        PDS4LunarDEMModel(label, expected_reference_radius_m=1_738_000.0)
