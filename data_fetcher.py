from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import re

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# The USACE tabular page reports times in Central time ("Time CS/CDT" header).
DAM_TIMEZONE = ZoneInfo("America/Chicago")


def parse_dam_datetime(date_str, time_str):
    """
    Parse a USACE date/time pair into a timezone-aware Central datetime.

    USACE encodes midnight as 2400 on the *previous* day's date
    (e.g. "23AUG2026 2400" is midnight entering 24AUG2026).
    """
    if time_str == "2400":
        date_time = datetime.strptime(date_str, "%d%b%Y") + timedelta(days=1)
    else:
        date_time = datetime.strptime(f"{date_str} {time_str}", "%d%b%Y %H%M")
    return date_time.replace(tzinfo=DAM_TIMEZONE)


def parse_table_content(html_content):
    """Parse the USACE tabular HTML into a list of data entries."""
    soup = BeautifulSoup(html_content, 'html.parser')

    # Find the table data between the two horizontal rules
    content = str(soup)

    # Try to find the table between <hr> tags
    try:
        table_section = content.split("<hr>")[1].split("<hr>")[0]
    except IndexError:
        # If we can't find the HR tags, look for the table directly
        table_section = content

    # Parse the data into a structured format
    lines = table_section.strip().split('\n')
    data = []

    for line in lines:
        # Skip header lines and empty lines
        if not re.search(r'\d{2}[A-Z]{3}\d{4}', line):
            continue

        # Extract data using regex - more flexible to handle different month formats
        match = re.search(r'(\d{2}[A-Z]{3}\d{4})\s+(\d{4})\s+(\d+\.\d+|\-+)\s+(\d+\.\d+|\-+)\s+(\d+|\-+)\s+(\d+|\-+)\s+(\d+|\-+)\s+(\d+|\-+)', line)
        if match:
            date_str, time_str, elevation, tailwater, generation, turbine_release, spillway_release, total_release = match.groups()

            # Convert to appropriate data types
            try:
                date_time = parse_dam_datetime(date_str, time_str)
                elevation = float(elevation) if elevation != '----' else None
                tailwater = float(tailwater) if tailwater != '----' else None
                generation = int(generation) if generation != '----' else None
                turbine_release = int(turbine_release) if turbine_release != '----' else None
                spillway_release = int(spillway_release) if spillway_release != '----' else None
                total_release = int(total_release) if total_release != '----' else None

                entry_data = {
                    'date_time': date_time,
                    'elevation': elevation,
                    'tailwater': tailwater,
                    'generation': generation,
                    'turbine_release': turbine_release,
                    'spillway_release': spillway_release,
                    'total_release': total_release
                }
                data.append(entry_data)
            except ValueError:
                # Skip entries with invalid data
                continue

    return data


USACE_URL = "https://www.swl-wc.usace.army.mil/pages/data/tabular/htm/bulsdam.htm"
USACE_HOST = "www.swl-wc.usace.army.mil"

# DNS-over-HTTPS resolver used only when the host's own resolver fails. The
# Pi's resolver is the home router, which returns SERVFAIL for army.mil (its
# DNSSEC chain has failed before — Aug 2026 — and did again 2026-09-21) while
# public resolvers answer fine. Pinning the answered IP into Chromium keeps
# the live feed up without touching the Pi's system configuration.
DOH_URL = "https://cloudflare-dns.com/dns-query"
DNS_FAILURE_MARKER = "ERR_NAME_NOT_RESOLVED"


def resolve_via_doh(hostname, timeout=10):
    """The first A record for hostname from DNS-over-HTTPS, or None."""
    import requests
    try:
        response = requests.get(DOH_URL, params={"name": hostname, "type": "A"},
                                headers={"accept": "application/dns-json"}, timeout=timeout)
        response.raise_for_status()
        for answer in response.json().get("Answer", []):
            if answer.get("type") == 1 and answer.get("data"):
                return answer["data"]
    except Exception as e:
        print(f"DoH lookup for {hostname} failed: {e}")
    return None


