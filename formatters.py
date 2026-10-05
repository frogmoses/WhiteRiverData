from datetime import datetime, timedelta
from water_calculator import (
    calculate_travel_time, format_generators, calculate_timeline,
    get_fishing_condition, get_flow, find_incoming_change, clock, group_forecast_runs
)
from water_quality import (
    describe as describe_water_quality, dam_line as dam_water_line, STALE_READING_HOURS
)
from release_outlook import describe as describe_release_outlook
from fishing_report import light_windows_for

from landmarks import LANDMARK_COORDS

# Mirrors data_fetcher.OUTAGE_NO_DATA_PUBLISHED. Kept as a literal so this
# module stays free of the Playwright import chain; tests/test_formatters.py
# asserts the two never drift apart.
OUTAGE_NO_DATA_PUBLISHED = "no_data_published"


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
    source = water_quality["site_label"]
    if water_quality.get("site"):
        source = (f'<a href="https://waterdata.usgs.gov/monitoring-location/USGS-{water_quality["site"]}/" '
                  f'target="_blank" style="color: #718096;">{source}</a>')
    dam = dam_water_line(water_quality, _dam_reading_time(water_quality, current_time))
    dam_html = (f'\n        <p style="color: #4a5568; font-size: 0.9em; margin: 6px 0 0;">{dam}</p>'
                if dam else "")
    return f'''
        <div class="condition-pills" style="margin-top: 12px;">{"".join(pills)}</div>
        <p style="color: #718096; font-size: 0.85em; margin: 6px 0 0;">Tailwater {source}, {when}</p>{dam_html}'''


def _dam_reading_time(water_quality, current_time):
    """Clock time of the reading at the dam riding on water_quality, or None."""
    dam = (water_quality or {}).get("dam")
    return clock(dam["observed"], current_time) if dam else None


def water_quality_text(water_quality, current_time):
    """Temperature, oxygen and at-the-dam lines for the text summaries."""
    temp_line, do_line = describe_water_quality(water_quality)
    dam = dam_water_line(water_quality, _dam_reading_time(water_quality, current_time))
    return "".join(f"{line}\n" for line in (temp_line, do_line, dam) if line)


# Mirrors data_fetcher.TURBINE_COUNT (same reason as the outage literal above)
TURBINE_COUNT = 8


def units_running_label(units):
    """'3 of 8 units running' for a measured hour, or '' when unknown."""
    if units is None:
        return ""
    return f"{units} of {TURBINE_COUNT} units running"


def generate_release_outlook_html(outlook):
    """The Corps' days-ahead release line under the arrivals table ('' if none)."""
    days_line, context = describe_release_outlook(outlook)
    if not days_line:
        return ""
    return f'''
    <div class="release-outlook" style="margin: 12px 0; padding: 10px 14px; background: #f7fafc; border-left: 4px solid #805ad5; border-radius: 6px;">
        <p style="margin: 0;"><strong>Days ahead</strong> — Corps planned release: {days_line}</p>
        <p style="color: #718096; font-size: 0.85em; margin: 6px 0 0;">{context}</p>
    </div>'''


def release_outlook_text(outlook):
    """The same line for the text summaries ('' if none)."""
    days_line, context = describe_release_outlook(outlook)
    if not days_line:
        return ""
    return f"Days ahead (Corps planned release): {days_line}. {context}\n"


def outage_headline(reason):
    """The banner headline for an outage, by its reason (data_fetcher)."""
    if reason == OUTAGE_NO_DATA_PUBLISHED:
        return "DAM TELEMETRY OUT"
    return "LIVE DAM FEED UNAVAILABLE"


