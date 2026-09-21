from datetime import datetime, timedelta

from landmarks import WHITE_HOLE_MILE


def get_flow(entry):
    """
    Return the total flow (CFS) moving downriver for a data entry.

    Uses total_release (turbine + spillway) so that flood-gate and other
    non-power releases are counted; falls back to turbine_release for
    entries where the total is unavailable.
    """
    total = entry.get('total_release')
    if total is not None:
        return total
    return entry.get('turbine_release')


# Speed anchors: (CFS at the midpoint of a generator band, average speed in mph).
# Speeds are the midpoints of His Place Resort's observed ranges; the gap bands
# (2-3, 4-5, 6-7 generators) and the >8-gen extension are interpolated values.
# Anchoring each band's average at its midpoint keeps the model faithful to the
# source ("3 to 4 generators ≈ 2.875 mph" applies mid-band, not at the top).
SPEED_ANCHORS = [
    (1650, 1.875),    # 0-1 gen
    (4950, 2.375),    # 1-2 gen
    (8250, 2.625),    # 2-3 gen (interpolated)
    (11550, 2.875),   # 3-4 gen
    (14850, 3.125),   # 4-5 gen (interpolated)
    (18150, 3.375),   # 5-6 gen
    (21450, 3.8125),  # 6-7 gen (interpolated)
    (24750, 4.25),    # 7-8 gen
    (28050, 4.75),    # >8 gen (extrapolated)
]


def calculate_travel_time(cfs):
    """
    Calculate travel time to White Hole based on flow rate (CFS), using
    the generator-band speeds described by His Place Resort (1 gen = 3300 CFS).

    Speed is piecewise-linear between band-midpoint anchors, clamped to the
    first/last anchor speeds outside the anchored range.

    Returns travel time in hours for 7 miles.
    """
    distance = WHITE_HOLE_MILE  # miles from dam to White Hole (landmarks.py)

    if cfs <= SPEED_ANCHORS[0][0]:
        speed = SPEED_ANCHORS[0][1]
    elif cfs >= SPEED_ANCHORS[-1][0]:
        speed = SPEED_ANCHORS[-1][1]
    else:
        for (lo_cfs, lo_speed), (hi_cfs, hi_speed) in zip(SPEED_ANCHORS, SPEED_ANCHORS[1:]):
            if lo_cfs <= cfs <= hi_cfs:
                fraction = (cfs - lo_cfs) / (hi_cfs - lo_cfs)
                speed = lo_speed + (hi_speed - lo_speed) * fraction
                break

    return distance / speed

# A change in flow counts as significant when it is both relatively and
# absolutely large — the thresholds shared by every rise/fall decision here
SIGNIFICANT_RATIO = 1.2
SIGNIFICANT_CFS = 500


def significant_change(from_cfs, to_cfs):
    """
    Classify a flow change as "rising", "falling", or None (not significant),
    using the >20% AND >500 CFS rule shared by the state, forecast, banner
    and timeline logic.
    """
    if from_cfs is None or to_cfs is None:
        return None
    if to_cfs > from_cfs * SIGNIFICANT_RATIO and to_cfs - from_cfs > SIGNIFICANT_CFS:
        return "rising"
    if from_cfs > to_cfs * SIGNIFICANT_RATIO and from_cfs - to_cfs > SIGNIFICANT_CFS:
        return "falling"
    return None


def recession_window(cut_time, from_cfs, to_cfs, mile=WHITE_HOLE_MILE):
    """
    When a cut in generation released at cut_time is felt at a point `mile`
    miles below the dam.

    Falling water is not a plug. The front of the cut travels at the speed
    of the higher flow ahead of it, and the river is fully down only when
    the slower low-flow water has made the trip — so the drop plays out as a
    window bracketed by the two travel times rather than a single step. The
    bracket agrees with His Place Resort's rule of thumb (distance in miles
    ÷ 2 ≈ hours to ~85% fall-out): for their 15-mile / 25,000 CFS example
    this gives a 3.3–8 h window against their quoted 7.5 h.

    Returns (start, end): when the level begins dropping and when it is
    fully down. For small cuts the window collapses toward the plug step.
    """
    fraction = mile / WHITE_HOLE_MILE
    start = cut_time + timedelta(hours=calculate_travel_time(from_cfs) * fraction)
    end = cut_time + timedelta(hours=calculate_travel_time(to_cfs) * fraction)
    if start > end:
        start = end
    return start, end


def clock(dt, reference=None, minutes=True):
    """
    Format a time for the page ("4:39 PM"), prefixed with the weekday when
    it falls on a different day than `reference` ("Mon 4:39 PM") — needed
    now that the schedule runs into tomorrow.
    """
    text = dt.strftime('%I:%M %p' if minutes else '%I %p').lstrip('0')
    if reference is not None and dt.date() != reference.date():
        text = f"{dt.strftime('%a')} {text}"
    return text


