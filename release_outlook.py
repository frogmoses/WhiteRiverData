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

A failed fetch returns None and the page renders without the line.
"""
from datetime import datetime, timedelta

import requests

from data_fetcher import CWMS_URL, CWMS_OFFICE, DAM_TIMEZONE

FORECAST_SERIES = "Bull_Shoals_Dam.Flow-Res Out.Ave.~1Day.1Day.Forecast"
MEASURED_SERIES = "Bull_Shoals_Dam.Flow-Res Out.Ave.~1Day.1Day.Regi-Comp"

# Days after today to show; the series runs about four days out
OUTLOOK_DAYS = 5


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


def get_release_outlook(current_time):
    """
    {'days': [{'date', 'cfs'}, ...] for the days after today,
     'yesterday_cfs': measured average or None}, or None when the Corps has
    no forecast to give.
    """
    today = current_time.date()
    try:
        forecast = fetch_daily_series(
            FORECAST_SERIES, current_time,
            current_time + timedelta(days=OUTLOOK_DAYS + 2))
    except Exception as e:
        print(f"Warning: Could not fetch the Corps release outlook: {e}")
        return None

    days = [{'date': day, 'cfs': forecast[day]} for day in sorted(forecast)
            if today < day <= today + timedelta(days=OUTLOOK_DAYS)]
    if not days:
        return None

    yesterday_cfs = None
    try:
        measured = fetch_daily_series(
            MEASURED_SERIES, current_time - timedelta(days=2), current_time)
        yesterday_cfs = measured.get(today - timedelta(days=1))
    except Exception as e:
        print(f"Warning: Could not fetch yesterday's average release: {e}")

    return {'days': days, 'yesterday_cfs': yesterday_cfs}


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
