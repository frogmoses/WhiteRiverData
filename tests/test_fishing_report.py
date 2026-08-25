"""Tests for fishing_report.py — flow-driven fishing report."""
from datetime import datetime, timedelta
import pytest

from fishing_report import (
    get_flow_band,
    get_trip_season,
    spot_arrival_times,
    generate_fishing_report,
    render_fishing_report_html,
    build_timing,
    REACH_SPOTS,
    WHITE_HOLE_MILE,
)
from water_calculator import calculate_travel_time
from main import generate_white_hole_summary


OCTOBER = datetime(2026, 10, 5, 12, 0)
APRIL = datetime(2026, 4, 6, 12, 0)
JULY = datetime(2026, 7, 6, 12, 0)


class TestFlowBands:
    """Band boundaries align with the repo's condition thresholds."""

    def test_band_boundaries(self):
        assert get_flow_band(750) == "minimum"
        assert get_flow_band(1999) == "minimum"
        assert get_flow_band(2000) == "one_unit"
        assert get_flow_band(4999) == "one_unit"
        assert get_flow_band(5000) == "two_three_units"
        assert get_flow_band(9999) == "two_three_units"
        assert get_flow_band(10000) == "four_five_units"
        assert get_flow_band(16499) == "four_five_units"
        assert get_flow_band(16500) == "high"
        assert get_flow_band(26400) == "high"


class TestSeasonGating:
    def test_trip_windows(self):
        assert get_trip_season(datetime(2026, 3, 15)) == "spring"
        assert get_trip_season(APRIL) == "spring"
        assert get_trip_season(datetime(2026, 9, 20)) == "fall"
        assert get_trip_season(OCTOBER) == "fall"

    def test_off_season_months(self):
        for month in (1, 2, 5, 6, 7, 8, 11, 12):
            assert get_trip_season(datetime(2026, month, 10)) is None

    def test_off_season_report_is_placeholder(self):
        report = generate_fishing_report(750, JULY)
        assert report["active"] is False
        assert "trip windows" in report["placeholder"]

    def test_off_season_html_renders_placeholder(self):
        html = render_fishing_report_html(generate_fishing_report(750, JULY))
        assert "Fishing Report" in html
        assert "trip windows" in html


class TestSpotArrivals:
    """ETAs must come from the repo's travel model, scaled by river mile."""

    def test_white_hole_eta_matches_travel_model(self):
        release = OCTOBER
        cfs = 6600
        etas = dict(spot_arrival_times(release, cfs))
        expected = release + timedelta(hours=calculate_travel_time(cfs))
        assert abs((etas["White Hole"] - expected).total_seconds()) < 1

    def test_spots_ordered_downstream(self):
        etas = [eta for _, eta in spot_arrival_times(OCTOBER, 6600)]
        assert etas == sorted(etas)

    def test_narrows_beyond_white_hole(self):
        etas = dict(spot_arrival_times(OCTOBER, 6600))
        assert etas["The Narrows"] > etas["White Hole"]
        assert etas["Gaston's"] < etas["White Hole"]

    def test_spot_miles(self):
        miles = dict(REACH_SPOTS)
        assert miles["Gaston's"] == 4.0
        assert miles["White Hole"] == WHITE_HOLE_MILE == 7.0
        assert miles["The Narrows"] == 9.5


class TestReportStructure:
    def test_active_report_has_all_sections(self):
        report = generate_fishing_report(750, OCTOBER)
        assert report["active"] is True
        for key in ("band_label", "summary", "where", "boat", "timing",
                    "spin", "fly", "season_notes", "regulations", "gear_check"):
            assert report[key]

    def test_band_follows_cfs(self):
        assert generate_fishing_report(750, OCTOBER)["band"] == "minimum"
        assert generate_fishing_report(12000, OCTOBER)["band"] == "four_five_units"

    def test_season_content_differs(self):
        fall = generate_fishing_report(750, OCTOBER)
        spring = generate_fishing_report(750, APRIL)
        assert fall["season"] == "fall"
        assert spring["season"] == "spring"
        assert fall["season_notes"] != spring["season_notes"]

    def test_regulations_present(self):
        report = generate_fishing_report(3300, OCTOBER)
        regs = " ".join(report["regulations"])
        assert "single hooking point" in regs
        assert "2 rainbows under 14" in regs


