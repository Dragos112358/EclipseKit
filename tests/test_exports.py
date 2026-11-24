from types import SimpleNamespace

import pytest

from eclipsekit.exports import (
    city_hits_to_geojson,
    shadow_path_to_geojson,
    write_city_hits_csv,
    write_geojson,
)
from eclipsekit.models import City, CityEclipseHit, ContactTimes


class FakeSkyfieldTime:
    def utc_iso(self, delimiter="T", places=3):
        return "2026-08-12T17:00:00.000Z"

    @property
    def utc(self):
        return (2026, 8, 12, 17, 0, 0.0)


def point(latitude, longitude, width=100.0):
    return SimpleNamespace(
        latitude=latitude,
        longitude=longitude,
        width_km=width,
        shadow_kind="umbral",
        time=FakeSkyfieldTime(),
    )


def test_shadow_path_geojson_uses_lon_lat_order():
    result = shadow_path_to_geojson([point(10, 20), point(11, 21)])
    assert result["geometry"]["type"] == "LineString"
    assert result["geometry"]["coordinates"] == [[20.0, 10.0], [21.0, 11.0]]
    assert result["properties"]["point_count"] == 2


def test_shadow_path_splits_antimeridian():
    result = shadow_path_to_geojson([point(10, 179), point(11, -179)])
    assert result["geometry"]["type"] == "MultiLineString"
    assert len(result["geometry"]["coordinates"]) == 2
    assert result["geometry"]["coordinates"][0][-1][0] == 180.0
    assert result["geometry"]["coordinates"][1][0][0] == -180.0


def test_shadow_path_requires_two_points():
    with pytest.raises(ValueError, match="At least two"):
        shadow_path_to_geojson([point(10, 20)])


def test_write_geojson_creates_parent_and_utf8(tmp_path):
    output = write_geojson({"type": "FeatureCollection", "name": "Știință", "features": []}, tmp_path / "sub" / "x.geojson")
    text = output.read_text(encoding="utf-8")
    assert "Știință" in text
    assert output.is_file()


def test_city_hits_geojson_and_csv_export(tmp_path):
    hit = CityEclipseHit(
        city=City("León", "Spain", 42.6, -5.5703, 844),
        maximum=FakeSkyfieldTime(),
        magnitude=1.01,
        obscuration_percent=100.0,
        eclipse_type="total",
        sun_altitude_deg=9.7,
        offset_from_geocentric_maximum_minutes=43.2,
        contacts=ContactTimes(c1=FakeSkyfieldTime()),
    )
    geojson = city_hits_to_geojson([hit])
    feature = geojson["features"][0]
    assert feature["geometry"]["coordinates"] == [-5.5703, 42.6, 844.0]
    assert feature["properties"]["eclipse_type"] == "total"
    assert feature["properties"]["contacts_utc"]["C1"].endswith("Z")

    output = write_city_hits_csv([hit], tmp_path / "nested" / "exports" / "cities.csv")
    content = output.read_text(encoding="utf-8-sig")
    assert "León" in content
    assert "C1_utc" in content
