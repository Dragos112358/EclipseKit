# Lunar-eclipse calculations

EclipseKit provides a geocentric lunar-eclipse solver with a non-circular
Earth-shadow model. The default is the **Herald--Sinnott (2014) oblate-Earth
prescription**, including the empirically adopted 87 km notional eclipse-forming
layer (NEL). It is separate from the solar-eclipse solver: lunar-eclipse contacts
are tangencies between the Moon's disc and the terrestrial penumbral/umbral
shadow, not contacts of a terrestrial observer with a solar shadow cone.

The calculation is still a numerical astronomy model, not a claim of exact
physical truth. Contact-time precision depends on the SPK kernel, time scale,
Earth-orientation data, adopted body radii and the physical shadow prescription.

## Public API

```python
from eclipsekit import EclipseEngine

engine = EclipseEngine("de440s")

# Find the next geocentric lunar eclipse.
event = engine.find_next_lunar_eclipse("2025-01-01")
if event is not None:
    print(event.eclipse_type)
    print(event.to_dict())

# Search a civil-date interval.
events = engine.find_lunar_eclipses("2025-01-01", "2026-01-01")

# Reproduce a proleptic Julian date interpretation.
event = engine.calculate_lunar_eclipse(
    "2025-03-01T12:00:00", calendar="julian"
)
```

`find_lunar_eclipses(start, end)` uses Skyfield full-moon phase times only to
seed candidate epochs. Each candidate is independently tested against the
Earth-shadow model. Its interval is half-open: the start is included and the end
is excluded (`[start, end)`). Date-only strings and `date` objects are interpreted
at civil midnight for both boundaries, so
`find_lunar_eclipses("2025-03-14", "2025-03-15")` searches the complete civil day
of 14 March. Explicit timestamps remain exact instants. This interval behavior is
intentionally distinct from `EclipseEngine.time("YYYY-MM-DD")`, which continues
to interpret a date-only value at 12:00 as a useful centre for a single-event
calculation window. `calculate_lunar_eclipse(when)` expects a date/time near a
full moon. `find_next_lunar_eclipse(start)` searches forward (550 days by
default); a date-only `start` begins at civil midnight.

The result provides:

- `eclipse_type`: `penumbral`, `partial`, or `total`;
- penumbral and umbral magnitudes, plus the geocentric shadow-axis distance;
- P1, U1, U2, greatest eclipse, U3, U4 and P4, where the relevant contacts exist;
- penumbral, partial and totality durations;
- angle-dependent umbral/penumbral radii at the Moon-centre position angle;
- the shadow model, NEL height, flattening coefficient and effective Earth-radius factor;
- distinct UTC, UT1 and TT values in `to_dict()` (`*_utc`, `*_ut1`, `*_jd_tt`);
- the selected civil calendar and scientific warnings.

The geocentric contact instants are independent of where an observer is located.
`lunar_eclipse_city_visibility()` separately calculates topocentric Moon altitude
at greatest eclipse and at each geocentric contact. It reports which phases occur
while the Moon is above the requested altitude threshold; it does not invent
local contact times or substitute moonrise/moonset for a geocentric contact.

## Default shadow model: Herald--Sinnott oblate Earth

The default call is:

```python
event = engine.calculate_lunar_eclipse(
    "2025-03-14T06:55:00Z",
    shadow_model="herald_sinnott",
    atmospheric_nel_height_km=87.0,
    flattening_coefficient=0.003353,
    shadow_enlargement=1.0,
)
```

At each TT Julian date, the engine obtains apparent geocentric Sun and Moon
vectors in the same Earth-fixed ITRS frame. The positive Z axis is Earth's north
rotation pole. It computes the angular separation `gamma` between the Moon's
geocentric direction and the anti-solar shadow axis, and the Moon's angular
semidiameter `S_m`.

Let:

- `pi_m = asin(a / D_m)` be the Moon's equatorial horizontal parallax;
- `pi_s = asin(a / D_s)` be the Sun's equatorial horizontal parallax;
- `S_s = asin(R_sun / D_s)` be the Sun's geocentric semidiameter;
- `a` be Earth's WGS84 equatorial radius (6378.137 km by default);
- `h = H_NEL / a`, with `H_NEL = 87 km` by default;
- `psi` be the shadow-boundary position angle measured from the east-west axis,
  positive toward celestial north;
