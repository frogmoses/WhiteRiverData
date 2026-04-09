"""Unit tests for water_calculator.py"""
from datetime import datetime, timedelta
import pytest
from water_calculator import (
    calculate_travel_time,
    determine_water_state,
    get_fishing_condition,
    get_recent_trend,
    forecast_conditions,
    format_generators,
    calculate_timeline,
    calculate_forecast_timeline
)


class TestCalculateTravelTime:
    """Tests for calculate_travel_time function."""

    def test_low_flow_0_to_1_gen(self):
        """Test travel time for low flow (0-1 generator range)."""
        # 1650 CFS (0.5 generators) should use avg speed of 1.875 mph
        travel_time = calculate_travel_time(1650)
        expected_time = 7 / 1.875  # ~3.73 hours
        assert abs(travel_time - expected_time) < 0.1

    def test_medium_flow_1_to_2_gen(self):
        """Test travel time for medium flow (1-2 generator range)."""
        # 4950 CFS (1.5 generators) should interpolate
        travel_time = calculate_travel_time(4950)
        assert 2.5 < travel_time < 3.5  # Should be between speeds for 1 and 2 gens

    def test_high_flow_3_to_4_gen(self):
        """Test travel time for high flow (3-4 generator range)."""
        # 11550 CFS (3.5 generators)
        travel_time = calculate_travel_time(11550)
        assert 2.0 < travel_time < 3.0  # Faster travel at higher flow

    def test_very_high_flow_7_to_8_gen(self):
        """Test travel time for very high flow (7-8 generator range)."""
        # 24750 CFS (7.5 generators)
        travel_time = calculate_travel_time(24750)
        assert 1.5 < travel_time < 2.0  # Even faster at very high flow

    def test_extreme_high_flow_above_8_gen(self):
        """Test travel time for extreme flow (>8 generators)."""
        # 30000 CFS (>9 generators)
        travel_time = calculate_travel_time(30000)
        assert travel_time < 2.0  # Fastest travel time


class TestDetermineWaterState:
    """Tests for determine_water_state function."""

    def test_rising_water(self, base_time):
        """Test that rising water is detected correctly."""
        # Create data with significant rise (>20% and >500 CFS)
        from datetime import timedelta
        data = [
            {'date_time': base_time - timedelta(hours=6),
             'turbine_release': 5000},
            {'date_time': base_time - timedelta(hours=5),
             'turbine_release': 6000},
            {'date_time': base_time - timedelta(hours=4),
             'turbine_release': 7500},
        ]
        state = determine_water_state(data, base_time, 7500)
        assert state == "rising"

    def test_falling_water(self, base_time):
        """Test that falling water is detected correctly."""
        # Create data with significant fall (>20% and >500 CFS)
        from datetime import timedelta
        data = [
            {'date_time': base_time - timedelta(hours=6),
             'turbine_release': 10000},
            {'date_time': base_time - timedelta(hours=5),
             'turbine_release': 8000},
            {'date_time': base_time - timedelta(hours=4),
             'turbine_release': 6000},
        ]
        state = determine_water_state(data, base_time, 6000)
        assert state == "falling"

    def test_stable_water(self, normal_conditions_data, base_time):
        """Test that stable water is detected correctly."""
        state = determine_water_state(normal_conditions_data, base_time, 6600)
        assert state == "stable"

    def test_insufficient_data(self):
        """Test handling of insufficient data."""
        # Only one entry
        data = [{'date_time': datetime.now(), 'turbine_release': 6600}]
        state = determine_water_state(data, datetime.now(), 6600)
        assert state == "stable"  # Default to stable


class TestGetFishingCondition:
    """Tests for get_fishing_condition function."""

    def test_excellent_wading_low_flow(self):
        """Test conditions for excellent wading (low flow)."""
        wading, boating = get_fishing_condition(1500)
        assert wading == "excellent wading"
        assert boating == "low for boating"

    def test_still_wadable_medium_flow(self):
        """Test conditions for marginal wading (medium flow)."""
        wading, boating = get_fishing_condition(3500)
        assert wading == "still wadable"
        assert boating == "ideal boating"

    def test_no_wading_medium_high_flow(self):
        """Test conditions for no wading but good boating."""
        wading, boating = get_fishing_condition(7500)
        assert wading == "no wading"
        assert boating == "ideal boating"

    def test_no_wading_high_water(self):
        """Test conditions for high water (no wading, high for boating)."""
        wading, boating = get_fishing_condition(12000)
        assert wading == "no wading"
        assert boating == "high water"

    def test_boundary_2000_cfs(self):
        """Test boundary at 2000 CFS."""
        wading_below, boating_below = get_fishing_condition(1999)
        wading_at, boating_at = get_fishing_condition(2000)
        assert wading_below == "excellent wading"
        assert wading_at == "still wadable"

    def test_boundary_5000_cfs(self):
        """Test boundary at 5000 CFS."""
        wading_below, boating_below = get_fishing_condition(4999)
        wading_at, boating_at = get_fishing_condition(5000)
        assert wading_below == "still wadable"
        assert wading_at == "no wading"

    def test_boundary_10000_cfs(self):
        """Test boundary at 10000 CFS."""
        wading_below, boating_below = get_fishing_condition(9999)
        wading_at, boating_at = get_fishing_condition(10000)
        assert boating_below == "ideal boating"
        assert boating_at == "high water"


