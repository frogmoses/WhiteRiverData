"""Pytest fixtures for White River Data tests."""
from datetime import datetime, timedelta
import pytest


@pytest.fixture
def base_time():
    """Base time for test datasets."""
    return datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)


@pytest.fixture
def normal_conditions_data(base_time):
    """Normal conditions dataset - steady flow around 6600 CFS (2 generators)."""
    return [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': 6600,
         'elevation': 654.0,
         'tailwater': 450.0,
         'generation': 100,
         'spillway_release': 0,
         'total_release': 6600}
        for i in range(24, 0, -1)
    ]


@pytest.fixture
def rising_water_data(base_time):
    """Rising water dataset - increasing from 3300 to 26400 CFS over 6 hours.

    This creates realistic rising conditions where water released 3-4 hours ago
    is currently arriving at White Hole, and higher flows are still incoming.
    """
    # Gradual increase: 23100 CFS over 5 hours = ~4620 CFS/hour
    return [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': int(3300 + ((6 - i) * 4620)),
         'elevation': 654.0,
         'tailwater': 450.0,
         'generation': 50 + ((6 - i) * 26),
         'spillway_release': 0,
         'total_release': int(3300 + ((6 - i) * 4620))}
        for i in range(6, 0, -1)
    ]


@pytest.fixture
def falling_water_data(base_time):
    """Falling water dataset - decreasing from 26400 to 3300 CFS over 6 hours.

    This creates realistic falling conditions where water released 3-4 hours ago
    is currently arriving at White Hole, and lower flows are still incoming.
    """
    # Gradual decrease: 23100 CFS over 5 hours = ~4620 CFS/hour
    return [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': int(26400 - ((6 - i) * 4620)),
         'elevation': 654.0,
         'tailwater': 450.0,
         'generation': 180 - ((6 - i) * 26),
         'spillway_release': 0,
         'total_release': int(26400 - ((6 - i) * 4620))}
        for i in range(6, 0, -1)
    ]


@pytest.fixture
def high_water_data(base_time):
    """High water dataset - steady high flow around 23100 CFS (7 generators)."""
    return [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': 23100,
         'elevation': 654.0,
         'tailwater': 460.0,
         'generation': 150,
         'spillway_release': 0,
         'total_release': 23100}
        for i in range(24, 0, -1)
    ]


@pytest.fixture
def low_water_data(base_time):
    """Low water dataset - steady low flow around 1650 CFS (0.5 generators)."""
    return [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': 1650,
         'elevation': 654.0,
         'tailwater': 440.0,
         'generation': 25,
         'spillway_release': 0,
         'total_release': 1650}
        for i in range(24, 0, -1)
    ]


@pytest.fixture
def flood_conditions_data(base_time):
    """Flood conditions - high flow with spillway release, turbine at 26400 CFS (8 generators)."""
    return [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': 26400,
         'elevation': 660.0,
         'tailwater': 470.0,
         'generation': 180,
         'spillway_release': 5000,
         'total_release': 31400}
        for i in range(24, 0, -1)
    ]


@pytest.fixture
def fluctuating_conditions_data(base_time):
    """Fluctuating conditions - alternating between 3300, 9900, 16500, 23100 CFS."""
    return [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': [3300, 9900, 16500, 23100][(i // 3) % 4],
         'elevation': 654.0,
         'tailwater': 450.0,
         'generation': 50 if (i // 3) % 4 == 0 else 100,
         'spillway_release': 0,
         'total_release': [3300, 9900, 16500, 23100][(i // 3) % 4]}
        for i in range(36, 0, -1)
    ]


@pytest.fixture
def sudden_jump_data(base_time):
    """Edge case: sudden jump from low to high."""
    return [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': 1650 if i > 12 else 26400,
         'elevation': 654.0,
         'tailwater': 440.0 if i > 12 else 470.0,
         'generation': 25 if i > 12 else 180,
         'spillway_release': 0,
         'total_release': 1650 if i > 12 else 26400}
        for i in range(24, 0, -1)
    ]


@pytest.fixture
def sudden_drop_data(base_time):
    """Edge case: sudden drop from high to low."""
    return [
        {'date_time': base_time - timedelta(hours=i),
         'turbine_release': 26400 if i > 12 else 1650,
         'elevation': 660.0 if i > 12 else 654.0,
         'tailwater': 470.0 if i > 12 else 440.0,
         'generation': 180 if i > 12 else 25,
         'spillway_release': 0,
         'total_release': 26400 if i > 12 else 1650}
        for i in range(24, 0, -1)
    ]


@pytest.fixture
def falling_water_scenario_data(base_time):
    """
    Scenario from bug report: water dropping from 10,000+ to 6,000+ CFS.
    At 09:00: 10,647 CFS (currently at White Hole)
    At 10:00: 6,187 CFS (arriving in ~53 minutes)
    """
    return [
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
