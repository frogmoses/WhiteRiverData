"""
Build the trip journal into fishing-report knowledge.

journal/entries/*.md holds free-form notes — what was seen and what the fish did, which no
feed records. This script parses them and writes, under journal/build/ (gitignored,
regenerable):

    digest.md          every entry in full + tag/species indexes (the one file to read
                       before touching the report's doctrine)
    index.json         the same content structured, for scripts
    catches.csv        one row per fish from every entry's "## Catches" table, with the
                       flow model's numbers for that hour attached from predictions.csv
    catches_report.md  the rows summarised by program, band, spot, rig, bait, water and
                       window, and crossed against the report's flow bands × species
                       programs so each block of advice shows the fish behind it
    stage.csv          one row per reading from every entry's "## Stage" table — the dock
                       post at White Hole read as a staff gauge — with the model's numbers
                       for that hour attached
    stage_report.md    every observed rise or drop against the arrival the model had
                       predicted for it (the travel model's only validation), the raw
                       readings beside the model, and reading-vs-flow as a rating-curve seed

Same model as new-croton-fishing/scripts/build_journal.py, with this river's vocabulary.
Deliberately NOT coupled to predictions.csv: the log says what the model predicted, the
journal says what happened. A catch finds its model row by clock time at build time,
and a catch with no row near it is a warning, never an error.

Rebuilds from scratch every run. Zero entries is a valid, quiet outcome.

    uv run python scripts/build_journal.py            # build
    uv run python scripts/build_journal.py --check    # validate only, write nothing
"""
import csv
import datetime
import glob
import json
import os
import re
import sys
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import suncalc  # noqa: E402  (repo root: the one copy the page and report share)
from landmarks import LANDMARK_COORDS  # noqa: E402
from fishing_report import FLOW_BANDS, BAND_CONTENT, REACH_SPOTS, get_flow_band  # noqa: E402

ENTRY_DIR = os.path.join(ROOT, "journal", "entries")
OUT_DIR = os.path.join(ROOT, "journal", "build")
PREDICTIONS = os.path.join(ROOT, "predictions.csv")

TZ = zoneinfo.ZoneInfo("America/Chicago")
WHITE_HOLE_LAT, WHITE_HOLE_LON = dict(LANDMARK_COORDS)["The White Hole"]

# A catch's model row is the run at or before its time, no older than this
MODEL_MATCH_HOURS = 2

# A stage event (a rise or drop seen at the dock) is matched against the run, within this
# many hours before it, whose predicted arrival lies closest to the observation
EVENT_MATCH_HOURS = 6

# Fields split on commas into lists; everything else is kept as the string typed
LIST_FIELDS = ("tags", "species")

# Generous box around the reach — only used to warn about a fat-fingered coordinate
LAT_RANGE = (36.0, 36.6)
LON_RANGE = (-92.9, -92.2)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FILENAME_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
TIME_RE = re.compile(r"^~?\s*(\d{1,2}):(\d{2})\s*([ap]\.?m\.?)?$", re.I)
CATCH_HEADING_RE = re.compile(r"^#{1,6}\s*catches\b", re.I)
STAGE_HEADING_RE = re.compile(r"^#{1,6}\s*stage\b", re.I)
READING_RE = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?)")

CSV_COLUMNS = ["date", "time", "species", "program", "size", "spot", "spot_name", "water",
               "boat", "rig", "rig_class", "bait", "bait_class", "lost", "vs_sunset", "window",
               "model_cfs", "model_band", "model_state", "model_temp_f", "model_do", "file"]
STAGE_COLUMNS = ["date", "time", "reading", "reading_value", "water", "water_source", "note",
                 "model_cfs", "model_band", "model_state", "model_next_change",
                 "model_next_start", "model_next_down", "file"]

# The report's two species programs (fishing_report.py): browns vs rainbows & others
SPECIES_GROUPS = [
    ("brown", r"brown"),
    ("rainbow", r"rainbow|\bbow\b|\bbows\b"),
    ("cutthroat", r"cutt"),
    ("brook", r"brook"),
    ("tiger", r"tiger"),
]
PROGRAM_FOR = {"brown": "browns"}
DEFAULT_PROGRAM = "rainbows"

