# Phase 13 — Performance and Scalability

## Scope

Phase 13 improves repeated and large city-catalogue searches without changing
the established eclipse geometry, ephemeris, contact-solving or default result
semantics. It focuses on a reusable country index and a streaming result API.
It also measures whether threads are useful for the existing NumPy screening
kernel instead of adding concurrency by assumption.

## Country index cache

`CityCatalog` now builds immutable NumPy index arrays grouped by normalized
country at construction. `indices_for_country()` continues returning an
independent mutable copy for compatibility and caller safety. `countries`
returns the cached display-name list. `index_cache_info()` reports country
count, indexed-city count, and country-index payload bytes.

`iter_index_batches(country, batch_size=512)` yields read-only slices of the
cached arrays. This avoids allocating a second full-sized integer index array
when a caller processes a large catalogue in bounded batches. The slices are
views and must not be modified.

## Streaming city search

`EclipseEngine.iter_search_cities()` evaluates the same coarse/refinement
NumPy screening algorithm as the previous list API, but emits each hit as soon
as its batch has been screened. Its order is the original catalogue order
within batches; it is not globally sorted by magnitude. This allows consumers
to persist or process hits incrementally and avoids retaining a complete list
of result objects.

`EclipseEngine.search_cities()` remains the compatibility API. It collects
`iter_search_cities()` results, sorts them by descending magnitude, and returns
a list exactly as before. Existing defaults remain unchanged, including
`batch_size=512`, `coarse_steps=49`, and the refinement count. `include_contacts`
still invokes the exact local solver sequentially for each candidate.

The batch size controls the largest city-by-coarse-time intermediate arrays.
Smaller batches reduce peak temporary memory; larger batches may reduce loop
overhead. The best setting depends on the size of the supplied catalogue and
available memory.

## Parallelism decision

The Phase 13 benchmark includes an explicitly synthetic, deterministic
comparison of serial batch evaluation against a four-thread `ThreadPoolExecutor`
for the NumPy-only screening kernel. In the development environment (CPython
3.13.5, NumPy 2.3.5, Linux x86_64), a 2,048-city workload measured:

| Workload | Median per call | p95 per call |
|---|---:|---:|
| Serial, 8 batches | 24.96 ms | 26.54 ms |
| Four threads, 8 batches | 47.36 ms | 50.41 ms |

Four threads were about 1.9× slower in this particular workload. This is not
a universal performance result, but it is sufficient reason not to ship a
thread-count option or make parallel execution the default. The city search
still performs the expensive ephemeris node preparation once and then applies
bounded vectorized batches. Future parallel work should be reconsidered only
after an end-to-end benchmark on the target OS and real catalogue demonstrates
a repeatable improvement without excessive memory growth.

## Benchmark suite

`eclipsekit-benchmark` retains the original scalar numerical workloads and
adds:

- full country-index scan of 2,048 entries;
- precomputed country-index lookup;
- streaming index-batch iteration;
- serial city-screening batches;
- four-thread city-screening batches (diagnostic only).

A representative development-container measurement recorded 0.0256 ms median
for the old-style country scan and 0.0010 ms for the cached lookup (about 25×
faster for this exact 2,048-entry case). Timings are environment-dependent and
do not imply a universal speedup. The country-index cache is built once when
the catalogue is constructed; the cached arrays consume memory proportional to
the number of catalogue entries.

Run a short benchmark on the target machine:

```powershell
eclipsekit-benchmark --warmups 1 --repeats 5 --iterations 5 `
  --track-memory --output-dir reports/phase13 --stem scalability
```

Use `--profile-output reports/phase13/scalability.pstats` when profiling is
needed. Baseline comparisons are meaningful only when Python implementation,
Python version, OS and machine identity match.

## Verification and limits

Tests compare streamed and list results, verify that streaming yields from the
first completed batch, exercise country-index cache immutability and batched
read-only views, and check input validation. The full numerical regression
suite remains part of Phase 13 verification.

The synthetic benchmark has no Skyfield ephemeris access. It measures the
array-screening stage only; it does not establish end-to-end eclipse-search
speed, local-contact latency, or scientific accuracy. No new third-party
dependencies, numerical defaults, ephemeris settings or contact algorithms
were introduced.
