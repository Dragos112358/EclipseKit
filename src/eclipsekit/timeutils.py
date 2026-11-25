"""Time-scale utilities. Internal event calculations use Skyfield TT Julian dates."""

from __future__ import annotations

from datetime import date, datetime, timezone
import math
import re
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


def _calendar_gregorian_flag(
    year: int, month: int, day: int, calendar: str = "historical"
) -> bool:
    """Resolve a calendar name to the Gregorian/Julian arithmetic convention.

    ``historical`` follows the civil reform: Julian through 1582-10-04, then
    Gregorian from 1582-10-15. The ten skipped civil dates are rejected.
    ``julian`` and ``gregorian`` select proleptic calendars for every year.
    """
    name = str(calendar).casefold()
    if name == "gregorian":
        return True
    if name == "julian":
        return False
    if name != "historical":
        raise ValueError("calendar must be 'historical', 'julian', or 'gregorian'")
    civil = (int(year), int(month), int(day))
    if (1582, 10, 5) <= civil <= (1582, 10, 14):
        raise ValueError(
            "1582-10-05 through 1582-10-14 do not exist in the historical "
            "Julian-to-Gregorian calendar transition; choose calendar='julian' "
            "or calendar='gregorian' for a proleptic date"
        )
    return civil >= (1582, 10, 15)


def _calendar_iso_fields(value: str) -> tuple[int, int, int, int, int, float] | None:
    """Parse a calendar date/time without Python datetime's Gregorian assumption."""
    match = re.fullmatch(
        r"([+-]?\d{1,6})-(\d{2})-(\d{2})"
        r"(?:[Tt ](\d{2}):(\d{2})(?::(\d{2}(?:\.\d*)?))?)?",
        value.strip(),
    )
    if match is None:
        return None
    year, month, day = (int(match.group(i)) for i in (1, 2, 3))
    hour = int(match.group(4) or 12)
    minute = int(match.group(5) or 0)
    second = float(match.group(6) or 0.0)
    return year, month, day, hour, minute, second


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
        gregorian = _calendar_gregorian_flag(year, month, day, "historical")
    days_in_month = (31, 29 if (year % 4 == 0 and not gregorian) or
                     (gregorian and (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)))
                     else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    if not 1 <= day <= days_in_month[month - 1]:
        raise ValueError(f"day must be valid for {year:04d}-{month:02d}")
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


def calendar_from_julian_day(
    jd: float, *, gregorian: bool | None = None,
) -> tuple[int, int, int, int, int, float]:
    """Convert a Julian Day to calendar fields.

    The default uses the historical Julian/Gregorian cutover. Set
    ``gregorian=True`` or ``False`` for a proleptic calendar.
    """
    jd_shift = jd + 0.5
    z = math.floor(jd_shift)
    f = jd_shift - z
    use_gregorian = (z >= 2299161) if gregorian is None else bool(gregorian)
    if not use_gregorian:
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


def time_from_calendar(
    ts: Any, year: int, month: int, day: int, hour: int = 0,
    minute: int = 0, second: float = 0.0, *, calendar: str = "historical",
) -> Any:
    """Create a Skyfield Time from a civil calendar date.

    ``historical`` uses Julian dates up to 1582-10-04 and Gregorian dates
    from 1582-10-15. ``julian`` and ``gregorian`` request proleptic calendars.
    Modern Gregorian input is passed through Skyfield's UTC conversion; other
    dates are converted through JD and the project's documented Delta-T model.
    A modern Julian date is first converted to its equivalent Gregorian UTC date.
    """
    is_gregorian = _calendar_gregorian_flag(year, month, day, calendar)
    jd_ut = julian_day_from_calendar(
        year, month, day, hour, minute, second, gregorian=is_gregorian
    )
    if is_gregorian and 1900 <= year <= 2100:
        return ts.utc(year, month, day, hour, minute, second)
    if not is_gregorian and 1900 <= year <= 2100:
        gy, gm, gd, gh, gmin, gs = calendar_from_julian_day(
            jd_ut, gregorian=True
        )
        if 1900 <= gy <= 2100:
            return ts.utc(gy, gm, gd, gh, gmin, gs)
    jd_tt = jd_ut + delta_t_seconds(year, month) / 86400.0
    return ts.tt_jd(jd_tt)


def coerce_time(ts: Any, value: Any, *, calendar: str = "historical") -> Any:
    """Accept a Skyfield Time, JD(TT), datetime, date, or ISO date/time string.

    Naive ISO date/time strings and :class:`datetime.date` values are interpreted
    using ``calendar``. Python ``datetime`` objects and ISO strings with ``Z`` or
    a numeric UTC offset represent absolute instants. A date-only value is
    interpreted at 12:00 so a search window can cover the civil date.
    """
    _calendar_gregorian_flag(2000, 1, 1, calendar)
    if hasattr(value, "tt") and hasattr(value, "utc"):
        return value
    if isinstance(value, (int, float)):
        return ts.tt_jd(float(value))
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return ts.from_datetime(dt.astimezone(timezone.utc))
    if isinstance(value, date):
        return time_from_calendar(ts, value.year, value.month, value.day, 12, calendar=calendar)
    if isinstance(value, str):
        s = value.strip()
        fields = _calendar_iso_fields(s)
        # A naive ISO date/time is a civil-calendar value and must respect the
        # selected Julian/Gregorian convention. Strings with an explicit Z or
        # numeric UTC offset represent absolute instants and are parsed below.
        has_timezone = s.endswith(("Z", "z")) or bool(
            re.search(r"[Tt ]\d{2}:\d{2}(?::\d{2}(?:\.\d*)?)?[+-]\d{2}:?\d{2}$", s)
        )
        if fields is not None and not has_timezone:
            return time_from_calendar(ts, *fields, calendar=calendar)
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00").replace("z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return ts.from_datetime(dt.astimezone(timezone.utc))
        except ValueError as exc:
            raise ValueError(
                f"Unsupported date/time {value!r}; use YYYY-MM-DD or ISO-8601"
            ) from exc
    raise TypeError("time must be a Skyfield Time, JD(TT), date, datetime, or ISO-8601 string")


