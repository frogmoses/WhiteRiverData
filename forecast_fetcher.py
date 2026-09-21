from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re

import requests
from bs4 import BeautifulSoup

# SWPA generation schedules are published in Central time
SWPA_TIMEZONE = ZoneInfo("America/Chicago")

# Bull Shoals Dam reference data from SWPA project table
BSD_FULL_MW = 391
BSD_FULL_CFS = 26400
BSD_MIN_FLOW_CFS = 250  # Base flow added on top of scheduled generation
# The dam never runs below its minimum-flow release (~750 CFS observed;
# His Place cites ~850 at dead-low), even when the schedule shows 0 MW.
BSD_MIN_TOTAL_CFS = 750

# Day-of-week to URL slug mapping
DAY_SLUGS = {
    0: "mon",
    1: "tue",
    2: "wed",
    3: "thu",
    4: "fri",
    5: "sat",
    6: "sun",
}

SWPA_BASE_URL = "https://www.energy.gov/swpa"


def mw_to_cfs(mw, include_base_flow=True):
    """Convert megawatts to CFS using Bull Shoals Dam's capacity ratio.

    Args:
        mw: Megawatts of generation
        include_base_flow: If True, adds the minimum base flow and floors the
            result at the dam's minimum-flow release (BSD_MIN_TOTAL_CFS).
    """
    generation_cfs = int(round((mw / BSD_FULL_MW) * BSD_FULL_CFS)) if mw > 0 else 0
    if include_base_flow:
        return max(generation_cfs + BSD_MIN_FLOW_CFS, BSD_MIN_TOTAL_CFS)
    return generation_cfs


def get_swpa_schedule_url(target_date=None):
    """Get the SWPA schedule URL for the given date (defaults to today, Central time)."""
    if target_date is None:
        target_date = datetime.now(SWPA_TIMEZONE)
    slug = DAY_SLUGS[target_date.weekday()]
    return f"{SWPA_BASE_URL}/{slug}.htm"


def parse_schedule_html(html_content, target_date=None):
    """
    Parse the SWPA generation schedule HTML and extract Bull Shoals (BSD) hourly data.

    The schedule is a fixed-width ASCII table inside a <PRE> tag with format:
     HR   BBD   DEN   KEY   ...   BSD   ...
      1     0    90     0   ...     7   ...
      2     0    90     0   ...     7   ...

    Hours are in "hour ending" format: hour 1 = 00:00-01:00, hour 14 = 13:00-14:00.

    Returns a list of dicts with keys: hour, mw, cfs, start_time, end_time.
    Times carry the timezone of target_date (Central in production).
    """
    if target_date is None:
        target_date = datetime.now(SWPA_TIMEZONE)

    soup = BeautifulSoup(html_content, 'html.parser')
    pre = soup.find('pre')
    if not pre:
        return []

    text = pre.get_text()
    lines = text.strip().split('\n')

    # Find the header row with project abbreviations (contains "HR" and "BSD")
    header_line = None
    header_line_idx = None
    bsd_col = None
    for idx, line in enumerate(lines):
        if 'BSD' in line and 'HR' in line:
            header_line = line
            header_line_idx = idx
            break

    if not header_line:
        return []

    # Find BSD column position by splitting header
    headers = header_line.split()
    try:
        bsd_col = headers.index('BSD')
    except ValueError:
        return []

    # Parse hourly data rows — only lines AFTER the header row
    # Lines start with an hour number (1-24) in the HR column
    schedule = []
    base_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)

    for line in lines[header_line_idx + 1:]:
        # Match lines that start with an hour number (1-24)
        match = re.match(r'^\s*(\d{1,2})\s+', line)
        if not match:
            continue

        hour = int(match.group(1))
        if hour < 1 or hour > 24:
            continue

        # Split the line and extract the BSD column value
        values = line.split()
        if len(values) <= bsd_col:
            continue

        # Skip the TOT (totals) row
        if values[0] == 'TOT':
            break

        try:
            mw = float(values[bsd_col])
        except (ValueError, IndexError):
            continue

        generation_cfs = mw_to_cfs(mw, include_base_flow=False)
        total_cfs = max(generation_cfs + BSD_MIN_FLOW_CFS, BSD_MIN_TOTAL_CFS)

        # "hour ending" format: hour 1 means 00:00-01:00
        start_time = base_date + timedelta(hours=hour - 1)
        end_time = base_date + timedelta(hours=hour)

        schedule.append({
            'hour': hour,
            'mw': mw,
            'cfs': total_cfs,
            'generation_cfs': generation_cfs,
            # Whatever isn't scheduled generation is minimum/base flow, so the
            # displayed "generation + min flow" breakdown always sums to cfs
            'min_flow_cfs': total_cfs - generation_cfs,
            'start_time': start_time,
            'end_time': end_time,
        })

    return schedule


def _fetch_schedule(target_date):
    """
    Fetch and parse the SWPA day-of-week page for target_date.

    Returns the parsed schedule, or [] when the fetch fails or the page's
    schedule date (from the <pre> header) is not target_date. The day pages
    persist for a week, so a missed post would otherwise serve last week's
    schedule under today's name.
    """
    url = get_swpa_schedule_url(target_date)
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching SWPA schedule {url}: {e}")
        return []

    page_date = get_schedule_date_from_html(response.text)
    if page_date is None:
        print(f"SWPA schedule {url} has no recognizable schedule date; skipping")
        return []
    if page_date.date() != target_date.date():
        print(f"SWPA schedule {url} is for {page_date.date()}, "
              f"not {target_date.date()}; skipping")
        return []

    return parse_schedule_html(response.text, target_date)


def get_swpa_forecast(current_time=None):
    """
    Fetch and parse the SWPA generation schedule for Bull Shoals Dam.

    Returns the remaining hours of today's schedule followed by tomorrow's
    full schedule once SWPA has posted it (normally by ~5 p.m. Central;
    Friday's post covers the weekend). Each page is validated against the
    date it is supposed to carry, so a stale page is dropped rather than
    re-anchored to the wrong day. Returns [] if nothing valid is available.
    """
    if current_time is None:
        current_time = datetime.now(SWPA_TIMEZONE)

    schedule = _fetch_schedule(current_time)
    schedule += _fetch_schedule(current_time + timedelta(days=1))

    # Filter to future hours only (where end_time is still in the future)
    future = [entry for entry in schedule if entry['end_time'] > current_time]

    return future


# Schedule-date line inside the <pre> block, e.g.
# "PROJECTED LOADING SCHEDULE      TUESDAY SEPTEMBER 15, 2026      CALICO ROCK TEMP:  98"
SCHEDULE_DATE_RE = re.compile(
    r'PROJECTED LOADING SCHEDULE\s+[A-Z]+\s+([A-Z]+)\s+(\d{1,2}),\s*(\d{4})',
    re.IGNORECASE)


def get_schedule_date_from_html(html_content):
    """
    Extract the schedule's own date from the <pre> header line.

    The page <title> also carries a date, but it is the CMS render date —
    every day-of-week page shows today's date there, including last
    week's leftovers — so it says nothing about which day the schedule
    covers. Only the "PROJECTED LOADING SCHEDULE <DAY> <MONTH> <DD>, <YYYY>"
    line inside the <pre> block is authoritative. Returns None when absent.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    pre = soup.find('pre')
    if not pre:
        return None

    match = SCHEDULE_DATE_RE.search(pre.get_text())
    if not match:
        return None
    try:
        return datetime.strptime(
            f"{match.group(1).title()} {match.group(2)} {match.group(3)}", "%B %d %Y")
    except ValueError:
        return None