class TestSpinFlySeparation:
    """Spin and fly content must never intermingle."""

    @pytest.mark.parametrize("cfs", [750, 3300, 6600, 12000, 20000])
    def test_sections_render_separately(self, cfs):
        html = render_fishing_report_html(generate_fishing_report(cfs, OCTOBER))
        assert "Spin Fishing" in html
        assert "Fly Fishing" in html
        # Isolate the two blocks: spin runs until the fly header, fly runs
        # until the season-notes section
        spin_block = html.split("Spin Fishing", 1)[1].split("Fly Fishing", 1)[0]
        fly_block = html.split("Fly Fishing", 1)[1].split("Season notes", 1)[0]
        # Fly-only vocabulary stays out of the spin block
        assert "Woolly Bugger" not in spin_block
        assert "Zebra Midge" not in spin_block
        assert "tippet" not in spin_block
        # Spin-only vocabulary stays out of the fly block
        assert "PowerBait" not in fly_block
        assert "Kastmaster" not in fly_block
        assert "Rooster Tail" not in fly_block
        assert "White River rig" not in fly_block

    def test_high_band_fly_rod_cased(self):
        report = generate_fishing_report(20000, OCTOBER)
        assert "cased" in report["fly"]["setup"]
        assert report["fly"]["flies"] == []


class TestTiming:
    def test_rise_en_route_from_actual_timeline(self):
        timeline_data = [{
            "release_time": OCTOBER - timedelta(hours=1),
            "cfs": 12000, "generators": "3-4 generators",
            "arrival_time": OCTOBER + timedelta(hours=1.5),
            "status": "incoming", "minutes_until": 90,
        }]
        timing = " ".join(build_timing(750, OCTOBER, timeline_data, None))
        assert "RISE EN ROUTE" in timing
        assert "12,000" in timing

    def test_scheduled_rise_uses_travel_model(self):
        scheduled = OCTOBER + timedelta(hours=2)
        forecast = [{
            "scheduled_time": scheduled, "cfs": 13504,
            "arrival_time": scheduled + timedelta(hours=2.4),
        }]
        timing = " ".join(build_timing(750, OCTOBER, None, forecast))
        assert "SCHEDULED RISE" in timing
        # White Hole ETA in the message must match the repo travel model
        expected = scheduled + timedelta(hours=calculate_travel_time(13504))
        assert expected.strftime("%I:%M %p").lstrip("0") in timing

    def test_scheduled_drop_detected(self):
        scheduled = OCTOBER + timedelta(hours=1)
        forecast = [{
            "scheduled_time": scheduled, "cfs": 750,
            "arrival_time": scheduled + timedelta(hours=3.7),
        }]
        timing = " ".join(build_timing(13000, OCTOBER, None, forecast))
        assert "SCHEDULED DROP" in timing

    def test_no_change_no_alerts(self):
        forecast = [{
            "scheduled_time": OCTOBER + timedelta(hours=1), "cfs": 800,
            "arrival_time": OCTOBER + timedelta(hours=4),
        }]
        timing = " ".join(build_timing(750, OCTOBER, None, forecast))
        assert "SCHEDULED" not in timing
        assert "EN ROUTE" not in timing


class TestPageIntegration:
    def _entry(self, dt, cfs):
        return {"date_time": dt, "elevation": 657.0, "tailwater": 450.0,
                "generation": 100, "turbine_release": cfs,
                "spillway_release": 0, "total_release": cfs}

    def test_report_at_bottom_of_page_in_trip_window(self):
        data = [self._entry(OCTOBER - timedelta(hours=h), 750)
                for h in range(6, 0, -1)]
        html = generate_white_hole_summary(
            output_format="html", data=data, current_time=OCTOBER)
        assert "Fishing Report" in html
        assert "Spin Fishing" in html
        assert "Fly Fishing" in html
        # Renders after the timeline/details sections (bottom of the page)
        assert html.index("Fishing Report") > html.index("Water Timeline")

    def test_placeholder_on_page_off_season(self):
        data = [self._entry(JULY - timedelta(hours=h), 750)
                for h in range(6, 0, -1)]
        html = generate_white_hole_summary(
            output_format="html", data=data, current_time=JULY)
        assert "Fishing Report" in html
        assert "trip windows" in html
        assert "Spin Fishing" not in html