def _fetch_html(url, extra_args=()):
    """Render the page in headless Chromium and return its HTML."""
    with sync_playwright() as p:
        # ignore-certificate-errors: the USACE cert chain has been flaky, and a
        # resolver-pinned IP may present a mismatched certificate
        browser = p.chromium.launch(
            args=["--ignore-certificate-errors", *extra_args],
            headless=True
        )
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        html_content = page.content()
        browser.close()
    return html_content


# Why a run has no readings. The two cases look identical on the page unless
# they are told apart: FETCH_FAILED is ours to fix (DNS, TLS, the site down),
# NO_DATA_PUBLISHED is the Corps publishing a table of dashes, which no retry
# or cache can repair (first seen 01OCT2026 2050, ~36 h and counting).
OUTAGE_FETCH_FAILED = "fetch_failed"
OUTAGE_NO_DATA_PUBLISHED = "no_data_published"


# Second source for the same readings: the Corps' CWMS Data API, the public
# JSON service behind the district's replacement site
# (https://water.usace.army.mil/office/swl/hourly and .../reports — the two
# links Public Affairs sent 2026-10-05 after the legacy app's Oct 1-4 blank
# spell; that site says it "will replace our legacy website in 2026"). The
# pages themselves are a JavaScript app behind a DoD consent banner, so the
# API is read directly. Checked 2026-10-05: each series matches the legacy
# table row for row, and the API held every hour of the blank spell. It ran
# ~2 h behind the legacy table that afternoon, so legacy stays first.
CWMS_URL = "https://cwms-data.usace.army.mil/cwms-data/timeseries"
CWMS_OFFICE = "SWL"
CWMS_LOOKBACK = "PT-48H"
# entry field -> (time series, unit). Spillway is not a series of its own
# here: it is whatever the reservoir released beyond the powerhouse.
CWMS_SERIES = {
    'elevation': ("Bull_Shoals_Dam-Headwater.Elev.Inst.1Hour.0.Decodes-rev", "ft"),
    'tailwater': ("Bull_Shoals_Dam-Tailwater.Elev-Downstream.Inst.1Hour.0.Decodes-rev", "ft"),
    'generation': ("Bull_Shoals_Dam.Energy-Gen_Plant.Total.1Hour.1Hour.CCP-Comp", "MWh"),
    'turbine_release': ("Bull_Shoals_Dam.Flow-Plant.Ave.1Hour.1Hour.CCP-Comp", "cfs"),
    'total_release': ("Bull_Shoals_Dam.Flow-Res Out.Ave.1Hour.1Hour.Regi-Comp", "cfs"),
}
# The legacy table is passed over for CWMS when its newest reading is older
# than this and CWMS has a newer one (mirrors main.STALE_DATA_HOURS).
LEGACY_STALE_HOURS = 3


def _fetch_cwms_series(name, unit, timeout=30):
    """One CWMS time series as {epoch ms: value}, missing values dropped."""
    import requests
    response = requests.get(
        CWMS_URL,
        params={"office": CWMS_OFFICE, "name": name, "unit": unit,
                "begin": CWMS_LOOKBACK, "page-size": 500},
        headers={"accept": "application/json;version=2"}, timeout=timeout)
    response.raise_for_status()
    return {row[0]: row[1] for row in response.json().get("values", [])
            if row[1] is not None}


