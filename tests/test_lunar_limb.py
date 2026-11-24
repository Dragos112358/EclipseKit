from __future__ import annotations

import json
import math

import numpy as np
import pytest

from eclipsekit import (
    AngularLunarLimbProfile,
    GriddedLunarLimbModel,
    LunarLimbModelMetadata,
    LunarLimbPrediction,
    LunarLimbQuery,
    NeuralLunarLimbModel,
    LunarLimbCorrector,
    SphericalLunarLimbModel,
    TabulatedAngularLunarLimbProfile,
    predict_lunar_limb,
)


def _query(lat=0.0, lon=0.0, angle=45.0):
    return LunarLimbQuery(
        selenographic_latitude_deg=lat,
        selenographic_longitude_deg=lon,
        limb_angle_deg=angle,
        contact_name="C1",
        time_tt_jd=2461265.25,
        libration_longitude_deg=1.2,
        libration_latitude_deg=-0.3,
    )


def test_limb_metadata_is_json_friendly_and_validated():
    metadata = LunarLimbModelMetadata(
        name="test DEM", model_type="gridded_dem", source="synthetic test data",
        resolution_m=100.0, validation_rmse_m=12.5,
    )
    assert metadata.to_dict()["reference_frame"] == "selenographic"
    json.dumps(metadata.to_dict())
    with pytest.raises(ValueError, match="source"):
        LunarLimbModelMetadata(name="test", model_type="custom", source="")
    with pytest.raises(ValueError, match="resolution_m"):
        LunarLimbModelMetadata(
            name="test", model_type="custom", source="test", resolution_m=0.0,
        )


def test_spherical_model_is_zero_relief_baseline():
    model = SphericalLunarLimbModel()
    prediction = model.predict(_query())
    assert prediction.altitude_m == 0.0
    assert prediction.uncertainty_m is None
    assert prediction.model_type == "spherical"
    assert model.predict_altitude_m(0.0, 0.0) == 0.0


def test_gridded_dem_bilinear_interpolation_and_uncertainty_propagation():
    model = GriddedLunarLimbModel(
        latitudes_deg=[-1.0, 1.0],
        longitudes_deg=[-1.0, 1.0],
        altitudes_m=[[0.0, 100.0], [200.0, 300.0]],
        uncertainties_m=[[2.0, 2.0], [2.0, 2.0]],
        name="small DEM",
        source="unit-test fixture",
        vertical_datum="radial reference surface",
    )
    result = model.predict(_query(0.0, 0.0))
    assert result.altitude_m == pytest.approx(150.0)
    assert result.uncertainty_m == pytest.approx(1.0)
    assert result.source == "unit-test fixture"
    assert model.metadata.vertical_datum == "radial reference surface"


def test_gridded_dem_periodic_longitude_interpolates_across_seam():
    model = GriddedLunarLimbModel(
        latitudes_deg=[-1.0, 1.0],
        longitudes_deg=[0.0, 90.0, 180.0, 270.0],
        altitudes_m=[
            [0.0, 90.0, 180.0, 270.0],
            [0.0, 90.0, 180.0, 270.0],
        ],
        periodic_longitude=True,
    )
    at_359 = model.predict(_query(0.0, 359.0)).altitude_m
    at_minus_1 = model.predict(_query(0.0, -1.0)).altitude_m
    assert at_359 == pytest.approx(at_minus_1)
    assert at_359 == pytest.approx(3.0)


def test_gridded_dem_rejects_out_of_coverage_and_missing_cells():
    model = GriddedLunarLimbModel(
        latitudes_deg=[-1.0, 1.0],
        longitudes_deg=[-1.0, 1.0],
        altitudes_m=[[0.0, np.nan], [200.0, 300.0]],
    )
    with pytest.raises(ValueError, match="outside DEM coverage"):
        model.predict(_query(2.0, 0.0))
    with pytest.raises(ValueError, match="missing elevation"):
        model.predict(_query(0.0, 0.0))


