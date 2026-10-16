"""Tests for fishing_report.py — flow-driven fishing report."""
from datetime import datetime, timedelta
import pytest
import re

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
        assert report["spin"]["notes"] and report["fly"]["notes"]

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
                    "spin", "fly", "season_notes", "regulations", "gear_check",
                    "core", "experiments", "parked"):
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
            panel = panel.split("<!-- /bands -->", 1)[0]
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
        assert report["fly"]["notes"] == []


class TestCoreAndExperiments:
    """The report is a core program (what catches fish) plus one experiment
    per session; the species split lives in the experiment list, not in the
    band panels (Brian, after the first trip)."""

    ALL_BANDS_CFS = [750, 3300, 6600, 12000, 20000]

    def test_core_program_is_the_same_in_every_band_and_renders_first(self):
        from fishing_report import CORE_PROGRAM
        for cfs in self.ALL_BANDS_CFS:
            report = generate_fishing_report(cfs, OCTOBER)
            assert report["core"]["lines"] == CORE_PROGRAM["lines"]
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        order = [html.index(m) for m in ("Today at White Hole", "The core program", "The playbook by flow",
                                         "Things to try — one or two a session")]
        assert order == sorted(order)
        assert "Journal: 77 fish on record" in html or "fish on record —" in html

    def test_core_names_both_line_classes_and_the_crawdad_tail(self):
        text = " ".join(generate_fishing_report(750, OCTOBER)["core"]["lines"])
        assert "4 lb mono" in text and "8 lb fluoro" in text
        assert "crawdad tail" in text and "nightcrawler" in text
        assert "Cleo" in text and "Rooster Tail" in text

    def test_experiments_carry_the_species_split(self):
        from fishing_report import EXPERIMENTS, FLOW_BANDS, SOURCES
        keys = [x["key"] for x in EXPERIMENTS]
        assert keys == sorted(keys) and len(keys) == len(set(keys))
        assert {x["program"] for x in EXPERIMENTS} == {"browns", "rainbows"}
        band_keys = {key for _, _, key in FLOW_BANDS}
        for x in EXPERIMENTS:
            assert x["bands"] and set(x["bands"]) <= band_keys, x["key"]
            assert x["needs"] and x["status"] and x["text"], x["key"]
            assert all(src in SOURCES for src in x["sources"]), x["key"]
        # the fly rod is an experiment, not a parallel program
        assert any("fly rod" in x["title"].lower() for x in EXPERIMENTS)

    @pytest.mark.parametrize("cfs", ALL_BANDS_CFS)
    def test_each_band_points_at_the_experiments_that_fit(self, cfs):
        from fishing_report import EXPERIMENTS
        report = generate_fishing_report(cfs, OCTOBER)
        band = report["band"]
        expected = [x["key"] for x in EXPERIMENTS if band in x["bands"]]
        current = next(b for b in report["bands"] if b["key"] == band)
        assert current["experiments"] == expected
        # the panel prints titles, not letters
        assert current["experiment_titles"] == [x["title"] for x in EXPERIMENTS if band in x["bands"]]
        html = render_fishing_report_html(report)
        assert "Worth trying at this level:" in html
        panel = html.split(f"<!-- band:{band} -->", 1)[1].split("<!-- /bands -->", 1)[0]
        for title in current["experiment_titles"]:
            assert title in panel

    def test_things_to_try_render_as_titles_with_what_to_bring(self):
        """No letters, no 'Needs: nothing new — owned', no untested status
        lines (Joe: 'a science fair'; the newcomer: 'owned by whom?')."""
        from fishing_report import EXPERIMENTS
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        block = html.split("Things to try", 1)[1].split("Before the trip", 1)[0]
        for x in EXPERIMENTS:
            assert f"<strong>{x['title']}</strong>" in block
            assert f"<strong>{x['key']}." not in block
        assert block.count("Bring:") == len(EXPERIMENTS)
        assert "Needs:" not in block and "Nothing new" not in block
        assert "untested" not in block and "[CONFIRMED]" not in block and "[REPORTED]" not in block
        assert "trophy, all released" in block and "keep 2 under 14 in" in block
        # a rainbow count never stands as evidence for a browns bet
        dawn = next(x for x in EXPERIMENTS if x["key"] == "A")
        assert dawn["status"].startswith("no brown yet")

    def test_parked_renders_collapsed_with_reasons(self):
        report = generate_fishing_report(750, OCTOBER)
        assert any("Night browns" in p["what"] for p in report["parked"])
        html = render_fishing_report_html(report)
        tail = html.split("<!-- /bands -->", 1)[1]
        assert ">Tried and parked <span" in tail and "<details open" not in tail

    @pytest.mark.parametrize("when", [OCTOBER, APRIL])
    @pytest.mark.parametrize("cfs", ALL_BANDS_CFS)
    def test_only_two_line_weights_prescribed(self, cfs, when):
        """Prescriptions run on exactly two spools: 4 lb (rainbows), 8 lb
        (browns). 20 lb is allowed only as the fly leader's butt section. Any
        other pound-test in the prescriptions is drift. The gear check is
        excluded: it records owned main lines and spools, not a leader class."""
        import re
        report = generate_fishing_report(cfs, when)
        prescriptions = [report["spin"]["rig"], report["fly"]["setup"]]
        prescriptions += report["spin"]["notes"] + report["fly"]["notes"]
        prescriptions += report["season_adds"]["spin"] + report["season_adds"]["fly"]
        prescriptions += report["core"]["lines"] + [text for _, text in report["today"]]
        for x in report["experiments"]:
            prescriptions += [x["text"], x["needs"]]
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
        """Each band prescribes a single starting sinker, no ranges."""
        import re
        report = generate_fishing_report(cfs, OCTOBER)
        assert sinker in report["spin"]["rig"]
        html = render_fishing_report_html(report)
        assert re.findall(r"[\d/]+–[\d/]+ oz", html) == []

    @pytest.mark.parametrize("cfs", [750, 3300, 6600, 12000, 20000])
    def test_band_panels_carry_no_species_headers(self, cfs):
        """The species split left the panels: no program headers in any band."""
        import re
        html = render_fishing_report_html(generate_fishing_report(cfs, OCTOBER))
        panels = re.split(r"<!-- band:\w+ -->", html)[1:]
        assert len(panels) == 5
        for panel in panels:
            panel = panel.split("<!-- /bands -->", 1)[0]
            assert "trophy program" not in panel and "numbers program" not in panel
            assert ">Wading<" in panel

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
            # "tippet ring" is legitimate dual-use hardware in the hook-leader
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


