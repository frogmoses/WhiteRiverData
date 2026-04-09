"""Tests for forecast_fetcher.py"""
from datetime import datetime, timedelta
import pytest
from forecast_fetcher import (
    mw_to_cfs,
    parse_schedule_html,
    get_swpa_schedule_url,
    get_schedule_date_from_html,
    BSD_FULL_MW,
    BSD_FULL_CFS,
    BSD_MIN_FLOW_CFS,
)

# Sample SWPA schedule HTML matching the real page format
SAMPLE_SCHEDULE_HTML = """<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 3.2//EN">
<HTML>
  <HEAD>
    <TITLE>Generation Schedule,WEDNESDAY,APRIL 08, 2026</TITLE>
  </HEAD>
  <BODY bgcolor='white'>
    <PRE>

                           SOUTHWESTERN POWER ADMINISTRATION  -  GENERATION SCHEDULE

PROJECTED LOADING SCHEDULE                             WEDNESDAY APRIL 08, 2026           CALICO ROCK TEMP:  N/A

        1     2     3     4     5     6     7     8     9    10    11    12    13    14    15    16    17    18
 HR   BBD   DEN   KEY   FGD   WFD   TKD   EUF   RSK   OZK   DAD   BEV   TRD   BSD   NFD   GFD   STD   HST   CAN
  1     0    90     0    35    20     0     0     0     0     0     0     0     7     4     0     0    90    30
  2     0    90     0    35    20     0     0     0     0     0     0     0     7     4     0     0    90    30
  3     0    90     0    35    20     0     0    28     0     0     0     0     7     4     0     0    90    30
  4     0    90     0    35    20     0     0    72    60   105     0     0     7     4     0     0    90    30
  5     0    90     0    35    20    40     0    72    60   105     0     0     7     4     0     0    90    30
  6     0    90     0    35    20    40     0    72    60   105     0     0     7     4     0     0    90    30

  7     0    90     0    35    20    40     0    72    60   105     0     0     7     4     0     0    90    30
  8     0    90     0    35    20    40     0    72    60   105     0     0     7     4     0     0    90    30
  9     0    90     0    35    20    40     0    72    60   105     0     0     7     4     0     0    90    30
 10     0    90     0    35    20    40     0    72    60   105     0     0     7     4     0     0    90    30
 11     0    90     0    35    20    40     0    72    60   105     0     0     7     4     0     0    90    30
 12     0    90     0    35    20    40     0    72    60   105     0     0     7     4     0     0    90    30

 13     0    90     0    35    20    40     0    72     0   105     0     0     7     4     0     0    90    30
 14     0    90     0    35    20    40     0    72     0   105     0     0     7     4     0     0    90    30
 15     0    90     0    35    20    40     0    72    60   105     0     0     7     4     0     0    90    30
 16     0    90     0    35    20    40     0    72    60   105     0     0     7     4     0     0    90    30
 17     0    90     0    35    20    40     0    72    60   105     0     0     7     4     0     0    90    30
 18     0    90     0    35    20    40     0    72    60   105     0     0     7     4     0     0    90    30

 19     0    90     0    35    20    40    30    72    60   105     0   100     7    40     0     0    90    30
 20   100    90     0    35    20    40    60    72    60   105     0     0    40    40     0     0    90    30
 21     0    90     0    35    20     0     0    72    60   105     0     0     7     4     0     0    90    30
 22     0    90     0    35    20     0     0    28    60   105     0     0     7     4     0     0    90    30
 23     0    90     0    35    20     0     0     0     0     0     0     0     7     4     0     0    60    30
 24     0    90     0    35    20     0     0     0     0     0     0     0     7     4     0     0    60    30

TOT   100  2160     0   840   480   640    90  1352  1020  1995     0   100   201   168     0     0  2100   720

    </PRE>
  </BODY>
</HTML>"""


class TestMwToCfs:
    """Tests for MW to CFS conversion."""

    def test_full_capacity_with_base_flow(self):
        assert mw_to_cfs(BSD_FULL_MW) == BSD_FULL_CFS + BSD_MIN_FLOW_CFS

    def test_full_capacity_without_base_flow(self):
        assert mw_to_cfs(BSD_FULL_MW, include_base_flow=False) == BSD_FULL_CFS

    def test_zero_with_base_flow(self):
        assert mw_to_cfs(0) == BSD_MIN_FLOW_CFS

    def test_zero_without_base_flow(self):
        assert mw_to_cfs(0, include_base_flow=False) == 0

    def test_small_value(self):
        cfs = mw_to_cfs(7)
        expected = int(round((7 / 391) * 26400)) + BSD_MIN_FLOW_CFS
        assert cfs == expected

    def test_half_capacity(self):
        cfs = mw_to_cfs(195.5)
        assert cfs == int(round((195.5 / 391) * 26400)) + BSD_MIN_FLOW_CFS

    def test_negative_returns_base_flow(self):
        assert mw_to_cfs(-10) == BSD_MIN_FLOW_CFS


