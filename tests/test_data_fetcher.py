"""Unit tests for data_fetcher.py parsing (no network required)."""
import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from data_fetcher import (
    parse_dam_datetime, parse_table_content, DAM_TIMEZONE,
    save_last_good_data, load_last_good_data, get_error_data
)

CENTRAL = ZoneInfo("America/Chicago")

# Excerpt in the live page's format, including a 2400 (midnight) row and a
# partial row of dashes
SAMPLE_HTML = """
<pre>
              Time    Elevation    Tailwater    Generation    Release    Release    Release
  Date       CS/CDT  (ft-NGVD29)  (ft-NGVD29)     (mwh)        (cfs)      (cfs)      (cfs)
_________________________________________________________________________________________________
<hr>
 23AUG2026    2300     657.91       450.72          8            765          0        765
 23AUG2026    2400     657.90       450.72          8            758          0        758
 24AUG2026    0100     657.91       450.72          8            762          0        762
 24AUG2026    1700     657.91       457.86        317          20707       1000      21707
 24AUG2026    1800       ----         ----       ----           ----        ---        ---
<hr>
</pre>
"""


class TestParseDamDatetime:
    def test_normal_time_is_central(self):
        dt = parse_dam_datetime("24AUG2026", "0100")
        assert dt == datetime(2026, 8, 24, 1, 0, tzinfo=CENTRAL)
        assert dt.tzinfo is DAM_TIMEZONE

    def test_midnight_2400_rolls_to_next_day(self):
        """USACE's '23AUG2026 2400' means midnight entering 24AUG2026."""
        dt = parse_dam_datetime("23AUG2026", "2400")
        assert dt == datetime(2026, 8, 24, 0, 0, tzinfo=CENTRAL)


class TestParseTableContent:
    def test_all_complete_rows_parsed(self):
        data = parse_table_content(SAMPLE_HTML)
        # 4 complete rows; the dashes-only row has no parseable releases
        times = [entry['date_time'] for entry in data]
        assert datetime(2026, 8, 23, 23, 0, tzinfo=CENTRAL) in times
        assert datetime(2026, 8, 24, 1, 0, tzinfo=CENTRAL) in times

    def test_midnight_row_not_dropped(self):
        data = parse_table_content(SAMPLE_HTML)
        midnight = [entry for entry in data
                    if entry['date_time'] == datetime(2026, 8, 24, 0, 0, tzinfo=CENTRAL)]
        assert len(midnight) == 1
        assert midnight[0]['turbine_release'] == 758

    def test_timestamps_are_timezone_aware_central(self):
        data = parse_table_content(SAMPLE_HTML)
        assert data
        for entry in data:
            assert entry['date_time'].tzinfo is DAM_TIMEZONE

    def test_spillway_and_total_release_parsed(self):
        data = parse_table_content(SAMPLE_HTML)
        row = [entry for entry in data
               if entry['date_time'] == datetime(2026, 8, 24, 17, 0, tzinfo=CENTRAL)][0]
        assert row['turbine_release'] == 20707
        assert row['spillway_release'] == 1000
        assert row['total_release'] == 21707


class TestLastGoodDataCache:
    """Cache of the last successful fetch, used when the USACE site is down."""

    def _entry(self, dt, cfs):
        return {'date_time': dt, 'elevation': 657.0, 'tailwater': 450.0,
                'generation': 100, 'turbine_release': cfs,
                'spillway_release': 0, 'total_release': cfs}

    def test_round_trip_preserves_aware_datetimes(self):
        now = datetime(2026, 8, 27, 6, 0, tzinfo=CENTRAL)
        data = [self._entry(now - timedelta(hours=h), 6600) for h in (2, 1)]
        assert save_last_good_data(data)
        loaded = load_last_good_data(current_time=now)
        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0]['date_time'] == data[0]['date_time']
        assert loaded[0]['date_time'].tzinfo is not None
        assert loaded[0]['total_release'] == 6600

    def test_round_trip_preserves_naive_datetimes(self):
        now = datetime(2026, 8, 27, 6, 0)
        data = [self._entry(now - timedelta(hours=1), 3300)]
        assert save_last_good_data(data)
        loaded = load_last_good_data(current_time=now)
        assert loaded is not None
        assert loaded[0]['date_time'] == data[0]['date_time']
        assert loaded[0]['date_time'].tzinfo is None

    def test_missing_cache_returns_none(self):
        assert load_last_good_data() is None

    def test_corrupt_cache_returns_none(self):
        with open("last_good_data.json", "w") as f:
            f.write("not json{{{")
        assert load_last_good_data() is None

    def test_error_sentinel_never_served_from_cache(self):
        save_last_good_data(get_error_data())
        assert load_last_good_data() is None

    def test_cache_older_than_max_age_rejected(self):
        now = datetime(2026, 8, 27, 6, 0, tzinfo=CENTRAL)
        data = [self._entry(now - timedelta(hours=30), 6600)]
        assert save_last_good_data(data)
        assert load_last_good_data(max_age_hours=24, current_time=now) is None

    def test_cache_within_max_age_accepted(self):
        now = datetime(2026, 8, 27, 6, 0, tzinfo=CENTRAL)
        data = [self._entry(now - timedelta(hours=5), 6600)]
        assert save_last_good_data(data)
        assert load_last_good_data(max_age_hours=24, current_time=now) is not None

    def test_mixed_naive_cache_aware_now_rejected(self):
        """A naive cache compared against an aware clock must fail closed."""
        naive_now = datetime(2026, 8, 27, 6, 0)
        data = [self._entry(naive_now - timedelta(hours=1), 3300)]
        assert save_last_good_data(data)
        aware_now = datetime(2026, 8, 27, 6, 0, tzinfo=CENTRAL)
        assert load_last_good_data(current_time=aware_now) is None


