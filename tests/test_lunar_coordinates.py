"""Tests for explicit lunar body-fixed frame and vertical-datum transforms."""

import json

import numpy as np
import pytest

from eclipsekit.lunar_coordinates import (
    LunarCoordinateTransform,
    LunarFrameTransform,
    LunarReferenceSphereTransform,
    de421_me_to_de440_pa_transform,
    de440_pa_to_de421_me_transform,
)
from eclipsekit.lunar_coordinates_validation import (
    validate_de440_pa_to_de421_me,
    write_lunar_frame_audit_report,
)


def test_published_de440_pa_to_de421_me_matrix_is_proper_rotation():
    transform = de440_pa_to_de421_me_transform()
    matrix = np.asarray(transform.rotation_matrix)
    assert transform.source_frame == "MOON_PA_DE440"
    assert transform.target_frame == "MOON_ME_DE421"
    assert np.allclose(matrix @ matrix.T, np.eye(3), atol=2e-12, rtol=0.0)
    assert np.linalg.det(matrix) == pytest.approx(1.0, abs=2e-12)


def test_published_rotation_reconstructs_all_five_paired_reflector_coordinates():
    report = validate_de440_pa_to_de421_me(tolerance_m=0.01)
    assert report.status == "PASS"
    assert len(report.rows) == 5
    assert all(row.status == "PASS" for row in report.rows)
    assert report.maximum_residual_m < 0.001


def test_frame_transform_inverse_round_trips_cartesian_points():
    forward = de440_pa_to_de421_me_transform()
    inverse = forward.inverse()
    xyz = np.array([[1.0, 2.0, 3.0], [-4.0, 0.5, 7.0]])
    actual = inverse.transform_cartesian(forward.transform_cartesian(xyz))
    assert np.allclose(actual, xyz, atol=1e-12, rtol=0.0)
    assert inverse.source_frame == forward.target_frame
    assert inverse.target_frame == forward.source_frame


def test_de421_me_to_de440_pa_factory_is_inverse():
    first = de440_pa_to_de421_me_transform()
    second = de421_me_to_de440_pa_transform()
    assert np.allclose(
        np.asarray(second.rotation_matrix), np.asarray(first.rotation_matrix).T, atol=0.0
    )


def test_transform_latlon_handles_scalars_and_normalizes_longitude():
    identity = LunarFrameTransform(
        source_frame="A", target_frame="A",
        rotation_matrix=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        provenance="identity for test", reference_url="https://example.invalid/identity",
    )
    latitude, longitude = identity.transform_latlon(12.5, 190.0)
    assert latitude == pytest.approx(12.5)
    assert longitude == pytest.approx(-170.0)


def test_transform_latlon_broadcasts_arrays_and_preserves_shape():
    transform = de440_pa_to_de421_me_transform()
    latitude, longitude = transform.transform_latlon(np.array([0.0, 10.0]), 20.0)
    assert latitude.shape == (2,)
    assert longitude.shape == (2,)
    assert np.all(np.isfinite(latitude))
    assert np.all(np.isfinite(longitude))


def test_transform_latlon_rejects_invalid_latitude_and_non_finite_inputs():
    transform = de440_pa_to_de421_me_transform()
    with pytest.raises(ValueError, match=r"\[-90, 90\]"):
        transform.transform_latlon(90.1, 0.0)
    with pytest.raises(ValueError, match="finite"):
        transform.transform_latlon(float("nan"), 0.0)


def test_transform_cartesian_rejects_invalid_dimensions_and_booleans():
    transform = de440_pa_to_de421_me_transform()
    with pytest.raises(ValueError, match="final dimension"):
        transform.transform_cartesian([1.0, 2.0])
    with pytest.raises(TypeError, match="booleans"):
        transform.transform_cartesian([True, False, True])
    with pytest.raises(TypeError, match="booleans"):
        transform.transform_cartesian([True, 1.0, 2.0])


