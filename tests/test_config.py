
import json

import pytest

from eclipsekit import (
    AtmosphereConfig,
    ContactModelConfig,
    EarthOrientationConfig,
    EclipseConfig,
    EclipseEngine,
    EphemerisConfig,
    SolverConfig,
)
from eclipsekit.geometry import (
    MOON_RADIUS_PEAKS_KM,
    MOON_RADIUS_VALLEYS_KM,
    MOON_RADIUS_VISUAL_KM,
    MOON_RADIUS_XAVIER_KM,
    SUN_RADIUS_KM,
)


def test_default_eclipse_config_preserves_legacy_engine_defaults():
    config = EclipseConfig()
    assert config.ephemeris.kernel == "de440s"
    assert config.ephemeris.earth_orientation.mode == "builtin"
    assert config.contacts.sun_radius_km == SUN_RADIUS_KM
    assert config.contacts.moon_radius_external_km == MOON_RADIUS_PEAKS_KM
    assert config.contacts.moon_radius_internal_km == MOON_RADIUS_VALLEYS_KM
    assert config.contacts.moon_radius_visual_km == MOON_RADIUS_VISUAL_KM
    assert config.contacts.moon_radius_shadow_km == MOON_RADIUS_XAVIER_KM
    assert config.solver.root_method == "bisection"
    assert config.solver.auto_expand_bracket is True
    assert config.solver.detect_tangent_contacts is True
    assert config.atmosphere.refraction_enabled is True


def test_ephemeris_config_rejects_unknown_body_name_key():
    with pytest.raises(ValueError, match="body_names keys"):
        EphemerisConfig(body_names={"mars": "mars"})


def test_ephemeris_config_rejects_timescale_and_orientation_together():
    with pytest.raises(ValueError, match="not both"):
        EphemerisConfig(timescale=object())


def test_contact_model_config_validates_positive_radii():
    with pytest.raises(ValueError, match="finite positive"):
        ContactModelConfig(moon_radius_visual_km=0.0)


def test_solver_config_validates_supported_methods_and_expansion_settings():
    assert SolverConfig(root_method="brent").root_method == "brent"
    with pytest.raises(ValueError, match="root_method"):
        SolverConfig(root_method="newton")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive"):
        SolverConfig(root_tolerance_seconds=0.0)
    with pytest.raises(ValueError, match="at least 1"):
        SolverConfig(root_max_iterations=0)
    with pytest.raises(ValueError, match="greater than 1"):
        SolverConfig(bracket_expansion_factor=1.0)
    with pytest.raises(ValueError, match="at least 3"):
        SolverConfig(bracket_scan_samples=2)
    with pytest.raises(ValueError, match=">= 0"):
        SolverConfig(bracket_max_expansions=-1)


def test_atmosphere_config_validates_physical_values():
    with pytest.raises(ValueError, match="pressure_mbar"):
        AtmosphereConfig(pressure_mbar=-1.0)
    with pytest.raises(ValueError, match="absolute zero"):
        AtmosphereConfig(temperature_c=-273.15)


def test_atmosphere_can_disable_refraction_without_losing_station_pressure():
    atmosphere = AtmosphereConfig(refraction_enabled=False, pressure_mbar=900.0)
    assert atmosphere.pressure_mbar == 900.0
    assert atmosphere.refraction_enabled is False


def test_config_to_dict_is_json_friendly():
    config = EclipseConfig(
        ephemeris=EphemerisConfig.jpl("de440s", earth_orientation=EarthOrientationConfig.iers()),
        atmosphere=AtmosphereConfig(refraction_enabled=False),
    )
    summary = config.to_dict()
    assert summary["ephemeris"]["kernel"] == "de440s"
    assert summary["ephemeris"]["earth_orientation"] == "iers"
    assert summary["contacts"]["geometry"] == "spherical_discs"
    assert summary["solver"]["auto_expand_bracket"] is True
    assert summary["solver"]["detect_tangent_contacts"] is True
    assert summary["atmosphere"]["refraction_enabled"] is False
    json.dumps(summary)


def test_iau_mean_moon_uses_the_adopted_mean_radius():
    config = ContactModelConfig.iau_mean_moon()
    assert config.moon_radius_external_km == pytest.approx(1737.4)
    assert config.moon_radius_internal_km == pytest.approx(1737.4)


class _FakeContext:
    def __init__(self, ephemeris, **kwargs):
        self.ephemeris = ephemeris
        self.kwargs = kwargs
        self.ts = object()
        self.time_scale_mode = "fake"
        self.earth = object()
        self.sun = object()
        self.moon = object()


