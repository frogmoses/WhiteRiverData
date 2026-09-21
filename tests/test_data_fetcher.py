"""Unit tests for data_fetcher.py parsing (no network required)."""
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
