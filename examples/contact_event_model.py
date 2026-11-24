"""Demonstrate structured C1/C2/maximum/C3/C4 event metadata."""

import json

from eclipsekit import EclipseConfig, EclipseEngine, Observer, SolverConfig


config = EclipseConfig(solver=SolverConfig(root_method="brent"))
engine = EclipseEngine(config=config)
observer = Observer(
    42.6,
    -5.5703,
    elevation_m=800.0,
    name="León",
    country="Spain",
)
result = engine.calculate_local(
    observer,
    "2026-08-12",
    find_next_if_none=False,
    include_sunrise_sunset=False,
    include_shadow_metrics=False,
    include_planets=False,
)

if result is None:
    raise SystemExit("No local eclipse found for the selected observer and date.")

print("Event sequence:")
for name, event in result.contact_events.items():
    solver = event.solver_result
    solver_summary = (
        f"{solver.status}/{solver.method}, residual={solver.residual!r}"
        if solver is not None else "minimum refinement"
    )
    print(
        f"{name:7s} {event.time_utc}  "
        f"PA={event.position_angle_deg!r}°  "
        f"vertex={event.vertex_angle_deg!r}°  "
        f"Sun alt={event.sun_altitude_deg:.3f}°  "
        f"visibility={event.visibility_status}  {solver_summary}"
    )

print("Central phase duration:", result.central_phase_duration_seconds)
print("Uncertainty:", result.contact_events["MAXIMUM"].uncertainty_seconds)
print("JSON keys:", list(result.to_dict()))
# Full structured output is JSON serializable.
json.dumps(result.to_dict(), indent=2)
