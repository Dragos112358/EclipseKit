from __future__ import annotations

from types import SimpleNamespace

import pytest

from eclipsekit import extensions
from eclipsekit.api import LunarDEMReader


class FakeEntryPoint:
    def __init__(self, group: str, name: str, value: str, loaded=None, error=None, dist=None):
        self.group = group
        self.name = name
        self.value = value
        self._loaded = loaded
        self._error = error
        self.dist = dist
        self.load_calls = 0

    def load(self):
        self.load_calls += 1
        if self._error is not None:
            raise self._error
        return self._loaded


class FakeEntryPoints(list):
    def select(self, *, group: str):
        return [item for item in self if item.group == group]


def _patch_entry_points(monkeypatch, points):
    monkeypatch.setattr(extensions.metadata, "entry_points", lambda: FakeEntryPoints(points))


def test_discovery_reads_metadata_without_loading_extension_code(monkeypatch):
    point = FakeEntryPoint(
        "eclipsekit.lunar_limb_models", "demo", "demo_plugin:factory", loaded=lambda: object(),
        dist=SimpleNamespace(metadata={"Name": "demo-plugin"}, version="1.2.3"),
    )
    _patch_entry_points(monkeypatch, [point])
    found = extensions.discover_extensions()
    assert len(found) == 1
    assert found[0].name == "demo"
    assert found[0].distribution == "demo-plugin"
    assert found[0].version == "1.2.3"
    assert point.load_calls == 0


def test_discovery_filters_to_requested_group_and_sorts(monkeypatch):
    points = [
        FakeEntryPoint("eclipsekit.dem_readers", "zeta", "zeta:factory"),
        FakeEntryPoint("eclipsekit.lunar_limb_models", "beta", "beta:factory"),
        FakeEntryPoint("eclipsekit.lunar_limb_models", "alpha", "alpha:factory"),
    ]
    _patch_entry_points(monkeypatch, points)
    assert [item.name for item in extensions.discover_extensions("eclipsekit.lunar_limb_models")] == [
        "alpha", "beta"
    ]


def test_discovery_rejects_unknown_extension_group():
    with pytest.raises(ValueError, match="Unsupported"):
        extensions.discover_extensions("arbitrary.import.group")


def test_load_extension_returns_factory_without_instantiating_it(monkeypatch):
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return "provider"

    point = FakeEntryPoint("eclipsekit.lunar_limb_models", "test-provider", "provider:factory", factory)
    _patch_entry_points(monkeypatch, [point])
    loaded = extensions.load_extension("test-provider", "eclipsekit.lunar_limb_models")
    assert loaded is factory
    assert calls == []
    assert loaded(resolution=3) == "provider"
    assert calls == [{"resolution": 3}]


def test_load_extension_reports_missing_ambiguous_and_broken_plugins(monkeypatch):
    _patch_entry_points(monkeypatch, [])
    with pytest.raises(extensions.UnknownExtensionError):
        extensions.load_extension("missing", "eclipsekit.dem_readers")

    duplicate = [
        FakeEntryPoint("eclipsekit.dem_readers", "same", "a:factory", lambda: None),
        FakeEntryPoint("eclipsekit.dem_readers", "same", "b:factory", lambda: None),
    ]
    _patch_entry_points(monkeypatch, duplicate)
    with pytest.raises(extensions.AmbiguousExtensionError):
        extensions.load_extension("same", "eclipsekit.dem_readers")

    broken = FakeEntryPoint(
        "eclipsekit.dem_readers", "broken", "bad:factory", error=ImportError("missing dependency")
    )
    _patch_entry_points(monkeypatch, [broken])
    with pytest.raises(extensions.ExtensionLoadError, match="missing dependency"):
        extensions.load_extension("broken", "eclipsekit.dem_readers")


def test_load_extension_rejects_non_callable_entry_point(monkeypatch):
    point = FakeEntryPoint("eclipsekit.dem_readers", "not-a-factory", "bad:value", loaded=42)
    _patch_entry_points(monkeypatch, [point])
    with pytest.raises(extensions.ExtensionLoadError, match="callable factory"):
        extensions.load_extension("not-a-factory", "eclipsekit.dem_readers")


def test_load_extension_validates_name_and_group(monkeypatch):
    _patch_entry_points(monkeypatch, [])
    with pytest.raises(ValueError, match="name"):
        extensions.load_extension(" ", "eclipsekit.dem_readers")
    with pytest.raises(ValueError, match="Unsupported"):
        extensions.load_extension("plugin", "unknown")


def test_lunar_dem_reader_protocol_accepts_structural_provider():
    class Provider:
        metadata = object()

        def predict_altitude_m(self, latitude_deg: float, longitude_deg: float) -> float:
            return latitude_deg + longitude_deg

    assert isinstance(Provider(), LunarDEMReader)
