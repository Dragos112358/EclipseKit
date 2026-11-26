---
description: Calculate local solar-eclipse circumstances in Python with EclipseKit, including maximum eclipse, magnitude, obscuration and applicable contacts.
---

# Python solar-eclipse calculator

Use `EclipseEngine.calculate_local()` to calculate the circumstances of a solar eclipse for a geographic observer.

## Example: 12 August 2026 near León, Spain

```python
from eclipsekit import EclipseEngine, Observer

engine = EclipseEngine.from_jpl("de440s")

observer = Observer(
    latitude=42.6,
    longitude=-5.5703,
    name="León, Spain",
)

result = engine.calculate_local(observer, "2026-08-12")

if result is None:
    print("No local eclipse was found in the search horizon.")
else:
    print(engine.format_report(result))

    print("Maximum:", result.maximum)
    print("Magnitude:", result.magnitude)
    print("Obscuration:", result.obscuration_percent)
    print("C1:", result.contacts.c1)
    print("C2:", result.contacts.c2)
    print("C3:", result.contacts.c3)
    print("C4:", result.contacts.c4)
```

The exact fields available depend on the event type and the result model. Use `engine.format_report(result)` for a readable summary and `result.to_dict()` for a JSON-friendly representation.

## Inputs to record for reproducibility

Record at least:

- Observer latitude, longitude and elevation.
- Event date/time and the interpretation of date-only input.
- JPL kernel name or local SPK/BSP path.
- Earth-orientation and time-scale configuration.
- Adopted radii and contact-model settings.
- EclipseKit and dependency versions.

## Related documentation

- [C1–C4 contact times](solar-eclipse-contacts.md)
- [Contact event model](CONTACT_EVENT_MODEL.md)
- [Contact solver](CONTACT_SOLVER_V2.md)
- [Configuration API](CONFIGURATION_API.md)
- [Runnable local-eclipse example](https://github.com/Dragos112358/EclipseKit/blob/main/examples/local_eclipse.py)
