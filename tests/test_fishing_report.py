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

    def test_effective_season_previews_upcoming_window(self):
        from fishing_report import get_effective_season
        for month in (5, 6, 7, 8):
            assert get_effective_season(datetime(2026, month, 10)) == ("fall", False)
        for month in (11, 12, 1, 2):
            assert get_effective_season(datetime(2026, month, 10)) == ("spring", False)
        assert get_effective_season(OCTOBER) == ("fall", True)
        assert get_effective_season(APRIL) == ("spring", True)

    def test_off_season_report_is_full_preview(self):
        """Off-window months render the upcoming window's full playbook."""
        report = generate_fishing_report(750, JULY)
        assert report["in_window"] is False
        assert report["season"] == "fall"
        assert report["spin"]["browns"] and report["fly"]["rainbows"]

    def test_off_season_html_carries_preview_note(self):
        html = render_fishing_report_html(generate_fishing_report(750, JULY))
        assert "Off-season preview" in html
        assert "September–October" in html
        assert "Spin Fishing" in html

    def test_in_window_has_no_preview_note(self):
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        assert "Off-season preview" not in html

    def test_report_is_collapsed_by_default(self):
        """The whole report is a <details> block with no open attribute,
        and the summary line carries the band and flow."""
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        assert '<details class="timeline-box">' in html
        first_tag = html.split(">", 1)[0]
        assert "open" not in first_tag
        summary = html.split("</summary>", 1)[0]
        assert "Minimum flow (dead low)" in summary
        assert "750 CFS" in summary


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

    def test_cranors_island_beyond_white_hole(self):
        etas = dict(spot_arrival_times(OCTOBER, 6600))
        assert etas["Cranor's Island"] > etas["White Hole"]
        assert etas["Gaston's"] < etas["White Hole"]

    def test_spot_miles(self):
        from landmarks import GASTONS_MILE
        miles = dict(REACH_SPOTS)
        assert miles["Gaston's"] == GASTONS_MILE == pytest.approx(4.09)
        assert miles["White Hole"] == WHITE_HOLE_MILE == 7.0
        assert miles["Cranor's Island"] == 9.5

    def test_cranors_island_pinned_coordinates(self):
        from fishing_report import SPOT_COORDS
        lat, lon = SPOT_COORDS["Cranor's Island"]
        assert abs(lat - 36.333492497534266) < 1e-9
        assert abs(lon - (-92.56191314472997)) < 1e-9

    def test_reach_spots_have_pinned_coordinates(self):
        from fishing_report import SPOT_COORDS
        assert set(SPOT_COORDS) == {"Gaston's", "White Hole", "Cranor's Island"}

    def test_map_link_rendered(self):
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        assert "google.com/maps?q=36.333492497534266,-92.56191314472997" in html
        assert "Cranor's Island" in html


class TestReportStructure:
    def test_active_report_has_all_sections(self):
        report = generate_fishing_report(750, OCTOBER)
        assert report["in_window"] is True
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
        # Every band renders as its own panel (marked <!-- band:key -->); in
        # each, spin runs until the fly header and fly runs to the panel's end
        import re
        panels = re.split(r"<!-- band:\w+ -->", html)[1:]
        assert len(panels) == 5
        for panel in panels:
            panel = panel.split("Season notes", 1)[0]
            spin_block = panel.split("Spin Fishing", 1)[1].split("Fly Fishing", 1)[0]
            fly_block = panel.split("Fly Fishing", 1)[1]
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
        assert report["fly"]["browns"] == []
        assert report["fly"]["rainbows"] == []


