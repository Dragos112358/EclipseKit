
from __future__ import annotations

import math

from eclipsekit import EclipseEngine, EarthOrientationConfig
from eclipsekit.lunar_eclipse import lunar_shadow_geometry
from eclipsekit.timeutils import time_to_ut1_iso
from skyfield.framelib import itrs


JD_MAX = 2461605.168724

REFERENCE = {
    "Sun": (
        7 + 51 / 60 + 14.4 / 3600,
        20 + 58 / 60 + 43.6 / 3600,
    ),
    "Moon": (
        19 + 52 / 60 + 57.2 / 3600,
        -(22 + 20 / 60 + 25.3 / 3600),
    ),
}


def compare_coordinates(name, position):
    ra, dec, distance = position.radec(epoch="date")
    ref_ra, ref_dec = REFERENCE[name]

    ra_time_error = (ra.hours - ref_ra) * 3600.0
    ra_sky_error = (
        ra_time_error * 15.0 * math.cos(math.radians(ref_dec))
    )
    dec_error = (dec.degrees - ref_dec) * 3600.0

    print(f"\n{name}")
    print(f"RA: {ra.hours:.10f} h")
    print(f"Dec: {dec.degrees:.10f} deg")
    print(f"Distance: {distance.km:.3f} km")
    print(f"RA difference: {ra_time_error:+.4f} seconds of time")
    print(f"RA sky difference: {ra_sky_error:+.4f} arcsec")
    print(f"Dec difference: {dec_error:+.4f} arcsec")


engine = EclipseEngine(
    "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de430.bsp",
    earth_orientation=EarthOrientationConfig.fixed(72.7),
)

t = engine.ts.tt_jd(JD_MAX)

print("TIME SCALE")
print("TT JD:", t.tt)
print("Delta-T:", t.delta_t)
print("DUT1:", t.dut1)

at = engine.earth.at(t)

sun_astrometric = at.observe(engine.sun)
moon_astrometric = at.observe(engine.moon)

sun_apparent = sun_astrometric.apparent()
moon_apparent = moon_astrometric.apparent()

print("\nASTROMETRIC COORDINATES")
compare_coordinates("Sun", sun_astrometric)
compare_coordinates("Moon", moon_astrometric)

print("\nAPPARENT COORDINATES")
compare_coordinates("Sun", sun_apparent)
compare_coordinates("Moon", moon_apparent)

print("\nGEOMETRY COMPARISON")

geometries = {}

for label, sun_position, moon_position in (
    ("astrometric", sun_astrometric, moon_astrometric),
    ("apparent", sun_apparent, moon_apparent),
):
    geometry = lunar_shadow_geometry(
        sun_position.frame_xyz(itrs).km,
        moon_position.frame_xyz(itrs).km,
        sun_radius_km=696000.0,
        moon_radius_km=1737.4,
        earth_radius_km=6378.137,
        shadow_enlargement=1.0,
        shadow_model="herald_sinnott",
        atmospheric_nel_height_km=87.0,
        flattening_coefficient=0.003353,
        boundary_samples=384,
    )

    geometries[label] = geometry

    print(f"\n{label.upper()}")
    print("Axis distance:", geometry.axis_distance_deg)
    print("Earth radius factor:", geometry.earth_radius_factor)
    print("Penumbral radius:", geometry.penumbra_radius_rad * 180 / math.pi)
    print("Penumbral magnitude:", geometry.penumbral_magnitude)
    print("Umbral magnitude:", geometry.umbral_magnitude)

# Estimate a lunar radius from the rounded published semidiameter.
# This is a sensitivity experiment, not a new project default.
geometry = geometries["apparent"]

reference_sd_deg = 14.0 / 60.0 + 43.0 / 3600.0

reference_radius_km = (
    geometry.moon_distance_km
    * math.sin(math.radians(reference_sd_deg))
)

print("\nMOON RADIUS SENSITIVITY")
print("Current radius: 1737.4 km")
print("Radius inferred from reference SD:", reference_radius_km)

for moon_radius in (1737.4, reference_radius_km):
    event = engine.calculate_lunar_eclipse(
        t,
        search_half_window_hours=3.0,
        contact_search_half_window_hours=1.0,
        contact_step_seconds=60.0,
        contact_tolerance_seconds=0.01,
        boundary_samples=384,
        moon_radius_km=moon_radius,
    )

    print(f"\nMOON RADIUS = {moon_radius:.6f} km")

    if event is None:
        print("No eclipse returned")
        continue

    print("Penumbral magnitude:", event.penumbral_magnitude)
    print("Umbral magnitude:", event.umbral_magnitude)

    for name, contact in event.contacts.as_dict().items():
        value = time_to_ut1_iso(contact) if contact is not None else None
        print(f"{name}: {value}")
