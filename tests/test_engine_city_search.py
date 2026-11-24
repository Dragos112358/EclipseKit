from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from eclipsekit.cities import CityCatalog
from eclipsekit.models import City

from test_engine_helpers import FakeTime, bare_engine


def install_fake_itrs(monkeypatch):
    skyfield = ModuleType("skyfield")
    framelib = ModuleType("skyfield.framelib")
    framelib.itrs = object()
    skyfield.framelib = framelib
    monkeypatch.setitem(sys.modules, "skyfield", skyfield)
    monkeypatch.setitem(sys.modules, "skyfield.framelib", framelib)


class NodeAt:
    def __init__(self, engine, times):
        self.engine = engine
        tt = np.asarray(getattr(times, "tt", times), dtype=float)
        self.count = int(tt.size) if tt.ndim else 1

    def observe(self, body):
        if body is self.engine.sun:
            vector = np.vstack((np.full(self.count, 150_000_000.0),
                                np.zeros(self.count), np.zeros(self.count)))
        else:
            vector = np.vstack((np.full(self.count, 384_000.0),
                                np.zeros(self.count), np.zeros(self.count)))
        return NodeApparent(vector)


class NodeApparent:
    def __init__(self, vector):
        self.vector = vector

    def apparent(self):
        return self

    def frame_xyz(self, frame):
        return SimpleNamespace(km=self.vector)


def city_search_engine(monkeypatch):
    install_fake_itrs(monkeypatch)
    engine = bare_engine()
    engine.find_global_maximum = lambda when: FakeTime(2.0)
    engine.earth = SimpleNamespace(at=lambda times: NodeAt(engine, times))
    engine.ts.tt_jd = lambda jd: FakeTime(jd)
    return engine


def sample_catalog():
    return CityCatalog([
        City("Day-side", "Test", 0.0, 0.0, 0.0),
        City("Night-side", "Test", 0.0, 180.0, 0.0),
    ])


def test_search_cities_vectorizes_batches_and_filters_night_side(monkeypatch):
    engine = city_search_engine(monkeypatch)
    catalog = sample_catalog()

    hits = engine.search_cities(
        "date", catalog, country="Test", min_magnitude=0.1,
        search_radius_hours=1.0, coarse_steps=5, refinement_iterations=3,
        batch_size=1, include_contacts=False,
    )

    assert len(hits) == 1
    assert hits[0].city.name == "Day-side"
    assert hits[0].magnitude > 0.9
    assert hits[0].eclipse_type in {"total", "annular"}
    assert hits[0].contacts is None
    assert hits[0].limb_corrected_contacts == {}


def test_search_cities_can_attach_local_contacts_and_use_limb_model_alias(monkeypatch):
    engine = city_search_engine(monkeypatch)
    catalog = sample_catalog()
    local_result = SimpleNamespace(
        contacts=object(), limb_corrected_contacts={"C1": "corrected"},
        maximum=FakeTime(2.001), magnitude=1.02, obscuration_percent=99.0,
        eclipse_type="total", sun_altitude_deg=30.0,
    )
    calls = {}

    def calculate_local(observer, when, **kwargs):
        calls.update(observer=observer, when=when, kwargs=kwargs)
        return local_result

    engine.calculate_local = calculate_local
    hits = engine.search_cities(
        "date", catalog, country="Test", min_magnitude=0.1,
        search_radius_hours=1.0, coarse_steps=5, refinement_iterations=2,
        batch_size=2, include_contacts=True, limb_model="test-limb-model",
    )

    assert len(hits) == 1
    assert hits[0].contacts is local_result.contacts
    assert hits[0].limb_corrected_contacts == {"C1": "corrected"}
    assert hits[0].maximum.tt == pytest.approx(2.001)
    assert hits[0].magnitude == pytest.approx(1.02)
    assert calls["kwargs"]["limb_corrector"] == "test-limb-model"


def test_search_cities_contact_fallback_preserves_vectorized_result(monkeypatch):
    engine = city_search_engine(monkeypatch)
    engine.calculate_local = lambda *args, **kwargs: None
    hits = engine.search_cities(
        "date", sample_catalog(), country="Test", min_magnitude=0.1,
        search_radius_hours=1.0, coarse_steps=5, refinement_iterations=2,
        batch_size=2, include_contacts=True,
    )
    assert len(hits) == 1
    assert hits[0].contacts is None
    assert hits[0].maximum.tt != 2.0
    assert hits[0].sun_altitude_deg > 0.0


def test_search_cities_returns_empty_when_all_samples_are_night_side(monkeypatch):
    engine = city_search_engine(monkeypatch)
    catalog = CityCatalog([City("Night", "Test", 0.0, 180.0, 0.0)])
    assert engine.search_cities(
        "date", catalog, country="Test", min_magnitude=0.001,
        search_radius_hours=1.0, coarse_steps=5, batch_size=1,
    ) == []




def test_iter_search_cities_streams_batch_hits_and_search_cities_keeps_sorted_api(monkeypatch):
    engine = city_search_engine(monkeypatch)
    catalog = CityCatalog([
        City("Day-side A", "Test", 0.0, 0.0, 0.0),
        City("Night-side", "Test", 0.0, 180.0, 0.0),
        City("Day-side B", "Test", 1.0, 0.0, 0.0),
        City("Night-side B", "Test", -1.0, 180.0, 0.0),
    ])
    kwargs = dict(
        country="Test", min_magnitude=0.1, search_radius_hours=1.0,
        coarse_steps=5, refinement_iterations=4, batch_size=1,
    )
    streamed = engine.iter_search_cities("date", catalog, **kwargs)
    assert iter(streamed) is streamed
    streamed_hits = list(streamed)
    sorted_hits = engine.search_cities("date", catalog, **kwargs)
    assert [hit.city.name for hit in sorted_hits] == [hit.city.name for hit in streamed_hits]
    assert [hit.magnitude for hit in sorted_hits] == pytest.approx(
        [hit.magnitude for hit in streamed_hits], rel=0.0, abs=1e-12
    )
    assert [hit.maximum.tt for hit in sorted_hits] == pytest.approx(
        [hit.maximum.tt for hit in streamed_hits], rel=0.0, abs=1e-12
    )


def test_iter_search_cities_yields_before_processing_later_batches(monkeypatch):
    engine = city_search_engine(monkeypatch)
    catalog = CityCatalog([
        City("Day-side A", "Test", 0.0, 0.0, 0.0),
        City("Day-side B", "Test", 1.0, 0.0, 0.0),
    ])
    streamed = engine.iter_search_cities(
        "date", catalog, country="Test", min_magnitude=0.1,
        search_radius_hours=1.0, coarse_steps=5, refinement_iterations=2,
        batch_size=1,
    )
    first = next(streamed)
    assert first.city.name == "Day-side A"


def test_search_cities_rejects_invalid_batch_settings(monkeypatch):
    engine = city_search_engine(monkeypatch)
    for value in (0, -1, True, 1.5, "2"):
        with pytest.raises(ValueError, match="batch_size must be >= 1"):
            engine.search_cities("date", sample_catalog(), batch_size=value)