class TestDnsFallback:
    """When the local resolver fails, resolve over DoH and pin the IP."""

    SAMPLE_ROW = ("<html><body><hr>\n 21SEP2026    0600     655.40       450.80          8"
                  "            771          0        771\n<hr></body></html>")

    def test_resolve_via_doh_parses_first_a_record(self, monkeypatch):
        import data_fetcher
        import requests

        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"Answer": [{"type": 5, "data": "cname.example."},
                                   {"type": 1, "data": "140.194.204.29"}]}

        seen = {}
        monkeypatch.setattr(requests, "get",
                            lambda url, params=None, headers=None, timeout=None: seen.update(params) or Resp())
        assert data_fetcher.resolve_via_doh("www.swl-wc.usace.army.mil") == "140.194.204.29"
        assert seen["name"] == "www.swl-wc.usace.army.mil" and seen["type"] == "A"

    def test_resolve_via_doh_offline_returns_none(self):
        import data_fetcher
        assert data_fetcher.resolve_via_doh("www.swl-wc.usace.army.mil") is None

    def test_retries_with_pinned_ip_on_dns_failure(self, monkeypatch):
        import data_fetcher
        calls = []

        def fake_fetch(url, extra_args=()):
            calls.append(list(extra_args))
            if len(calls) == 1:
                raise RuntimeError("Page.goto: net::ERR_NAME_NOT_RESOLVED at " + url)
            return self.SAMPLE_ROW

        monkeypatch.setattr(data_fetcher, "_fetch_html", fake_fetch)
        monkeypatch.setattr(data_fetcher, "resolve_via_doh", lambda host: "140.194.204.29")
        data = data_fetcher.get_bull_shoals_data()
        assert calls == [[], ["--host-resolver-rules=MAP www.swl-wc.usace.army.mil 140.194.204.29"]]
        assert data[0]["total_release"] == 771 and not data[0].get("error")

    def test_no_retry_for_other_errors(self, monkeypatch):
        import data_fetcher
        calls = []

        def fake_fetch(url, extra_args=()):
            calls.append(1)
            raise RuntimeError("Page.goto: Timeout 60000ms exceeded")

        monkeypatch.setattr(data_fetcher, "_fetch_html", fake_fetch)
        data = data_fetcher.get_bull_shoals_data()
        assert len(calls) == 1 and data[0]["error"] is True

    def test_dns_failure_without_doh_answer_is_error_data(self, monkeypatch):
        import data_fetcher
        monkeypatch.setattr(data_fetcher, "_fetch_html",
                            lambda url, extra_args=(): (_ for _ in ()).throw(RuntimeError("net::ERR_NAME_NOT_RESOLVED")))
        monkeypatch.setattr(data_fetcher, "resolve_via_doh", lambda host: None)
        assert data_fetcher.get_bull_shoals_data()[0]["error"] is True