class TestSpeciesPrograms:
    """Advice is split into a browns program and a rainbows/others program."""

    ALL_BANDS_CFS = [750, 3300, 6600, 12000, 20000]

    @pytest.mark.parametrize("cfs", ALL_BANDS_CFS)
    def test_spin_has_both_programs(self, cfs):
        report = generate_fishing_report(cfs, OCTOBER)
        assert report["spin"]["browns"]
        assert report["spin"]["rainbows"]

    @pytest.mark.parametrize("cfs", [750, 3300, 6600, 12000])
    def test_fly_has_both_programs_below_heavy_water(self, cfs):
        report = generate_fishing_report(cfs, OCTOBER)
        assert report["fly"]["browns"]
        assert report["fly"]["rainbows"]

    @pytest.mark.parametrize("cfs", ALL_BANDS_CFS)
    def test_leader_guidance_differs_by_species(self, cfs):
        """The core of the split: browns get heavier leaders than rainbows."""
        report = generate_fishing_report(cfs, OCTOBER)
        browns_leader = report["spin"]["browns"][0]
        rainbows_leader = report["spin"]["rainbows"][0]
        assert browns_leader.startswith("Leader:")
        assert rainbows_leader.startswith("Leader:")
        assert "fluoro" in browns_leader.lower()
        assert browns_leader != rainbows_leader

    def test_species_bait_assignment(self):
        """Sculpin/big baits belong to browns; PowerBait belongs to rainbows."""
        report = generate_fishing_report(750, OCTOBER)
        browns_text = " ".join(report["spin"]["browns"])
        rainbows_text = " ".join(report["spin"]["rainbows"])
        assert "culpin" in browns_text
        assert "PowerBait" not in browns_text
        assert "PowerBait" in rainbows_text
        assert "culpin" not in rainbows_text

    def test_fly_tippet_differs_by_species(self):
        report = generate_fishing_report(750, OCTOBER)
        browns_text = " ".join(report["fly"]["browns"])
        rainbows_text = " ".join(report["fly"]["rainbows"])
        assert "8 lb" in browns_text
        assert "4 lb" in rainbows_text

    @pytest.mark.parametrize("when", [OCTOBER, APRIL])
    @pytest.mark.parametrize("cfs", ALL_BANDS_CFS)
    def test_only_two_line_weights_prescribed(self, cfs, when):
        """Leader/cartridge prescriptions run on exactly two spools: 4 lb
        (rainbows), 8 lb (browns). 20 lb is allowed only as the fly leader's
        butt section. Any other pound-test (6, 10, 12, 16, ranges like 6-8 or
        8-10...) in the prescriptions is drift.

        Scoped to the spin/fly programs and the rigging how-to — the gear check
        is deliberately excluded, since it records rod main lines and owned
        inventory (10 lb Cherrywood main, 20/30 lb fluoro spools) rather than
        prescribing a leader class.
        """
        import re
        report = generate_fishing_report(cfs, when)
        prescriptions = [report["spin"]["rig"], report["fly"]["setup"]]
        for program in ("browns", "rainbows", "notes"):
            prescriptions += report["spin"].get(program, [])
        for program in ("browns", "rainbows"):
            prescriptions += report["fly"][program]
        for section in report["rigging"]:
            prescriptions.append(section["intro"] or "")
            prescriptions += section["items"]
        text = " ".join(prescriptions)
        weights = set(re.findall(r"(\d+(?:–\d+)?) lb", text))
        assert weights <= {"4", "8", "20"}, f"nonconforming weights: {weights}"

    BAND_SINKERS = {
        750: "1/8 oz bell (#10)",
        3300: "1/4 oz bell (#8)",
        6600: "3/8 oz bell (#7)",
        12000: "1/2 oz bell (#6)",
        20000: "1 oz bell (#4)",
    }

    @pytest.mark.parametrize("cfs,sinker", list(BAND_SINKERS.items()))
    def test_one_fixed_sinker_weight_per_band(self, cfs, sinker):
        """Each band prescribes a single starting sinker, no ranges.

        Within-band variation is handled by the on-water calibration rule,
        not by making the reader choose from a range at the bench.
        """
        import re
        report = generate_fishing_report(cfs, OCTOBER)
        assert sinker in report["spin"]["rig"]
        html = render_fishing_report_html(report)
        assert re.findall(r"[\d/]+–[\d/]+ oz", html) == []

    @pytest.mark.parametrize("cfs", [750, 3300, 6600, 12000])
    def test_both_program_headers_render_in_each_section(self, cfs):
        """Every band panel carries both program headers in spin and, where
        the fly rod is out, in fly — so the live panel shows 2 of each."""
        import re
        html = render_fishing_report_html(generate_fishing_report(cfs, OCTOBER))
        panels = re.split(r"<!-- band:\w+ -->", html)[1:]
        assert len(panels) == 5
        for panel in panels:
            panel = panel.split("Season notes", 1)[0]
            fly_cased = "stays cased" in panel
            expected = 1 if fly_cased else 2
            assert panel.count("trophy program") == expected
            assert panel.count("numbers program") == expected

    def test_gear_check_is_seasonal(self):
        """Core packing list plus season-specific additions."""
        fall = generate_fishing_report(750, OCTOBER)["gear_check"]
        spring = generate_fishing_report(750, APRIL)["gear_check"]
        # Core items appear in both seasons
        assert any("8 lb fluorocarbon" in item for item in fall["spin"])
        assert any("8 lb fluorocarbon" in item for item in spring["spin"])
        # Season-specific items appear only in their season
        assert any("hoppers" in item for item in fall["fly"])
        assert not any("hoppers" in item for item in spring["fly"])
        assert any("Elk Hair Caddis" in item for item in spring["fly"])
        assert not any("Elk Hair Caddis" in item for item in fall["fly"])

    def test_gear_check_separates_spin_from_fly(self):
        """Spin gear and fly gear are separate lists — never mixed."""
        for when in (OCTOBER, APRIL):
            gear = generate_fishing_report(750, when)["gear_check"]
            assert gear["spin"] and gear["fly"]
            spin_text = " ".join(gear["spin"])
            fly_text = " ".join(gear["fly"])
            # Fly vocabulary stays out of the spin list
            # "tippet ring" is legitimate dual-use hardware in the cartridge
            # rig; ban tippet-as-line vocabulary only
            assert "tippet" not in spin_text.replace("tippet ring", "")
            assert "VersiLeader" not in spin_text
            assert "fly box" not in spin_text
            # Spin vocabulary stays out of the fly list
            assert "bell" not in fly_text.lower()
            assert "mono" not in fly_text
            assert "PowerBait" not in fly_text

    def test_gear_check_renders_both_subsections(self):
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        assert "Spin gear:" in html
        assert "Fly gear:" in html


