"""Ephemeris loading and body-name resolution.

Kernel files are never bundled inside the EclipseKit wheel. A named JPL kernel is
cached separately by Skyfield; a local SPK/BSP path can be supplied by the user.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .earth_orientation import EarthOrientationConfig, describe_earth_orientation_source


_JPL_PLANETS_URL = (
    "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/"
)
_KNOWN_JPL_KERNELS = {"de432s.bsp", "de440s.bsp", "de440.bsp", "de441.bsp"}


def default_ephemeris_cache_dir() -> Path:
    """Return the default cache path, reusing a legacy PyEclipse cache if present."""
    primary = Path.home() / ".eclipsekit" / "ephemerides"
    legacy = Path.home() / ".pyeclipse" / "ephemerides"
    if not primary.exists() and legacy.exists():
        return legacy
    return primary


class EphemerisContext:
    def __init__(
        self,
        ephemeris: str | Path | Any,
        *,
        cache_dir: str | Path | None = None,
        timescale: Any | None = None,
        earth_orientation: EarthOrientationConfig | None = None,
        body_names: dict[str, str] | None = None,
    ) -> None:
        try:
            from skyfield.api import Loader, load_file
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Skyfield is required. Install it with: pip install skyfield") from exc

        if cache_dir is None:
            cache_dir = default_ephemeris_cache_dir()
        self.cache_dir = Path(cache_dir).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.loader = Loader(str(self.cache_dir), verbose=False)

        if hasattr(ephemeris, "__getitem__") and not isinstance(ephemeris, (str, Path)):
            self.ephemeris = ephemeris
            self.kernel_source = "in-memory ephemeris object"
        else:
            raw = str(ephemeris).strip()
            candidate = Path(raw).expanduser()
            if candidate.is_file():
                self.ephemeris = load_file(str(candidate.resolve()))
                self.kernel_source = str(candidate.resolve())
            elif raw.lower().startswith(("https://", "http://")):
                # Explicit URL: download into Skyfield's cache, then open the local SPK.
                local_file = self.loader.download(raw)
                self.ephemeris = load_file(str(local_file))
                self.kernel_source = raw
            else:
                name = raw.lower()
                if not name.endswith(".bsp") and "/" not in name and "\\" not in name:
                    name += ".bsp"
                if not name.endswith(".bsp"):
                    raise ValueError(
                        "ephemeris must be a local .bsp file, an HTTP(S) URL, or a JPL kernel name "
                        "such as 'de432s', 'de440s', 'de440', or 'de441'"
                    )
                if name in _KNOWN_JPL_KERNELS:
                    # Use the official NAIF SPK directory directly so the common DE
                    # kernels work even when a Skyfield release does not map the name.
                    local_file = self.cache_dir / name
                    if not local_file.is_file():
                        local_file = self.loader.download(_JPL_PLANETS_URL + name)
                    self.ephemeris = load_file(str(local_file))
                else:
                    # Other recognised kernels can still use Skyfield's name registry.
                    self.ephemeris = self.loader(name)
                self.kernel_source = name

        if timescale is not None and earth_orientation is not None:
            raise ValueError(
                "Pass either an explicit Skyfield timescale or earth_orientation config, not both"
            )
        self.earth_orientation = earth_orientation or EarthOrientationConfig.builtin()
        self.time_scale_mode = "explicit_timescale" if timescale is not None else self.earth_orientation.mode
        self.ts = (
            timescale
            if timescale is not None
            else self.earth_orientation.create_timescale(self.loader)
        )
        self.earth_orientation_provenance = describe_earth_orientation_source(
            self.earth_orientation,
            cache_dir=self.cache_dir,
            explicit_timescale=timescale is not None,
        )
        names = {"earth": "earth", "sun": "sun", "moon": "moon"}
        if body_names:
            names.update(body_names)
        try:
            self.earth = self.ephemeris[names["earth"]]
            self.sun = self.ephemeris[names["sun"]]
            self.moon = self.ephemeris[names["moon"]]
        except Exception as exc:
            raise ValueError(
                "The selected ephemeris must expose Earth, Sun, and Moon segments. "
                f"Requested names: {names}"
            ) from exc
        self.body_names = names

    @classmethod
    def from_jpl(cls, kernel: str = "de440s", **kwargs: Any) -> "EphemerisContext":
        """Load a supported JPL kernel by name, downloading it to ``cache_dir`` if absent."""
        return cls(kernel, **kwargs)

    def optional_body(self, key: str) -> Any | None:
        try:
            return self.ephemeris[key]
        except Exception:
            return None
