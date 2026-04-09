from datetime import datetime, timedelta
import re

import requests
from bs4 import BeautifulSoup

# Bull Shoals Dam reference data from SWPA project table
BSD_FULL_MW = 391
BSD_FULL_CFS = 26400
BSD_MIN_FLOW_CFS = 250  # Approximate minimum base flow always released at the dam
BSD_COLUMN_INDEX = 12  # 0-based index in the data columns (column 13 in the table)

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
        include_base_flow: If True, adds the minimum base flow that the dam
            always releases regardless of generation.
    """
    generation_cfs = int(round((mw / BSD_FULL_MW) * BSD_FULL_CFS)) if mw > 0 else 0
    if include_base_flow:
        return generation_cfs + BSD_MIN_FLOW_CFS
    return generation_cfs


def get_swpa_schedule_url(target_date=None):
    """Get the SWPA schedule URL for the given date (defaults to today)."""
    if target_date is None:
        target_date = datetime.now()
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

    Returns a list of dicts with keys: hour, mw, cfs, start_time, end_time
    """
    if target_date is None:
        target_date = datetime.now()

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
        total_cfs = generation_cfs + BSD_MIN_FLOW_CFS

        # "hour ending" format: hour 1 means 00:00-01:00
        start_time = base_date + timedelta(hours=hour - 1)
        end_time = base_date + timedelta(hours=hour)

        schedule.append({
            'hour': hour,
            'mw': mw,
            'cfs': total_cfs,
            'generation_cfs': generation_cfs,
            'min_flow_cfs': BSD_MIN_FLOW_CFS,
            'start_time': start_time,
            'end_time': end_time,
        })

    return schedule


def get_swpa_forecast(current_time=None):
    """
    Fetch and parse the SWPA generation schedule for Bull Shoals Dam.

    Returns only future hours (hours that haven't ended yet).
    Returns an empty list if the fetch fails.
    """
    if current_time is None:
        current_time = datetime.now()

    url = get_swpa_schedule_url(current_time)

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching SWPA schedule: {e}")
        return []

    schedule = parse_schedule_html(response.text, current_time)

    # Filter to future hours only (where end_time is still in the future)
    future = [entry for entry in schedule if entry['end_time'] > current_time]

    return future


def get_schedule_date_from_html(html_content):
    """Extract the schedule date from the HTML title tag."""
    soup = BeautifulSoup(html_content, 'html.parser')
    title = soup.find('title')
    if not title:
        return None

    # Title format: "Generation Schedule,WEDNESDAY,APRIL 08, 2026"
    text = title.get_text()
    match = re.search(r'(\w+)\s+(\d{1,2}),\s*(\d{4})', text)
    if match:
        try:
            return datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%B %d %Y")
        except ValueError:
            return None
    return None