def test_gridded_dem_csv_loader_and_duplicate_guard(tmp_path):
    csv_path = tmp_path / "dem.csv"
    csv_path.write_text(
        "latitude_deg,longitude_deg,altitude_m,uncertainty_m\n"
        "-1,-1,0,4\n-1,1,100,4\n1,-1,200,4\n1,1,300,4\n",
        encoding="utf-8",
    )
    model = GriddedLunarLimbModel.from_csv(csv_path)
    assert model.predict(_query()).altitude_m == pytest.approx(150.0)
    assert model.metadata.source == str(csv_path)

    duplicate_path = tmp_path / "duplicate.csv"
    duplicate_path.write_text(
        "latitude_deg,longitude_deg,altitude_m\n0,0,1\n0,0,2\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate DEM sample"):
        GriddedLunarLimbModel.from_csv(duplicate_path)


def test_gridded_dem_npz_loader(tmp_path):
    path = tmp_path / "dem.npz"
    np.savez(
        path,
        latitudes_deg=np.array([-1.0, 1.0]),
        longitudes_deg=np.array([-1.0, 1.0]),
        altitudes_m=np.array([[0.0, 100.0], [200.0, 300.0]]),
    )
    model = GriddedLunarLimbModel.from_npz(path)
    assert model.predict(_query()).altitude_m == pytest.approx(150.0)


def test_angular_profile_interpolates_and_wraps_360_degrees():
    profile = TabulatedAngularLunarLimbProfile(
        [0.0, 90.0, 180.0, 270.0],
        [0.0, 90.0, 180.0, 270.0],
        uncertainties_m=[1.0, 1.0, 1.0, 1.0],
        name="test apparent limb",
        source="synthetic angular profile",
    )
    assert isinstance(profile, AngularLunarLimbProfile)
    assert profile.predict_by_limb_angle(45.0).altitude_m == pytest.approx(45.0)
    assert profile.predict_by_limb_angle(315.0).altitude_m == pytest.approx(135.0)
    assert profile.predict(_query(angle=-45.0)).altitude_m == pytest.approx(135.0)
    assert profile.predict_by_limb_angle(45.0).uncertainty_m == pytest.approx(1.0)
    assert profile.metadata.reference_frame == "apparent_limb"


def test_angular_profile_nonperiodic_rejects_outside_range():
    profile = AngularLunarLimbProfile(
        [-20.0, 0.0, 20.0], [1.0, 2.0, 3.0], periodic=False,
    )
    with pytest.raises(ValueError, match="outside profile coverage"):
        profile.predict_by_limb_angle(45.0)


def test_angular_profile_csv_loader(tmp_path):
    path = tmp_path / "profile.csv"
    path.write_text(
        "limb_angle_deg,altitude_m\n0,1\n90,2\n180,3\n270,4\n",
        encoding="utf-8",
    )
    profile = AngularLunarLimbProfile.from_csv(path)
    assert profile.predict_by_limb_angle(45.0).altitude_m == pytest.approx(1.5)
    assert profile.metadata.source == str(path)


def test_model_adapter_accepts_phase5_and_legacy_interfaces():
    spherical = predict_lunar_limb(SphericalLunarLimbModel(), _query())
    assert spherical.altitude_m == 0.0

    class LegacyPredictor:
        def predict_altitude_m(self, latitude_deg, longitude_deg):
            assert latitude_deg == 1.0
            assert longitude_deg == 2.0
            return 12.0

    legacy = predict_lunar_limb(LegacyPredictor(), _query(1.0, 2.0))
    assert legacy.altitude_m == pytest.approx(12.0)
    assert legacy.model_type == "custom"

    class ProtocolPredictor:
        metadata = LunarLimbModelMetadata("custom", "custom", "fixture")

        def predict(self, query):
            assert query.contact_name == "C1"
            return 4.5

    custom = predict_lunar_limb(ProtocolPredictor(), _query())
    assert custom.altitude_m == pytest.approx(4.5)
    assert custom.source == "fixture"


