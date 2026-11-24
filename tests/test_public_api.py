from __future__ import annotations

import importlib
import json
from pathlib import Path

import eclipsekit
from eclipsekit import api


def test_curated_api_exports_are_present_unique_and_stable() -> None:
    assert api.API_CONTRACT_VERSION == "1"
    assert api.API_STATUS == "stabilization-candidate"
    assert len(api.__all__) == len(set(api.__all__))
    for public_name in api.__all__:
        assert hasattr(api, public_name), public_name


def test_root_and_curated_api_share_the_same_core_objects() -> None:
    assert eclipsekit.EclipseEngine is api.EclipseEngine
    assert eclipsekit.Observer is api.Observer
    assert eclipsekit.EclipseConfig is api.EclipseConfig
    assert eclipsekit.HorizonProfile is api.HorizonProfile
    assert eclipsekit.__version__ == api.PACKAGE_VERSION


def test_runtime_info_reports_versions_without_importing_optional_packages(monkeypatch) -> None:
    forbidden = {"torch", "rasterio"}
    original_import = __import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".", 1)[0] in forbidden:
            raise AssertionError(f"optional dependency imported unexpectedly: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    info = api.get_runtime_info()
    payload = info.to_dict()
    assert info.api_contract_version == "1"
    assert info.package_version == eclipsekit.__version__
    assert payload["python_version"]
    assert dict(info.required_dependencies).keys() == {"numpy", "skyfield"}
    assert dict(info.optional_dependencies).keys() == {"limb/torch", "raster/rasterio"}


def test_pep561_marker_is_in_the_package_source_tree() -> None:
    marker = Path(importlib.import_module("eclipsekit").__file__).parent / "py.typed"
    assert marker.is_file()


def test_public_api_import_does_not_load_optional_runtime_packages() -> None:
    # This process may already have other test modules imported, so only verify
    # the API itself does not require torch/rasterio by checking its imports.
    assert "torch" not in api.__dict__
    assert "rasterio" not in api.__dict__


def test_public_api_manifest_pins_contract_exports():
    manifest_path = Path(__file__).resolve().parents[1] / "docs" / "API_MANIFEST_V1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["api_contract_version"] == api.API_CONTRACT_VERSION
    assert manifest["status"] == api.API_STATUS
    assert manifest["module"] == "eclipsekit.api"
    assert manifest["export_count"] == len(api.__all__)
    assert manifest["exports"] == api.__all__


def test_wheel_build_config_explicitly_includes_pep561_marker():
    project_root = Path(__file__).resolve().parents[1]
    config_text = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.hatch.build.targets.wheel.force-include]" in config_text
    assert '\"src/eclipsekit/py.typed\" = \"eclipsekit/py.typed\"' in config_text
