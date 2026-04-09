"""Unit tests for formatters.py"""
from datetime import datetime, timedelta
import pytest
import re
from formatters import (
    generate_html_summary,
    generate_error_html,
    generate_text_summary,
    generate_table_rows
)


class TestGenerateTableRows:
    """Tests for generate_table_rows function."""

    def test_table_rows_structure(self, normal_conditions_data):
        """Test that table rows are generated with correct HTML structure."""
        rows = generate_table_rows(normal_conditions_data[:5])
        assert '<tr' in rows
        assert '<td' in rows
        assert '</tr>' in rows
        assert '</td>' in rows

    def test_table_rows_contain_data(self, normal_conditions_data):
        """Test that table rows contain the actual data."""
        data = normal_conditions_data[:1]
        rows = generate_table_rows(data)
        assert '6600' in rows  # CFS value
        assert '2.0' in rows  # Generator count (6600/3300)

    def test_empty_data(self):
        """Test table generation with empty data."""
        rows = generate_table_rows([])
        assert rows == ''


class TestGenerateErrorHtml:
    """Tests for generate_error_html function."""

    def test_error_html_structure(self):
        """Test that error HTML has correct structure."""
        html = generate_error_html("Test error message")
        assert '<!DOCTYPE html>' in html
        assert '<html' in html
        assert '</html>' in html
        assert 'Test error message' in html

    def test_error_html_contains_timestamp(self):
        """Test that error HTML contains a timestamp."""
        test_time = datetime(2026, 1, 18, 12, 0, 0)
        html = generate_error_html("Error", test_time)
        assert '2026-01-18' in html


class TestGenerateTextSummary:
    """Tests for generate_text_summary function."""

    def test_text_summary_structure(self, base_time):
        """Test that text summary has correct structure."""
        latest_entry = {
            'date_time': base_time - timedelta(hours=2),
            'turbine_release': 6600
        }
        relevant_entry = {
            'date_time': base_time - timedelta(hours=3),
            'turbine_release': 6600
        }

        summary = generate_text_summary(
            current_time=base_time,
            white_hole_cfs=6600,
            generators_equivalent=2.0,
            water_state="stable",
            wading_condition="still wadable",
            boating_condition="ideal boating",
            recent_trend="remained relatively steady",
            forecast="stable conditions expected",
            latest_entry=latest_entry,
            relevant_entry=relevant_entry
        )

        assert "WHITE HOLE CURRENT CONDITIONS SUMMARY" in summary
        assert "6600" in summary
        assert "stable" in summary.lower()

    def test_text_summary_contains_all_data(self, base_time):
        """Test that text summary includes all required data fields."""
        latest_entry = {
            'date_time': base_time - timedelta(hours=2),
            'turbine_release': 10000
        }
        relevant_entry = {
            'date_time': base_time - timedelta(hours=3),
            'turbine_release': 8000
        }

        summary = generate_text_summary(
            current_time=base_time,
            white_hole_cfs=8000,
            generators_equivalent=2.4,
            water_state="rising",
            wading_condition="no wading",
            boating_condition="ideal boating",
            recent_trend="moderately increased",
            forecast="rising water expected soon",
            latest_entry=latest_entry,
            relevant_entry=relevant_entry
        )

        assert "8000" in summary  # white_hole_cfs
        assert "2.4" in summary  # generators_equivalent
        assert "rising" in summary.lower()
        assert "no wading" in summary.lower()
        assert "10000" in summary  # latest dam reading


