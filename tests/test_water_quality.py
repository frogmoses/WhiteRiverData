"""Tests for water_quality.py — USGS tailwater temperature / oxygen."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

import water_quality
from water_quality import (
    parse_water_quality, get_water_quality, describe, do_status, temp_status,
    DO_LOW_MG_L, TEMP_HOT_F,
)

CENTRAL = ZoneInfo("America/Chicago")
NOW = datetime(2026, 9, 20, 19, 30, tzinfo=CENTRAL)


def _series(site, name, param, unit, readings):
    return {
        "sourceInfo": {"siteName": name, "siteCode": [{"value": site}]},
        "variable": {"variableCode": [{"value": param}], "unit": {"unitCode": unit},
                     "noDataValue": -999999.0},
        "values": [{"value": [{"value": v, "qualifiers": ["P"], "dateTime": t}
                              for t, v in readings]}],
    }


def _payload(fairview=True, below_dam=True, fairview_do="4.5"):
    series = []
    if below_dam:
        series += [
            _series("07054502", "below Bull Shoals Dam at Bull Shoals", "00010", "deg C",
                    [("2026-09-20T18:45:00.000-05:00", "14.1"), ("2026-09-20T19:00:00.000-05:00", "14.1")]),
            _series("07054502", "below Bull Shoals Dam at Bull Shoals", "00300", "mg/l",
                    [("2026-09-20T19:00:00.000-05:00", "4.6")]),
        ]
    if fairview:
        series += [
            _series("07054527", "below Bull Shoals Dam near Fairview", "00010", "deg C",
                    [("2026-09-20T19:00:00.000-05:00", "14.6")]),
            _series("07054527", "below Bull Shoals Dam near Fairview", "00300", "mg/l",
                    [("2026-09-20T18:45:00.000-05:00", "4.4"), ("2026-09-20T19:00:00.000-05:00", fairview_do)]),
        ]
    return {"value": {"timeSeries": series}}


class TestParse:
    def test_prefers_the_cane_island_gauge(self):
        wq = parse_water_quality(_payload(), NOW)
        assert wq["site"] == "07054527"
        assert wq["temp_c"] == 14.6 and wq["temp_f"] == 58.3
        assert wq["do_mg_l"] == 4.5
        assert wq["observed"] == datetime(2026, 9, 20, 19, 0, tzinfo=CENTRAL)
        assert abs(wq["age_hours"] - 0.5) < 1e-9
        assert wq["do_status"] == "low" and wq["temp_status"] == "prime"

    def test_falls_back_to_the_below_dam_gauge(self):
        wq = parse_water_quality(_payload(fairview=False), NOW)
        assert wq["site"] == "07054502" and wq["do_mg_l"] == 4.6

    def test_skips_no_data_values(self):
        payload = _payload(below_dam=False, fairview_do="-999999")
        wq = parse_water_quality(payload, NOW)
        # falls back to the earlier good oxygen reading in the same series
        assert wq["do_mg_l"] == 4.4

    def test_none_when_empty_or_malformed(self):
        assert parse_water_quality(None, NOW) is None
        assert parse_water_quality({"value": {"timeSeries": []}}, NOW) is None
        assert parse_water_quality({"junk": 1}, NOW) is None

    def test_partial_reading_keeps_what_it_has(self):
        payload = {"value": {"timeSeries": [
            _series("07054527", "Fairview", "00010", "deg C",
                    [("2026-09-20T19:00:00.000-05:00", "20.5")])]}}
        wq = parse_water_quality(payload, NOW)
        assert wq["temp_f"] == 68.9 and wq["temp_status"] == "hot"
        assert wq["do_mg_l"] is None and wq["do_status"] is None


class TestThresholds:
    def test_oxygen_bands(self):
        assert do_status(DO_LOW_MG_L - 0.1) == "low"
        assert do_status(5.5) == "marginal"
        assert do_status(7.0) == "good"
        assert do_status(None) is None

    def test_temperature_bands(self):
        assert temp_status(45.0) == "cold"
        assert temp_status(55.0) == "prime"
        assert temp_status(64.0) == "warm"
        assert temp_status(TEMP_HOT_F) == "hot"


class TestDescribe:
    def test_lines_carry_value_and_verdict(self):
        wq = parse_water_quality(_payload(), NOW)
        temp_line, do_line = describe(wq)
        assert temp_line.startswith("Water 58.3°F — prime")
        assert do_line.startswith("Oxygen 4.5 mg/L — LOW")

    def test_none_reading(self):
        assert describe(None) == (None, None)


class TestFetch:
    def test_network_failure_returns_none(self):
        # conftest disables the network for every test
        assert get_water_quality(NOW) is None

    def test_fetch_and_parse(self, monkeypatch):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return _payload()

        seen = {}

        def fake_get(url, params=None, timeout=None):
            seen.update(params)
            return Resp()

        monkeypatch.setattr(water_quality.requests, "get", fake_get)
        wq = get_water_quality(NOW)
        assert wq["site"] == "07054527"
        assert "07054527" in seen["sites"] and "07054502" in seen["sites"]
        assert seen["parameterCd"] == "00010,00300"

    def test_bad_json_returns_none(self, monkeypatch):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                raise ValueError("not json")

        monkeypatch.setattr(water_quality.requests, "get", lambda *a, **k: Resp())
        assert get_water_quality(NOW) is None