class TestRiggingReference:
    """Static rigging/techniques reference after the gear check."""

    EXPECTED_TITLES = [
        "Building the White River rig (spin)",
        "Bait prep (spin)",
        "Boat strategy — tie, drift, or anchor",
        "Presentations from a tied boat (spin)",
        "Fly fishing from the tied boat (fly)",
        "River etiquette",
    ]

    def test_all_reference_blocks_present(self):
        report = generate_fishing_report(750, OCTOBER)
        titles = [section["title"] for section in report["rigging"]]
        assert titles == self.EXPECTED_TITLES

    def test_static_across_bands_and_seasons(self):
        a = generate_fishing_report(750, OCTOBER)["rigging"]
        b = generate_fishing_report(20000, APRIL)["rigging"]
        assert a == b

    def test_renders_as_collapsibles_after_gear_check(self):
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        assert "Rigging &amp; techniques" in html
        assert html.index("Rigging &amp; techniques") > html.index("Gear check")
        for title in self.EXPECTED_TITLES:
            assert title in html

    def test_rig_build_content(self):
        report = generate_fishing_report(750, OCTOBER)
        rig = next(s for s in report["rigging"]
                   if s["title"].startswith("Building"))
        text = " ".join(rig["items"])
        assert "dropper loop" in text
        assert "#10 = 1/8 oz" in text

    def test_spin_fly_blocks_stay_separate(self):
        report = generate_fishing_report(750, OCTOBER)
        spin_blocks = " ".join(
            " ".join(s["items"]) for s in report["rigging"] if "(spin)" in s["title"])
        fly_block = " ".join(
            " ".join(s["items"]) for s in report["rigging"] if "(fly)" in s["title"])
        assert "roll cast" not in spin_blocks.lower()
        assert "mend" not in spin_blocks.lower()
        assert "sinker" not in fly_block.lower()
        assert "PowerBait" not in fly_block

    def test_season_adds_land_in_the_right_program(self):
        fall = generate_fishing_report(750, OCTOBER)
        assert any("crawdad" in item for item in fall["spin"]["browns"])
        assert any("garlic" in item for item in fall["spin"]["rainbows"])
        spring = generate_fishing_report(750, APRIL)
        assert any("caddis pupa" in item for item in spring["fly"]["browns"])
        assert any("Elk Hair Caddis" in item for item in spring["fly"]["rainbows"])


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

    def test_en_route_picks_the_plug_that_changes_the_band(self):
        """Regression: a same-level plug ahead of the real rise must not
        hide it (the nearest-only logic did)."""
        timeline_data = [
            {"release_time": OCTOBER - timedelta(hours=3), "cfs": 800,
             "generators": "0-1 generators", "arrival_time": OCTOBER + timedelta(minutes=40),
             "status": "incoming", "minutes_until": 40, "change": None, "recession_start": None},
            {"release_time": OCTOBER - timedelta(hours=1), "cfs": 12000,
             "generators": "3-4 generators", "arrival_time": OCTOBER + timedelta(hours=1.5),
             "status": "incoming", "minutes_until": 90, "change": "rising", "recession_start": None},
        ]
        timing = " ".join(build_timing(750, OCTOBER, timeline_data, None))
        assert "RISE EN ROUTE" in timing and "12,000" in timing

    def test_drop_en_route_is_a_window(self):
        start = OCTOBER + timedelta(minutes=70)
        down = OCTOBER + timedelta(minutes=110)
        timeline_data = [{
            "release_time": OCTOBER - timedelta(hours=1), "cfs": 750,
            "generators": "0-1 generators", "arrival_time": down,
            "status": "incoming", "minutes_until": 110, "change": "falling",
            "recession_start": start,
        }]
        timing = " ".join(build_timing(13000, OCTOBER, timeline_data, None))
        assert "DROP EN ROUTE" in timing
        assert start.strftime("%I:%M %p").lstrip("0") in timing
        assert down.strftime("%I:%M %p").lstrip("0") in timing

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
        # Falling water is a window per spot, bracketed by the two travel
        # times (from the flow being replaced to the new flow)
        from fishing_report import spot_recession_windows
        for name, start, end in spot_recession_windows(scheduled, 13000, 750):
            assert start < end
            assert f"{name} ~{start.strftime('%I:%M %p').lstrip('0')}–{end.strftime('%I:%M %p').lstrip('0')}" in timing

    def test_scheduled_drop_uses_the_hour_before_it_as_the_from_flow(self):
        first = OCTOBER + timedelta(hours=1)
        second = OCTOBER + timedelta(hours=2)
        forecast = [
            {"scheduled_time": first, "cfs": 16000, "arrival_time": first + timedelta(hours=2)},
            {"scheduled_time": second, "cfs": 750, "arrival_time": second + timedelta(hours=3.7)},
        ]
        # Current flow is already high, so the first hour is no change (<2000
        # CFS) and the drop's window must start from 16,000 CFS water, not 15,000
        from fishing_report import _find_flow_change
        direction, entry, from_cfs = _find_flow_change(15000, forecast)
        assert direction == "drop" and entry["cfs"] == 750 and from_cfs == 16000

    def test_scheduled_change_tomorrow_carries_the_day(self):
        scheduled = OCTOBER + timedelta(days=1, hours=2)
        forecast = [{"scheduled_time": scheduled, "cfs": 13504,
                     "arrival_time": scheduled + timedelta(hours=2.4)}]
        timing = " ".join(build_timing(750, OCTOBER, None, forecast))
        assert f"at {scheduled.strftime('%a')} 2 PM" in timing

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

    def test_off_season_page_shows_collapsed_preview(self):
        data = [self._entry(JULY - timedelta(hours=h), 750)
                for h in range(6, 0, -1)]
        html = generate_white_hole_summary(
            output_format="html", data=data, current_time=JULY)
        assert "Fishing Report" in html
        assert "Off-season preview" in html
        assert "Spin Fishing" in html
        assert '<details class="timeline-box">' in html