def test_neural_adapter_preserves_validation_metric_without_claiming_uncertainty():
    class FakeMetadata:
        best_val_rmse_m = 18.0

    class FakeCorrector:
        metadata = FakeMetadata()

        def predict_altitude_m(self, latitude_deg, longitude_deg):
            return latitude_deg + longitude_deg

    model = NeuralLunarLimbModel(FakeCorrector())
    result = model.predict(_query(1.0, 2.0))
    assert result.altitude_m == pytest.approx(3.0)
    assert result.uncertainty_m is None
    assert model.metadata.validation_rmse_m == pytest.approx(18.0)


def test_prediction_rejects_invalid_values():
    with pytest.raises(ValueError, match="must be finite"):
        LunarLimbPrediction(float("nan"), "model", "custom", "fixture")
    with pytest.raises(ValueError, match="uncertainty_m"):
        LunarLimbPrediction(0.0, "model", "custom", "fixture", -1.0)


def test_query_rejects_invalid_coordinates():
    with pytest.raises(ValueError, match="latitude"):
        _query(91.0, 0.0)
    with pytest.raises(ValueError, match="finite"):
        _query(0.0, 0.0, float("nan"))



def test_limb_contact_provenance_is_serialized_on_contact_event():
    from eclipsekit import ContactEvent, LimbContact

    class FakeTime:
        tt = 2461265.25
        ut1 = 2461265.249999

        def utc_iso(self, delimiter="T", places=3):
            return "2026-08-12T17:00:00.000Z"

    contact = LimbContact(
        contact="C1",
        time=FakeTime(),
        delta_seconds=0.25,
        selenographic_latitude_deg=3.0,
        selenographic_longitude_deg=4.0,
        predicted_terrain_altitude_m=120.0,
        corrected_moon_radius_km=1737.52,
        limb_angle_deg=35.0,
        model_name="regional DEM",
        model_type="gridded_dem",
        model_source="PDS product fixture",
        altitude_uncertainty_m=8.0,
    )
    event = ContactEvent(
        name="C1", event_type="external", time=FakeTime(),
        separation_deg=0.5, sun_angular_radius_deg=0.266,
        moon_angular_radius_deg=0.272, position_angle_deg=35.0,
        vertex_angle_deg=12.0, sun_altitude_deg=10.0,
        sun_azimuth_deg=180.0, visibility_status="above_horizon",
        limb_correction=contact,
    )
    payload = event.to_dict()["limb_correction"]
    assert payload["model_name"] == "regional DEM"
    assert payload["model_type"] == "gridded_dem"
    assert payload["model_source"] == "PDS product fixture"
    assert payload["altitude_uncertainty_m"] == pytest.approx(8.0)
    json.dumps(payload)


def test_engine_rejects_ambiguous_legacy_and_phase5_limb_arguments():
    from eclipsekit import EclipseEngine, Observer

    engine = object.__new__(EclipseEngine)
    with pytest.raises(ValueError, match="either limb_model or legacy limb_corrector"):
        engine.calculate_local(
            Observer(0.0, 0.0), "not-used",
            limb_corrector=object(), limb_model=object(),
        )



def test_original_lunar_limb_corrector_remains_accepted_directly():
    from eclipsekit.limb import LunarLimbMetadata

    corrector = LunarLimbCorrector(
        object(),
        LunarLimbMetadata(alt_mean=0.0, alt_std=1.0),
    )

    def fake_prediction(latitude_deg, longitude_deg):
        return latitude_deg * 2.0 + longitude_deg

    # Replace inference for this compatibility test so PyTorch remains optional.
    corrector.predict_altitude_m = fake_prediction
    result = predict_lunar_limb(corrector, _query(2.0, 3.0))
    assert result.altitude_m == pytest.approx(7.0)
    assert result.model_type == "neural"
    assert result.source == "user-supplied PyTorch checkpoint"