class TestGenerateHtmlSummary:
    """Tests for generate_html_summary function."""

    def test_html_structure(self, base_time, normal_conditions_data):
        """Test that HTML has correct structure."""
        latest_entry = normal_conditions_data[0]
        relevant_entry = normal_conditions_data[0]

        html = generate_html_summary(
            current_time=base_time,
            white_hole_cfs=6600,
            generators_equivalent=2.0,
            water_state="stable",
            wading_condition="still wadable",
            boating_condition="ideal boating",
            recent_trend="remained relatively steady",
            forecast="stable conditions expected",
            latest_entry=latest_entry,
            relevant_entry=relevant_entry,
            recent_data=normal_conditions_data,
            timeline_data=[]
        )

        assert '<!DOCTYPE html>' in html
        assert '<html' in html
        assert '</html>' in html
        assert 'headline-banner' in html
        assert 'White Hole' in html

    def test_html_contains_flow_data(self, base_time, normal_conditions_data):
        """Test that HTML contains flow data."""
        latest_entry = normal_conditions_data[0]
        relevant_entry = normal_conditions_data[0]

        html = generate_html_summary(
            current_time=base_time,
            white_hole_cfs=6600,
            generators_equivalent=2.0,
            water_state="stable",
            wading_condition="still wadable",
            boating_condition="ideal boating",
            recent_trend="remained relatively steady",
            forecast="stable conditions expected",
            latest_entry=latest_entry,
            relevant_entry=relevant_entry,
            recent_data=normal_conditions_data,
            timeline_data=[]
        )

        assert '6,600' in html

    def test_html_headline_banner(self, base_time, normal_conditions_data):
        """Test that HTML includes headline banner with correct messages."""
        latest_entry = normal_conditions_data[0]
        relevant_entry = normal_conditions_data[0]

        html = generate_html_summary(
            current_time=base_time,
            white_hole_cfs=12000,
            generators_equivalent=3.6,
            water_state="stable",
            wading_condition="no wading",
            boating_condition="high water",
            recent_trend="steady",
            forecast="stable conditions expected",
            latest_entry=latest_entry,
            relevant_entry=relevant_entry,
            recent_data=normal_conditions_data,
            timeline_data=[]
        )

        assert 'NO WADING' in html
        assert 'headline-banner' in html

    def test_html_wading_conditions_excellent(self, base_time, normal_conditions_data):
        """Test HTML headline for excellent wading conditions."""
        latest_entry = normal_conditions_data[0]
        relevant_entry = normal_conditions_data[0]

        html = generate_html_summary(
            current_time=base_time,
            white_hole_cfs=1500,
            generators_equivalent=0.45,
            water_state="stable",
            wading_condition="excellent wading",
            boating_condition="low for boating",
            recent_trend="steady",
            forecast="stable conditions expected",
            latest_entry=latest_entry,
            relevant_entry=relevant_entry,
            recent_data=normal_conditions_data,
            timeline_data=[]
        )

        assert 'GOOD WADING' in html or 'excellent wading' in html.lower()

    def test_html_forecast_rising(self, base_time, normal_conditions_data):
        """Test HTML forecast message for rising water."""
        latest_entry = normal_conditions_data[0]
        relevant_entry = normal_conditions_data[0]
        timeline_data = [
            {
                'release_time': base_time - timedelta(hours=2),
                'cfs': 12000,
                'generators': '3-4 generators',
                'arrival_time': base_time + timedelta(minutes=30),
                'status': 'incoming',
                'minutes_until': 30
            }
        ]

        html = generate_html_summary(
            current_time=base_time,
            white_hole_cfs=6600,
            generators_equivalent=2.0,
            water_state="rising",
            wading_condition="still wadable",
            boating_condition="ideal boating",
            recent_trend="increased",
            forecast="rising water expected soon",
            latest_entry=latest_entry,
            relevant_entry=relevant_entry,
            recent_data=normal_conditions_data,
            timeline_data=timeline_data
        )

        assert 'RISING WATER' in html
        assert '30 min' in html or '30 minutes' in html

    def test_html_forecast_falling(self, base_time, normal_conditions_data):
        """Test HTML forecast message for falling water."""
        latest_entry = normal_conditions_data[0]
        relevant_entry = normal_conditions_data[0]

        html = generate_html_summary(
            current_time=base_time,
            white_hole_cfs=10000,
            generators_equivalent=3.0,
            water_state="falling",
            wading_condition="no wading",
            boating_condition="ideal boating",
            recent_trend="decreased",
            forecast="falling water expected soon",
            latest_entry=latest_entry,
            relevant_entry=relevant_entry,
            recent_data=normal_conditions_data,
            timeline_data=[]
        )

        assert 'FALLING WATER' in html

    def test_html_timeline_rendering(self, base_time, normal_conditions_data):
        """Test that HTML renders timeline correctly."""
        latest_entry = normal_conditions_data[0]
        relevant_entry = normal_conditions_data[0]
        timeline_data = [
            {
                'release_time': base_time - timedelta(hours=3),
                'cfs': 6600,
                'generators': '2 generators',
                'arrival_time': base_time - timedelta(hours=0.5),
                'status': 'current',
                'minutes_until': None
            },
            {
                'release_time': base_time - timedelta(hours=2),
                'cfs': 8000,
                'generators': '2-3 generators',
                'arrival_time': base_time + timedelta(hours=0.5),
                'status': 'incoming',
                'minutes_until': 30
            }
        ]

        html = generate_html_summary(
            current_time=base_time,
            white_hole_cfs=6600,
            generators_equivalent=2.0,
            water_state="stable",
            wading_condition="still wadable",
            boating_condition="ideal boating",
            recent_trend="steady",
            forecast="stable conditions expected",
            latest_entry=latest_entry,
            relevant_entry=relevant_entry,
            recent_data=normal_conditions_data,
            timeline_data=timeline_data
        )

        assert 'Water Timeline' in html
        assert 'AT WHITE HOLE NOW' in html
        assert 'Arrives' in html
        assert '8000' in html or '8,000' in html

    def test_html_responsive_design(self, base_time, normal_conditions_data):
        """Test that HTML includes responsive design CSS."""
        latest_entry = normal_conditions_data[0]
        relevant_entry = normal_conditions_data[0]

        html = generate_html_summary(
            current_time=base_time,
            white_hole_cfs=6600,
            generators_equivalent=2.0,
            water_state="stable",
            wading_condition="still wadable",
            boating_condition="ideal boating",
            recent_trend="steady",
            forecast="stable conditions expected",
            latest_entry=latest_entry,
            relevant_entry=relevant_entry,
            recent_data=normal_conditions_data,
            timeline_data=[]
        )

        assert '@media' in html
        assert 'max-width: 600px' in html


