# Lunar-eclipse reference comparison (2022–2025)

**Comparison recorded:** 2026-11-25  
**Local run:** `examples/lunar_eclipse.py --start 2022-01-01 --end 2026-01-01`  
**Reference family:** EclipseWise, Herald/Sinnott shadow rule, shadow enlargement 1.000.

This is an independent numerical cross-check of the local output supplied for
EclipseKit. It is not a formal scientific certification. The EclipseWise pages
identify JPL DE430 and event-specific ΔT values, whereas the example CLI
selects `de440s` by default and uses the configured Skyfield time-scale data.
Small residual differences are therefore expected.

## Event detection and classification

All eight lunar eclipses expected in the 2022–2025 interval were found, with
matching classifications:

| Date (UTC) | EclipseKit | Reference |
|---|---|---|
| 2022-05-16 | Total | Total |
| 2022-11-08 | Total | Total |
| 2023-05-05 | Penumbral | Penumbral |
| 2023-10-28 | Partial | Partial |
| 2024-03-25 | Penumbral | Penumbral |
| 2024-09-18 | Partial | Partial |
| 2025-03-14 | Total | Total |
| 2025-09-07 | Total | Total |

## Contact-time agreement

The following values are the maximum absolute difference among the contacts
published for each eclipse. Values are calculated from the supplied EclipseKit
`contacts_ut1` and `maximum_ut1` fields against the UT1 values on the cited
EclipseWise pages.

| Date | Maximum absolute time difference |
|---|---:|
| 2022-05-16 | 2.86 s |
| 2022-11-08 | 3.18 s |
| 2023-05-05 | 7.26 s |
| 2023-10-28 | 4.32 s |
| 2024-03-25 | 4.30 s |
| 2024-09-18 | 5.22 s |
| 2025-03-14 | 4.32 s |
| 2025-09-07 | 4.56 s |

The largest observed difference is approximately **7.3 seconds** (greatest
eclipse on 2023-05-05). This is a strong match for a DE440s/Skyfield run against
DE430-based published tables, and does not justify retuning the shadow model.

## Magnitude agreement

Across all eight cases, both penumbral and umbral magnitudes differ from the
published values by less than **0.00065**. In particular, the shallow partial
eclipse of 2024-09-18 is classified correctly and its umbral magnitude is close
to the reference; the penumbral-only events correctly have no U1/U2/U3/U4
contacts.

## Field semantics

The serialized EclipseKit `gamma` is a nonnegative axis-distance magnitude in
equatorial Earth radii. Some EclipseWise pages show a signed `Gamma`; its sign
is a convention describing which side of the shadow axis the Moon passes.
Therefore compare `abs(Gamma)` to the current EclipseKit `gamma`, not the sign.

## Known issue fixed separately

A date-only value passed to the general time conversion intentionally resolves
to 12:00, but this was inappropriate for the boundaries of an interval search.
Consequently, a date-only interval beginning 2025-03-14 at noon filtered out the
2025-03-14 maximum at 06:58 UT1. Lunar interval searches now interpret date-only
start and end values at civil midnight and use the half-open interval
`[start, end)`. Thus `--start 2025-03-14 --end 2025-03-15` includes the whole of
14 March. The general `EclipseEngine.time("YYYY-MM-DD")` behavior remains
unchanged for single-event calculations.

## Reference pages

- [2022-05-16 total lunar eclipse](https://www.eclipsewise.com/lunar/LEprime/2001-2100/LE2022May16Tprime.html)
- [2022-11-08 total lunar eclipse](https://www.eclipsewise.com/lunar/LEprime/2001-2100/LE2022Nov08Tprime.html)
- [2023-05-05 penumbral lunar eclipse](https://www.eclipsewise.com/lunar/LEprime/2001-2100/LE2023May05Nprime.html)
- [2023-10-28 partial lunar eclipse](https://www.eclipsewise.com/lunar/LEprime/2001-2100/LE2023Oct28Pprime.html)
- [2024-03-25 penumbral lunar eclipse](https://www.eclipsewise.com/lunar/LEprime/2001-2100/LE2024Mar25Nprime.html)
- [2024-09-18 partial lunar eclipse](https://www.eclipsewise.com/lunar/LEprime/2001-2100/LE2024Sep18Pprime.html)
- [2025-03-14 total lunar eclipse](https://www.eclipsewise.com/lunar/LEprime/2001-2100/LE2025Mar14Tprime.html)
- [2025-09-07 total lunar eclipse](https://www.eclipsewise.com/lunar/LEprime/2001-2100/LE2025Sep07Tprime.html)
