# Phase 11 — Advanced Eclipse Prediction Engine

## Scope

Phase 11 adds bounded solar-eclipse discovery for a time interval and explicit
multi-observer evaluation. It reuses Skyfield's new-moon phase events only to
seed candidate conjunctions; it then refines geocentric maximum and calls the
existing local contact solver independently for each observer.

## Python API

```python
from eclipsekit import EclipseEngine, Observer

engine = EclipseEngine("de440s")
observers = [
    Observer(44.4268, 26.1025, name="Bucharest", country="Romania"),
    Observer(40.4168, -3.7038, name="Madrid", country="Spain"),
    Observer(30.0444, 31.2357, name="Cairo", country="Egypt"),
]

result = engine.search_solar_eclipses(
    "2026-01-01",
    "2028-01-01",
    observers,
    min_magnitude=0.01,
)

print(result.to_dict())
```

`search_solar_eclipses(start, end, observers, ...)` accepts any iterable of
`Observer` objects. For each new moon in an expanded discovery interval it
computes a geocentric maximum, then obtains local maximum and contact
circumstances at every requested observer. It returns an event only when at
least one requested observer has a local eclipse meeting the magnitude filter.

The interval applies to each **local maximum**: results are kept only when the
local maximum lies between `start` and `end`, inclusive. Each observer is
calculated independently and can have a different local maximum. The default
local search window is +/- 12 hours around geocentric maximum; it can be reduced
or widened up to 24 hours. The method never invokes the "find next eclipse"
fallback outside the requested interval.

The result types are `SolarEclipseSearchResult`, `SolarEclipseSearchEvent`, and
`SolarEclipseLocationHit`. They provide event counts and `to_dict()` output,
including the requested interval, new moons examined, geocentric maximum, and
each location's full `LocalEclipseResult` serialization.

Optional `include_sunrise_sunset`, `include_shadow_metrics`, and
`include_planets` flags are passed through to the local calculation; all default
to `False` to avoid doing work that a batch search may not need. A lunar-limb
provider may be supplied with `limb_model=`; the legacy `limb_corrector=` alias
is preserved.

## Constraints and scientific interpretation

- The search is only as spatially complete as the explicit observer list. It
does not infer visibility for unlisted points or continuously scan the globe.
- New moon is a candidate-generation mechanism, not proof of an eclipse.
  Local geometry and contact calculations determine whether each observer has
  a local event.
- `min_magnitude` is a filter on the local apparent-disk magnitude. It is not
  an obscuration percentage or a probability of successful observation.
- The discovery interval is padded by one day at both ends, then local maxima
  are filtered against the exact requested interval.
- This phase does not add new ephemerides, alter contact models, or certify
  prediction accuracy. Scientific acceptance still requires comparisons with
  independent published cases and explicit time-scale/kernel provenance.

## Example

Run the multi-location example with a locally available kernel/cache:

```powershell
python examples/solar_eclipse_interval_search.py `
  --start 2026-01-01 --end 2028-01-01 `
  --kernel de440s --output reports/phase11-search.json
```

The sample locations in the example are illustrative; replace them with the
observers relevant to the study. The command does not geocode place names or
download location catalogues.