class TestWaterTimelineRendering:
    """Tests for the merged water timeline in HTML output."""

    def _make_html(self, base_time, normal_conditions_data, forecast_timeline=None, white_hole_cfs=1500, wading_condition="excellent wading", timeline_data=None):
        latest_entry = normal_conditions_data[0]
        relevant_entry = normal_conditions_data[0]
        return generate_html_summary(
            current_time=base_time,
            white_hole_cfs=white_hole_cfs,
            generators_equivalent=white_hole_cfs / 3300,
            water_state="stable",
            wading_condition=wading_condition,
            boating_condition="low for boating",
            recent_trend="steady",
            forecast="stable conditions expected",
            latest_entry=latest_entry,
            relevant_entry=relevant_entry,
            recent_data=normal_conditions_data,
            timeline_data=timeline_data or [],
            forecast_timeline=forecast_timeline,
        )

    def test_no_timeline_when_no_data(self, base_time, normal_conditions_data):
        """Timeline should not appear when both sources are empty."""
        html = self._make_html(base_time, normal_conditions_data, forecast_timeline=None, timeline_data=[])
        assert 'Water Timeline' not in html

    def test_timeline_with_only_actual_data(self, base_time, normal_conditions_data):
        """Timeline should show actual section even without forecast."""
        timeline_data = [
            {
                'release_time': base_time - timedelta(hours=3),
                'cfs': 6600, 'generators': '2 generators',
                'arrival_time': base_time - timedelta(hours=0.5),
                'status': 'current', 'minutes_until': None
            }
        ]
        html = self._make_html(base_time, normal_conditions_data, timeline_data=timeline_data)
        assert 'Water Timeline' in html
        assert 'Actual (dam readings)' in html
        assert 'Scheduled (SWPA forecast)' not in html

    def test_timeline_with_only_forecast_data(self, base_time, normal_conditions_data):
        """Timeline should show forecast section even without actual."""
        forecast_timeline = [
            {
                'scheduled_time': base_time + timedelta(hours=2),
                'hour': 14, 'mw': 40, 'cfs': 2951,
                'generation_cfs': 2701, 'min_flow_cfs': 250,
                'generators': '0-1 generators',
                'arrival_time': base_time + timedelta(hours=5),
                'wading': 'still wadable', 'boating': 'ideal boating',
            }
        ]
        html = self._make_html(base_time, normal_conditions_data, forecast_timeline=forecast_timeline)
        assert 'Water Timeline' in html
        assert 'Scheduled (SWPA forecast)' in html
        assert 'Actual (dam readings)' not in html

    def test_merged_timeline_shows_both(self, base_time, normal_conditions_data):
        """Timeline should show both forecast and actual sections."""
        timeline_data = [
            {
                'release_time': base_time - timedelta(hours=3),
                'cfs': 728, 'generators': '0-1 generators',
                'arrival_time': base_time - timedelta(hours=0.5),
                'status': 'current', 'minutes_until': None
            }
        ]
        forecast_timeline = [
            {
                'scheduled_time': base_time + timedelta(hours=2),
                'hour': 14, 'mw': 40, 'cfs': 2951,
                'generation_cfs': 2701, 'min_flow_cfs': 250,
                'generators': '0-1 generators',
                'arrival_time': base_time + timedelta(hours=5),
                'wading': 'still wadable', 'boating': 'ideal boating',
            }
        ]
        html = self._make_html(base_time, normal_conditions_data, forecast_timeline=forecast_timeline, timeline_data=timeline_data)
        assert 'Scheduled (SWPA forecast)' in html
        assert 'Actual (dam readings)' in html
        assert '2,951 CFS' in html
        assert '2701 generation + 250 min flow' in html

    def test_forecast_limited_to_4_hours(self, base_time, normal_conditions_data):
        """Forecast section should show at most 4 hours."""
        forecast_timeline = [
            {
                'scheduled_time': base_time + timedelta(hours=h),
                'hour': h, 'mw': 7, 'cfs': 723,
                'generation_cfs': 473, 'min_flow_cfs': 250,
                'generators': '0-1 generators',
                'arrival_time': base_time + timedelta(hours=h + 3.7),
                'wading': 'excellent wading', 'boating': 'low for boating',
            }
            for h in range(1, 9)  # 8 hours of forecast
        ]
        html = self._make_html(base_time, normal_conditions_data, forecast_timeline=forecast_timeline)
        # Count forecast rows (each has the light purple background)
        assert html.count('faf5ff') == 4

    def test_forecast_wading_condition_shown(self, base_time, normal_conditions_data):
        """Forecast rows should show wading condition."""
        forecast_timeline = [
            {
                'scheduled_time': base_time + timedelta(hours=2),
                'hour': 14, 'mw': 200, 'cfs': 13504,
                'generation_cfs': 13254, 'min_flow_cfs': 250,
                'generators': '4-5 generators',
                'arrival_time': base_time + timedelta(hours=4),
                'wading': 'no wading', 'boating': 'ideal boating',
            }
        ]
        html = self._make_html(base_time, normal_conditions_data, forecast_timeline=forecast_timeline)
        assert 'No Wading' in html

    def test_banner_scheduled_alert_high_water(self, base_time, normal_conditions_data):
        """Banner should show scheduled alert when high water is coming."""
        forecast_timeline = [
            {
                'scheduled_time': base_time + timedelta(hours=2),
                'hour': 14, 'mw': 200, 'cfs': 13504,
                'generation_cfs': 13254, 'min_flow_cfs': 250,
                'generators': '4-5 generators',
                'arrival_time': base_time + timedelta(hours=4),
                'wading': 'no wading', 'boating': 'ideal boating',
            }
        ]
        html = self._make_html(base_time, normal_conditions_data, forecast_timeline=forecast_timeline, white_hole_cfs=1500, wading_condition="excellent wading")
        assert 'HIGH WATER SCHEDULED' in html

    def test_banner_no_alert_when_water_already_high(self, base_time, normal_conditions_data):
        """Banner should not show scheduled alert if water is already high."""
        forecast_timeline = [
            {
                'scheduled_time': base_time + timedelta(hours=2),
                'hour': 14, 'mw': 200, 'cfs': 13504,
                'generation_cfs': 13254, 'min_flow_cfs': 250,
                'generators': '4-5 generators',
                'arrival_time': base_time + timedelta(hours=4),
                'wading': 'no wading', 'boating': 'ideal boating',
            }
        ]
        html = self._make_html(base_time, normal_conditions_data, forecast_timeline=forecast_timeline, white_hole_cfs=10000, wading_condition="no wading")
        assert 'HIGH WATER SCHEDULED' not in html
        assert 'HIGHER WATER SCHEDULED' not in html