def time_to_utc_iso(t: Any, *, calendar: str = "historical") -> str:
    """Format a Skyfield Time as an ISO timestamp in the requested civil calendar.

    The absolute instant is unchanged. ``historical`` observes the 1582 cutover;
    ``julian`` and ``gregorian`` choose proleptic calendars for display.
    """
    _calendar_gregorian_flag(2000, 1, 1, calendar)
    try:
        utc = t.utc
        year, month = int(utc[0]), int(utc[1])
    except Exception:
        year, month, *_ = calendar_from_julian_day(float(t.tt))

    # Keep Skyfield's EOP-aware UTC formatter for ordinary modern Gregorian dates.
    if calendar in {"historical", "gregorian"} and 1900 <= year <= 2100:
        try:
            value = t.utc_iso(delimiter="T", places=3)
            return value if value.endswith("Z") else value + "Z"
        except Exception:
            pass

    if calendar == "julian" and 1900 <= year <= 2100:
        # Skyfield's scalar UTC tuple is Gregorian. Convert that exact UTC civil
        # instant to JD, then express the same instant in the proleptic Julian
        # calendar; do not approximate UTC by subtracting a polynomial Delta-T.
        try:
            utc = t.utc
            jd_ut = julian_day_from_calendar(
                int(utc[0]), int(utc[1]), int(utc[2]),
                int(utc[3]), int(utc[4]), float(utc[5]), gregorian=True,
            )
        except Exception:
            dt = delta_t_seconds(year, month)
            jd_ut = float(t.tt) - dt / 86400.0
    else:
        dt = delta_t_seconds(year, month)
        jd_ut = float(t.tt) - dt / 86400.0
    # Quantize before calendar decomposition so a binary-float value just below
    # a minute boundary cannot be rendered as an invalid ``:60`` second.
    jd_ut = round(jd_ut * 86_400_000.0) / 86_400_000.0
    gregorian = None if calendar == "historical" else calendar == "gregorian"
    y, m, d, hh, mm, ss = calendar_from_julian_day(jd_ut, gregorian=gregorian)
    sign_year = f"-{abs(y):04d}" if y < 0 else f"{y:04d}"
    milliseconds = int(round((ss - int(ss)) * 1000.0))
    whole_seconds = int(ss)
    if milliseconds >= 1000:
        # Calendar decomposition can return 59.99999 because a JD cannot
        # represent every millisecond exactly. Move just past the boundary and
        # decompose again so we emit 07:00:00.000, never 06:59:60.000.
        y, m, d, hh, mm, ss = calendar_from_julian_day(
            jd_ut + 0.0005 / 86400.0, gregorian=gregorian
        )
        whole_seconds = int(ss)
        milliseconds = int(round((ss - whole_seconds) * 1000.0))
    return (
        f"{sign_year}-{m:02d}-{d:02d}T{hh:02d}:{mm:02d}:"
        f"{whole_seconds:02d}.{milliseconds:03d}Z"
    )


def time_to_ut1_iso(t: Any, *, calendar: str = "historical") -> str:
    """Format a Skyfield Time's UT1 instant in an explicit civil calendar.

    Unlike :func:`time_to_utc_iso`, this labels the Earth's rotation time scale
    itself.  The returned suffix is ``UT1`` (not ``Z``), because UT1 is not UTC.
    Its accuracy is limited by the active Skyfield/IERS or fixed-Delta-T source.
    """
    _calendar_gregorian_flag(2000, 1, 1, calendar)
    jd_ut1 = float(t.ut1)
    gregorian = None if calendar == "historical" else calendar == "gregorian"
    year, month, day, hour, minute, second = calendar_from_julian_day(
        jd_ut1, gregorian=gregorian
    )
    milliseconds = int(round((second - int(second)) * 1000.0))
    whole_seconds = int(second)
    if milliseconds >= 1000:
        year, month, day, hour, minute, second = calendar_from_julian_day(
            jd_ut1 + 0.0005 / 86400.0, gregorian=gregorian
        )
        whole_seconds = int(second)
        milliseconds = int(round((second - whole_seconds) * 1000.0))
    sign_year = f"-{abs(year):04d}" if year < 0 else f"{year:04d}"
    return (
        f"{sign_year}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:"
        f"{whole_seconds:02d}.{milliseconds:03d} UT1"
    )