class TestGetRecentTrend:
    """Tests for get_recent_trend function."""

    def test_steady_trend(self, normal_conditions_data, base_time):
        """Test detection of steady conditions."""
        trend = get_recent_trend(normal_conditions_data, base_time)
        assert "steady" in trend.lower()

    def test_increasing_trend(self, base_time):
        """Test detection of increasing trend."""
        from datetime import timedelta
        # Create data with significant increase (max > avg * 1.2)
        data = [
            {'date_time': base_time - timedelta(hours=5),
             'turbine_release': 5000},
            {'date_time': base_time - timedelta(hours=4),
             'turbine_release': 6000},
            {'date_time': base_time - timedelta(hours=3),
             'turbine_release': 7000},
            {'date_time': base_time - timedelta(hours=2),
             'turbine_release': 9000},
            {'date_time': base_time - timedelta(hours=1),
             'turbine_release': 10000},
        ]
        trend = get_recent_trend(data, base_time)
        assert "increased" in trend.lower()

    def test_decreasing_trend(self, base_time):
        """Test detection of decreasing trend."""
        from datetime import timedelta
        # Create data where min < avg * 0.8 but max is not > avg * 1.2
        # 7000, 7000, 7000, 6000, 3000
        # avg = 6000, min = 3000, max = 7000
        # min (3000) < avg (6000) * 0.8 (4800)? Yes
        # max (7000) > avg (6000) * 1.2 (7200)? No
        data = [
            {'date_time': base_time - timedelta(hours=5),
             'turbine_release': 7000},
            {'date_time': base_time - timedelta(hours=4),
             'turbine_release': 7000},
            {'date_time': base_time - timedelta(hours=3),
             'turbine_release': 7000},
            {'date_time': base_time - timedelta(hours=2),
             'turbine_release': 6000},
            {'date_time': base_time - timedelta(hours=1),
             'turbine_release': 3000},
        ]
        trend = get_recent_trend(data, base_time)
        assert "decreased" in trend.lower()


class TestForecastConditions:
    """Tests for forecast_conditions function."""

    def test_forecast_rising_water(self, base_time):
        """Test forecast correctly detects incoming rising water."""
        from datetime import timedelta
        # Current at White Hole: 5000 CFS (released 4 hours ago, has arrived)
        # Latest release: 12000 CFS (1 hour ago, hasn't arrived yet)
        # This should trigger rising (12000 > 5000 * 1.2 and 12000 - 5000 > 500)
        data = [
            {'date_time': base_time - timedelta(hours=4),
             'turbine_release': 5000},
            {'date_time': base_time - timedelta(hours=1),
             'turbine_release': 12000},
        ]
        forecast = forecast_conditions(data, base_time)
        assert "rising" in forecast.lower()

    def test_forecast_falling_water(self, base_time):
        """Test forecast correctly detects incoming falling water (bug fix verification)."""
        # Current at White Hole: 10647 CFS (released 3 hours ago)
        # Latest release: 6187 CFS (2 hours ago, hasn't arrived yet)
        data = [
            {'date_time': base_time - timedelta(hours=3),
             'turbine_release': 10647},
            {'date_time': base_time - timedelta(hours=2),
             'turbine_release': 6187},
        ]
        forecast = forecast_conditions(data, base_time)
        assert "falling" in forecast.lower()

    def test_forecast_stable_conditions(self, normal_conditions_data, base_time):
        """Test forecast for stable conditions."""
        forecast = forecast_conditions(normal_conditions_data, base_time)
        assert "stable" in forecast.lower() or "similar" in forecast.lower()

    def test_forecast_with_bug_scenario(self, falling_water_scenario_data, base_time):
        """Test the specific bug scenario: 10,647 CFS dropping to 6,187 CFS."""
        # This was showing "RISING WATER" incorrectly
        forecast = forecast_conditions(falling_water_scenario_data, base_time)
        assert "falling" in forecast.lower(), f"Expected falling water, got: {forecast}"


class TestFormatGenerators:
    """Tests for format_generators function."""

    def test_exact_single_generator(self):
        """Test formatting for exactly 1 generator."""
        result = format_generators(3300)
        assert result == "1 generator"

    def test_exact_multiple_generators(self):
        """Test formatting for exact multiple generators."""
        result = format_generators(6600)
        assert result == "2 generators"

    def test_fractional_generators(self):
        """Test formatting for fractional generators."""
        result = format_generators(5000)
        assert result == "1-2 generators"

    def test_high_generator_count(self):
        """Test formatting for high generator counts."""
        result = format_generators(24000)
        assert "7" in result  # Should show 7 or 7-8

    def test_very_low_flow(self):
        """Test formatting for very low flow."""
        result = format_generators(1000)
        assert result == "0 generators" or result == "0-1 generators"


