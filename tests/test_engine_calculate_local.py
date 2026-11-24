from __future__ import annotations

import pytest

from eclipsekit import HorizonProfile, Observer
from eclipsekit.contacts import RootResult

from test_engine_helpers import FakeObserver, FakeTime, bare_engine


def root_result(root, *, converged=True, status="converged"):
    return RootResult(
        root=root if converged else None,
        converged=converged,
        status=status,
        method="brent",
        iterations=5,
        function_calls=7,
        bracket_start=root - 0.001 if root is not None else None,
        bracket_end=root + 0.001 if root is not None else None,
        residual=0.0 if converged else 1.0,
        message="synthetic result",
    )


def configured_local_engine(monkeypatch, *, minimum_separation=0.05, roots=None):
    engine = bare_engine()
    engine.time = lambda value: FakeTime(2.0)
    engine._observer = lambda observer: FakeObserver()
    engine._find_minimum_separation = lambda *args, **kwargs: (2.0, minimum_separation)
    engine._angular_radii_deg = lambda *args, **kwargs: (0.2, 0.3)
    values = list(roots or [root_result(1.8), root_result(2.2), root_result(1.95), root_result(2.05)])
    calls = []

    def solve(function, start, end, **kwargs):
        calls.append((start, end))
        return values[len(calls) - 1]

    engine._solve_root_detailed = solve
    engine._approximate_zodiac_sector = lambda observer, when: "Aries"
    engine._visible_planets = lambda observer, when: [("Venus", 15.0)]
    engine._build_contact_event = lambda observer, observer_sf, name, event_type, event_time, **kwargs: {
        "name": name, "type": event_type, "time": event_time.tt,
    }
    return engine, calls


def test_calculate_local_builds_total_eclipse_and_orders_contact_events(monkeypatch):
    engine, calls = configured_local_engine(monkeypatch)
    result = engine.calculate_local(
        Observer(42.6, -5.57), "2026-08-12", include_sunrise_sunset=False,
        include_shadow_metrics=False, include_planets=True,
    )

    assert result.eclipse_type == "total"
    assert result.central_phase_duration_seconds == pytest.approx((2.05 - 1.95) * 86400)
    assert result.partial_phase_duration_seconds == pytest.approx((2.2 - 1.8) * 86400)
    assert list(result.contact_events) == ["C1", "C2", "MAXIMUM", "C3", "C4"]
    assert result.visible_planets == [("Venus", 15.0)]
    assert result.approximate_zodiac_sector == "Aries"
    assert result.warnings == []
    assert len(calls) == 4


def test_calculate_local_partial_eclipse_has_no_central_duration(monkeypatch):
    roots = [root_result(1.8), root_result(2.2)]
    engine, calls = configured_local_engine(monkeypatch, minimum_separation=0.15, roots=roots)
    result = engine.calculate_local(
        Observer(10, 20), "2026-08-12", find_next_if_none=False,
        include_sunrise_sunset=False, include_shadow_metrics=False, include_planets=False,
    )

    assert result.eclipse_type == "partial"
    assert result.central_phase_duration_seconds is None
    assert result.duration_seconds == 0.0
    assert result.contacts.c2 is None and result.contacts.c3 is None
    assert list(result.contact_events) == ["C1", "MAXIMUM", "C4"]
    assert result.visible_planets == []
    assert len(calls) == 2


def test_calculate_local_returns_none_when_no_local_eclipse_and_not_searching_next(monkeypatch):
    engine, _ = configured_local_engine(monkeypatch, minimum_separation=1.0)
    result = engine.calculate_local(
        Observer(10, 20), "2026-08-12", find_next_if_none=False,
    )
    assert result is None


def test_calculate_local_returns_none_when_next_search_finds_no_eclipse(monkeypatch):
    engine, _ = configured_local_engine(monkeypatch, minimum_separation=1.0)
    engine.find_next_local_eclipse = lambda observer, start: None
    result = engine.calculate_local(Observer(10, 20), "2026-08-12", find_next_if_none=True)
    assert result is None


def test_calculate_local_can_recenter_on_next_local_eclipse(monkeypatch):
    engine, _ = configured_local_engine(monkeypatch, minimum_separation=1.0)
    engine.find_next_local_eclipse = lambda observer, start: FakeTime(10.0)
    calls = {"count": 0}

    def find_minimum(*args, **kwargs):
        calls["count"] += 1
        return (2.0, 1.0) if calls["count"] == 1 else (10.0, 0.05)

    engine._find_minimum_separation = find_minimum
    roots = iter([root_result(9.8), root_result(10.2), root_result(9.95), root_result(10.05)])
    engine._solve_root_detailed = lambda *args, **kwargs: next(roots)
    result = engine.calculate_local(
        Observer(10, 20), "2026-08-12", find_next_if_none=True,
        include_sunrise_sunset=False, include_shadow_metrics=False, include_planets=False,
    )
    assert result is not None
    assert result.is_next_upcoming is True
    assert result.maximum.tt == 10.0


