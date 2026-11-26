---
description: Understand and retrieve C1, C2, C3 and C4 contact times from EclipseKit local solar-eclipse calculations.
---

# Solar-eclipse contact times: C1, C2, C3 and C4

For a local solar-eclipse calculation, EclipseKit exposes contact results through the structured `result.contacts` object.

| Contact | Meaning |
|---|---|
| C1 | First external contact; the partial phase begins |
| C2 | Second contact; the central phase begins for a total or annular eclipse |
| C3 | Third contact; the central phase ends |
| C4 | Fourth external contact; the partial phase ends |

C2 and C3 are only applicable when the observer experiences a central eclipse. For a partial eclipse, those internal contacts do not occur at that location.

## Retrieve the contacts

```python
from eclipsekit import EclipseEngine, Observer

engine = EclipseEngine.from_jpl("de440s")
observer = Observer(42.6, -5.5703, name="León, Spain")

result = engine.calculate_local(observer, "2026-08-12")

if result is not None:
    contacts = result.contacts

    for name in ("c1", "c2", "c3", "c4"):
        value = getattr(contacts, name)
        if value is not None:
            print(name.upper(), value)
```

For a human-readable report, use:

```python
print(engine.format_report(result))
```

For structured interchange:

```python
payload = result.to_dict()
```

## Precision and interpretation

A numerical root tolerance describes how accurately the solver locates a root for the selected model. It is not, by itself, a complete estimate of physical prediction uncertainty. The ephemeris, Earth orientation, time-scale assumptions, observer coordinates, adopted radii and any limb model can affect reported contact times.

For the event model and solver details, see:

- [Contact event model](CONTACT_EVENT_MODEL.md)
- [Contact solver](CONTACT_SOLVER_V2.md)
- [Uncertainty propagation](UNCERTAINTY_PROPAGATION.md)
- [Scientific validation](SCIENTIFIC_VALIDATION.md)
