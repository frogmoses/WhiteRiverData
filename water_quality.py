"""
Tailwater temperature and dissolved oxygen from the USGS gauges below Bull
Shoals Dam.

Two gauges publish 15-minute water quality (no discharge) on the reach:
    07054527  "below Bull Shoals Dam near Fairview" — beside Cane Island,
              about a mile above Gaston's; the closer one to the water
              we fish, so it is preferred
    07054502  "below Bull Shoals Dam at Bull Shoals" — ~0.7 mi below the
              dam; the fallback

Both are read in one call to the USGS instantaneous-values service. A
failed fetch returns None and the page renders without the section — the
water-quality block is a bonus on top of the flow report, never a reason
to blank it.

Thresholds are the commonly cited trout ranges (AGFC/USGS tailwater
guidance): dissolved oxygen under 5 mg/L is stressful, under 6 marginal;
water over 68°F is a stop-fishing level for released trout, 62–68°F warm,
50–62°F prime. Bull Shoals sags on oxygen every fall as the lake turns over.
"""
from datetime import datetime

import requests

from data_fetcher import DAM_TIMEZONE

USGS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/"

# (site code, short label), in order of preference
USGS_SITES = [
    ("07054527", "USGS gauge at Cane Island"),
    ("07054502", "USGS gauge below the dam"),
]
PARAM_TEMP = "00010"   # water temperature, °C
PARAM_DO = "00300"     # dissolved oxygen, mg/L

# Trout thresholds
DO_LOW_MG_L = 5.0
DO_GOOD_MG_L = 6.0
TEMP_COLD_F = 50.0
TEMP_WARM_F = 62.0
TEMP_HOT_F = 68.0

# A reading older than this is shown with its age rather than as "now"
STALE_READING_HOURS = 3


def fetch_usgs_iv(period="PT6H", timeout=15):
    """Raw USGS instantaneous-values JSON for both gauges, or None."""
    params = {
        "format": "json",
        "sites": ",".join(site for site, _ in USGS_SITES),
        "parameterCd": f"{PARAM_TEMP},{PARAM_DO}",
        "period": period,
    }
    try:
        response = requests.get(USGS_IV_URL, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as e:
        print(f"Error fetching USGS water quality: {e}")
        return None


def _latest_value(series):
    """(value, observed datetime in Central) for the newest good reading."""
    values = series.get("values", [{}])[0].get("value", [])
    try:
        no_data = float(series.get("variable", {}).get("noDataValue", -999999))
    except (TypeError, ValueError):
        no_data = -999999.0
    for reading in reversed(values):
        raw = reading.get("value")
        if raw in (None, ""):
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if value == no_data:
            continue
        observed = datetime.fromisoformat(reading["dateTime"])
        if observed.tzinfo is not None:
            observed = observed.astimezone(DAM_TIMEZONE)
        return value, observed
    return None, None


def parse_water_quality(raw, current_time=None):
    """
    Reduce the USGS JSON to one reading from the preferred gauge.

    Returns None when no gauge has either value, else a dict:
        site, site_label, temp_c, temp_f, do_mg_l, observed, age_hours,
        do_status ('low' | 'marginal' | 'good' | None),
        temp_status ('cold' | 'prime' | 'warm' | 'hot' | None)
    """
    if not raw:
        return None
    try:
        series_list = raw["value"]["timeSeries"]
    except (KeyError, TypeError):
        return None

    by_site = {}
    for series in series_list:
        try:
            site = series["sourceInfo"]["siteCode"][0]["value"]
            param = series["variable"]["variableCode"][0]["value"]
        except (KeyError, IndexError, TypeError):
            continue
        value, observed = _latest_value(series)
        if value is None:
            continue
        by_site.setdefault(site, {})[param] = (value, observed)

    for site, label in USGS_SITES:
        readings = by_site.get(site)
        if not readings:
            continue
        temp = readings.get(PARAM_TEMP)
        do = readings.get(PARAM_DO)
        observed = max(t for _, t in readings.values())
        temp_c = temp[0] if temp else None
        temp_f = round(temp_c * 9 / 5 + 32, 1) if temp_c is not None else None
        do_mg_l = do[0] if do else None
        age_hours = None
        if current_time is not None:
            age_hours = (current_time - observed).total_seconds() / 3600
        return {
            "site": site,
            "site_label": label,
            "temp_c": temp_c,
            "temp_f": temp_f,
            "do_mg_l": do_mg_l,
            "observed": observed,
            "age_hours": age_hours,
            "do_status": do_status(do_mg_l),
            "temp_status": temp_status(temp_f),
        }
    return None


def do_status(do_mg_l):
    if do_mg_l is None:
        return None
    if do_mg_l < DO_LOW_MG_L:
        return "low"
    if do_mg_l < DO_GOOD_MG_L:
        return "marginal"
    return "good"


def temp_status(temp_f):
    if temp_f is None:
        return None
    if temp_f < TEMP_COLD_F:
        return "cold"
    if temp_f < TEMP_WARM_F:
        return "prime"
    if temp_f < TEMP_HOT_F:
        return "warm"
    return "hot"


def get_water_quality(current_time=None):
    """Fetch and reduce the latest tailwater reading; None on any failure."""
    if current_time is None:
        current_time = datetime.now(DAM_TIMEZONE)
    return parse_water_quality(fetch_usgs_iv(), current_time)


# Short verdicts shared by the page and the fishing report
DO_VERDICTS = {
    "low": "LOW — fish are stressed: land them fast, keep them wet, skip the photo",
    "marginal": "marginal — land fish quickly and release in the current",
    "good": "good",
}
TEMP_VERDICTS = {
    "cold": "cold — slow metabolism, slow the presentation down",
    "prime": "prime trout water — fish will chase",
    "warm": "warm — fish early and late, release fast",
    "hot": "too warm to release trout safely — reconsider fishing for them",
}


def describe(wq):
    """
    Two plain sentences for the page/report, e.g.
    ("Water 58.3°F — prime trout water — fish will chase",
     "Oxygen 4.5 mg/L — LOW — fish are stressed: ...").
    Either may be None when that value is missing.
    """
    if not wq:
        return None, None
    temp_line = None
    if wq["temp_f"] is not None:
        temp_line = f"Water {wq['temp_f']:.1f}°F — {TEMP_VERDICTS[wq['temp_status']]}"
    do_line = None
    if wq["do_mg_l"] is not None:
        do_line = f"Oxygen {wq['do_mg_l']:.1f} mg/L — {DO_VERDICTS[wq['do_status']]}"
    return temp_line, do_line
