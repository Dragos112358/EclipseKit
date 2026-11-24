from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import pytest

from eclipsekit import (
    LunarControlPoint,
    LunarControlPointSet,
    LunarCoordinateTransform,
    LunarLimbQuery,
    LunarLimbModelMetadata,
    LunarReferenceSphereTransform,
    TransformedLunarDEMModel,
    de421_me_to_de440_pa_transform,
    validate_lunar_dem_control_points,
)


SOURCE_FRAME_LABEL = "MEAN EARTH/POLAR AXIS OF DE421"
SOURCE_DATUM = "radial height above DE421 ME 1,737,400 m sphere"
TARGET_DATUM = "radial height above DE440 PA 1,737,500 m sphere"
SOURCE_RADIUS_M = 1_737_400.0
TARGET_RADIUS_M = 1_737_500.0


@dataclass(frozen=True)
class _ProductInfo:
    coordinate_system_name: str = SOURCE_FRAME_LABEL
    vertical_datum: str = SOURCE_DATUM
    reference_radius_m: float = SOURCE_RADIUS_M
    product_id: str = "SYNTHETIC-DEM"
    format: str = "PDS3"
    shape: tuple[int, int] = (20, 40)

    def to_dict(self):
        return {
            "coordinate_system_name": self.coordinate_system_name,
            "vertical_datum": self.vertical_datum,
            "reference_radius_m": self.reference_radius_m,
            "product_id": self.product_id,
            "format": self.format,
            "shape": list(self.shape),
        }


class _SyntheticDEM:
    def __init__(self, *, height: float = 25.0, product_info=None):
        self.height = height
        self.product_info = product_info or _ProductInfo()
        self.metadata = LunarLimbModelMetadata(
            name="synthetic-source",
            model_type="pds3_dem",
            source="synthetic fixture only",
            vertical_datum=getattr(self.product_info, "vertical_datum", SOURCE_DATUM),
            resolution_m=100.0,
            product_id=getattr(self.product_info, "product_id", "SYNTHETIC-DEM"),
            coordinate_system=getattr(self.product_info, "coordinate_system_name", SOURCE_FRAME_LABEL),
            reference_radius_m=getattr(self.product_info, "reference_radius_m", SOURCE_RADIUS_M),
        )
        self.calls = []
        self.closed = False

    def predict_altitude_m(self, latitude_deg, longitude_deg):
        if self.closed:
            raise RuntimeError("source closed")
        self.calls.append((latitude_deg, longitude_deg))
        return self.height

    def close(self):
        self.closed = True


def _transform():
    return LunarCoordinateTransform(
        frame_transform=de421_me_to_de440_pa_transform(),
        vertical_transform=LunarReferenceSphereTransform(
            source_reference_radius_m=SOURCE_RADIUS_M,
            target_reference_radius_m=TARGET_RADIUS_M,
            source_vertical_datum=SOURCE_DATUM,
            target_vertical_datum=TARGET_DATUM,
        ),
    )


def _wrapper(source=None, **kwargs):
    return TransformedLunarDEMModel(
        source or _SyntheticDEM(),
        _transform(),
        source_coordinate_system_name=SOURCE_FRAME_LABEL,
        **kwargs,
    )


def test_transformed_dem_inverse_rotates_query_and_converts_returned_height():
    source = _SyntheticDEM(height=25.0)
    wrapper = _wrapper(source)
    target_lat, target_lon = 18.0, 42.0
    expected_source_lat, expected_source_lon = _transform().frame_transform.inverse().transform_latlon(
        target_lat, target_lon
    )

    result = wrapper.predict_altitude_m(target_lat, target_lon)

    assert source.calls == [(pytest.approx(expected_source_lat), pytest.approx(expected_source_lon))]
    assert result == pytest.approx(25.0 + SOURCE_RADIUS_M - TARGET_RADIUS_M)
    assert wrapper.product_info.coordinate_system_name == "MOON_PA_DE440"
    assert wrapper.product_info.reference_radius_m == TARGET_RADIUS_M
    assert wrapper.product_info.vertical_datum == TARGET_DATUM
    assert wrapper.product_info.shape == (20, 40)


def test_transformed_dem_exposes_provider_prediction_and_provenance():
    wrapper = _wrapper(_SyntheticDEM(height=-12.0))
    prediction = wrapper.predict(LunarLimbQuery(10.0, 20.0, 0.0))

    assert prediction.altitude_m == pytest.approx(-112.0)
    assert prediction.model_type == "custom"
    assert "MOON_ME_DE421 -> MOON_PA_DE440" in wrapper.metadata.description
    assert wrapper.product_info.to_dict()["coordinate_transform"]["sampling_strategy"].startswith(
        "inverse-transform"
    )