def test_calculate_local_keeps_partial_result_when_contact_solver_fails(monkeypatch):
    roots = [root_result(None, converged=False, status="not_bracketed"), root_result(2.2)]
    engine, _ = configured_local_engine(monkeypatch, minimum_separation=0.15, roots=roots)
    result = engine.calculate_local(
        Observer(10, 20), "2026-08-12", find_next_if_none=False,
        include_sunrise_sunset=False, include_shadow_metrics=False, include_planets=False,
    )
    assert result is not None
    assert result.contacts.c1 is None
    assert result.contacts.c4.tt == pytest.approx(2.2)
    assert any("C1 contact solver did not converge" in warning for warning in result.warnings)
    assert "C1" not in result.contact_events


def test_calculate_local_records_optional_shadow_metric_failure(monkeypatch):
    engine, _ = configured_local_engine(monkeypatch)
    engine._shadow_metrics = lambda *args: (_ for _ in ()).throw(RuntimeError("synthetic metric error"))
    result = engine.calculate_local(
        Observer(10, 20), "2026-08-12", include_sunrise_sunset=False,
        include_shadow_metrics=True, include_planets=False,
    )
    assert result is not None
    assert any("Shadow metrics unavailable" in warning for warning in result.warnings)
    assert result.shadow_velocity_km_s is None


def test_calculate_local_records_optional_sunrise_failure_without_losing_result(monkeypatch):
    engine, _ = configured_local_engine(monkeypatch)
    result = engine.calculate_local(
        Observer(10, 20), "2026-08-12", include_sunrise_sunset=True,
        include_shadow_metrics=False, include_planets=False,
    )
    assert result is not None
    assert any("Sunrise/sunset calculation unavailable" in warning for warning in result.warnings)


def test_calculate_local_records_contact_metadata_failures(monkeypatch):
    engine, _ = configured_local_engine(monkeypatch)
    engine._build_contact_event = lambda *args, **kwargs: (_ for _ in ()).throw(
        RuntimeError("synthetic event metadata failure")
    )
    result = engine.calculate_local(
        Observer(10, 20), "2026-08-12", include_sunrise_sunset=False,
        include_shadow_metrics=False, include_planets=False,
    )
    assert result is not None
    assert result.contact_events == {}
    assert any("C1 event metadata unavailable" in warning for warning in result.warnings)
    assert any("Maximum event metadata unavailable" in warning for warning in result.warnings)


def _patch_limb_pipeline(monkeypatch):
    from eclipsekit import limb as limb_module
    from eclipsekit import geometry
    from eclipsekit.limb import LunarLimbPrediction

    monkeypatch.setattr(geometry, "position_angle", lambda *args: 30.0)
    monkeypatch.setattr(
        limb_module, "compute_moon_libration_and_axis", lambda *args: (1.0, 2.0, 5.0)
    )
    monkeypatch.setattr(
        limb_module, "contact_selenographic_point", lambda *args: (3.0, 4.0)
    )
    monkeypatch.setattr(
        limb_module,
        "predict_lunar_limb",
        lambda model, query: LunarLimbPrediction(
            altitude_m=120.0,
            model_name="limb fixture",
            model_type="custom",
            source="test data only",
            uncertainty_m=7.5,
        ),
    )


def test_calculate_local_applies_lunar_limb_model_and_propagates_metadata(monkeypatch):
    engine, _ = configured_local_engine(monkeypatch)
    _patch_limb_pipeline(monkeypatch)
    corrected_roots = iter([1.79, 1.94, 2.06, 2.21])
    engine._contact_residual = lambda observer, jd, mode, radius: jd - 2.0
    engine._solve_root = lambda function, start, end: next(corrected_roots)

    result = engine.calculate_local(
        Observer(42.6, -5.57), "2026-08-12", limb_model=object(),
        include_sunrise_sunset=False, include_shadow_metrics=False, include_planets=False,
    )

    assert set(result.limb_corrected_contacts) == {"C1", "C2", "C3", "C4"}
    c1 = result.limb_corrected_contacts["C1"]
    assert c1.time.tt == pytest.approx(1.79)
    assert c1.delta_seconds == pytest.approx((1.79 - 1.8) * 86400)
    assert c1.predicted_terrain_altitude_m == pytest.approx(120.0)
    assert c1.corrected_moon_radius_km == pytest.approx(engine.moon_radius_visual_km + 0.12)
    assert c1.model_name == "limb fixture"
    assert c1.model_source == "test data only"
    assert c1.altitude_uncertainty_m == pytest.approx(7.5)
    assert result.limb_corrected_duration_seconds == pytest.approx((2.06 - 1.94) * 86400)
    assert result.limb_corrected_maximum.tt == pytest.approx(2.0)
    assert not any("Lunar-limb" in warning for warning in result.warnings)


