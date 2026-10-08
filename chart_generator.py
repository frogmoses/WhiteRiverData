import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta
from water_calculator import (
    calculate_travel_time, front_travel_time, flows_with_previous, release_time as row_release_time,
    format_generators, get_flow
)
from landmarks import LANDMARK_MILES, WHITE_HOLE_MILE


def generate_vertical_river_chart(data, current_time, filename="vertical_flow_chart.png"):
    """
    Generate a vertical river chart showing water flow progression with clear
    distinction between different water releases traveling downstream.

    Uses color gradient to distinguish older vs newer water and labels each
    point with release time and generator count.
    """
    sorted_data = sorted(data, key=lambda x: x['date_time'])
    valid_data = [entry for entry in sorted_data if get_flow(entry) is not None]
    if not valid_data:
        print("No valid data found for vertical chart generation")
        return None

    # Landmark points (miles from dam), derived from pinned GPS coordinates
    point_labels = [name for name, _ in LANDMARK_MILES]
    points = [mile for _, mile in LANDMARK_MILES]

    # For each point, find which release's water is currently there
    flows_at_points = []
    release_times = []
    release_hours_ago = []
    # When the parcel sitting at each landmark reaches White Hole. This is the
    # bridge between the chart and the arrivals table: the chart is ordered by
    # river mile (dam top, water moving down) so later-arriving water sits
    # HIGHER, while the table is ordered by arrival time so later water sits
    # LOWER. Printing the ETA on each row means the reader never has to
    # translate between the two axes (Brian, 2026-10-04).
    white_hole_etas = []

    for mile in points:
        relevant_entry = None
        relevant_release_time = None

        # Find the most recent release whose water has arrived at this point
        relevant_previous = None
        for entry, flow, previous in reversed(flows_with_previous(valid_data)):
            if mile == 0:
                # At the dam, show the latest release
                relevant_entry, relevant_previous = entry, previous
                relevant_release_time = row_release_time(entry)
                break
            else:
                travel_time_hours = front_travel_time(flow, previous, mile=mile)
                arrival_time = row_release_time(entry) + timedelta(hours=travel_time_hours)
                if arrival_time <= current_time:
                    relevant_entry, relevant_previous = entry, previous
                    relevant_release_time = row_release_time(entry)
                    break

        if relevant_entry:
            flow = get_flow(relevant_entry)
            flows_at_points.append(flow)
            release_times.append(relevant_release_time)
            hours_ago = (current_time - relevant_release_time).total_seconds() / 3600
            release_hours_ago.append(hours_ago)
            # Full-reach travel time from the release, the same model the
            # arrivals table uses, so the two agree to the minute
            white_hole_etas.append(
                relevant_release_time + timedelta(hours=front_travel_time(flow, relevant_previous)))
        else:
            flows_at_points.append(0)
            release_times.append(None)
            release_hours_ago.append(0)
            white_hole_etas.append(None)

    # Create the chart
    fig, ax = plt.subplots(figsize=(8, 10))
    y_pos = np.arange(len(points))

    # Create high-contrast colors based on release time
    # Group by release time - same release gets same color
    unique_releases = sorted(set(release_hours_ago))
    # Color palette: dark blue -> medium blue -> light blue/gray (high contrast)
    color_palette = [
        '#1a365d',  # Dark navy (newest)
        '#2b6cb0',  # Medium blue
        '#63b3ed',  # Light blue
        '#a0aec0',  # Gray-blue
        '#cbd5e0',  # Light gray (oldest)
    ]

    colors = []
    for hours in release_hours_ago:
        # Find index of this release in unique releases
        idx = unique_releases.index(hours)
        # Map to color palette (capped at palette length)
        color_idx = min(idx, len(color_palette) - 1)
        colors.append(color_palette[color_idx])

    # Plot each point with its color
    for i, (flow, y, color) in enumerate(zip(flows_at_points, y_pos, colors)):
        ax.barh(y, flow, color=color, height=0.6, edgecolor='#1a365d', linewidth=1.5)

    # Add a line connecting the points
    ax.plot(flows_at_points, y_pos, 'o-', color='#1a365d', linewidth=2, markersize=8, zorder=5)

    # Set y-ticks
    ax.set_yticks(y_pos)
    ax.set_yticklabels(point_labels)
    ax.invert_yaxis()

    ax.set_xlabel('Flow (CFS)', fontsize=12)
    # Scale the axis to the data (with headroom for the annotation boxes and
    # a floor so tiny min-flow days don't over-zoom) instead of always
    # spanning to 8+ generators, which rendered typical low-flow days as
    # unreadable slivers
    max_flow = max(flows_at_points) if flows_at_points else 26400
    ax.set_xlim(0, max(max_flow * 1.5, 5000))
    ax.grid(True, axis='x', linestyle='--', alpha=0.5)

    # Title
    ax.set_title(f'Water Flow Progression\nBull Shoals Dam to White Hole\n{current_time.strftime("%Y-%m-%d %H:%M")}',
                 fontsize=14, fontweight='bold')

    # Annotate each point with CFS, generators, and release time
    for i, (flow, release_time, hours) in enumerate(zip(flows_at_points, release_times, release_hours_ago)):
        gen_str = format_generators(flow)
        eta = white_hole_etas[i]
        if i == len(points) - 1:
            eta_line = "\nat White Hole now"
        elif eta is None:
            eta_line = ""
        elif eta <= current_time:
            eta_line = "\nat White Hole now"
        else:
            eta_line = f"\nWhite Hole ~{eta.strftime('%-I:%M %p')}"

        if i == 0:
            # Dam - show as "Current Release"
            annotation = f"{flow:,} CFS\n({gen_str})\nCurrent Release{eta_line}"
        elif i == len(points) - 1:
            # White Hole - show release time prominently
            if release_time:
                annotation = f"{flow:,} CFS\n({gen_str})\nReleased: {release_time.strftime('%H:%M')}{eta_line}"
            else:
                annotation = f"{flow:,} CFS\n({gen_str}){eta_line}"
        else:
            # Intermediate points - show release time if different from neighbors
            if release_time:
                annotation = f"{flow:,} CFS\n({gen_str})\n{release_time.strftime('%H:%M')}{eta_line}"
            else:
                annotation = f"{flow:,} CFS{eta_line}"

        # Position annotation to the right of the bar
        ax.annotate(annotation, (flow + 200, y_pos[i]), va='center', fontsize=9,
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.9))

    # Add legend explaining the color gradient
    ax.text(0.98, 0.02, "Darker bars = more recent releases\nLighter bars = older releases",
            transform=ax.transAxes, fontsize=9, ha='right', va='bottom',
            bbox=dict(boxstyle="round,pad=0.4", fc="#f0f4f8", ec="gray", alpha=0.9))

    # Footer
    fig.text(0.5, 0.01,
             "Each bar shows the flow rate of water currently at that location.\n"
             "Water takes about 1.5-4 hours to travel from dam to White Hole depending on flow rate.",
             ha="center", fontsize=9, style='italic')

    plt.tight_layout(rect=[0, 0.04, 1, 0.97])
    plt.savefig(filename, dpi=100, bbox_inches='tight')
    plt.close()
    print(f"Vertical river chart saved to {filename}")
    return filename
