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

    def _hour(self, base_time, h, cfs, wading='excellent wading'):
        return {
            'scheduled_time': base_time + timedelta(hours=h),
            'hour': h, 'mw': 7, 'cfs': cfs,
            'generation_cfs': max(cfs - 250, 0), 'min_flow_cfs': 250,
            'generators': '0-1 generators',
            'arrival_time': base_time + timedelta(hours=h + 3.7),
            'wading': wading, 'boating': 'low for boating',
        }

    def test_forecast_shows_whole_schedule_grouped(self, base_time, normal_conditions_data):
        """Regression: the old 4-row cap hid the afternoon surge behind four
        rows of the same morning flow. The whole schedule renders, with
        consecutive same-flow hours collapsed into one run."""
        forecast_timeline = (
            [self._hour(base_time, h, 723) for h in range(1, 7)]
            + [self._hour(base_time, 7, 8352, 'no wading')]
            + [self._hour(base_time, h, 19493, 'no wading') for h in range(8, 11)]
        )
        html = self._make_html(base_time, normal_conditions_data, forecast_timeline=forecast_timeline)
        assert html.count('faf5ff') == 3
        assert '19,493 CFS' in html
        assert '8,352 CFS' in html
        # A run is labelled with its span, a single hour with its start
        assert f"{(base_time + timedelta(hours=1)).strftime('%I %p').lstrip('0')}–" in html

    def test_forecast_rows_are_chronological_with_tomorrow_divider(self, base_time, normal_conditions_data):
        forecast_timeline = [
            self._hour(base_time, 20, 723),
            self._hour(base_time, 26, 8352, 'no wading'),  # 02:00 tomorrow
        ]
        html = self._make_html(base_time, normal_conditions_data, forecast_timeline=forecast_timeline)
        tomorrow = base_time + timedelta(days=1)
        assert tomorrow.strftime('%A') in html
        table = html[html.index('Scheduled (SWPA forecast)'):]
        assert table.index('723 CFS') < table.index('8,352 CFS')
        # Times on the other day carry a weekday prefix
        assert tomorrow.strftime('%a') in html

    def test_falling_forecast_row_shows_recession_window(self, base_time, normal_conditions_data):
        high = self._hour(base_time, 1, 17464, 'no wading')
        low = self._hour(base_time, 2, 5989, 'no wading')
        low['change'] = 'falling'
        low['recession_start'] = low['arrival_time'] - timedelta(minutes=30)
        html = self._make_html(base_time, normal_conditions_data, forecast_timeline=[high, low])
        start = low['recession_start'].strftime('%I:%M %p').lstrip('0')
        down = low['arrival_time'].strftime('%I:%M %p').lstrip('0')
        assert f'falling ~{start}, down ~{down}' in html

    def test_short_recession_window_collapses_to_one_time(self, base_time, normal_conditions_data):
        low = self._hour(base_time, 2, 750)
        low['change'] = 'falling'
        low['recession_start'] = low['arrival_time'] - timedelta(minutes=2)
        html = self._make_html(base_time, normal_conditions_data, forecast_timeline=[low])
        assert 'falling ~' not in html

    def test_scheduled_alert_names_the_peak_and_day(self, base_time, normal_conditions_data):
        forecast_timeline = [
            self._hour(base_time, 3, 8352, 'no wading'),
            self._hour(base_time, 27, 19493, 'no wading'),
        ]
        html = self._make_html(base_time, normal_conditions_data, forecast_timeline=forecast_timeline)
        assert 'HIGH WATER SCHEDULED' in html
        assert 'peaking near 19,493 CFS' in html

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

    def test_alert_prefers_high_water_over_earlier_moderate_hour(self, base_time, normal_conditions_data):
        """Regression: an early >=2000 CFS hour must not mask a later >=5000
        CFS hour — the banner should show the most severe scheduled level."""
        def hour(h, cfs):
            return {
                'scheduled_time': base_time + timedelta(hours=h),
                'hour': h, 'mw': 40, 'cfs': cfs,
                'generation_cfs': cfs - 250, 'min_flow_cfs': 250,
                'generators': '1-2 generators',
                'arrival_time': base_time + timedelta(hours=h + 3),
                'wading': 'still wadable', 'boating': 'ideal boating',
            }
        forecast_timeline = [hour(1, 2500), hour(3, 8000)]
        html = self._make_html(base_time, normal_conditions_data,
                               forecast_timeline=forecast_timeline,
                               white_hole_cfs=1500,
                               wading_condition="excellent wading")
        assert 'HIGH WATER SCHEDULED' in html
        assert 'HIGHER WATER SCHEDULED' not in html

    def test_rising_banner_uses_the_plug_that_rises(self, base_time, normal_conditions_data):
        """Regression (live page 2026-09-20 08:00): a same-level plug 43 min
        out was reported as the rise while the real rise was 162 min out."""
        timeline_data = [
            {'release_time': base_time - timedelta(hours=3), 'cfs': 779,
             'generators': '0-1 generators', 'arrival_time': base_time + timedelta(minutes=43),
             'status': 'incoming', 'minutes_until': 43, 'change': None, 'recession_start': None},
            {'release_time': base_time - timedelta(hours=1), 'cfs': 1708,
             'generators': '0-1 generators', 'arrival_time': base_time + timedelta(minutes=162),
             'status': 'incoming', 'minutes_until': 162, 'change': 'rising', 'recession_start': None},
        ]
        html = generate_html_summary(
            current_time=base_time, white_hole_cfs=771, generators_equivalent=0.2,
            water_state="rising", wading_condition="excellent wading",
            boating_condition="low for boating", recent_trend="increased",
            forecast="rising water expected soon",
            latest_entry=normal_conditions_data[0], relevant_entry=normal_conditions_data[0],
            recent_data=normal_conditions_data, timeline_data=timeline_data,
        )
        assert 'RISING WATER arriving in ~162 minutes (1,708 CFS)' in html
        assert '~43 minutes' not in html

    def test_falling_banner_shows_recession_window(self, base_time, normal_conditions_data):
        start = base_time + timedelta(minutes=81)
        down = base_time + timedelta(minutes=111)
        timeline_data = [
            {'release_time': base_time - timedelta(hours=1), 'cfs': 5989,
             'generators': '1-2 generators', 'arrival_time': down,
             'status': 'incoming', 'minutes_until': 111, 'change': 'falling',
             'recession_start': start},
        ]
        html = generate_html_summary(
            current_time=base_time, white_hole_cfs=14331, generators_equivalent=4.3,
            water_state="falling", wading_condition="no wading",
            boating_condition="high water", recent_trend="decreased",
            forecast="falling water expected soon",
            latest_entry=normal_conditions_data[0], relevant_entry=normal_conditions_data[0],
            recent_data=normal_conditions_data, timeline_data=timeline_data,
        )
        s = start.strftime('%I:%M %p').lstrip('0')
        d = down.strftime('%I:%M %p').lstrip('0')
        assert f'FALLING WATER — starts dropping ~{s}, fully down ~{d}' in html
        assert f'Falls from ~{s}, fully down ~{d}' in html

    def test_rising_banner_handles_zero_minutes_until(self, base_time, normal_conditions_data):
        """Regression: minutes_until == 0 (arriving now) is real data, not
        a missing value — the banner should show it, not fall back."""
        timeline_data = [
            {
                'release_time': base_time - timedelta(hours=2),
                'cfs': 10000, 'generators': '3 generators',
                'arrival_time': base_time,
                'status': 'incoming', 'minutes_until': 0
            }
        ]
        html = generate_html_summary(
            current_time=base_time,
            white_hole_cfs=1500,
            generators_equivalent=1500 / 3300,
            water_state="rising",
            wading_condition="excellent wading",
            boating_condition="low for boating",
            recent_trend="steady",
            forecast="rising water expected soon",
            latest_entry=normal_conditions_data[0],
            relevant_entry=normal_conditions_data[0],
            recent_data=normal_conditions_data,
            timeline_data=timeline_data,
            forecast_timeline=None,
        )
        assert 'RISING WATER arriving in ~0 minutes' in html


