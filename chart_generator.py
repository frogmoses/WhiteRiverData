import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta
from water_calculator import calculate_travel_time, format_generators


def generate_vertical_river_chart(data, current_time, filename="vertical_flow_chart.png"):
    """
    Generate a vertical river chart showing water flow progression with clear
    distinction between different water releases traveling downstream.

    Uses color gradient to distinguish older vs newer water and labels each
    point with release time and generator count.
    """
    sorted_data = sorted(data, key=lambda x: x['date_time'])
    valid_data = [entry for entry in sorted_data if entry['turbine_release'] is not None]
    if not valid_data:
        print("No valid data found for vertical chart generation")
        return None

    # Define the points (miles from dam)
    points = [0, 1, 2, 3, 4, 5, 6, 7]
    point_labels = ["Bull Shoals Dam", "White River State Park", "Copper John's", "Cane Island",
                    "Gaston's", "The Honey Hole", "a big island", "The White Hole"]

    # For each point, find which release's water is currently there
    flows_at_points = []
    release_times = []
    release_hours_ago = []

    for mile in points:
        relevant_entry = None
        relevant_release_time = None

        # Find the most recent release whose water has arrived at this point
        for entry in reversed(valid_data):
            if mile == 0:
                # At the dam, show the latest release
                relevant_entry = entry
                relevant_release_time = entry['date_time']
                break
            else:
                travel_time_hours = calculate_travel_time(entry['turbine_release']) * (mile / 7)
                arrival_time = entry['date_time'] + timedelta(hours=travel_time_hours)
                if arrival_time <= current_time:
                    relevant_entry = entry
                    relevant_release_time = entry['date_time']
                    break

        if relevant_entry:
            flows_at_points.append(relevant_entry['turbine_release'])
            release_times.append(relevant_release_time)
            hours_ago = (current_time - relevant_release_time).total_seconds() / 3600
            release_hours_ago.append(hours_ago)
        else:
            flows_at_points.append(0)
            release_times.append(None)
            release_hours_ago.append(0)

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
    max_flow = max(flows_at_points) if flows_at_points else 26400
    ax.set_xlim(0, max(26400, max_flow) * 1.35)
    ax.grid(True, axis='x', linestyle='--', alpha=0.5)

    # Title
    ax.set_title(f'Water Flow Progression\nBull Shoals Dam to White Hole\n{current_time.strftime("%Y-%m-%d %H:%M")}',
                 fontsize=14, fontweight='bold')

    # Annotate each point with CFS, generators, and release time
    for i, (flow, release_time, hours) in enumerate(zip(flows_at_points, release_times, release_hours_ago)):
        gen_str = format_generators(flow)

        if i == 0:
            # Dam - show as "Current Release"
            annotation = f"{flow:,} CFS\n({gen_str})\nCurrent Release"
        elif i == len(points) - 1:
            # White Hole - show release time prominently
            if release_time:
                annotation = f"{flow:,} CFS\n({gen_str})\nReleased: {release_time.strftime('%H:%M')}"
            else:
                annotation = f"{flow:,} CFS\n({gen_str})"
        else:
            # Intermediate points - show release time if different from neighbors
            if release_time:
                annotation = f"{flow:,} CFS\n({gen_str})\n{release_time.strftime('%H:%M')}"
            else:
                annotation = f"{flow:,} CFS"

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
             "Water takes 2-4 hours to travel from dam to White Hole depending on flow rate.",
             ha="center", fontsize=9, style='italic')

    plt.tight_layout(rect=[0, 0.04, 1, 0.97])
    plt.savefig(filename, dpi=100, bbox_inches='tight')
    plt.close()
    print(f"Vertical river chart saved to {filename}")
    return filename