def build_cwms_entries(series):
    """
    Merge {field: {epoch ms: value}} into entries shaped like the legacy
    table's rows. An hour with no flow figure at all is dropped, as a row of
    dashes is there.
    """
    timestamps = sorted(set().union(*[set(v) for v in series.values()])) if series else []
    data = []
    for ts in timestamps:
        value = {field: values.get(ts) for field, values in series.items()}
        turbine, total = value.get('turbine_release'), value.get('total_release')
        if turbine is None and total is None:
            continue
        turbine = round(turbine) if turbine is not None else None
        total = round(total) if total is not None else None
        spillway = max(0, total - turbine) if None not in (turbine, total) else None
        elevation, tailwater, generation = (
            value.get('elevation'), value.get('tailwater'), value.get('generation'))
        data.append({
            'date_time': datetime.fromtimestamp(ts / 1000, DAM_TIMEZONE),
            'elevation': round(elevation, 2) if elevation is not None else None,
            'tailwater': round(tailwater, 2) if tailwater is not None else None,
            'generation': round(generation) if generation is not None else None,
            'turbine_release': turbine,
            'spillway_release': spillway,
            'total_release': total,
        })
    return data


def get_cwms_data():
    """Bull Shoals readings from the CWMS Data API, or [] when it has none."""
    try:
        series = {}
        for field, (name, unit) in CWMS_SERIES.items():
            try:
                series[field] = _fetch_cwms_series(name, unit)
            except Exception as e:
                # elevation/tailwater/generation are not needed downstream;
                # only the two flow series can sink the fallback
                print(f"CWMS series {field} failed: {e}")
        return build_cwms_entries(series)
    except Exception as e:
        print(f"CWMS fallback failed: {e}")
        return []


# The eight main units each publish their own hourly flow, and they sum to
# the plant flow exactly (checked over 14 days, 2026-10-05), so counting the
# non-zero ones gives the units actually running — which the page otherwise
# only estimates from total flow. A running unit never read under ~200 CFS
# in that fortnight; one unit carries the ~700 CFS minimum flow on its own.
TURBINE_COUNT = 8
TURBINE_SERIES = "Bull_Shoals_Dam-Turbine{n}.Flow-Power.Ave.1Hour.1Hour.Decodes-rev"
UNIT_RUNNING_MIN_CFS = 100


def get_units_running():
    """
    {reading time: main units running that hour}, or {} when CWMS cannot
    say. An hour counts only when all eight units reported; the first failed
    request abandons the lot, so a dead API costs one timeout, not eight.
    """
    try:
        per_unit = [_fetch_cwms_series(TURBINE_SERIES.format(n=n), "cfs", timeout=15)
                    for n in range(1, TURBINE_COUNT + 1)]
    except Exception as e:
        print(f"Units-running lookup failed: {e}")
        return {}
    hours = set(per_unit[0]).intersection(*per_unit[1:])
    return {
        datetime.fromtimestamp(ts / 1000, DAM_TIMEZONE):
            sum(1 for unit in per_unit if unit[ts] >= UNIT_RUNNING_MIN_CFS)
        for ts in hours
    }


def annotate_units_running(data, units=None):
    """
    Tag each reading with `units_running` where CWMS has that hour. CWMS has
    run a couple of hours behind the legacy table, so the newest readings
    often go untagged; everything downstream treats the key as optional.
    """
    if units is None:
        units = get_units_running()
    for entry in data:
        count = units.get(entry['date_time'])
        if count is not None:
            entry['units_running'] = count
    return data


def _newest(data):
    return max(entry['date_time'] for entry in data)


def get_legacy_data():
    """
    Scrape the legacy Bull Shoals table using Playwright. Raises when the
    page cannot be fetched; returns [] when it loads with every row blank.

    When the local resolver cannot resolve the USACE host, resolve it over
    DNS-over-HTTPS and retry with the answer pinned into Chromium.
    """
    try:
        html_content = _fetch_html(USACE_URL)
    except Exception as e:
        if DNS_FAILURE_MARKER not in str(e):
            raise
        ip = resolve_via_doh(USACE_HOST)
        if not ip:
            raise
        print(f"Local DNS failed for {USACE_HOST}; retrying with DoH answer {ip}")
        html_content = _fetch_html(
            USACE_URL, [f"--host-resolver-rules=MAP {USACE_HOST} {ip}"])
    return parse_table_content(html_content)