def determine_water_state(data, current_time):
    """Determine if water is rising, falling, or stable at White Hole."""
    # Get the most recent entries that would affect White Hole
    relevant_entries = []

    for entry in data:
        flow = get_flow(entry)
        if entry['date_time'] <= current_time and flow is not None:
            travel_time = calculate_travel_time(flow)
            arrival_time = entry['date_time'] + timedelta(hours=travel_time)

            # If this water has already reached White Hole
            if arrival_time <= current_time:
                relevant_entries.append({
                    'date_time': entry['date_time'],
                    'arrival_time': arrival_time,
                    'turbine_release': flow
                })
    
    # Sort by arrival time
    relevant_entries.sort(key=lambda x: x['arrival_time'])
    
    # Look at the trend over the last few entries
    if len(relevant_entries) >= 3:
        recent_entries = relevant_entries[-3:]
        first_cfs = recent_entries[0]['turbine_release']
        last_cfs = recent_entries[-1]['turbine_release']
        
        # Check for significant change (more than 20% and at least 500 CFS)
        return significant_change(first_cfs, last_cfs) or "stable"
    else:
        return "stable"  # Default if not enough data

def get_fishing_condition(cfs):
    """Determine fishing conditions based on CFS."""
    if cfs < 2000:
        return ("excellent wading", "low for boating")
    elif cfs < 5000:
        return ("still wadable", "ideal boating")
    elif cfs < 10000:
        return ("no wading", "ideal boating")
    else:
        return ("no wading", "high water")

def get_recent_trend(data, current_time, hours_back=6):
    """
    Analyze the trend of dam releases over the past few hours.

    Compares the earliest and latest readings in the window so the reported
    direction matches reality (a spread-vs-average comparison previously
    reported steady declines as increases).
    """
    # Filter to entries within the specified time window
    cutoff_time = current_time - timedelta(hours=hours_back)
    recent_data = [entry for entry in data if entry['date_time'] >= cutoff_time and entry['date_time'] <= current_time]

    if not recent_data:
        return "unknown"

    recent_data.sort(key=lambda x: x['date_time'])
    cfs_values = [get_flow(entry) for entry in recent_data if get_flow(entry) is not None]
    if not cfs_values:
        return "unknown"

    first_cfs = cfs_values[0]
    last_cfs = cfs_values[-1]

    # Significant change requires both a relative and an absolute difference,
    # matching the thresholds used by determine_water_state.
    if last_cfs > first_cfs * 1.5 and last_cfs - first_cfs > 500:
        return "significantly increased"
    elif first_cfs > last_cfs * 1.5 and first_cfs - last_cfs > 500:
        return "significantly decreased"
    elif last_cfs > first_cfs * 1.2 and last_cfs - first_cfs > 500:
        return "moderately increased"
    elif first_cfs > last_cfs * 1.2 and first_cfs - last_cfs > 500:
        return "moderately decreased"
    else:
        return "remained relatively steady"

def forecast_conditions(data, current_time):
    """Forecast conditions for the next few hours based on recent dam activity."""
    # Get the most recent entry
    recent_entries = [entry for entry in data if entry['date_time'] <= current_time]
    if not recent_entries:
        return "unknown"
    
    recent_entries.sort(key=lambda x: x['date_time'], reverse=True)
    latest_entry = recent_entries[0]
    
    # Check if there are entries that haven't reached White Hole yet
    latest_cfs = get_flow(latest_entry)
    if latest_cfs is None:
        return "unknown"

    travel_time = calculate_travel_time(latest_cfs)
    latest_impact_time = latest_entry['date_time'] + timedelta(hours=travel_time)

    # If the latest release hasn't reached White Hole yet
    if latest_impact_time > current_time:
        # Find the entry that's currently affecting White Hole
        # recent_entries is already sorted newest to oldest, so iterate without reversing
        current_cfs = None
        for entry in recent_entries:
            entry_flow = get_flow(entry)
            if entry_flow is not None:
                entry_travel_time = calculate_travel_time(entry_flow)
                entry_impact_time = entry['date_time'] + timedelta(hours=entry_travel_time)

                if entry_impact_time <= current_time:
                    current_cfs = entry_flow
                    break

        if current_cfs is None:
            # Nothing has arrived yet (all readings very recent) — compare
            # against the oldest release on the books instead
            current_cfs = next((get_flow(entry) for entry in reversed(recent_entries)
                                if get_flow(entry) is not None), None)

        if current_cfs is not None:
            change = significant_change(current_cfs, latest_cfs)
            if change == "rising":
                return "rising water expected soon"
            elif change == "falling":
                return "falling water expected soon"
            else:
                return "stable conditions expected"

    return "conditions should remain similar"


def format_generators(cfs):
    """
    Format CFS as an integer generator range (e.g., "2-3 generators").

    This matches how the dam reports generators (integers) rather than
    showing confusing decimal values like "2.6 generators".
    """
    exact = cfs / 3300
    low = int(exact)
    high = low + 1 if (exact % 1) > 0.1 else low

    if low == high:
        if low == 1:
            return "1 generator"
        return f"{low} generators"
    else:
        return f"{low}-{high} generators"


