# Besselian Backend — Phase 4

EclipseKit now has an independent solar-eclipse backend that consumes explicit,
published Besselian elements. It does **not** derive those elements from the
active JPL kernel. The caller supplies the six time-dependent polynomial
quantities and the two shadow-cone angle tangents.

## Element convention and units

The eight inputs are:

| Element | Meaning | Units |
|---|---|---|
| `x`, `y` | Shadow-axis intersection with the fundamental plane | Earth equatorial radii |
| `d` | Shadow-axis declination | degrees |
| `mu` | Shadow-axis ephemeris hour angle | degrees |
| `l1` | Penumbral radius in the fundamental plane | Earth equatorial radii |
| `l2` | Signed umbral/antumbral radius in the fundamental plane | Earth equatorial radii |
| `tan_f1`, `tan_f2` | Tangents of the penumbral and umbral cone angles | dimensionless |

The six polynomial series are stored in ascending coefficient order:

\[
a(t)=c_0+c_1t+c_2t^2+c_3t^3,\qquad
 t=\frac{JD_{TT}-JD_{TT,0}}{1\ \mathrm{hour}}.
\]

`epoch_tt_jd` is the Besselian reference epoch in TT/TDT. The validity interval
is expressed as hours before/after that epoch. Published NASA tables commonly
use a cubic fit valid over a six-hour interval, but the class allows an explicit
shorter or longer interval and still enforces it by default. `mu` must be
unwrapped continuously through 360 degrees before coefficients are entered.

The NASA/GSFC coefficient convention is labelled `mu_convention="ephemeris"`.
For local Earth-fixed circumstances, EclipseKit reduces μ by the supplied ΔT:

\[
\mu_{UT1}=\mu-\Delta T\,(1.002738\times15/3600)\quad[\mathrm{degrees}].
\]

Use `mu_convention="ut1"` only for coefficients whose μ has already been
reduced to UT1; no second ΔT correction is then applied. The backend accepts a
constant ΔT (useful for reproducing a published prediction) or a callable of TT
Julian Date (useful when connected to an Earth-orientation source).

## Public API

```python
from eclipsekit import (
    BesselianElements, BesselianSolver, EclipseConfig,
    BesselianConfig, SolverConfig, Observer,
)

# `elements.json` follows the format in data/validation/besselian_1999_aug11_nasa.json.
elements = BesselianElements.from_json("elements.json")
config = EclipseConfig(
    besselian=BesselianConfig(),
    solver=SolverConfig(root_method="brent"),
)
solver = BesselianSolver(config=config.besselian, solver_config=config.solver)

observer = Observer(45.075, 24.30, name="Example site")
local = solver.calculate_local(
    elements, observer, delta_t_seconds=63.7,
)
print(local.eclipse_type)
print(local.contacts["C2"].jd_tt if "C2" in local.contacts else None)

maximum_jd_tt = solver.find_global_maximum(elements)
path = solver.global_central_line(
    elements,
    elements.epoch_tt_jd - 1 / 24,
    elements.epoch_tt_jd + 1 / 24,
    samples=101,
    delta_t_seconds=63.7,
)
```

`BesselianLocalResult` contains C1–C4 roots (when present), TT Julian Dates,
solver diagnostics, partial and central durations, the best-fit local maximum
state, selected source/ephemeris metadata, and warnings. It deliberately keeps
TT JDs rather than creating a new time-scale service. When used through an
`EclipseEngine`, convert a result time to Skyfield `Time` with
`engine.ts.tt_jd(jd_tt)`.

`EclipseEngine` also exposes three opt-in methods that keep the backends
separate:

- `calculate_local_besselian(elements, observer, ...)` — local Besselian result;
- `find_global_maximum_besselian(elements, ...)` — geocentric closest approach;
- `besselian_global_shadow_path(elements, start, end, ...)` — central-axis
  ground-track points.

When the engine wrapper is used and `delta_t_seconds` is omitted, it supplies
ΔT from the engine's configured Skyfield TT/UT1 time scales. Pass a fixed ΔT
explicitly to reproduce a published catalogue's clock convention. The runnable
`examples/besselian_engine_integration.py` exercises these wrappers and requires
the same `de440s` kernel access as the rest of `EclipseEngine`.

