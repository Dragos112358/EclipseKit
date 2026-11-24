"""Compact city/country catalogue loader. Geographic data are user-supplied, not bundled."""

from __future__ import annotations

import csv
from pathlib import Path
import unicodedata
from typing import Iterable, Iterator
import numpy as np

from .geometry import wgs84_geodetic_to_ecef, wgs84_up_vector
from .models import City


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.casefold().split())


class CityCatalog:
    """In-memory vectorized catalogue, typically loaded from CountryPoints.csv.

    The default positional format follows the supplied simulator file:
    country,name,latitude,longitude,elevation_m. No global city database is
    embedded in this package, keeping the wheel small and avoiding data-license
    assumptions.
    """

    def __init__(self, cities: Iterable[City]) -> None:
        self.cities = list(cities)
        if not self.cities:
            raise ValueError("city catalogue is empty")
        self.ecef = np.vstack([
            wgs84_geodetic_to_ecef(c.latitude, c.longitude, c.elevation_m) for c in self.cities
        ])
        self.up = np.vstack([wgs84_up_vector(c.latitude, c.longitude) for c in self.cities])
        self._countries = np.array([_norm(c.country) for c in self.cities], dtype=object)
        self._all_indices = np.arange(len(self.cities), dtype=np.intp)
        self._all_indices.setflags(write=False)
        grouped_indices: dict[str, list[int]] = {}
        for row_index, normalized_country in enumerate(self._countries.tolist()):
            grouped_indices.setdefault(str(normalized_country), []).append(row_index)
        self._country_indices: dict[str, np.ndarray] = {}
        for normalized_country, row_indices in grouped_indices.items():
            country_indices = np.asarray(row_indices, dtype=np.intp)
            country_indices.setflags(write=False)
            self._country_indices[normalized_country] = country_indices
        self._country_names = sorted({city.country for city in self.cities})

    @classmethod
    def from_csv(
        cls,
        filename: str | Path,
        *,
        country_column: int | str = 0,
        name_column: int | str = 1,
        latitude_column: int | str = 2,
        longitude_column: int | str = 3,
        elevation_column: int | str = 4,
        delimiter: str = ",",
        encoding: str = "utf-8-sig",
    ) -> "CityCatalog":
        path = Path(filename).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"City catalogue not found: {path}")
        with path.open("r", encoding=encoding, newline="") as file:
            rows = list(csv.reader(file, delimiter=delimiter))
        if len(rows) < 2:
            raise ValueError("CSV must contain a header and at least one data row")
        header = [h.strip().casefold() for h in rows[0]]
        aliases = {
            "country": {"country", "country_name", "nation", "tara"},
            "name": {"name", "city", "locality", "oras", "localitate"},
            "latitude": {"lat", "latitude", "latitud", "latitudine"},
            "longitude": {"lon", "lng", "longitude", "longitudine"},
            "elevation": {"alt", "elevation", "elevation_m", "altitude", "altitudine"},
        }

        def get_index(value: int | str, key: str) -> int:
            if isinstance(value, int):
                return value
            lookup = value.strip().casefold()
            if lookup in header:
                return header.index(lookup)
            for idx, col in enumerate(header):
                if col in aliases[key]:
                    return idx
            raise ValueError(f"Could not identify CSV column for {key!r}; pass its index or name")

        indices = [
            get_index(country_column, "country"), get_index(name_column, "name"),
            get_index(latitude_column, "latitude"), get_index(longitude_column, "longitude"),
            get_index(elevation_column, "elevation"),
        ]
        cities: list[City] = []
        for row_number, row in enumerate(rows[1:], start=2):
            if not row or all(not field.strip() for field in row):
                continue
            try:
                values = [row[i].strip() for i in indices]
                country, name = values[0], values[1]
                lat, lon, elevation = map(float, values[2:])
                if not country or not name or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                    continue
                cities.append(City(name=name, country=country, latitude=lat,
                                   longitude=lon, elevation_m=elevation))
            except (IndexError, ValueError):
                continue
        if not cities:
            raise ValueError(f"No valid city rows parsed from {path}")
        return cls(cities)

    def indices_for_country(self, country: str | None) -> np.ndarray:
        """Return catalogue row indices, using precomputed country groups.

        Returned arrays are independent copies so callers can safely reorder or
        modify them without corrupting this catalogue's internal index cache.
        """
        if country is None:
            return self._all_indices.copy()
        wanted = _norm(country)
        indices = self._country_indices.get(wanted)
        if indices is None:
            raise ValueError(
                f"Country {country!r} is not in this catalogue. "
                f"Sample values: {self._country_names[:20]}"
            )
        return indices.copy()

    def iter_index_batches(
        self, country: str | None, *, batch_size: int = 512
    ) -> Iterator[np.ndarray]:
        """Yield read-only index views in bounded batches without copying the index.

        This is intended for streaming/vectorised consumers. Unlike
        :meth:`indices_for_country`, returned slices are read-only views into
        the catalogue's immutable index arrays and must not be modified.
        """
        if isinstance(batch_size, bool) or not isinstance(batch_size, (int, np.integer)):
            raise ValueError("batch_size must be an integer >= 1")
        size = int(batch_size)
        if size < 1:
            raise ValueError("batch_size must be an integer >= 1")
        if country is None:
            indices = self._all_indices
        else:
            wanted = _norm(country)
            indices = self._country_indices.get(wanted)
            if indices is None:
                raise ValueError(
                    f"Country {country!r} is not in this catalogue. "
                    f"Sample values: {self._country_names[:20]}"
                )
        for offset in range(0, len(indices), size):
            yield indices[offset:offset + size]

    def index_cache_info(self) -> dict[str, int]:
        """Describe the immutable country-index cache and its NumPy payload."""
        return {
            "countries": len(self._country_indices),
            "indexed_cities": sum(len(indices) for indices in self._country_indices.values()),
            "index_bytes": sum(indices.nbytes for indices in self._country_indices.values()),
        }

    @property
    def countries(self) -> list[str]:
        return list(self._country_names)