def calculate_timeline(data, current_time):
    """
    Calculate timeline of dam releases and their arrival times at White Hole.

    Returns a list of dicts with:
    - release_time: when the dam released this water
    - cfs: the flow rate
    - generators: formatted generator string
    - arrival_time: when it arrives/arrived at White Hole
    - status: 'arrived', 'current', or 'incoming'
    - minutes_until: minutes until arrival (for incoming water)
    - change: 'rising', 'falling' or None versus the release before it
    - recession_start: for a falling release, when the level starts dropping
      at White Hole (arrival_time is then when it is fully down); else None
    """
    recent_entries = [entry for entry in data
                      if entry['date_time'] <= current_time
                      and get_flow(entry) is not None]

    if not recent_entries:
        return []

    recent_entries.sort(key=lambda x: x['date_time'], reverse=True)

    timeline = []
    current_found = False

    for entry in recent_entries[:6]:  # Look at last 6 entries
        cfs = get_flow(entry)
        travel_time = calculate_travel_time(cfs)
        arrival_time = entry['date_time'] + timedelta(hours=travel_time)

        if arrival_time <= current_time:
            # Water has arrived
            if not current_found:
                status = 'current'
                current_found = True
            else:
                status = 'arrived'
            minutes_until = None
        else:
            # Water is incoming
            status = 'incoming'
            delta = arrival_time - current_time
            minutes_until = int(delta.total_seconds() / 60)

        timeline.append({
            'release_time': entry['date_time'],
            'cfs': cfs,
            'generators': format_generators(cfs),
            'arrival_time': arrival_time,
            'status': status,
            'minutes_until': minutes_until
        })

    # Sort by release time (oldest first for display)
    timeline.sort(key=lambda x: x['release_time'])
    annotate_changes(timeline, 'release_time')

    # Filter to show only interesting entries (current + incoming)
    # Plus one "arrived" for context
    filtered = []
    for item in timeline:
        if item['status'] in ('current', 'incoming'):
            filtered.append(item)
        elif item['status'] == 'arrived' and len(filtered) == 0:
            # Include one arrived entry for context
            filtered.append(item)

    return filtered[-4:]  # Return at most 4 entries for the timeline


def annotate_changes(items, time_key, previous_cfs=None):
    """
    Tag each timeline item (sorted oldest first) with 'change' relative to
    the release before it and, for falling water, 'recession_start' — the
    start of the drop at White Hole, with the item's arrival_time marking
    when it is fully down. previous_cfs seeds the comparison for the first
    item (e.g. the latest actual reading ahead of a scheduled timeline).
    """
    prev = previous_cfs
    for item in items:
        change = significant_change(prev, item['cfs'])
        item['change'] = change
        if change == 'falling':
            item['recession_start'], _ = recession_window(
                item[time_key], prev, item['cfs'])
        else:
            item['recession_start'] = None
        prev = item['cfs']
    return items


def calculate_forecast_timeline(forecast_data, current_time=None, previous_cfs=None):
    """
    Calculate forecast timeline from SWPA scheduled generation data.

    Takes hourly forecast entries from forecast_fetcher and applies travel time
    to estimate when each scheduled release will arrive at White Hole.

    Returns a list of dicts:
        - scheduled_time: when the dam is scheduled to generate (start of hour)
        - hour: hour number (1-24)
        - mw: megawatts scheduled
        - cfs: estimated CFS
        - generators: formatted generator string
        - arrival_time: estimated arrival at White Hole
        - wading: wading condition string
        - boating: boating condition string
        - change / recession_start: as in calculate_timeline, versus the
          scheduled hour before it (previous_cfs seeds the first hour)
    """
    if current_time is None:
        current_time = datetime.now()

    if not forecast_data:
        return []

    timeline = []
    for entry in forecast_data:
        cfs = entry['cfs']
        travel_hours = calculate_travel_time(cfs)
        arrival_time = entry['start_time'] + timedelta(hours=travel_hours)

        wading, boating = get_fishing_condition(cfs)

        timeline.append({
            'scheduled_time': entry['start_time'],
            'hour': entry['hour'],
            'mw': entry['mw'],
            'cfs': cfs,
            'generation_cfs': entry.get('generation_cfs', cfs),
            'min_flow_cfs': entry.get('min_flow_cfs', 0),
            'generators': format_generators(cfs),
            'arrival_time': arrival_time,
            'wading': wading,
            'boating': boating,
        })

    timeline.sort(key=lambda x: x['scheduled_time'])
    annotate_changes(timeline, 'scheduled_time', previous_cfs)
    return timeline


def find_incoming_change(timeline_data, current_cfs):
    """
    The first incoming timeline item that significantly changes the flow at
    White Hole — not merely the nearest incoming plug, which may be a
    same-level reading ahead of the real rise or drop.

    Returns (direction, item) or (None, None).
    """
    for item in timeline_data or []:
        if item.get('status') != 'incoming':
            continue
        direction = significant_change(current_cfs, item['cfs'])
        if direction:
            return direction, item
    return None, None