class TestRigClarity:
    """Every bottom-bait bullet names its rig; no vague 'bottom rig' term."""

    @pytest.mark.parametrize("cfs", [750, 3300, 6600, 12000, 20000])
    @pytest.mark.parametrize("when", [OCTOBER, APRIL])
    def test_no_vague_bottom_rig_term(self, cfs, when):
        html = render_fishing_report_html(generate_fishing_report(cfs, when))
        assert "bottom rig" not in html.lower()

    def test_livebait_drifts_name_the_split_shot_rig(self):
        """Sculpin (minimum) and minnows (1 unit, 3-5 units) use the
        split-shot rig, explicitly."""
        minimum = generate_fishing_report(750, OCTOBER)["spin"]["browns"]
        assert any("split-shot rig" in item and "culpin" in item for item in minimum)
        one_unit = generate_fishing_report(3300, OCTOBER)["spin"]["browns"]
        assert any("split-shot rig" in item and "minnow" in item for item in one_unit)
        mid = generate_fishing_report(12000, OCTOBER)["spin"]["browns"]
        assert any("split-shot rig" in item and "minnow" in item for item in mid)

    @pytest.mark.parametrize("cfs", [750, 3300, 6600, 12000, 20000])
    def test_crawler_and_shrimp_baits_name_the_y(self, cfs):
        """Every crawler/shrimp soak or hold references the White River rig."""
        report = generate_fishing_report(cfs, OCTOBER)
        for program in ("browns", "rainbows"):
            for item in report["spin"][program]:
                text = item.lower()
                if ("crawler" in text or "shrimp" in text) and "split-shot" not in text:
                    assert "white river rig" in text, item


