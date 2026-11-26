---
description: Find lunar eclipses in Python with EclipseKit, calculate geocentric P1 through P4 contacts and assess local visibility from an observing site.
---

# Python lunar-eclipse calculator

EclipseKit provides a geocentric lunar-eclipse solver and a separate topocentric local-visibility calculation.

## Find the next lunar eclipse

```python
from eclipsekit import EclipseEngine

engine = EclipseEngine.from_jpl("de440s")

event = engine.find_next_lunar_eclipse("2025-01-01")

if event is not None:
    print("Type:", event.eclipse_type)
    print(event.to_dict())
else:
    print("No event found in the search horizon.")
```

To search a date interval:

```python
events = engine.find_lunar_eclipses(
    "2025-01-01",
    "2026-01-01",
)

for event in events:
    print(event.eclipse_type, event.to_dict())
```

The geocentric result can contain P1, U1, U2, greatest eclipse, U3, U4 and P4, as applicable. These are global shadow contacts and do not depend on an observer's location.

## Check local visibility

Use `lunar_eclipse_local_visibility()` to determine which parts of the event are above the local horizon.

```python
from eclipsekit import EclipseEngine, Observer

engine = EclipseEngine.from_jpl("de440s")

observer = Observer(
    latitude=44.4268,
    longitude=26.1025,
    elevation_m=80.0,
    name="Bucharest",
    country="Romania",
)

local = engine.lunar_eclipse_local_visibility(
    observer,
    "2027-07-18",
    apply_refraction=True,
    sample_interval_seconds=120,
)

if local is not None:
    print(local["visibility_status"])
    print("Moonrise:", local["moonrise_utc"])
    print("Moonset:", local["moonset_utc"])
    print("Visible intervals:", local["observable_intervals"])
    print("Phase visibility:", local["phase_visibility"])
```

Local visibility is distinct from the geocentric event contacts. Moonrise or moonset can clip the visible part of an eclipse. Refraction and the optional horizon profile affect local visibility, not the underlying geocentric contacts.

## Shadow model and assumptions

The documented default uses the Herald–Sinnott oblate-Earth prescription with an 87 km notional eclipse-forming atmospheric layer. This is an empirical geometric model, not a resolved, time-varying atmospheric simulation. The adopted lunar radius and reference convention can affect grazing contacts.

See:

- [Lunar-eclipse calculations](LUNAR_ECLIPSES.md)
- [Lunar-eclipse methodology and accuracy](LUNAR_ECLIPSE_METHODOLOGY.md)
- [Lunar reference validation](LUNAR_REFERENCE_VALIDATION_2022_2028.md)
- [Runnable lunar example](https://github.com/Dragos112358/EclipseKit/blob/main/examples/lunar_eclipse.py)
