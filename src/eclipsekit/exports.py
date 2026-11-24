"""Export EclipseKit results to interoperable GeoJSON and CSV files."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from .timeutils import time_to_utc_iso


def _time_iso(value: Any | None) -> str | None:
    if value is None:
        return None
    return time_to_utc_iso(value)


def city_hits_to_geojson(hits: Iterable[Any]) -> dict[str, Any]:
    """Convert ``CityEclipseHit`` objects into a GeoJSON FeatureCollection.

    Coordinates follow RFC 7946 order: longitude, latitude (and elevation).
    All computed properties are copied into JSON-safe primitive values.
    """
    features: list[dict[str, Any]] = []
    for hit in hits:
        city = hit.city
        contacts = None
        if getattr(hit, "contacts", None) is not None:
            contacts = {
                key: _time_iso(value)
                for key, value in hit.contacts.as_dict().items()
            }
        limb_contacts = {}
        for key, item in getattr(hit, "limb_corrected_contacts", {}).items():
            limb_contacts[key] = {
                "time_utc": _time_iso(item.time),
                "delta_seconds": item.delta_seconds,
                "selenographic_latitude_deg": item.selenographic_latitude_deg,
                "selenographic_longitude_deg": item.selenographic_longitude_deg,
                "predicted_terrain_altitude_m": item.predicted_terrain_altitude_m,
            }
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [
                    float(city.longitude), float(city.latitude), float(city.elevation_m)
                ],
            },
            "properties": {
                "name": city.name,
                "country": city.country,
                "eclipse_type": hit.eclipse_type,
                "maximum_utc": _time_iso(hit.maximum),
                "magnitude": float(hit.magnitude),
                "obscuration_percent": float(hit.obscuration_percent),
                "sun_altitude_deg": float(hit.sun_altitude_deg),
                "offset_from_geocentric_maximum_minutes": float(
                    hit.offset_from_geocentric_maximum_minutes
                ),
                "contacts_utc": contacts,
                "limb_corrected_contacts": limb_contacts,
            },
        })
    return {"type": "FeatureCollection", "features": features}


def _split_antimeridian(coordinates: list[list[float]]) -> list[list[list[float]]]:
    """Split a longitude/latitude track at ±180° to avoid world-spanning lines."""
    if len(coordinates) < 2:
        return [coordinates]

    segments: list[list[list[float]]] = []
    current = [coordinates[0]]
    for point in coordinates[1:]:
        previous = current[-1]
        lon1, lat1 = previous[0], previous[1]
        lon2, lat2 = point[0], point[1]
        delta = lon2 - lon1

        if delta > 180.0:
            adjusted_lon2 = lon2 - 360.0
            fraction = (-180.0 - lon1) / (adjusted_lon2 - lon1)
            crossing_lat = lat1 + fraction * (lat2 - lat1)
            current.append([-180.0, crossing_lat])
            if len(current) >= 2:
                segments.append(current)
            current = [[180.0, crossing_lat], point]
        elif delta < -180.0:
            adjusted_lon2 = lon2 + 360.0
            fraction = (180.0 - lon1) / (adjusted_lon2 - lon1)
            crossing_lat = lat1 + fraction * (lat2 - lat1)
            current.append([180.0, crossing_lat])
            if len(current) >= 2:
                segments.append(current)
            current = [[-180.0, crossing_lat], point]
        else:
            current.append(point)

    if len(current) >= 2:
        segments.append(current)
    return segments


def shadow_path_to_geojson(points: Iterable[Any]) -> dict[str, Any]:
    """Convert ordered ``ShadowPathPoint`` objects into a GeoJSON line feature.

    The track is split at the antimeridian where necessary. Point order is kept
    as supplied by ``global_shadow_path`` / ``global_path_for_eclipse``.
    """
    path = list(points)
    if len(path) < 2:
        raise ValueError("At least two shadow path points are required")

    coordinates = [[float(p.longitude), float(p.latitude)] for p in path]
    if any(not (-180.0 <= p[0] <= 180.0 and -90.0 <= p[1] <= 90.0) for p in coordinates):
        raise ValueError("Shadow path coordinates must be valid WGS84 longitude/latitude")

    segments = _split_antimeridian(coordinates)
    if not segments:
        raise ValueError("Shadow path does not contain a drawable line segment")
    if len(segments) == 1:
        geometry = {"type": "LineString", "coordinates": segments[0]}
    else:
        geometry = {"type": "MultiLineString", "coordinates": segments}

    widths = [float(p.width_km) for p in path]
    times = [_time_iso(p.time) for p in path]
    kinds = sorted({str(p.shadow_kind) for p in path})
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "point_count": len(path),
            "shadow_kinds": kinds,
            "width_min_km": min(widths),
            "width_max_km": max(widths),
            "width_mean_km": sum(widths) / len(widths),
            "start_utc": times[0],
            "end_utc": times[-1],
            "times_utc": times,
        },
    }


def shadow_footprint_to_geojson(footprint: Any) -> dict[str, Any]:
    """Convert an instantaneous ``ShadowFootprint`` into RFC 7946 GeoJSON.

    Boundary samples are exported as linework, not polygons: partial cone
    intersections and antimeridian crossings must not be closed into invented
    filled areas. Missing samples split lines rather than being bridged.
    """
    if not hasattr(footprint, "central_boundary") or not hasattr(footprint, "penumbra_boundary"):
        raise TypeError("footprint must be a ShadowFootprint-like object")
    features: list[dict[str, Any]] = []
    time_utc = _time_iso(footprint.time)
    if footprint.axis_latitude is not None and footprint.axis_longitude is not None:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [
                float(footprint.axis_longitude), float(footprint.axis_latitude)
            ]},
            "properties": {
                "feature": "shadow_axis", "time_utc": time_utc,
                "shadow_kind": footprint.shadow_kind,
                "cone_radius_km": footprint.cone_radius_km,
                "track_bearing_deg": footprint.track_bearing_deg,
                "shadow_velocity_km_s": footprint.shadow_velocity_km_s,
                "cross_track_width_km": footprint.cross_track_width_km,
            },
        })

    for label, boundary, coverage in (
        ("central", footprint.central_boundary, footprint.central_boundary_coverage),
        ("penumbra", footprint.penumbra_boundary, footprint.penumbra_boundary_coverage),
    ):
        runs: list[list[list[float]]] = []
        current: list[list[float]] = []
        for point in boundary:
            if point is None:
                if len(current) >= 2:
                    runs.extend(_split_antimeridian(current))
                current = []
                continue
            current.append([float(point.longitude), float(point.latitude)])
        if len(current) >= 2:
            # Close the line only when every angular ray produced a point. For
            # an incomplete boundary, keep the observed run open.
            if all(point is not None for point in boundary) and current[0] != current[-1]:
                current.append(list(current[0]))
            runs.extend(_split_antimeridian(current))
        if not runs:
            continue
        geometry = (
            {"type": "LineString", "coordinates": runs[0]}
            if len(runs) == 1 else {"type": "MultiLineString", "coordinates": runs}
        )
        features.append({
            "type": "Feature", "geometry": geometry,
            "properties": {
                "feature": f"{label}_shadow_boundary", "time_utc": time_utc,
                "shadow_kind": footprint.shadow_kind, "coverage_fraction": float(coverage),
            },
        })
    return {
        "type": "FeatureCollection", "features": features,
        "properties": {
            "time_utc": time_utc, "shadow_kind": footprint.shadow_kind,
            "geometry_model": "spherical shadow cones intersected with WGS84",
            "notes": list(footprint.notes),
        },
    }


def write_geojson(data: Mapping[str, Any], filename: str | Path) -> Path:
    """Write a GeoJSON object as UTF-8 JSON and return its destination path."""
    destination = Path(filename).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return destination


def write_shadow_footprint_geojson(footprint: Any, filename: str | Path) -> Path:
    """Serialize an instantaneous shadow footprint as UTF-8 GeoJSON."""
    return write_geojson(shadow_footprint_to_geojson(footprint), filename)


def write_city_hits_csv(hits: Iterable[Any], filename: str | Path) -> Path:
    """Write city eclipse hits to CSV, including geometric and corrected contacts."""
    destination = Path(filename).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "city", "country", "latitude", "longitude", "elevation_m", "eclipse_type",
        "magnitude", "obscuration_percent", "sun_altitude_deg", "maximum_utc",
        "offset_from_geocentric_maximum_minutes", "C1_utc", "C2_utc", "C3_utc", "C4_utc",
        "C1_limb_utc", "C2_limb_utc", "C3_limb_utc", "C4_limb_utc",
    ]
    with destination.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for hit in hits:
            city = hit.city
            contacts = hit.contacts.as_dict() if getattr(hit, "contacts", None) else {}
            corrected = getattr(hit, "limb_corrected_contacts", {})
            row = {
                "city": city.name,
                "country": city.country,
                "latitude": city.latitude,
                "longitude": city.longitude,
                "elevation_m": city.elevation_m,
                "eclipse_type": hit.eclipse_type,
                "magnitude": hit.magnitude,
                "obscuration_percent": hit.obscuration_percent,
                "sun_altitude_deg": hit.sun_altitude_deg,
                "maximum_utc": _time_iso(hit.maximum),
                "offset_from_geocentric_maximum_minutes": hit.offset_from_geocentric_maximum_minutes,
            }
            for name in ("C1", "C2", "C3", "C4"):
                row[f"{name}_utc"] = _time_iso(contacts.get(name))
                correction = corrected.get(name)
                row[f"{name}_limb_utc"] = _time_iso(correction.time) if correction else None
            writer.writerow(row)
    return destination


def _corridor_side_coordinates(corridor: Any, name: str) -> list[list[float]]:
    """Return a side boundary only when every time slice has a point."""
    result = []
    for sample in corridor.samples:
        point = getattr(sample, name)
        if point is None:
            return []
        result.append([float(point.longitude), float(point.latitude)])
    return result


def _corridor_side_runs(corridor: Any, name: str) -> list[list[list[float]]]:
    """Return contiguous available boundary runs without bridging missing slices."""
    runs: list[list[list[float]]] = []
    current: list[list[float]] = []
    for sample in corridor.samples:
        point = getattr(sample, name)
        if point is None:
            if len(current) >= 2:
                runs.append(current)
            current = []
            continue
        current.append([float(point.longitude), float(point.latitude)])
    if len(current) >= 2:
        runs.append(current)
    return runs


def _clip_vertical(ring: list[list[float]], boundary: float, keep_greater: bool) -> list[list[float]]:
    if not ring:
        return []
    result: list[list[float]] = []
    previous = ring[-1]
    previous_inside = previous[0] >= boundary if keep_greater else previous[0] <= boundary
    for current in ring:
        current_inside = current[0] >= boundary if keep_greater else current[0] <= boundary
        if current_inside != previous_inside:
            dx = current[0] - previous[0]
            if abs(dx) > 1e-15:
                fraction = (boundary - previous[0]) / dx
                result.append([boundary, previous[1] + fraction * (current[1] - previous[1])])
        if current_inside:
            result.append([current[0], current[1]])
        previous, previous_inside = current, current_inside
    return result


def _corridor_polygon_parts(left: list[list[float]], right: list[list[float]]) -> list[list[list[float]]]:
    """Build simple polygon rings and split them at the antimeridian."""
    if len(left) < 2 or len(right) < 2:
        return []
    path = left + list(reversed(right))
    unwrapped = [[path[0][0], path[0][1]]]
    for lon, lat in path[1:]:
        adjusted = float(lon)
        while adjusted - unwrapped[-1][0] > 180.0:
            adjusted -= 360.0
        while adjusted - unwrapped[-1][0] < -180.0:
            adjusted += 360.0
        unwrapped.append([adjusted, float(lat)])
    close_lon = unwrapped[0][0]
    while close_lon - unwrapped[-1][0] > 180.0:
        close_lon -= 360.0
    while close_lon - unwrapped[-1][0] < -180.0:
        close_lon += 360.0
    unwrapped.append([close_lon, unwrapped[0][1]])
    strip_start = math.floor((min(p[0] for p in unwrapped) + 180.0) / 360.0)
    strip_end = math.floor((max(p[0] for p in unwrapped) + 180.0) / 360.0)
    parts = []
    for strip in range(strip_start, strip_end + 1):
        low, high = -180.0 + 360.0 * strip, 180.0 + 360.0 * strip
        clipped = _clip_vertical(unwrapped, low, True)
        clipped = _clip_vertical(clipped, high, False)
        if len(clipped) < 3:
            continue
        clipped = [[point[0] - 360.0 * strip, point[1]] for point in clipped]
        if clipped[0] != clipped[-1]:
            clipped.append(list(clipped[0]))
        if len(clipped) < 4:
            continue
        area = sum(
            clipped[i][0] * clipped[i + 1][1] - clipped[i + 1][0] * clipped[i][1]
            for i in range(len(clipped) - 1)
        )
        if area < 0.0:
            clipped.reverse()
        parts.append(clipped)
    return parts


def shadow_corridor_to_geojson(corridor: Any) -> dict[str, Any]:
    """Export central axis, central/penumbral limits and complete corridor polygons."""
    samples = list(corridor.samples)
    if len(samples) < 2:
        raise ValueError("At least two valid corridor samples are required")
    features = []
    center_feature = shadow_path_to_geojson([sample.center for sample in samples])
    center_feature["properties"].update({"name": "central_axis", "feature_role": "central_path"})
    features.append(center_feature)

    for field, name, kind in (
        ("central_left", "central_boundary_left", "central"),
        ("central_right", "central_boundary_right", "central"),
        ("penumbra_left", "penumbra_boundary_left", "penumbra"),
        ("penumbra_right", "penumbra_boundary_right", "penumbra"),
    ):
        runs = _corridor_side_runs(corridor, field)
        segments = [segment for run in runs for segment in _split_antimeridian(run)]
        if not segments:
            continue
        geometry = ({"type": "LineString", "coordinates": segments[0]} if len(segments) == 1
                    else {"type": "MultiLineString", "coordinates": segments})
        features.append({"type": "Feature", "geometry": geometry, "properties": {
            "name": name, "feature_role": "corridor_boundary", "boundary_type": kind,
            "side_reference": "left/right relative to central-track direction",
        }})

    for left_name, right_name, name, kind in (
        ("central_left", "central_right", "central_shadow_corridor", "central"),
        ("penumbra_left", "penumbra_right", "penumbral_partial_eclipse_corridor", "penumbra"),
    ):
        if not all(getattr(sample, left_name) is not None and getattr(sample, right_name) is not None
                   for sample in samples):
            continue
        parts = _corridor_polygon_parts(
            _corridor_side_coordinates(corridor, left_name),
            _corridor_side_coordinates(corridor, right_name),
        )
        if parts:
            features.append({"type": "Feature", "geometry": {
                "type": "MultiPolygon", "coordinates": [[ring] for ring in parts],
            }, "properties": {"name": name, "feature_role": "corridor_area",
                              "boundary_type": kind, "geometry_model": corridor.geometry_model}})
    return {"type": "FeatureCollection", "name": "EclipseKit shadow corridor",
            "properties": {"geometry_model": corridor.geometry_model,
                           "requested_sample_count": corridor.requested_sample_count,
                           "boundary_sample_count": corridor.boundary_sample_count,
                           "valid_sample_count": len(samples), "notes": list(corridor.notes)},
            "features": features}


def write_shadow_corridor_csv(corridor: Any, filename: str | Path) -> Path:
    """Write centerline and central/penumbral side limits to CSV."""
    fields = ["time_utc", "center_latitude_deg", "center_longitude_deg", "shadow_kind",
              "central_left_latitude_deg", "central_left_longitude_deg",
              "central_right_latitude_deg", "central_right_longitude_deg",
              "penumbra_left_latitude_deg", "penumbra_left_longitude_deg",
              "penumbra_right_latitude_deg", "penumbra_right_longitude_deg",
              "central_width_km", "penumbral_width_km", "shadow_velocity_km_s",
              "central_track_chord_km", "penumbral_track_chord_km",
              "central_phase_duration_estimate_seconds", "penumbral_duration_estimate_seconds", "track_bearing_deg",
              "central_boundary_coverage", "penumbra_boundary_coverage"]
    destination = Path(filename).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for sample in corridor.samples:
            row = {"time_utc": _time_iso(sample.time),
                   "center_latitude_deg": sample.center.latitude,
                   "center_longitude_deg": sample.center.longitude,
                   "shadow_kind": sample.center.shadow_kind,
                   "central_width_km": sample.central_width_km,
                   "penumbral_width_km": sample.penumbral_width_km,
                   "shadow_velocity_km_s": sample.shadow_velocity_km_s,
                   "central_track_chord_km": sample.central_track_chord_km,
                   "penumbral_track_chord_km": sample.penumbral_track_chord_km,
                   "central_phase_duration_estimate_seconds": sample.central_phase_duration_estimate_seconds,
                   "penumbral_duration_estimate_seconds": sample.penumbral_duration_estimate_seconds,
                   "track_bearing_deg": sample.track_bearing_deg,
                   "central_boundary_coverage": sample.central_boundary_coverage,
                   "penumbra_boundary_coverage": sample.penumbra_boundary_coverage}
            for name in ("central_left", "central_right", "penumbra_left", "penumbra_right"):
                point = getattr(sample, name)
                row[f"{name}_latitude_deg"] = point.latitude if point else None
                row[f"{name}_longitude_deg"] = point.longitude if point else None
            writer.writerow(row)
    return destination


def shadow_corridor_to_kml(corridor: Any) -> str:
    """Create KML with central path, boundary lines and complete corridor polygons."""
    import xml.etree.ElementTree as ET
    namespace = "http://www.opengis.net/kml/2.2"
    ET.register_namespace("", namespace)

    def q(name: str) -> str:
        return f"{{{namespace}}}{name}"

    root = ET.Element(q("kml"))
    document = ET.SubElement(root, q("Document"))
    ET.SubElement(document, q("name")).text = "EclipseKit shadow corridor"

    def add_line(name: str, coordinates: list[list[float]]) -> None:
        if len(coordinates) < 2:
            return
        segments = _split_antimeridian(coordinates)
        placemark = ET.SubElement(document, q("Placemark"))
        ET.SubElement(placemark, q("name")).text = name
        if len(segments) == 1:
            geometries = [ET.SubElement(placemark, q("LineString"))]
        else:
            multi = ET.SubElement(placemark, q("MultiGeometry"))
            geometries = [ET.SubElement(multi, q("LineString")) for _ in segments]
        for line, segment in zip(geometries, segments):
            ET.SubElement(line, q("tessellate")).text = "1"
            ET.SubElement(line, q("coordinates")).text = " ".join(
                f"{lon:.9f},{lat:.9f},0" for lon, lat in segment
            )

    add_line("Central axis", [[s.center.longitude, s.center.latitude] for s in corridor.samples])
    for field, name in (("central_left", "Central boundary left"), ("central_right", "Central boundary right"),
                        ("penumbra_left", "Penumbral boundary left"), ("penumbra_right", "Penumbral boundary right")):
        for run in _corridor_side_runs(corridor, field):
            add_line(name, run)
    for left_name, right_name, title in (("central_left", "central_right", "Central shadow corridor"),
                                         ("penumbra_left", "penumbra_right", "Penumbral corridor")):
        if not all(getattr(s, left_name) is not None and getattr(s, right_name) is not None
                   for s in corridor.samples):
            continue
        parts = _corridor_polygon_parts(_corridor_side_coordinates(corridor, left_name),
                                        _corridor_side_coordinates(corridor, right_name))
        for index, ring in enumerate(parts, start=1):
            placemark = ET.SubElement(document, q("Placemark"))
            ET.SubElement(placemark, q("name")).text = f"{title} {index}"
            polygon = ET.SubElement(placemark, q("Polygon"))
            outer = ET.SubElement(polygon, q("outerBoundaryIs"))
            linear = ET.SubElement(outer, q("LinearRing"))
            ET.SubElement(linear, q("coordinates")).text = " ".join(
                f"{lon:.9f},{lat:.9f},0" for lon, lat in ring
            )
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def write_shadow_corridor_kml(corridor: Any, filename: str | Path) -> Path:
    """Write a KML shadow corridor."""
    destination = Path(filename).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(shadow_corridor_to_kml(corridor), encoding="utf-8")
    return destination



def write_observation_plan_csv(plan: Any, filename: str | Path) -> Path:
    """Write a ranked multi-observer eclipse plan as a UTF-8 CSV table."""
    fields = [
        "rank", "site_name", "country", "plan_target_time_utc",
        "latitude_deg", "longitude_deg", "elevation_m",
        "status", "visibility_class", "score", "obscuration_score",
        "solar_altitude_score", "partial_duration_score", "eclipse_type", "maximum_utc",
        "magnitude", "obscuration_percent", "sun_altitude_deg", "sun_azimuth_deg",
        "partial_phase_duration_seconds", "central_phase_duration_seconds",
        "C1_utc", "C2_utc", "C3_utc", "C4_utc", "message",
    ]
    destination = Path(filename).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for site in plan.sites:
            observer = site.observer
            result = site.local_result
            contacts = result.contacts.as_dict() if result is not None else {}
            row = {
                "rank": site.rank,
                "site_name": observer.name,
                "country": observer.country,
                "plan_target_time_utc": _time_iso(plan.target_time),
                "latitude_deg": observer.latitude,
                "longitude_deg": observer.longitude,
                "elevation_m": observer.elevation_m,
                "status": site.status,
                "visibility_class": site.visibility_class,
                "score": site.score,
                "obscuration_score": site.obscuration_score,
                "solar_altitude_score": site.solar_altitude_score,
                "partial_duration_score": site.partial_duration_score,
                "eclipse_type": result.eclipse_type if result is not None else None,
                "maximum_utc": _time_iso(result.maximum) if result is not None else None,
                "magnitude": result.magnitude if result is not None else None,
                "obscuration_percent": result.obscuration_percent if result is not None else None,
                "sun_altitude_deg": result.sun_altitude_deg if result is not None else None,
                "sun_azimuth_deg": result.sun_azimuth_deg if result is not None else None,
                "partial_phase_duration_seconds": (
                    result.partial_phase_duration_seconds if result is not None else None
                ),
                "central_phase_duration_seconds": (
                    result.central_phase_duration_seconds if result is not None else None
                ),
                "message": site.message,
            }
            for contact in ("C1", "C2", "C3", "C4"):
                row[f"{contact}_utc"] = _time_iso(contacts.get(contact))
            writer.writerow(row)
    return destination


def write_observation_plan_json(plan: Any, filename: str | Path) -> Path:
    """Write an :class:`ObservationPlan` dictionary as strict UTF-8 JSON."""
    if not callable(getattr(plan, "to_dict", None)):
        raise TypeError("plan must provide a to_dict() method")
    payload = plan.to_dict()
    destination = Path(filename).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return destination