class TestQuietSummary:
    """The collapsed header must not advertise that it expands."""

    def test_no_expand_hint(self):
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        summary = html.split("</summary>", 1)[0]
        assert "expand" not in summary.lower()
        assert "tap" not in summary.lower()
        assert "click" not in summary.lower()
        # No pointer cursor and no disclosure marker inviting interaction
        assert "cursor: default" in summary
        assert "list-style: none" in summary


class TestCartridgeRig:
    """The tippet-ring cartridge upgrade lives in the rig-build reference."""

    def test_cartridge_system_documented(self):
        report = generate_fishing_report(750, OCTOBER)
        rig = next(s for s in report["rigging"]
                   if s["title"].startswith("Building"))
        text = " ".join(rig["items"])
        assert "tippet-ring upgrade" in text
        assert "8 lb fluoro base" in text
        # The ladder and its band mapping
        assert "12, 24 or 36 in" in text
        assert "20, 32 or 44 in" in text
        # Species selection moves to the cartridge
        assert "4 lb mono = rainbows, 8 lb fluoro = browns" in text

    def test_rings_in_both_gear_lists(self):
        gear = generate_fishing_report(750, OCTOBER)["gear_check"]
        assert any("tippet rings" in item for item in gear["spin"])
        assert any("tippet ring" in item for item in gear["fly"])


class TestGearDoctrine:
    """tackle-inventory.md is the inventory of record; anything the report
    recommends that isn't owned must surface in the gear check."""

    def test_boat_gear_list_present_and_rendered(self):
        report = generate_fishing_report(750, OCTOBER)
        assert report["gear_check"]["boat"]
        html = render_fishing_report_html(report)
        assert "Boat &amp; trip gear" in html

    def test_not_owned_items_flagged(self):
        gear = generate_fishing_report(750, OCTOBER)["gear_check"]
        spin = " ".join(gear["spin"])
        assert "Worm blower" in spin and "not owned" in spin
        assert "staged at Dad's" in spin
        fall_spin = " ".join(generate_fishing_report(750, OCTOBER)["gear_check"]["spin"])
        assert "soft craw" in fall_spin.lower()

    def test_soft_craw_not_presented_as_owned(self):
        """Brian doesn't own soft craw plastics — the fall crawdad bullet
        must lead with the owned option (half Senko on the Ned head)."""
        fall = generate_fishing_report(750, OCTOBER)
        craw = [item for item in fall["spin"]["browns"] if "crawdad" in item.lower()]
        assert craw and "green-pumpkin Senko" in craw[0]
        assert "not owned" in craw[0]

    def test_fly_gear_marked_unverified(self):
        gear = generate_fishing_report(750, OCTOBER)["gear_check"]
        fly = " ".join(gear["fly"])
        assert "isn't in the inventory yet" in fly or "isn't inventoried yet" in fly
        assert "Fly box audit" in fly


