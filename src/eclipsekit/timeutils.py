"""Time-scale utilities. Internal event calculations use Skyfield TT Julian dates."""

from __future__ import annotations

from datetime import date, datetime, timezone
import math
from typing import Any


def delta_t_seconds(year: float, month: int = 6) -> float:
    """Estimate ΔT = TT − UT using the Espenak–Meeus piecewise polynomials.

    The result is an estimate, not a replacement for observed UT1−UTC data.
    For modern epochs the polynomial is suitable for approximate conversions;
    for distant epochs the uncertainty can dominate eclipse-time accuracy.
    The polynomial branches are defined by NASA GSFC's Five Millennium Canon.
    """
    y = float(year) + (int(month) - 0.5) / 12.0

    if y < -500:
        u = (y - 1820.0) / 100.0
        return -20.0 + 32.0 * u**2

    if y < 500:
        u = y / 100.0
        return (
            10583.6 - 1014.41*u + 33.78311*u**2 - 5.952053*u**3
            - 0.1798452*u**4 + 0.022174192*u**5 + 0.0090316521*u**6
        )

    if y < 1600:
        u = (y - 1000.0) / 100.0
        return (
            1574.2 - 556.01*u + 71.23472*u**2 + 0.319781*u**3
            - 0.8503463*u**4 - 0.005050998*u**5 + 0.0083572073*u**6
        )

    if y < 1700:
        t = y - 1600.0
        return 120.0 - 0.9808*t - 0.01532*t**2 + t**3/7129.0

    if y < 1800:
        t = y - 1700.0
        return 8.83 + 0.1603*t - 0.0059285*t**2 + 0.00013336*t**3 - t**4/1174000.0

    if y < 1860:
        t = y - 1800.0
        return (
            13.72 - 0.332447*t + 0.0068612*t**2 + 0.0041116*t**3
            - 0.00037436*t**4 + 0.0000121272*t**5
            - 0.0000001699*t**6 + 0.000000000875*t**7
        )

    if y < 1900:
        t = y - 1860.0
        return (
            7.62 + 0.5737*t - 0.251754*t**2 + 0.01680668*t**3
            - 0.0004473624*t**4 + t**5/233174.0
        )

    if y < 1920:
        t = y - 1900.0
        return -2.79 + 1.494119*t - 0.0598939*t**2 + 0.0061966*t**3 - 0.000197*t**4

    if y < 1941:
        t = y - 1920.0
        return 21.20 + 0.84493*t - 0.076100*t**2 + 0.0020936*t**3

    if y < 1961:
        t = y - 1950.0
        return 29.07 + 0.407*t - t**2/233.0 + t**3/2547.0

    if y < 1986:
        t = y - 1975.0
        return 45.45 + 1.067*t - t**2/260.0 - t**3/718.0

    if y < 2005:
        t = y - 2000.0
        return (
            63.86 + 0.3345*t - 0.060374*t**2 + 0.0017275*t**3
            + 0.000651814*t**4 + 0.00002373599*t**5
        )

    if y < 2050:
        t = y - 2000.0
        return 62.92 + 0.32217*t + 0.005589*t**2

    if y < 2150:
        u = (y - 1820.0) / 100.0
        return -20.0 + 32.0*u**2 - 0.5628*(2150.0 - y)

    u = (y - 1820.0) / 100.0
    return -20.0 + 32.0*u**2


def julian_day_from_calendar(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0,
    second: float = 0.0, *, gregorian: bool | None = None,
) -> float:
    """Convert a civil date to JD(UT-like input), including astronomical year numbering.

    If ``gregorian`` is omitted, the Gregorian calendar is used from 1582-10-15;
    earlier dates use the Julian calendar, matching the historical convention.
    """
    if not 1 <= month <= 12:
        raise ValueError("month must be in 1..12")
    if hour not in range(24) or minute not in range(60) or not 0 <= second < 61:
        raise ValueError("invalid time of day")
    if gregorian is None:
        gregorian = (year, month, day) >= (1582, 10, 15)
    y, m = int(year), int(month)
    if m <= 2:
        y -= 1
        m += 12
    if gregorian:
        a = math.floor(y / 100)
        b = 2 - a + math.floor(a / 4)
    else:
        b = 0
    jd0 = (
        math.floor(365.25 * (y + 4716))
        + math.floor(30.6001 * (m + 1))
        + day + b - 1524.5
    )
    return jd0 + (hour + minute / 60.0 + second / 3600.0) / 24.0