def test_calculate_local_records_limb_no_sign_change_without_dropping_geometric_contacts(monkeypatch):
    engine, _ = configured_local_engine(monkeypatch)
    _patch_limb_pipeline(monkeypatch)
    engine._contact_residual = lambda observer, jd, mode, radius: 1.0
    engine._solve_root = lambda *args, **kwargs: pytest.fail("root solver must not run without a sign change")

    result = engine.calculate_local(
        Observer(42.6, -5.57), "2026-08-12", limb_model=object(),
        include_sunrise_sunset=False, include_shadow_metrics=False, include_planets=False,
    )

    assert result.eclipse_type == "total"
    assert len(result.limb_corrected_contacts) == 4
    assert all(value.time is None and value.delta_seconds is None for value in result.limb_corrected_contacts.values())
    assert result.limb_corrected_duration_seconds is None
    assert sum("no sign-changing root" in warning for warning in result.warnings) == 4


def test_calculate_local_catches_lunar_limb_prediction_failure(monkeypatch):
    from eclipsekit import limb as limb_module
    from eclipsekit import geometry

    engine, _ = configured_local_engine(monkeypatch)
    monkeypatch.setattr(geometry, "position_angle", lambda *args: 30.0)
    monkeypatch.setattr(
        limb_module, "compute_moon_libration_and_axis", lambda *args: (1.0, 2.0, 5.0)
    )
    monkeypatch.setattr(
        limb_module, "contact_selenographic_point", lambda *args: (3.0, 4.0)
    )
    monkeypatch.setattr(
        limb_module, "predict_lunar_limb",
        lambda *args: (_ for _ in ()).throw(RuntimeError("outside model coverage")),
    )
    result = engine.calculate_local(
        Observer(42.6, -5.57), "2026-08-12", limb_model=object(),
        include_sunrise_sunset=False, include_shadow_metrics=False, include_planets=False,
    )
    assert result is not None
    assert result.limb_corrected_contacts == {}
    assert any("Lunar-limb correction was not applied" in warning for warning in result.warnings)


def test_calculate_local_populates_sunrise_and_sunset_when_almanac_succeeds(monkeypatch):
    import sys
    from types import ModuleType, SimpleNamespace

    engine, _ = configured_local_engine(monkeypatch)
    engine.eph = {"earth": object()}
    calls = {}
    skyfield = ModuleType("skyfield")
    almanac = ModuleType("skyfield.almanac")
    api = ModuleType("skyfield.api")
    skyfield.almanac = almanac
    skyfield.api = api

    def latlon(**kwargs):
        calls["observer"] = kwargs
        return "topos"

    almanac.sunrise_sunset = lambda eph, topos: ("sunrise-set-function", eph, topos)

    def find_discrete(start, end, function):
        calls["search"] = (start.tt, end.tt, function)
        return [FakeTime(1.82), FakeTime(2.18)], [1, 0]

    almanac.find_discrete = find_discrete
    api.wgs84 = SimpleNamespace(latlon=latlon)
    monkeypatch.setitem(sys.modules, "skyfield", skyfield)
    monkeypatch.setitem(sys.modules, "skyfield.almanac", almanac)
    monkeypatch.setitem(sys.modules, "skyfield.api", api)

    observer = Observer(42.6, -5.57, elevation_m=800.0)
    result = engine.calculate_local(
        observer, "2026-08-12", include_sunrise_sunset=True,
        include_shadow_metrics=False, include_planets=False,
    )

    assert result.sunrise.tt == pytest.approx(1.82)
    assert result.sunset.tt == pytest.approx(2.18)
    assert calls["observer"] == {
        "latitude_degrees": 42.6, "longitude_degrees": -5.57, "elevation_m": 800.0,
    }
    assert calls["search"][:2] == pytest.approx((1.8, 2.2))


def test_calculate_local_passes_optional_horizon_profile_to_all_events(monkeypatch):
    engine, _ = configured_local_engine(monkeypatch)
    profile = HorizonProfile.flat(6.0, name="local-skyline")
    captured = {}
    geometry = object()

    def build_event(observer, observer_sf, name, event_type, event_time, **kwargs):
        captured[name] = kwargs.get("horizon_profile")
        return {"name": name, "type": event_type, "time": event_time.tt}

    engine._build_contact_event = build_event
    def build_observation_geometry(observer, when, *, horizon_profile):
        captured["maximum_geometry_profile"] = horizon_profile
        return geometry

    engine.calculate_observation_geometry = build_observation_geometry

    result = engine.calculate_local(
        Observer(42.6, -5.57), "2026-08-12", horizon_profile=profile,
        include_sunrise_sunset=False, include_shadow_metrics=False, include_planets=False,
    )

    assert set(captured) == {"C1", "C2", "C3", "C4", "MAXIMUM", "maximum_geometry_profile"}
    assert all(captured[name] is profile for name in ("C1", "C2", "C3", "C4", "MAXIMUM"))
    assert captured["maximum_geometry_profile"] is profile
    assert result.observation_geometry is geometry
