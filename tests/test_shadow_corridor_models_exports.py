import pytest

from eclipsekit.exports import (
    shadow_corridor_to_geojson,
    shadow_corridor_to_kml,
    write_shadow_corridor_csv,
    write_shadow_corridor_kml,
)
from eclipsekit.models import (
    ShadowCorridorEdge,
    ShadowCorridorResult,
    ShadowCorridorSample,
    ShadowPathPoint,
)


class FakeTime:
    utc = (2017, 8, 21, 17, 0, 0.0)

    def utc_iso(self, delimiter="T", places=3):
        return "2017-08-21T17:00:00.000Z"


def _wrap_longitude(value):
    return (value + 180.0) % 360.0 - 180.0


def build_corridor(longitudes=(179.0, -179.0)):
    samples = []
    for index, longitude in enumerate(longitudes):
        moment = FakeTime()
        center = ShadowPathPoint(moment, 10.0 + index, longitude, 80.0, "umbral")
        samples.append(ShadowCorridorSample(
            time=moment, center=center,
            central_left=ShadowCorridorEdge(10.5 + index, _wrap_longitude(longitude - 0.2)),
            central_right=ShadowCorridorEdge(9.5 + index, _wrap_longitude(longitude + 0.2)),
            penumbra_left=ShadowCorridorEdge(11.0 + index, _wrap_longitude(longitude - 0.5)),
            penumbra_right=ShadowCorridorEdge(9.0 + index, _wrap_longitude(longitude + 0.5)),
            central_width_km=100.0, penumbral_width_km=300.0,
            shadow_velocity_km_s=2.0, central_phase_duration_estimate_seconds=50.0,
            penumbral_duration_estimate_seconds=150.0, track_bearing_deg=90.0,
            central_boundary_coverage=1.0, penumbra_boundary_coverage=1.0,
            central_track_chord_km=140.0, penumbral_track_chord_km=420.0,
        ))
    return ShadowCorridorResult(tuple(samples), max(2, len(samples)), 72)


def test_corridor_sample_serializes_provenance_and_width_fields():
    corridor = build_corridor((10.0, 11.0))
    payload = corridor.to_dict()
    assert payload["valid_sample_count"] == 2
    assert payload["samples"][0]["central_width_km"] == 100.0
    assert payload["samples"][0]["penumbral_duration_estimate_seconds"] == 150.0
    assert payload["samples"][0]["central_track_chord_km"] == 140.0


def test_corridor_geojson_contains_axis_boundaries_and_polygons():
    corridor = build_corridor((10.0, 11.0))
    result = shadow_corridor_to_geojson(corridor)
    names = {feature["properties"].get("name") for feature in result["features"]}
    assert "central_axis" in names
    assert "central_boundary_left" in names
    assert "central_shadow_corridor" in names
    assert "penumbral_partial_eclipse_corridor" in names


def test_corridor_geojson_splits_lines_when_crossing_antimeridian():
    corridor = build_corridor((179.0, -179.0))
    result = shadow_corridor_to_geojson(corridor)
    axis = next(feature for feature in result["features"] if feature["properties"]["name"] == "central_axis")
    assert axis["geometry"]["type"] == "MultiLineString"
    assert len(axis["geometry"]["coordinates"]) == 2


def test_corridor_kml_and_csv_writers_create_files(tmp_path):
    corridor = build_corridor((10.0, 11.0))
    kml = shadow_corridor_to_kml(corridor)
    assert "<kml" in kml and "Central axis" in kml
    kml_path = write_shadow_corridor_kml(corridor, tmp_path / "nested" / "corridor.kml")
    csv_path = write_shadow_corridor_csv(corridor, tmp_path / "nested" / "corridor.csv")
    assert kml_path.is_file() and csv_path.is_file()
    csv_text = csv_path.read_text(encoding="utf-8-sig")
    assert "central_width_km" in csv_text
    assert "central_track_chord_km" in csv_text


def test_corridor_geojson_requires_two_samples():
    corridor = build_corridor((10.0,))
    with pytest.raises(ValueError, match="At least two"):
        shadow_corridor_to_geojson(corridor)


def test_edge_point_rejects_out_of_range_coordinates():
    with pytest.raises(ValueError, match="latitude"):
        ShadowCorridorEdge(91.0, 0.0)
    with pytest.raises(ValueError, match="longitude"):
        ShadowCorridorEdge(0.0, 181.0)



