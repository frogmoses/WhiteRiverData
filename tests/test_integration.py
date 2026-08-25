"""Integration tests for the complete White Hole summary generation."""
import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from main import generate_white_hole_summary
from water_calculator import calculate_timeline, forecast_conditions


class TestTimezoneAwareData:
    """Production data carries Central-time (America/Chicago) timestamps."""

    CENTRAL = ZoneInfo("America/Chicago")

    def _entry(self, dt, cfs):
        return {'date_time': dt, 'elevation': 657.0, 'tailwater': 450.0,
                'generation': 100, 'turbine_release': cfs,
                'spillway_release': 0, 'total_release': cfs}

    def test_summary_with_aware_central_timestamps(self):
        """The pipeline must handle timezone-aware data end to end."""
        now = datetime(2026, 8, 24, 12, 0, tzinfo=self.CENTRAL)
        data = [self._entry(now - timedelta(hours=h), 750) for h in range(6, 0, -1)]
        text = generate_white_hole_summary(
            output_format="text", data=data, current_time=now)
        assert "WHITE HOLE" in text
        assert "750" in text

    def test_fresh_release_not_reported_as_arrived(self):
        """Water released 30 minutes ago (2+ hour travel) is not at White Hole.

        Regression for the Central-vs-Eastern skew, which shifted every
        arrival an hour early.
        """
        now = datetime(2026, 8, 24, 12, 0, tzinfo=self.CENTRAL)
        data = [
            self._entry(now - timedelta(hours=4), 750),
            self._entry(now - timedelta(minutes=30), 20000),
        ]
        timeline = calculate_timeline(data, now)
        current = [e for e in timeline if e['status'] == 'current']
        incoming = [e for e in timeline if e['status'] == 'incoming']
        assert current and current[0]['cfs'] == 750
        assert incoming and incoming[0]['cfs'] == 20000


class TestStaleDataWarning:
    """The page must warn when the USACE feed has stalled."""

    def _entry(self, dt, cfs):
        return {'date_time': dt, 'elevation': 657.0, 'tailwater': 450.0,
                'generation': 100, 'turbine_release': cfs,
                'spillway_release': 0, 'total_release': cfs}

    def test_stale_data_shows_warning(self, base_time):
        data = [self._entry(base_time - timedelta(hours=h), 750)
                for h in range(10, 5, -1)]  # newest reading is 6 hours old
        text = generate_white_hole_summary(
            output_format="text", data=data, current_time=base_time)
        assert "delayed" in text.lower()

        html = generate_white_hole_summary(
            output_format="html", data=data, current_time=base_time)
        assert "DAM DATA DELAYED" in html

    def test_fresh_data_has_no_warning(self, normal_conditions_data, base_time):
        text = generate_white_hole_summary(
            output_format="text", data=normal_conditions_data, current_time=base_time)
        assert "delayed" not in text.lower()

        html = generate_white_hole_summary(
            output_format="html", data=normal_conditions_data, current_time=base_time)
        assert "DAM DATA DELAYED" not in html


class TestWholeSystemIntegration:
    """Integration tests that test the complete system end-to-end."""

    def test_generate_summary_normal_conditions(self, normal_conditions_data, base_time):
        """Test generating summary with normal steady conditions."""
        html = generate_white_hole_summary(
            output_format="html",
            data=normal_conditions_data,
            current_time=base_time
        )
        assert html is not None
        assert "White Hole" in html
        assert "6600" in html or "6,600" in html

    def test_generate_summary_rising_water(self, rising_water_data, base_time):
        """Test generating summary with rising water conditions."""
        text = generate_white_hole_summary(
            output_format="text",
            data=rising_water_data,
            current_time=base_time
        )
        assert text is not None
        assert "WHITE HOLE" in text

    def test_generate_summary_falling_water(self, falling_water_data, base_time):
        """Test generating summary with falling water conditions."""
        html = generate_white_hole_summary(
            output_format="html",
            data=falling_water_data,
            current_time=base_time
        )
        assert html is not None
        assert "White Hole" in html

    def test_generate_summary_high_water(self, high_water_data, base_time):
        """Test generating summary with high water conditions."""
        text = generate_white_hole_summary(
            output_format="text",
            data=high_water_data,
            current_time=base_time
        )
        assert text is not None
        assert "23100" in text or "23,100" in text
        # High water should indicate no wading
        assert "no wading" in text.lower()

    def test_generate_summary_low_water(self, low_water_data, base_time):
        """Test generating summary with low water conditions."""
        text = generate_white_hole_summary(
            output_format="text",
            data=low_water_data,
            current_time=base_time
        )
        assert text is not None
        assert "1650" in text or "1,650" in text
        # Low water should indicate good wading
        assert "wading" in text.lower()

    def test_generate_summary_html_format(self, normal_conditions_data, base_time):
        """Test generating HTML format with headline banner."""
        html = generate_white_hole_summary(
            output_format="html",
            data=normal_conditions_data,
            current_time=base_time
        )
        assert html is not None
        assert "headline-banner" in html
        assert "White Hole" in html

    def test_generate_summary_flood_conditions(self, flood_conditions_data, base_time):
        """Test generating summary with flood conditions."""
        html = generate_white_hole_summary(
            output_format="html",
            data=flood_conditions_data,
            current_time=base_time
        )
        assert html is not None
        # Flood conditions should show total release (turbine + spillway),
        # not just the turbine release
        assert "31400" in html or "31,400" in html

    def test_generate_summary_fluctuating_conditions(self, fluctuating_conditions_data, base_time):
        """Test generating summary with fluctuating conditions."""
        text = generate_white_hole_summary(
            output_format="text",
            data=fluctuating_conditions_data,
            current_time=base_time
        )
        assert text is not None
        # Should mention some level of variability
        assert "WHITE HOLE" in text

    def test_generate_summary_sudden_jump(self, sudden_jump_data, base_time):
        """Test generating summary with sudden jump in water level."""
        html = generate_white_hole_summary(
            output_format="html",
            data=sudden_jump_data,
            current_time=base_time
        )
        assert html is not None
        # Should handle the sudden change gracefully
        assert "White Hole" in html

    def test_generate_summary_sudden_drop(self, sudden_drop_data, base_time):
        """Test generating summary with sudden drop in water level."""
        html = generate_white_hole_summary(
            output_format="html",
            data=sudden_drop_data,
            current_time=base_time
        )
        assert html is not None
        assert "White Hole" in html

    def test_all_formats_work(self, normal_conditions_data, base_time):
        """Test that all output formats can be generated without errors."""
        text = generate_white_hole_summary(
            output_format="text",
            data=normal_conditions_data,
            current_time=base_time
        )
        assert text is not None

        html = generate_white_hole_summary(
            output_format="html",
            data=normal_conditions_data,
            current_time=base_time
        )
        assert html is not None


