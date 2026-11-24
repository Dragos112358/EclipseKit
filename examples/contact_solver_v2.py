"""Demonstrate configurable root finding and detailed contact diagnostics."""

from eclipsekit import (
    EclipseConfig,
    EclipseEngine,
    EarthOrientationConfig,
    EphemerisConfig,
    Observer,
    SolverConfig,
    time_to_utc_iso,
)


config = EclipseConfig(
    ephemeris=EphemerisConfig.jpl(
        "de440s", earth_orientation=EarthOrientationConfig.builtin()
    ),
    solver=SolverConfig(
        root_method="brent",
        root_tolerance_seconds=1e-4,
        auto_expand_bracket=True,
        detect_tangent_contacts=True,
    ),
)
engine = EclipseEngine(config=config)
observer = Observer(42.6, -5.5703, elevation_m=800, name="León", country="Spain")

# The interval intentionally surrounds the published C1 time.
diagnostic = engine.solve_contact_detailed(
    observer,
    "external",
    "2026-08-12T17:30:00Z",
    "2026-08-12T17:35:00Z",
)

print("Status:", diagnostic.status)
print("Method:", diagnostic.method)
print("Iterations:", diagnostic.iterations)
print("Function calls:", diagnostic.function_calls)
print("Residual (degrees):", diagnostic.residual)
print("Final TT-JD bracket:", diagnostic.bracket_start, diagnostic.bracket_end)
print("Message:", diagnostic.message)

if diagnostic.converged and diagnostic.root is not None:
    contact_time = engine.ts.tt_jd(diagnostic.root)
    print("C1 UTC:", time_to_utc_iso(contact_time))
else:
    print("Contact was not solved; inspect the diagnostic status and message.")
