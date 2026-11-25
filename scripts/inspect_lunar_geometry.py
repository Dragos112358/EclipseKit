import math

from eclipsekit import EclipseEngine, EarthOrientationConfig
from eclipsekit.lunar_eclipse import lunar_shadow_geometry
from skyfield.framelib import itrs

engine = EclipseEngine(
    "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de430.bsp",
    earth_orientation=EarthOrientationConfig.fixed(72.7),
)

# Greatest eclipse from the EclipseWise reference (TD/TT JD).
time = engine.ts.tt_jd(2461605.168724)
at = engine.earth.at(time)

sun = at.observe(engine.sun).apparent()
moon = at.observe(engine.moon).apparent()

sun_vector = sun.frame_xyz(itrs).km
moon_vector = moon.frame_xyz(itrs).km

sun_ra, sun_dec, _ = sun.radec(epoch="date")
moon_ra, moon_dec, _ = moon.radec(epoch="date")

geometry = lunar_shadow_geometry(
    sun_vector,
    moon_vector,
    sun_radius_km=engine.sun_radius_km,
    moon_radius_km=1737.4,
    earth_radius_km=6378.137,
    shadow_enlargement=1.0,
    shadow_model="herald_sinnott",
    atmospheric_nel_height_km=87.0,
    flattening_coefficient=0.003353,
    boundary_samples=384,
)

def arcseconds(radius, distance):
    return math.degrees(math.asin(radius / distance)) * 3600.0

def parallax_arcseconds(distance):
    return math.degrees(math.asin(6378.137 / distance)) * 3600.0

print("SUN")
print("RA hours:", sun_ra.hours)
print("Dec degrees:", sun_dec.degrees)
print("Semidiameter arcsec:",
      arcseconds(engine.sun_radius_km, geometry.sun_distance_km))
print("Horizontal parallax arcsec:",
      parallax_arcseconds(geometry.sun_distance_km))

print("\nMOON")
print("RA hours:", moon_ra.hours)
print("Dec degrees:", moon_dec.degrees)
print("Semidiameter arcsec:",
      arcseconds(1737.4, geometry.moon_distance_km))
print("Horizontal parallax arcsec:",
      parallax_arcseconds(geometry.moon_distance_km))

print("\nSHADOW GEOMETRY")
print("Axis distance degrees:", geometry.axis_distance_deg)
print("Axis distance Earth radii:",
      geometry.axis_distance_km / 6378.137)
print("Earth radius factor:", geometry.earth_radius_factor)
print("Shadow position angle degrees:",
      math.degrees(geometry.shadow_position_angle_rad))
print("Penumbra radius degrees:",
      math.degrees(geometry.penumbra_radius_rad))
print("Umbra radius degrees:",
      math.degrees(geometry.umbra_radius_rad))
print("Penumbral magnitude:", geometry.penumbral_magnitude)
print("Umbral magnitude:", geometry.umbral_magnitude)