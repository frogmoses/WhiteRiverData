"""Tests for scripts/build_journal.py — the trip journal and catch table."""
import csv
import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "build_journal.py")

spec = importlib.util.spec_from_file_location("build_journal", SCRIPT)
bj = importlib.util.module_from_spec(spec)
sys.modules["build_journal"] = bj
spec.loader.exec_module(bj)


PREDICTIONS = """run_time,latest_reading_time,latest_dam_cfs,white_hole_cfs,white_hole_release_time,water_state,forecast,next_change,next_change_cfs,next_change_release_time,next_change_start,next_change_down,scheduled_change,scheduled_change_cfs,scheduled_time,scheduled_arrival,water_temp_f,dissolved_oxygen_mg_l,feed_failed
2026-10-06T07:00-05:00,2026-10-06T06:00-05:00,771,750,2026-10-06T03:00-05:00,stable,stable conditions expected,,,,,,rising,8352,2026-10-06T14:00-05:00,2026-10-06T16:39-05:00,57.2,5.1,0
2026-10-06T08:00-05:00,2026-10-06T07:00-05:00,771,750,2026-10-06T04:00-05:00,stable,stable conditions expected,,,,,,rising,8352,2026-10-06T14:00-05:00,2026-10-06T16:39-05:00,57.4,5.0,0
2026-10-06T15:00-05:00,2026-10-06T14:00-05:00,771,750,2026-10-06T11:00-05:00,stable,stable conditions expected,,,,,,rising,8352,2026-10-06T14:00-05:00,2026-10-06T16:39-05:00,57.9,4.9,0
2026-10-06T17:00-05:00,2026-10-06T16:00-05:00,14331,8109,2026-10-06T14:00-05:00,rising,rising water expected soon,rising,12891,2026-10-06T15:00-05:00,2026-10-06T17:21-05:00,,,,,,58.3,4.5,0
"""

ENTRY = """---
date: 2026-10-06
title: First morning
tags: low water, sculpin
species: brown, rainbow
party: Dad, William
spot: White Hole
cfs_reported: 750
---

Launched at 0700. Gin clear.

## Catches

| species | size | time | spot | water | boat | rig | bait | lost |
|---|---|---|---|---|---|---|---|---|
| brown | 19 | 07:40 | White Hole head | dead low | tie | split-shot | sculpin | |
| rainbow | 12 | 08:15 | Gaston's | dead low | tie | WR rig | PowerBait pink worm | |
| rainbow |  | 8:50 am | White Hole | dead low | tie | float | 1/16 jig white grub | x |
| brown | 22 | 17:30 | Cranor's | rising | drift | direct | Countdown | |
| rainbow | 11 | 22:10 | White Hole | falling | tie | WR rig | shrimp | |

## Stage

| time | reading | water | note |
|---|---|---|---|
| 07:10 | 14 in | dead low | dock post, tape mark |
| 16:20 | 14 | steady | |
| 16:40 | 16 | rising | first push, foam line |
| 17:00 | 22 | | |
| 17:30 | 30 | rising | |
"""

STAGE_ONLY = """---
date: 2026-10-07
title: Reading the post
---

## Stage

| time | reading | water | note |
|---|---|---|---|
| 06:30 | 40 | | |
| 07:05 | 36 | | dropping |
| 07:40 | 31 | | |
| 08:10 | 31 | | |
"""


@pytest.fixture
def journal(tmp_path):
    entries = tmp_path / "entries"
    entries.mkdir()
    (entries / "2026-10-06-first-morning.md").write_text(ENTRY, encoding="utf-8")
    (tmp_path / "predictions.csv").write_text(PREDICTIONS, encoding="utf-8")
    return tmp_path


