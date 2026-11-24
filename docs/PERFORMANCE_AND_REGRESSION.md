# Phase 7.7 — Performance and scientific regression

Phase 7.7 adds measurement and repeatable acceptance checks without silently
changing established astronomical algorithms or their numerical defaults.

## Performance measurement

`eclipsekit-benchmark` exercises five small deterministic hot paths:

1. WGS84 inverse geodesic across the antimeridian.
2. Scalar Brent root solving.
3. Solar/lunar apparent-disc overlap fraction.
4. Finite-difference Jacobian evaluation.
5. 2×2 covariance propagation.

Each workload is warmed up, then run in batches. The JSON/Markdown report records
per-call samples, median, mean, sample standard deviation, minimum, maximum,
nearest-rank p95, calls/second, Python/NumPy/OS/machine identity, and optional
`tracemalloc` peak bytes. Memory tracking changes allocation overhead, so do not
compare tracked and untracked timing results as if they were equivalent.

The optional `.pstats` output profiles the micro-benchmark workloads separately
from the timing run. For a full public-API scenario, use `cProfile` on
`examples/full_api_check.py` with the same local DE440s/model assets, then inspect
cumulative time with `pstats`.

A saved JSON run can be used as a local baseline. The comparison tool requires
matching Python implementation/version, OS and machine architecture; otherwise
it returns `INCOMPARABLE`, not `REGRESSION`. A configurable slowdown ratio is a
screening signal only. Repeat suspicious measurements under low system load
before acting. No universal millisecond thresholds are encoded in CI.

## Scientific regression checks

`eclipsekit-regression` runs these deterministic checks:

- WGS84 equatorial one-degree geodesic anchor.
- Short antimeridian geodesic anchor.
- WGS84 geodetic/ECEF forward-inverse round-trip.
- High-latitude near-antipodal fallback finiteness.
- Brent root against a closed-form cubic.
- Tangential-root detection without a sign change.
- Root solving at Julian-day magnitude.
- Correlated linear covariance propagation against a closed-form matrix result.
- Seeded Monte Carlo repeatability.
- Published NASA 1999 Besselian-elements reference (maximum epoch, central-line
  position, eclipse type, central duration, and C1–C4 convergence/order).

When `--dem-image` and `--dem-label` are both supplied, the same report includes
the Phase 7.6 PDS3 metadata/storage and deterministic interpolation-sample
validator. This remains a structural/sample check, not an independent vertical
accuracy assessment.

The default report labels the real DEM check `NOT_RUN` unless a product is
provided. It also labels live DE440s global-path and shadow-corridor checks
`NOT_RUN`, because those require the user's explicit BSP kernel and
Earth-orientation policy. Use the existing `eclipsekit-validate` command for
those live path/local-circumstance references. A `PARTIAL` Phase 7.7 report means
all checks actually executed passed, while explicitly named layers were not run;
it must not be described as a complete live validation.

## Compatibility and acceptance policy

- Existing public astronomical functions and default model parameters are not
  changed by this phase.
- Benchmarks are descriptive; no performance guarantee is inferred without a
  comparable machine-specific baseline.
- Scientific PASS results always state the particular reference case and
  tolerance. A single regression event is not proof of universal accuracy.
- Any future optimisation must preserve the published regression results and
  existing default behavior, with the baseline/benchmark used to demonstrate
  that the change addresses a measured bottleneck.


## Phase 13 — scalable catalogue searches

The benchmark suite extends the original five scalar numerical workloads with
five deterministic workloads: full country-index scan, cached country index,
batched iteration over cached indexes, and serial versus four-thread execution
of the vectorised city-screening kernel. The city-search arrays are
synthetic and intentionally kernel-free; these comparisons measure the NumPy
batch stage, not a full DE440s search or the local-contact solver.

The current development-container run (CPython 3.13.5, NumPy 2.3.5, Linux
x86_64) measured a 2,048-row country scan at 0.0256 ms median and cached lookup
at 0.0010 ms median. The 2,048-city synthetic batch stage measured 25.0 ms
serial versus 47.4 ms with four worker threads. The thread result is not a
universal claim: it is evidence that thread scheduling and memory-bandwidth
contention can overwhelm NumPy's released-GIL work for this workload. EclipseKit
therefore exposes no thread-count switch for city searches in Phase 13.

For large catalogues, `CityCatalog.iter_index_batches()` yields read-only
slices over its precomputed indexes. `EclipseEngine.iter_search_cities()` uses
those slices and yields local hits incrementally, so a caller can write or
consume them without holding the complete result list. Its output follows
catalogue order, while the original `search_cities()` still collects and sorts
hits by descending magnitude. Lower `batch_size` reduces the temporary
city-by-time working set; larger batches can improve throughput but increase
peak memory. Exact optional local contacts are still solved sequentially.

Recommended target-platform measurement:

```powershell
eclipsekit-benchmark --warmups 1 --repeats 5 --iterations 5 `
   --track-memory --output-dir reports/phase13 --stem scalability
```

Compare a baseline only when the benchmark tool reports compatible runtime
identity. Do not treat a benchmark as a scientific-accuracy check or a general
performance guarantee. No numerical constants or astronomy defaults were
modified in this phase.
