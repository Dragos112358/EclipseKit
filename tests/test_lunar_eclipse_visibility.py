from __future__ import annotations

import math
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from eclipsekit import Observer
from eclipsekit.cities import CityCatalog
from eclipsekit.models import City

from test_engine_helpers import FakeTime, FakeTimescale, bare_engine


def _time(value: float) -> FakeTime:
    return FakeTime(value)


def _event(
    *, p1=10.0, u1=10.10, u2=None, u3=None,
    u4=10.24, greatest=10.15, p4=10.30,
):
    contact_values = {
        "P1": _time(p1), "U1": _time(u1),
        "U2": _time(u2) if u2 is not None else None,
        "greatest": _time(greatest),
        "U3": _time(u3) if u3 is not None else None,
        "U4": _time(u4), "P4": _time(p4),
    }
    contacts = SimpleNamespace(
        p1=contact_values["P1"], u1=contact_values["U1"],
        u2=contact_values["U2"], greatest=contact_values["greatest"],
        u3=contact_values["U3"], u4=contact_values["U4"],
        p4=contact_values["P4"], as_dict=lambda: contact_values,
    )
    return SimpleNamespace(
        contacts=contacts,
        maximum=_time(greatest),
        penumbral_magnitude=0.25,
        umbral_magnitude=-0.2,
        eclipse_type="total" if u2 is not None and u3 is not None else "partial",
        to_dict=lambda **kwargs: {"eclipse_type": "partial"},
    )


class _Angle:
    def __init__(self, degrees):
        self.degrees = np.asarray(degrees, dtype=float)


class _Distance:
    def __init__(self, km):
        self.km = np.asarray(km, dtype=float)


class _TimeDependentMoon:
    def __init__(self, jd):
        self.jd = np.asarray(jd, dtype=float)

    def apparent(self):
        return self

    def altaz(self, **kwargs):
        # The centre crosses the horizon at JD 10.18 while the geocentric
        # greatest-eclipse instant is JD 10.15: the event becomes visible later.
        altitude = 24.0 * np.sin(2.0 * math.pi * (self.jd - 10.18) / 0.16)
        azimuth = np.full_like(altitude, 120.0)
        distance = np.full_like(altitude, 384_000.0)
        return _Angle(altitude), _Angle(azimuth), _Distance(distance)


class _LocalObserver:
    def at(self, when):
        return SimpleNamespace(
            observe=lambda body: _TimeDependentMoon(np.asarray(when.tt, dtype=float))
        )


def _install_time_formatter(monkeypatch):
    import eclipsekit.engine as engine_module

    monkeypatch.setattr(
        engine_module,
        "time_to_utc_iso",
        lambda value, **kwargs: f"JD-{float(value.tt):.8f}",
    )


def test_local_visibility_intersects_eclipse_with_moonrise_after_p1(monkeypatch):
    engine = bare_engine()
    engine.ts = FakeTimescale()
    engine._observer = lambda observer: _LocalObserver()
    engine.calculate_lunar_eclipse = lambda *args, **kwargs: _event(u1=10.12, u2=10.13, u3=10.21)
    _install_time_formatter(monkeypatch)

    result = engine.lunar_eclipse_local_visibility(
        Observer(45.0, 25.0, elevation_m=120.0, name="Test site"),
        "2027-07-18",
        apply_refraction=False,
        search_margin_hours=1.0,
        sample_interval_seconds=120.0,
    )

    assert result is not None
    assert result["visibility_status"] == "partially_visible"
    assert result["visible_at_greatest"] is False
    assert result["moonrise_utc"]
    assert result["moonset_utc"]
    assert result["observable_intervals"]
    assert result["observable_intervals"][0]["start_cause"] == "moonrise"
    assert result["observable_intervals"][0]["end_cause"] == "moonset"
    assert result["phase_visibility"]["penumbral"]["visible"] is True
    assert result["phase_visibility"]["partial"]["visible"] is True
    assert result["phase_visibility"]["partial"]["intervals"][0]["start_cause"] == "moonrise"
    assert result["phase_visibility"]["partial"]["intervals"][0]["end_cause"] == "U4"
    assert result["phase_visibility"]["totality"]["visible"] is True
    assert result["phase_visibility"]["totality"]["intervals"][0]["start_cause"] == "moonrise"
    assert result["phase_visibility"]["totality"]["intervals"][0]["end_cause"] == "U3"
    assert result["observer"]["elevation_m"] == 120.0
    assert result["altitude_profile"]
    assert result["contact_visibility"]["P1"]["visible"] is False
    assert result["contact_visibility"]["greatest"]["visible"] is False



