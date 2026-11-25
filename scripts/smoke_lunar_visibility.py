from eclipsekit import EclipseEngine, Observer

engine = EclipseEngine("de430")

# TEST A: Agartala, India — 8 November 2022
agartala = Observer(
    latitude=23.8315,
    longitude=91.2868,
    elevation_m=16.0,
    name="Agartala",
    country="India",
)

india = engine.lunar_eclipse_local_visibility(
    agartala,
    "2022-11-08",
    apply_refraction=True,
    sample_interval_seconds=60,
)

assert india is not None
assert india["phase_visibility"]["totality"]["visible"]
assert india["observable_intervals"][0]["start_cause"] == "moonrise"

print("\nAGARTALA — 2022-11-08")
print("Status:", india["visibility_status"])
print("Moonrise:", india["moonrise_utc"])
print("Intervals:", india["observable_intervals"])
print("Totality:", india["phase_visibility"]["totality"])

# TEST B: London — 14 March 2025
london = Observer(
    latitude=51.5074,
    longitude=-0.1278,
    elevation_m=11.0,
    name="London",
    country="United Kingdom",
)

uk = engine.lunar_eclipse_local_visibility(
    london,
    "2025-03-14",
    apply_refraction=True,
    sample_interval_seconds=60,
)

assert uk is not None
assert uk["phase_visibility"]["penumbral"]["visible"]
assert uk["phase_visibility"]["partial"]["visible"]
assert not uk["phase_visibility"]["totality"]["visible"]
assert uk["observable_intervals"][-1]["end_cause"] == "moonset"

print("\nLONDON — 2025-03-14")
print("Status:", uk["visibility_status"])
print("Moonset:", uk["moonset_utc"])
print("Intervals:", uk["observable_intervals"])
print("Totality:", uk["phase_visibility"]["totality"])

print("\nBoth real-event visibility smoke tests passed.")
