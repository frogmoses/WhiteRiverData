from datetime import datetime, timedelta
from data_fetcher import (
    get_bull_shoals_data, DAM_TIMEZONE,
    save_last_good_data, load_last_good_data, OUTAGE_FETCH_FAILED
)
from forecast_fetcher import get_swpa_forecast
from water_calculator import (
    calculate_travel_time, front_travel_time, flows_with_previous, release_time,
    determine_water_state, get_fishing_condition,
    get_recent_trend, forecast_conditions, calculate_timeline,
    calculate_forecast_timeline, get_flow
)
from formatters import (
    generate_html_summary, generate_error_html, save_html_summary,
    generate_text_summary, include_chart_in_html,
    generate_schedule_only_html, generate_schedule_only_text, outage_sentence
)
from chart_generator import generate_vertical_river_chart
from fishing_report import generate_fishing_report, render_fishing_report_html
from water_quality import get_water_quality
from release_outlook import get_release_outlook
from prediction_log import build_prediction_row, append_prediction, PREDICTION_LOG_FILE

# Warn on the page when the newest dam reading is older than this many hours
# (the USACE feed normally updates hourly but sometimes stalls)
STALE_DATA_HOURS = 3

# When the live fetch fails, fall back to the last successful fetch — but only
# if its newest reading is within this window; beyond it the error page is
# more honest than day-old conditions
MAX_CACHE_AGE_HOURS = 24


def _is_error_data(data):
    """True for the error sentinel returned by data_fetcher on fetch failure."""
    return len(data) == 1 and data[0].get('error', False)


def _outage_reason(data):
    """Why this run has no readings, from the sentinel (None if it has some)."""
    if data and _is_error_data(data):
        return data[0].get('reason', OUTAGE_FETCH_FAILED)
    return None


def _fetch_forecast(current_time, previous_cfs=None):
    """SWPA schedule, arrival-adjusted. Optional: failures return None."""
    try:
        swpa_data = get_swpa_forecast(current_time)
        if swpa_data:
            return calculate_forecast_timeline(
                swpa_data, current_time, previous_cfs=previous_cfs)
    except Exception as e:
        print(f"Warning: Could not fetch SWPA forecast: {e}")
    return None


def _fetch_water_quality(current_time):
    """USGS tailwater temperature / oxygen. Optional: failures return None."""
    try:
        return get_water_quality(current_time)
    except Exception as e:
        print(f"Warning: Could not fetch USGS water quality: {e}")
    return None


def _fetch_release_outlook(current_time):
    """The Corps' days-ahead daily releases. Optional: failures return None."""
    try:
        return get_release_outlook(current_time)
    except Exception as e:
        print(f"Warning: Could not fetch the Corps release outlook: {e}")
    return None


def _scheduled_now(forecast_timeline, current_time):
    """
    The CFS the schedule has running at White Hole now: the last hour whose
    water has already arrived, else the first one on its way. Used only when
    there is no measured flow at all.
    """
    if not forecast_timeline:
        return None
    arrived = [item for item in forecast_timeline
               if item['arrival_time'] <= current_time]
    return (arrived[-1] if arrived else forecast_timeline[0])['cfs']