def test_transformed_dem_predict_many_broadcasts_and_preserves_shape():
    source = _SyntheticDEM(height=7.5)
    wrapper = _wrapper(source)
    values = wrapper.predict_many(np.array([[0.0], [10.0]]), np.array([0.0, 20.0, 40.0]))

    assert values.shape == (2, 3)
    assert np.allclose(values, -92.5)
    assert len(source.calls) == 6


def test_transformed_dem_rejects_source_label_that_does_not_match_product():
    source = _SyntheticDEM()
    with pytest.raises(ValueError, match="does not match the source DEM"):
        TransformedLunarDEMModel(
            source,
            _transform(),
            source_coordinate_system_name="DE440 PA",
        )


def test_transformed_dem_rejects_source_radius_mismatch():
    source = _SyntheticDEM(product_info=_ProductInfo(reference_radius_m=1_737_000.0))
    with pytest.raises(ValueError, match="reference radius does not match"):
        _wrapper(source)


def test_transformed_dem_rejects_source_vertical_datum_mismatch():
    source = _SyntheticDEM(product_info=_ProductInfo(vertical_datum="unknown datum"))
    with pytest.raises(ValueError, match="vertical datum does not match"):
        _wrapper(source)


def test_transformed_dem_requires_declared_product_frame_datum_and_radius():
    source = _SyntheticDEM(product_info=SimpleNamespace(reference_radius_m=SOURCE_RADIUS_M))
    with pytest.raises(ValueError, match="coordinate_system_name"):
        _wrapper(source)


def test_transformed_dem_validates_query_coordinates_before_source_sampling():
    source = _SyntheticDEM()
    wrapper = _wrapper(source)
    with pytest.raises(ValueError, match="latitude_deg must be within"):
        wrapper.predict_altitude_m(91.0, 0.0)
    with pytest.raises(ValueError, match="longitude_deg must be finite"):
        wrapper.predict_altitude_m(0.0, float("nan"))
    assert source.calls == []


def test_transformed_dem_predict_many_rejects_boolean_and_non_finite_inputs():
    wrapper = _wrapper()
    with pytest.raises(TypeError, match="not booleans"):
        wrapper.predict_many([True], [0.0])
    with pytest.raises(ValueError, match="must be finite"):
        wrapper.predict_many([0.0], [float("inf")])


def test_transformed_dem_close_does_not_close_non_owned_source_by_default():
    source = _SyntheticDEM()
    wrapper = _wrapper(source)
    wrapper.close()
    assert source.closed is False
    with pytest.raises(RuntimeError, match="is closed"):
        wrapper.predict_altitude_m(0.0, 0.0)


def test_transformed_dem_can_own_source_lifecycle():
    source = _SyntheticDEM()
    wrapper = _wrapper(source, close_source=True)
    with wrapper:
        assert wrapper.predict_altitude_m(0.0, 0.0) == pytest.approx(-75.0)
    assert source.closed is True


def test_transformed_dem_metadata_integrates_with_control_point_validator():
    source = _SyntheticDEM(height=25.0)
    wrapper = _wrapper(source)
    control_points = LunarControlPointSet(
        dataset_id="synthetic-test-only",
        title="Synthetic unit-test control point",
        source_name="unit-test fixture",
        source_uri="urn:synthetic:test",
        source_doi=None,
        independent_of_test_dem=True,
        independence_statement="Synthetic assertion used only to exercise the software interface.",
        coordinate_system_name="MOON_PA_DE440",
        latitude_type="planetocentric",
        longitude_direction="east",
        longitude_domain="-180_180",
        vertical_datum=TARGET_DATUM,
        reference_radius_m=TARGET_RADIUS_M,
        value_interpretation="height",
        points=(LunarControlPoint("P1", 8.0, 9.0, -75.0),),
    )

    report = validate_lunar_dem_control_points(wrapper, control_points, tolerance_m=1e-9)

    assert report.status == "PASS"
    assert report.dem["coordinate_system_name"] == "MOON_PA_DE440"
    assert report.rows[0].residual_m == pytest.approx(0.0)


def test_transformed_dem_rejects_missing_source_reader_product_metadata():
    source = SimpleNamespace(predict_altitude_m=lambda lat, lon: 0.0)
    with pytest.raises(TypeError, match="product_info metadata"):
        _wrapper(source)


def test_transformed_dem_rejects_transform_type_and_close_flag():
    source = _SyntheticDEM()
    with pytest.raises(TypeError, match="coordinate_transform"):
        TransformedLunarDEMModel(
            source,
            object(),
            source_coordinate_system_name=SOURCE_FRAME_LABEL,
        )
    with pytest.raises(TypeError, match="close_source"):
        TransformedLunarDEMModel(
            source,
            _transform(),
            source_coordinate_system_name=SOURCE_FRAME_LABEL,
            close_source=1,
        )
