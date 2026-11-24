"""Phase 7.2 hardening tests for lunar-limb data and prediction contracts."""
from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest

from eclipsekit.limb import (
    GriddedLunarLimbModel,
    LunarLimbCorrector,
    LunarLimbMetadata,
    LunarLimbModelMetadata,
    LunarLimbPrediction,
    LunarLimbQuery,
    NeuralLunarLimbModel,
    TabulatedAngularLunarLimbProfile,
    compute_moon_libration_and_axis,
    contact_selenographic_point,
    predict_lunar_limb,
)


def _query(lat=0.0, lon=0.0, angle=0.0, **kwargs):
    return LunarLimbQuery(lat, lon, angle, **kwargs)


@pytest.mark.parametrize("kwargs, message", [
    ({"name": " "}, "name must be non-empty"),
    ({"source": " "}, "source must be non-empty"),
    ({"model_type": "unknown"}, "Unsupported lunar-limb model_type"),
    ({"reference_frame": "equatorial"}, "reference_frame must"),
    ({"resolution_m": float("nan")}, "resolution_m must be finite"),
    ({"resolution_m": -1}, "resolution_m must be finite"),
    ({"validation_rmse_m": float("inf")}, "validation_rmse_m must be finite"),
    ({"validation_rmse_m": -1}, "validation_rmse_m must be finite"),
])
def test_limb_model_metadata_rejects_invalid_provenance(kwargs, message):
    base = {"name": "sample", "model_type": "custom", "source": "fixture"}
    with pytest.raises(ValueError, match=message):
        LunarLimbModelMetadata(**(base | kwargs))


def test_limb_query_rejects_invalid_time_and_libration_values():
    with pytest.raises(ValueError, match="time_tt_jd must be finite"):
        _query(time_tt_jd=float("nan"))
    with pytest.raises(ValueError, match="Optional libration"):
        _query(libration_longitude_deg=float("inf"))
    with pytest.raises(ValueError, match="Optional libration"):
        _query(libration_latitude_deg=float("nan"))


@pytest.mark.parametrize("altitude, uncertainty, name, source", [
    (float("inf"), None, "m", "s"),
    (1.0, float("nan"), "m", "s"),
    (1.0, -0.1, "m", "s"),
    (1.0, None, " ", "s"),
    (1.0, None, "m", " "),
])
def test_limb_prediction_rejects_invalid_result_metadata(altitude, uncertainty, name, source):
    with pytest.raises(ValueError):
        LunarLimbPrediction(altitude, name, "custom", source, uncertainty)


@pytest.mark.parametrize("lats, lons, heights, kwargs, message", [
    ([0], [0, 1], [[0, 0]], {}, "latitudes_deg"),
    ([0, 1], [0], [[0], [0]], {}, "longitudes_deg"),
    ([0, float("nan")], [0, 1], [[0, 0], [0, 0]], {}, "Grid coordinates"),
    ([1, 0], [0, 1], [[0, 0], [0, 0]], {}, "strictly increasing"),
    ([0, 1], [1, 0], [[0, 0], [0, 0]], {}, "strictly increasing"),
    ([-91, 0], [0, 1], [[0, 0], [0, 0]], {}, r"within \[-90, 90\]"),
    ([0, 1], [0, 1], [[0]], {}, "shape"),
    ([0, 1], [0, 1], [[float("inf"), 0], [0, 0]], {}, "not infinity"),
    ([0, 1], [0, 1], [[float("nan"), float("nan")], [float("nan"), float("nan")]], {}, "at least one finite"),
    ([0, 1], [0, 1], [[0, 0], [0, 0]], {"uncertainties_m": [[1]]}, "shape"),
    ([0, 1], [0, 1], [[0, 0], [0, 0]], {"uncertainties_m": [[1, -1], [1, 1]]}, "finite and non-negative"),
    ([0, 1], [0, 360], [[0, 0], [0, 0]], {"periodic_longitude": True}, "must not duplicate"),
    ([0, 1], [0, 1], [[0, 0], [0, 0]], {"periodic_longitude": 1}, "must be a bool"),
])
def test_gridded_dem_constructor_rejects_invalid_grids(lats, lons, heights, kwargs, message):
    with pytest.raises(ValueError, match=message):
        GriddedLunarLimbModel(lats, lons, heights, **kwargs)