## Local and global geometry

For a geodetic observer, the backend first calculates the observer's WGS84
geocentric coordinates, then projects them into the moving fundamental plane:

\[
\begin{aligned}
\xi &= \rho\cos\phi'\sin H,\\
\eta &= \rho\sin\phi'\cos d-\rho\cos\phi'\sin d\cos H,\\
\zeta &= \rho\sin\phi'\sin d+\rho\cos\phi'\cos d\cos H,
\end{aligned}
\]

where \(H=\mu_{UT1}+\lambda_E\) and east longitude is positive. With
\(u=x-\xi\), \(v=y-\eta\), the local axis distance is
\(m=\sqrt{u^2+v^2}\), while the cone radii at the observer's fundamental-plane
height are \(L_1'=l_1-\zeta\tan f_1\) and
\(L_2'=l_2-\zeta\tan f_2\). External and internal boundaries are found by
solving \(m-L_1'=0\) and \(m-|L_2'|=0\), respectively.

The signed `L2` convention is retained: a negative effective `L2` denotes the
umbra (totality), while a positive effective `L2` denotes the antumbra
(annularity). The internal contact radius is its absolute value.

The global central-line routine intersects the shadow axis with the oblate
Earth. `BesselianGlobalPoint.umbral_radius_fundamental_km` is the absolute
cross-sectional radius evaluated in the fundamental-plane construction; it is
**not** a complete geographic path-width solution. `gamma` is the geocentric
axis distance in Earth radii.

## Known limits and interpretation

1. **Explicit elements only.** Phase 4 imports/evaluates supplied coefficients;
   it does not synthesize Besselian elements from DE440s/DE441. This keeps the
   backend genuinely independent for comparisons.
2. **Element provenance matters.** Record the source, ephemeris, adopted ΔT,
   lunar-radius convention, and valid time interval. The same event can have
   different coefficients from different ephemerides and conventions.
3. **Local maximum is a Besselian proxy.** It minimizes the penumbral
   fundamental-plane residual. It is not yet a full apparent-disc maximum based
   on topocentric angular radii and exact obscuration.
4. **No limb correction.** C1–C4 are spherical Besselian-cone contacts. The
   Phase 5 limb-profile framework will add a separate, auditable correction.
5. **No path boundaries or width solution yet.** Phase 4 reports sampled central
   axis locations and the fundamental-plane umbral radius, not northern/southern
   penumbral boundaries or a fully projected path width.
6. **No uncertainty model.** Numerical root residuals describe solver behaviour;
   they are not an estimate of physical eclipse-prediction uncertainty.
7. **Validity is enforced.** Evaluation outside the published interval raises
   `ValueError` unless `check_validity=False` is explicitly requested for a
   diagnostic use. Do not extrapolate a short polynomial silently.

## Included independent reference case

`data/validation/besselian_1999_aug11_nasa.json` contains the NASA/GSFC
polynomial coefficients for the total solar eclipse of 11 August 1999, with
`t0 = 11:00 TDT` and ΔT = 63.7 seconds. The unit tests verify the geocentric
closest-approach time and the central-line location against the NASA page, as
well as local totality duration at a coordinate rounded to the published
greatest-eclipse region. This validates the implemented polynomial and
fundamental-plane reductions against that case only; it does not certify all
eclipses or replace the later Phase 6 validation suite.

## Sources

- NASA/GSFC, [Besselian Elements of Solar Eclipses](https://eclipse.gsfc.nasa.gov/SEcat5/beselm.html).
- NASA/GSFC, [Besselian elements for 11 August 1999](https://eclipse.gsfc.nasa.gov/SEsearch/SEdata.php?Ecl=19990811).
- Stellarium, [`SolarEclipseComputer.cpp`](https://github.com/Stellarium/stellarium/blob/master/src/core/SolarEclipseComputer.cpp), implementation reference for the oblate-Earth fundamental-plane intersection.
- HM Nautical Almanac Office, *Explanatory Supplement to the Astronomical Ephemeris and the American Ephemeris and Nautical Almanac*, 3rd ed. (2013).
