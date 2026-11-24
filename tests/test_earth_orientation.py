from types import SimpleNamespace

import pytest

from eclipsekit.earth_orientation import EarthOrientationConfig, describe_time_scale


class FakeLoader:
    def __init__(self):
        self.calls = []

    def timescale(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(mode_call=kwargs)


def test_builtin_mode_uses_skyfield_bundled_tables():
    loader = FakeLoader()
    result = EarthOrientationConfig.builtin().create_timescale(loader)
    assert result.mode_call == {}


def test_iers_mode_uses_external_iers_file():
    loader = FakeLoader()
    result = EarthOrientationConfig.iers().create_timescale(loader)
    assert result.mode_call == {"builtin": False}


def test_fixed_delta_t_mode_passes_exact_value_to_skyfield():
    loader = FakeLoader()
    result = EarthOrientationConfig.fixed(71.4).create_timescale(loader)
    assert result.mode_call == {"delta_t": 71.4}


def test_fixed_delta_t_requires_finite_value():
    with pytest.raises(ValueError, match="required"):
        EarthOrientationConfig(mode="fixed_delta_t")
    with pytest.raises(ValueError, match="finite"):
        EarthOrientationConfig.fixed(float("nan"))


def test_delta_t_override_rejected_for_other_modes():
    with pytest.raises(ValueError, match="only valid"):
        EarthOrientationConfig(mode="iers", fixed_delta_t_seconds=71.4)


def test_unknown_mode_rejected():
    with pytest.raises(ValueError, match="mode must"):
        EarthOrientationConfig(mode="best_guess")  # type: ignore[arg-type]


def test_time_scale_diagnostics_flags_non_physical_dut1_for_fixed_mode():
    fake_time = SimpleNamespace(
        delta_t=71.4,
        dut1=-2.216,
        utc_iso=lambda: "2026-08-12T18:30:00Z",
    )
    info = describe_time_scale(fake_time, "fixed_delta_t")
    assert info["delta_t_seconds"] == pytest.approx(71.4)
    assert info["dut1_seconds"] == pytest.approx(-2.216)
    assert info["dut1_within_utc_limit"] is False
    assert "historical-prediction" in info["warning"]


def test_time_scale_diagnostics_accepts_iers_dut1():
    fake_time = SimpleNamespace(
        delta_t=69.172744,
        dut1=0.011256,
        utc_iso=lambda: "2026-08-12T18:30:00Z",
    )
    info = describe_time_scale(fake_time, "iers")
    assert info["dut1_within_utc_limit"] is True
    assert "warning" not in info