@pytest.mark.unit
class TestOutageReason:
    """
    The sentinel says WHY there are no readings: our fetch broke, or the dam
    published a table of dashes (01OCT2026 2050 onward). The page words the
    two differently, so the tag has to survive.
    """

    def test_error_data_defaults_to_fetch_failed(self):
        from data_fetcher import get_error_data, OUTAGE_FETCH_FAILED
        assert get_error_data()[0]['reason'] == OUTAGE_FETCH_FAILED

    def test_error_data_carries_the_given_reason(self):
        from data_fetcher import get_error_data, OUTAGE_NO_DATA_PUBLISHED
        sentinel = get_error_data(OUTAGE_NO_DATA_PUBLISHED)
        assert sentinel[0]['error'] is True
        assert sentinel[0]['reason'] == OUTAGE_NO_DATA_PUBLISHED

    def test_a_page_of_dashes_is_no_data_published_not_a_fetch_failure(self, monkeypatch):
        """The live 2026-10-03 failure: page served fine, every row blank."""
        import data_fetcher
        from data_fetcher import OUTAGE_NO_DATA_PUBLISHED
        dashes = """<pre>
  Date       CS/CDT  (ft-NGVD29)  (ft-NGVD29)     (mwh)        (cfs)      (cfs)      (cfs)
 01OCT2026    2050       ----         ----       ----           ----        ---        ---
 01OCT2026    2150       ----         ----       ----           ----        ---        ---
</pre>"""
        monkeypatch.setattr(data_fetcher, "_fetch_html", lambda *a, **k: dashes)
        result = data_fetcher.get_bull_shoals_data()
        assert result[0]['error'] is True
        assert result[0]['reason'] == OUTAGE_NO_DATA_PUBLISHED

    def test_a_broken_fetch_is_fetch_failed(self, monkeypatch):
        import data_fetcher
        from data_fetcher import OUTAGE_FETCH_FAILED

        def boom(*a, **k):
            raise RuntimeError("net::ERR_CONNECTION_REFUSED")

        monkeypatch.setattr(data_fetcher, "_fetch_html", boom)
        result = data_fetcher.get_bull_shoals_data()
        assert result[0]['reason'] == OUTAGE_FETCH_FAILED


class TestCwmsFallback:
    """
    The CWMS Data API behind the Corps' replacement site carries the same
    readings and held them through the legacy app's Oct 2026 blank spell.
    """

    HOUR = 3600 * 1000
    T0 = int(datetime(2026, 10, 5, 11, 0, tzinfo=CENTRAL).timestamp() * 1000)

    def _series(self):
        t0, t1 = self.T0, self.T0 + self.HOUR
        return {
            'elevation': {t0: 654.2301, t1: 654.2199},
            'tailwater': {t0: 450.84, t1: 450.80},
            'generation': {t0: 8.338, t1: 8.327},
            'turbine_release': {t0: 775.0000933, t1: 20707.2},
            'total_release': {t0: 775.0000933, t1: 21707.1},
        }

    def test_entries_match_the_legacy_row_shape(self):
        from data_fetcher import build_cwms_entries
        first, second = build_cwms_entries(self._series())
        assert first == {
            'date_time': datetime(2026, 10, 5, 11, 0, tzinfo=CENTRAL),
            'elevation': 654.23, 'tailwater': 450.84, 'generation': 8,
            'turbine_release': 775, 'spillway_release': 0, 'total_release': 775,
        }
        assert first['date_time'].tzinfo is DAM_TIMEZONE
        assert second['spillway_release'] == 1000

    def test_an_hour_without_any_flow_is_dropped(self):
        from data_fetcher import build_cwms_entries
        series = self._series()
        series['elevation'][self.T0 + 2 * self.HOUR] = 654.2
        assert len(build_cwms_entries(series)) == 2

    def test_missing_side_series_do_not_sink_the_entry(self):
        from data_fetcher import build_cwms_entries
        entries = build_cwms_entries({'total_release': {self.T0: 775.0}})
        assert entries[0]['total_release'] == 775
        assert entries[0]['turbine_release'] is None
        assert entries[0]['spillway_release'] is None

    def test_fetch_reads_values_and_drops_nulls(self, monkeypatch):
        import requests
        import data_fetcher

        class Resp:
            def raise_for_status(self): pass
            def json(self):
                return {"values": [[1, 775.0, 0], [2, None, 5]]}

        seen = {}

        def fake_get(url, params=None, **kwargs):
            seen.update(params)
            return Resp()

        monkeypatch.setattr(requests, "get", fake_get)
        assert data_fetcher._fetch_cwms_series("X.Flow", "cfs") == {1: 775.0}
        assert seen["office"] == "SWL" and seen["unit"] == "cfs"

    def test_offline_cwms_is_empty_not_an_exception(self):
        import data_fetcher
        assert data_fetcher.get_cwms_data() == []

    def _cwms(self, when):
        return [{'date_time': when, 'elevation': None, 'tailwater': None,
                 'generation': 8, 'turbine_release': 775,
                 'spillway_release': 0, 'total_release': 775}]

    def test_used_when_the_legacy_page_is_all_dashes(self, monkeypatch):
        import data_fetcher
        dashes = "<hr>\n 03OCT2026    0850       ----         ----       ----           ----        ---        ---\n<hr>"
        cwms = self._cwms(datetime.now(CENTRAL))
        monkeypatch.setattr(data_fetcher, "_fetch_html", lambda *a, **k: dashes)
        monkeypatch.setattr(data_fetcher, "get_cwms_data", lambda: cwms)
        assert data_fetcher.get_bull_shoals_data() is cwms

    def test_used_when_the_legacy_fetch_fails(self, monkeypatch):
        import data_fetcher

        def boom(*a, **k):
            raise RuntimeError("net::ERR_CONNECTION_REFUSED")

        cwms = self._cwms(datetime.now(CENTRAL))
        monkeypatch.setattr(data_fetcher, "_fetch_html", boom)
        monkeypatch.setattr(data_fetcher, "get_cwms_data", lambda: cwms)
        assert data_fetcher.get_bull_shoals_data() is cwms

    def test_newer_cwms_replaces_a_stale_legacy_table(self, monkeypatch):
        import data_fetcher
        cwms = self._cwms(datetime.now(CENTRAL))
        monkeypatch.setattr(data_fetcher, "_fetch_html", lambda *a, **k: SAMPLE_HTML)
        monkeypatch.setattr(data_fetcher, "get_cwms_data", lambda: cwms)
        assert data_fetcher.get_bull_shoals_data() is cwms

    def test_stale_legacy_kept_when_cwms_is_no_newer(self, monkeypatch):
        import data_fetcher
        cwms = self._cwms(datetime(2026, 8, 1, tzinfo=CENTRAL))
        monkeypatch.setattr(data_fetcher, "_fetch_html", lambda *a, **k: SAMPLE_HTML)
        monkeypatch.setattr(data_fetcher, "get_cwms_data", lambda: cwms)
        assert len(data_fetcher.get_bull_shoals_data()) == 4

    def test_fresh_legacy_never_asks_cwms(self, monkeypatch):
        import data_fetcher
        now = datetime.now(CENTRAL)
        row = f" {now.strftime('%d%b%Y').upper()}    {now.strftime('%H')}00     654.21       450.77          7            660          0        660"

        def unexpected():
            raise AssertionError("CWMS queried while the legacy table is fresh")

        monkeypatch.setattr(data_fetcher, "_fetch_html", lambda *a, **k: f"<hr>\n{row}\n<hr>")
        monkeypatch.setattr(data_fetcher, "get_cwms_data", unexpected)
        assert data_fetcher.get_bull_shoals_data()[0]['total_release'] == 660