class TestParseScheduleHtml:
    """Tests for parsing SWPA schedule HTML."""

    def test_parses_all_24_hours(self):
        target_date = datetime(2026, 4, 8)
        result = parse_schedule_html(SAMPLE_SCHEDULE_HTML, target_date)
        assert len(result) == 24

    def test_hour_values(self):
        target_date = datetime(2026, 4, 8)
        result = parse_schedule_html(SAMPLE_SCHEDULE_HTML, target_date)
        hours = [entry['hour'] for entry in result]
        assert hours == list(range(1, 25))

    def test_bsd_low_generation(self):
        """Most hours have 7 MW for BSD."""
        target_date = datetime(2026, 4, 8)
        result = parse_schedule_html(SAMPLE_SCHEDULE_HTML, target_date)
        hour_1 = result[0]
        assert hour_1['mw'] == 7
        assert hour_1['generation_cfs'] == int(round((7 / 391) * 26400))
        assert hour_1['cfs'] == hour_1['generation_cfs'] + BSD_MIN_FLOW_CFS

    def test_bsd_high_generation(self):
        """Hour 20 has 40 MW for BSD."""
        target_date = datetime(2026, 4, 8)
        result = parse_schedule_html(SAMPLE_SCHEDULE_HTML, target_date)
        hour_20 = result[19]  # 0-indexed
        assert hour_20['mw'] == 40
        assert hour_20['generation_cfs'] == 2701
        assert hour_20['cfs'] == 2701 + BSD_MIN_FLOW_CFS

    def test_hour_ending_times(self):
        """Hour 1 should be 00:00-01:00, hour 20 should be 19:00-20:00."""
        target_date = datetime(2026, 4, 8)
        result = parse_schedule_html(SAMPLE_SCHEDULE_HTML, target_date)

        assert result[0]['start_time'] == datetime(2026, 4, 8, 0, 0)
        assert result[0]['end_time'] == datetime(2026, 4, 8, 1, 0)

        assert result[19]['start_time'] == datetime(2026, 4, 8, 19, 0)
        assert result[19]['end_time'] == datetime(2026, 4, 8, 20, 0)

    def test_empty_html_returns_empty(self):
        result = parse_schedule_html("<html><body></body></html>")
        assert result == []

    def test_no_pre_tag_returns_empty(self):
        result = parse_schedule_html("<html><body><p>No data</p></body></html>")
        assert result == []

    def test_each_entry_has_required_keys(self):
        target_date = datetime(2026, 4, 8)
        result = parse_schedule_html(SAMPLE_SCHEDULE_HTML, target_date)
        for entry in result:
            assert 'hour' in entry
            assert 'mw' in entry
            assert 'cfs' in entry
            assert 'generation_cfs' in entry
            assert 'min_flow_cfs' in entry
            assert 'start_time' in entry
            assert 'end_time' in entry


class TestGetSwpaScheduleUrl:
    """Tests for URL generation."""

    def test_wednesday(self):
        wed = datetime(2026, 4, 8)  # Wednesday
        url = get_swpa_schedule_url(wed)
        assert url.endswith("/wed.htm")

    def test_monday(self):
        mon = datetime(2026, 4, 6)  # Monday
        url = get_swpa_schedule_url(mon)
        assert url.endswith("/mon.htm")

    def test_sunday(self):
        sun = datetime(2026, 4, 12)  # Sunday
        url = get_swpa_schedule_url(sun)
        assert url.endswith("/sun.htm")


class TestGetScheduleDateFromHtml:
    """Tests for extracting date from schedule HTML."""

    def test_extracts_date(self):
        result = get_schedule_date_from_html(SAMPLE_SCHEDULE_HTML)
        assert result == datetime(2026, 4, 8)

    def test_no_title_returns_none(self):
        result = get_schedule_date_from_html("<html><body></body></html>")
        assert result is None

    def test_bad_title_returns_none(self):
        result = get_schedule_date_from_html("<html><head><title>Bad Title</title></head></html>")
        assert result is None