def test_engine_accepts_top_level_config(monkeypatch):
    monkeypatch.setattr("eclipsekit.engine.EphemerisContext", _FakeContext)
    config = EclipseConfig(
        ephemeris=EphemerisConfig.jpl("de440s", earth_orientation=EarthOrientationConfig.iers()),
        contacts=ContactModelConfig(sun_radius_km=695700.0),
        atmosphere=AtmosphereConfig(refraction_enabled=False, pressure_mbar=880.0),
    )
    engine = EclipseEngine(config=config)
    assert engine.config is config
    assert engine.context.ephemeris == "de440s"
    assert engine.sun_radius_km == 695700.0
    assert engine.pressure_mbar == 0.0  # refraction disabled for Skyfield altaz()
    assert engine.temperature_c == 15.0
    assert engine.context.kwargs["earth_orientation"].mode == "iers"


def test_engine_legacy_constructor_is_backwards_compatible(monkeypatch):
    monkeypatch.setattr("eclipsekit.engine.EphemerisContext", _FakeContext)
    engine = EclipseEngine("de432s", sun_radius_km=695700.0, pressure_mbar=900.0)
    assert engine.ephemeris_config.kernel == "de432s"
    assert engine.sun_radius_km == 695700.0
    assert engine.pressure_mbar == 900.0


def test_engine_rejects_mixed_config_and_legacy_overrides(monkeypatch):
    monkeypatch.setattr("eclipsekit.engine.EphemerisContext", _FakeContext)
    with pytest.raises(ValueError, match="not both"):
        EclipseEngine(config=EclipseConfig(), ephemeris="de440s")


def test_from_jpl_accepts_config_and_preserves_old_form(monkeypatch):
    monkeypatch.setattr("eclipsekit.engine.EphemerisContext", _FakeContext)
    config = EclipseConfig(ephemeris=EphemerisConfig.jpl("de440"))
    configured = EclipseEngine.from_jpl(config=config)
    legacy = EclipseEngine.from_jpl("de432s")
    assert configured.ephemeris_config.kernel == "de440"
    assert legacy.ephemeris_config.kernel == "de432s"


def test_engine_root_solver_uses_configured_tolerances(monkeypatch):
    captured = {}

    from eclipsekit.contacts import RootResult

    def fake_solve(function, start, end, **kwargs):
        captured.update(kwargs)
        return RootResult(
            root=(start + end) / 2.0, converged=True, status="converged",
            method=kwargs["method"], iterations=1, function_calls=3,
            bracket_start=start, bracket_end=end, residual=0.0,
        )

    monkeypatch.setattr("eclipsekit.engine.solve_root", fake_solve)
    engine = object.__new__(EclipseEngine)
    engine.solver_config = SolverConfig(
        root_tolerance_seconds=0.25,
        root_value_tolerance_deg=2e-9,
        root_max_iterations=123,
    )
    result = engine._solve_root(lambda value: value, 1.0, 3.0)
    assert result == 2.0
    assert captured["tolerance_days"] == pytest.approx(0.25 / 86400.0)
    assert captured["value_tolerance"] == pytest.approx(2e-9)
    assert captured["max_iterations"] == 123
    assert captured["method"] == "bisection"


def test_engine_detailed_contact_solver_returns_root_diagnostics():
    from types import SimpleNamespace
    from eclipsekit import Observer

    engine = object.__new__(EclipseEngine)
    engine.solver_config = SolverConfig(root_method="brent", auto_expand_bracket=False)
    engine.moon_radius_peaks_km = 1738.0
    engine.moon_radius_valleys_km = 1736.0
    engine._observer = lambda observer: "fake-observer"
    engine._contact_residual = lambda observer, jd, mode, radius: jd - 1.5
    engine.ts = SimpleNamespace(tt_jd=lambda jd: ("skyfield-time", jd))

    result = engine.solve_contact_detailed(
        Observer(0.0, 0.0), "external", 1.0, 2.0, auto_expand=False
    )
    assert result.converged is True
    assert result.status == "converged"
    assert result.method == "brent"
    assert result.root == pytest.approx(1.5)
    assert result.function_calls >= 3

    legacy_time = engine.solve_contact(
        Observer(0.0, 0.0), "external", 1.0, 2.0, auto_expand=False
    )
    assert legacy_time == ("skyfield-time", pytest.approx(1.5))


def test_engine_detailed_contact_solver_can_expand_bracket():
    from types import SimpleNamespace
    from eclipsekit import Observer

    engine = object.__new__(EclipseEngine)
    engine.solver_config = SolverConfig(
        root_method="brent", auto_expand_bracket=True,
        bracket_expansion_factor=2.0, bracket_max_expansions=5,
        bracket_max_span_seconds=1_000_000.0,
    )
    engine.moon_radius_peaks_km = 1738.0
    engine.moon_radius_valleys_km = 1736.0
    engine._observer = lambda observer: "fake-observer"
    engine._contact_residual = lambda observer, jd, mode, radius: jd - 5.0
    engine.ts = SimpleNamespace(tt_jd=lambda jd: ("skyfield-time", jd))

    result = engine.solve_contact_detailed(Observer(0.0, 0.0), "external", 0.0, 1.0)
    assert result.converged is True
    assert result.root == pytest.approx(5.0)
    assert result.bracket_start <= 5.0 <= result.bracket_end
