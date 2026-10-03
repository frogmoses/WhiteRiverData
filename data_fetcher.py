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


def get_bull_shoals_data():
    """
    Scrape the Bull Shoals Dam data table from the website using Playwright.

    When the local resolver cannot resolve the USACE host, resolve it over
    DNS-over-HTTPS and retry with the answer pinned into Chromium.
    """
    try:
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

        data = parse_table_content(html_content)

        if data:
            return data
        # The page came back but held no usable rows: Bull Shoals is
        # publishing dashes. Say so rather than blaming the fetch.
        print("USACE page fetched but every row is blank — dam publishing no readings")
        return get_error_data(OUTAGE_NO_DATA_PUBLISHED)

    except Exception as e:
        print(f"Error fetching data: {e}")
        return get_error_data(OUTAGE_FETCH_FAILED)

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
