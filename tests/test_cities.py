from eclipsekit.cities import CityCatalog


def test_city_catalog_country_filter(tmp_path):
    path = tmp_path / "cities.csv"
    path.write_text(
        "country,name,latitude,longitude,elevation_m\n"
        "Romania,Bucharest,44.4268,26.1025,80\n"
        "Spain,Madrid,40.4168,-3.7038,667\n",
        encoding="utf-8",
    )
    catalog = CityCatalog.from_csv(path)
    indices = catalog.indices_for_country("românia")
    assert len(indices) == 1
    assert catalog.cities[int(indices[0])].name == "Bucharest"
    assert catalog.ecef.shape == (2, 3)
    assert catalog.up.shape == (2, 3)
