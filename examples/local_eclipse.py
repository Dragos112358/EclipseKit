from eclipsekit import EclipseEngine, Observer

engine = EclipseEngine("de440s")  # alternatively: de432s, de440, de441, or a local .bsp path
site = Observer(42.0, -5.0, elevation_m=0, name="Example observer")
result = engine.calculate_local(site, "2026-08-12")

if result is None:
    print("No local eclipse found in the search horizon.")
else:
    print(engine.format_report(result))
