"""
The Corps' multi-day release outlook for Bull Shoals Dam.

SWPA's schedule covers today and tomorrow hour by hour; nothing else on the
page looks further. The Corps' CWMS Data API publishes the district's
planned daily-average release several days out
(`Bull_Shoals_Dam.Flow-Res Out.Ave.~1Day.1Day.Forecast`), the figure behind
the Reservoir Forecast report on their replacement site.

Date convention: a value stamped midnight is the average for the day that
ENDS there — the day before the stamp. Two checks agree (2026-10-05): the
measured daily series (`...Regi-Comp`) stamped a given midnight equals the
mean of the previous day's 24 hourly rows, and the Corps' own report code
shifts this forecast by -1 day before printing it.

What it is worth: a planning figure, not a schedule. Over the three weeks
to 2026-10-05 the stored forecast missed the measured daily average by
~740 CFS on average (days of 900-6,000 CFS) and once by 2,400. And a daily
average says nothing about the shape of the day: 2,000 CFS can be minimum
flow all night and five units at dusk. The copy says both.

Lake level rides along as `outlook["lake"]`: the pool elevation, how full
the conservation pool is, how much of the flood pool is in use, and the
Corps' forecast elevation. It is the reason behind the release figures —
water in the flood pool has to be evacuated, which means heavy generation
for as long as it takes; below the top of the conservation pool, releases
follow power demand. That reading of it is this repo's inference from how
the pools are operated, not a Corps statement; the numbers are theirs.
The elevation forecast is stamped 07:00 on the day it is for (no shift —
the Corps' report prints it as-is).

A failed fetch returns None and the page renders without the line.
"""
from datetime import datetime, timedelta

import requests

from data_fetcher import CWMS_URL, CWMS_OFFICE, DAM_TIMEZONE

FORECAST_SERIES = "Bull_Shoals_Dam.Flow-Res Out.Ave.~1Day.1Day.Forecast"
MEASURED_SERIES = "Bull_Shoals_Dam.Flow-Res Out.Ave.~1Day.1Day.Regi-Comp"

# Days after today to show; the series runs about four days out
OUTLOOK_DAYS = 5

LAKE_ELEV_SERIES = "Bull_Shoals_Dam-Headwater.Elev.Inst.1Hour.0.Decodes-rev"
LAKE_CONSERVATION_SERIES = "Bull_Shoals_Dam-Headwater.%-Conservation Pool.Inst.1Hour.0.CCP-Comp"
LAKE_FLOOD_SERIES = "Bull_Shoals_Dam-Headwater.%-Flood Pool.Inst.1Hour.0.CCP-Comp"
LAKE_ELEV_FORECAST_SERIES = "Bull_Shoals_Dam-Headwater.Elev.Inst.~1Day.0.Forecast"


def fetch_daily_series(name, begin, end, timeout=30):
    """A daily CWMS flow series as {the day it averages: CFS}."""
    response = requests.get(
        CWMS_URL,
        params={"office": CWMS_OFFICE, "name": name, "unit": "cfs",
                "begin": begin.isoformat(), "end": end.isoformat(),
                "page-size": 100},
        headers={"accept": "application/json;version=2"}, timeout=timeout)
    response.raise_for_status()
    days = {}
    for row in response.json().get("values", []):
        if row[1] is None:
            continue
        stamp = datetime.fromtimestamp(row[0] / 1000, DAM_TIMEZONE)
        # stamped at the END of the day it averages (see module docstring);
        # the noon nudge keeps a DST-shifted midnight on the right date
        days[(stamp - timedelta(hours=12)).date()] = round(row[1])
    return days


def _fetch_points(name, unit, begin, end, timeout=30):
    """A CWMS series as [(Central datetime, value)], oldest first, nulls dropped."""
    response = requests.get(
        CWMS_URL,
        params={"office": CWMS_OFFICE, "name": name, "unit": unit,
                "begin": begin.isoformat(), "end": end.isoformat(),
                "page-size": 100},
        headers={"accept": "application/json;version=2"}, timeout=timeout)
    response.raise_for_status()
    return [(datetime.fromtimestamp(row[0] / 1000, DAM_TIMEZONE), row[1])
            for row in response.json().get("values", []) if row[1] is not None]


