"""Isolated tests for ephemeris loading; no network or real BSP kernel is required."""

from __future__ import annotations

import sys
from types import ModuleType

import pytest

from eclipsekit.earth_orientation import EarthOrientationConfig
from eclipsekit.ephemeris import EphemerisContext


class FakeTimeScale:
    pass


class FakeKernel(dict):
    def __init__(self):
        super().__init__({name: object() for name in ("earth", "sun", "moon")})


class FakeLoader:
    instances = []

    def __init__(self, directory, verbose=False):
        self.directory = directory
        self.verbose = verbose
        self.timescale_calls = []
        self.download_calls = []
        self.registry_calls = []
        self.ts = FakeTimeScale()
        self.__class__.instances.append(self)

    def timescale(self, **kwargs):
        self.timescale_calls.append(kwargs)
        return self.ts

    def download(self, url):
        self.download_calls.append(url)
        from pathlib import Path

        destination = Path(self.directory) / url.rsplit("/", 1)[-1]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake-spk")
        return str(destination)

    def __call__(self, name):
        self.registry_calls.append(name)
        return FakeKernel()


@pytest.fixture
def fake_skyfield(monkeypatch):
    FakeLoader.instances.clear()
    loaded_paths = []

    def load_file(path):
        loaded_paths.append(path)
        return FakeKernel()

    skyfield = ModuleType("skyfield")
    api = ModuleType("skyfield.api")
    api.Loader = FakeLoader
    api.load_file = load_file
    skyfield.api = api
    monkeypatch.setitem(sys.modules, "skyfield", skyfield)
    monkeypatch.setitem(sys.modules, "skyfield.api", api)
    return {"loaded_paths": loaded_paths}


def test_in_memory_ephemeris_and_builtin_timescale(fake_skyfield, tmp_path):
    kernel = FakeKernel()
    context = EphemerisContext(kernel, cache_dir=tmp_path)

    assert context.ephemeris is kernel
    assert context.kernel_source == "in-memory ephemeris object"
    assert context.ts is FakeLoader.instances[-1].ts
    assert FakeLoader.instances[-1].timescale_calls == [{}]
    assert context.time_scale_mode == "builtin"
    assert context.earth is kernel["earth"]
    assert context.sun is kernel["sun"]
    assert context.moon is kernel["moon"]


def test_explicit_timescale_is_used_without_creating_another(fake_skyfield, tmp_path):
    kernel = FakeKernel()
    ts = FakeTimeScale()
    context = EphemerisContext(kernel, cache_dir=tmp_path, timescale=ts)

    assert context.ts is ts
    assert context.time_scale_mode == "explicit_timescale"
    assert FakeLoader.instances[-1].timescale_calls == []


def test_earth_orientation_modes_are_forwarded_to_loader(fake_skyfield, tmp_path):
    for config, expected in (
        (EarthOrientationConfig.iers(), {"builtin": False}),
        (EarthOrientationConfig.fixed(71.4), {"delta_t": 71.4}),
    ):
        EphemerisContext(FakeKernel(), cache_dir=tmp_path, earth_orientation=config)
        assert FakeLoader.instances[-1].timescale_calls == [expected]


def test_local_bsp_path_is_loaded_as_absolute_path(fake_skyfield, tmp_path):
    kernel_path = tmp_path / "local.bsp"
    kernel_path.write_bytes(b"not a real SPK; load_file is mocked")

    context = EphemerisContext(kernel_path, cache_dir=tmp_path / "cache")

    assert context.kernel_source == str(kernel_path.resolve())
    assert fake_skyfield["loaded_paths"] == [str(kernel_path.resolve())]


def test_explicit_url_is_downloaded_and_loaded(fake_skyfield, tmp_path):
    url = "https://example.invalid/kernels/custom.bsp"
    context = EphemerisContext(url, cache_dir=tmp_path)

    loader = FakeLoader.instances[-1]
    assert loader.download_calls == [url]
    assert context.kernel_source == url
    assert fake_skyfield["loaded_paths"] == [str(tmp_path / "custom.bsp")]


