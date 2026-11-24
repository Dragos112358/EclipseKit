# Earth-orientation and time-scale policy

EclipseKit separates three concepts that must not be collapsed into one number:

- **UTC**: civil clock labels used by ordinary ISO timestamps and user input.
- **UT1**: Earth-rotation time used for the orientation of the terrestrial frame.
- **TT**: uniform dynamical time used to evaluate the planetary/lunar ephemeris.

Skyfield exposes `delta_t = TT - UT1` and `dut1 = UT1 - UTC`. The relationship
is therefore `delta_t = (TT - UTC) - dut1`. A custom Delta-T value changes the
implied DUT1 when a Skyfield `Time` is constructed from UTC.

## Supported modes

| Mode | Skyfield construction | Intended use |
|---|---|---|
| `builtin` | `Loader.timescale()` | Offline-friendly default using Skyfield's bundled tables |
| `iers` | `Loader.timescale(builtin=False)` | Operational Earth orientation using IERS `finals2000A.all` |
| `fixed_delta_t` | `Loader.timescale(delta_t=value)` | Reproduce a publication that explicitly states a historical Delta-T assumption |

Example:

```python
from eclipsekit import EclipseEngine, EarthOrientationConfig

# Default / offline-friendly
engine = EclipseEngine.from_jpl("de440s")

# Load IERS finals2000A.all (Internet may be required on first run)
iers_engine = EclipseEngine.from_jpl(
    "de440s", earth_orientation=EarthOrientationConfig.iers()
)

# Reproduce the specific 2026 NASA path-table prediction only
legacy_engine = EclipseEngine.from_jpl(
    "de440s", earth_orientation=EarthOrientationConfig.fixed(71.4)
)
```

`engine.time(...)` interprets ISO strings and Python datetimes as UTC.
`engine.time_from_ut1(year, month, day, hour, minute, second)` explicitly
constructs a time from UT1 fields. Do not silently interpret a source's `UT`
clock column as UTC; record the source convention in the reference data.

Inspect the exact time-scale realization at a date:

```python
print(engine.time_scale_diagnostics("2026-08-12T18:30:00Z") )
```

The diagnostic reports the selected mode, Delta-T, DUT1, and whether the
implied DUT1 lies within the UTC convention's ±0.9 second limit.

## Why the 2026 NASA path table is a special case

The NASA GSFC path page for 12 August 2026 states that its table was generated
with VSOP87/ELP2000-85 and `Delta-T = 71.4 s`. The EclipseKit diagnostic
comparison produced:

| Realization | Delta-T | DUT1 | Mean error vs NASA path subset | Max error |
|---|---:|---:|---:|---:|
| Skyfield bundled | 69.099009 s | +0.084991 s | 4.179 km (UT1 labels) | 9.697 km |
| IERS `finals2000A.all` | 69.172744 s | +0.011256 s | 4.072 km (UT1 labels) | 9.444 km |
| Fixed NASA path-table assumption | 71.4 s | -2.216 s | 0.823 km (UT1 labels) | 1.800 km |

The IERS result is close to Skyfield's bundled value; changing from bundled to
IERS therefore does not explain the roughly 9 km endpoint difference. The
fixed 71.4 s mode reproduces the time assumption of the older NASA path product,
but its derived DUT1 is outside the normal UTC range. It is a **historical
prediction reproduction mode**, not an operational estimate of the actual
Earth rotation on the eclipse date.

NASA also publishes other 2026 prediction products using different ephemeris
realizations and a different Delta-T value (for example, its eclipse search
map/canonical Besselian products). Do not combine their coordinate tables,
clock labels, ephemerides, and Delta-T assumptions as though they formed one
single reference solution.

## Recommended policy

1. Use `iers` when the task requires observed Earth orientation and the IERS
   data are available for the date. Preserve the downloaded `finals2000A.all`
   file and record its provenance/version for reproducible research.
2. Use `builtin` for offline work and repeatable unit/integration tests. Record
   the Skyfield version because bundled Earth-orientation tables can change
   between releases.
3. Use `fixed_delta_t` only when reproducing a specific named publication.
   Always record the publication, ephemeris realization, its stated Delta-T,
   and whether the reference clock is UT1 or UTC.
4. Never tune Delta-T solely to minimize a path residual. A close match to one
   published path does not prove that the fixed value is the physically correct
   Earth-orientation model for another use.
5. Report the time scale alongside every scientific validation result.