class TestTimelineIntegration:
    """Integration tests for timeline functionality."""

    def test_timeline_with_rising_water(self, rising_water_data, base_time):
        """Test timeline generation with rising water."""
        timeline = calculate_timeline(rising_water_data, base_time)
        assert timeline is not None
        assert len(timeline) > 0

        # Should have incoming water with higher CFS
        incoming = [e for e in timeline if e['status'] == 'incoming']
        if incoming:
            assert incoming[0]['minutes_until'] is not None

    def test_timeline_with_falling_water(self, falling_water_data, base_time):
        """Test timeline generation with falling water."""
        timeline = calculate_timeline(falling_water_data, base_time)
        assert timeline is not None
        assert len(timeline) > 0

    def test_timeline_identifies_current_correctly(self, normal_conditions_data, base_time):
        """Test that timeline correctly identifies current water at White Hole."""
        timeline = calculate_timeline(normal_conditions_data, base_time)
        assert timeline is not None

        # Should have exactly one 'current' entry
        current_entries = [e for e in timeline if e['status'] == 'current']
        assert len(current_entries) == 1


class TestForecastIntegration:
    """Integration tests for forecast functionality."""

    def test_forecast_detects_incoming_rise(self, base_time):
        """Test that forecast correctly detects incoming water rise."""
        from datetime import timedelta

        # Simulate: currently 6000 CFS at White Hole, 12000 CFS incoming
        data = [
            {'date_time': base_time - timedelta(hours=4),
             'turbine_release': 6000},
            {'date_time': base_time - timedelta(hours=2),
             'turbine_release': 12000},
        ]

        forecast = forecast_conditions(data, base_time)
        assert "rising" in forecast.lower()

    def test_forecast_detects_incoming_fall(self, base_time):
        """Test that forecast correctly detects incoming water fall (bug fix)."""
        from datetime import timedelta

        # Simulate: currently 10647 CFS at White Hole, 6187 CFS incoming
        data = [
            {'date_time': base_time - timedelta(hours=4),
             'turbine_release': 10647},
            {'date_time': base_time - timedelta(hours=2),
             'turbine_release': 6187},
        ]

        forecast = forecast_conditions(data, base_time)
        # This is the bug we fixed - should say falling, not rising
        assert "falling" in forecast.lower(), f"Expected 'falling' in forecast, got: {forecast}"


class TestBugFixes:
    """Tests that verify specific bugs are fixed."""

    def test_falling_water_bug_fix(self, falling_water_scenario_data, base_time):
        """
        Test the specific bug where water dropping from 10,647 to 6,187 CFS
        was incorrectly reported as "RISING WATER".
        """
        html = generate_white_hole_summary(
            output_format="html",
            data=falling_water_scenario_data,
            current_time=base_time
        )

        # Should NOT contain "RISING WATER"
        assert "RISING WATER" not in html, "Bug: Still showing RISING WATER for falling conditions"

        # Should contain "FALLING WATER"
        assert "FALLING WATER" in html or "falling" in html.lower(), \
            "Expected FALLING WATER message when water is dropping"

    def test_forecast_uses_most_recent_water_at_hole(self, base_time):
        """
        Test that forecast compares latest release to the MOST RECENT water
        at White Hole, not the oldest water.
        """
        from datetime import timedelta

        # Multiple entries where water has arrived
        data = [
            {'date_time': base_time - timedelta(hours=6),
             'turbine_release': 5000},  # Old, already passed through
            {'date_time': base_time - timedelta(hours=4),
             'turbine_release': 10000},  # Current at White Hole
            {'date_time': base_time - timedelta(hours=2),
             'turbine_release': 6000},  # Incoming (lower than current)
        ]

        forecast = forecast_conditions(data, base_time)

        # Should compare 6000 to 10000 (the current), not to 5000 (old water)
        # 6000 < 10000, so should be falling
        assert "falling" in forecast.lower(), \
            f"Forecast should detect falling water (10000 -> 6000), got: {forecast}"
