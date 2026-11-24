"""Demonstrate the public EclipseKit configuration API.

Run from the project root after installing the package and selecting a JPL
kernel. IERS mode can download finals2000A.all on first use.
"""

from eclipsekit import (
    AtmosphereConfig,
    ContactModelConfig,
    EclipseConfig,
    EclipseEngine,
    EphemerisConfig,
    EarthOrientationConfig,
    Observer,
    SolverConfig,
)


config = EclipseConfig(
    ephemeris=EphemerisConfig.jpl(
        "de440s",
        earth_orientation=EarthOrientationConfig.iers(),
    ),
    contacts=ContactModelConfig(),
    solver=SolverConfig(
        root_tolerance_seconds=1e-5,
        root_max_iterations=100,
        minimum_tolerance_seconds=0.05,
    ),
    atmosphere=AtmosphereConfig(
        refraction_enabled=True,
        pressure_mbar=1013.25,
        temperature_c=15.0,
    ),
)

engine = EclipseEngine(config=config)
observer = Observer(42.6, -5.5703, elevation_m=800, name="León")
result = engine.calculate_local(observer, "2026-08-12")

print("Configuration:", config.to_dict())
print("Time-scale diagnostics:", engine.time_scale_diagnostics("2026-08-12T18:30:00Z"))
if result is None:
    print("No local eclipse found")
else:
    print(engine.format_report(result, language="en"))
