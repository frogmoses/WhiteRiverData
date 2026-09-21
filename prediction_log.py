"""
Per-run prediction log.

The travel model has never been validated: there is no discharge gauge
near White Hole, and until now each run kept only its rendered page. This
appends one row per production run to a committed CSV so predictions can
be compared against on-site observations (timestamped notes at the ramp)
and against later dam readings — the only route to a calibrated model.

Written only from main.py's __main__ (like the last-good-data cache) and
committed by run_white_hole.sh; tests run in a tmp dir and never touch it.
"""
import csv
import os

from water_calculator import find_incoming_change

PREDICTION_LOG_FILE = "predictions.csv"

FIELDS = [
    "run_time",                  # when the prediction was made (Central)
    "latest_reading_time",       # newest USACE row
    "latest_dam_cfs",
    "white_hole_cfs",            # predicted flow at White Hole now
    "white_hole_release_time",   # the dam reading that water came from
    "water_state",
    "forecast",
    "next_change",               # rising / falling / '' — from actual readings
    "next_change_cfs",
    "next_change_release_time",
    "next_change_start",         # arrival (rise) or start of the drop (fall)
    "next_change_down",          # fully down (fall only)
    "scheduled_change",          # first significant SWPA change: rising / falling / ''
    "scheduled_change_cfs",
    "scheduled_time",
    "scheduled_arrival",
    "water_temp_f",
    "dissolved_oxygen_mg_l",
    "feed_failed",
]


def _iso(dt):
    return dt.isoformat(timespec="minutes") if dt else ""


def build_prediction_row(current_time, latest_entry, relevant_entry, white_hole_cfs,
                         water_state, forecast, timeline_data=None,
                         forecast_timeline=None, water_quality=None, feed_failed=False):
    """One CSV row (dict keyed by FIELDS) for this run's predictions."""
    from water_calculator import get_flow

    row = {field: "" for field in FIELDS}
    row.update({
        "run_time": _iso(current_time),
        "latest_reading_time": _iso(latest_entry["date_time"]),
        "latest_dam_cfs": get_flow(latest_entry),
        "white_hole_cfs": white_hole_cfs,
        "white_hole_release_time": _iso(relevant_entry["date_time"]),
        "water_state": water_state,
        "forecast": forecast,
        "feed_failed": int(bool(feed_failed)),
    })

    direction, item = find_incoming_change(timeline_data, white_hole_cfs)
    if item:
        row["next_change"] = direction
        row["next_change_cfs"] = item["cfs"]
        row["next_change_release_time"] = _iso(item["release_time"])
        if direction == "falling" and item.get("recession_start"):
            row["next_change_start"] = _iso(item["recession_start"])
            row["next_change_down"] = _iso(item["arrival_time"])
        else:
            row["next_change_start"] = _iso(item["arrival_time"])

    for entry in forecast_timeline or []:
        if entry.get("change"):
            row["scheduled_change"] = entry["change"]
            row["scheduled_change_cfs"] = entry["cfs"]
            row["scheduled_time"] = _iso(entry["scheduled_time"])
            row["scheduled_arrival"] = _iso(entry["arrival_time"])
            break

    if water_quality:
        if water_quality.get("temp_f") is not None:
            row["water_temp_f"] = water_quality["temp_f"]
        if water_quality.get("do_mg_l") is not None:
            row["dissolved_oxygen_mg_l"] = water_quality["do_mg_l"]

    return row


def append_prediction(row, filename=PREDICTION_LOG_FILE):
    """Append the row, writing the header on a new file. True on success."""
    try:
        new_file = not os.path.exists(filename) or os.path.getsize(filename) == 0
        with open(filename, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow(row)
        return True
    except OSError as e:
        print(f"Warning: could not append to prediction log: {e}")
        return False