- `delta_s` be the apparent geocentric solar declination in the Earth-equatorial
  frame.

Herald and Sinnott's effective Earth radius, in equatorial Earth radii, is
computed iteratively as:

\[
R_E(\psi)=1+h-f_E\sin^2\psi\,
          \cos^2\!\left(\delta_s+q\sin\psi\right),
\]

where `f_E = 0.003353` is the published oblateness coefficient and

\[
q=S_s-R_E\,\pi_s.
\]

Two fixed-point updates are used; the source notes that one iteration is
sufficient for the stated prescription. The angular polar radii of the shadows
are then:

\[
r_u(\psi)=R_E(\psi)\,\pi_m-S_s+\pi_s,
\]

\[
r_p(\psi)=R_E(\psi)\,\pi_m+S_s+\pi_s.
\]

Thus the shadow boundaries are not circles: their radii vary with position
angle according to Earth's oblateness and the Sun's declination. The penumbral
boundary uses the same angle-dependent Earth-radius term; the source notes that
the resulting oblateness effect on the penumbra is small.

The standard model uses `shadow_enlargement=1.0`; the atmospheric layer is
already represented by `atmospheric_nel_height_km=87.0`. The default lunar-disc
radius is the mean lunar radius (1737.4 km), independent of the separate lunar
limb radii used by the solar-eclipse contact solver. Pass `moon_radius_km=`
explicitly to reproduce another published radius convention. The
`shadow_enlargement` argument is retained as an optional additional multiplier
for reproducing a separately specified shadow convention. Do not set it to 1.02
on top of the standard NEL unless a particular reference explicitly requires
that additional scaling.

### Contact calculation

For each time, EclipseKit parameterizes the penumbral and umbral boundaries as
angle-dependent radial curves on the celestial sphere. It finds the minimum
great-circle distance from the Moon centre to each curve. External contacts
(P1/P4 and U1/U4) occur when that distance equals the lunar angular radius from
outside; internal contacts (U2/U3) occur when the Moon is wholly inside the umbra
and the distance to the boundary equals the lunar angular radius from inside.

A coarse radial clearance is used only to bracket each contact. The final root is
refined against the exact spherical distance to the non-circular boundary using
bisection to `contact_tolerance_seconds` (0.05 s by default). The 96-point angular
boundary scan locates the closest boundary segment; a bounded golden-section
minimization refines its position angle. `boundary_samples` can be raised for
additional robustness near very shallow grazing geometries (minimum 24).

Greatest eclipse is the instant when the geocentric lunar centre has minimum
perpendicular distance (minimum gamma) from the shadow axis. The umbral and
penumbral magnitudes use the signed shortest
angular distance from the lunar centre to the corresponding non-circular shadow
boundary. This generalizes the conventional diameter-normalized circular
formula; the values are not illuminated-area fractions. The serialized `gamma`
is the **nonnegative** axis distance in equatorial Earth radii, while
`epsilon_deg` is the same separation expressed as an angle in degrees. It does
not preserve the sign convention used for the signed `Gamma` values in some
published catalogues (including EclipseWise); compare its absolute value when
validating the axis-distance magnitude.

### Legacy circular model

For reproducing older EclipseKit Alpha results, the earlier circular-cone model
remains selectable:

```python
event = engine.calculate_lunar_eclipse(
    "2025-03-14T06:55:00Z",
    shadow_model="circular",
)
```

This option is not the default and does not apply the oblate-Earth/NEL model.

## Julian and Gregorian civil calendars

Astronomical calculations use continuous Julian Dates (TT) internally. The
`calendar` parameter controls how naive civil dates are interpreted and how
result timestamps are rendered; it does not change the physical instant or the
geocentric geometry.

- `"historical"` (default): Julian through 1582-10-04, then Gregorian from
  1582-10-15; the skipped dates 1582-10-05 through 1582-10-14 are rejected.
- `"julian"`: proleptic Julian calendar for every date.
- `"gregorian"`: proleptic Gregorian calendar for every date.