class TestFocusedLayout:
    """What the reader needs now leads (today, the rules, the core, the live
    band); the clock and the season follow; the bets after them; everything
    else is a collapsed reference block, with one Sources block for the lot."""

    def test_expanded_order_is_today_core_playbook_timing_season_tries(self):
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        order = [html.index(marker) for marker in (
            "Today at White Hole", "<strong>Rules:</strong>", "New to this river?", "The core program",
            "The playbook by flow", "<!-- /bands -->", ">Timing<", ">This season<",
            "Things to try — one or two a session", "Before the trip", "Rigging &amp; techniques",
            ">Sources <span")]
        assert order == sorted(order)

    def test_reference_blocks_are_collapsed_below_the_bands(self):
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        tail = html.split("<!-- /bands -->", 1)[1]
        for title in (">Regulations <span", ">Gear check <span", ">New to this river?" ):
            assert title in tail or title in html
        assert "<details open" not in tail
        # The on-the-water rules ride in the collapsed summary line
        assert "2 rainbows under 14 in, all other trout released" in tail

    def test_rules_line_is_open_above_the_core(self):
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        head = html.split("The core program", 1)[0]
        assert "<strong>Rules:</strong> 2 rainbows under 14 in" in head
        assert 'href="#wh-before-trip"' in head and 'id="wh-before-trip"' in html

    def test_new_here_glossary_is_collapsed_and_defines_the_words(self):
        """The newcomer's list of undefined words, answered once and folded
        away so the regulars never see it."""
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        block = html.split("New to this river?", 1)[1].split("</details>", 1)[0]
        for phrase in ("cubic feet per second", "eight turbines", "1.5–4 hours", "7 miles below the dam",
                       "bell sinker", "Power Egg", "Mice Tail", "crawdad tail", "Corps", "SWPA", "USGS"):
            assert phrase in block, phrase
        # the map pins live here now
        assert "google.com/maps?q=" in block
        opening = html.split("New to this river?", 1)[0].rsplit("<details", 1)[1]
        assert "open" not in opening

    def test_season_adds_render_once_not_in_every_panel(self):
        """The orange-garlic bullet used to print in all five panels."""
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        assert html.count("Orange garlic is the named fall colour") == 1
        assert html.count("#10 hopper on warm afternoons") == 1
        season = html.split(">This season<", 1)[1].split("Things to try", 1)[0]
        assert "Spin this season" in season and "Fly this season" in season
        assert season.index("Spin this season") < season.index("Fly this season")

    def test_one_sources_block_not_a_line_per_section(self):
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        assert "Sources:" not in html
        assert html.count(">Sources <span") == 1
        assert html.index(">Sources <span") > html.index("Rigging &amp; techniques")

    def test_pack_list_is_one_tap_further_in(self):
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        gear = html.split(">Gear check <span", 1)[1].split("Tried and parked", 1)[0]
        assert re.search(r"<summary[^>]*>Owned — pack it \(", gear), \
            "the pack list must sit behind its own <summary>"
        assert "SCPS70MF2-SG" in gear

    def test_seasonal_pattern_is_a_timing_bullet(self):
        fall = generate_fishing_report(750, OCTOBER)
        spring = generate_fishing_report(750, APRIL)
        assert any("Typical fall pattern" in t for t in fall["timing"])
        assert any("Typical spring pattern" in t for t in spring["timing"])
        assert not any("Typical" in n for n in fall["season_notes"] + spring["season_notes"])

    def test_gear_check_groups_by_action(self):
        report = generate_fishing_report(750, OCTOBER)
        actions = report["gear_actions"]
        assert list(actions) == ["buy", "verify", "bench", "pack"]
        assert any("dip net" in i for i in actions["buy"]["spin"])
        assert any("SCPS70MF2-SG" in i for i in actions["pack"]["spin"])
        assert any("8 lb fluorocarbon — OWNED" in i for i in actions["pack"]["spin"])
        assert any("Fly box audit" in i for i in actions["verify"]["fly"])
        assert any("Pre-tie whole White River rigs" in i for i in actions["bench"]["spin"])
        assert any("Worm blower" in i for i in actions["pack"]["spin"])
        # Nothing is lost between the grouped view and the flat lists
        for kind in ("spin", "fly", "boat"):
            grouped = [i for a in actions.values() for i in a[kind]]
            assert sorted(grouped) == sorted(report["gear_check"][kind])
        html = render_fishing_report_html(report)
        buy = sum(len(v) for v in actions["buy"].values())
        verify = sum(len(v) for v in actions["verify"].values())
        assert f"{buy} to buy · {verify} to verify" in html
        assert html.index("To buy (") < html.index("To verify (") \
            < html.index("Bench jobs at home (") < html.index("Owned — pack it (")


