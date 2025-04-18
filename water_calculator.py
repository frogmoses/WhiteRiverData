from datetime import datetime, timedelta

def calculate_travel_time(cfs):
    """
    Calculate travel time to White Hole based on flow rate (CFS), using
    the generator bands and average speeds as described by His Place Resort.

    Generator bands (1 gen = 3300 CFS):
        - 0 to 1 gen (0–3300): avg 1.875 mph
        - 1 to 2 gen (3300–6600): avg 2.375 mph
        - 3 to 4 gen (9900–13200): avg 2.875 mph
        - 5 to 6 gen (16500–19800): avg 3.375 mph
        - 7 to 8 gen (23100–26400+): avg 4.25 mph
        - Between bands: interpolate between averages

    Returns travel time in hours for 7 miles.
    """
    distance = 7  # miles from dam to White Hole

    # Define generator bands and average speeds
    bands = [
        (0, 3300, 1.875),      # 0–1 gen
        (3300, 6600, 2.375),   # 1–2 gen
        (6600, 9900, 2.625),   # 2–3 gen (interpolated)
        (9900, 13200, 2.875),  # 3–4 gen
        (13200, 16500, 3.125), # 4–5 gen (interpolated)
        (16500, 19800, 3.375), # 5–6 gen
        (19800, 23100, 3.8125),# 6–7 gen (interpolated)
        (23100, 26400, 4.25),  # 7–8 gen
        (26400, float('inf'), 4.75), # >8 gen, extrapolated
    ]

    # Find the band for the given cfs
    for i, (low, high, avg_speed) in enumerate(bands):
        if low <= cfs < high:
            # If not the first band, interpolate between this and previous
            if i > 0:
                prev_low, prev_high, prev_speed = bands[i-1]
                # Linear interpolation between prev_speed and avg_speed
                band_range = high - low
                if band_range > 0:
                    interp = (cfs - low) / band_range
                    speed = prev_speed + (avg_speed - prev_speed) * interp
                else:
                    speed = avg_speed
            else:
                speed = avg_speed
            break
    else:
        # If above all bands, use the last avg_speed
        speed = bands[-1][2]

    # Calculate travel time in hours
    travel_time = distance / speed
    return travel_time

def determine_water_state(data, current_time, white_hole_cfs):
    """Determine if water is rising, falling, or stable at White Hole."""
    # Get the most recent entries that would affect White Hole
    relevant_entries = []
    
    for entry in data:
        if entry['date_time'] <= current_time and entry['turbine_release'] is not None:
            travel_time = calculate_travel_time(entry['turbine_release'])
            arrival_time = entry['date_time'] + timedelta(hours=travel_time)
            
            # If this water has already reached White Hole
            if arrival_time <= current_time:
                relevant_entries.append({
                    'date_time': entry['date_time'],
                    'arrival_time': arrival_time,
                    'turbine_release': entry['turbine_release']
                })
    
    # Sort by arrival time
    relevant_entries.sort(key=lambda x: x['arrival_time'])
    
    # Look at the trend over the last few entries
    if len(relevant_entries) >= 3:
        recent_entries = relevant_entries[-3:]
        first_cfs = recent_entries[0]['turbine_release']
        last_cfs = recent_entries[-1]['turbine_release']
        
        # Check for significant change (more than 20% and at least 500 CFS)
        if last_cfs > first_cfs * 1.2 and last_cfs - first_cfs > 500:
            return "rising"
        elif first_cfs > last_cfs * 1.2 and first_cfs - last_cfs > 500:
            return "falling"
        else:
            return "stable"
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
    """Analyze the trend over the past few hours."""
    # Filter to entries within the specified time window
    cutoff_time = current_time - timedelta(hours=hours_back)
    recent_data = [entry for entry in data if entry['date_time'] >= cutoff_time and entry['date_time'] <= current_time]
    
    if not recent_data:
        return "unknown"
    
    # Calculate average and look for significant changes
    cfs_values = [entry['turbine_release'] for entry in recent_data if entry['turbine_release'] is not None]
    if not cfs_values:
        return "unknown"
    
    avg_cfs = sum(cfs_values) / len(cfs_values)
    max_cfs = max(cfs_values)
    min_cfs = min(cfs_values)
    
    # Determine trend
    if max_cfs > avg_cfs * 1.5:
        return "significantly increased"
    elif min_cfs < avg_cfs * 0.5:
        return "significantly decreased"
    elif max_cfs > avg_cfs * 1.2:
        return "moderately increased"
    elif min_cfs < avg_cfs * 0.8:
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
    latest_cfs = latest_entry['turbine_release']
    if latest_cfs is None:
        return "unknown"
    
    travel_time = calculate_travel_time(latest_cfs)
    latest_impact_time = latest_entry['date_time'] + timedelta(hours=travel_time)
    
    # If the latest release hasn't reached White Hole yet
    if latest_impact_time > current_time:
        # Find the entry that's currently affecting White Hole
        # recent_entries is already sorted newest to oldest, so iterate without reversing
        for entry in recent_entries:
            if entry['turbine_release'] is not None:
                entry_travel_time = calculate_travel_time(entry['turbine_release'])
                entry_impact_time = entry['date_time'] + timedelta(hours=entry_travel_time)

                if entry_impact_time <= current_time:
                    current_cfs = entry['turbine_release']

                    # Compare to forecast what's coming
                    if latest_cfs > current_cfs * 1.2 and latest_cfs - current_cfs > 500:
                        return "rising water expected soon"
                    elif current_cfs > latest_cfs * 1.2 and current_cfs - latest_cfs > 500:
                        return "falling water expected soon"
                    else:
                        return "stable conditions expected"

                    break
    
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
    """
    recent_entries = [entry for entry in data
                      if entry['date_time'] <= current_time
                      and entry['turbine_release'] is not None]

    if not recent_entries:
        return []

    recent_entries.sort(key=lambda x: x['date_time'], reverse=True)

    timeline = []
    current_found = False

    for entry in recent_entries[:6]:  # Look at last 6 entries
        cfs = entry['turbine_release']
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
