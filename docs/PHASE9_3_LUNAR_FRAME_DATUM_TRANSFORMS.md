# Phase 9.3 — Explicit lunar frame and vertical-datum transformations

## Purpose

Phase 9.1 added bounded tiled reads and Phase 9.2 added additional raster
formats. Those readers retain the frame and vertical-datum metadata of their
source products; they do not transform it. Phase 9.3 introduces an explicit,
provenance-carrying point transform so an application can convert coordinates
only when it has identified the source and target frames and spherical reference
radii.

## Published fixed DE440 / DE421 relation

Park et al. (2021), *The JPL Planetary and Lunar Ephemerides DE440 and DE441*,
Equation (19), gives the rotation from the DE440 principal-axes frame to the
DE421 mean-Earth/mean-rotation frame:

\[
\mathbf r_{\mathrm{ME,DE421}} =
R_x(-0.2785'') R_y(-78.6944'') R_z(-67.8526'')
\mathbf r_{\mathrm{PA,DE440}}.
\]

The implementation uses the passive right-handed matrices printed in the same
paper (Equations (9)--(11)), column-vector semantics, and the published
`Rx @ Ry @ Rz` order. The public names are `MOON_PA_DE440` and
`MOON_ME_DE421`; the ME/MER system is also described in cartographic standards
as mean-Earth/mean-rotation or mean-Earth/polar-axis. The inverse is the exact
transpose of the orthonormal rotation matrix.

The transform is a fixed alignment between these two named frames. It is not a
substitute for the time-dependent orientation of the Moon relative to inertial
space. NAIF documents high-accuracy lunar orientation through binary PCK files
and associated lunar frame kernels; applications needing instantaneous lunar
attitude must use appropriate kernels and coverage rather than treating this
constant alignment as a time-varying orientation model.

## Public API

### Frame rotation

```python
from eclipsekit import de440_pa_to_de421_me_transform

pa_to_me = de440_pa_to_de421_me_transform()
xyz_me_m = pa_to_me.transform_cartesian((x_pa_m, y_pa_m, z_pa_m))
lat_me, lon_me = pa_to_me.transform_latlon(latitude_pa_deg, longitude_pa_deg)
me_to_pa = pa_to_me.inverse()
```

`transform_cartesian()` accepts one XYZ triple or an array with final dimension
3. `transform_latlon()` uses geocentric spherical latitude and east-positive
longitude in degrees; output longitude is normalized to `[-180, 180)`.

### Spherical vertical-datum conversion

For a height measured above a sphere with radius \(R_s\), its centre-of-Moon
radius is \(r = R_s + h_s\). A target sphere with radius \(R_t\) therefore has

\[
h_t = h_s + R_s - R_t.
\]

This is implemented by `LunarReferenceSphereTransform`. It is valid only when
both vertical references are explicitly modelled as spheres centred on the
same lunar centre. It does not convert a geoid, triaxial ellipsoid, local datum,
normal height, or an unspecified vertical reference.

### Combined point conversion

```python
from eclipsekit import (
    LunarCoordinateTransform,
    LunarReferenceSphereTransform,
    de421_me_to_de440_pa_transform,
)

point_transform = LunarCoordinateTransform(
    frame_transform=de421_me_to_de440_pa_transform(),
    vertical_transform=LunarReferenceSphereTransform(
        source_reference_radius_m=1_737_400.0,
        target_reference_radius_m=1_737_400.0,
        source_vertical_datum="DE421 ME sphere, radius 1737400 m",
        target_vertical_datum="DE440 PA sphere, radius 1737400 m",
    ),
)
point_pa = point_transform.transform_point(14.25, -72.5, -1200.0)
```

The combined transform converts geocentric spherical points. NumPy arrays are
broadcast together, so regular point clouds can be processed in one call.
Metadata is retained in `to_dict()` and can be stored with a downstream product.

## Reproducible reference audit

The command

```powershell
eclipsekit-audit-lunar-frames --tolerance-m 0.01 --output-dir "reports\phase9_3"
```

reconstructs all five paired XYZ coordinate sets printed in Table 1 of
Park et al. (2021): Apollo 11, Apollo 14, Apollo 15, Lunokhod 2 and Lunokhod 1.
It writes `lunar-frame-transform-audit.json` and
`lunar-frame-transform-audit.md`. This is a reproducibility/implementation
consistency check against the same published fitted transformation and its
paired points, not independent evidence of absolute lunar control accuracy.

## Explicit limitations

- This API transforms points and metadata only; it does not warp, resample,
  rewrite, or mosaic any PDS3/PDS4/GeoTIFF/JP2 raster.
- It does not infer a frame transform from a frame-name string or from an
  ephemeris kernel name. The chosen transform must be supplied explicitly.
- The built-in DE440 PA / DE421 ME transform is a fixed frame alignment, not a
  time-dependent lunar-attitude model and not an implementation of SPICE PCK/FK.
- The spherical vertical conversion assumes a common lunar centre and two
  explicitly declared spherical radii. Geoid and ellipsoid conversions remain
  separate geodetic work.
- The audit's tolerance is for reproducing published table coordinates from
  rounded angles/coordinates; it must not be interpreted as DEM accuracy.

## Scientific references

1. Park, R. S., Folkner, W. M., Williams, J. G., & Boggs, D. H. (2021), *The JPL
   Planetary and Lunar Ephemerides DE440 and DE441*, The Astronomical Journal,
   161:105, especially Section 2.4, Equations (9)--(11), (19), and Table 1.
   <https://doi.org/10.3847/1538-3881/abd414>
2. NAIF, *High Accuracy Orientation and Body-fixed Frames for the Moon and
   Earth* (Lunar PCK/FK Summary), January 2020. Explains the need to load lunar
   binary PCK and associated frame kernel to use high-accuracy ME/PA frames.
   <https://naif.jpl.nasa.gov/pub/naif/self_training/individual_docs/A6_lunar-earth_pck-fk.pdf>
3. JPL Horizons System Manual, *Lunar Mean-Earth Frame of DE421*. Describes the
   fixed offset from DE440 PA to the standard DE421 mean-Earth frame.
   <https://ssd.jpl.nasa.gov/horizons/manual.html>
4. USGS Planetary Spatial Data Infrastructure, *Lunar Data Interoperability
   Standards*. Describes the 1,737.4 km reference sphere and the DE421 ME frame
   used by many lunar cartographic products.
   <https://psdi.astrogeology.usgs.gov/moon/standards/data_standards/>