class TestCalculateTimeline:
    """Tests for calculate_timeline function."""

    def test_timeline_structure(self, normal_conditions_data, base_time):
        """Test that timeline has correct structure."""
        timeline = calculate_timeline(normal_conditions_data, base_time)
        assert isinstance(timeline, list)

        if timeline:
            entry = timeline[0]
            assert 'release_time' in entry
            assert 'cfs' in entry
            assert 'generators' in entry
            assert 'arrival_time' in entry
            assert 'status' in entry

    def test_timeline_identifies_current_water(self, base_time):
        """Test that timeline correctly identifies current water at White Hole."""
        # Create data where one entry has arrived, one hasn't
        data = [
            {'date_time': base_time - timedelta(hours=3),
             'turbine_release': 6600},  # Should be at White Hole now
            {'date_time': base_time - timedelta(hours=1),
             'turbine_release': 10000},  # Should be incoming
        ]
        timeline = calculate_timeline(data, base_time)

        # Find the current entry
        current_entries = [e for e in timeline if e['status'] == 'current']
        assert len(current_entries) == 1
        assert current_entries[0]['cfs'] == 6600

    def test_timeline_identifies_incoming_water(self, base_time):
        """Test that timeline correctly identifies incoming water."""
        data = [
            {'date_time': base_time - timedelta(hours=3),
             'turbine_release': 6600},  # At White Hole
            {'date_time': base_time - timedelta(hours=1),
             'turbine_release': 10000},  # Incoming
        ]
        timeline = calculate_timeline(data, base_time)

        # Find incoming entries
        incoming_entries = [e for e in timeline if e['status'] == 'incoming']
        assert len(incoming_entries) >= 1

        # Check that minutes_until is set
        incoming = incoming_entries[0]
        assert incoming['minutes_until'] is not None
        assert incoming['minutes_until'] > 0

    def test_timeline_max_entries(self, normal_conditions_data, base_time):
        """Test that timeline doesn't return too many entries."""
        timeline = calculate_timeline(normal_conditions_data, base_time)
        assert len(timeline) <= 4  # Should return at most 4 entries


class TestCalculateForecastTimeline:
    """Tests for calculate_forecast_timeline function."""

    def test_empty_input(self, base_time):
        result = calculate_forecast_timeline([], base_time)
        assert result == []

    def test_none_input(self, base_time):
        result = calculate_forecast_timeline(None, base_time)
        assert result == []

    def test_basic_structure(self, base_time):
        forecast_data = [
            {'hour': 14, 'mw': 40, 'cfs': 2703, 'start_time': base_time + timedelta(hours=2), 'end_time': base_time + timedelta(hours=3)},
        ]
        result = calculate_forecast_timeline(forecast_data, base_time)
        assert len(result) == 1
        entry = result[0]
        assert 'scheduled_time' in entry
        assert 'mw' in entry
        assert 'cfs' in entry
        assert 'generators' in entry
        assert 'arrival_time' in entry
        assert 'wading' in entry
        assert 'boating' in entry

    def test_arrival_time_after_scheduled_time(self, base_time):
        """Arrival at White Hole should always be after the scheduled release."""
        forecast_data = [
            {'hour': 14, 'mw': 40, 'cfs': 2703, 'start_time': base_time + timedelta(hours=2), 'end_time': base_time + timedelta(hours=3)},
        ]
        result = calculate_forecast_timeline(forecast_data, base_time)
        assert result[0]['arrival_time'] > result[0]['scheduled_time']

    def test_conditions_match_cfs(self, base_time):
        """Wading/boating conditions should match the CFS thresholds."""
        # Low CFS = excellent wading
        forecast_low = [
            {'hour': 1, 'mw': 7, 'cfs': 473, 'start_time': base_time + timedelta(hours=1), 'end_time': base_time + timedelta(hours=2)},
        ]
        result = calculate_forecast_timeline(forecast_low, base_time)
        assert result[0]['wading'] == 'excellent wading'

        # High CFS = no wading
        forecast_high = [
            {'hour': 20, 'mw': 200, 'cfs': 13504, 'start_time': base_time + timedelta(hours=8), 'end_time': base_time + timedelta(hours=9)},
        ]
        result = calculate_forecast_timeline(forecast_high, base_time)
        assert result[0]['wading'] == 'no wading'

    def test_multiple_hours(self, base_time):
        """Test with multiple forecast hours."""
        forecast_data = [
            {'hour': h, 'mw': 7, 'cfs': 473, 'start_time': base_time + timedelta(hours=h), 'end_time': base_time + timedelta(hours=h+1)}
            for h in range(1, 7)
        ]
        result = calculate_forecast_timeline(forecast_data, base_time)
        assert len(result) == 6