class TestLandmarkMapLinks:
    """The flow page's chart section links every landmark to its map pin."""

    def test_all_landmarks_linked(self, base_time, normal_conditions_data):
        from landmarks import LANDMARK_COORDS
        html = generate_html_summary(
            current_time=base_time,
            white_hole_cfs=6600,
            generators_equivalent=2.0,
            water_state="stable",
            wading_condition="no wading",
            boating_condition="ideal boating",
            recent_trend="steady",
            forecast="stable conditions expected",
            latest_entry=normal_conditions_data[0],
            relevant_entry=normal_conditions_data[0],
        )
        for name, (lat, lon) in LANDMARK_COORDS:
            assert f"https://www.google.com/maps?q={lat},{lon}" in html
        assert html.count("google.com/maps?q=") == len(LANDMARK_COORDS)


class TestCopyrightNotice:
    def test_notice_in_page_footer(self, base_time, normal_conditions_data):
        html = generate_html_summary(
            current_time=base_time,
            white_hole_cfs=6600,
            generators_equivalent=2.0,
            water_state="stable",
            wading_condition="no wading",
            boating_condition="ideal boating",
            recent_trend="steady",
            forecast="stable conditions expected",
            latest_entry=normal_conditions_data[0],
            relevant_entry=normal_conditions_data[0],
        )
        assert f"&copy; {base_time.year} Brian Carroll. All rights reserved." in html