# Rig vocabulary (journal/README.md). An exact class name wins; otherwise the pattern
RIG_CLASSES = [
    ("dry", r"\bdry|dry.?dropper|hopper"),      # before WR rig: "dry-dropper" is not a dropper loop
    ("WR rig", r"wr rig|white river|dropper|\by\b.?rig|three.?way|bell"),
    ("split-shot", r"split"),
    ("float", r"float|bobber|slip"),
    ("indicator", r"indicator|thingamabobber|airlock"),
    ("tightline", r"tight.?line|euro|czech"),
    ("swing", r"swing|sink.?leader|polyleader|versileader"),
    ("direct", r"direct|jerk|spinner|spoon|\bjig|swimbait|keitech"),
]

# Bait / lure classes, in an order that lets specific names win over generic words
# ("San Juan worm" is a nymph, "floating worm" is PowerBait, "night crawler" is a crawler)
BAIT_CLASSES = [
    ("sculpin", r"sculpin"),
    ("crawler", r"crawler|night.?crawler"),
    ("powerbait", r"power.?bait|mice.?tail|floating worm|power.?egg|dough|marshmallow|gulp"),
    ("nymph", r"nymph|sowbug|sow bug|scud|midge|sunday special|san juan|pheasant|hare|zebra|ruby|pupa|copper john"),
    ("streamer", r"streamer|bugger|girdle|sculpzilla|zonker|clouser"),
    ("soft hackle", r"soft.?hackle"),
    ("dry", r"\bdry\b|hopper|caddis|elk hair|bwo|adams|parachute"),
    ("shrimp", r"shrimp"),
    ("egg", r"\begg|bead"),
    ("minnow", r"minnow|shiner"),
    ("crawdad", r"craw"),
    ("worm", r"red.?worm|\bworm"),
    ("plastic", r"senko|plastic|grub|fluke"),
    ("jig", r"marabou|\bjig|\bned\b"),
    ("spinner", r"spinner|rooster|mepps|panther|beetle|aglia|fury|blade"),
    ("spoon", r"spoon|kastmaster|cleo|xps|krocodile"),
    ("jerkbait", r"jerk|countdown|rapala|husky|x-rap|stickbait"),
    ("swimbait", r"keitech|swimbait|tab tail|swing impact|flashy"),
]

WATER_CLASSES = [
    ("rising", r"ris|coming up|\bup\b"),
    ("falling", r"fall|drop|going down|\bdown\b|reced"),
    ("dead low", r"dead|min"),
    ("steady", r"stead|stable|flat|holding"),
]
BOAT_CLASSES = [
    ("tie", r"\btie|tied"),
    ("drift", r"drift"),
    ("anchor", r"anchor"),
    ("wade", r"wad|bank|shore|foot"),
]

errors = []      # refuse to build
warnings = []    # report and carry on


def reset_messages():
    del errors[:]
    del warnings[:]


# ---------------------------------------------------------------------------
# Entries
# ---------------------------------------------------------------------------

