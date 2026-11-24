# Security policy

## Supported versions

Security fixes are developed against the current supported EclipseKit source
release. Pre-1.0 releases may change APIs and should not be treated as a
security-maintained production line.

## Reporting a vulnerability

Please do not publish exploitable details in a public issue. Use the private
security-reporting facility of the repository host when available. Include the
EclipseKit version, Python version, operating system, a minimal reproduction,
and the impact you observed. Do not attach private DEMs, ephemeris kernels,
credentials, or other sensitive local data unless the maintainer explicitly
requests a safe sample.

EclipseKit loads third-party entry-point extensions only when explicitly
requested, but extension factories execute ordinary Python code in the host
process. Install and load extensions only from sources you trust.

## Dependency checks

The `security` optional dependency group installs `pip-audit`. The Phase 15
release procedure records the result of a dependency vulnerability scan.