def _rows(tmp_path, name="catches.csv"):
    with open(tmp_path / "build" / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class TestBuild:
    def test_builds_all_outputs(self, journal):
        summary = bj.build(str(journal / "entries"), str(journal / "build"),
                           str(journal / "predictions.csv"))
        assert summary["entries"] == 1 and summary["catches"] == 5 and summary["stage"] == 5
        for name in ("digest.md", "index.json", "catches.csv", "catches_report.md",
                     "stage.csv", "stage_report.md"):
            assert (journal / "build" / name).exists()

    def test_check_writes_nothing(self, journal):
        bj.build(str(journal / "entries"), str(journal / "build"),
                 str(journal / "predictions.csv"), check_only=True)
        assert not (journal / "build").exists()

    def test_empty_journal_is_quiet(self, tmp_path):
        (tmp_path / "entries").mkdir()
        summary = bj.build(str(tmp_path / "entries"), str(tmp_path / "build"),
                           str(tmp_path / "predictions.csv"))
        assert summary["entries"] == 0 and summary["catches"] == 0
        assert "No entries yet" in (tmp_path / "build" / "digest.md").read_text()
        assert "No landed fish" in (tmp_path / "build" / "catches_report.md").read_text()
        assert "No readings yet" in (tmp_path / "build" / "stage_report.md").read_text()


class TestCatchRows:
    def test_vocabulary_and_programs(self, journal):
        bj.build(str(journal / "entries"), str(journal / "build"), str(journal / "predictions.csv"))
        rows = _rows(journal)
        by_time = {r["time"]: r for r in rows}
        brown = by_time["07:40"]
        assert brown["program"] == "browns" and brown["rig_class"] == "split-shot"
        assert brown["bait_class"] == "sculpin" and brown["spot_name"] == "White Hole"
        bow = by_time["08:15"]
        assert bow["program"] == "rainbows" and bow["rig_class"] == "WR rig"
        assert bow["bait_class"] == "powerbait" and bow["spot_name"] == "Gaston's"
        lost = by_time["08:50"]          # "8:50 am" parsed
        assert lost["lost"] == "x" and lost["bait_class"] == "plastic"
        assert by_time["17:30"]["spot_name"] == "Cranor's Island"
        assert by_time["17:30"]["bait_class"] == "jerkbait" and by_time["17:30"]["rig_class"] == "direct"

    def test_model_numbers_attach_by_time(self, journal):
        bj.build(str(journal / "entries"), str(journal / "build"), str(journal / "predictions.csv"))
        by_time = {r["time"]: r for r in _rows(journal)}
        # 07:40 -> the 07:00 run; 17:30 -> the 17:00 run
        assert by_time["07:40"]["model_cfs"] == "750"
        assert by_time["07:40"]["model_band"] == "Minimum flow (dead low)"
        assert by_time["07:40"]["model_temp_f"] == "57.2"
        assert by_time["17:30"]["model_cfs"] == "8109"
        assert by_time["17:30"]["model_state"] == "rising"
        # 22:10 is more than 2 h after the last run -> no model numbers
        assert by_time["22:10"]["model_cfs"] == ""

    def test_sunset_windows(self, journal):
        bj.build(str(journal / "entries"), str(journal / "build"), str(journal / "predictions.csv"))
        by_time = {r["time"]: r for r in _rows(journal)}
        assert by_time["07:40"]["window"] == "dawn"
        assert by_time["17:30"]["window"] == "dusk"
        assert int(by_time["17:30"]["vs_sunset"]) < 0 < int(by_time["22:10"]["vs_sunset"])

    def test_report_crosses_bands_and_programs(self, journal):
        bj.build(str(journal / "entries"), str(journal / "build"), str(journal / "predictions.csv"))
        report = (journal / "build" / "catches_report.md").read_text()
        assert "| Minimum flow (dead low) | browns | 1 |" in report
        assert "| Minimum flow (dead low) | rainbows | 1 |" in report
        assert "| 2–3 units (5,000–10,000 CFS) | browns | 1 |" in report
        assert "Hooked and lost" in report
        assert "| rising | rising | 1 |" in report      # your read vs the model


class TestStage:
    def test_rows_and_derived_direction(self, journal):
        bj.build(str(journal / "entries"), str(journal / "build"), str(journal / "predictions.csv"))
        by_time = {r["time"]: r for r in _rows(journal, "stage.csv")}
        assert by_time["07:10"]["reading_value"] == "14" and by_time["07:10"]["water"] == "dead low"
        assert by_time["07:10"]["water_source"] == "typed"
        assert by_time["07:10"]["model_cfs"] == "750"
        # blank water cell: derived from the reading before it
        assert by_time["17:00"]["water"] == "rising" and by_time["17:00"]["water_source"] == "derived"
        assert by_time["17:30"]["model_next_change"] == "rising"

    def test_event_matches_prediction(self, journal):
        bj.build(str(journal / "entries"), str(journal / "build"), str(journal / "predictions.csv"))
        rows = bj.collect_stage(bj.load_entries(str(journal / "entries")),
                                bj.load_predictions(str(journal / "predictions.csv")))
        events = bj.stage_events(rows)
        assert [e["direction"] for e in events] == ["rising"]     # 17:00 continues, not a new event
        ev = events[0]
        assert ev["observed"].strftime("%H:%M") == "16:40"
        assert ev["after"].strftime("%H:%M") == "16:20"
        pred = bj.prediction_for_event(ev, bj.load_predictions(str(journal / "predictions.csv")))
        # no run saw the water leave the dam before 16:40 -> the SWPA schedule's 16:39 arrival
        assert pred["source"] == "scheduled"
        assert pred["start"].strftime("%H:%M") == "16:39" and pred["delta_min"] == 1
        assert pred["to_cfs"] == "8352"

    def test_measured_prediction_preferred_and_closest(self, tmp_path):
        entries = tmp_path / "entries"
        entries.mkdir()
        (entries / "2026-10-06-x.md").write_text(ENTRY, encoding="utf-8")
        # a later run that saw the release: arrival 17:21, plus a stale scheduled one
        extra = ("2026-10-06T16:00-05:00,2026-10-06T15:00-05:00,8352,750,2026-10-06T12:00-05:00,"
                 "stable,rising water expected soon,rising,8352,2026-10-06T14:00-05:00,"
                 "2026-10-06T16:45-05:00,,rising,12891,2026-10-06T15:00-05:00,2026-10-06T17:21-05:00,58.0,4.8,0\n")
        (tmp_path / "predictions.csv").write_text(PREDICTIONS + extra, encoding="utf-8")
        preds = bj.load_predictions(str(tmp_path / "predictions.csv"))
        rows = bj.collect_stage(bj.load_entries(str(entries)), preds)
        pred = bj.prediction_for_event(bj.stage_events(rows)[0], preds)
        assert pred["source"] == "measured"
        assert pred["start"].strftime("%H:%M") == "16:45" and pred["delta_min"] == -5

    def test_report_tables(self, journal):
        bj.build(str(journal / "entries"), str(journal / "build"), str(journal / "predictions.csv"))
        report = (journal / "build" / "stage_report.md").read_text()
        assert "| 2026-10-06 | rising | between 16:20 and 16:40 | 16:39 (scheduled) | +1 min (late) | 750 → 8352 | 15:00 |" in report
        assert "| 750 | Minimum flow (dead low) | 14 (2026-10-06 07:10)" in report   # rating seed
        assert "16 (2026-10-06 16:40)" not in report.split("## Reading vs model flow")[1]  # mid-rise excluded

    def test_series_without_water_column_yields_drop_event(self, tmp_path):
        entries = tmp_path / "entries"
        entries.mkdir()
        (entries / "2026-10-07-post.md").write_text(STAGE_ONLY, encoding="utf-8")
        (tmp_path / "predictions.csv").write_text(PREDICTIONS, encoding="utf-8")
        summary = bj.build(str(entries), str(tmp_path / "build"), str(tmp_path / "predictions.csv"))
        assert summary["stage"] == 4
        rows = bj.collect_stage(bj.load_entries(str(entries)), [])
        assert [r["water"] for r in rows] == ["", "falling", "falling", "steady"]
        events = bj.stage_events(rows)
        assert len(events) == 1 and events[0]["direction"] == "falling"
        assert events[0]["observed"].strftime("%H:%M") == "07:05"
        report = (tmp_path / "build" / "stage_report.md").read_text()
        assert "| 2026-10-07 | falling | between 06:30 and 07:05 | no prediction |" in report

    def test_bad_stage_time_refuses(self, tmp_path):
        entries = tmp_path / "entries"
        entries.mkdir()
        (entries / "2026-10-06-x.md").write_text(ENTRY.replace("| 16:40 |", "| four forty |"),
                                                 encoding="utf-8")
        with pytest.raises(SystemExit):
            bj.build(str(entries), str(tmp_path / "build"), str(tmp_path / "predictions.csv"))

    def test_unnumbered_reading_warns_only(self, tmp_path, capsys):
        entries = tmp_path / "entries"
        entries.mkdir()
        (entries / "2026-10-06-x.md").write_text(ENTRY.replace("| 14 in |", "| below the tape |"),
                                                 encoding="utf-8")
        summary = bj.build(str(entries), str(tmp_path / "build"), str(tmp_path / "predictions.csv"))
        assert "no leading number" in capsys.readouterr().out
        assert summary["stage"] == 5


class TestValidation:
    def test_bad_time_refuses(self, tmp_path):
        entries = tmp_path / "entries"
        entries.mkdir()
        (entries / "2026-10-06-x.md").write_text(
            ENTRY.replace("| 07:40 |", "| seven forty |"), encoding="utf-8")
        with pytest.raises(SystemExit):
            bj.build(str(entries), str(tmp_path / "build"), str(tmp_path / "predictions.csv"))

    def test_unterminated_front_matter_refuses(self, tmp_path):
        entries = tmp_path / "entries"
        entries.mkdir()
        (entries / "2026-10-06-x.md").write_text("---\ndate: 2026-10-06\nno end", encoding="utf-8")
        with pytest.raises(SystemExit):
            bj.build(str(entries), str(tmp_path / "build"), str(tmp_path / "predictions.csv"))

    def test_unknown_vocabulary_warns_only(self, tmp_path, capsys):
        entries = tmp_path / "entries"
        entries.mkdir()
        (entries / "2026-10-06-x.md").write_text(
            ENTRY.replace("| sculpin |", "| mystery bait |").replace("| split-shot |", "| weird rig |"),
            encoding="utf-8")
        summary = bj.build(str(entries), str(tmp_path / "build"), str(tmp_path / "predictions.csv"))
        out = capsys.readouterr().out
        assert "mystery bait" in out and "weird rig" in out
        assert summary["catches"] == 5

    def test_missing_predictions_warns_only(self, tmp_path, capsys):
        entries = tmp_path / "entries"
        entries.mkdir()
        (entries / "2026-10-06-x.md").write_text(ENTRY, encoding="utf-8")
        summary = bj.build(str(entries), str(tmp_path / "build"), str(tmp_path / "none.csv"))
        assert "not found" in capsys.readouterr().out
        assert summary["catches"] == 5

    def test_date_from_filename(self, tmp_path):
        entries = tmp_path / "entries"
        entries.mkdir()
        body = "\n".join(line for line in ENTRY.splitlines() if not line.startswith("date:"))
        (entries / "2026-10-07-no-date-field.md").write_text(body, encoding="utf-8")
        bj.build(str(entries), str(tmp_path / "build"), str(tmp_path / "predictions.csv"))
        assert all(r["date"] == "2026-10-07" for r in _rows(tmp_path))


class TestClassifiers:
    @pytest.mark.parametrize("text,expected", [
        ("San Juan worm", "nymph"), ("night crawler", "crawler"), ("red worm", "worm"),
        ("Mice Tail", "powerbait"), ("Power Eggs", "powerbait"), ("orange bead", "egg"),
        ("olive Woolly Bugger #8", "streamer"), ("pink hopper", "dry"),
        ("Rooster Tail", "spinner"), ("Kastmaster", "spoon"), ("Keitech 3.8", "swimbait"),
        ("half a Senko on the Ned head", "plastic"), ("marabou jig", "jig"),
        ("3-in minnow", "minnow"), ("soft-shell craw", "crawdad"), ("", ""), ("gum", ""),
    ])
    def test_bait_classes(self, text, expected):
        assert bj.classify(text, bj.BAIT_CLASSES) == expected

    @pytest.mark.parametrize("text,expected", [
        ("WR rig", "WR rig"), ("white river rig", "WR rig"), ("split shot", "split-shot"),
        ("slip float", "float"), ("tied direct", "direct"), ("swing", "swing"),
        ("tightline", "tightline"), ("dry-dropper", "dry"), ("", ""),
    ])
    def test_rig_classes(self, text, expected):
        assert bj.classify(text, bj.RIG_CLASSES) == expected

    def test_programs(self):
        assert bj.program_for(bj.species_group("Brown")) == "browns"
        for s in ("rainbow", "bow", "cutthroat", "brookie", "tiger"):
            assert bj.program_for(bj.species_group(s)) == "rainbows"
        assert bj.program_for(bj.species_group("walleye")) == ""

    def test_spots(self):
        assert bj.spot_name("gastons") == "Gaston's"
        assert bj.spot_name("head of the White Hole") == "White Hole"
        assert bj.spot_name("Cranor's far side") == "Cranor's Island"
        assert bj.spot_name("the honey hole") == ""