def parse_front_matter(text, path):
    """(fields, body). A leading '---' opens the block; the next '---' closes it."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        errors.append("%s: front matter opens with '---' but never closes" % path)
        return {}, text

    fields = {}
    for raw in lines[1:end]:
        line = raw.strip()
        if not line:
            continue
        if ":" not in line:
            warnings.append("%s: front-matter line has no colon, ignored -> %r" % (path, line))
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if not value:
            continue
        if key in LIST_FIELDS:
            fields[key] = [v.strip() for v in value.split(",") if v.strip()]
        else:
            fields[key] = value
    return fields, "\n".join(lines[end + 1:]).strip("\n")


def parse_coords(value, path):
    parts = [p.strip() for p in value.replace(";", ",").split(",") if p.strip()]
    if len(parts) != 2:
        errors.append("%s: coords must be 'lat, lon' -> got %r" % (path, value))
        return None
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError:
        errors.append("%s: coords are not numbers -> %r" % (path, value))
        return None
    if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
        warnings.append("%s: coords %.5f, %.5f are well off the reach - check the sign and "
                        "the order (lat first)" % (path, lat, lon))
    return (lat, lon)


def load_entries(entry_dir=ENTRY_DIR):
    entries = []
    for path in sorted(glob.glob(os.path.join(entry_dir, "*.md"))):
        name = os.path.basename(path)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        fields, body = parse_front_matter(text, path)

        date = fields.pop("date", None)
        if date is None:
            m = FILENAME_DATE_RE.match(name)
            date = m.group(1) if m else None
        if date is not None and not DATE_RE.match(date):
            errors.append("%s: date must be YYYY-MM-DD -> got %r" % (path, date))
            date = None
        if date is None:
            warnings.append("%s: no date (neither a date: field nor a YYYY-MM-DD- filename "
                            "prefix) - listed as undated" % path)

        coords = None
        if "coords" in fields:
            coords = parse_coords(fields.pop("coords"), path)

        entry = {
            "file": os.path.relpath(path, ROOT) if path.startswith(ROOT) else path,
            "date": date,
            "title": fields.pop("title", None) or os.path.splitext(name)[0],
            "tags": fields.pop("tags", []),
            "species": fields.pop("species", []),
            "lat": coords[0] if coords else None,
            "lon": coords[1] if coords else None,
            "extra": fields,          # party, spot, cfs_reported, sky, wind, anything invented
            "body": body,
        }
        entries.append(entry)
    entries.sort(key=lambda e: (e["date"] or "", e["file"]), reverse=True)
    return entries


def group_by(entries, key):
    out = {}
    for e in entries:
        for v in e[key]:
            out.setdefault(v.lower(), []).append(e)
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
# Catches
# ---------------------------------------------------------------------------

def classify(text, classes):
    """The class whose name the text IS, else the first class whose pattern matches."""
    t = (text or "").strip().lower()
    if not t:
        return ""
    for name, _ in classes:
        if t == name.lower():
            return name
    for name, pat in classes:
        if re.search(pat, t, re.I):
            return name
    return ""


def species_group(name):
    return classify(name, SPECIES_GROUPS)


def program_for(group):
    return PROGRAM_FOR.get(group, DEFAULT_PROGRAM) if group else ""


def spot_name(text):
    t = (text or "").strip().lower()
    if not t:
        return ""
    for name, _ in REACH_SPOTS:
        key = name.lower().replace("'", "")
        if key.split()[0] in t.replace("'", ""):
            return name
    return ""


def parse_time(value, path):
    """'14:35', '~14:30', '2:35 pm' -> datetime.time, or None (an error when malformed)."""
    t = (value or "").strip()
    if not t:
        return None
    m = TIME_RE.match(t)
    if not m:
        errors.append("%s: table time must be HH:MM (Central) -> got %r" % (path, value))
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    ampm = (m.group(3) or "").lower()
    if ampm.startswith("p") and hh < 12:
        hh += 12
    if ampm.startswith("a") and hh == 12:
        hh = 0
    if not (0 <= hh < 24 and 0 <= mm < 60):
        errors.append("%s: table time out of range -> %r" % (path, value))
        return None
    return datetime.time(hh, mm)


def parse_table(body, heading_re, key):
    """Rows of the first table under a heading matching heading_re, keyed by the header's
    column names; a row without a `key` cell is skipped."""
    lines = body.splitlines()
    start = None
    for i, line in enumerate(lines):
        if heading_re.match(line.strip()):
            start = i + 1
            break
    if start is None:
        return []
    header = None
    rows = []
    for line in lines[start:]:
        t = line.strip()
        if header is not None and not t.startswith("|"):
            if rows or t:
                break
            continue
        if not t.startswith("|"):
            continue
        cells = [c.strip() for c in t.strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        row = dict(zip(header, cells))
        if not row.get(key):
            continue
        rows.append(row)
    return rows


def parse_catch_table(body):
    return parse_table(body, CATCH_HEADING_RE, "species")


def parse_stage_table(body):
    return parse_table(body, STAGE_HEADING_RE, "time")


def sun_for(date_str):
    return suncalc.sun_times(datetime.date.fromisoformat(date_str),
                            WHITE_HOLE_LAT, WHITE_HOLE_LON, TZ)


def window_for(when, rise, set_):
    """dawn / midday / dusk / night / other — the light windows the report talks about."""
    if when is None or rise is None:
        return ""
    h = datetime.timedelta(hours=1)
    if rise - h <= when <= rise + 2 * h:
        return "dawn"
    if set_ - 2 * h <= when <= set_ + h:
        return "dusk"
    if set_ + h < when <= set_ + 3 * h:
        return "night"
    if 10 <= when.hour < 16:
        return "midday"
    return "other"


def minutes_vs_sunset(when, set_):
    if when is None or set_ is None:
        return ""
    return str(int(round((when - set_).total_seconds() / 60)))


# ---------------------------------------------------------------------------
# The model's side: predictions.csv
# ---------------------------------------------------------------------------

def load_predictions(path=PREDICTIONS):
    """predictions.csv rows with run_time parsed (aware Central), oldest first."""
    if not os.path.exists(path):
        warnings.append("%s not found - catches get no model numbers" % path)
        return []
    rows = []
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                when = datetime.datetime.fromisoformat(r["run_time"])
            except (KeyError, ValueError):
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=TZ)
            r["_when"] = when.astimezone(TZ)
            rows.append(r)
    rows.sort(key=lambda r: r["_when"])
    return rows


def model_for(when, predictions):
    """The run at or before `when`, within MODEL_MATCH_HOURS; else None."""
    if when is None:
        return None
    best = None
    for r in predictions:
        if r["_when"] <= when:
            best = r
        else:
            break
    if best is None:
        return None
    if when - best["_when"] > datetime.timedelta(hours=MODEL_MATCH_HOURS):
        return None
    return best


def band_label(cfs_text):
    try:
        return BAND_CONTENT[get_flow_band(int(float(cfs_text)))]["label"]
    except (TypeError, ValueError, KeyError):
        return ""


def collect_catches(entries, predictions):
    rows = []
    for e in entries:
        table = parse_catch_table(e["body"])
        if not table:
            continue
        if not e["date"]:
            warnings.append("%s: Catches rows on an undated entry are skipped" % e["file"])
            continue
        rise, set_ = sun_for(e["date"])
        for r in table:
            clock = parse_time(r.get("time", ""), e["file"])
            when = None
            if clock is not None:
                when = datetime.datetime.combine(datetime.date.fromisoformat(e["date"]),
                                                 clock, tzinfo=TZ)
            group = species_group(r["species"])
            if not group:
                warnings.append("%s: Catches species %r is not a trout the vocabulary knows"
                                % (e["file"], r["species"]))
            rig_class = classify(r.get("rig", ""), RIG_CLASSES)
            if r.get("rig") and not rig_class:
                warnings.append("%s: Catches rig %r is not in the vocabulary (journal/README.md)"
                                % (e["file"], r["rig"]))
            bait_class = classify(r.get("bait", ""), BAIT_CLASSES)
            if r.get("bait") and not bait_class:
                warnings.append("%s: Catches bait %r is not in the vocabulary (journal/README.md)"
                                % (e["file"], r["bait"]))
            model = model_for(when, predictions)
            if when is not None and model is None and predictions:
                warnings.append("%s: no predictions.csv run within %d h before %s - row keeps "
                                "no model numbers" % (e["file"], MODEL_MATCH_HOURS,
                                                      when.strftime("%Y-%m-%d %H:%M")))
            rows.append({
                "date": e["date"],
                "time": clock.strftime("%H:%M") if clock else "",
                "species": r["species"].lower(),
                "program": program_for(group),
                "size": r.get("size", ""),
                "spot": r.get("spot", ""),
                "spot_name": spot_name(r.get("spot", "")),
                "water": classify(r.get("water", ""), WATER_CLASSES) or r.get("water", ""),
                "boat": classify(r.get("boat", ""), BOAT_CLASSES) or r.get("boat", ""),
                "rig": r.get("rig", ""),
                "rig_class": rig_class,
                "bait": r.get("bait", ""),
                "bait_class": bait_class,
                "lost": "x" if (r.get("lost", "").strip()) else "",
                "vs_sunset": minutes_vs_sunset(when, set_),
                "window": window_for(when, rise, set_),
                "model_cfs": model["white_hole_cfs"] if model else "",
                "model_band": band_label(model["white_hole_cfs"]) if model else "",
                "model_state": model["water_state"] if model else "",
                "model_temp_f": model.get("water_temp_f", "") if model else "",
                "model_do": model.get("dissolved_oxygen_mg_l", "") if model else "",
                "file": e["file"],
            })
    rows.sort(key=lambda r: (r["date"], r["time"]))
    return rows


# ---------------------------------------------------------------------------
# Stage: the dock post at White Hole, read as a staff gauge
# ---------------------------------------------------------------------------

def _parse_iso(text):
    try:
        return datetime.datetime.fromisoformat(text).astimezone(TZ)
    except (TypeError, ValueError):
        return None


def collect_stage(entries, predictions):
    """One row per reading, in time order, with the model's numbers for that hour.

    `water` is your read (rising / falling / steady / dead low); when it is blank it is
    derived from the reading against the previous one in the same entry (water_source
    'derived'), so a plain series of numbers still yields the events."""
    rows = []
    for e in entries:
        table = parse_stage_table(e["body"])
        if not table:
            continue
        if not e["date"]:
            warnings.append("%s: Stage rows on an undated entry are skipped" % e["file"])
            continue
        day = datetime.date.fromisoformat(e["date"])
        prev = None
        for r in table:
            clock = parse_time(r.get("time", ""), e["file"])
            if clock is None:
                continue
            when = datetime.datetime.combine(day, clock, tzinfo=TZ)
            reading = r.get("reading", "")
            m = READING_RE.match(reading)
            value = float(m.group(1)) if m else None
            if reading and value is None:
                warnings.append("%s: Stage reading %r has no leading number - kept as text only"
                                % (e["file"], reading))
            water = classify(r.get("water", ""), WATER_CLASSES)
            source = "typed" if water else ""
            if r.get("water") and not water:
                warnings.append("%s: Stage water %r is not rising / falling / steady / dead low"
                                % (e["file"], r["water"]))
                water = r["water"]
                source = "typed"
            if not water and value is not None and prev is not None and prev["reading_value"] != "":
                before = float(prev["reading_value"])
                water = "rising" if value > before else "falling" if value < before else "steady"
                source = "derived"
            model = model_for(when, predictions)
            if model is None and predictions:
                warnings.append("%s: no predictions.csv run within %d h before %s - stage row "
                                "keeps no model numbers" % (e["file"], MODEL_MATCH_HOURS,
                                                            when.strftime("%Y-%m-%d %H:%M")))
            row = {
                "date": e["date"],
                "time": clock.strftime("%H:%M"),
                "reading": reading,
                "reading_value": "" if value is None else ("%g" % value),
                "water": water,
                "water_source": source,
                "note": r.get("note", ""),
                "model_cfs": model["white_hole_cfs"] if model else "",
                "model_band": band_label(model["white_hole_cfs"]) if model else "",
                "model_state": model["water_state"] if model else "",
                "model_next_change": model.get("next_change", "") if model else "",
                "model_next_start": model.get("next_change_start", "") if model else "",
                "model_next_down": model.get("next_change_down", "") if model else "",
                "file": e["file"],
                "_when": when,
            }
            rows.append(row)
            prev = row
    rows.sort(key=lambda r: (r["date"], r["time"]))
    return rows


def stage_events(rows):
    """The moments the water was first seen rising or falling, per entry: each is the
    reading that carries the new state, bracketed by the reading before it."""
    events = []
    prev = None
    for r in rows:
        if prev is not None and prev["file"] != r["file"]:
            prev = None
        state = r["water"]
        if state in ("rising", "falling") and (prev is None or prev["water"] != state):
            events.append({"direction": state, "row": r, "observed": r["_when"],
                           "after": prev["_when"] if prev else None})
        prev = r
    return events


def prediction_for_event(event, predictions):
    """The prediction this observation tests: among runs in the EVENT_MATCH_HOURS before
    it, the one whose next-change arrival (measured readings first, then the SWPA
    schedule) in the same direction lies closest to the observed time."""
    obs = event["observed"]
    direction = event["direction"]
    window = [r for r in predictions
              if obs - datetime.timedelta(hours=EVENT_MATCH_HOURS) <= r["_when"] <= obs]
    best = None
    for source, change_col, cfs_col, start_col, down_col in (
            ("measured", "next_change", "next_change_cfs", "next_change_start", "next_change_down"),
            ("scheduled", "scheduled_change", "scheduled_change_cfs", "scheduled_arrival", None)):
        for r in window:
            if r.get(change_col) != direction:
                continue
            start = _parse_iso(r.get(start_col, ""))
            if start is None:
                continue
            gap = abs((obs - start).total_seconds())
            if best is None or gap < best["gap"]:
                best = {"source": source, "run": r["_when"], "start": start,
                        "down": _parse_iso(r.get(down_col, "")) if down_col else None,
                        "from_cfs": r.get("white_hole_cfs", ""), "to_cfs": r.get(cfs_col, ""),
                        "gap": gap}
        if best is not None:
            break
    if best is not None:
        best["delta_min"] = int(round((obs - best["start"]).total_seconds() / 60))
    return best


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

def write_digest(path, entries, by_tag, by_species):
    L = ["# Trip journal — digest", "",
         "Generated by `scripts/build_journal.py` from `journal/entries/`. **Do not edit "
         "this file** — it is rebuilt from scratch on every run. Edit the entries.", ""]
    if not entries:
        L += ["No entries yet. Copy `journal/TEMPLATE.md` into `journal/entries/` to start "
              "one; see `journal/README.md` for the format.", ""]
    else:
        dated = [e["date"] for e in entries if e["date"]]
        span = ("%s to %s" % (dated[-1], dated[0])) if dated else "undated"
        L += ["%d entr%s, %s." % (len(entries), "y" if len(entries) == 1 else "ies", span), ""]

    for label, groups in (("Tags", by_tag), ("Species", by_species)):
        if groups:
            L += ["## %s" % label, ""]
            for value, hits in groups.items():
                refs = ", ".join("%s (%s)" % (e["title"], e["date"] or "undated") for e in hits)
                L.append("- **%s** — %s" % (value, refs))
            L.append("")

    if entries:
        L += ["## Entries", ""]
        for e in entries:
            L += ["### %s — %s" % (e["date"] or "undated", e["title"]), ""]
            meta = []
            if e["tags"]:
                meta.append("tags: " + ", ".join(e["tags"]))
            if e["species"]:
                meta.append("species: " + ", ".join(e["species"]))
            if e["lat"] is not None:
                meta.append("coords: %.5f, %.5f" % (e["lat"], e["lon"]))
            for k, v in sorted(e["extra"].items()):
                meta.append("%s: %s" % (k, v))
            meta.append("source: `%s`" % e["file"])
            L += ["*" + " · ".join(meta) + "*", "", e["body"] if e["body"] else "_(no body)_", ""]

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L).rstrip() + "\n")


def _summary_table(L, title, key, rows):
    counts = {}
    for r in rows:
        counts.setdefault(key(r) or "—", []).append(r)
    L += ["## %s" % title, "",
          "| %s | landed | bands | spots | rigs | baits | windows |" % title.lower(),
          "|---|---|---|---|---|---|---|"]
    for k, rs in sorted(counts.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        def uniq(field):
            return ", ".join(sorted({r[field] for r in rs if r[field]})) or "—"
        L.append("| %s | %d | %s | %s | %s | %s | %s |" % (
            k, len(rs), uniq("model_band"), uniq("spot_name"), uniq("rig_class"),
            uniq("bait_class"), uniq("window")))
    L.append("")


def write_catches(csv_path, md_path, rows):
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in CSV_COLUMNS})

    landed = [r for r in rows if not r["lost"]]
    lost = [r for r in rows if r["lost"]]
    dates = sorted({r["date"] for r in rows})
    with_model = [r for r in rows if r["model_cfs"]]

    L = ["# Catches — the evidence behind the report", "",
         "Generated by `scripts/build_journal.py` from the `## Catches` tables in "
         "`journal/entries/`. **Do not edit** — rebuilt every run; the rows live in the "
         "entries. Columns and rules: `journal/README.md`.", "",
         "**%d rows** (%d landed, %d hooked and lost) across %d date%s; %d carry the flow "
         "model's numbers for their hour." % (len(rows), len(landed), len(lost), len(dates),
                                              "" if len(dates) == 1 else "s", len(with_model)),
         "",
         "`model_*` columns are the White Hole prediction from `predictions.csv` at the run "
         "before the catch; a Gaston's fish saw that water about an hour earlier and a "
         "Cranor's fish an hour later. Your `water` cell is the read on the spot; the two "
         "are set side by side below on purpose.", ""]

    if landed:
        _summary_table(L, "By program", lambda r: r["program"], landed)
        _summary_table(L, "By species", lambda r: r["species"], landed)
        _summary_table(L, "By flow band (model)", lambda r: r["model_band"], landed)
        _summary_table(L, "By spot", lambda r: r["spot_name"] or r["spot"], landed)
        _summary_table(L, "By rig", lambda r: r["rig_class"], landed)
        _summary_table(L, "By bait", lambda r: r["bait_class"], landed)
        _summary_table(L, "By window", lambda r: r["window"], landed)

        # Your read of the water against the model's — the one table that grades the model
        L += ["## Your water read vs the model", "",
              "| your read | model said | fish |", "|---|---|---|"]
        pairs = {}
        for r in landed:
            pairs.setdefault((r["water"] or "—", r["model_state"] or "—"), 0)
            pairs[(r["water"] or "—", r["model_state"] or "—")] += 1
        for (yours, model), n in sorted(pairs.items(), key=lambda kv: -kv[1]):
            L.append("| %s | %s | %d |" % (yours, model, n))
        L.append("")
    else:
        L += ["No landed fish recorded yet.", ""]

    if lost:
        L += ["## Hooked and lost", ""]
        for r in lost:
            L.append("- %s %s — %s at %s on %s (%s)" % (
                r["date"], r["time"] or "?", r["species"], r["spot"] or "?", r["bait"] or "?",
                r["file"]))
        L.append("")

    # The crosswalk: every band × program block in the report, with its fish
    L += ["## Bands and programs with a fish behind them", "",
          "A landed row counts for a block when the model's band for its hour is that band "
          "and its species is in that program. Rows with no model row are listed last.", "",
          "| band | program | landed | spots | rigs | baits | windows |",
          "|---|---|---|---|---|---|---|"]
    for _, _, band in FLOW_BANDS:
        label = BAND_CONTENT[band]["label"]
        for program in ("browns", "rainbows"):
            hits = [r for r in landed if r["model_band"] == label and r["program"] == program]

            def uniq(field):
                return ", ".join(sorted({r[field] for r in hits if r[field]})) or "—"
            L.append("| %s | %s | %d | %s | %s | %s | %s |" % (
                label, program, len(hits), uniq("spot_name"), uniq("rig_class"),
                uniq("bait_class"), uniq("window")))
    no_model = [r for r in landed if not r["model_band"]]
    if no_model:
        L.append("| (no model row) | — | %d | | | | |" % len(no_model))
    L.append("")

    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L).rstrip() + "\n")
    return len(landed), len(lost)


def _clock(dt):
    return dt.strftime("%H:%M") if dt else "?"


def write_stage(csv_path, md_path, rows, predictions):
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=STAGE_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in STAGE_COLUMNS})

    events = stage_events(rows)
    dates = sorted({r["date"] for r in rows})
    L = ["# Stage — the dock post against the travel model", "",
         "Generated by `scripts/build_journal.py` from the `## Stage` tables in "
         "`journal/entries/`. **Do not edit** — rebuilt every run. Columns and rules: "
         "`journal/README.md`.", "",
         "**%d reading%s** across %d date%s; **%d event%s** (a rise or drop first seen at the "
         "dock)." % (len(rows), "" if len(rows) == 1 else "s", len(dates),
                     "" if len(dates) == 1 else "s", len(events),
                     "" if len(events) == 1 else "s"), "",
         "The travel model has never been checked against the river — there is no discharge "
         "gauge between the dam and Norfork. These readings are that check. An event's "
         "prediction is the run, within %d h before it, whose arrival for the same direction "
         "lies closest to it: `measured` when the model saw the water leave the dam, "
         "`scheduled` when it only had the SWPA schedule. `delta` is observed minus predicted "
         "— positive means the water came later than the model said." % EVENT_MATCH_HOURS, ""]

    L += ["## Predicted vs observed", ""]
    if events:
        L += ["| date | event | observed | predicted | delta | model CFS | run |",
              "|---|---|---|---|---|---|---|"]
        for ev in events:
            pred = prediction_for_event(ev, predictions)
            observed = ("between %s and %s" % (_clock(ev["after"]), _clock(ev["observed"]))
                        if ev["after"] else "by %s" % _clock(ev["observed"]))
            if pred:
                predicted = _clock(pred["start"])
                if ev["direction"] == "falling" and pred["down"]:
                    predicted = "falling %s, down %s" % (predicted, _clock(pred["down"]))
                predicted += " (%s)" % pred["source"]
                d = pred["delta_min"]
                delta = "%+d min (%s)" % (d, "late" if d > 0 else "early" if d < 0 else "on time")
                cfs = "%s → %s" % (pred["from_cfs"] or "?", pred["to_cfs"] or "?")
                run = _clock(pred["run"])
            else:
                predicted, delta, cfs, run = "no prediction", "—", "—", "—"
            L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                ev["row"]["date"], ev["direction"], observed, predicted, delta, cfs, run))
        L.append("")
    else:
        L += ["No rise or drop observed yet. A row whose `water` says `rising` or `falling` "
              "after one that did not (or a reading that moves) makes an event.", ""]

    L += ["## Readings", ""]
    if rows:
        for date in dates:
            day = [r for r in rows if r["date"] == date]
            L += ["### %s (%s)" % (date, day[0]["file"]), "",
                  "| time | reading | water | model CFS | model state | note |",
                  "|---|---|---|---|---|---|"]
            for r in day:
                water = r["water"] + (" *(derived)*" if r["water_source"] == "derived" else "")
                L.append("| %s | %s | %s | %s | %s | %s |" % (
                    r["time"], r["reading"] or "—", water or "—", r["model_cfs"] or "—",
                    r["model_state"] or "—", r["note"] or ""))
            L.append("")
    else:
        L += ["No readings yet.", ""]

    # Steady readings against the model's flow: the start of a stage-discharge rating
    steady = [r for r in rows if r["reading_value"] != "" and r["model_cfs"]
              and r["water"] in ("steady", "dead low")]
    L += ["## Reading vs model flow", "",
          "Steady readings only (a reading taken mid-change belongs to no flow). Sorted by the "
          "model's White Hole CFS for that hour; once this fills in, a glance at the post "
          "reads as a flow.", ""]
    if steady:
        L += ["| model CFS | band | readings |", "|---|---|---|"]
        by_cfs = {}
        for r in steady:
            by_cfs.setdefault((int(float(r["model_cfs"])), r["model_band"]), []).append(r)
        for (cfs, band), rs in sorted(by_cfs.items()):
            readings = ", ".join("%s (%s %s)" % (r["reading_value"], r["date"], r["time"])
                                 for r in rs)
            L.append("| %d | %s | %s |" % (cfs, band, readings))
        L.append("")
    else:
        L += ["Nothing to pair yet.", ""]

    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L).rstrip() + "\n")
    return len(events)


def build(entry_dir=ENTRY_DIR, out_dir=OUT_DIR, predictions_path=PREDICTIONS,
          check_only=False):
    """Parse, validate, and (unless check_only) write everything. Returns a summary dict."""
    reset_messages()
    if not os.path.isdir(entry_dir):
        raise SystemExit("no %s/ directory - see journal/README.md" % entry_dir)

    entries = load_entries(entry_dir)
    predictions = load_predictions(predictions_path)
    catches = collect_catches(entries, predictions)
    stage = collect_stage(entries, predictions)

    for w in warnings:
        print("WARNING  " + w)
    if errors:
        print("\nERRORS:")
        for x in errors:
            print("  " + x)
        raise SystemExit("refusing to build the journal with unparseable entries")

    by_tag = group_by(entries, "tags")
    by_species = group_by(entries, "species")
    summary = {"entries": len(entries), "tags": len(by_tag), "species": len(by_species),
               "catches": len(catches), "stage": len(stage), "warnings": len(warnings)}
    print("journal OK: %d entries, %d tags, %d species, %d catch rows, %d stage readings, "
          "%d warnings" % (summary["entries"], summary["tags"], summary["species"],
                           summary["catches"], summary["stage"], summary["warnings"]))
    if check_only:
        return summary

    os.makedirs(out_dir, exist_ok=True)
    digest = os.path.join(out_dir, "digest.md")
    index = os.path.join(out_dir, "index.json")
    catches_csv = os.path.join(out_dir, "catches.csv")
    catches_md = os.path.join(out_dir, "catches_report.md")
    stage_csv = os.path.join(out_dir, "stage.csv")
    stage_md = os.path.join(out_dir, "stage_report.md")

    write_digest(digest, entries, by_tag, by_species)
    with open(index, "w", encoding="utf-8") as fh:
        json.dump({"entries": entries,
                   "tags": {k: [e["file"] for e in v] for k, v in by_tag.items()},
                   "species": {k: [e["file"] for e in v] for k, v in by_species.items()},
                   "catches": catches,
                   "stage": [{k: r[k] for k in STAGE_COLUMNS} for r in stage]},
                  fh, indent=1, default=str)
    n_landed, n_lost = write_catches(catches_csv, catches_md, catches)
    n_events = write_stage(stage_csv, stage_md, stage, predictions)

    for p in (digest, index):
        print("wrote %s" % p)
    print("wrote %s  (%d landed, %d lost)" % (catches_csv, n_landed, n_lost))
    print("wrote %s" % catches_md)
    print("wrote %s  (%d readings, %d events)" % (stage_csv, len(stage), n_events))
    print("wrote %s" % stage_md)
    return summary


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    build(check_only="--check" in argv)


if __name__ == "__main__":
    main()
