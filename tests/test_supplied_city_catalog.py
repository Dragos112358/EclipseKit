from pathlib import Path

import pytest

from eclipsekit import CityCatalog


def test_supplied_country_points_catalogue():
    root = Path(__file__).resolve().parents[1]
    catalogue_path = root / "data" / "CountryPoints.csv"
    if not catalogue_path.is_file():
        pytest.skip("CountryPoints.csv is a local data asset and is not distributed in Git")
    catalog = CityCatalog.from_csv(catalogue_path)
    assert len(catalog.cities) == 8133
    assert len(catalog.countries) == 245
    romania = catalog.indices_for_country("Romania")
    assert len(romania) == 60
    assert any(c.name == "Bucharest" for c in (catalog.cities[int(i)] for i in romania))