# USACE Little Rock District. The district site names this address itself —
# "For website corrections, write to ceswl-pa@usace.army.mil" — and a table of
# dashes is a website correction; Public Affairs routes it to Water Management.
# Email leads because the water-control site's own (501) 324-6231 does not
# connect (Brian tried it, 2026-10-04); 324-6235 is the Water Management team's
# published number. The Corps publishes the release table, USGS only runs the
# temperature/oxygen gauges, so a blank table reported to USGS reaches the wrong
# agency — which is where Brian wrote first, the page having told him nothing.
USACE_EMAIL = "ceswl-pa@usace.army.mil"
USACE_WM_PHONE = "(501) 324-6235"
USACE_WM_TEL = "+15013246235"


def outage_action(reason, last_reading_time=None):
    """
    What the reader can do about this outage, or None when there is nothing.

    Only the telemetry case gets one: dashes in the Corps' table are theirs to
    fix and reporting it is the only lever a reader has. A failed fetch is ours.
    """
    if reason != OUTAGE_NO_DATA_PUBLISHED:
        return None
    since = ""
    if last_reading_time is not None:
        since = f" (nothing since {last_reading_time.strftime('%a %b %d, %-I:%M %p')})"
    return (f"Worth reporting: email USACE Little Rock at {USACE_EMAIL} \u2014 the address "
            f"their own site gives for website corrections \u2014 or Water Management on "
            f"{USACE_WM_PHONE}. Tell them the Bull Shoals hourly table is publishing "
            f"\u2014\u2014\u2014\u2014 in every column{since}. Not USGS: they run the "
            f"temperature and oxygen gauges, not the release table.")


def _with_tel_link(text):
    """Make the email and phone number in an action line tappable."""
    link = 'style="color: inherit; font-weight: 600;"'
    return (text
            .replace(USACE_EMAIL,
                     f'<a href="mailto:{USACE_EMAIL}?subject=Bull%20Shoals%20hourly%20data'
                     f'%20table%20blank" {link}>{USACE_EMAIL}</a>')
            .replace(USACE_WM_PHONE,
                     f'<a href="tel:{USACE_WM_TEL}" {link}>{USACE_WM_PHONE}</a>'))


def outage_sentence(reason):
    """One sentence saying what is broken and whose problem it is."""
    if reason == OUTAGE_NO_DATA_PUBLISHED:
        return ("The USACE page is up, but Bull Shoals is publishing no readings \u2014 "
                "every row in its table is blank. Nothing here can fix that; it comes "
                "back when the Corps' telemetry does.")
    return ("The USACE page could not be reached, so there are no dam readings "
            "this run. Retried automatically every hour.")


def _effective_time(row):
    """When a row starts to matter at White Hole: the start of a drop, else arrival."""
    if is_recession(row):
        return row['recession_start']
    return row['arrival_time']


def arrival_rows(timeline_data, forecast_timeline, current_time):
    """
    The water headed for White Hole as one list keyed on arrival there.

    The row for the water at White Hole now comes first; everything that has
    already passed is dropped (the chart shows what is where). Measured
    readings ('released 7:00 AM') and scheduled hours ('scheduled 2 PM')
    interleave by arrival time; a scheduled hour the dam has already reported
    is dropped in favour of the reading. Each row: kind ('now' | 'actual' |
    'scheduled'), cfs, generators, wading, arrival_time, change,
    recession_start, source (the dam-side label).
    """
    rows = []
    for item in timeline_data or []:
        if item['status'] == 'arrived':
            continue
        rows.append({
            'kind': 'now' if item['status'] == 'current' else 'actual',
            'cfs': item['cfs'],
            'generators': item['generators'],
            'units_running': item.get('units_running'),
            'wading': get_fishing_condition(item['cfs'])[0],
            'arrival_time': item['arrival_time'],
            'change': item.get('change'),
            'recession_start': item.get('recession_start'),
            'minutes_until': item.get('minutes_until'),
            'source': f"released {clock(item['release_time'], current_time)}",
        })
    # A measured reading trumps the schedule for its hour: once the dam has
    # reported 10:00, the "scheduled 10 AM" row only contradicts it
    measured_through = max((item['release_time'] for item in timeline_data or []), default=None)
    pending = [entry for entry in forecast_timeline or []
               if measured_through is None or entry['scheduled_time'] > measured_through]
    for run in group_forecast_runs(pending):
        start_str = clock(run['start_time'], current_time, minutes=False)
        if run['hours'] == 1:
            when = start_str
        else:
            when = f"{start_str}–{clock(run['end_time'], run['start_time'], minutes=False)}"
        rows.append({
            'kind': 'scheduled',
            'cfs': run['cfs'],
            'generators': run['generators'],
            'wading': run['wading'],
            'arrival_time': run['arrival_time'],
            'change': run['change'],
            'recession_start': run['recession_start'],
            'minutes_until': None,
            'source': f"scheduled {when}",
        })
    now_rows = [r for r in rows if r['kind'] == 'now']
    future = sorted((r for r in rows if r['kind'] != 'now'), key=_effective_time)
    return now_rows + future