class _ExactContactMoon:
    def __init__(self, jd):
        self.jd = np.asarray(jd, dtype=float)

    def apparent(self):
        return self

    def altaz(self, **kwargs):
        distance = np.full_like(self.jd, 384_000.0)
        semidiameter = np.degrees(np.arcsin(1737.4 / distance))
        # Clearance is exactly zero at P1 (JD 10.0), which is inserted into
        # the visibility sample grid as a known physical contact epoch.
        altitude = 100.0 * (self.jd - 10.0) - semidiameter
        azimuth = np.full_like(altitude, 90.0)
        return _Angle(altitude), _Angle(azimuth), _Distance(distance)


class _ExactContactObserver:
    def at(self, when):
        return SimpleNamespace(
            observe=lambda body: _ExactContactMoon(np.asarray(when.tt, dtype=float))
        )


def test_local_visibility_keeps_horizon_crossing_on_exact_sample(monkeypatch):
    engine = bare_engine()
    engine.ts = FakeTimescale()
    engine._observer = lambda observer: _ExactContactObserver()
    engine.calculate_lunar_eclipse = lambda *args, **kwargs: _event()
    _install_time_formatter(monkeypatch)

    result = engine.lunar_eclipse_local_visibility(
        Observer(0.0, 0.0),
        "2027-07-18",
        apply_refraction=False,
        search_margin_hours=1.0,
        sample_interval_seconds=600.0,
    )

    assert result is not None
    assert any(
        item["kind"] == "moonrise" and item["time_utc"] == "JD-10.00000000"
        for item in result["horizon_crossings"]
    )
    assert result["contact_visibility"]["P1"]["visible"] is True


def test_local_visibility_supports_horizon_profile_and_refraction_controls(monkeypatch):
    engine = bare_engine()
    engine.ts = FakeTimescale()
    engine._observer = lambda observer: _LocalObserver()
    engine.calculate_lunar_eclipse = lambda *args, **kwargs: _event()
    _install_time_formatter(monkeypatch)

    from eclipsekit.models import HorizonProfile

    result = engine.lunar_eclipse_local_visibility(
        Observer(45.0, 25.0, elevation_m=2500.0),
        "2027-07-18",
        horizon_profile=HorizonProfile.flat(5.0, name="ridge"),
        apply_refraction=True,
        pressure_mbar=760.0,
        temperature_c=5.0,
        limb_visibility="center",
        search_margin_hours=1.0,
        include_altitude_profile=False,
    )

    assert result is not None
    assert result["visibility_model"]["refraction_applied"] is True
    assert result["visibility_model"]["pressure_mbar"] == 760.0
    assert result["visibility_model"]["temperature_c"] == 5.0
    assert result["visibility_model"]["horizon_profile"] == "ridge"
    assert result["visibility_model"]["limb_visibility"] == "center"
    assert result["altitude_profile"] == []


def test_local_visibility_rejects_invalid_limb_mode():
    engine = bare_engine()
    with pytest.raises(ValueError, match="limb_visibility"):
        engine.lunar_eclipse_local_visibility(
            Observer(0.0, 0.0), "2027-07-18", limb_visibility="whole-moon"
        )


class _EarthAt:
    def __init__(self, when):
        self.when = when

    def observe(self, body):
        return _CityMoonPosition(self.when)


class _CityMoonPosition:
    def __init__(self, when):
        self.when = when

    def apparent(self):
        return self

    def frame_xyz(self, frame):
        values = np.asarray(self.when.tt, dtype=float)
        angle = 2.0 * math.pi * (values - 10.00) / 0.30
        x = 384_000.0 * np.cos(angle)
        y = 384_000.0 * np.sin(angle)
        z = np.zeros_like(x)
        if values.ndim == 0:
            return SimpleNamespace(km=np.array([float(x), float(y), 0.0]))
        return SimpleNamespace(km=np.vstack((x, y, z)))


def test_city_visibility_any_includes_city_visible_only_before_greatest(monkeypatch):
    skyfield = ModuleType("skyfield")
    framelib = ModuleType("skyfield.framelib")
    framelib.itrs = object()
    skyfield.framelib = framelib
    monkeypatch.setitem(sys.modules, "skyfield", skyfield)
    monkeypatch.setitem(sys.modules, "skyfield.framelib", framelib)

    engine = bare_engine()
    engine.ts = FakeTimescale()
    event = _event()
    engine.calculate_lunar_eclipse = lambda *args, **kwargs: event
    engine.earth = SimpleNamespace(at=lambda when: _EarthAt(when))
    catalog = CityCatalog([City("Test city", "Testland", 0.0, 0.0)])

    results = engine.lunar_eclipse_city_visibility(
        "2027-07-18", catalog, visibility_window="any", sample_interval_seconds=300.0
    )

    assert len(results) == 1
    assert results[0]["visible_at_maximum"] is False
    assert results[0]["visible_during_eclipse"] is True
    assert results[0]["first_visible_sample_utc"] is not None
    assert results[0]["last_visible_sample_utc"] is not None