def test_frame_transform_rejects_non_orthonormal_and_reflection_matrices():
    arguments = {
        "source_frame": "A", "target_frame": "B",
        "provenance": "test", "reference_url": "https://example.invalid",
    }
    with pytest.raises(ValueError, match="orthonormal"):
        LunarFrameTransform(
            rotation_matrix=((1.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 1.0)),
            **arguments,
        )
    with pytest.raises(ValueError, match="determinant"):
        LunarFrameTransform(
            rotation_matrix=((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            **arguments,
        )


def test_euler_factory_rejects_non_finite_angles():
    with pytest.raises(ValueError, match="finite"):
        LunarFrameTransform.from_euler_xyz_arcsec(
            source_frame="A", target_frame="B", x_arcsec=float("nan"),
            y_arcsec=0.0, z_arcsec=0.0, provenance="test",
            reference_url="https://example.invalid",
        )


def test_vertical_datum_transform_preserves_centre_radius():
    transform = LunarReferenceSphereTransform(
        source_reference_radius_m=1_737_400.0,
        target_reference_radius_m=1_738_000.0,
        source_vertical_datum="height over 1737.4 km sphere",
        target_vertical_datum="height over 1738.0 km sphere",
    )
    assert transform.transform_height_m(100.0) == pytest.approx(-500.0)
    assert transform.transform_height_m(np.array([0.0, 100.0])).tolist() == pytest.approx(
        [-600.0, -500.0]
    )
    assert transform.inverse().transform_height_m(-500.0) == pytest.approx(100.0)


def test_vertical_datum_transform_rejects_non_positive_absolute_radius():
    transform = LunarReferenceSphereTransform(
        1_737_400.0, 1_738_000.0, "source sphere", "target sphere"
    )
    with pytest.raises(ValueError, match="source radius"):
        transform.transform_height_m(-1_737_400.0)


def test_combined_point_transform_and_inverse_round_trip():
    forward = LunarCoordinateTransform(
        frame_transform=de440_pa_to_de421_me_transform(),
        vertical_transform=LunarReferenceSphereTransform(
            1_737_400.0, 1_737_400.0, "DE440 PA sphere", "DE421 ME sphere"
        ),
    )
    source = (14.25, -72.5, -1200.0)
    transformed = forward.transform_point(*source)
    recovered = forward.inverse().transform_point(
        transformed.latitude_deg, transformed.longitude_deg,
        transformed.height_above_reference_m,
    )
    assert recovered.latitude_deg == pytest.approx(source[0], abs=1e-10)
    assert recovered.longitude_deg == pytest.approx(source[1], abs=1e-10)
    assert recovered.height_above_reference_m == pytest.approx(source[2], abs=1e-7)


def test_combined_point_transform_applies_radius_datum_shift_and_broadcasts():
    transform = LunarCoordinateTransform(
        frame_transform=de440_pa_to_de421_me_transform(),
        vertical_transform=LunarReferenceSphereTransform(
            1_737_400.0, 1_738_000.0, "source sphere", "target sphere"
        ),
    )
    result = transform.transform_points([0.0, 30.0], [0.0, 90.0], [100.0, 200.0])
    assert isinstance(result.latitude_deg, np.ndarray)
    assert result.latitude_deg.shape == (2,)
    assert result.height_above_reference_m.tolist() == pytest.approx([-500.0, -400.0])


def test_combined_transform_rejects_negative_absolute_radius_and_bad_latitude():
    transform = LunarCoordinateTransform(
        frame_transform=de440_pa_to_de421_me_transform(),
        vertical_transform=LunarReferenceSphereTransform(
            1_737_400.0, 1_737_400.0, "source sphere", "target sphere"
        ),
    )
    with pytest.raises(ValueError, match="source radius"):
        transform.transform_point(0.0, 0.0, -1_737_400.0)
    with pytest.raises(ValueError, match="latitude_deg"):
        transform.transform_point(91.0, 0.0, 0.0)


def test_lunar_coordinate_and_frame_metadata_are_json_serializable():
    transform = LunarCoordinateTransform(
        frame_transform=de440_pa_to_de421_me_transform(),
        vertical_transform=LunarReferenceSphereTransform(
            1_737_400.0, 1_737_400.0, "source sphere", "target sphere"
        ),
    )
    result = transform.transform_points([0.0, 10.0], [0.0, 20.0], [0.0, 100.0])
    json.dumps(transform.to_dict(), allow_nan=False)
    json.dumps(result.to_dict(), allow_nan=False)


def test_lunar_frame_audit_writes_json_and_markdown_reports(tmp_path):
    report = validate_de440_pa_to_de421_me()
    json_path, markdown_path = write_lunar_frame_audit_report(report, tmp_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert len(payload["rows"]) == 5
    assert "not an independent geodetic validation" in markdown_path.read_text(encoding="utf-8")


def test_combined_transform_requires_typed_component_transforms():
    with pytest.raises(TypeError, match="frame_transform"):
        LunarCoordinateTransform(
            frame_transform="not a frame transform",  # type: ignore[arg-type]
            vertical_transform=LunarReferenceSphereTransform(
                1_737_400.0, 1_737_400.0, "source", "target"
            ),
        )


def test_frame_audit_rejects_invalid_tolerances():
    with pytest.raises(ValueError, match="positive"):
        validate_de440_pa_to_de421_me(tolerance_m=0.0)
    with pytest.raises(TypeError, match="positive"):
        validate_de440_pa_to_de421_me(tolerance_m=True)