WADING_PILL = {
    "no wading": ("#fee2e2", "#991b1b"),
    "excellent wading": ("#d1fae5", "#065f46"),
}


def render_arrivals(rows, current_time, wading_condition, has_forecast):
    """The Arrivals at White Hole table."""
    body = []
    last_date = current_time.date()
    for row in rows:
        when = _effective_time(row) if row['kind'] != 'now' else current_time
        if when.date() != last_date:
            last_date = when.date()
            body.append(f'''
                    <tr><td colspan="3" style="padding: 6px 10px; font-size: 0.8em; font-weight: bold; color: #4a5568; background-color: #edf2f7;">{when.strftime('%A')}</td></tr>
            ''')

        arrival = clock(row['arrival_time'], current_time)
        if row['kind'] == 'now':
            when_html = (f'<span style="color: #319795; font-weight: bold;">AT WHITE HOLE NOW</span>'
                         f'<br><small style="color: #666;">since ~{arrival}</small>')
        elif is_recession(row):
            start = row['recession_start']
            if start <= current_time:
                when_html = f'falling now, down ~{arrival}'
            else:
                when_html = f'falling ~{clock(start, current_time)}, down ~{arrival}'
        else:
            when_html = f'~{arrival}'
            if row['minutes_until'] is not None:
                when_html += f'<br><small style="color: #666;">in {row["minutes_until"]} min</small>'

        bg, color = WADING_PILL.get(row['wading'], ("#fef3c7", "#92400e"))
        pill = (f'<span style="display: inline-block; margin-top: 4px; padding: 2px 8px; border-radius: 12px; '
                f'font-size: 0.8em; background-color: {bg}; color: {color};">{row["wading"].title()}</span>')

        row_border = ""
        if row['kind'] != 'now':
            if row['wading'] == "no wading" and wading_condition != "no wading":
                row_border = "border-left: 4px solid #e53e3e;"
            elif row['wading'] == "excellent wading" and wading_condition != "excellent wading":
                row_border = "border-left: 4px solid #38a169;"

        row_bg = {'now': '#e6fffa', 'actual': '#ebf8ff', 'scheduled': '#faf5ff'}[row['kind']]
        source_color = '#6b46c1' if row['kind'] == 'scheduled' else '#2b6cb0'
        units = units_running_label(row.get('units_running'))
        units_html = f'<br><small style="color: #666;">{units}</small>' if units else ""
        body.append(f'''
                    <tr style="background-color: {row_bg}; {row_border}">
                        <td style="padding: 10px; font-weight: bold;">{when_html}</td>
                        <td style="padding: 10px;">{row['cfs']:,} CFS<br><small style="color: #666;">({row['generators']})</small>{units_html}<br>{pill}</td>
                        <td style="padding: 10px; color: {source_color};">{row['source']}</td>
                    </tr>
        ''')

    note = ""
    if has_forecast:
        note = '''
            <p style="color: #999; font-size: 0.8em; margin-top: 10px;">Scheduled CFS are estimates based on generation plus ~250 CFS minimum base flow. Actual release may vary. Tomorrow's schedule appears once SWPA posts it (usually by 5 PM). Falling water arrives as a window, not a step — "falling" is when the level starts dropping, "down" when it is fully down.</p>
            <p style="color: #999; font-size: 0.8em; margin-top: 5px;">Forecast source: <a href="https://www.energy.gov/swpa/generation-schedules" target="_blank" style="color: #999;">SWPA Generation Schedules</a></p>
        '''

    return f'''
        <div class="timeline-box">
            <h3>Arrivals at White Hole</h3>
            <p style="color: #666; margin-bottom: 15px;">The water on its way to you, in the order it gets here. <span style="color: #2b6cb0;">Released</span> rows are the dam's hourly readings; <span style="color: #6b46c1;">scheduled</span> rows are SWPA's generation plan. Water takes about 1.5&ndash;4 hours to travel from the dam, faster at higher flows &mdash; the chart below shows where each release is right now.</p>
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="border-bottom: 2px solid #ddd;">
                        <th style="padding: 10px; text-align: left;">At White Hole</th>
                        <th style="padding: 10px; text-align: left;">Flow</th>
                        <th style="padding: 10px; text-align: left;">From the dam</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(body)}
                </tbody>
            </table>
            {note}
        </div>
        '''