def calendar_from_julian_day(jd: float) -> tuple[int, int, int, int, int, float]:
    """Inverse of the mixed Julian/Gregorian conversion, returning UTC-like fields."""
    jd_shift = jd + 0.5
    z = math.floor(jd_shift)
    f = jd_shift - z
    if z < 2299161:
        a = z
    else:
        alpha = math.floor((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - math.floor(alpha / 4)
    b = a + 1524
    c = math.floor((b - 122.1) / 365.25)
    d = math.floor(365.25 * c)
    e = math.floor((b - d) / 30.6001)
    day_float = b - d - math.floor(30.6001 * e) + f
    day = math.floor(day_float)
    frac = day_float - day
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    total_seconds = frac * 86400.0
    hour = int(total_seconds // 3600)
    minute = int((total_seconds % 3600) // 60)
    second = total_seconds - hour * 3600 - minute * 60
    return int(year), int(month), int(day), hour, minute, second


def time_from_calendar(ts: Any, year: int, month: int, day: int,
                       hour: int = 0, minute: int = 0, second: float = 0.0) -> Any:
    """Create a Skyfield Time; use Skyfield/IERS for 1900–2100 and the legacy Delta-T model outside."""
    if 1900 <= year <= 2100:
        return ts.utc(year, month, day, hour, minute, second)
    jd_ut = julian_day_from_calendar(year, month, day, hour, minute, second)
    jd_tt = jd_ut + delta_t_seconds(year, month) / 86400.0
    return ts.tt_jd(jd_tt)


def coerce_time(ts: Any, value: Any) -> Any:
    """Accept a Skyfield Time, JD(TT) float, datetime, date, or ISO date/time string.

    A date-only string is interpreted as 12:00 UTC so a +/-12-hour search covers
    that civil date. A naive datetime is interpreted as UTC.
    """
    if hasattr(value, "tt") and hasattr(value, "utc"):
        return value
    if isinstance(value, (int, float)):
        return ts.tt_jd(float(value))
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return ts.from_datetime(dt.astimezone(timezone.utc))
    if isinstance(value, date):
        return time_from_calendar(ts, value.year, value.month, value.day, 12)
    if isinstance(value, str):
        s = value.strip()
        try:
            if len(s) == 10:
                y, m, d = map(int, s.split("-"))
                return time_from_calendar(ts, y, m, d, 12)
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return ts.from_datetime(dt.astimezone(timezone.utc))
        except ValueError as exc:
            raise ValueError(f"Unsupported date/time {value!r}; use YYYY-MM-DD or ISO-8601") from exc
    raise TypeError("time must be a Skyfield Time, JD(TT), date, datetime, or ISO-8601 string")


def time_to_utc_iso(t: Any) -> str:
    """Format a Skyfield Time as UTC ISO-8601, preserving the custom Delta-T convention for ancient epochs."""
    try:
        utc = t.utc
        year = int(utc[0])
        month = int(utc[1])
    except Exception:
        year, month, *_ = calendar_from_julian_day(float(t.tt))
    if 1900 <= year <= 2100:
        try:
            value = t.utc_iso(delimiter="T", places=3)
            return value if value.endswith("Z") else value + "Z"
        except Exception:
            pass
    dt = delta_t_seconds(year, month)
    y, m, d, hh, mm, ss = calendar_from_julian_day(float(t.tt) - dt / 86400.0)
    sign_year = f"-{abs(y):04d}" if y < 0 else f"{y:04d}"
    whole = int(ss)
    ms = int(round((ss - whole) * 1000))
    if ms == 1000:
        whole += 1
        ms = 0
    return f"{sign_year}-{m:02d}-{d:02d}T{hh:02d}:{mm:02d}:{whole:02d}.{ms:03d}Z"
