# Lunar-eclipse methodology and accuracy

This document describes the two separate calculations exposed by EclipseKit:
(1) geocentric lunar-eclipse circumstances and (2) topocentric visibility from a
particular observing site. The distinction is important: P1/U1/U2/greatest/U3/U4/P4
are global geometric contacts, while moonrise and moonset are local horizon events.

## 1. Geocentric eclipse model

The default shadow model is the Herald--Sinnott oblate-Earth prescription. It
uses an 87 km notional eclipse-forming layer and an angle-dependent effective
Earth radius to account for the Earth's oblateness at the shadow contact point.
The model is empirical; the 87 km layer is not a resolved, time-varying
atmospheric simulation.

At a given TT Julian Date, EclipseKit obtains apparent geocentric Sun and Moon
vectors in the Earth-fixed ITRS frame. The solver derives the Moon-to-shadow-axis
separation, evaluates non-circular penumbral and umbral boundaries, and finds
the minimum signed spherical distance from the lunar centre to each boundary.
Contact roots are refined against the exact boundary-distance residual rather
than relying solely on a circular or radial approximation.

The contacts mean:

| Contact | Meaning |
|---|---|
| P1 | First external contact with the penumbra |
| U1 | First external contact with the umbra; partial phase begins |
| U2 | First internal contact; totality begins |
| Greatest | Moon centre is closest to the shadow axis |
| U3 | Last internal contact; totality ends |
| U4 | Last external umbral contact; partial phase ends |
| P4 | Last external contact with the penumbra |

P1/P4 exist for penumbral, partial and total events. U1/U4 exist for partial
and total events. U2/U3 exist only for total events. These contacts are not
moonrise or moonset times and do not depend on an observer's location.

Penumbral and umbral magnitudes are signed, diameter-normalized measures of
lunar-disc penetration into the corresponding shadow boundary. They are not
fractions of the lunar surface area covered or darkened. Greatest eclipse is
reported separately from the four kinds of contact pairs.

## 2. Adopted radii and the 18 July 2027 grazing case

The standard shadow-contact lunar radius is **1737.4 km**, the IAU/JPL volumetric
mean radius. Keep this as the normal physical default. EclipseKit does not use
the separate solar-eclipse limb peak/valley radii for lunar-shadow contacts.

The frozen EclipseWise matrix contains an explicit source-reproduction override
for 18 July 2027: 1737.979126 km, inferred by inverting that page's rounded
lunar semidiameter and geocentric distance. That value is **not** a universal
physical radius and is not the library default.

With DE430 and Skyfield's built-in time-scale data, the observed development
run had these outcomes:

- 15/16 reference events passed with the 1737.4 km default radius.
- The only default-radius failure was the extremely shallow penumbral grazing
event on 18 July 2027: P1 differed by +40.51 s and P4 by -33.12 s. Greatest
  eclipse differed by +1.63 s. Magnitude differences were -0.000430 (penumbral)
  and -0.000797 (umbral), within the configured magnitude tolerance.
- All 16/16 events passed when the reference-only per-event radius override was
enabled. This reproduces the source's rounded semidiameter convention; it does
not mean that the same radius should be used for ordinary predictions.
- Doubling angular boundary samples from 384 to 768 and halving the contact
  search step from 60 s to 30 s did not materially change this residual. The
  remaining mismatch is therefore not explained by those two numerical
  resolution settings.

Do not change the library-wide radius or loosen the validator's 30 s contact
threshold merely to make this one grazing event pass. Report the default-radius
result and the reference-convention reproduction separately. For a production
release, describe this event as a known near-grazing reference-convention
residual.

## 3. Local topocentric visibility

Use `EclipseEngine.lunar_eclipse_local_visibility(observer, when)` when the
question is whether an observer can see any part of the eclipse. It calculates
Moon altitude and azimuth at the observing site across the full P1--P4 interval,
not only at greatest eclipse.

The method:

1. Converts the supplied `Observer` (latitude, longitude and elevation above
   sea level) into a Skyfield WGS84 topocentric observing location.
2. Samples the apparent topocentric Moon over a configurable search window
   around the eclipse. The default profile cadence is 300 seconds.
3. Computes the Moon's apparent altitude, azimuth and semidiameter at each
   sample. If a caller supplies `HorizonProfile`, its azimuth-dependent mask is
   applied at each sample.
4. Finds each sign change in the lunar-limb clearance function and refines the
   crossing by bisection to 0.1 seconds.
5. Intersects the resulting above-horizon intervals with P1--P4, U1--U4 and
   U2--U3. The result therefore identifies partial local visibility, including
   cases where P1 occurs before moonrise or P4 occurs after moonset.

The default `limb_visibility="upper"` declares the Moon visible when any part
of its disc clears the horizon; this is the usual moonrise/moonset convention.
`"center"` requires the lunar centre to clear the horizon, while `"lower"`
requires the full disc to clear it.

### Refraction and elevation

The observer's elevation is passed to Skyfield's WGS84 location. With
`apply_refraction=True` (the default follows the engine's atmosphere config),
Skyfield's standard-atmosphere pressure estimate (adjusted for observer
elevation) is used when the engine has its default 1013.25 mbar pressure. A
non-default engine pressure or an explicit `pressure_mbar` is treated as station
pressure. `temperature_c` defaults to the engine's configured temperature. Set
`apply_refraction=False` to use geometric, unrefracted altitudes. Explicit
pressure should be the local station pressure, not a sea-level weather-app
pressure unless that is what the configuration represents.

