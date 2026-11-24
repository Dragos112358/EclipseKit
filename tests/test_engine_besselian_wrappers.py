from __future__ import annotations

from types import SimpleNamespace

import pytest

from eclipsekit import Observer
from eclipsekit import besselian as besselian_module

from test_engine_helpers import FakeTime, bare_engine


class RecordingBesselianSolver:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.__class__.instances.append(self)

    def calculate_local(self, elements, observer, **kwargs):
        self.calls.append((elements, observer, kwargs))
        callback = kwargs.get("delta_t_seconds")
        callback_value = callback(123.0) if callable(callback) else callback
        return {"center": kwargs["center_jd_tt"], "delta_t": callback_value}

    def find_global_maximum(self, elements, **kwargs):
        self.calls.append((elements, kwargs))
        return 456.0

    def global_central_line(self, elements, start, end, **kwargs):
        self.calls.append((elements, start, end, kwargs))
        return [(start, end, kwargs)]


@pytest.fixture(autouse=True)
def install_recording_solver(monkeypatch):
    RecordingBesselianSolver.instances.clear()
    monkeypatch.setattr(besselian_module, "BesselianSolver", RecordingBesselianSolver)


def test_calculate_local_besselian_uses_explicit_delta_t_and_default_center(monkeypatch):
    engine = bare_engine()
    engine.solver_config = object()
    elements = SimpleNamespace(epoch_tt_jd=2450000.5)
    observer = Observer(10, 20)

    result = engine.calculate_local_besselian(
        elements, observer, search_half_window_hours=3, delta_t_seconds=63.7,
    )

    assert result == {"center": 2450000.5, "delta_t": 63.7}
    instance = RecordingBesselianSolver.instances[-1]
    assert instance.kwargs["config"] == engine.config.besselian
    assert instance.calls[0][2]["search_half_window_hours"] == 3


def test_calculate_local_besselian_uses_engine_timescale_delta_t_callback(monkeypatch):
    engine = bare_engine()
    elements = SimpleNamespace(epoch_tt_jd=2450000.5)
    result = engine.calculate_local_besselian(elements, Observer(10, 20))

    assert result["center"] == 2450000.5
    assert result["delta_t"] == pytest.approx(70.0)


def test_calculate_local_besselian_accepts_numeric_and_timestamp_center(monkeypatch):
    engine = bare_engine()
    engine.time = lambda value: FakeTime(2450001.0)
    elements = SimpleNamespace(epoch_tt_jd=2450000.5)

    numeric = engine.calculate_local_besselian(elements, Observer(0, 0), center=2450002.0, delta_t_seconds=70)
    timestamp = engine.calculate_local_besselian(elements, Observer(0, 0), center="2026-08-12", delta_t_seconds=70)
    assert numeric["center"] == 2450002.0
    assert timestamp["center"] == 2450001.0


def test_find_global_maximum_besselian_uses_published_validity_by_default():
    engine = bare_engine()
    elements = SimpleNamespace(
        epoch_tt_jd=2450000.5, validity_start_hours=-4.0, validity_end_hours=4.0,
    )
    result = engine.find_global_maximum_besselian(elements)
    assert result.tt == 456.0
    _, kwargs = RecordingBesselianSolver.instances[-1].calls[0]
    assert kwargs["start_jd_tt"] == pytest.approx(2450000.5 - 4 / 24)
    assert kwargs["end_jd_tt"] == pytest.approx(2450000.5 + 4 / 24)


def test_find_global_maximum_besselian_accepts_explicit_numeric_and_time_bounds():
    engine = bare_engine()
    engine.time = lambda value: FakeTime(2450005.0)
    elements = SimpleNamespace(
        epoch_tt_jd=2450000.5, validity_start_hours=-4.0, validity_end_hours=4.0,
    )
    engine.find_global_maximum_besselian(elements, start=2450001.0, end="2026-08-12")
    _, kwargs = RecordingBesselianSolver.instances[-1].calls[0]
    assert kwargs["start_jd_tt"] == 2450001.0
    assert kwargs["end_jd_tt"] == 2450005.0


def test_besselian_global_shadow_path_passes_explicit_delta_t():
    engine = bare_engine()
    elements = object()
    result = engine.besselian_global_shadow_path(
        elements, 10.0, 12.0, samples=9, delta_t_seconds=63.7,
    )
    assert result[0][0:2] == (10.0, 12.0)
    _, start, end, kwargs = RecordingBesselianSolver.instances[-1].calls[0]
    assert (start, end) == (10.0, 12.0)
    assert kwargs == {"samples": 9, "delta_t_seconds": 63.7}


def test_besselian_global_shadow_path_uses_configured_delta_t_callback():
    engine = bare_engine()
    engine.time = lambda value: FakeTime({"start": 100.0, "end": 102.0}[value])
    engine.besselian_global_shadow_path(object(), "start", "end", samples=5)
    _, start, end, kwargs = RecordingBesselianSolver.instances[-1].calls[0]
    assert start == 100.0 and end == 102.0
    assert kwargs["samples"] == 5
    assert kwargs["delta_t_seconds"](100.0) == pytest.approx(70.0)