def page_css(banner_color, banner_text_color, wading_condition, boating_condition):
    """
    The page stylesheet, shared by every full page this module renders.

    One copy on purpose: the schedule-only page used to carry its own cut-down
    sheet and silently lost the rules the water-quality pills and the fishing
    report depend on (run-on pill text, no box round the report — Brian,
    2026-10-04). Only the banner colours and the two condition pills vary.
    """
    return f'''
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
'''


def generate_html_summary(current_time, white_hole_cfs, generators_equivalent, water_state,
                           wading_condition, boating_condition, recent_trend, forecast, latest_entry,
                           relevant_entry, recent_data=None, timeline_data=None, forecast_timeline=None,
                           stale_hours=None, feed_failed=False, fishing_report_html="",
                           water_quality=None, feed_reason=None, release_outlook=None,
                           units_running=None):
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
    units = units_running_label(units_running)
    units_html = (f'<div class="generator-display">{units} at the dam when this water left</div>'
                  if units else "")

    # Feed-outage banner (shown when the live USACE fetch failed and the page
    # is being served from the last-good-data cache)
    feed_failed_banner_html = ""
    if feed_failed:
        action = outage_action(feed_reason, latest_entry.get('date_time'))
        action_html = (f'<div style="font-weight: 400; font-size: 0.9em; margin-top: 8px;">'
                       f'{_with_tel_link(action)}</div>') if action else ""
        feed_failed_banner_html = f'''
    <div style="background-color: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; border-radius: 12px; padding: 15px 25px; margin-bottom: 20px; font-weight: 500;">
        ⚠️ {outage_headline(feed_reason)} — Showing the last readings retrieved before it stopped. Conditions may have changed since.{action_html}
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

    # Arrivals at White Hole: one list of the water on its way to the reader,
    # in the order it gets there, measured and scheduled rows interleaved
    water_timeline_html = ""
    rows = arrival_rows(timeline_data, forecast_timeline, current_time)
    if rows:
        water_timeline_html = render_arrivals(rows, current_time, wading_condition,
                                              has_forecast=bool(forecast_timeline))

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
{page_css(banner_color, banner_text_color, wading_condition, boating_condition)}
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
        {units_html}
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
    {generate_release_outlook_html(release_outlook)}

    <!-- CHART PLACEHOLDER -->
    <div class="chart-section">
        <h3>Water Flow Progression</h3>
        <p style="color: #666;">Chart shows water traveling from Bull Shoals Dam to White Hole</p>
        <p style="color: #666; font-size: 0.9em; margin-top: -6px;">Dam at the top, White Hole at the
           bottom &mdash; water moves <em>down</em> the chart, so a bar above White Hole is still on its
           way. Each bar carries the time that water reaches White Hole, which is the order the
           arrivals table above lists them in.</p>
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


def generate_schedule_only_html(current_time, forecast_timeline, scheduled_cfs,
                                fishing_report_html="", water_quality=None,
                                feed_reason=None, last_reading_time=None,
                                release_outlook=None):
    """
    The page with no measured flow: an outage banner, what the SWPA schedule
    says the dam is doing, and everything that does not depend on a dam
    reading (temperature/oxygen, light windows, the fishing report).

    Rendered when there are no usable readings AND the last-good cache is gone
    or too old. Every flow figure here is SCHEDULED, never measured, and the
    page says so in the places a reader would otherwise assume a reading.
    """
    wading, boating = get_fishing_condition(scheduled_cfs)
    water_quality_html = generate_water_quality_html(water_quality, current_time)

    sun_html = ""
    light = light_windows_for(current_time)
    if light:
        sun_html = (f'<p style="color: #718096; font-size: 0.9em; margin: 10px 0 0;">'
                    f'\u2600\ufe0f Sunrise {clock(light["sunrise"])} \u00b7 Sunset {clock(light["sunset"])} '
                    f'<small>\u2014 low light: dawn until {clock(light["dawn"][1])}, '
                    f'dusk from {clock(light["dusk"][0])}</small></p>')

    arrivals_html = ""
    rows = arrival_rows([], forecast_timeline, current_time)
    if rows:
        arrivals_html = render_arrivals(rows, current_time, wading, has_forecast=True)

    action = outage_action(feed_reason, last_reading_time)
    action_html = (f'<div style="margin-top: 10px; font-size: 0.95em;">'
                   f'{_with_tel_link(action)}</div>') if action else ""

    last_reading_html = ""
    if last_reading_time is not None:
        last_reading_html = (f'<p style="color: #718096; font-size: 0.9em;">Last reading the dam '
                             f'published: {last_reading_time.strftime("%a %b %d, %-I:%M %p")} '
                             f'\u2014 too old to show as current.</p>')

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>White Hole Conditions - {current_time.strftime('%Y-%m-%d %H:%M')}</title>
    <style>
{page_css("#991b1b", "white", wading, boating)}
        .scheduled-flow {{ font-size: 2em; font-weight: bold; color: #553c9a; }}
        .tag {{
            display: inline-block;
            background: #ede9fe;
            color: #553c9a;
            border-radius: 6px;
            padding: 2px 8px;
            font-size: 0.75em;
            font-weight: 600;
            letter-spacing: 0.04em;
            vertical-align: middle;
        }}
        .outage-banner {{
            background-color: #fee2e2;
            color: #991b1b;
            border: 1px solid #fca5a5;
            border-radius: 12px;
            padding: 20px 25px;
            margin-bottom: 20px;
        }}
        .outage-banner .headline {{ font-weight: 700; font-size: 1.1em; margin-bottom: 6px; }}
    </style>
</head>
<body>
    <h1>White Hole Conditions</h1>
    <p class="subtitle">{current_time.strftime('%A, %B %d, %Y at %-I:%M %p')} Central</p>

    <div class="outage-banner">
        <div class="headline">\u26a0\ufe0f {outage_headline(feed_reason)} \u2014 NO MEASURED FLOW</div>
        <div>{outage_sentence(feed_reason)}</div>
        {action_html}
    </div>

    <div class="current-conditions">
        <h3 style="margin-top: 0;">What the dam is scheduled to run</h3>
        <p><span class="scheduled-flow">{scheduled_cfs:,} CFS</span>
           <span class="tag">SCHEDULED \u2014 NOT MEASURED</span></p>
        <p>{format_generators(scheduled_cfs)} \u00b7 Wading: <strong>{wading}</strong> \u00b7 Boating: <strong>{boating}</strong></p>
        <p style="color: #718096; font-size: 0.9em;">From the SWPA generation schedule, which is still
           publishing. Treat it as the dam's plan, not as the river: a schedule change, a spill, or
           non-power release would not show up here while the readings are out.</p>
        {water_quality_html}
        {sun_html}
        {last_reading_html}
    </div>

    {arrivals_html}
    {generate_release_outlook_html(release_outlook)}

    {fishing_report_html}

    <div class="timestamp">
        Generated {current_time.strftime('%Y-%m-%d %H:%M')} Central \u00b7 schedule from SWPA \u00b7
        readings from USACE Bull Shoals (out)
    </div>
</body>
</html>'''