The option is available on `EclipseEngine.time`, `time_from_calendar`,
`calculate_lunar_eclipse`, `find_lunar_eclipses`, `find_next_lunar_eclipse` and
`LunarEclipseResult.to_dict`. Naive ISO strings such as
`"1500-02-29T12:00:00"` use the selected calendar. ISO strings with `Z` or a
numeric UTC offset, and Python `datetime` values, are absolute instants and are
not reinterpreted as Julian civil fields. Python `date` values use their
year/month/day fields under the selected calendar.

`to_dict()` distinguishes:

- `*_utc`: civil UTC representation;
- `*_ut1`: Earth-rotation time, explicitly labelled `UT1` (not `Z`);
- `*_jd_tt`: continuous TT Julian Date.

For historic dates, UT1/UTC conversion depends on the selected Delta-T model.
The built-in Espenak--Meeus polynomial is an estimate outside the modern
observational range; its uncertainty can dominate historical timing error.
For modern precision work, configure IERS Earth-orientation data, for example
`EarthOrientationConfig.iers()`, and record its provenance. Fixed Delta-T is
only appropriate when reproducing a reference that explicitly specifies it.

## Independent reference regression

EclipseWise publishes a detailed solution for the total lunar eclipse of
2025-03-14 (JPL DE430; Herald--Sinnott shadow model; Delta-T 71.7 s):

- greatest eclipse: 06:59:56.2 TD / 06:58:44.5 UT1;
- penumbral magnitude: 2.26146;
- umbral magnitude: 1.18038;
- P1: 03:57:09.4 UT1; U1: 05:09:22.6; U2: 06:25:57.5;
- U3: 07:32:01.5; U4: 08:48:18.5; P4: 10:00:31.9.

Source: Fred Espenak, [EclipseWise — Total Lunar Eclipse of 2025 Mar 14](https://eclipsewise.com/lunar/LEprime/2001-2100/LE2025Mar14Tprime.html).
The source identifies its predictions as using JPL DE430 and the Herald--Sinnott
shadow method. The test suite includes a geometry regression reconstructed from
the rounded RA/Dec, parallax and semidiameter values printed on that page. Full
event/contact regression should use the same ephemeris, Delta-T and shadow
convention; differences in kernel and Earth-orientation data must be recorded.

For a frozen 16-event comparison matrix spanning 2022–2028, the command-line
validation tool, tolerances, source URLs and interpretation guide, see
[LUNAR_REFERENCE_VALIDATION_2022_2028.md](LUNAR_REFERENCE_VALIDATION_2022_2028.md)
and run `python scripts/validate_lunar_references.py --kernel de440s` from the
repository root. The historical 2022–2025 results supplied during development
pass all eight reference cases with the tested configuration; the 2026–2028
cases are retained as additional regression targets until evaluated against
the local ephemeris and time-scale configuration.

## Accuracy and scientific status

The default model is substantially more complete than a spherical-shadow
approximation, but it is not an assertion of mathematically exact atmospheric
physics. The 87 km NEL is an empirical, globally uniform layer inferred from
historical contact and crater-timing observations. The implementation uses the
published angle-dependent oblate-Earth radius prescription; it does not resolve
wavelength-dependent atmospheric refraction, local atmospheric structure,
mountain topography, or spatially varying opacity. It also uses an adopted mean
lunar radius for the shadow-contact disc rather than a limb-topography correction
for the Moon.

The reported contacts are geocentric. Local visibility is a separate topocentric
question. For very shallow grazing eclipses, compare against an independent
canon with the same shadow rule and ensure the angular boundary sampling is
converged. A small numerical root tolerance is not itself a physical accuracy
claim.

## References

- Fred Espenak, *21st Century Canon of Lunar Eclipses*, section 2.3, “Earth's
  Elliptical Shadows” (Herald & Sinnott model and Eq. 2-5):
  [shadow-model extract](https://www.eclipsewise.com/pubs/images/21CCLE-Shadows.pdf).
- Fred Espenak, [EclipseWise lunar eclipse catalogues](https://eclipsewise.com/lunar/).
- Nugnes & Colombo (2023), “Analytical determination of eclipse entry and exit
  points considering a conical shadow and oblate Earth,” *Acta Astronautica* 211,
  795–807, [DOI: 10.1016/j.actaastro.2023.07.007](https://doi.org/10.1016/j.actaastro.2023.07.007).