class TestRiggingReference:
    """Static rigging/techniques reference after the gear check."""

    EXPECTED_TITLES = [
        "The White River rig (spin)",
        "The split-shot rig (spin)",
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

    def test_rig_reference_content(self):
        """The rig block is the diagram plus how to SIZE, tune and fish the rig.
        Brian's call 2026-09-29: the tying steps came out — the drawing shows
        the construction and prose describing it only drifted from the picture."""
        report = generate_fishing_report(750, OCTOBER)
        rig = next(s for s in report["rigging"]
                   if s["title"].startswith("The White River rig"))
        text = " ".join(rig["items"])
        assert "#10 = 1/8 oz" in text
        assert "Tune the hook leg" in text

    def test_rig_block_carries_no_tying_steps(self):
        """Guard on the 2026-09-29 decision. The rubber-band breakaway keeps its
        girth-hitch — that is the band, not the rig — but no knot-by-knot build
        comes back, and the rig prose names no outside shop."""
        report = generate_fishing_report(750, OCTOBER)
        rig = next(s for s in report["rigging"]
                   if s["title"].startswith("The White River rig"))
        text = " ".join([rig["intro"] or ""] + rig["items"])
        for banned in ("surgeon's loop", "improved clinch", "six-turn",
                       "nothing is cut", "His Place"):
            assert banned not in text, banned

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

    def test_season_adds_land_in_the_right_section(self):
        fall = generate_fishing_report(750, OCTOBER)
        assert any("garlic" in item for item in fall["season_adds"]["spin"])
        assert any("hopper" in item for item in fall["season_adds"]["fly"])
        assert not any("garlic" in item for item in fall["spin"]["notes"])
        spring = generate_fishing_report(750, APRIL)
        assert any("Flashy Swimmer" in item for item in spring["season_adds"]["spin"])
        assert any("caddis pupa" in item for item in spring["season_adds"]["fly"])
        assert any("Elk Hair Caddis" in item for item in spring["season_adds"]["fly"])


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
        # White Hole ETA in the message must match the repo travel model —
        # a scheduled rise on 750 CFS travels as a front
        from water_calculator import front_travel_time
        expected = scheduled + timedelta(hours=front_travel_time(13504, 750))
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
        assert html.index("Fishing Report") > html.index("Arrivals at White Hole")

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
        from fishing_report import EXPERIMENTS
        sculpin = next(x for x in EXPERIMENTS if "culpin" in x["title"] and "jig" not in x["title"])
        assert "split-shot rig" in sculpin["text"]
        one_unit = generate_fishing_report(3300, OCTOBER)["spin"]["notes"]
        assert any("split-shot rig" in item and "minnow" in item for item in one_unit)
        mid = generate_fishing_report(12000, OCTOBER)["spin"]["notes"]
        assert any("split-shot rig" in item and "minnow" in item for item in mid)

    @pytest.mark.parametrize("cfs", [750, 3300, 6600, 12000, 20000])
    def test_crawler_and_shrimp_baits_name_the_y(self, cfs):
        """Every crawler/shrimp soak or hold is on the White River rig: the
        bullet says so, or it names no rig at all and inherits the section's
        Rig line, which must then be the White River rig."""
        report = generate_fishing_report(cfs, OCTOBER)
        assert "White River rig" in report["spin"]["rig"]
        other_rigs = ("float", "tied direct")
        for item in report["spin"]["notes"] + [x["text"] for x in report["experiments"]]:
            text = item.lower()
            if ("crawler" in text or "shrimp" in text) and "split-shot" not in text:
                assert ("white river rig" in text or "the rig" in text
                        or not any(rig in text for rig in other_rigs)), item


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


class TestOnePieceRig:
    """The White River rig is tied in one piece, as Brian fishes it: the main
    line clinches to a loop 7 in above the bell; the hook leg runs on from the
    loop. The tippet-ring base-and-leader construction is gone (first trip:
    "completely unworkable"); the hook-leg ladder by flow band stays."""

    def test_rig_reference_describes_the_one_piece_tie(self):
        report = generate_fishing_report(750, OCTOBER)
        rig = next(s for s in report["rigging"]
                   if s["title"].startswith("The White River rig"))
        text = " ".join([rig["intro"]] + rig["items"])
        assert "loop 7 in above" in text and "One piece of leader" in text
        assert "44, 32 or 20 in" in text
        assert "4 lb mono = rainbows, 8 lb fluoro = browns" in text
        assert "costs the whole rig" in text
        assert "tippet ring" not in text and "base" not in rig["intro"]

    def test_band_rig_lines_give_the_hook_leg(self):
        report = generate_fishing_report(750, OCTOBER)
        legs = {b["key"]: b["spin"]["rig"] for b in report["bands"]}
        assert "44 in hook leg" in legs["minimum"]
        assert "32 in hook leg" in legs["one_unit"]
        for key in ("two_three_units", "four_five_units", "high"):
            assert "20 in hook leg" in legs[key]
        assert "hook leader" not in " ".join(legs.values())

    def test_rings_stay_only_in_the_fly_list(self):
        gear = generate_fishing_report(750, OCTOBER)["gear_check"]
        assert not any("tippet ring" in item for item in gear["spin"])
        assert any("tippet ring" in item for item in gear["fly"])

    def test_breakaway_is_on_probation(self):
        gear = generate_fishing_report(750, OCTOBER)["gear_actions"]
        bench = " ".join(gear["bench"]["spin"])
        assert "rubber bands" in bench and "probation" in bench
        assert not any("rubber band" in item for item in gear["pack"]["spin"])


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
        # The worm blower, the tippet rings, the rubber bands and the soft craw
        # were bought 2026-09-28, and the rainbow leader turned out to be owned
        # all along; all five now say OWNED. The browns fluoro spool followed
        # on 2026-10-04 - it packs, it is no longer a purchase
        assert "Worm blower" in spin and "OWNED" in spin
        assert "8 lb fluorocarbon — OWNED" in spin and "8 lb fluorocarbon (~$" not in spin
        # The rods live at Dad's, the reels travel and are respooled at home
        # (2026-09-29) — the gear check must keep that split visible
        assert "live at Dad's" in spin and "the reels travel" in spin
        fall_spin = " ".join(generate_fishing_report(750, OCTOBER)["gear_check"]["spin"])
        assert "soft craw" in fall_spin.lower()

    def test_crawdad_on_the_open_ned_head_is_parked_and_weedless_is_experiment_g(self):
        """First trip: the CrawZ on the open Ned head fouls in the weed every
        cast. The open head is parked with the reason; the craw itself comes
        back weedless as experiment G on the bait rig, packs for it, and the
        BulletZ weedless head is a buy item."""
        fall = generate_fishing_report(750, OCTOBER)
        craw = [p for p in fall["parked"] if "TRD CrawZ" in p["what"]]
        assert craw and "Fouls" in craw[0]["why"] and "weedless crawdad" in craw[0]["why"]
        g = next(x for x in fall["experiments"] if x["key"] == "G")
        assert "TRD CrawZ" in g["text"] and "drop-shot hook" in g["text"] and g["program"] == "browns"
        actions = fall["gear_actions"]
        assert any("TRD CrawZ" in i for i in actions["pack"]["spin"])
        assert not any("mushroom heads" in i for i in actions["pack"]["spin"] if "stay home" not in i)
        assert any("BulletZ" in i for i in actions["buy"]["spin"])

    def test_fly_gear_marked_unverified(self):
        gear = generate_fishing_report(750, OCTOBER)["gear_check"]
        fly = " ".join(gear["fly"])
        assert "isn't in the inventory yet" in fly or "isn't inventoried yet" in fly
        assert "Fly box audit" in fly


class TestWaterNotes:
    """Measured USGS temperature/oxygen sits under the flow line, not in the
    season notes."""

    WQ = {"site": "07054527", "site_label": "USGS gauge at Cane Island",
          "temp_c": 14.6, "temp_f": 58.3, "do_mg_l": 4.5,
          "observed": OCTOBER - timedelta(minutes=30), "age_hours": 0.5,
          "do_status": "low", "temp_status": "prime"}

    def test_measured_reading_replaces_the_guess(self):
        report = generate_fishing_report(750, OCTOBER, water_quality=self.WQ)
        notes = report["water"]
        assert notes[0].startswith("Water 58.3°F — prime")
        assert notes[1].startswith("Oxygen 4.5 mg/L — LOW")
        assert "USGS gauge at Cane Island" in notes[1]
        assert not any("unavailable" in n for n in notes)

    def test_fallback_without_a_reading(self):
        for when in (OCTOBER, APRIL):
            notes = generate_fishing_report(750, when, water_quality=None)["water"]
            assert notes[0].startswith("No temperature reading from the USGS gauge")

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


class TestTodayBlock:
    """The lead for a reader with one minute: water, where, rig, next — from
    the live band and the flow model (Joe: 'lead with the day')."""

    def test_four_lines_from_the_live_band(self):
        report = generate_fishing_report(750, OCTOBER)
        labels = [label for label, _ in report["today"]]
        assert labels == ["Water", "Go", "Rig", "Next"]
        today = dict(report["today"])
        assert today["Water"].startswith("Minimum flow (dead low) — 750 CFS at White Hole")
        assert "Excellent wading" in today["Water"]
        assert today["Go"] == report["go"] and "Cranor's Island" in today["Go"]
        assert today["Rig"].startswith(report["spin"]["rig"]) and "crawdad tail" in today["Rig"]
        html = render_fishing_report_html(report)
        head = html.split("The core program", 1)[0]
        assert "Today at White Hole" in head and "<strong>Next:</strong>" in head
        # the gauge lines ride inside the box
        assert "USGS gauge" in head

    def test_every_band_has_a_go_line(self):
        from fishing_report import BAND_CONTENT
        for key, content in BAND_CONTENT.items():
            assert content["go"], key

    def test_next_line_from_released_rise_and_the_wading_caveat(self):
        timeline_data = [{
            "release_time": OCTOBER - timedelta(hours=1), "cfs": 9900, "generators": "3 generators",
            "arrival_time": OCTOBER + timedelta(hours=1.5), "status": "incoming", "minutes_until": 90,
        }]
        report = generate_fishing_report(750, OCTOBER, timeline_data=timeline_data)
        today = dict(report["today"])
        eta = (OCTOBER + timedelta(hours=1.5)).strftime("%I:%M %p").lstrip("0")
        assert today["Next"].startswith("A rise to 9,900 CFS") and eta in today["Next"]
        assert "off the bars" in today["Next"]
        assert today["Water"].endswith("until the rise gets here.")

    def test_next_line_from_released_drop(self):
        start = OCTOBER + timedelta(minutes=70)
        down = OCTOBER + timedelta(minutes=110)
        timeline_data = [{
            "release_time": OCTOBER - timedelta(hours=1), "cfs": 750, "generators": "0-1 generators",
            "arrival_time": down, "status": "incoming", "minutes_until": 110, "change": "falling",
            "recession_start": start,
        }]
        today = dict(generate_fishing_report(13000, OCTOBER, timeline_data=timeline_data)["today"])
        assert today["Next"].startswith("A drop to 750 CFS")
        assert start.strftime("%I:%M %p").lstrip("0") in today["Next"]
        assert "first hour of the drop" in today["Next"]

    def test_next_line_from_the_schedule(self):
        scheduled = OCTOBER + timedelta(hours=2)
        forecast = [{"scheduled_time": scheduled, "cfs": 13504,
                     "arrival_time": scheduled + timedelta(hours=2.4)}]
        today = dict(generate_fishing_report(750, OCTOBER, forecast_timeline=forecast)["today"])
        from water_calculator import front_travel_time
        eta = scheduled + timedelta(hours=front_travel_time(13504, 750))
        assert "is scheduled for 2 PM" in today["Next"]
        assert eta.strftime("%I:%M %p").lstrip("0") in today["Next"]

    def test_next_line_is_honest_when_nothing_is_coming(self):
        today = dict(generate_fishing_report(750, OCTOBER, timeline_data=[], forecast_timeline=[])["today"])
        assert today["Next"].startswith("No rise or drop has been released or scheduled")
        preview = dict(generate_fishing_report(750, OCTOBER)["today"])
        assert "preview" in preview["Next"]

    def test_minimum_band_warns_about_the_rise(self):
        """The safety gap both reviewers found: 'anchoring is safe' and 'wading
        is wide open' with nothing about the afternoon rise reaching someone on
        a gravel bar."""
        from fishing_report import BAND_CONTENT
        low = BAND_CONTENT["minimum"]
        assert "until the rise" in " ".join(low["boat"]) and "arrivals table" in " ".join(low["boat"])
        wading = " ".join(low["wading"])
        assert "until the rise arrives" in wading and "arrivals table" in wading
        assert "grey rock" in wading


class TestWrittenForWhoeverIsInTheBoat:
    """The report is read by more than its author: no names, no trip numbers,
    no one's private deliberations in the copy that renders for everyone. The
    gear check's pack list is the one exception — it is the kit, and it says
    where the rods live."""

    DIARY = re.compile(r"\bDad\b|\bBrian\b|first trip|minded to|Brian's call")

    def _strings(self, value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from self._strings(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from self._strings(item)

    def test_no_diary_in_the_rendered_copy(self):
        from fishing_report import (BAND_CONTENT, SEASON_CONTENT, RIGGING_REFERENCE,
                                    CORE_PROGRAM, EXPERIMENTS, PARKED, NEW_HERE, GEAR_CHECK)
        blocks = [BAND_CONTENT, SEASON_CONTENT, RIGGING_REFERENCE, CORE_PROGRAM, EXPERIMENTS, PARKED, NEW_HERE]
        offenders = [t for block in blocks for t in self._strings(block) if self.DIARY.search(t)]
        # the gear check minus its pack lists
        jobs = {kind: {a: items for a, items in actions.items() if a != "pack"}
                for kind, actions in GEAR_CHECK.items()}
        offenders += [t for t in self._strings(jobs) if self.DIARY.search(t)]
        assert not offenders, "\n- ".join(["diary in rendered copy:"] + [t[:100] for t in offenders])

    def test_the_bait_rig_still_says_who_drives(self):
        text = " ".join(generate_fishing_report(750, OCTOBER)["core"]["lines"])
        assert "One drives, one fishes" in text

    def test_sculpin_netting_is_from_the_bank_not_a_night_on_the_water(self):
        """The headlamp and dip net sat beside 'night browns — we are off the
        water by dark', which read as a contradiction."""
        report = generate_fishing_report(750, OCTOBER)
        boat = " ".join(report["gear_actions"]["pack"]["boat"])
        assert "Headlamp" in boat and "from the bank" in boat
        night = next(p for p in report["parked"] if p["what"] == "Night browns")
        assert "from the bank" in night["why"]


class TestNoScheduleOutline:
    """The per-day outline bullets repeated the arrivals table in a form that
    was hard to read; Timing keeps only the first scheduled change."""

    def test_timing_carries_no_day_outline(self):
        scheduled = OCTOBER.replace(hour=14, minute=0)
        forecast = [{"scheduled_time": scheduled, "cfs": 8352,
                     "arrival_time": scheduled + timedelta(hours=2)}]
        timing = " ".join(build_timing(750, OCTOBER, None, forecast))
        assert "SCHEDULED RISE" in timing
        assert "Rest of today" not in timing and "Tomorrow (" not in timing


class TestProvenance:
    def test_every_band_and_season_names_sources(self):
        from fishing_report import BAND_CONTENT, SEASON_CONTENT, SOURCES
        for content in list(BAND_CONTENT.values()) + list(SEASON_CONTENT.values()):
            assert content["sources"], content["label"]
            assert all(key in SOURCES for key in content["sources"])

    @pytest.mark.parametrize("cfs", [750, 3300, 6600, 12000, 20000])
    def test_sources_and_evidence_render(self, cfs):
        from fishing_report import SOURCES
        html = render_fishing_report_html(generate_fishing_report(cfs, OCTOBER))
        footnote = html.split(">Sources <span", 1)[1]
        for label, url in SOURCES.values():
            assert label in footnote
            if url:
                assert url in footnote
        assert "no fish on record yet" in html

    def test_evidence_renders_when_recorded(self, monkeypatch):
        import fishing_report
        monkeypatch.setitem(fishing_report.EVIDENCE, ("minimum", "browns"),
                            {"fish": 2, "dates": ["2026-10-06"], "note": "sculpin at dawn"})
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        assert "Journal — browns: 2 fish on record (Oct 6) — sculpin at dawn" in html
        assert "no fish on record yet in this band" in html      # the heavy-water band is still empty

    def test_dates_read_like_a_person_says_them(self):
        """'73 fish on record (2026-10-08, 2026-10-09, 2026-10-10)' read as a
        database dump to the newcomer."""
        from fishing_report import dates_phrase, evidence_lines
        assert dates_phrase(["2026-10-06"]) == "Oct 6"
        assert dates_phrase(["2026-10-08", "2026-10-09", "2026-10-10"]) == "Oct 8–10"
        assert dates_phrase(["2026-09-30", "2026-10-01"]) == "Sep 30–Oct 1"
        assert dates_phrase(["2026-10-06", "2026-10-09"]) == "Oct 6, Oct 9"
        assert any("73 fish on record over 3 days (Oct 8–10)" in line for line in evidence_lines("minimum"))


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
        assert "Journal — browns: 1 fish on record (Oct 7)" in heavy
        minimum = html.split("<!-- band:minimum -->", 1)[1].split("<!-- band:one_unit -->", 1)[0]
        assert "Journal — rainbows &amp; others" in minimum or "Journal — rainbows & others" in minimum


class TestRigDiagram:
    def test_rig_reference_carries_the_drawing(self):
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        rig = html.split("The White River rig (spin)", 1)[1].split("</details>", 1)[0]
        assert "<svg" in rig and "loop 7 in above the bell" in rig and "44 / 32 / 20 in" in rig
        assert "one piece" in rig.lower()
        assert "tippet ring" not in rig

    def test_split_shot_rig_has_its_own_drawing(self):
        html = render_fishing_report_html(generate_fishing_report(750, OCTOBER))
        rig = html.split("The split-shot rig (spin)", 1)[1].split("</details>", 1)[0]
        assert "<svg" in rig and "split shot ~12 in above the hook" in rig
        assert "#1 drop-shot hook" in rig and "8 lb fluoro" in rig
        # the livebait exception moved out of the Y block
        wr = html.split("The White River rig (spin)", 1)[1].split("</details>", 1)[0]
        assert "livebait drift exception" not in wr


@pytest.mark.unit
class TestNoHousekeepingDates:
    """
    The page is for fishing, not for a purchase ledger: no "(bought
    2026-09-28)" or "Brian's call 2026-09-29" in anything that renders.
    Brian, 2026-10-04 — "I don't need info about dates about when I bought
    stuff, or made decisions."

    Dates that ARE the information stay: a regulation's effective date, a
    source's verification date in SOURCES, and the journal's catch dates in
    EVIDENCE. Those are not covered here.
    """

    ISO_DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")

    def _strings(self, value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from self._strings(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from self._strings(item)

    def test_rendered_content_carries_no_iso_dates(self):
        from fishing_report import (
            BAND_CONTENT, SEASON_CONTENT, GEAR_CHECK, RIGGING_REFERENCE,
            CORE_PROGRAM, EXPERIMENTS, PARKED, NEW_HERE)
        offenders = [text for block in (BAND_CONTENT, SEASON_CONTENT,
                                        GEAR_CHECK, RIGGING_REFERENCE,
                                        CORE_PROGRAM, EXPERIMENTS, PARKED, NEW_HERE)
                     for text in self._strings(block)
                     if self.ISO_DATE.search(text)]
        assert not offenders, (
            "housekeeping dates leaked into rendered copy:\n- "
            + "\n- ".join(f"{t[:110]}..." for t in offenders))

    def test_the_rendered_report_carries_no_purchase_dates(self):
        """Belt and braces: the assembled HTML, not just the content tables."""
        from datetime import datetime
        from fishing_report import generate_fishing_report, render_fishing_report_html
        html = render_fishing_report_html(
            generate_fishing_report(750, datetime(2026, 10, 3, 9, 0)))
        for phrase in ("bought 2026-", "Brian's call 2026-", "his call 2026-"):
            assert phrase not in html
