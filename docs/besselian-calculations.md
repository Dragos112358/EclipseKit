---
description: Use EclipseKit's independent Besselian backend to calculate local circumstances, greatest eclipse and central-line points from published Besselian elements.
---

# Besselian eclipse calculations in Python

EclipseKit includes an independent solar-eclipse backend that evaluates explicitly supplied Besselian elements.

**Important:** this backend consumes published Besselian coefficients. It does not derive Besselian elements automatically from the active JPL kernel. This separation allows the Besselian result to be compared with the direct ephemeris engine without silently mixing the two methods.

## Load published elements

```python
from eclipsekit import (
    BesselianElements,
    BesselianSolver,
    Observer,
    SolverConfig,
)

elements = BesselianElements.from_json("path/to/elements.json")

solver = BesselianSolver(
    solver_config=SolverConfig(root_method="brent")
)

observer = Observer(
    45.075,
    24.30,
    name="Example site",
    country="Romania",
)

local = solver.calculate_local(
    elements,
    observer,
    delta_t_seconds=63.7,
)

print("Classification:", local.eclipse_type)
print("C2:", local.contacts["C2"].jd_tt if "C2" in local.contacts else None)

maximum_jd_tt = solver.find_global_maximum(elements)
print("Greatest-approach epoch, JD(TT):", maximum_jd_tt)
```

The JSON input must follow the documented Besselian element schema and include its epoch, polynomial coefficients, valid interval and provenance.

## Engine integration

The engine also exposes opt-in Besselian methods, including:

- `calculate_local_besselian(elements, observer, ...)`
- `find_global_maximum_besselian(elements, ...)`
- `besselian_global_shadow_path(elements, start, end, ...)`

## Interpretation limits

- The source coefficients and their validity interval matter; do not extrapolate them silently.
- Record the source ephemeris, ΔT convention, reference epoch and adopted radii.
- The Besselian local maximum is a fundamental-plane proxy, not a full apparent-disc maximum.
- The backend does not currently provide a complete geographic path-width solution or lunar-limb correction.
- Solver residuals are not a complete physical uncertainty estimate.

See [Besselian Backend](BESSELIAN_BACKEND.md) and the [runnable NASA 1999 example](https://github.com/Dragos112358/EclipseKit/blob/main/examples/besselian_backend.py).