Atmospheric refraction near the horizon is variable. Temperature and pressure
inputs improve reproducibility but do not model local vertical atmospheric
profiles, inversions, extinction, diffraction, or weather. A `HorizonProfile`
is a caller-provided azimuth/altitude mask, not a DEM-derived terrain skyline.

### Example: Moon rises after P1

```python
from eclipsekit import EclipseEngine, Observer

engine = EclipseEngine("de440s")
site = Observer(
    latitude=44.4268,
    longitude=26.1025,
    elevation_m=80.0,
    name="Bucharest",
    country="Romania",
)

local = engine.lunar_eclipse_local_visibility(
    site,
    "2027-07-18",
    apply_refraction=True,
    sample_interval_seconds=120,
)

if local is not None:
    print(local["visibility_status"])
    print("Moonrise:", local["moonrise_utc"])
    print("Moonset:", local["moonset_utc"])
    print("Visible penumbral intervals:", local["observable_intervals"])
    print("Visible partial phase:", local["phase_visibility"]["partial"])
```

The returned `observable_intervals` are intersections of the global penumbral
interval with local above-horizon intervals. Their start/end causes are P1/P4
or moonrise/moonset. In `phase_visibility`, partial-phase interval boundaries
are identified as U1/U4, and totality boundaries as U2/U3; any interval clipped
by a local horizon crossing is identified as moonrise/moonset. The
`contact_visibility` mapping preserves the altitude and visibility state at
each geocentric contact. `altitude_profile` is a sampled profile; set
`include_altitude_profile=False` to omit its per-sample payload while retaining
crossings and extrema.

### City-catalogue screening

`lunar_eclipse_city_visibility(..., visibility_window="greatest")` preserves the
original fast filter at greatest eclipse. Set `visibility_window="any"` to
screen the entire P1--P4 period and include a city whose Moon is above the
requested centre-altitude threshold at any sample, even if it is below the
threshold at greatest eclipse. The returned first/last times are sample
brackets, not refined moonrise/moonset predictions. Use
`lunar_eclipse_local_visibility()` for exact local crossing refinement,
refraction and custom horizon masks.

## 4. Time scales and reproducibility

The solver's continuous independent variable is TT Julian Date. Serialized
results keep UTC, UT1 and TT distinct. UT1 describes Earth rotation; UTC is the
civil time scale; TT is used for ephemeris evaluation. Contact time comparisons
must use the same time-scale convention as the reference.

The apparent geocentric geometry depends on the SPK ephemeris. The relation
between TT and Earth-rotation time depends on Delta-T and, for modern dates, on
Earth-orientation data such as UT1-UTC and polar motion. To reproduce a published
reference, record its SPK kernel, Delta-T, shadow prescription, shadow
magnification/enlargement and adopted radii. A numerical root tolerance is a
solver setting, not a claim that the physical prediction is accurate to that
many seconds.

## 5. Validation commands

Run the test suite and the frozen event comparison from the repository root:

```powershell
python -m pytest -q
python scripts/validate_lunar_references.py `
  --kernel de430 `
  --boundary-samples 384 `
  --contact-step-seconds 60 `
  --solver-tolerance-seconds 0.01 `
  --json-output reports/lunar-reference-de430-default-radius.json
```

For a separate comparison against the rounded source semidiameter convention,
repeat with `--use-reference-moon-radii` and a different report filename. Do not
confuse that reproducibility run with the default-radius physical calculation.

## 6. Known limitations

- The shadow prescription is an empirical global atmospheric-layer model; it
  does not resolve wavelength-dependent atmospheric structure around Earth.
- The lunar disc is spherical with an adopted radius. Lunar limb topography is
  not yet applied to lunar-eclipse contacts.
- Local refraction uses a standard model and static pressure/temperature
  parameters; real near-horizon refraction can differ.
- Local skyline obstruction is only represented when the caller supplies a
  `HorizonProfile`; the library does not infer buildings, mountains or trees.
- City-catalogue `visibility_window="any"` is a sampling-based screening
  feature. The single-observer API provides the refined crossings and intervals.
- High-latitude grazing horizon events can be sensitive to the horizon profile
  and atmospheric assumptions. Always retain the selected options in reports.

## References

- Herald & Sinnott (2014), *Analysis of lunar crater timings*, Journal of the
  British Astronomical Association, 124, 247–253:
  <https://adsabs.harvard.edu/pdf/2014JBAA..124..247H>
- JPL Solar System Dynamics, satellite physical parameters (Moon mean radius):
  <https://ssd.jpl.nasa.gov/sats/phys_par/>
- NASA GSFC, Moon Fact Sheet (volumetric mean radius):
  <https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html>
- Skyfield, astronomical positions and refraction:
  <https://rhodesmill.org/skyfield/api-position.html>
- Skyfield, Moonrise/moonset definitions and elevated observers:
  <https://rhodesmill.org/skyfield/almanac.html>
- EclipseWise reference event pages are recorded per event in
  `tests/reference_data/lunar_eclipse_eclipsewise_2022_2028.json`.