def test_gridded_dem_csv_loader_reports_missing_header_empty_and_numeric_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        GriddedLunarLimbModel.from_csv(tmp_path / "missing.csv")

    bad_header = tmp_path / "header.csv"
    bad_header.write_text("lat,lon,height\n0,0,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="requires latitude_deg"):
        GriddedLunarLimbModel.from_csv(bad_header)

    empty = tmp_path / "empty.csv"
    empty.write_text("latitude_deg,longitude_deg,altitude_m\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no data rows"):
        GriddedLunarLimbModel.from_csv(empty)

    malformed = tmp_path / "malformed.csv"
    malformed.write_text(
        "latitude_deg,longitude_deg,altitude_m\n0,0,not-a-number\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="non-numeric sample"):
        GriddedLunarLimbModel.from_csv(malformed)


def test_gridded_dem_csv_requires_complete_uncertainty_values(tmp_path):
    path = tmp_path / "uncertainty.csv"
    path.write_text(
        "latitude_deg,longitude_deg,altitude_m,uncertainty_m\n"
        "-1,-1,1,2\n-1,1,2,\n1,-1,3,2\n1,1,4,2\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Every uncertainty_m"):
        GriddedLunarLimbModel.from_csv(path)


def test_gridded_dem_npz_loader_reports_missing_file_and_schema(tmp_path):
    with pytest.raises(FileNotFoundError):
        GriddedLunarLimbModel.from_npz(tmp_path / "missing.npz")
    path = tmp_path / "bad.npz"
    np.savez(path, latitudes_deg=[0, 1])
    with pytest.raises(ValueError, match="must contain"):
        GriddedLunarLimbModel.from_npz(path)


def test_gridded_dem_nonperiodic_longitude_bounds_and_scalar_adapter():
    model = GriddedLunarLimbModel(
        [-1, 1], [-1, 1], [[0, 2], [2, 4]], name="regional", source="test"
    )
    assert model.predict_altitude_m(0.0, 0.0) == pytest.approx(2.0)
    with pytest.raises(ValueError, match="outside DEM coverage"):
        model.predict(_query(0.0, 2.0))


def test_angular_profile_rejects_invalid_shapes_values_and_duplicates():
    with pytest.raises(ValueError, match="matching 1D arrays"):
        TabulatedAngularLunarLimbProfile([0, 90], [1])
    with pytest.raises(ValueError, match="must be finite"):
        TabulatedAngularLunarLimbProfile([0, float("nan")], [1, 2])
    with pytest.raises(ValueError, match="uncertainties_m must be finite"):
        TabulatedAngularLunarLimbProfile([0, 90], [1, 2], uncertainties_m=[1])
    with pytest.raises(ValueError, match="non-negative"):
        TabulatedAngularLunarLimbProfile([0, 90], [1, 2], uncertainties_m=[1, -1])
    with pytest.raises(ValueError, match="unique after"):
        TabulatedAngularLunarLimbProfile([0, 360], [1, 2])


def test_angular_profile_csv_loader_reports_invalid_inputs(tmp_path):
    with pytest.raises(FileNotFoundError):
        TabulatedAngularLunarLimbProfile.from_csv(tmp_path / "missing.csv")

    header = tmp_path / "header.csv"
    header.write_text("angle,height\n0,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="requires limb_angle_deg"):
        TabulatedAngularLunarLimbProfile.from_csv(header)

    empty = tmp_path / "empty.csv"
    empty.write_text("limb_angle_deg,altitude_m\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no samples"):
        TabulatedAngularLunarLimbProfile.from_csv(empty)

    malformed = tmp_path / "malformed.csv"
    malformed.write_text("limb_angle_deg,altitude_m\n0,abc\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-numeric sample"):
        TabulatedAngularLunarLimbProfile.from_csv(malformed)


def test_angular_profile_sorts_nonperiodic_data_and_rejects_non_finite_request():
    profile = TabulatedAngularLunarLimbProfile(
        [30, -10, 10], [3, -1, 1], periodic=False
    )
    assert profile.limb_angles_deg.tolist() == [-10, 10, 30]
    with pytest.raises(ValueError, match="must be finite"):
        profile.predict_by_limb_angle(float("nan"))


def test_neural_corrector_uses_lazy_torch_import_and_adapter_provenance():
    import torch

    class FakeModel:
        def __call__(self, u, v):
            return torch.ones_like(u) * (u + v)

    corrector = LunarLimbCorrector(
        FakeModel(), LunarLimbMetadata(alt_mean=10.0, alt_std=2.0, lat_min=-90.0, lat_max=90.0)
    )
    # Deliberately do not set _torch: prediction must import torch on demand.
    predicted = corrector.predict_altitude_m(0.0, 0.0)
    assert math.isfinite(predicted)

    wrapped = NeuralLunarLimbModel(corrector, source="test checkpoint")
    result = wrapped.predict(_query(0.0, 0.0))
    assert result.model_type == "neural"
    assert result.source == "test checkpoint"
    assert result.uncertainty_m is None
    assert wrapped.predict_altitude_m(0, 0) == pytest.approx(predicted)


def test_predict_lunar_limb_validates_provider_return_contracts():
    query = _query()

    class BadProvider:
        def predict(self, _query):
            return object()

    with pytest.raises(TypeError, match="must return"):
        predict_lunar_limb(BadProvider(), query)

    class NumericProvider:
        metadata = SimpleNamespace(name="Numeric", model_type="custom", source="fixture")

        def predict(self, _query):
            return 12.5

    numeric = predict_lunar_limb(NumericProvider(), query)
    assert numeric.altitude_m == pytest.approx(12.5)
    assert numeric.model_name == "Numeric"

    class NoMetadata:
        def predict(self, _query):
            return 3

    plain = predict_lunar_limb(NoMetadata(), query)
    assert plain.model_name == "NoMetadata"
    assert plain.source == "custom predictor"

    with pytest.raises(TypeError, match="must implement"):
        predict_lunar_limb(object(), query)


def test_legacy_predictor_non_numeric_result_is_rejected():
    class BadLegacy:
        def predict_altitude_m(self, *_args):
            return "not numeric"

    with pytest.raises(ValueError):
        predict_lunar_limb(BadLegacy(), _query())


def test_libration_axis_singular_denominator_uses_zero_axis_position_angle():
    time = SimpleNamespace(tt=2451545.0)
    omega = math.radians(125.0445479)
    inclination = math.radians(1.54242)
    beta = inclination - math.pi / 2.0
    longitude = omega - math.pi / 2.0

    class FakeApparent:
        def apparent(self):
            return self

        def ecliptic_latlon(self):
            return (
                SimpleNamespace(radians=beta),
                SimpleNamespace(radians=longitude),
                None,
            )

    observer = SimpleNamespace(at=lambda _t: SimpleNamespace(observe=lambda _m: FakeApparent()))
    libration_lon, libration_lat, axis = compute_moon_libration_and_axis(observer, time, object())
    assert math.isfinite(libration_lon)
    assert math.isfinite(libration_lat)
    assert math.isfinite(axis)
    assert 0.0 <= axis < 360.0


def test_contact_selenographic_point_handles_angle_wrap_and_polar_libration():
    for libration_lon, libration_lat, angle in [(-179.9, 89.0, 270.0), (179.9, -89.0, -90.0)]:
        lat, lon = contact_selenographic_point(libration_lon, libration_lat, angle)
        assert -90.0 <= lat <= 90.0
        assert -180.0 <= lon <= 180.0
