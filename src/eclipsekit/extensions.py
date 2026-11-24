"""Explicit discovery/loading for third-party EclipseKit extensions.

Discovery reads entry-point metadata only. Extension modules are imported only
when :func:`load_extension` is called; nothing is auto-loaded at package import.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .limb import LunarLimbModel


EXTENSION_GROUPS = (
    "eclipsekit.lunar_limb_models",
    "eclipsekit.dem_readers",
)


class LunarLimbModelFactory(Protocol):
    """Static contract for an entry-point factory in the lunar-limb group."""

    def __call__(self, **configuration: Any) -> "LunarLimbModel": ...


@runtime_checkable
class LunarDEMReader(Protocol):
    """Minimum scalar sampling contract for third-party DEM reader providers."""

    metadata: object

    def predict_altitude_m(self, latitude_deg: float, longitude_deg: float) -> float: ...


class LunarDEMReaderFactory(Protocol):
    """Static contract for an entry-point factory in the DEM-reader group."""

    def __call__(self, source: str | Path, **options: Any) -> LunarDEMReader: ...


@dataclass(frozen=True, slots=True)
class ExtensionInfo:
    """Metadata for one registered third-party extension entry point."""

    group: str
    name: str
    value: str
    distribution: str | None = None
    version: str | None = None


class ExtensionError(RuntimeError):
    """Base class for controlled extension discovery/loading failures."""


class UnknownExtensionError(ExtensionError, LookupError):
    """Raised when no extension with the requested group/name is installed."""


class AmbiguousExtensionError(ExtensionError):
    """Raised when multiple distributions register the same group/name."""


class ExtensionLoadError(ExtensionError):
    """Raised when a registered entry point cannot be imported or is invalid."""


def _validate_group(group: str) -> str:
    if not isinstance(group, str) or group not in EXTENSION_GROUPS:
        allowed = ", ".join(EXTENSION_GROUPS)
        raise ValueError(f"Unsupported EclipseKit extension group; choose one of: {allowed}")
    return group


def _entry_points_for(group: str) -> tuple[Any, ...]:
    available = metadata.entry_points()
    if hasattr(available, "select"):
        selected = available.select(group=group)
    elif isinstance(available, dict):  # pragma: no cover - Python 3.10 compatibility
        selected = available.get(group, ())
    else:  # pragma: no cover - legacy SelectableGroups compatibility
        selected = [item for item in available if getattr(item, "group", None) == group]
    return tuple(selected)


def _entry_point_info(entry_point: Any) -> ExtensionInfo:
    distribution = getattr(entry_point, "dist", None)
    dist_name = None
    dist_version = None
    if distribution is not None:
        metadata_map = getattr(distribution, "metadata", {})
        dist_name = metadata_map.get("Name") if hasattr(metadata_map, "get") else None
        dist_version = getattr(distribution, "version", None)
    return ExtensionInfo(
        group=str(entry_point.group),
        name=str(entry_point.name),
        value=str(entry_point.value),
        distribution=str(dist_name) if dist_name else None,
        version=str(dist_version) if dist_version else None,
    )


def discover_extensions(group: str | None = None) -> tuple[ExtensionInfo, ...]:
    """Return installed extension metadata without importing extension code.

    Passing no group lists both supported groups. Duplicate registrations are
    returned as separate records so callers can detect and report conflicts.
    """
    groups = EXTENSION_GROUPS if group is None else (_validate_group(group),)
    records = [
        _entry_point_info(entry_point)
        for selected_group in groups
        for entry_point in _entry_points_for(selected_group)
    ]
    return tuple(sorted(records, key=lambda item: (
        item.group, item.name.casefold(), (item.distribution or "").casefold(), item.value
    )))


def load_extension(name: str, group: str) -> Any:
    """Load and return a registered extension callable by exact group and name.

    The returned object is not instantiated. The host application is
    responsible for passing its own validated configuration/paths to it.
    """
    selected_group = _validate_group(group)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("extension name must be a non-empty string")
    matches = [
        entry_point for entry_point in _entry_points_for(selected_group)
        if entry_point.name == name
    ]
    if not matches:
        raise UnknownExtensionError(
            f"No EclipseKit extension named {name!r} in group {selected_group!r}"
        )
    if len(matches) > 1:
        raise AmbiguousExtensionError(
            f"Multiple distributions register {name!r} in {selected_group!r}; "
            "resolve the duplicate installation before loading"
        )
    entry_point = matches[0]
    try:
        extension = entry_point.load()
    except Exception as exc:
        raise ExtensionLoadError(
            f"Could not load extension {name!r} from {selected_group!r}: {exc}"
        ) from exc
    if not callable(extension):
        raise ExtensionLoadError(
            f"Extension {name!r} in {selected_group!r} must expose a callable factory"
        )
    return extension


__all__ = [
    "EXTENSION_GROUPS", "LunarLimbModelFactory", "LunarDEMReader",
    "LunarDEMReaderFactory", "ExtensionInfo", "ExtensionError", "UnknownExtensionError",
    "AmbiguousExtensionError", "ExtensionLoadError", "discover_extensions", "load_extension",
]
