from datetime import datetime, timedelta
from data_fetcher import get_bull_shoals_data
from water_calculator import (
    calculate_travel_time, determine_water_state, get_fishing_condition,
    get_recent_trend, forecast_conditions, calculate_timeline
)
from formatters import (
    generate_html_summary, generate_error_html, save_html_summary,
    generate_text_summary, include_chart_in_html
)
from chart_generator import generate_vertical_river_chart

def generate_white_hole_summary(output_format="text", data=None, dataset_name=None, current_time=None):
    """
    Generate a summary of current water conditions at White Hole.

    Args:
        output_format (str): Format of the output - "text" or "html"
        data (list, optional): Pre-fetched data. If None, data will be fetched.
        dataset_name (str, optional): Name of the dataset, used for chart filename.
        current_time (datetime, optional): Override for current time. Defaults to now.

    Returns:
        str: Summary in the requested format
    """
    # Get current time
    if current_time is None:
        current_time = datetime.now()

    # Get Bull Shoals Dam data if not provided
    if data is None:
        data = get_bull_shoals_data()

    if not data:
        if output_format == "html":
            return generate_error_html("Unable to retrieve data from Bull Shoals Dam.")
        else:
            return "Unable to retrieve data from Bull Shoals Dam."

    # Check if we got error data
    if len(data) == 1 and data[0].get('error', False):
        error_message = """
ERROR: Unable to retrieve data from Bull Shoals Dam website.
Please try again later or check your internet connection.

The White Hole water conditions cannot be determined at this time.
"""
        if output_format == "html":
            return generate_error_html(error_message, current_time)
        else:
            return f"""
WHITE HOLE CURRENT CONDITIONS SUMMARY
Generated: {current_time.strftime('%Y-%m-%d %H:%M')}

{error_message}
"""

    # Sort data by date_time
    data.sort(key=lambda x: x['date_time'])

    # Find the most recent complete entry
    latest_entry = None
    for entry in reversed(data):
        if entry['turbine_release'] is not None:
            latest_entry = entry
            break

    if latest_entry is None:
        return "No valid data available for analysis."

    # Calculate which historical entry affects White Hole now
    relevant_entry = None
    for entry in reversed(data):
        if entry['turbine_release'] is not None:
            travel_time = calculate_travel_time(entry['turbine_release'])
            arrival_time = entry['date_time'] + timedelta(hours=travel_time)

            if arrival_time <= current_time:
                relevant_entry = entry
                break

    if relevant_entry is None:
        relevant_entry = data[0]  # Use the oldest entry if nothing else is available

    # Calculate current conditions at White Hole
    white_hole_cfs = relevant_entry['turbine_release']
    water_state = determine_water_state(data, current_time, white_hole_cfs)
    wading_condition, boating_condition = get_fishing_condition(white_hole_cfs)
    recent_trend = get_recent_trend(data, current_time)
    forecast = forecast_conditions(data, current_time)

    # Calculate equivalent number of generators
    # According to explanation.txt, each generator is about 3300 CFS at full capacity
    generators_equivalent = white_hole_cfs / 3300

    # Calculate travel time for the summary
    travel_time = calculate_travel_time(relevant_entry['turbine_release'])

    # Get the last 12 hours of data for the details section
    twelve_hours_ago = current_time - timedelta(hours=12)

    recent_data = [entry for entry in data
                  if entry['date_time'] >= twelve_hours_ago
                  and entry['turbine_release'] is not None]

    recent_data.sort(key=lambda x: x['date_time'], reverse=True)

    # Calculate timeline data
    timeline_data = calculate_timeline(data, current_time)

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
            timeline_data=timeline_data
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
            relevant_entry=relevant_entry
        )

if __name__ == "__main__":
    # Get Bull Shoals Dam data once
    data = get_bull_shoals_data()

    # Generate text summary
    text_summary = generate_white_hole_summary(output_format="text", data=data)
    print(text_summary)

    # Generate HTML report
    html_summary = generate_white_hole_summary(output_format="html", data=data)
    save_html_summary(html_summary, filename="white_hole_conditions.html")
