from datetime import datetime, timedelta
from water_calculator import (
    calculate_travel_time, format_generators, calculate_timeline,
    get_fishing_condition, get_flow, find_incoming_change, clock
)
from water_quality import describe as describe_water_quality, STALE_READING_HOURS
from fishing_report import light_windows_for

from landmarks import LANDMARK_COORDS


def generate_landmark_map_links():
    """Clickable map pins for the chart's landmarks, dam to White Hole."""
    links = " · ".join(
        f'<a href="https://www.google.com/maps?q={lat},{lon}" target="_blank" '
        f'style="color: #2b6cb0; text-decoration: none;">{name}</a>'
        for name, (lat, lon) in LANDMARK_COORDS
    )
    return (f'<p style="color: #666; font-size: 0.85em; margin-top: 10px;">'
            f'📍 Tap a landmark for its map pin: {links}</p>')


def include_chart_in_html(html_content, chart_path):
    """
    Include the flow chart in the HTML content.
    Inserts the chart into the chart-container div.
    """
    chart_img = f'<img src="{chart_path}" alt="Water Flow Progression Chart" style="max-width: 100%; height: auto; border-radius: 8px;">'

    # Replace the chart placeholder comment
    return html_content.replace(
        '<!-- Chart will be inserted here -->',
        chart_img
    )


def generate_table_rows(data):
    """Generate HTML table rows for the dam readings."""
    rows = []
    for entry in data:
        flow = get_flow(entry)
        row = f"""
                <tr style="border-bottom: 1px solid #eee;">
                    <td style="padding: 8px;">{entry['date_time'].strftime('%Y-%m-%d %H:%M')}</td>
                    <td style="padding: 8px; text-align: right;">{flow}</td>
                    <td style="padding: 8px; text-align: right;">{flow/3300:.1f}</td>
                    <td style="padding: 8px; text-align: right;">{calculate_travel_time(flow):.1f}</td>
                </tr>
                """
        rows.append(row)
    return ''.join(rows)


# A drop whose recession window is shorter than this renders as a single
# arrival time — the window is real but not worth two clock readings
MIN_RECESSION_WINDOW = timedelta(minutes=10)


def is_recession(item):
    """True when a timeline item is a drop with a window worth showing."""
    start = item.get('recession_start')
    return (item.get('change') == 'falling' and start is not None
            and item['arrival_time'] - start >= MIN_RECESSION_WINDOW)


WQ_PILL_STYLES = {
    "low": ("#fee2e2", "#991b1b"), "hot": ("#fee2e2", "#991b1b"),
    "marginal": ("#fef3c7", "#92400e"), "warm": ("#fef3c7", "#92400e"),
    "cold": ("#dbeafe", "#1e40af"),
    "good": ("#d1fae5", "#065f46"), "prime": ("#d1fae5", "#065f46"),
}


def generate_water_quality_html(water_quality, current_time):
    """Temperature and oxygen pills with their verdicts; '' when no reading."""
    temp_line, do_line = describe_water_quality(water_quality)
    if not temp_line and not do_line:
        return ""

    pills = []
    for line, status in ((temp_line, water_quality["temp_status"]),
                         (do_line, water_quality["do_status"])):
        if not line:
            continue
        bg, color = WQ_PILL_STYLES.get(status, ("#edf2f7", "#2d3748"))
        value, verdict = line.split(" — ", 1)
        pills.append(
            f'<span class="pill" style="background-color: {bg}; color: {color};">'
            f'{value} <small>— {verdict}</small></span>')

    age = water_quality.get("age_hours")
    observed = clock(water_quality["observed"], current_time)
    if age is not None and age > STALE_READING_HOURS:
        when = f"reading is {age:.1f} h old ({observed})"
    else:
        when = f"as of {observed}"
    source = (f'<a href="https://waterdata.usgs.gov/monitoring-location/USGS-{water_quality["site"]}/" '
              f'target="_blank" style="color: #718096;">{water_quality["site_label"]}</a>')
    return f'''
        <div class="condition-pills" style="margin-top: 12px;">{"".join(pills)}</div>
        <p style="color: #718096; font-size: 0.85em; margin: 6px 0 0;">Tailwater {source}, {when}</p>'''


