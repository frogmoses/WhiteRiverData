"""Unit tests for release_outlook.py (the Corps' days-ahead releases)."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
import requests

import release_outlook
from release_outlook import describe, fetch_daily_series, get_release_outlook

CENTRAL = ZoneInfo("America/Chicago")
NOW = datetime(2026, 10, 5, 16, 30, tzinfo=CENTRAL)


def _ms(year, month, day):
    return int(datetime(year, month, day, tzinfo=CENTRAL).timestamp() * 1000)


class _Resp:
    def __init__(self, values):
        self._values = values

    def raise_for_status(self):
        pass

    def json(self):
        return {"values": self._values}


FORECAST = [[_ms(2026, 10, 6), 2500.0, 0], [_ms(2026, 10, 7), 2000.0, 0],
            [_ms(2026, 10, 8), 2000.0, 0], [_ms(2026, 10, 9), 1999.9999, 0],
            [_ms(2026, 10, 10), 3500.0, 0]]
MEASURED = [[_ms(2026, 10, 4), 896.2, 0], [_ms(2026, 10, 5), 1041.4, 0]]


def _fake_get(url, params=None, **kwargs):
    if params["name"] == release_outlook.FORECAST_SERIES:
        return _Resp(FORECAST)
    return _Resp(MEASURED)


@pytest.mark.unit
class TestDateConvention:
    def test_a_midnight_stamp_is_the_day_that_ends_there(self, monkeypatch):
        """Stamped 06 Oct 00:00 = the average for 05 Oct (the Corps' own -1 day)."""
        monkeypatch.setattr(requests, "get", _fake_get)
        days = fetch_daily_series(release_outlook.FORECAST_SERIES, NOW, NOW)
        assert days[date(2026, 10, 5)] == 2500
        assert date(2026, 10, 10) not in days

    def test_nulls_are_dropped(self, monkeypatch):
        monkeypatch.setattr(requests, "get",
                            lambda *a, **k: _Resp([[_ms(2026, 10, 7), None, 5]]))
        assert fetch_daily_series("x", NOW, NOW) == {}


@pytest.mark.unit
class TestGetReleaseOutlook:
    def test_days_after_today_with_yesterday_for_scale(self, monkeypatch):
        monkeypatch.setattr(requests, "get", _fake_get)
        outlook = get_release_outlook(NOW)
        assert [d['date'] for d in outlook['days']] == [
            date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)]
        assert [d['cfs'] for d in outlook['days']] == [2000, 2000, 2000, 3500]
        assert outlook['yesterday_cfs'] == 1041

    def test_offline_is_none(self):
        assert get_release_outlook(NOW) is None

    def test_no_future_days_is_none(self, monkeypatch):
        monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(FORECAST[:1]))
        assert get_release_outlook(NOW) is None

    def test_missing_yesterday_keeps_the_outlook(self, monkeypatch):
        def get(url, params=None, **kwargs):
            if params["name"] == release_outlook.FORECAST_SERIES:
                return _Resp(FORECAST)
            raise requests.ConnectionError("down")

        monkeypatch.setattr(requests, "get", get)
        outlook = get_release_outlook(NOW)
        assert len(outlook['days']) == 4 and outlook['yesterday_cfs'] is None


@pytest.mark.unit
class TestDescribe:
    DAYS = [{'date': date(2026, 10, 6), 'cfs': 2000}, {'date': date(2026, 10, 7), 'cfs': 2000},
            {'date': date(2026, 10, 8), 'cfs': 2000}, {'date': date(2026, 10, 9), 'cfs': 3500}]

    def test_equal_days_collapse_to_a_range(self):
        line, context = describe({'days': self.DAYS, 'yesterday_cfs': 1041})
        assert line == "Tue–Thu 2,000 · Fri 3,500 CFS"
        assert context.startswith("Yesterday averaged 1,041.")
        assert "not a schedule" in context

    def test_without_yesterday(self):
        _, context = describe({'days': self.DAYS[:1], 'yesterday_cfs': None})
        assert "Yesterday" not in context and "not a schedule" in context

    def test_nothing_to_say(self):
        assert describe(None) == (None, None)
        assert describe({'days': [], 'yesterday_cfs': 900}) == (None, None)