def test_corridor_geojson_splits_corridor_polygons_at_antimeridian():
    corridor = build_corridor((179.0, -179.0))
    result = shadow_corridor_to_geojson(corridor)
    polygon = next(
        feature for feature in result["features"]
        if feature["properties"].get("name") == "central_shadow_corridor"
    )
    assert polygon["geometry"]["type"] == "MultiPolygon"
    assert len(polygon["geometry"]["coordinates"]) == 2
    for polygon_coordinates in polygon["geometry"]["coordinates"]:
        for ring in polygon_coordinates:
            assert ring[0] == ring[-1]
            assert all(-180.0 <= point[0] <= 180.0 for point in ring)


def test_corridor_exports_do_not_bridge_missing_boundary_samples():
    corridor = build_corridor((10.0, 11.0, 12.0, 13.0))
    samples = list(corridor.samples)
    missing = samples[1]
    samples[1] = ShadowCorridorSample(
        time=missing.time, center=missing.center,
        central_left=None, central_right=missing.central_right,
        penumbra_left=missing.penumbra_left, penumbra_right=missing.penumbra_right,
        central_width_km=None, penumbral_width_km=missing.penumbral_width_km,
        shadow_velocity_km_s=missing.shadow_velocity_km_s,
        central_phase_duration_estimate_seconds=None,
        penumbral_duration_estimate_seconds=missing.penumbral_duration_estimate_seconds,
        track_bearing_deg=missing.track_bearing_deg,
        central_boundary_coverage=0.5, penumbra_boundary_coverage=1.0,
    )
    partial = ShadowCorridorResult(tuple(samples), 4, 72)
    result = shadow_corridor_to_geojson(partial)
    central_left = next(
        feature for feature in result["features"]
        if feature["properties"].get("name") == "central_boundary_left"
    )
    assert central_left["geometry"]["type"] == "LineString"
    coordinates = central_left["geometry"]["coordinates"]
    assert len(coordinates) == 2
    assert coordinates[0] == [samples[2].central_left.longitude, samples[2].central_left.latitude]
    assert coordinates[-1] == [samples[3].central_left.longitude, samples[3].central_left.latitude]
    assert not any(
        feature["properties"].get("name") == "central_shadow_corridor"
        for feature in result["features"]
    )


def test_kml_splits_antimeridian_crossing_lines_into_multigeometry():
    import xml.etree.ElementTree as ET

    root = ET.fromstring(shadow_corridor_to_kml(build_corridor((179.0, -179.0))))
    namespace = {"k": "http://www.opengis.net/kml/2.2"}
    axis = next(
        placemark for placemark in root.findall(".//k:Placemark", namespace)
        if placemark.findtext("k:name", namespaces=namespace) == "Central axis"
    )
    assert axis.find("k:MultiGeometry", namespace) is not None
    assert len(axis.findall(".//k:LineString", namespace)) == 2


def test_corridor_sample_rejects_invalid_metrics_and_inconsistent_edges():
    from dataclasses import replace

    sample = build_corridor((10.0, 11.0)).samples[0]
    with pytest.raises(ValueError, match="central_width_km"):
        replace(sample, central_width_km=float("nan"))
    with pytest.raises(ValueError, match="coverage"):
        replace(sample, central_boundary_coverage=1.1)
    with pytest.raises(ValueError, match="track_bearing"):
        replace(sample, track_bearing_deg=360.0)
    with pytest.raises(ValueError, match="requires both"):
        replace(sample, central_left=None)


def test_corridor_result_rejects_invalid_counts_and_notes():
    corridor = build_corridor((10.0, 11.0))
    with pytest.raises(ValueError, match="requested_sample_count"):
        ShadowCorridorResult(corridor.samples, 1, 72)
    with pytest.raises(ValueError, match="boundary_sample_count"):
        ShadowCorridorResult(corridor.samples, 2, 8)
    with pytest.raises(ValueError, match="exceed"):
        ShadowCorridorResult((*corridor.samples, corridor.samples[0]), 2, 72)
    with pytest.raises(ValueError, match="geometry_model"):
        ShadowCorridorResult(corridor.samples, 2, 72, geometry_model=" ")


def test_corridor_edge_rejects_boolean_or_non_numeric_coordinates():
    with pytest.raises(ValueError, match="boolean"):
        ShadowCorridorEdge(True, 0.0)
    with pytest.raises(ValueError, match="numeric"):
        ShadowCorridorEdge("north", 0.0)