def generate_schedule_only_text(current_time, forecast_timeline, scheduled_cfs,
                                water_quality=None, feed_reason=None,
                                last_reading_time=None, release_outlook=None):
    """The text twin of generate_schedule_only_html."""
    wading, boating = get_fishing_condition(scheduled_cfs)
    wq_text = water_quality_text(water_quality, current_time)
    action = outage_action(feed_reason, last_reading_time)
    action_text = f"{action}\n" if action else ""

    last_reading_text = ""
    if last_reading_time is not None:
        last_reading_text = (f"Last reading the dam published: "
                             f"{last_reading_time.strftime('%Y-%m-%d %H:%M')} (too old to show as current)\n")
    schedule_lines = ""
    for run in group_forecast_runs(forecast_timeline or [])[:6]:
        schedule_lines += (f"- {clock(run['start_time'], current_time, minutes=False)}: "
                           f"{run['cfs']:,} CFS scheduled, at White Hole ~"
                           f"{clock(run['arrival_time'], current_time)}\n")
    return f"""
WHITE HOLE CURRENT CONDITIONS SUMMARY
Generated: {current_time.strftime('%Y-%m-%d %H:%M')}

WARNING: {outage_headline(feed_reason).capitalize()} — no measured flow.
{outage_sentence(feed_reason)}
{action_text}{last_reading_text}
SCHEDULED (not measured), from SWPA:
- Now: {scheduled_cfs:,} CFS, {format_generators(scheduled_cfs)}
- Wading: {wading}
- Boating: {boating}
{schedule_lines}{release_outlook_text(release_outlook)}{wq_text}
"""


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
                         feed_reason=None,
                         water_quality=None, release_outlook=None, units_running=None):
    """Generate a text version of the White Hole summary."""
    units = units_running_label(units_running)
    units_text = f"Units Running: {units} at the dam when this water left\n" if units else ""
    # Calculate travel time for the summary
    travel_time = calculate_travel_time(get_flow(relevant_entry))
    wq_text = water_quality_text(water_quality, current_time)
    stale_warning = ""
    if feed_failed:
        stale_warning += (f"\nWARNING: {outage_headline(feed_reason).capitalize()} — "
                          "showing the last readings retrieved before it stopped.\n")
        action = outage_action(feed_reason, latest_entry.get('date_time'))
        if action:
            stale_warning += f"{action}\n"
    if stale_hours is not None:
        stale_warning += f"\nWARNING: Dam data is delayed — latest reading is {stale_hours:.1f} hours old.\n"
    summary = f"""
WHITE HOLE CURRENT CONDITIONS SUMMARY
Generated: {current_time.strftime('%Y-%m-%d %H:%M')}
{stale_warning}
Current Flow: Approximately {white_hole_cfs} CFS
Equivalent Generators: {generators_equivalent:.1f} at full capacity
{units_text}Water State: {water_state.title()}
Wading Conditions: {wading_condition.title()}
Boating Conditions: {boating_condition.title()}

Over the past 6 hours, dam releases have {recent_trend}.
Looking ahead: {forecast.capitalize()}.
{release_outlook_text(release_outlook)}{wq_text}
CALCULATION DETAILS:
- Latest dam reading: {get_flow(latest_entry)} CFS at {latest_entry['date_time'].strftime('%Y-%m-%d %H:%M')}
- Travel time to White Hole: {travel_time:.1f} hours at {white_hole_cfs} CFS
- White Hole conditions based on dam reading from: {relevant_entry['date_time'].strftime('%Y-%m-%d %H:%M')}
"""
    return summary
