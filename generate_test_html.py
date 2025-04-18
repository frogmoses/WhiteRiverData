"""
Generate HTML test files for manual visual inspection.

This script generates HTML and chart files for various water scenarios,
allowing you to visually inspect how the system behaves under different
conditions in a browser.

Usage:
    uv run python generate_test_html.py
"""
from datetime import datetime, timedelta
from main import generate_white_hole_summary
from formatters import save_html_summary


def create_test_data(base_time):
    """Create test datasets for various water conditions."""

    scenarios = {}

    # Normal conditions - steady flow around 6600 CFS (2 generators)
    scenarios['normal'] = [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': 6600,
         'elevation': 654.0,
         'tailwater': 450.0,
         'generation': 100,
         'spillway_release': 0,
         'total_release': 6600}
        for i in range(24, 0, -1)
    ]

    # Rising water - increasing from 3300 to 26400 CFS over 6 hours
    # Water takes 1.6-3.7 hours to reach White Hole, so 6 hours shows transition
    # Gradual increase: 23100 CFS over 5 hours = ~4620 CFS/hour
    scenarios['rising'] = [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': int(3300 + ((6 - i) * 4620)),
         'elevation': 654.0,
         'tailwater': 450.0,
         'generation': 50 + ((6 - i) * 26),
         'spillway_release': 0,
         'total_release': int(3300 + ((6 - i) * 4620))}
        for i in range(6, 0, -1)
    ]

    # Falling water - decreasing from 26400 to 3300 CFS over 6 hours
    # Water takes 1.6-3.7 hours to reach White Hole, so 6 hours shows transition
    # Gradual decrease: 23100 CFS over 5 hours = ~4620 CFS/hour
    scenarios['falling'] = [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': int(26400 - ((6 - i) * 4620)),
         'elevation': 654.0,
         'tailwater': 450.0,
         'generation': 180 - ((6 - i) * 26),
         'spillway_release': 0,
         'total_release': int(26400 - ((6 - i) * 4620))}
        for i in range(6, 0, -1)
    ]

    # High water - steady high flow around 23100 CFS (7 generators)
    scenarios['high'] = [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': 23100,
         'elevation': 654.0,
         'tailwater': 460.0,
         'generation': 150,
         'spillway_release': 0,
         'total_release': 23100}
        for i in range(24, 0, -1)
    ]

    # Low water - steady low flow around 1650 CFS (0.5 generators)
    scenarios['low'] = [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': 1650,
         'elevation': 654.0,
         'tailwater': 440.0,
         'generation': 25,
         'spillway_release': 0,
         'total_release': 1650}
        for i in range(24, 0, -1)
    ]

    # Flood conditions - high flow with spillway release
    scenarios['flood'] = [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': 26400,
         'elevation': 660.0,
         'tailwater': 470.0,
         'generation': 180,
         'spillway_release': 5000,
         'total_release': 31400}
        for i in range(24, 0, -1)
    ]

    # Fluctuating conditions - alternating between 3300, 9900, 16500, 23100 CFS
    scenarios['fluctuating'] = [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': [3300, 9900, 16500, 23100][(i // 3) % 4],
         'elevation': 654.0,
         'tailwater': 450.0,
         'generation': 50 if (i // 3) % 4 == 0 else 100,
         'spillway_release': 0,
         'total_release': [3300, 9900, 16500, 23100][(i // 3) % 4]}
        for i in range(36, 0, -1)
    ]

    # Sudden jump from low to high
    scenarios['jump'] = [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': 1650 if i > 12 else 26400,
         'elevation': 654.0,
         'tailwater': 440.0 if i > 12 else 470.0,
         'generation': 25 if i > 12 else 180,
         'spillway_release': 0,
         'total_release': 1650 if i > 12 else 26400}
        for i in range(24, 0, -1)
    ]

    # Sudden drop from high to low
    scenarios['drop'] = [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': 26400 if i > 12 else 1650,
         'elevation': 660.0 if i > 12 else 654.0,
         'tailwater': 470.0 if i > 12 else 440.0,
         'generation': 180 if i > 12 else 25,
         'spillway_release': 0,
         'total_release': 26400 if i > 12 else 1650}
        for i in range(24, 0, -1)
    ]

    # Bug scenario - water dropping from 10,647 to 6,187 CFS
    scenarios['bug_scenario'] = [
        {'date_time': base_time - timedelta(hours=11), 'turbine_release': 7325,
         'elevation': 654.0, 'tailwater': 450.0, 'generation': 100,
         'spillway_release': 0, 'total_release': 7325},
        {'date_time': base_time - timedelta(hours=10), 'turbine_release': 7265,
         'elevation': 654.0, 'tailwater': 450.0, 'generation': 100,
         'spillway_release': 0, 'total_release': 7265},
        {'date_time': base_time - timedelta(hours=9), 'turbine_release': 7500,
         'elevation': 654.0, 'tailwater': 450.0, 'generation': 100,
         'spillway_release': 0, 'total_release': 7500},
        {'date_time': base_time - timedelta(hours=8), 'turbine_release': 8519,
         'elevation': 654.0, 'tailwater': 450.0, 'generation': 100,
         'spillway_release': 0, 'total_release': 8519},
        {'date_time': base_time - timedelta(hours=7), 'turbine_release': 10941,
         'elevation': 654.0, 'tailwater': 450.0, 'generation': 100,
         'spillway_release': 0, 'total_release': 10941},
        {'date_time': base_time - timedelta(hours=6), 'turbine_release': 11669,
         'elevation': 654.0, 'tailwater': 450.0, 'generation': 100,
         'spillway_release': 0, 'total_release': 11669},
        {'date_time': base_time - timedelta(hours=5), 'turbine_release': 9997,
         'elevation': 654.0, 'tailwater': 450.0, 'generation': 100,
         'spillway_release': 0, 'total_release': 9997},
        {'date_time': base_time - timedelta(hours=4), 'turbine_release': 11557,
         'elevation': 654.0, 'tailwater': 450.0, 'generation': 100,
         'spillway_release': 0, 'total_release': 11557},
        {'date_time': base_time - timedelta(hours=3), 'turbine_release': 10647,
         'elevation': 654.0, 'tailwater': 450.0, 'generation': 100,
         'spillway_release': 0, 'total_release': 10647},
        {'date_time': base_time - timedelta(hours=2), 'turbine_release': 6187,
         'elevation': 654.0, 'tailwater': 450.0, 'generation': 100,
         'spillway_release': 0, 'total_release': 6187},
    ]

    return scenarios


def generate_test_html_files():
    """Generate HTML files for each test dataset."""

    base_time = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    scenarios = create_test_data(base_time)

    print("Generating HTML test files for manual visual inspection...\n")

    for name, data in scenarios.items():
        print(f"Generating HTML for '{name}' scenario...")

        html = generate_white_hole_summary(
            output_format="html",
            data=data,
            dataset_name=name,
            current_time=base_time
        )
        save_html_summary(html, filename=f"white_hole_conditions_{name}.html")

        print(f"  ✓ Created white_hole_conditions_{name}.html")
        print(f"  ✓ Created vertical_flow_chart_{name}.png\n")

    print(f"Generated {len(scenarios)} test scenarios.")
    print("\nOpen the HTML files in your browser to visually inspect the output.")


if __name__ == "__main__":
    generate_test_html_files()
