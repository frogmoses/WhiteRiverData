"""Tests for prediction_log.py — the per-run CSV of model predictions."""
import csv
from datetime import datetime, timedelta

from prediction_log import build_prediction_row, append_prediction, FIELDS
from main import generate_white_hole_summary

T0 = datetime(2026, 10, 5, 12, 0)


def _entry(dt, cfs):
    return {"date_time": dt, "elevation": 655.0, "tailwater": 450.0,
            "generation": 20, "turbine_release": cfs,
            "spillway_release": 0, "total_release": cfs}


class TestBuildRow:
    def test_row_has_every_field(self):
        row = build_prediction_row(T0, _entry(T0, 1708), _entry(T0 - timedelta(hours=3), 771),
                                   771, "stable", "rising water expected soon")
        assert set(row) == set(FIELDS)
        assert row["run_time"] == "2026-10-05T12:00"
        assert row["latest_dam_cfs"] == 1708 and row["white_hole_cfs"] == 771
        assert row["next_change"] == "" and row["scheduled_change"] == ""
        assert row["feed_failed"] == 0

    def test_next_change_is_the_significant_plug(self):
        timeline = [
            {"status": "incoming", "cfs": 779, "release_time": T0 - timedelta(hours=3),
             "arrival_time": T0 + timedelta(minutes=43), "minutes_until": 43,
             "change": None, "recession_start": None},
            {"status": "incoming", "cfs": 1708, "release_time": T0 - timedelta(hours=1),
             "arrival_time": T0 + timedelta(minutes=162), "minutes_until": 162,
             "change": "rising", "recession_start": None},
        ]
        row = build_prediction_row(T0, _entry(T0, 1708), _entry(T0 - timedelta(hours=3), 771),
                                   771, "stable", "rising", timeline)
        assert row["next_change"] == "rising" and row["next_change_cfs"] == 1708
        assert row["next_change_start"] == "2026-10-05T14:42"
        assert row["next_change_down"] == ""

    def test_falling_change_logs_the_window(self):
        timeline = [{
            "status": "incoming", "cfs": 5989, "release_time": T0 - timedelta(hours=1),
            "arrival_time": T0 + timedelta(hours=2), "minutes_until": 120,
            "change": "falling", "recession_start": T0 + timedelta(hours=1.5),
        }]
        row = build_prediction_row(T0, _entry(T0, 5989), _entry(T0 - timedelta(hours=3), 17464),
                                   17464, "stable", "falling", timeline)
        assert row["next_change_start"] == "2026-10-05T13:30"
        assert row["next_change_down"] == "2026-10-05T14:00"

    def test_scheduled_change_and_water_quality(self):
        forecast = [
            {"scheduled_time": T0 + timedelta(hours=1), "cfs": 750,
             "arrival_time": T0 + timedelta(hours=4.7), "change": None},
            {"scheduled_time": T0 + timedelta(hours=2), "cfs": 8352,
             "arrival_time": T0 + timedelta(hours=4.7), "change": "rising"},
        ]
        wq = {"temp_f": 58.3, "do_mg_l": 4.5}
        row = build_prediction_row(T0, _entry(T0, 750), _entry(T0, 750), 750, "stable",
                                   "stable", None, forecast, wq, feed_failed=True)
        assert row["scheduled_change"] == "rising" and row["scheduled_change_cfs"] == 8352
        assert row["scheduled_time"] == "2026-10-05T14:00"
        assert row["water_temp_f"] == 58.3 and row["dissolved_oxygen_mg_l"] == 4.5
        assert row["feed_failed"] == 1


class TestAppend:
    def test_header_once_then_rows(self, tmp_path):
        path = tmp_path / "predictions.csv"
        row = build_prediction_row(T0, _entry(T0, 750), _entry(T0, 750), 750, "stable", "stable")
        assert append_prediction(row, str(path))
        assert append_prediction(row, str(path))
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2
        assert list(rows[0].keys()) == FIELDS

    def test_page_run_logs_only_when_asked(self, tmp_path):
        data = [_entry(T0 - timedelta(hours=h), 750) for h in range(6, 0, -1)]
        generate_white_hole_summary(output_format="html", data=data, current_time=T0)
        assert not (tmp_path / "predictions.csv").exists()
        generate_white_hole_summary(output_format="html", data=data, current_time=T0,
                                    prediction_log_file=str(tmp_path / "predictions.csv"))
        with open(tmp_path / "predictions.csv", newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1 and rows[0]["white_hole_cfs"] == "750"