def group_forecast_runs(forecast_timeline):
    """
    Collapse consecutive scheduled hours at the same CFS into runs so the
    whole remaining schedule fits on the page. Each run carries the first
    hour's arrival/recession times (when that level reaches White Hole) and
    the span it covers.
    """
    runs = []
    for item in forecast_timeline:
        if runs and runs[-1]['cfs'] == item['cfs']:
            runs[-1]['end_time'] = item['scheduled_time'] + timedelta(hours=1)
            runs[-1]['hours'] += 1
            continue
        runs.append({
            'start_time': item['scheduled_time'],
            'end_time': item['scheduled_time'] + timedelta(hours=1),
            'hours': 1,
            'cfs': item['cfs'],
            'generators': item['generators'],
            'generation_cfs': item.get('generation_cfs', item['cfs']),
            'min_flow_cfs': item.get('min_flow_cfs', 0),
            'wading': item['wading'],
            'arrival_time': item['arrival_time'],
            'change': item.get('change'),
            'recession_start': item.get('recession_start'),
        })
    return runs


def generate_html_summary(current_time, white_hole_cfs, generators_equivalent, water_state,
                           wading_condition, boating_condition, recent_trend, forecast, latest_entry,
                           relevant_entry, recent_data=None, timeline_data=None, forecast_timeline=None,
                           stale_hours=None, feed_failed=False, fishing_report_html="",
                           water_quality=None):
    """
    Generate HTML summary with headline banner, timeline, and reorganized layout.

    Prioritizes actionable information:
    1. Headline banner answering "Can I wade?" and "Is water coming?"
    2. Current conditions at White Hole
    3. Timeline showing water progression
    4. Chart and details (collapsible)
    """

    # Determine banner color and message based on conditions
    if wading_condition == "no wading":
        banner_color = "#1a365d"  # Dark blue - high water
        banner_text_color = "white"
        wading_message = "NO WADING — Water too high for safe wading"
        wading_icon = "🚫"
    elif wading_condition == "still wadable":
        banner_color = "#2b6cb0"  # Medium blue - caution
        banner_text_color = "white"
        wading_message = "MARGINAL WADING — Use caution"
        wading_icon = "⚠️"
    else:
        banner_color = "#319795"  # Teal - good conditions
        banner_text_color = "white"
        wading_message = "GOOD WADING — Conditions favorable"
        wading_icon = "✅"

    # Determine forecast message. The ETA must come from the incoming plug
    # that actually changes the level — the nearest incoming reading is
    # often a same-level plug ahead of the real rise or drop.
    direction, change_item = find_incoming_change(timeline_data, white_hole_cfs)
    if "rising" in forecast.lower():
        if direction == "rising" and change_item['minutes_until'] is not None:
            forecast_message = (f"RISING WATER arriving in ~{change_item['minutes_until']} minutes "
                                f"({change_item['cfs']:,} CFS)")
        else:
            forecast_message = "RISING WATER expected soon"
        forecast_icon = "⏱️"
    elif "falling" in forecast.lower():
        if direction == "falling":
            down_at = clock(change_item['arrival_time'], current_time)
            start = change_item.get('recession_start')
            if not is_recession(change_item):
                forecast_message = f"FALLING WATER — arrives ~{down_at}"
            elif start <= current_time:
                forecast_message = f"FALLING WATER — dropping now, fully down ~{down_at}"
            else:
                forecast_message = (f"FALLING WATER — starts dropping ~{clock(start, current_time)}, "
                                    f"fully down ~{down_at}")
        else:
            forecast_message = "FALLING WATER — Conditions improving"
        forecast_icon = "📉"
    else:
        forecast_message = "STABLE CONDITIONS expected"
        forecast_icon = "➡️"

    # Check SWPA scheduled generation for significant upcoming changes.
    # Scan the whole schedule so an early moderate hour can't mask a later
    # high-water hour; alert on the most severe level scheduled.
    scheduled_alert = ""
    if forecast_timeline:
        high_hour = next((item for item in forecast_timeline
                          if item['cfs'] >= 5000 and white_hole_cfs < 5000), None)
        higher_hour = next((item for item in forecast_timeline
                            if item['cfs'] >= 2000 and white_hole_cfs < 2000), None)
        peak = max(forecast_timeline, key=lambda item: item['cfs'])
        if high_hour is not None:
            scheduled_alert = (f"HIGH WATER SCHEDULED — ~{clock(high_hour['arrival_time'], current_time)}, "
                               f"peaking near {peak['cfs']:,} CFS ({peak['generators']})")
        elif higher_hour is not None:
            scheduled_alert = f"HIGHER WATER SCHEDULED — ~{clock(higher_hour['arrival_time'], current_time)}"

    # Format generators as integer range
    gen_display = format_generators(white_hole_cfs)

    # Feed-outage banner (shown when the live USACE fetch failed and the page
    # is being served from the last-good-data cache)
    feed_failed_banner_html = ""
    if feed_failed:
        feed_failed_banner_html = '''
    <div style="background-color: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; border-radius: 12px; padding: 15px 25px; margin-bottom: 20px; font-weight: 500;">
        ⚠️ LIVE DAM FEED UNAVAILABLE — Showing the last successfully retrieved readings. Conditions may have changed since.
    </div>'''

    # Stale-data warning banner (shown when the USACE feed has stalled)
    stale_banner_html = ""
    if stale_hours is not None:
        stale_banner_html = f'''
    <div style="background-color: #fef3c7; color: #92400e; border: 1px solid #fcd34d; border-radius: 12px; padding: 15px 25px; margin-bottom: 20px; font-weight: 500;">
        ⚠️ DAM DATA DELAYED — The latest reading is {stale_hours:.1f} hours old. Conditions shown may not reflect the river right now.
    </div>'''

    # Tailwater temperature / oxygen block (USGS), omitted when unavailable
    water_quality_html = generate_water_quality_html(water_quality, current_time)

    # Sunrise / sunset and the low-light windows the fishing report keys on
    sun_html = ""
    light = light_windows_for(current_time)
    if light:
        sun_html = (f'<p style="color: #718096; font-size: 0.9em; margin: 10px 0 0;">'
                    f'☀️ Sunrise {clock(light["sunrise"])} · Sunset {clock(light["sunset"])} '
                    f'<small>— low light: dawn until {clock(light["dawn"][1])}, '
                    f'dusk from {clock(light["dusk"][0])}</small></p>')

    # Build unified water timeline (scheduled forecast + actual dam readings)
    water_timeline_html = ""
    has_actual = timeline_data and len(timeline_data) > 0
    has_forecast = forecast_timeline and len(forecast_timeline) > 0

    if has_actual or has_forecast:
        # Build forecast rows: the whole remaining schedule (today's rest and
        # tomorrow once posted), newest first, with consecutive same-flow
        # hours collapsed into one run so the day's shape — and its peak —
        # stays visible instead of four rows of the next four hours
        forecast_rows_html = ""
        if has_forecast:
            forecast_rows = []
            last_date = current_time.date()
            for run in group_forecast_runs(forecast_timeline):
                if run['start_time'].date() != last_date:
                    last_date = run['start_time'].date()
                    forecast_rows.append(f'''
                    <tr><td colspan="3" style="padding: 6px 10px; font-size: 0.8em; font-weight: bold; color: #6b46c1; background-color: #f3e8ff;">{run['start_time'].strftime('%A')}</td></tr>
                ''')
                start_str = clock(run['start_time'], current_time, minutes=False)
                if run['hours'] == 1:
                    hour_str = start_str
                else:
                    hour_str = f"{start_str}–{clock(run['end_time'], run['start_time'], minutes=False)}"
                cfs_formatted = f"{run['cfs']:,}"
                gen_cfs = run['generation_cfs']
                min_flow = run['min_flow_cfs']

                if is_recession(run):
                    arrival_html = (f"falling ~{clock(run['recession_start'], current_time)}, "
                                    f"down ~{clock(run['arrival_time'], current_time)}")
                else:
                    arrival_html = f"~{clock(run['arrival_time'], current_time)}"

                # Determine wading pill style
                if run['wading'] == "no wading":
                    wading_bg = "#fee2e2"
                    wading_color = "#991b1b"
                elif run['wading'] == "excellent wading":
                    wading_bg = "#d1fae5"
                    wading_color = "#065f46"
                else:
                    wading_bg = "#fef3c7"
                    wading_color = "#92400e"

                # Highlight row if conditions differ significantly from current
                row_border = ""
                if run['wading'] == "no wading" and wading_condition != "no wading":
                    row_border = "border-left: 4px solid #e53e3e;"
                elif run['wading'] == "excellent wading" and wading_condition != "excellent wading":
                    row_border = "border-left: 4px solid #38a169;"

                forecast_rows.append(f'''
                    <tr style="background-color: #faf5ff; {row_border}">
                        <td style="padding: 10px; font-weight: bold;">{hour_str}</td>
                        <td style="padding: 10px;">{cfs_formatted} CFS<br><small style="color: #666;">({run['generators']}: {gen_cfs} generation + {min_flow} min flow)</small></td>
                        <td style="padding: 10px;">{arrival_html}
                            <span style="display: inline-block; margin-left: 6px; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; background-color: {wading_bg}; color: {wading_color};">{run['wading'].title()}</span>
                        </td>
                    </tr>
                ''')

            forecast_rows_html = f'''
                <tr><td colspan="3" style="padding: 8px 10px; font-size: 0.8em; font-weight: bold; color: #6b46c1; text-transform: uppercase; letter-spacing: 0.05em; background-color: #f3e8ff;">Scheduled (SWPA forecast)</td></tr>
                {''.join(forecast_rows)}
            '''

        # Build actual data rows (newest first)
        actual_rows_html = ""
        if has_actual:
            actual_rows = []
            for item in timeline_data:
                cfs_formatted = f"{item['cfs']:,}"

                if item['status'] == 'current':
                    status_html = '<span style="color: #319795; font-weight: bold;">← AT WHITE HOLE NOW</span>'
                    row_style = "background-color: #e6fffa;"
                elif item['status'] == 'incoming':
                    arrival_str = clock(item['arrival_time'], current_time)
                    mins = item['minutes_until']
                    start = item.get('recession_start')
                    if is_recession(item):
                        if start <= current_time:
                            status_html = f'<span style="color: #2b6cb0;">↘ Falling now, fully down ~{arrival_str} (in {mins} min)</span>'
                        else:
                            status_html = f'<span style="color: #2b6cb0;">↘ Falls from ~{clock(start, current_time)}, fully down ~{arrival_str}</span>'
                    else:
                        status_html = f'<span style="color: #2b6cb0;">→ Arrives ~{arrival_str} (in {mins} min)</span>'
                    row_style = "background-color: #ebf8ff;"
                else:
                    status_html = '<span style="color: #718096;">passed</span>'
                    row_style = ""

                time_str = item['release_time'].strftime('%I:%M %p').lstrip('0')
                actual_rows.append(f'''
                    <tr style="{row_style}">
                        <td style="padding: 10px; font-weight: bold;">{time_str}</td>
                        <td style="padding: 10px;">{cfs_formatted} CFS<br><small style="color: #666;">({item['generators']})</small></td>
                        <td style="padding: 10px;">{status_html}</td>
                    </tr>
                ''')

            actual_rows_html = f'''
                <tr><td colspan="3" style="padding: 8px 10px; font-size: 0.8em; font-weight: bold; color: #2b6cb0; text-transform: uppercase; letter-spacing: 0.05em; background-color: #ebf8ff;">Actual (dam readings)</td></tr>
                {''.join(actual_rows)}
            '''

        # Footer note if forecast data present
        forecast_note = ""
        if has_forecast:
            forecast_note = '''
            <p style="color: #999; font-size: 0.8em; margin-top: 10px;">Scheduled CFS are estimates based on generation plus ~250 CFS minimum base flow. Actual release may vary. Tomorrow's schedule appears once SWPA posts it (usually by 5 PM). Falling water arrives as a window, not a step — "falling" is when the level starts dropping, "down" when it is fully down.</p>
            <p style="color: #999; font-size: 0.8em; margin-top: 5px;">Forecast source: <a href="https://www.energy.gov/swpa/generation-schedules" target="_blank" style="color: #999;">SWPA Generation Schedules</a></p>
            '''

        water_timeline_html = f'''
        <div class="timeline-box">
            <h3>Water Timeline</h3>
            <p style="color: #666; margin-bottom: 15px;">Water released at the dam takes about 1.5&ndash;4 hours to reach White Hole (faster at higher flows). Oldest at the top: what has passed, what is at White Hole now, what is on the way, then the scheduled hours.</p>
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="border-bottom: 2px solid #ddd;">
                        <th style="padding: 10px; text-align: left;">Time</th>
                        <th style="padding: 10px; text-align: left;">Flow</th>
                        <th style="padding: 10px; text-align: left;">At White Hole</th>
                    </tr>
                </thead>
                <tbody>
                    {actual_rows_html}
                    {forecast_rows_html}
                </tbody>
            </table>
            {forecast_note}
        </div>
        '''

    # Build collapsible details
    details_html = ""
    if recent_data:
        table_rows = generate_table_rows(recent_data)
        details_html = f'''
        <details class="details-section">
            <summary style="cursor: pointer; font-weight: bold; padding: 10px; background: #f7fafc; border-radius: 8px;">
                📊 View Last 12 Hours of Dam Readings
            </summary>
            <div style="padding: 15px;">
                <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
                    <thead>
                        <tr style="background-color: #f2f2f2; border-bottom: 1px solid #ddd;">
                            <th style="padding: 8px; text-align: left;">Date/Time</th>
                            <th style="padding: 8px; text-align: right;">Flow (CFS)</th>
                            <th style="padding: 8px; text-align: right;">Generators</th>
                            <th style="padding: 8px; text-align: right;">Travel Time (hrs)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows}
                    </tbody>
                </table>
            </div>
        </details>
        '''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>White Hole Conditions - {current_time.strftime('%Y-%m-%d %H:%M')}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f7fafc;
        }}
        h1 {{
            color: #2c3e50;
            margin-bottom: 5px;
        }}
        .subtitle {{
            color: #718096;
            margin-bottom: 20px;
        }}
        .headline-banner {{
            background-color: {banner_color};
            color: {banner_text_color};
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .headline-banner .main-status {{
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        .headline-banner .forecast-status {{
            font-size: 18px;
            opacity: 0.95;
        }}
        .current-conditions {{
            background-color: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .current-conditions h3 {{
            margin-top: 0;
            color: #2c3e50;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 10px;
        }}
        .flow-display {{
            font-size: 36px;
            font-weight: bold;
            color: #2b6cb0;
        }}
        .generator-display {{
            font-size: 18px;
            color: #666;
            margin-bottom: 15px;
        }}
        .condition-pills {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .pill {{
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: 500;
        }}
        .pill.wading {{
            background-color: {('#fee2e2' if wading_condition == 'no wading' else '#d1fae5' if wading_condition == 'excellent wading' else '#fef3c7')};
            color: {('#991b1b' if wading_condition == 'no wading' else '#065f46' if wading_condition == 'excellent wading' else '#92400e')};
        }}
        .pill.boating {{
            background-color: {('#dbeafe' if boating_condition == 'ideal boating' else '#fee2e2' if boating_condition == 'high water' else '#fef3c7')};
            color: {('#1e40af' if boating_condition == 'ideal boating' else '#991b1b' if boating_condition == 'high water' else '#92400e')};
        }}
        .timeline-box {{
            background-color: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .timeline-box h3 {{
            margin-top: 0;
            color: #2c3e50;
        }}
        .chart-section {{
            background-color: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .chart-section h3 {{
            margin-top: 0;
            color: #2c3e50;
        }}
        .webcam-link {{
            display: inline-block;
            background-color: #ebf8ff;
            color: #2b6cb0;
            padding: 10px 20px;
            border-radius: 8px;
            border: 1px solid #bee3f8;
            text-decoration: none;
            font-weight: 500;
        }}
        .webcam-link:hover {{
            background-color: #bee3f8;
        }}
        .details-section {{
            background-color: white;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .details-section summary {{
            list-style: none;
        }}
        .details-section summary::-webkit-details-marker {{
            display: none;
        }}
        .timestamp {{
            font-size: 0.85em;
            color: #718096;
            text-align: center;
            margin-top: 20px;
        }}
        @media (max-width: 600px) {{
            .headline-banner .main-status {{
                font-size: 20px;
            }}
            .headline-banner .forecast-status {{
                font-size: 16px;
            }}
            .flow-display {{
                font-size: 28px;
            }}
        }}
    </style>
</head>
<body>
    <h1>White Hole Current Conditions</h1>
    <p class="subtitle">{current_time.strftime('%A, %B %d, %Y at %I:%M %p')}</p>
{feed_failed_banner_html}
{stale_banner_html}
    <!-- HEADLINE BANNER -->
    <div class="headline-banner">
        <div class="main-status">{wading_icon} {wading_message}</div>
        <div class="forecast-status">{forecast_icon} {forecast_message}</div>
        {'<div class="forecast-status" style="margin-top: 5px; opacity: 0.9;">📅 ' + scheduled_alert + '</div>' if scheduled_alert else ''}
    </div>

    <!-- CURRENT CONDITIONS -->
    <div class="current-conditions">
        <h3>Current Conditions at White Hole</h3>
        <div class="flow-display">{white_hole_cfs:,} CFS</div>
        <div class="generator-display">Equivalent to {gen_display}</div>
        <div class="condition-pills">
            <span class="pill wading">{wading_condition.title()}</span>
            <span class="pill boating">{boating_condition.title()}</span>
        </div>
        {sun_html}
        {water_quality_html}
        <a href="https://www.youtube.com/channel/UCAXhb9nFnsfu367AthDrgIA/live" target="_blank" class="webcam-link" style="margin-top: 15px;">
            📹 View Live Webcam
        </a>
    </div>

    <!-- WATER TIMELINE -->
    {water_timeline_html}

    <!-- CHART PLACEHOLDER -->
    <div class="chart-section">
        <h3>Water Flow Progression</h3>
        <p style="color: #666;">Chart shows water traveling from Bull Shoals Dam to White Hole</p>
        <div id="chart-container" style="text-align: center; margin: 20px 0;">
            <!-- Chart will be inserted here -->
        </div>
        {generate_landmark_map_links()}
    </div>

    <!-- COLLAPSIBLE DETAILS -->
    <details class="details-section">
        <summary style="cursor: pointer; font-weight: bold; padding: 15px; background: #f7fafc; border-radius: 8px;">
            📋 Calculation Details
        </summary>
        <div style="padding: 15px;">
            <ul>
                <li>Latest dam reading: {get_flow(latest_entry):,} CFS at {latest_entry['date_time'].strftime('%Y-%m-%d %H:%M')}</li>
                <li>Travel time to White Hole: {calculate_travel_time(get_flow(relevant_entry)):.1f} hours at current flow</li>
                <li>White Hole conditions based on dam reading from: {relevant_entry['date_time'].strftime('%Y-%m-%d %H:%M')}</li>
            </ul>
        </div>
    </details>

    {details_html}

    <!-- FISHING REPORT -->
    {fishing_report_html}

    <div class="timestamp">
        Data retrieved and processed on {current_time.strftime('%Y-%m-%d %H:%M:%S')} (Central time)<br>
        Travel times are observational estimates (per <a href="https://www.hisplaceresort.net/white-river-info" target="_blank" style="color: #718096;">His Place Resort</a>) &mdash; always judge wading safety on-site.<br>
        &copy; {current_time.year} Brian Carroll. All rights reserved.
    </div>
</body>
</html>'''

    return html


def generate_error_html(error_message, current_time=None):
    """Generate an HTML error page."""
    if current_time is None:
        current_time = datetime.now()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>White Hole Conditions - Error</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 2px solid #e74c3c;
            padding-bottom: 10px;
        }}
        .error-box {{
            background-color: #fef0f0;
            border-left: 4px solid #e74c3c;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }}
        .timestamp {{
            font-size: 0.8em;
            color: #7f8c8d;
            text-align: right;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <h1>White Hole Conditions - Error</h1>

    <div class="error-box">
        <p>{error_message}</p>
    </div>

    <div class="timestamp">
        Generated on {current_time.strftime('%Y-%m-%d %H:%M:%S')}
    </div>
</body>
</html>"""

    return html

def save_html_summary(html_content, filename="white_hole_conditions.html"):
    """Save the HTML summary to a file."""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"HTML summary saved to {filename}")
        return True
    except Exception as e:
        print(f"Error saving HTML file: {e}")
        return False

def generate_text_summary(current_time, white_hole_cfs, generators_equivalent, water_state,
                         wading_condition, boating_condition, recent_trend, forecast,
                         latest_entry, relevant_entry, stale_hours=None, feed_failed=False,
                         water_quality=None):
    """Generate a text version of the White Hole summary."""
    # Calculate travel time for the summary
    travel_time = calculate_travel_time(get_flow(relevant_entry))
    temp_line, do_line = describe_water_quality(water_quality)
    water_quality_text = "".join(f"{line}\n" for line in (temp_line, do_line) if line)
    stale_warning = ""
    if feed_failed:
        stale_warning += "\nWARNING: Live dam feed unavailable — showing the last successfully retrieved readings.\n"
    if stale_hours is not None:
        stale_warning += f"\nWARNING: Dam data is delayed — latest reading is {stale_hours:.1f} hours old.\n"
    summary = f"""
WHITE HOLE CURRENT CONDITIONS SUMMARY
Generated: {current_time.strftime('%Y-%m-%d %H:%M')}
{stale_warning}
Current Flow: Approximately {white_hole_cfs} CFS
Equivalent Generators: {generators_equivalent:.1f} at full capacity
Water State: {water_state.title()}
Wading Conditions: {wading_condition.title()}
Boating Conditions: {boating_condition.title()}

Over the past 6 hours, dam releases have {recent_trend}.
Looking ahead: {forecast.capitalize()}.
{water_quality_text}
CALCULATION DETAILS:
- Latest dam reading: {get_flow(latest_entry)} CFS at {latest_entry['date_time'].strftime('%Y-%m-%d %H:%M')}
- Travel time to White Hole: {travel_time:.1f} hours at {white_hole_cfs} CFS
- White Hole conditions based on dam reading from: {relevant_entry['date_time'].strftime('%Y-%m-%d %H:%M')}
"""
    return summary