def generate_white_hole_summary(output_format="text", data=None, dataset_name=None, current_time=None,
                                prediction_log_file=None):
    """
    Generate a summary of current water conditions at White Hole.

    Args:
        output_format (str): Format of the output - "text" or "html"
        data (list, optional): Pre-fetched data. If None, data will be fetched.
        dataset_name (str, optional): Name of the dataset, used for chart filename.
        current_time (datetime, optional): Override for current time. Defaults to now.
        prediction_log_file (str, optional): When given, append this run's
            predictions to that CSV (production only — see prediction_log.py).

    Returns:
        str: Summary in the requested format
    """
    # Get current time in the dam's timezone (Central) so comparisons against
    # the USACE/SWPA timestamps are correct regardless of the host's timezone
    if current_time is None:
        current_time = datetime.now(DAM_TIMEZONE)

    # Get Bull Shoals Dam data if not provided
    if data is None:
        data = get_bull_shoals_data()

    # Live fetch failed — fall back to the cached last successful fetch so an
    # upstream outage degrades to a (possibly stale-flagged) report instead of
    # replacing the whole page with an error
    feed_failed = False
    feed_reason = _outage_reason(data)
    if not data or _is_error_data(data):
        cached = load_last_good_data(
            max_age_hours=MAX_CACHE_AGE_HOURS, current_time=current_time)
        if cached:
            print(f"Warning: no live USACE readings ({feed_reason}); "
                  "using last-good data cache")
            data = cached
            feed_failed = True

    # No readings at all and no cache worth showing. The schedule, the gauges
    # and the fishing report do not depend on a dam reading, so serve those
    # with the outage stated instead of replacing the page with an error
    # (added 2026-10-03, when Bull Shoals published dashes for 36 h straight).
    if not data or _is_error_data(data):
        forecast_timeline = _fetch_forecast(current_time)
        water_quality = _fetch_water_quality(current_time)
        release_outlook = _fetch_release_outlook(current_time)
        scheduled_cfs = _scheduled_now(forecast_timeline, current_time)

        if scheduled_cfs is None:
            # Both feeds down: there is genuinely nothing to say
            message = (f"Unable to retrieve data from Bull Shoals Dam. "
                       f"{outage_sentence(feed_reason)} The SWPA generation "
                       f"schedule is unavailable too, so no flow can be "
                       f"estimated either.")
            if output_format == "html":
                return generate_error_html(message, current_time)
            return (f"\nWHITE HOLE CURRENT CONDITIONS SUMMARY\n"
                    f"Generated: {current_time.strftime('%Y-%m-%d %H:%M')}\n\n"
                    f"ERROR: {message}\n")

        fishing_report = generate_fishing_report(
            scheduled_cfs, current_time, None, forecast_timeline,
            water_quality=water_quality)

        if output_format == "html":
            return generate_schedule_only_html(
                current_time=current_time,
                forecast_timeline=forecast_timeline,
                scheduled_cfs=scheduled_cfs,
                fishing_report_html=render_fishing_report_html(fishing_report),
                water_quality=water_quality,
                feed_reason=feed_reason,
                release_outlook=release_outlook)
        return generate_schedule_only_text(
            current_time=current_time,
            forecast_timeline=forecast_timeline,
            scheduled_cfs=scheduled_cfs,
            water_quality=water_quality,
            feed_reason=feed_reason,
            release_outlook=release_outlook)

    # Sort data by date_time
    data.sort(key=lambda x: x['date_time'])

    # Find the most recent complete entry
    latest_entry = None
    for entry in reversed(data):
        if get_flow(entry) is not None:
            latest_entry = entry
            break

    if latest_entry is None:
        return "No valid data available for analysis."

    # Flag stale data so the page doesn't present old readings as current
    data_age_hours = (current_time - latest_entry['date_time']).total_seconds() / 3600
    stale_hours = data_age_hours if data_age_hours > STALE_DATA_HOURS else None

    # Calculate which historical entry affects White Hole now
    relevant_entry = None
    for entry, flow, previous in reversed(flows_with_previous(data)):
        travel_time = front_travel_time(flow, previous)
        arrival_time = release_time(entry) + timedelta(hours=travel_time)

        if arrival_time <= current_time:
            relevant_entry = entry
            break

    if relevant_entry is None:
        # Nothing has arrived yet; fall back to the oldest complete entry
        relevant_entry = next(
            (entry for entry in data if get_flow(entry) is not None),
            latest_entry
        )

    # Calculate current conditions at White Hole
    white_hole_cfs = get_flow(relevant_entry)
    water_state = determine_water_state(data, current_time)
    wading_condition, boating_condition = get_fishing_condition(white_hole_cfs)
    recent_trend = get_recent_trend(data, current_time)
    forecast = forecast_conditions(data, current_time)

    # Calculate equivalent number of generators
    # According to explanation.txt, each generator is about 3300 CFS at full capacity
    generators_equivalent = white_hole_cfs / 3300

    # Calculate travel time for the summary
    travel_time = calculate_travel_time(white_hole_cfs)

    # Get the last 12 hours of data for the details section
    twelve_hours_ago = current_time - timedelta(hours=12)

    recent_data = [entry for entry in data
                  if entry['date_time'] >= twelve_hours_ago
                  and get_flow(entry) is not None]

    recent_data.sort(key=lambda x: x['date_time'], reverse=True)

    # Calculate timeline data
    timeline_data = calculate_timeline(data, current_time)

    # SWPA forecast schedule (optional — failures don't break the page). The
    # latest actual reading is the flow ahead of the first scheduled hour, so
    # a scheduled cut right after it reads as a drop.
    forecast_timeline = _fetch_forecast(
        current_time, previous_cfs=get_flow(latest_entry))

    # Tailwater temperature / dissolved oxygen from the USGS gauges
    water_quality = _fetch_water_quality(current_time)

    # The Corps' planned daily releases for the days past SWPA's horizon
    release_outlook = _fetch_release_outlook(current_time)

    # Build the fishing report (full content during trip windows,
    # placeholder otherwise) driven by the flow at White Hole
    fishing_report = generate_fishing_report(
        white_hole_cfs, current_time, timeline_data, forecast_timeline,
        water_quality=water_quality)
    fishing_report_html = render_fishing_report_html(fishing_report)

    if prediction_log_file:
        append_prediction(build_prediction_row(
            current_time, latest_entry, relevant_entry, white_hole_cfs,
            water_state, forecast, timeline_data, forecast_timeline,
            water_quality, feed_failed), prediction_log_file)

    # Format the summary based on requested output format
    if output_format == "html":
        html_content = generate_html_summary(
            current_time=current_time,
            white_hole_cfs=white_hole_cfs,
            generators_equivalent=generators_equivalent,
            water_state=water_state,
            wading_condition=wading_condition,
            boating_condition=boating_condition,
            recent_trend=recent_trend,
            forecast=forecast,
            latest_entry=latest_entry,
            relevant_entry=relevant_entry,
            recent_data=recent_data,
            timeline_data=timeline_data,
            forecast_timeline=forecast_timeline,
            stale_hours=stale_hours,
            feed_failed=feed_failed,
            feed_reason=feed_reason,
            fishing_report_html=fishing_report_html,
            water_quality=water_quality,
            release_outlook=release_outlook,
            units_running=relevant_entry.get('units_running')
        )

        chart_filename = f"vertical_flow_chart_{dataset_name}.png" if dataset_name else "vertical_flow_chart.png"
        chart_path = generate_vertical_river_chart(data, current_time, filename=chart_filename)

        if chart_path:
            html_content = include_chart_in_html(html_content, chart_path)

        return html_content
    else:
        # Text format (default)
        return generate_text_summary(
            current_time=current_time,
            white_hole_cfs=white_hole_cfs,
            generators_equivalent=generators_equivalent,
            water_state=water_state,
            wading_condition=wading_condition,
            boating_condition=boating_condition,
            recent_trend=recent_trend,
            forecast=forecast,
            latest_entry=latest_entry,
            relevant_entry=relevant_entry,
            stale_hours=stale_hours,
            feed_failed=feed_failed,
            feed_reason=feed_reason,
            water_quality=water_quality,
            release_outlook=release_outlook,
            units_running=relevant_entry.get('units_running')
        )

if __name__ == "__main__":
    # Get Bull Shoals Dam data once
    data = get_bull_shoals_data()

    # A successful fetch refreshes the outage-fallback cache (production only:
    # generate_test_html and tests never write it)
    if data and not _is_error_data(data):
        save_last_good_data(data)

    # Generate text summary
    text_summary = generate_white_hole_summary(output_format="text", data=data)
    print(text_summary)

    # Generate HTML report; the production run also logs its predictions
    html_summary = generate_white_hole_summary(
        output_format="html", data=data, prediction_log_file=PREDICTION_LOG_FILE)
    save_html_summary(html_summary, filename="white_hole_conditions.html")
