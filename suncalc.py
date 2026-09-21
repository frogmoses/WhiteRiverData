# Sunrise and sunset, stdlib only - the NOAA equation, copied verbatim from
# new-croton-fishing/scripts/suncalc.py (2026-09-20) so a catch's clock time can be
# placed against sunset. Good to a minute or two. Latitude and longitude are
# parameters on purpose: every caller (the page, the fishing report, the journal
# builder) passes the White Hole pin from landmarks.py, so nothing here can drift
# from it. Lives at the repo root so all three import the one copy.
import datetime
import math


def julian(d):
    # Julian day number at 00:00 UT on a civil date.
    a = (14 - d.month) // 12
    y = d.year + 4800 - a
    m = d.month + 12 * a - 3
    return (d.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100
            + y // 400 - 32045)


def from_julian(jd, tz):
    # Julian date -> aware datetime in tz.
    unix = (jd - 2440587.5) * 86400.0
    return datetime.datetime.fromtimestamp(unix, datetime.timezone.utc).astimezone(tz)


def sun_times(d, lat, lon, tz):
    # (sunrise, sunset) as aware datetimes in tz, or (None, None) where the sun
    # never rises or sets that day - not at this latitude.
    rad = math.pi / 180
    n = julian(d) - 2451545 + 0.0008
    j_star = n - lon / 360.0
    m = (357.5291 + 0.98560028 * j_star) % 360
    c = (1.9148 * math.sin(m * rad) + 0.02 * math.sin(2 * m * rad)
         + 0.0003 * math.sin(3 * m * rad))
    lam = (m + c + 180 + 102.9372) % 360
    j_transit = (2451545.0 + j_star + 0.0053 * math.sin(m * rad)
                 - 0.0069 * math.sin(2 * lam * rad))
    sin_dec = math.sin(lam * rad) * math.sin(23.44 * rad)
    dec = math.asin(sin_dec)
    # -0.833 deg accounts for refraction and the sun's disc
    cos_omega = ((math.sin(-0.833 * rad) - math.sin(lat * rad) * sin_dec)
                 / (math.cos(lat * rad) * math.cos(dec)))
    if abs(cos_omega) > 1:
        return None, None
    omega = math.degrees(math.acos(cos_omega))
    return (from_julian(j_transit - omega / 360.0, tz),
            from_julian(j_transit + omega / 360.0, tz))


def light_windows(d, lat, lon, tz):
    """
    The day's low-light windows, as the journal builder scores them: dawn is
    sunrise-1h to sunrise+2h, dusk is sunset-2h to sunset+1h. Returns a dict
    with sunrise, sunset, dawn (start, end) and dusk (start, end), or None
    where the sun never rises or sets.
    """
    rise, set_ = sun_times(d, lat, lon, tz)
    if rise is None:
        return None
    h = datetime.timedelta(hours=1)
    return {"sunrise": rise, "sunset": set_,
            "dawn": (rise - h, rise + 2 * h), "dusk": (set_ - 2 * h, set_ + h)}