class TestWaterNotes:
    """Measured USGS temperature/oxygen leads the season notes."""

    WQ = {"site": "07054527", "site_label": "USGS gauge at Cane Island",
          "temp_c": 14.6, "temp_f": 58.3, "do_mg_l": 4.5,
          "observed": OCTOBER - timedelta(minutes=30), "age_hours": 0.5,
          "do_status": "low", "temp_status": "prime"}

    def test_measured_reading_replaces_the_guess(self):
        report = generate_fishing_report(750, OCTOBER, water_quality=self.WQ)
        notes = report["season_notes"]
        assert notes[0].startswith("Water 58.3°F — prime")
        assert notes[1].startswith("Oxygen 4.5 mg/L — LOW")
        assert "USGS gauge at Cane Island" in notes[1]
        assert not any("unavailable" in n for n in notes)

    def test_fallback_without_a_reading(self):
        for when in (OCTOBER, APRIL):
            notes = generate_fishing_report(750, when, water_quality=None)["season_notes"]
            assert "USGS tailwater reading unavailable" in notes[0]

    def test_no_hardcoded_temperature_claims(self):
        """The old fixed '~53–56°F' note contradicted the live gauge."""
        for when in (OCTOBER, APRIL):
            html = render_fishing_report_html(generate_fishing_report(750, when))
            assert "53–56" not in html and "annual warmest" not in html


class TestLightWindows:
    def test_timing_names_the_days_low_light_windows(self):
        from datetime import datetime as dt
        from zoneinfo import ZoneInfo
        import suncalc
        from fishing_report import SPOT_COORDS
        when = dt(2026, 10, 5, 12, 0, tzinfo=ZoneInfo("America/Chicago"))
        timing = " ".join(build_timing(750, when, None, None))
        assert "Low light today" in timing
        lat, lon = SPOT_COORDS["White Hole"]
        rise, set_ = suncalc.sun_times(when.date(), lat, lon, when.tzinfo)
        assert f"sunrise {rise.strftime('%I:%M %p').lstrip('0')}" in timing
        assert f"sunset {set_.strftime('%I:%M %p').lstrip('0')}" in timing

    def test_naive_time_uses_central(self):
        timing = " ".join(build_timing(750, OCTOBER, None, None))
        assert "Low light today" in timing

    def test_regulations_do_not_call_it_an_emergency(self):
        report = generate_fishing_report(750, OCTOBER)
        regs = " ".join(report["regulations"])
        assert "emergency management" not in regs
        assert "until further notice" in regs


class TestScheduleOutline:
    def _hour(self, when, cfs, change=None, recession_start=None):
        return {"scheduled_time": when, "cfs": cfs, "generators": "x",
                "arrival_time": when + timedelta(hours=calculate_travel_time(cfs)),
                "wading": "no wading", "change": change, "recession_start": recession_start,
                "generation_cfs": cfs - 250, "min_flow_cfs": 250}

    def test_tomorrow_bullet_lists_every_significant_change_and_the_peak(self):
        tomorrow = OCTOBER.replace(hour=0) + timedelta(days=1)
        forecast = (
            [self._hour(tomorrow + timedelta(hours=h), 750) for h in range(0, 6)]
            + [self._hour(tomorrow + timedelta(hours=h), 1600, "rising") for h in range(6, 11)]
            + [self._hour(tomorrow + timedelta(hours=11), 4301, "rising")]
            + [self._hour(tomorrow + timedelta(hours=16), 18818, "rising")]
            + [self._hour(tomorrow + timedelta(hours=19), 10378, "falling",
                          tomorrow + timedelta(hours=21))]
        )
        timing = build_timing(750, OCTOBER, None, forecast)
        outline = [t for t in timing if t.startswith("Tomorrow (")][0]
        assert "at White Hole:" in outline
        assert "1,600 by ~" in outline and "4,301 by ~" in outline
        assert "18,818 by ~" in outline and "(peak)" in outline
        assert "10,378 falling ~" in outline
        # weekday prefix on every clock, since the day is tomorrow
        assert tomorrow.strftime("%a") in outline

    def test_rest_of_today_bullet(self):
        later = OCTOBER + timedelta(hours=2)
        forecast = [self._hour(later, 8352, "rising"), self._hour(later + timedelta(hours=3), 750, "falling")]
        timing = " ".join(build_timing(750, OCTOBER, None, forecast))
        assert "Rest of today at White Hole: 8,352 by ~" in timing

    def test_no_forecast_no_outline(self):
        assert not [t for t in build_timing(750, OCTOBER, None, None) if "at White Hole:" in t]