def get_bull_shoals_data():
    """
    The dam's hourly readings: the legacy table first, the CWMS Data API
    when that table cannot be fetched, is blank, or has gone stale while
    CWMS is newer. The error sentinel only when both come up empty.
    """
    reason = OUTAGE_NO_DATA_PUBLISHED
    try:
        data = get_legacy_data()
    except Exception as e:
        print(f"Error fetching data: {e}")
        data, reason = [], OUTAGE_FETCH_FAILED

    if data:
        age = datetime.now(DAM_TIMEZONE) - _newest(data)
        if age <= timedelta(hours=LEGACY_STALE_HOURS):
            return annotate_units_running(data)
        cwms = get_cwms_data()
        if cwms and _newest(cwms) > _newest(data):
            print("Legacy USACE table is stale; using the newer CWMS readings")
            return annotate_units_running(cwms)
        return annotate_units_running(data)

    cwms = get_cwms_data()
    if cwms:
        print("Legacy USACE table unavailable; using CWMS readings")
        return annotate_units_running(cwms)
    if reason == OUTAGE_NO_DATA_PUBLISHED:
        # The page came back but held no usable rows: Bull Shoals is
        # publishing dashes. Say so rather than blaming the fetch.
        print("USACE page fetched but every row is blank — dam publishing no readings")
    return get_error_data(reason)

# Cache of the last successful fetch, used as a fallback when the USACE site
# is unreachable (e.g. the Aug 2026 army.mil DNS outage). Written relative to
# the working directory: production runs from the repo root and commits the
# file (see run_white_hole.sh — a plain untracked file would be lost to its
# `git stash -u`); tests run from a tmp dir and stay isolated.
LAST_GOOD_CACHE_FILE = "last_good_data.json"


def save_last_good_data(data, filename=LAST_GOOD_CACHE_FILE):
    """Persist a successful fetch so a later outage can fall back to it."""
    try:
        serializable = []
        for entry in data:
            entry = dict(entry)
            entry['date_time'] = entry['date_time'].isoformat()
            serializable.append(entry)
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(serializable, f, indent=1)
        return True
    except Exception as e:
        print(f"Warning: could not save last-good data cache: {e}")
        return False


def load_last_good_data(filename=LAST_GOOD_CACHE_FILE, max_age_hours=24,
                        current_time=None):
    """
    Load the cached last successful fetch.

    Returns the data list, or None when the cache is missing, unreadable,
    error-flagged, or its newest reading is older than max_age_hours
    (checked only when current_time is given).
    """
    try:
        with open(filename, encoding='utf-8') as f:
            raw = json.load(f)

        data = []
        for entry in raw:
            entry = dict(entry)
            parsed = datetime.fromisoformat(entry['date_time'])
            if parsed.tzinfo is not None:
                # fromisoformat yields a fixed-offset tz; normalize to the
                # dam's zone so downstream arithmetic crosses DST correctly
                parsed = parsed.astimezone(DAM_TIMEZONE)
            entry['date_time'] = parsed
            data.append(entry)

        if not data or any(entry.get('error') for entry in data):
            return None

        if current_time is not None and max_age_hours is not None:
            newest = max(entry['date_time'] for entry in data)
            age_hours = (current_time - newest).total_seconds() / 3600
            if age_hours > max_age_hours:
                return None

        return data
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"Warning: could not load last-good data cache: {e}")
        return None


def get_error_data(reason=OUTAGE_FETCH_FAILED):
    """Return the error sentinel, tagged with why there are no readings."""
    # Return a minimal dataset with just the current time and an error indicator
    current_time = datetime.now(DAM_TIMEZONE)
    error_data = [{
        'date_time': current_time,
        'elevation': None,
        'tailwater': None,
        'generation': None,
        'turbine_release': 0,  # Using 0 as an error indicator
        'spillway_release': 0,
        'total_release': 0,
        'error': True,  # Flag to indicate this is error data
        'reason': reason
    }]
    
    return error_data