def test_neural_corrector_loads_safe_checkpoint_and_predicts(tmp_path, monkeypatch):
    """Exercise the locally-defined PyTorch architecture without real weights."""
    torch = pytest.importorskip(
        "torch", reason="Neural checkpoint tests require the optional limb extra"
    )

    checkpoint_path = tmp_path / "synthetic-checkpoint.pt"
    checkpoint_path.write_bytes(b"test fixture; torch.load is replaced below")
    calls = {}
    checkpoint = {
        "recommended_lon_cells": 128,
        "model_state": {},
        "alt_mean": 125.0,
        "alt_std": 20.0,
        "limb_centers_deg": [0.0, 90.0],
        "band_half_width_deg": [5.0, 5.0],
        "lat_min": -80.0,
        "lat_max": 80.0,
        "best_val_rmse_m": 18.5,
    }

    def fake_load(path, *, map_location, weights_only):
        calls.update(path=path, map_location=map_location, weights_only=weights_only)
        return checkpoint

    monkeypatch.setattr(torch, "load", fake_load)
    monkeypatch.setattr(torch.nn.Module, "load_state_dict", lambda self, state: None)

    corrector = LunarLimbCorrector.from_checkpoint(checkpoint_path, device="cpu")
    prediction = corrector.predict_altitude_m(90.0, 181.0)

    assert calls == {
        "path": checkpoint_path,
        "map_location": "cpu",
        "weights_only": True,
    }
    assert corrector.checkpoint_path == str(checkpoint_path)
    assert corrector.metadata.alt_mean == 125.0
    assert corrector.metadata.best_val_rmse_m == 18.5
    assert -90.0 <= corrector.metadata.lat_min < corrector.metadata.lat_max <= 90.0
    assert np.isfinite(prediction)


def test_neural_corrector_rejects_missing_checkpoint_before_loading(tmp_path):
    with pytest.raises(FileNotFoundError, match="checkpoint not found"):
        LunarLimbCorrector.from_checkpoint(tmp_path / "missing.pt")


def test_neural_corrector_wraps_unsafe_checkpoint_load_error(tmp_path, monkeypatch):
    torch = pytest.importorskip(
        "torch", reason="Neural checkpoint tests require the optional limb extra"
    )

    path = tmp_path / "untrusted.pt"
    path.write_bytes(b"not a real checkpoint")

    def reject_load(*args, **kwargs):
        raise RuntimeError("weights-only rejected payload")

    monkeypatch.setattr(torch, "load", reject_load)
    with pytest.raises(RuntimeError, match="could not be loaded safely"):
        LunarLimbCorrector.from_checkpoint(path)


def test_libration_and_axis_geometry_return_finite_angles():
    from types import SimpleNamespace

    from eclipsekit.limb import compute_moon_libration_and_axis, contact_selenographic_point

    class ApparentMoon:
        def apparent(self):
            return self

        def ecliptic_latlon(self):
            return (
                SimpleNamespace(radians=math.radians(4.0)),
                SimpleNamespace(radians=math.radians(123.0)),
                None,
            )

    class ObserverAt:
        def observe(self, moon):
            return ApparentMoon()

    class Observer:
        def at(self, when):
            return ObserverAt()

    class Time:
        tt = 2461265.25

    longitude, latitude, axis = compute_moon_libration_and_axis(Observer(), Time(), object())
    assert -180.0 <= longitude <= 180.0
    assert -90.0 <= latitude <= 90.0
    assert 0.0 <= axis < 360.0

    for angle in (0.0, 45.0, 180.0, 315.0):
        lat, lon = contact_selenographic_point(longitude, latitude, angle)
        assert -90.0 <= lat <= 90.0
        assert -180.0 <= lon <= 180.0