class TestFeedFailedBanner:
    """The live-feed-unavailable banner shown when serving cached data."""

    def _summary_kwargs(self, base_time):
        entry = {'date_time': base_time - timedelta(hours=2),
                 'turbine_release': 6600}
        return dict(
            current_time=base_time,
            white_hole_cfs=6600,
            generators_equivalent=2.0,
            water_state="stable",
            wading_condition="still wadable",
            boating_condition="ideal boating",
            recent_trend="remained relatively steady",
            forecast="stable conditions expected",
            latest_entry=entry,
            relevant_entry=entry,
        )

    def test_html_banner_shown_when_feed_failed(self, base_time):
        html = generate_html_summary(
            **self._summary_kwargs(base_time), feed_failed=True)
        assert "LIVE DAM FEED UNAVAILABLE" in html

    def test_html_banner_absent_by_default(self, base_time):
        html = generate_html_summary(**self._summary_kwargs(base_time))
        assert "LIVE DAM FEED UNAVAILABLE" not in html

    def test_text_warning_shown_when_feed_failed(self, base_time):
        text = generate_text_summary(
            **self._summary_kwargs(base_time), feed_failed=True)
        assert "Live dam feed unavailable" in text

    def test_feed_failed_and_stale_warnings_coexist(self, base_time):
        text = generate_text_summary(
            **self._summary_kwargs(base_time), feed_failed=True, stale_hours=5.0)
        assert "Live dam feed unavailable" in text
        assert "5.0 hours old" in text


class TestWaterQualityBlock:
    WQ = {"site": "07054527", "site_label": "USGS gauge at Cane Island",
          "temp_c": 14.6, "temp_f": 58.3, "do_mg_l": 4.5,
          "observed": None, "age_hours": 0.5, "do_status": "low", "temp_status": "prime"}

    def _html(self, base_time, normal_conditions_data, wq):
        return generate_html_summary(
            current_time=base_time, white_hole_cfs=750, generators_equivalent=0.2,
            water_state="stable", wading_condition="excellent wading",
            boating_condition="low for boating", recent_trend="steady",
            forecast="stable conditions expected",
            latest_entry=normal_conditions_data[0], relevant_entry=normal_conditions_data[0],
            recent_data=normal_conditions_data, timeline_data=[], water_quality=wq)

    def test_pills_and_source(self, base_time, normal_conditions_data):
        wq = dict(self.WQ, observed=base_time - timedelta(minutes=30))
        html = self._html(base_time, normal_conditions_data, wq)
        assert "Water 58.3°F" in html and "Oxygen 4.5 mg/L" in html
        assert "LOW" in html
        assert "USGS-07054527" in html
        assert "as of" in html and "h old" not in html

    def test_stale_reading_shows_age(self, base_time, normal_conditions_data):
        wq = dict(self.WQ, observed=base_time - timedelta(hours=5), age_hours=5.0)
        html = self._html(base_time, normal_conditions_data, wq)
        assert "reading is 5.0 h old" in html

    def test_absent_without_reading(self, base_time, normal_conditions_data):
        html = self._html(base_time, normal_conditions_data, None)
        assert "Tailwater" not in html

    def test_text_summary_carries_lines(self, base_time, normal_conditions_data):
        wq = dict(self.WQ, observed=base_time)
        text = generate_text_summary(
            current_time=base_time, white_hole_cfs=750, generators_equivalent=0.2,
            water_state="stable", wading_condition="excellent wading",
            boating_condition="low for boating", recent_trend="steady",
            forecast="stable conditions expected",
            latest_entry=normal_conditions_data[0], relevant_entry=normal_conditions_data[0],
            water_quality=wq)
        assert "Water 58.3°F" in text and "Oxygen 4.5 mg/L" in text


class TestSunLine:
    def test_sunrise_and_sunset_on_the_page(self, base_time, normal_conditions_data):
        html = generate_html_summary(
            current_time=base_time, white_hole_cfs=750, generators_equivalent=0.2,
            water_state="stable", wading_condition="excellent wading",
            boating_condition="low for boating", recent_trend="steady",
            forecast="stable conditions expected",
            latest_entry=normal_conditions_data[0], relevant_entry=normal_conditions_data[0],
            recent_data=normal_conditions_data, timeline_data=[])
        assert "Sunrise" in html and "Sunset" in html
        assert "dawn until" in html and "dusk from" in html
