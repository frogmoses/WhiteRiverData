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

The Corps also has sensors in the tailwater at the dam itself, published
through the CWMS Data API (see data_fetcher). That reading rides along as
`wq["dam"]` and renders as one line under the USGS pills: it is the water
before it has travelled, so the gap to the gauge is how much the reach
warmed it, and it is where a low-oxygen release shows first (2026-10-04:
8.9 mg/L at minimum flow, 5.9 the hour three units came on). When USGS is
down the dam reading stands in as the main one, labelled as such. The
series are the Corps' own averages of their two probes; the right-bank
probe alone swings several mg/L in daylight at minimum flow.

Thresholds are the commonly cited trout ranges (AGFC/USGS tailwater
guidance): dissolved oxygen under 5 mg/L is stressful, under 6 marginal;
water over 68°F is a stop-fishing level for released trout, 62–68°F warm,
50–62°F prime. Bull Shoals sags on oxygen every fall as the lake turns over.
"""
from datetime import datetime

import requests

from data_fetcher import DAM_TIMEZONE, CWMS_URL, CWMS_OFFICE

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

# The Corps' tailwater sensors at the dam (hourly, averaged over both probes)
DAM_TEMP_SERIES = "Bull_Shoals_Dam-Tailwater.Temp-Water_Ave.Inst.1Hour.0.CCP-Comp"
DAM_DO_SERIES = "Bull_Shoals_Dam-Tailwater.Conc-DO_Ave.Inst.1Hour.0.CCP-Comp"
DAM_SOURCE = "corps_dam"
DAM_LABEL = "Corps sensors at the dam"


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


def _latest_cwms(name, unit, timeout=15):
    """(value, observed Central datetime) for a CWMS series' newest reading."""
    response = requests.get(
        CWMS_URL,
        params={"office": CWMS_OFFICE, "name": name, "unit": unit,
                "begin": "PT-12H", "page-size": 100},
        headers={"accept": "application/json;version=2"}, timeout=timeout)
    response.raise_for_status()
    for row in reversed(response.json().get("values", [])):
        if row[1] is not None:
            return row[1], datetime.fromtimestamp(row[0] / 1000, DAM_TIMEZONE)
    return None, None


def get_dam_water_quality(current_time=None):
    """
    The Corps' temperature/oxygen reading at the dam, shaped like the USGS
    one (source DAM_SOURCE, no site), or None when CWMS has nothing.
    """
    if current_time is None:
        current_time = datetime.now(DAM_TIMEZONE)
    try:
        temp_f, temp_time = _latest_cwms(DAM_TEMP_SERIES, "F")
        do_mg_l, do_time = _latest_cwms(DAM_DO_SERIES, "mg/l")
    except Exception as e:
        print(f"Error fetching Corps tailwater sensors: {e}")
        return None
    if temp_f is None and do_mg_l is None:
        return None
    observed = max(t for t in (temp_time, do_time) if t is not None)
    temp_f = round(temp_f, 1) if temp_f is not None else None
    do_mg_l = round(do_mg_l, 1) if do_mg_l is not None else None
    return {
        "source": DAM_SOURCE,
        "site": None,
        "site_label": DAM_LABEL,
        "temp_c": round((temp_f - 32) * 5 / 9, 1) if temp_f is not None else None,
        "temp_f": temp_f,
        "do_mg_l": do_mg_l,
        "observed": observed,
        "age_hours": (current_time - observed).total_seconds() / 3600,
        "do_status": do_status(do_mg_l),
        "temp_status": temp_status(temp_f),
    }


def get_water_quality(current_time=None):
    """
    The latest tailwater reading: the USGS gauge with the Corps' reading at
    the dam attached as `["dam"]`, or the dam reading alone when USGS is
    down. None when neither answers.
    """
    if current_time is None:
        current_time = datetime.now(DAM_TIMEZONE)
    usgs = parse_water_quality(fetch_usgs_iv(), current_time)
    dam = get_dam_water_quality(current_time)
    if usgs and dam:
        usgs["dam"] = dam
    return usgs or dam


def dam_line(wq, when=None):
    """
    One plain line for the reading at the dam riding on a USGS reading, e.g.
    "At the dam: 57.9°F · oxygen 5.9 mg/L — marginal (Corps sensors, 12:00 PM)".
    None when there is no such reading.
    """
    dam = (wq or {}).get("dam")
    if not dam:
        return None
    parts = []
    if dam["temp_f"] is not None:
        parts.append(f"{dam['temp_f']:.1f}°F")
    if dam["do_mg_l"] is not None:
        oxygen = f"oxygen {dam['do_mg_l']:.1f} mg/L"
        if dam["do_status"] != "good":
            oxygen += f" — {dam['do_status']}"
        parts.append(oxygen)
    if not parts:
        return None
    source = f"Corps sensors, {when}" if when else "Corps sensors"
    return f"At the dam: {' · '.join(parts)} ({source})"


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