def test_known_jpl_kernel_uses_official_naif_directory(fake_skyfield, tmp_path):
    context = EphemerisContext("de440s", cache_dir=tmp_path)

    loader = FakeLoader.instances[-1]
    assert loader.download_calls == [
        "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp"
    ]
    assert context.kernel_source == "de440s.bsp"
    assert fake_skyfield["loaded_paths"] == [str(tmp_path / "de440s.bsp")]


def test_de430_kernel_name_downloads_from_official_naif_directory(fake_skyfield, tmp_path):
    context = EphemerisContext("de430", cache_dir=tmp_path)

    loader = FakeLoader.instances[-1]
    assert loader.download_calls == [
        "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de430.bsp"
    ]
    assert context.kernel_source == "de430.bsp"
    assert fake_skyfield["loaded_paths"] == [str(tmp_path / "de430.bsp")]


def test_missing_path_like_bsp_fails_clearly_instead_of_registry_download(
    fake_skyfield, tmp_path
):
    missing = tmp_path / "data" / "de430.bsp"
    with pytest.raises(FileNotFoundError, match="Local ephemeris kernel not found"):
        EphemerisContext(missing, cache_dir=tmp_path / "cache")
    assert FakeLoader.instances[-1].download_calls == []
    assert FakeLoader.instances[-1].registry_calls == []


def test_known_jpl_kernel_reuses_cached_file(fake_skyfield, tmp_path):
    cached = tmp_path / "de440s.bsp"
    cached.write_bytes(b"cached fake data")
    context = EphemerisContext("DE440S", cache_dir=tmp_path)

    assert FakeLoader.instances[-1].download_calls == []
    assert context.kernel_source == "de440s.bsp"
    assert fake_skyfield["loaded_paths"] == [str(cached)]


def test_unregistered_bsp_name_uses_loader_registry(fake_skyfield, tmp_path):
    context = EphemerisContext("custom-kernel", cache_dir=tmp_path)

    assert FakeLoader.instances[-1].registry_calls == ["custom-kernel.bsp"]
    assert context.kernel_source == "custom-kernel.bsp"


def test_path_like_non_bsp_kernel_is_rejected(fake_skyfield, tmp_path):
    invalid_path = tmp_path / "folder" / "kernel.txt"
    with pytest.raises(ValueError, match="local .bsp file"):
        EphemerisContext(invalid_path, cache_dir=tmp_path / "cache")


def test_explicit_timescale_and_earth_orientation_are_mutually_exclusive(
    fake_skyfield, tmp_path
):
    with pytest.raises(ValueError, match="not both"):
        EphemerisContext(
            FakeKernel(), cache_dir=tmp_path, timescale=FakeTimeScale(),
            earth_orientation=EarthOrientationConfig.iers(),
        )


def test_missing_required_body_segments_raise_clear_error(fake_skyfield, tmp_path):
    with pytest.raises(ValueError, match="Earth, Sun, and Moon"):
        EphemerisContext({"earth": object(), "sun": object()}, cache_dir=tmp_path)


def test_custom_body_names_are_resolved_and_retained(fake_skyfield, tmp_path):
    kernel = FakeKernel()
    kernel.update({"399": object(), "10": object(), "301": object()})
    context = EphemerisContext(
        kernel, cache_dir=tmp_path,
        body_names={"earth": "399", "sun": "10", "moon": "301"},
    )

    assert context.body_names == {"earth": "399", "sun": "10", "moon": "301"}
    assert context.earth is kernel["399"]
    assert context.sun is kernel["10"]
    assert context.moon is kernel["301"]


def test_optional_body_returns_none_when_segment_is_absent(fake_skyfield, tmp_path):
    context = EphemerisContext(FakeKernel(), cache_dir=tmp_path)
    assert context.optional_body("not-present") is None


def test_optional_body_returns_existing_segment(fake_skyfield, tmp_path):
    kernel = FakeKernel()
    mars = object()
    kernel["mars"] = mars
    context = EphemerisContext(kernel, cache_dir=tmp_path)
    assert context.optional_body("mars") is mars


def test_from_jpl_delegates_to_constructor(fake_skyfield, tmp_path):
    context = EphemerisContext.from_jpl("de441", cache_dir=tmp_path)
    assert context.kernel_source == "de441.bsp"