class TestProvenance:
    def test_every_band_and_season_names_sources(self):
        from fishing_report import BAND_CONTENT, SEASON_CONTENT, SOURCES
        for content in list(BAND_CONTENT.values()) + list(SEASON_CONTENT.values()):
            assert content["sources"], content["label"]
            assert all(key in SOURCES for key in content["sources"])

    @pytest.mark.parametrize("cfs", [750, 3300, 6600, 12000, 20000])
    def test_sources_and_evidence_render(self, cfs):
        html = render_fishing_report_html(generate_fishing_report(cfs, OCTOBER))
        assert html.count("Sources:") >= 3          # band, season, regulations
        assert "hisplaceresort.net" in html
        assert "agfc.com" in html
        assert "no fish on record yet" in html

    def test_evidence_renders_when_recorded(self, monkeypatch):
        import fishing_report
        monkeypatch.setitem(fishing_report.EVIDENCE, ("minimum", "browns"),
                            {"fish": 2, "dates": ["2026-10-06"], "note": "sculpin at dawn"})
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        assert "Journal: 2 fish on record (2026-10-06) — sculpin at dawn" in html
        assert "no fish on record yet" in html      # the rainbows block is still empty


class TestBandPicker:
    """The tap-to-pick strip and per-band panels ported from the White Hole Book."""

    def test_report_carries_every_band_in_order(self):
        from fishing_report import FLOW_BANDS
        report = generate_fishing_report(3300, OCTOBER)
        assert [b["key"] for b in report["bands"]] == [key for _, _, key in FLOW_BANDS]
        current = next(b for b in report["bands"] if b["key"] == "one_unit")
        assert current["spin"] == report["spin"] and current["fly"] == report["fly"]

    @pytest.mark.parametrize("cfs,key", [(750, "minimum"), (3300, "one_unit"), (6600, "two_three_units"),
                                         (12000, "four_five_units"), (20000, "high")])
    def test_live_band_selected_and_visible(self, cfs, key):
        import re
        html = render_fishing_report_html(generate_fishing_report(cfs, OCTOBER))
        assert html.count('class="wh-flowpick"') == 1
        pressed = re.findall(r'<button type="button" data-band="(\w+)" aria-pressed="true"', html)
        assert pressed == [key]
        panels = re.findall(r'<div class="wh-band-panel" data-band="(\w+)"( hidden)?>', html)
        assert len(panels) == 5
        assert [k for k, hidden in panels if not hidden] == [key]
        assert "at White Hole now" in html
        assert "<script>" in html

    def test_evidence_lines_are_per_band(self, monkeypatch):
        import fishing_report
        monkeypatch.setitem(fishing_report.EVIDENCE, ("high", "browns"),
                            {"fish": 1, "dates": ["2026-10-07"], "note": "swimbait in the slack"})
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        heavy = html.split("<!-- band:high -->", 1)[1]
        assert "Journal: 1 fish on record (2026-10-07)" in heavy
        minimum = html.split("<!-- band:minimum -->", 1)[1].split("<!-- band:one_unit -->", 1)[0]
        assert "no fish on record yet" in minimum


class TestRigDiagram:
    def test_rig_reference_carries_the_drawing(self):
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        rig = html.split("Building the White River rig (spin)", 1)[1].split("</details>", 1)[0]
        assert "<svg" in rig and "2 mm tippet ring" in rig and "12 / 24 / 36 in" in rig
        assert "20 / 32 / 44 in" in rig
        assert "cartridge-class line" in rig
