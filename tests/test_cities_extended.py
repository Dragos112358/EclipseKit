from __future__ import annotations

import pytest

from eclipsekit.cities import CityCatalog
from eclipsekit.models import City


def test_city_catalog_rejects_empty_iterable():
    with pytest.raises(ValueError, match="empty"):
        CityCatalog([])


def test_city_catalog_countries_are_sorted_and_indices_can_include_all():
    catalog = CityCatalog([
        City("Paris", "France", 48.85, 2.35),
        City("Madrid", "Spain", 40.4, -3.7),
        City("Lyon", "France", 45.76, 4.84),
    ])
    assert catalog.countries == ["France", "Spain"]
    assert catalog.indices_for_country(None).tolist() == [0, 1, 2]
    assert catalog.indices_for_country("FRANCE").tolist() == [0, 2]


def test_city_catalog_unknown_country_lists_available_countries():
    catalog = CityCatalog([City("Bucharest", "Romania", 44.4, 26.1)])
    with pytest.raises(ValueError, match="Romania"):
        catalog.indices_for_country("Portugal")


def test_city_catalog_from_csv_file_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="City catalogue not found"):
        CityCatalog.from_csv(tmp_path / "missing.csv")


def test_city_catalog_from_csv_requires_header_and_data(tmp_path):
    path = tmp_path / "header-only.csv"
    path.write_text("country,name,lat,lon,alt\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header and at least one"):
        CityCatalog.from_csv(path)


def test_city_catalog_from_csv_recognizes_aliases_and_skips_bad_rows(tmp_path):
    path = tmp_path / "aliases.csv"
    path.write_text(
        "Nation,Localitate,Latitudine,Longitudine,Altitudine\n"
        "România,București,44.4268,26.1025,80\n"
        "Spain,Madrid,not-a-number,-3.7,667\n"
        "Spain,Invalid latitude,91,10,0\n"
        "Spain,Invalid longitude,40,181,0\n"
        " , , , , \n"
        "Spain,Malformed,40\n",
        encoding="utf-8",
    )
    catalog = CityCatalog.from_csv(path)
    assert len(catalog.cities) == 1
    assert catalog.cities[0].name == "București"


def test_city_catalog_from_csv_accepts_custom_column_indices_and_delimiter(tmp_path):
    path = tmp_path / "custom.csv"
    path.write_text(
        "name;lon;country;alt;lat\nBucharest;26.1;Romania;80;44.4\n",
        encoding="utf-8",
    )
    catalog = CityCatalog.from_csv(
        path, country_column=2, name_column=0, latitude_column=4,
        longitude_column=1, elevation_column=3, delimiter=";",
    )
    assert catalog.cities[0].name == "Bucharest"
    assert catalog.cities[0].elevation_m == 80


def test_city_catalog_from_csv_rejects_unmatched_named_column(tmp_path):
    path = tmp_path / "unknown-header.csv"
    path.write_text("foo,bar,baz,qux,quux\na,b,1,2,3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Could not identify CSV column"):
        CityCatalog.from_csv(
            path, country_column="country", name_column="name", latitude_column="lat",
            longitude_column="lon", elevation_column="elevation_m",
        )


def test_city_catalog_from_csv_rejects_file_with_no_valid_rows(tmp_path):
    path = tmp_path / "invalid.csv"
    path.write_text(
        "country,name,lat,lon,elevation_m\nSpain,Nowhere,91,20,0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="No valid city rows"):
        CityCatalog.from_csv(path)



def test_city_catalog_country_indices_are_precomputed_and_defensively_copied():
    catalog = CityCatalog([
        City("Paris", "France", 48.85, 2.35),
        City("Madrid", "Spain", 40.4, -3.7),
        City("Lyon", "France", 45.76, 4.84),
    ])
    first = catalog.indices_for_country("FRANCE")
    first[:] = 99
    assert catalog.indices_for_country("France").tolist() == [0, 2]
    assert catalog.index_cache_info() == {
        "countries": 2,
        "indexed_cities": 3,
        "index_bytes": 3 * 8,
    }


def test_city_catalog_all_indices_are_defensively_copied():
    catalog = CityCatalog([City("A", "X", 0.0, 0.0), City("B", "Y", 1.0, 1.0)])
    result = catalog.indices_for_country(None)
    result[0] = 100
    assert catalog.indices_for_country(None).tolist() == [0, 1]



def test_city_catalog_iter_index_batches_are_read_only_views_without_duplicates():
    catalog = CityCatalog([
        City("Paris", "France", 48.85, 2.35),
        City("Lyon", "France", 45.76, 4.84),
        City("Madrid", "Spain", 40.4, -3.7),
        City("Marseille", "France", 43.3, 5.4),
        City("Seville", "Spain", 37.4, -5.98),
    ])
    batches = list(catalog.iter_index_batches("france", batch_size=2))
    assert [batch.tolist() for batch in batches] == [[0, 1], [3]]
    assert all(not batch.flags.writeable for batch in batches)
    assert catalog.indices_for_country("France").tolist() == [0, 1, 3]


def test_city_catalog_iter_index_batches_reject_invalid_size_and_country():
    catalog = CityCatalog([City("Paris", "France", 48.85, 2.35)])
    for value in (0, -1, True, 1.5, "2"):
        with pytest.raises(ValueError, match="batch_size must be an integer"):
            list(catalog.iter_index_batches("France", batch_size=value))
    with pytest.raises(ValueError, match="Portugal"):
        list(catalog.iter_index_batches("Portugal", batch_size=1))