class TestUnitsRunning:
    """Units actually running, counted from the eight per-turbine flow series."""

    T0 = int(datetime(2026, 10, 4, 17, 0, tzinfo=CENTRAL).timestamp() * 1000)
    T1 = T0 + 3600 * 1000

    def _patch_series(self, monkeypatch, flows_by_unit):
        import data_fetcher

        def fake(name, unit, timeout=30):
            n = int(name.split("Turbine")[1].split(".")[0])
            return flows_by_unit[n - 1]

        monkeypatch.setattr(data_fetcher, "_fetch_cwms_series", fake)

    def test_counts_units_with_flow(self, monkeypatch):
        import data_fetcher
        flows = [{self.T0: 0.0, self.T1: 0.0}] * 5 + [
            {self.T0: 922.0, self.T1: 0.0}, {self.T0: 947.0, self.T1: 673.0},
            {self.T0: 1152.0, self.T1: 0.0}]
        self._patch_series(monkeypatch, flows)
        units = data_fetcher.get_units_running()
        assert units[datetime(2026, 10, 4, 17, 0, tzinfo=CENTRAL)] == 3
        assert units[datetime(2026, 10, 4, 18, 0, tzinfo=CENTRAL)] == 1

    def test_an_hour_missing_a_unit_is_not_counted(self, monkeypatch):
        import data_fetcher
        flows = [{self.T0: 2000.0, self.T1: 2000.0}] * 7 + [{self.T0: 2000.0}]
        self._patch_series(monkeypatch, flows)
        units = data_fetcher.get_units_running()
        assert list(units.values()) == [8]

    def test_offline_is_empty(self):
        import data_fetcher
        assert data_fetcher.get_units_running() == {}

    def test_annotate_tags_only_matching_hours(self):
        from data_fetcher import annotate_units_running
        known = datetime(2026, 10, 4, 17, 0, tzinfo=CENTRAL)
        data = [{'date_time': known}, {'date_time': known + timedelta(hours=1)}]
        annotate_units_running(data, {known: 3})
        assert data[0]['units_running'] == 3
        assert 'units_running' not in data[1]

    def test_literal_matches_formatters(self):
        import data_fetcher
        import formatters
        assert formatters.TURBINE_COUNT == data_fetcher.TURBINE_COUNT
