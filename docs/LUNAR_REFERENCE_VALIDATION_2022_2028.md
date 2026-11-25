# Lunar eclipse validation matrix (2022–2028)

**Reference matrix frozen:** 2026-11-25  
**Primary reference:** EclipseWise, Fred Espenak  
**Primary prediction convention:** Herald/Sinnott, shadow enlargement 1.000, JPL DE430  
**Independent classification check:** NASA GSFC Five Millennium Catalog (classification only)

## Purpose

This matrix expands the initial eight-event spot check into 16 events spanning
all three lunar-eclipse types. It includes deep and shallow events, a grazing
penumbral event, and both total and partial umbral eclipses. Each record stores
the UT1 greatest-eclipse instant, all expected contacts (including explicit
`null` contacts), both eclipse magnitudes, signed catalog Gamma, the NASA
catalog type code, and the original EclipseWise event page.

The data are fixed snapshots so validation is reproducible and does not need
network access during test execution. The source page remains the authority for
revisions; update the snapshot only after checking the page and recording the
new retrieval date.

## How to run

From the repository root, with the project environment active and the JPL
DE440s kernel available through Skyfield:

```powershell
python scripts/validate_lunar_references.py --kernel de440s
```

To save a machine-readable report:

```powershell
python scripts/validate_lunar_references.py --kernel de440s --json-output reports/lunar-reference-2022-2028.json
```

The default search interval is `[2022-01-01, 2029-01-01)`. To use a local BSP
kernel, pass its path to `--kernel`.

For controlled reproducibility runs, the validator also accepts
`--boundary-samples`, `--contact-step-seconds`,
`--solver-tolerance-seconds`, and `--delta-t-seconds`. The JSON report records
these settings and includes signed per-contact and per-magnitude residuals.
For the 2027-07-18 EclipseWise reference, the source page specifies DE430 and
Delta-T = 72.7 s; use both when checking that grazing event against the source.

## Acceptance thresholds

The defaults are deliberately broader than the residuals in the first
2022–2025 comparison. They are **screening thresholds**, not a formal
uncertainty budget or a scientific certification:

| Quantity | Default maximum difference |
|---|---:|
| Greatest eclipse and each published contact (UT1) | 30 seconds |
| Penumbral and umbral magnitude | 0.01 |
| Absolute Gamma / axis distance | 0.005 Earth radii |

The contacts are compared only when they exist in the reference. Missing
contacts are tested explicitly: a penumbral eclipse must not gain U1/U2/U3/U4,
and a partial eclipse must not gain U2/U3. The reported Gamma is unsigned in
EclipseKit; the comparison therefore uses `abs(Gamma)` from EclipseWise. This is
consistent with the current public field definition and does not change the API.

## Primary and independent sources

EclipseWise's individual event pages provide contact times in UT1, magnitudes,
Gamma, the JPL DE430 ephemeris, the Herald/Sinnott shadow rule, and a shadow
 enlargement of 1.000. The site explicitly permits reproduction of eclipse
data when accompanied by a link and acknowledgment. The dataset includes the
original URL for every event and credits: **Eclipse Predictions by Fred
Espenak, www.EclipseWise.com**.

NASA GSFC's Five Millennium Catalog supplies an independent check on the event
date and broad type (N/P/T). NASA's catalog uses Danjon's shadow enlargement
method and a different ephemeris/time treatment. Consequently, NASA values are
not used as numerical contact or magnitude targets in this matrix.

### Edge case: 2027 July 18

This is an extremely shallow penumbral grazing event. EclipseWise's
Herald/Sinnott page reports penumbral magnitude 0.00320 and a penumbral contact
interval of about 17 minutes. NASA's catalog independently classifies it as
penumbral (catalog code `Ne`; `N` is the eclipse type and `e` is the Saros-series
ending qualifier) but reports a different penumbral magnitude under its own
shadow convention. This case is included to probe event detection and contact
existence near the penumbral threshold. It should not be used to tune a model
against NASA's Danjon magnitude.

## Event matrix

| Date (UTC) | Type | Stress characteristic |
|---|---|---|
| 2022-05-16 | Total | Deep central total eclipse |
| 2022-11-08 | Total | Total eclipse |
| 2023-05-05 | Penumbral | Deep penumbral eclipse |
| 2023-10-28 | Partial | Shallow partial eclipse |
| 2024-03-25 | Penumbral | Deep penumbral eclipse |
| 2024-09-18 | Partial | Very shallow partial eclipse |
| 2025-03-14 | Total | Previously compared total eclipse |
| 2025-09-07 | Total | Previously compared total eclipse |
| 2026-03-03 | Total | Future total validation case |
| 2026-08-28 | Partial | Deep partial eclipse |
| 2027-02-20 | Penumbral | Deep penumbral eclipse |
| 2027-07-18 | Penumbral | Extremely shallow grazing event |
| 2027-08-17 | Penumbral | Moderate penumbral eclipse |
| 2028-01-12 | Partial | Very shallow partial eclipse |
| 2028-07-06 | Partial | Moderate partial eclipse |
| 2028-12-31 | Total | Total eclipse |

## Interpretation

A passing result means that this installed ephemeris/time-scale configuration
agrees with the frozen EclipseWise/Herald-Sinnott reference within the stated
screening limits. It does not mean the ephemeris, Delta-T model, Earth
orientation, lunar figure, or atmospheric shadow prescription is exact. A
failure should be classified before changing code:

1. event missing or duplicated — search/discovery logic;
2. wrong type or contact presence — classification/geometry;
3. contact-time residual — ephemeris, Earth orientation, time scale, or root
   solver;
4. magnitude/Gamma residual — shadow geometry or lunar/Solar apparent sizes.

Do not retune the shadow model to compensate for a time-scale discrepancy.