def get_lake_level(current_time):
    """
    {'elevation_ft', 'conservation_pct', 'flood_pct', 'forecast_ft',
     'forecast_date'} for Bull Shoals Lake, or None without an elevation.
    Every field but the elevation may be None.
    """
    recent = current_time - timedelta(hours=12)
    try:
        elevation = _fetch_points(LAKE_ELEV_SERIES, "ft", recent, current_time)
    except Exception as e:
        print(f"Warning: Could not fetch the lake level: {e}")
        return None
    if not elevation:
        return None
    lake = {'elevation_ft': round(elevation[-1][1], 1), 'conservation_pct': None,
            'flood_pct': None, 'forecast_ft': None, 'forecast_date': None}
    try:
        conservation = _fetch_points(LAKE_CONSERVATION_SERIES, "%", recent, current_time)
        flood = _fetch_points(LAKE_FLOOD_SERIES, "%", recent, current_time)
        if conservation:
            lake['conservation_pct'] = round(conservation[-1][1])
        if flood:
            lake['flood_pct'] = round(flood[-1][1])
        ahead = _fetch_points(LAKE_ELEV_FORECAST_SERIES, "ft", current_time,
                              current_time + timedelta(days=OUTLOOK_DAYS + 2))
        if ahead:
            lake['forecast_ft'] = round(ahead[-1][1], 1)
            lake['forecast_date'] = ahead[-1][0].date()
    except Exception as e:
        print(f"Warning: Lake level is partial: {e}")
    return lake


def get_release_outlook(current_time):
    """
    {'days': [{'date', 'cfs'}, ...] for the days after today,
     'yesterday_cfs': measured average or None,
     'lake': get_lake_level() or None}, or None when the Corps has neither
    a forecast nor a lake level to give.
    """
    today = current_time.date()
    lake = get_lake_level(current_time)
    try:
        forecast = fetch_daily_series(
            FORECAST_SERIES, current_time,
            current_time + timedelta(days=OUTLOOK_DAYS + 2))
    except Exception as e:
        print(f"Warning: Could not fetch the Corps release outlook: {e}")
        forecast = {}

    days = [{'date': day, 'cfs': forecast[day]} for day in sorted(forecast)
            if today < day <= today + timedelta(days=OUTLOOK_DAYS)]
    if not days:
        return {'days': [], 'yesterday_cfs': None, 'lake': lake} if lake else None

    yesterday_cfs = None
    try:
        measured = fetch_daily_series(
            MEASURED_SERIES, current_time - timedelta(days=2), current_time)
        yesterday_cfs = measured.get(today - timedelta(days=1))
    except Exception as e:
        print(f"Warning: Could not fetch yesterday's average release: {e}")

    return {'days': days, 'yesterday_cfs': yesterday_cfs, 'lake': lake}


def describe(outlook):
    """
    (days line, context line) for the page and the text summary, or
    (None, None). Consecutive days at the same figure collapse to a range.
    """
    if not outlook or not outlook.get('days'):
        return None, None

    runs = []
    for day in outlook['days']:
        if runs and runs[-1]['cfs'] == day['cfs'] \
                and day['date'] - runs[-1]['end'] == timedelta(days=1):
            runs[-1]['end'] = day['date']
        else:
            runs.append({'start': day['date'], 'end': day['date'], 'cfs': day['cfs']})

    parts = []
    for run in runs:
        label = run['start'].strftime('%a')
        if run['end'] != run['start']:
            label += f"–{run['end'].strftime('%a')}"
        parts.append(f"{label} {run['cfs']:,}")
    days_line = " · ".join(parts) + " CFS"

    context = "Daily averages, not a schedule — a planning figure that moves."
    if outlook.get('yesterday_cfs') is not None:
        context = f"Yesterday averaged {outlook['yesterday_cfs']:,}. " + context
    return days_line, context


def describe_lake(outlook):
    """
    (level line, what it means) for the lake riding on the outlook, e.g.
    ("Lake 654.2 ft — 82% of conservation pool, flood pool empty; forecast 654.1 ft by Thu",
     "No flood water to evacuate: releases follow power demand."), or (None, None).
    """
    lake = (outlook or {}).get('lake')
    if not lake:
        return None, None
    line = f"Lake {lake['elevation_ft']:.1f} ft"
    flood, conservation = lake.get('flood_pct'), lake.get('conservation_pct')
    meaning = None
    if flood:
        line += f" — {flood}% of the flood pool in use"
        meaning = ("Flood water to evacuate: expect heavier, longer generation "
                   "until the lake is back in the conservation pool.")
    elif flood is not None:
        if conservation is not None:
            line += f" — {conservation}% of conservation pool, flood pool empty"
        else:
            line += " — flood pool empty"
        meaning = "No flood water to evacuate: releases follow power demand."
    elif conservation is not None:
        line += f" — {conservation}% of conservation pool"
    if lake.get('forecast_ft') is not None and lake.get('forecast_date'):
        line += f"; forecast {lake['forecast_ft']:.1f} ft by {lake['forecast_date'].strftime('%a')}"
    return line, meaning
