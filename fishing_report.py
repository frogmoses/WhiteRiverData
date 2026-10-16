"""
Fishing report generator for the Gaston's -> Cranor's Island reach of the
White River.

Content is distilled from a Claude Cowork research brief (fishing knowledge:
spots, rigs, baits, presentations, regulations) but ALL flow numbers, travel
times, and arrival ETAs come from this repo's verified model
(water_calculator). Where the brief's flow claims conflicted with the repo
(e.g. its "rise arrives in 90 minutes" surge-front table), the repo wins.

The shape, for two readers at once — the old hand who wants the day in four
lines and the newcomer who needs the words defined:
  - TODAY — water, where to go, rig and bait, the next rise or drop, generated
    from the live band and the flow model; the on-the-water rules in one open
    line; a collapsed glossary ("New to this river?").
  - THE CORE PROGRAM — what has caught fish here, with the journal's count.
  - THE BAND PANELS — where / boat / wading / rig by flow, tap to pick.
  - TIMING and THIS SEASON — what the clock and the month add.
  - THINGS TO TRY — one or two a session; this is where the species split
    lives (browns are the point of most of them; the fly rod is the exception):
      BROWNS — trophy program, all released. Wild fish eating big, holding on
      structure, crepuscular/nocturnal at low water. 8 lb fluoro.
      RAINBOWS & OTHERS — numbers program (keep 2 rainbows under 14 in).
      Stocked invertebrate feeders in open drifts. 4 lb mono.
  - Reference, collapsed: regulations, gear check, tried-and-parked, rigging,
    and one Sources block for the whole report.

The copy is written for whoever is in the boat — no names, no trip numbers —
except the gear check's pack list, which is the kit and says where it lives.
Gear recommendations are restricted to owned tackle
(new-croton-fishing/reference/tackle-inventory.md) plus cheap consumables.

The report renders year-round as a collapsible section (collapsed by
default). During trip windows (March-April, September-October) it shows
that window's playbook; other months preview the upcoming window's
playbook against current flow, labeled as such. Spin and fly sections
are kept strictly separate.

Standalone use:
    uv run python fishing_report.py [--season fall|spring] [--cfs N]
"""
from datetime import datetime, timedelta

from water_calculator import (
    calculate_travel_time, front_travel_time, get_flow, format_generators, get_fishing_condition,
    recession_window, clock
)
from landmarks import GASTONS_MILE, LANDMARK_COORDS, WHITE_HOLE_MILE
import suncalc
from water_quality import describe as describe_water_quality, dam_line as dam_water_line
from data_fetcher import DAM_TIMEZONE as SPOT_TZ

# Reach landmarks, miles below the dam. Gaston's and White Hole come from the
# GPS-derived chart model (landmarks.py); Cranor's Island extends it downstream
# (no intermediate GPS points below White Hole, so its mile stays estimated).
REACH_SPOTS = [
    ("Gaston's", GASTONS_MILE),
    ("White Hole", WHITE_HOLE_MILE),
    ("Cranor's Island", 9.5),
]

# Pinned coordinates (lat, lon) for reach landmarks, rendered as map links.
# Gaston's and White Hole from landmarks.py; Cranor's Island pinned by Brian
# (the island below Cranor's White River Lodge — his downstream turnaround).
# The run into it is "the Narrows" — Brian's name and the research brief's;
# the journal maps that word to this spot.
SPOT_COORDS = {
    "Gaston's": dict(LANDMARK_COORDS)["Gaston's"],
    "White Hole": dict(LANDMARK_COORDS)["The White Hole"],
    "Cranor's Island": (36.333492497534266, -92.56191314472997),
}

# Trip windows: months with researched, full-playbook content
SEASON_MONTHS = {
    3: "spring", 4: "spring",
    9: "fall", 10: "fall",
}

# Flow bands, aligned to the repo's wading/boating thresholds (2000/5000/
# 10000 in get_fishing_condition) plus a 5-unit split at 16500
FLOW_BANDS = [
    (0, 2000, "minimum"),
    (2000, 5000, "one_unit"),
    (5000, 10000, "two_three_units"),
    (10000, 16500, "four_five_units"),
    (16500, float("inf"), "high"),
]


def get_flow_band(cfs):
    """Map a CFS value at White Hole to a fishing band key."""
    for low, high, band in FLOW_BANDS:
        if low <= cfs < high:
            return band
    return "high"


def get_trip_season(date):
    """Return 'fall', 'spring', or None outside the trip windows."""
    return SEASON_MONTHS.get(date.month)


def get_effective_season(date):
    """
    Return (season, in_window). During a trip window, that window's season;
    otherwise the next upcoming window's season (May-Aug preview fall,
    Nov-Feb preview spring), flagged as out-of-window.
    """
    season = get_trip_season(date)
    if season is not None:
        return season, True
    return ("spring" if date.month in (1, 2, 11, 12) else "fall"), False


def spot_arrival_times(release_time, cfs, previous_cfs=None):
    """
    When water released at the dam reaches each reach landmark, using the
    repo's travel model scaled by river mile (same method as the chart); a
    significant rise on previous_cfs travels as a front.
    """
    return [
        (name, release_time + timedelta(hours=front_travel_time(cfs, previous_cfs, mile=mile)))
        for name, mile in REACH_SPOTS
    ]


def spot_recession_windows(cut_time, from_cfs, to_cfs):
    """
    When a cut released at the dam is felt at each reach landmark: (name,
    start, fully_down) per spot, from the repo's recession model.
    """
    return [
        (name, *recession_window(cut_time, from_cfs, to_cfs, mile=mile))
        for name, mile in REACH_SPOTS
    ]


def _window_str(name, start, end, reference):
    """'Gaston's ~9:15–9:40 PM' — or a single time when the window is a step."""
    if end - start < timedelta(minutes=10):
        return f"{name} ~{clock(end, reference)}"
    return f"{name} ~{clock(start, reference)}–{clock(end, reference)}"


# ---------------------------------------------------------------------------
# Provenance. Every block of advice names its sources. The "brief" is the Aug
# 2026 research brief, restored to research/ on 2026-09-21: each of its claims
# carries a confidence tag, so a bullet here can be traced to a tagged claim and
# its §12 source. The journal's catch rows are what confirms or retires the
# REPORTED/INFERRED ones (EVIDENCE below, journal/README.md).
# ---------------------------------------------------------------------------

SOURCES = {
    "his_place": ("His Place Resort river guide (flow bands, travel and fall-out times, "
                  "boat safety)", "https://www.hisplaceresort.net/white-river-info"),
    "agfc_regs": ("AGFC 2026 trout regulations (verified 2026-09-20)",
                  "https://www.agfc.com/news/agfc-passes-new-trout-regulations-for-2026/"),
    "agfc_code": ("AGFC Code ch. 32 — sculpin as legal baitfish (verified Aug 2026)",
                  "https://www.agfc.com/regulations/"),
    "usgs": ("USGS tailwater gauges 07054527 / 07054502 (temperature, oxygen)",
             "https://waterdata.usgs.gov/monitoring-location/USGS-07054527/"),
    "brief": ("Research brief, Aug 2026 (research/WHITE_RIVER_RESEARCH_BRIEF.md — every "
              "claim carries a CONFIRMED / REPORTED / INFERRED / CONFLICT tag and §12 lists "
              "the sources)", "research/WHITE_RIVER_RESEARCH_BRIEF.md"),
    "brian": ("Brian's own vetting and boat experience on this reach", None),
}

# Journal evidence per (band key, program): filled by hand from
# journal/build/catches_report.md after each trip — the count of landed fish
# behind the block and the dates. Empty until the first rows exist.
EVIDENCE = {
    # ("minimum", "browns"): {"fish": 1, "dates": ["2026-10-06"], "note": "sculpin, split-shot, dawn"},
    # keep these notes free of tackle words: they render under the fly block too
    ("minimum", "rainbows"): {
        "fish": 73, "dates": ["2026-10-08", "2026-10-09", "2026-10-10"],
        "note": "three days on dead-low water, mostly the Narrows — drifting down from the "
                "White Hole, then tied at its head — plus a few from the Honey Hole reach",
    },
    ("two_three_units", "rainbows"): {
        "fish": 1, "dates": ["2026-10-09"],
        "note": "the Honey Hole at 5:21 PM, the afternoon rise already through there",
    },
    ("one_unit", "rainbows"): {
        "fish": 3, "dates": ["2026-10-08"],
        "note": "the first of the afternoon rise, half a mile below the White Hole, 3:58-4:23 PM",
    },
}


def dates_phrase(dates):
    """
    ISO dates as a reader says them: 'Oct 6'; a consecutive run 'Oct 8–10';
    otherwise 'Oct 6, Oct 9'. Across months the run reads 'Sep 30–Oct 2'.
    """
    days = sorted(datetime.strptime(d, "%Y-%m-%d").date() for d in dates)
    if not days:
        return ""
    def one(d):
        return f"{d.strftime('%b')} {d.day}"
    if len(days) == 1:
        return one(days[0])
    if all((b - a).days == 1 for a, b in zip(days, days[1:])):
        first, last = days[0], days[-1]
        tail = str(last.day) if first.month == last.month else one(last)
        return f"{one(first)}–{tail}"
    return ", ".join(one(d) for d in days)


def _fish_on_record(e):
    """'73 fish on record over 3 days (Oct 8–10)' or '2 fish on record (Oct 6)'."""
    dates = e.get("dates", [])
    span = f" over {len(dates)} days" if len(dates) > 1 else ""
    return f"{e['fish']} fish on record{span} ({dates_phrase(dates)})"


def evidence_line(band, program):
    """'Journal: 3 fish on record over 2 days (Oct 6–7) — note' or the honest default."""
    e = EVIDENCE.get((band, program))
    if not e or not e.get("fish"):
        return "Journal: no fish on record yet for this block"
    note = f" — {e['note']}" if e.get("note") else ""
    return f"Journal: {_fish_on_record(e)}{note}"


PROGRAM_LABELS = {"browns": "browns", "rainbows": "rainbows & others"}


def evidence_lines(band):
    """
    One 'Journal — <program>: N fish on record (dates) — note' line per
    program with fish behind it in this band, or the honest default.
    """
    lines = []
    for program in ("browns", "rainbows"):
        e = EVIDENCE.get((band, program))
        if e and e.get("fish"):
            note = f" — {e['note']}" if e.get("note") else ""
            lines.append(f"Journal — {PROGRAM_LABELS[program]}: {_fish_on_record(e)}{note}")
    return lines or ["Journal: no fish on record yet in this band"]


def core_evidence_line():
    """'Journal: 77 fish on record — 73 at minimum flow, 3 around 1 unit, …' from EVIDENCE."""
    per_band = {}
    for (band, _program), e in EVIDENCE.items():
        per_band[band] = per_band.get(band, 0) + int(e.get("fish", 0))
    total = sum(per_band.values())
    if not total:
        return "Journal: no fish on record yet"
    parts = [f"{per_band[key]} {BAND_PICKER_SHORT[key]}" for _, _, key in FLOW_BANDS if per_band.get(key)]
    return f"Journal: {total} fish on record — " + ", ".join(parts)


BAND_PICKER_SHORT = {
    "minimum": "at minimum flow",
    "one_unit": "around 1 unit",
    "two_three_units": "at 2–3 units",
    "four_five_units": "at 3–5 units",
    "high": "on heavy water",
}

# ---------------------------------------------------------------------------
# The core program: what has actually caught fish from a driven boat in
# daylight. Written from the journal after the first trip; the band panels say
# WHERE at each flow, the things-to-try list carries the species split.
# Written for whoever is in the boat — no names, no trip numbers.
# ---------------------------------------------------------------------------
CORE_BAIT_SHORT = ("a Power Egg or a Mice Tail with a crawdad tail, or a nightcrawler — "
                   "4 lb mono for rainbows, 8 lb fluoro for browns")

CORE_PROGRAM = {
    "title": "The core program — what catches fish here",
    "lines": [
        "The one-piece White River rig: 4 lb mono for rainbows and others, 8 lb fluoro when a brown is the point (the rig is tied in the program's line — see Rigging). Bell and hook leg by flow band, below",
        "On it, a Power Egg (orange or white) or a Mice Tail with a crawdad tail — the crawdad tail is the common factor, 60 of the 77 fish on record — or a nightcrawler, whole or in stubs, bought once at the start of the trip and kept in the cooler",
        "At first light, hardware before bait: a gold Cleo or a Rooster Tail — 5 fish before 8:30 AM on record",
        "Fish it wherever the flow band says the fish hold. On dead-low water that has been Cranor's Island (the Narrows) — drift down from the White Hole, then tie at its head and work it; a boat in an eddy at the head of a rapid upriver reported about 60 rainbows the same way",
        "One drives, one fishes the drift; tied up, both fish. The fly rod and the brown-specific presentations are the things to try, one or two a session — pick the night before",
    ],
    "sources": ["brian", "brief"],
}

# Things to try: one or two a session, chosen the night before and in the boat
# before launch. Each says what to bring and what the journal has so far; the
# stop rule is advice, not law: an hour or until the water changes, then back
# to the core. 'bands' lists the flow bands it fits, which is how the band
# panels point at it. This is where the species split lives now. The keys are
# for code and tests — the page renders titles, not letters. A status that
# starts "untested" is not rendered: if it had caught fish it would say so.
EXPERIMENTS = [
    {
        "key": "A", "title": "Dawn hardware for a brown", "program": "browns",
        "bands": ["minimum", "one_unit", "two_three_units"],
        "text": "First light, before the bait rods go in: a Rooster Tail 1/6 oz gold/orange (the brief's most-cited brown spinner) or the gold Cleo, worked deep along the wood and across the slot. Low light is the one edge a daylight brown program has here.",
        "needs": "A Rooster Tail (1/6 oz gold/orange is the cited one) or the gold Cleo, on the 8 lb rod",
        "sources": ["brief", "brian"],
        "status": "no brown yet — the same lures took 5 rainbows before 8:30 AM, so the hour is right",
    },
    {
        "key": "B", "title": "The first hour of the drop — big bait, tied near wood", "program": "browns",
        "bands": ["minimum", "one_unit", "two_three_units"],
        "text": "When the drop reaches you — the page's time is a guide; the water has arrived ahead of it — tie up by an undercut bank or a root wad and fish the 8 lb rig with the biggest bait aboard: two whole nightcrawlers threaded on a #4, tails dangling, or a Mice Tail with a crawdad tail. Hold it in the soft lane; don't drift it. The first hour of falling water is the best-documented brown window on this river.",
        "needs": "Nightcrawlers in the cooler (bought on the way in) and the 8 lb rigs pre-tied",
        "sources": ["brief"],
        "status": "untested",
    },
    {
        "key": "C", "title": "Sculpin on the split-shot rig", "program": "browns",
        "bands": ["minimum", "one_unit"],
        "text": "The reported trophy bait: a live sculpin, lips-hooked on the split-shot rig (not the White River rig), presented at the openings around the base of big rocks at first or last light. Legal to catch your own — see Bait prep in the rigging reference.",
        "needs": "A hand dip net (on the buy list) and a half hour netting sculpin from the bank the evening before — the one try that costs effort on the day",
        "sources": ["brief", "agfc_code"],
        "status": "untested",
    },
    {
        "key": "D", "title": "The sculpin jig at first light", "program": "browns",
        "bands": ["minimum", "one_unit"],
        "text": "A 1/16 oz marabou jig in 'sculpin' olive/brown (the brief's #1 colour), swum through the deep slot at first light — swum over the weed, not hopped through it.",
        "needs": "The marabou jigs, hooks filed sharp or replaced first — they failed inspection",
        "sources": ["brief"],
        "status": "untested",
    },
    {
        "key": "E", "title": "The Keitech on its Flashy Swimmer", "program": "browns",
        "bands": ["two_three_units", "four_five_units", "high"],
        "text": "Keitech Swing Impact FAT 3.8 or 4.3 on the Flashy Swimmer — the buried point makes it weedless — swum along the bank edge on moving water, white being the named colour for White River browns. Not the 2.8: it rides too high.",
        "needs": "Keitech Swing Impact FAT 3.8 or 4.3, white, and a Flashy Swimmer head",
        "sources": ["brief", "brian"],
        "status": "the 2.8 fished once, no fish; the 3.8 and 4.3 not yet",
    },
    {
        "key": "F", "title": "The fly rod, with a bait rod drifting beside you", "program": "rainbows",
        "bands": ["minimum", "one_unit"],
        "text": "Tied up on dead-low water, the 9 ft 5-wt with an indicator and a sowbug or ruby midge under an egg, on the same water the bait catches on. An hour, then back to the core — this is a learning block, not a parallel program.",
        "needs": "The 9 ft 5-wt, indicators, sowbugs and midges",
        "sources": ["brief", "brian"],
        "status": "1 landed, 2 lost",
    },
    {
        "key": "G", "title": "The crawdad, weedless, on the bait rig", "program": "browns",
        "bands": ["minimum", "one_unit"],
        "text": "The Z-Man TRD CrawZ Texas-rigged on a #1 drop-shot hook — point through the nose, turned back and skin-hooked into the body — on a White River rig tied with a short hook leg (7–12 in): the bell sits in the weed, the craw rides a foot above it with the point buried. Tied up by rock or wood, hold it in the current and twitch it so the claws work. The weed fouled the open Ned head, not the weight: the same bells caught 73 fish through it.",
        "needs": "The Z-Man TRD CrawZ, #1 drop-shot hooks and the bells; a pack of Z-Man Finesse BulletZ 1/10 oz weedless heads (on the buy list) if the hop-and-settle matters",
        "sources": ["brief", "brian"],
        "status": "untested",
    },
]

# Tried, or ruled out on contact with the river, and parked with the reason —
# kept on the page so it is not re-learned next year.
PARKED = [
    {
        "what": "Night browns",
        "why": "Prime time for the big fish, and not fishable for us — we are off the water by dark. Sculpin for bait are netted from the bank after dark, not from the boat",
        "sources": ["brief"],
    },
    {
        "what": "The crawdad on the open Ned head — the Z-Man TRD CrawZ, or the green pumpkin Senko half, on the 1/10 oz mushroom head",
        "why": "Fouls in the aquatic weed every cast at the White Hole. The forage is real (one seen on the gravel), so the craw gets a weedless presentation instead — the weedless crawdad under Things to try — and the open mushroom heads stay home",
        "sources": ["brian"],
    },
]


def experiments_for(band):
    """The keys of the things to try that fit a flow band, in list order."""
    return [x["key"] for x in EXPERIMENTS if band in x["bands"]]


def experiment_titles_for(band):
    """The titles of the things to try that fit a flow band — what the panel prints."""
    return [x["title"] for x in EXPERIMENTS if band in x["bands"]]


# ---------------------------------------------------------------------------
# For a reader who has never fished a tailwater: the words the page uses
# without stopping (CFS, units, the places, the rig, the baits, who publishes
# what). Collapsed — the regulars don't want it and the newcomer taps once.
# ---------------------------------------------------------------------------
NEW_HERE = [
    "<strong>CFS</strong> is cubic feet per second — how much water the dam is letting through. Under 2,000 is minimum flow (the river at its lowest, wadeable); each generating <strong>unit</strong> — one of Bull Shoals Dam's eight turbines — adds roughly 3,300 CFS, and past two units nobody wades",
    "The water takes <strong>1.5–4 hours</strong> from the dam to the White Hole, slower at low flow. The arrivals table above is the warning, and it has run a few minutes behind the river: when the water starts to climb the gravel bar, the rise is here, whatever the page says",
    "<strong>The places</strong>: the White Hole is the ramp and the hole below it, 7 miles below the dam — everything on this page is measured there. Gaston's is the resort 3 miles upstream; Cranor's Island (the run into it is the Narrows) is 2.5 miles down, the usual turnaround",
    "<strong>The White River rig</strong> is the local bottom-bait rig: a bell sinker on the bottom end of the leader, the bait on a long leg above it so it rides up off the rock. The drawing is under Rigging below. Bell sinkers are numbered backwards — #10 is 1/8 oz, #4 is 1 oz — and so are hooks: a #6 is smaller than a #4, a #1 is big",
    "<strong>The baits</strong>: a Power Egg is a moulded floating egg (not the jarred dough); a Mice Tail is a moulded egg with a worm tail; a crawdad tail is the tail of a soft-plastic craw threaded on the same hook — that combination has caught most of the fish on record here. Nightcrawlers are bought on the way in",
    "<strong>Who publishes what</strong>: the Corps (US Army Corps of Engineers) runs the dam and reports each hour's release — the \"released\" rows above. SWPA (Southwestern Power Administration) sells the power and posts the generation schedule — the \"scheduled\" rows. The USGS gauges measure temperature and oxygen below the dam",
]


# ---------------------------------------------------------------------------
# Band content: what changes with the flow — where the fish hold, how the boat
# is handled, whether wading is on, the rig for the band and the tackle notes
# that only make sense at that level. Spin and fly are separate by design.
# The species split (browns vs rainbows & others) lives in EXPERIMENTS, not
# here: the core program is the same rig and bait in every band.
# ---------------------------------------------------------------------------

BAND_CONTENT = {
    "minimum": {
        "label": "Minimum flow (dead low)",
        "sources": ["his_place", "brief", "brian", "agfc_code"],
        "summary": "Gravel bars exposed; prop strikes are the boat risk and the White Hole "
                   "ramp can be tricky to launch. Wading is wide open until the rise. Fish "
                   "see everything — go light for rainbows, go dark (not light) for browns. "
                   "The river carries ~200 CFS more than the release figure says (the house "
                   "unit and leakage through the closed gates are not counted in it).",
        "go": "Drift down from the White Hole ramp to Cranor's Island (the Narrows) and tie at its head — that is where the low-water fish have come from; the weed-bed edges above the ramp are the second choice",
        "where": [
            "Cranor's Island (the Narrows) — fish both sides, deepest water on the far side; downstream holds low water longest. Where the low-water fish on record came from — though a boat in an eddy at the head of a rapid upriver did as well",
            "The weed-bed edges a short run upstream of the White Hole ramp — sowbug and scud water; trout hold on the edges and pick",
            "The head of the White Hole where the deep water starts at the ramp and runs downstream",
            "The downstream lip (drop-off) of every shoal, where gravel falls into the run",
            "The seam where the main tongue runs past a moss/grass bed — the single most important low-water feature",
            "Undercut banks, root wads, log jams, boulder pockets (brown water)",
        ],
        "boat": [
            "Bank-tie is easy and anchoring is safe at this level — until the rise. Pull the anchor before the time the arrivals table gives and tie to the bank if you are staying",
            "Watch the prop over gravel bars; know the channel before running",
            "Low water lingers longest downstream — run down early, work back upstream as any afternoon water arrives",
        ],
        "wading": [
            "Wide open — until the rise arrives: the bars, the shoal tails and the weed-bed edges above the ramp. Check the arrivals table before stepping off the boat, and watch the water, not the page: at the ramp the grey rock on the gravel bar's far edge goes under first, and the rise has reached it minutes ahead of the page's time. The one wade on record caught nothing — water to try from the bank, not the program",
        ],
        "spin": {
            "rig": "White River rig — 1/8 oz bell (#10), 44 in hook leg (the 3/16 has done the job so far; the 1/8 is still to be tried)",
            "notes": [
                "The core bait on the rig: a Power Egg (orange or white) or a Mice Tail with a crawdad tail; the changes are crawler stubs, peeled shrimp chunks (they stay on in current) or the egg-bead variant — an orange bead pegged a couple of inches above a bare #4 on the hook leg",
                "Float rig, worth a try in the slow lanes (reported, not yet fished here): slip float + bobber stop, 1/16 oz panfish head with a 2 in white grub or pink-head crappie jig, 1–3 ft off bottom, fed 40–80 ft downstream and repeated",
                "1/16 oz Beetle Spin or the small Panther Martin along seams and soft edges; the Cleo or Rooster Tail at first light (Things to try)",
                "One rod per angler in the water (regulation) — keep the second rod rigged and ready to swap, not fishing",
            ],
        },
        "fly": {
            "setup": "9 ft 5-wt (Recon). Tightline the near seam with a 10–12 ft thin leader (the owned "
                     "20 lb fluoro makes the butt), or a short indicator drift, 20–25 ft max, indicator "
                     "~1.5× depth — stick-on indicators hold on fine tippet at this flow. 4 lb-class "
                     "tippet (5X) on the nymph rig; 8 lb on the sink leader for the swing.",
            "notes": [
                "Gray sowbug #14–16 point + Zebra/Ruby Midge #16–18 dropper 18 in above, on the near seam — the rig that took the first fly fish here (Things to try)",
                "Pink San Juan worm or peach/orange egg the moment any water starts moving up",
                "Olive Woolly Bugger #8–10 or black Girdle Bug #8–10 swung at first and last light; the Sunday Special #12 tungsten dredged through the deep slots where the big fish hold",
                "Swing the soft hackle through shoal tails and hang it 6–10 seconds at the dangle — a trophy-finding presentation",
            ],
        },
    },
    "one_unit": {
        "label": "Around 1 unit (2,000–5,000 CFS)",
        "sources": ["his_place", "brief", "brian"],
        "summary": "The best all-round level. The channel runs cleanly and shoals are passable "
                   "with care. Wading is marginal: from the bank side only, and the bars go under first.",
        "go": "The seams where slow water meets the current — tie in the slack and cast to the seam; the head of the White Hole and the shoal-tail drop-offs, or drift the seams and motor back up",
        "where": [
            "Seams where slow water meets the main current — tie in the slack, cast to the seam",
            "The head of the White Hole and the shoal-tail drop-offs",
            "Both sides of Cranor's Island (deepest water far side)",
            "Behind logs, rocks and boulders; downstream of islands; inside bends",
        ],
        "boat": [
            "Tie from the BOW, bow pointed upstream, slip knot at the cleat, knife within reach",
            "When a spot quits, move: untie, drop 100 yards, retie",
            "Drifting works well at this level: drift the seams, motor back up, repeat — one drives and sits out, the other fishes",
        ],
        "wading": [
            "Marginal: from the bank side only, with caution — the bars go under first, so never wade out onto one",
        ],
        "spin": {
            "rig": "White River rig — 1/4 oz bell (#8), 32 in hook leg",
            "notes": [
                "The core bait on the rig through the seams: a Power Egg or Mice Tail with a crawdad tail, crawler stubs or shrimp",
                "1/4 oz spoons — Kastmaster chrome or blue/chrome, the gold Kastmaster or the gold Cleo; gold in bright sun, silver under cloud",
                "1/4 oz Rooster Tail (flame/chartreuse) or Mepps Aglia #3, quartering upstream, sink first, steady retrieve — the take comes on the swing (Black Fury #3 on dark days)",
                "The downstream hang with a spinner: let it swing dead below the tied boat and hold — the blade works on current alone",
                "3-in minnow on the split-shot rig, lips-hooked: cast quartering upstream and drift it past structure and drop-offs, feeding line to stretch the drift",
                "The sinking swimmers (Countdown class — brown-trout, brook-trout patterns) counted down and twitched along the drop-offs",
                "Float rig in the slower lanes, still effective to ~2 units",
                "Never clip a snap swivel to a spinner — run an 18 in leader to a small barrel swivel up the line",
            ],
        },
        "fly": {
            "setup": "Indicator rig with real weight (Airlock/Thingamabobber class), the swing setup, "
                     "or the streamer sink-leader: the fast-sinking RIO VersiLeader looped on the "
                     "floating line ('insta-sink-tip'). 4 lb-class tippet (5X) under the indicator; "
                     "8 lb fluoro on the sink leader.",
            "notes": [
                "Sowbug/midge pair under the indicator through the seams; lengthen the drift by feeding line",
                "Swing soft hackles, covering water by lengthening 20, 25, 30, 35 ft",
                "Egg and pink San Juan worm near the banks whenever the water is moving up",
                "Olive Woolly Bugger #8–10 / black Girdle Bug #8–10 on the sink leader, swung — not stripped — through bank seams and shoal tails; Sunday Special #12 tungsten deep in the slots",
            ],
        },
    },
    "two_three_units": {
        "label": "2–3 units (5,000–10,000 CFS)",
        "sources": ["his_place", "brief", "brian"],
        "summary": "Fish move to the banks and flooded grass. No wading. Fish the edges, "
                   "not open water — and the brown-trout window starts opening.",
        "go": "The banks: tie high to a tree and fish the flooded grass and gravel that was dry an hour ago — worms near the bank in the first hour of the rise",
        "where": [
            "Bank edges and newly flooded grass/gravel that was dry an hour ago — soft current, dislodged food",
            "Inside bends and the shelf-to-channel drop-off",
            "Behind bank structure: logs, root wads, boulders",
            "Foam lines and defined runs in 4–5 ft along the banks",
        ],
        "boat": [
            "Tie high to a tree, not the anchor — a bump in generation reaches this reach fast",
            "Tie from the BOW with slack, re-tend the rope every 20–30 minutes on rising water",
            "Bank-lane drifts are the coverage alternative to tying — the driver sits out, the other fishes",
            "Know what's downstream before committing to a spot; there is no warning siren on this river",
        ],
        "wading": [
            "No wading",
        ],
        "spin": {
            "rig": "White River rig — 3/8 oz bell (#7), 20 in hook leg",
            "notes": [
                "Worms cast near the banks in the first hour of the rise — a documented, predictable pattern, not folklore",
                "The rig with crawler stubs, shrimp, or the egg and crawdad tail in the soft lanes off the main push; walk it down — lift, feed 3–6 ft, re-settle — a 100-yard drift from a fixed boat",
                "3/8 oz Kastmaster (blue/chrome) in the defined runs when the 1/4 oz won't stay down",
                "Float rig only in true slack edges at this flow",
                "Jerkbait prime time (2–4 units): the sinking swimmers and the suspending perch deep jerkbait, twitch-pause along the banks; the Keitech on its Flashy Swimmer is under Things to try",
            ],
        },
        "fly": {
            "setup": "Streamer water: fast-sinking polyleader, weighted #6–10 flies, swung not stripped, "
                     "8 lb fluoro on the sink leader. Nymphing gets hard at 3+ units from a seat.",
            "notes": [
                "Olive Woolly Bugger #8–10 / black Girdle Bug #8–10 swung through the bank seams — this is the program now; hang every swing at the dangle before recasting",
                "Pink San Juan worm or egg dead-drifted tight to the flooded grass on the rise",
            ],
        },
    },
    "four_five_units": {
        "label": "3–5 units (10,000–16,500 CFS)",
        "sources": ["his_place", "brief", "brian"],
        "summary": "Boat water — and the big-brown window. Drag chain, not anchor. "
                   "Bank ties need a real eddy. No wading anywhere.",
        "go": "Soft water only — real eddies, inside bends, the shelf where the flooded bank drops to the channel; drag chain or tie high in a true eddy, never anchor",
        "where": [
            "Bank edges with soft water: real eddies, inside bends, current breaks behind structure",
            "The shelf where flooded bank drops to channel — big browns take station on it",
            "Slack pockets downstream of Cranor's Island",
        ],
        "boat": [
            "Do NOT anchor in current — this is how people drown on this river. Drag chain (legal on the White) or tie high in a genuine eddy",
            "Bow upstream, slip knot, knife in reach, re-tend the rope constantly",
            "Drifting the soft bank lane covers the minnow/swimbait water a tied boat can't reach — the driver drives, the other fishes",
            "Debris starts moving at these flows; keep watch upstream",
        ],
        "wading": [
            "No wading anywhere",
        ],
        "spin": {
            "rig": "White River rig — 1/2 oz bell (#6), 20 in hook leg",
            "notes": [
                "Soft-water soaks only: the rig with a whole crawler or shrimp in eddies and slack lanes off the push — honestly a browns level; save the numbers game for the drop",
                "3-in minnow on the split-shot rig (stack shot to match the push), lips-hooked, drifted down the bank edge from a tied boat — work the lane flowing past you",
                "Keitech FAT 3.8/4.3 on the 3/8 oz Flashy Swimmer swum along the bank (Things to try); the suspending perch jerkbait with long pauses in eddies and seams",
                "Calibrate weight: the rig should hold, then slip a few inches when the tip is lifted. Never moves = too heavy; never stops = too light",
            ],
        },
        "fly": {
            "setup": "Honestly limited water for a floating-line 5-wt. If you fish it: the sink-leader "
                     "swing (8 lb fluoro) from a boat tied in a true eddy, or park the fly rod until the drop.",
            "notes": [
                "Olive Woolly Bugger / black Girdle Bug #8 swung slow and deep through eddy seams",
                "A worm or egg under a heavily weighted indicator in true slack only",
            ],
        },
    },
    "high": {
        "label": "Heavy generation (16,500+ CFS)",
        "sources": ["his_place", "brief"],
        "summary": "20,000+ CFS class water. Debris moving, no wading anywhere, and this is not "
                   "a small-rental-jon proposition. Fish true slack water only — or wait for the drop.",
        "go": "True slack water only, or stay on the ramp — the fishing is the drop, when it comes",
        "where": [
            "True slack water only: backwaters, the inside of the biggest eddies, flooded margins out of the current",
            "Seriously consider not launching — watch the SWPA schedule for the cut and plan around the fall-out instead",
        ],
        "boat": [
            "Never anchor. Never tie in current. If afloat, stay in slack water and off the main flow",
            "Re-check the schedule and the ramp before committing — this level with a rental jon is a risk decision, not a tactics decision",
        ],
        "wading": [
            "No wading anywhere",
        ],
        "spin": {
            "rig": "White River rig — 1 oz bell (#4), 20 in hook leg; slack-water soaks only",
            "notes": [
                "Whole crawlers or shrimp soaked on the rig in true slack edges — that's the whole program",
                "4 in white Tab Tail or Keitech 4.3 on its swimbait head (tied direct), pitched along slack margins for a hunting brown (Things to try)",
                "The honest play is timing, not tackle: fish the first hours after the cut, when the river drops back through the good bands",
            ],
        },
        "fly": {
            "setup": "The fly rod stays cased at this level.",
            "notes": [],
        },
    },
}

# What to say about temperature/oxygen when the USGS reading is unavailable
WATER_FALLBACK_NOTES = {
    "fall": "No temperature reading from the USGS gauge right now. Fall is the oxygen sag as the lake turns over: land fish fast, keep them wet",
    "spring": "No temperature reading from the USGS gauge right now. Expect cold, oxygen-rich water; slow the presentation down",
}

SEASON_CONTENT = {
    "fall": {
        "label": "Fall (September–October): pre-spawn browns",
        "sources": ["brief", "usgs"],
        "timing": [
            "Typical fall pattern: minimum flow through the morning, generation arriving afternoon/evening — run downstream early, fish the low water, work back up on the rise",
        ],
        "notes": [
            "Browns are staging pre-spawn — aggression without redds. Reported to be eating big (sculpin here run 5–6 in), and the crawdad tail is what has actually caught here",
            "Stage points: upper ends of holes (trophy browns found in as little as 5 ft), shoal-tail drop-offs, undercut banks and wood",
            "Rainbows are on sowbugs, scuds and midges, and on worms when the water comes up",
            "Not a dry-fly month — nymphs and streamers; hoppers on warm afternoons are the exception",
        ],
        "spin_add": [
            "Orange garlic is the named fall colour — as Power Eggs, the moulded kind, never the jarred dough. White eggs with a crawdad tail did as well for the boat beside us",
        ],
        "fly_add": [
            "A #10 hopper on warm afternoons — browns here reportedly favor pink and black/purple; dry-dropper it over the soft bank water",
        ],
        "gear_add": {
            "spin": {
                "bench": [
                    "Warm-water season line rule: fluoro hook legs (they sink) — except on floating-bait rigs, which stay mono",
                ],
                "pack": [
                    "The soft craw — Z-Man TRD CrawZ 2.5 in Mudbug x12 — OWNED, packs for the weedless-craw try with the #1 drop-shot hooks; the open 1/10 oz mushroom heads stay home, they drag weed every cast here",
                ],
                
            },
            "fly": {
                "buy": [
                    "A few #10 hoppers in pink and black/purple (~$6) — the colors browns here reportedly favor",
                ],
            },
        },
    },
    "spring": {
        "label": "Spring (March–April): post-spawn rainbows, front edge of the caddis",
        "sources": ["brief", "agfc_regs"],
        "timing": [
            "Typical spring pattern: the bite skews later — mid-morning through afternoon, then the evening caddis window. Overcast and rainy days are the best days",
        ],
        "notes": [
            "Rainbows are post-spawn and feeding normally; stockings are still thin after the 2025 hatchery losses — temper numbers expectations, brown expectations are intact or better",
            "The caddis hatch truly fires at flows around 4,000 CFS or less and works upstream from the lower river — early April usually catches the front edge here, not the peak",
            "The tell: evening swarms of egg-laying caddis; activity picks up after 5 pm",
            "BWOs on grey days; shad get pulled through the dam on big water",
            "When Crooked Creek and the Buffalo rise on rain, the Corps cuts generation to protect Newport — rain can hand you surprise low water",
        ],
        "spin_add": [
            "Yellow and orange egg colors are the named March–April producers — run them as the egg-bead variant or Power Eggs on the White River rig",
            "On big spring water, white swimbaits on their Flashy Swimmer heads (tied direct) imitate shad pulled through the dam — fish them along the banks for a brown",
        ],
        "fly_add": [
            "Swing the caddis pupa — one of the best trophy-brown presentations of the spring",
            "Add the Tailwater Soft Hackle in caddis green #14 (the swinging fly) and an Elk Hair Caddis #14 for the after-5-pm window",
        ],
        "gear_add": {
            "spin": {
                "bench": [
                    "Cool-water season line rule: mono hook legs (they float with the drift)",
                ],
            },
            "fly": {
                "buy": [
                    "Caddis consumables for the fly box: Tailwater Soft Hackle caddis-green #14 and Elk Hair Caddis #14",
                ],
            },
        },
    },
}

REGULATIONS = [
    "Keep only 2 rainbows under 14 in; every other trout goes back immediately (Bull Shoals Dam to Norfork Access, effective Feb 2026) — browns are catch-and-release here",
    "Bait fishing = single hooking point per pole. Swap trebles for a single hook before tipping any spoon or spinner with shrimp/crawdad",
    "One rod per angler, attended at all times",
    "Trout permit required (16+) in addition to the fishing license",
    "Verify current limits by phone before the trip: AGFC 833-345-0325 — the Feb 2026 limits replaced an emergency order and hold until further notice, so they can change again",
]

# Core, season-independent packing list. Two axes: the kind of gear (spin and
# fly never mix, boat is shared) and the action each item asks for, which is
# how the page groups it (GEAR_ACTIONS). Each season appends its own gear_add
# items, keyed the same way, in generate_fishing_report
GEAR_ACTIONS = [
    ("buy", "To buy"),
    ("verify", "To verify"),
    ("bench", "Bench jobs at home"),
    ("pack", "Owned — pack it"),
]
GEAR_KINDS = [
    ("spin", "🎣 Spin gear:"),
    ("fly", "🪶 Fly gear:"),
    ("boat", "🛶 Boat &amp; trip gear:"),
]

GEAR_CHECK = {
    "spin": {
        "buy": [
            "Z-Man Finesse BulletZ 1/10 oz weedless heads (~$6) — the weedless Ned head for the CrawZ, the alternative for the weedless-craw try when the hop-and-settle matters",
            "Hand dip net for netting sculpin from the bank (~$8, e.g. Frabill 9x8 baitwell net) — fine mesh well under the 1 in legal max, short handle for one-hand work against the rocks",
            "Bait is bought fresh in Arkansas on the way in — one stop, kept in the cooler, not a run after each session: night crawlers + red worms, Power Eggs (orange-garlic in fall), pink/white Mice Tails or floating worms, cocktail shrimp, corn — plus mini marshmallows for flotation. NO jarred PowerBait dough — the line is drawn by form, not by the brand: the moulded eggs and Mice Tails stay",
        ],
        "verify": [
            "The bell ladder is OWNED in the middle — 3/16, 1/4, 3/8 and 1/2 oz (#9/#8/#7/#6) are on the shelf; verify or buy the two ends, 1/8 oz (#10) for minimum flow and 1 oz (#4) for 4+ units",
        ],
        "bench": [
            "Pre-tie whole White River rigs at home, wound on a foam disc: one piece of leader per rig, a few at each hook-leg length (44 / 32 / 20 in) in each line class — 4 lb mono for rainbows, 8 lb fluoro for browns",
            "#16 orthodontic rubber bands — OWNED, a bag of 100 ¼ in dental elastics — the breakaway sinker attachment, on probation: hard to tie on and they collect weed. Decide whether the breakaway stays before pre-tying rigs around it; if it stays, pull-test one on the tailgate before the first cast — the band must let go before the rig does",
            "Marabou jigs: the inventory records their hooks as failed inspection — file the points sharp or replace them before the 'sculpin' jig presentations count on them",
        ],
        "pack": [
            "Brown program leader: a spool of 8 lb fluorocarbon — OWNED",
            "Rainbow program leader: 4 lb, and it is OWNED, not a purchase — the Maxima Chameleon 4 lb wheel on the line shelf is what the whole rig is tied from, with a boxed Trilene XL 4 lb clear behind it for bulk. The 20/30 lb fluoro is rope in this water",
            "#6 Aberdeens — OWNED, a 50-pack beside the #4s — the light-wire hook for eggs and Mice Tails, where the #4 is oversized",
            "Worm blower — OWNED (Magic 1004); the inflated-crawler presentations depend on it, so it packs rather than gets bought",
            "The browns rod — OWNED: St. Croix SCPS70MF2-SG, 7 ft medium, 10-17 lb, 1/4-3/4 oz, 2-piece — lives at Dad's. The Black Max 30 travels to meet it, respooled to 10 lb mono: the main out-tests the 8 lb browns leader so break-offs happen at the hook leader. Anything the browns program throws under 1/4 oz goes on the St. Croix ultralight",
            "The AR reels are respooled and bagged: President 20 on 4 lb, Exceler 2000 SH on 6 lb, Black Max 30 on 10 lb. The RODS live at Dad's, the reels travel — so this is a bench job at home, not a job on arrival: the Dforce DWB-562MLS is the rainbow rod on light mono (a 5 ft 6 in medium-light, 6-12 lb, 1/8-3/8 oz; the 4 lb main sits under its rating and stays until a Presso ultralight replaces the rod at Dad's next season), and the St. Croix out-tests the 4 lb rainbow hook leaders and carries the spinner work — but its ultralight blank can never take the browns main",
        ],
    },
    "fly": {
        "buy": [
        ],
        "verify": [
            "Rainbow program tippet: 4 lb-class fluoro (5X) — VERIFY: fly gear isn't in the inventory yet",
            "Fly box audit (fly gear isn't inventoried yet — verify or buy): gray sowbug #14–16, Sunday Special #12–14 incl. tungsten, Zebra/Ruby Midge #16–18, pink San Juan worm, peach/orange egg, olive Woolly Bugger #8–10, black Girdle Bug #8–10, plus this season's adds",
        ],
        "pack": [
            "RIO Trout VersiLeader, 7 ft 12 lb fast-sinking — OWNED, two of them — the 'insta-sink-tip' the brown streamer program runs on; loop one onto the floating line and leave it there for the trip",
            "Brown program tippet: the same OWNED 8 lb fluoro spool as spin — 3–4 ft on the sink leader for the streamer swing",
            "A 2 mm tippet ring finishes the tightline leader butt (out of the owned 50-pack) — on probation: the ring stops the indicator sliding and is likely to go, though a knot in the same place would stop it just the same",
        ],
    },
    "boat": {
        "verify": [
            "Drag chain for 3+ units — check whether the resort provides one before buying",
        ],
        "pack": [
            "Tie-up rope (50+ ft) and a sharp fixed-blade knife in a sheath — the two non-negotiables",
            "Headlamp — sculpin for bait are netted from the bank after dark, at the ramp, not from the boat",
            "Polarized glasses — the structure-reading tool at low water",
        ],
    },
}


# ---------------------------------------------------------------------------
# Static rigging & techniques reference. Renders as collapsible blocks after
# the gear check — informational, unchanged by flow or season. Spin and fly
# blocks stay separate; boat handling and etiquette are shared seamanship.
# ---------------------------------------------------------------------------

# Inline diagram of the one-piece White River rig as Brian ties it. Literal
# colours, because the report page has no CSS custom properties and no dark
# mode. The main line is drawn in ink and the rig — one piece of leader — in
# orange: everything orange is tied at home and swapped as a unit.
SPIN_RIG_SVG = '''
<svg viewBox="0 0 420 356" role="img" aria-labelledby="rigttl"
     style="width:100%;max-width:430px;height:auto;display:block;margin:10px auto 0;">
  <title id="rigttl">The White River rig tied in one piece: the main line clinches to a loop
  tied in a single length of leader; below the loop a 7 inch sinker leg ends in a bell sinker on the
  bottom; above it the same leader runs on as the hook leg, 44, 32 or 20 inches to the hook, where
  the bait rides up off the bottom</title>
  <g fill="none" stroke="#2d3748" stroke-width="1.6" stroke-linecap="round">
    <path d="M100 10 L100 118"/>
  </g>
  <g fill="none" stroke="#c05621" stroke-width="1.9" stroke-linecap="round">
    <path d="M100 118 c -9 6, -9 18, 0 24 c 9 -6, 9 -18, 0 -24"/>
    <path d="M97 142 L83 246"/>
    <path d="M104 140 C 170 170, 250 212, 320 246"/>
  </g>
  <path d="M83 246 l-11 30 h22 z" fill="#4a5568" stroke="none"/>
  <path d="M0 280 C 70 272, 140 288, 210 278 S 340 284, 420 274"
        fill="none" stroke="#cbd5e0" stroke-width="2.5"/>
  <g fill="#cbd5e0" stroke="none" opacity=".75">
    <circle cx="40" cy="290" r="8"/><circle cx="130" cy="295" r="10"/>
    <circle cx="250" cy="288" r="8"/><circle cx="355" cy="292" r="11"/>
  </g>
  <path d="M320 246 l0 12 a9 9 0 1 0 -13 -6"
        fill="none" stroke="#2d3748" stroke-width="1.6" stroke-linecap="round"/>
  <circle cx="323" cy="248" r="9" fill="#2b6cb0" stroke="none"/>
  <g font-family="SFMono-Regular, Menlo, Consolas, monospace" font-size="10.5" fill="#718096">
    <text x="114" y="40">main line, as spooled</text>
    <text x="114" y="96">clinch knot to the loop</text>
    <text x="114" y="132" fill="#c05621">loop 7 in above the bell</text>
    <text x="2" y="190" fill="#c05621">7 in</text>
    <text x="2" y="232">bell #10–#4</text>
    <text x="150" y="252" fill="#c05621">hook leg  44 / 32 / 20 in</text>
    <text x="150" y="267">minimum · 1 unit · 2+ units</text>
    <text x="418" y="266" text-anchor="end">bait rides up</text>
  </g>
  <g font-family="SFMono-Regular, Menlo, Consolas, monospace" font-size="10" fill="#718096">
    <path d="M8 314 l22 0" fill="none" stroke="#2d3748" stroke-width="1.6" stroke-linecap="round"/>
    <text x="38" y="318">main line · 4 lb (rainbows) or 10 lb (browns) as spooled</text>
    <path d="M8 338 l22 0" fill="none" stroke="#c05621" stroke-width="1.9" stroke-linecap="round"/>
    <text x="38" y="342">the rig · one piece · 4 lb mono rainbows, 8 lb fluoro browns</text>
  </g>
</svg>
<p style="font-size: 0.82em; color: #718096; text-align: center; margin: 8px auto 4px; max-width: 430px; line-height: 1.5;">
  One piece of leader, tied at home and swapped whole: a snag costs the rig, so carry several at
  each hook-leg length. The loop sits 7&nbsp;in above the bell on every rig; only the hook leg
  changes with the flow.
</p>'''


# The split-shot drift rig — the livebait exception to the Y. Same drawing
# conventions as SPIN_RIG_SVG: ink for line and hook, orange for the one
# thing that makes this rig what it is (the pinched shot), literal colours.
SPLIT_SHOT_RIG_SVG = '''
<svg viewBox="0 0 420 316" role="img" aria-labelledby="ssrigttl"
     style="width:100%;max-width:430px;height:auto;display:block;margin:10px auto 0;">
  <title id="ssrigttl">The split-shot drift rig: main line to a small swivel or tied direct, then a
  single 8 lb fluorocarbon leader running straight to a number 1 drop-shot hook, with one or two
  split shot pinched about a foot above the hook; a sculpin hooked through the lips swims at the
  opening between two boulders on the bottom</title>
  <g fill="none" stroke="#2d3748" stroke-width="1.6" stroke-linecap="round">
    <path d="M60 10 L60 44"/>
    <ellipse cx="60" cy="52" rx="5" ry="8" stroke-width="1.4"/>
    <path d="M60 60 C 90 120, 150 170, 214 196"/>
    <path d="M222 199 C 262 214, 296 226, 318 236"/>
  </g>
  <g fill="#c05621" stroke="none">
    <circle cx="218" cy="197" r="6.5"/>
    <circle cx="207" cy="192" r="6.5" opacity=".45"/>
  </g>
  <path d="M0 262 C 60 256, 120 268, 180 260 S 300 268, 420 258"
        fill="none" stroke="#cbd5e0" stroke-width="2.5"/>
  <g fill="#cbd5e0" stroke="none" opacity=".85">
    <ellipse cx="290" cy="262" rx="30" ry="18"/>
    <ellipse cx="368" cy="264" rx="34" ry="20"/>
    <circle cx="90" cy="270" r="9"/>
  </g>
  <path d="M318 236 l0 12 a9 9 0 1 0 -13 -6"
        fill="none" stroke="#2d3748" stroke-width="1.6" stroke-linecap="round"/>
  <path d="M312 242 c -14 -4, -24 4, -30 6 c 8 4, 20 8, 32 2 z" fill="#2b6cb0" stroke="none"/>
  <g font-family="SFMono-Regular, Menlo, Consolas, monospace" font-size="10.5" fill="#718096">
    <text x="74" y="28">main line, as spooled</text>
    <text x="74" y="56">size 10 swivel — or tie direct</text>
    <text x="118" y="112" fill="#2b6cb0">leader 8 lb fluoro, 30–40 in</text>
    <text x="118" y="126" fill="#2b6cb0">no Y, no bell — straight to the hook</text>
    <text x="412" y="168" text-anchor="end" fill="#c05621">split shot ~12 in above the hook</text>
    <text x="412" y="182" text-anchor="end" fill="#c05621">stack a second as the push demands</text>
    <text x="8" y="292">#1 drop-shot hook · sculpin through the lips</text>
    <text x="412" y="308" text-anchor="end">swims at the opening between the rocks</text>
  </g>
</svg>
<p style="font-size: 0.82em; color: #718096; text-align: center; margin: 8px auto 4px; max-width: 430px; line-height: 1.5;">
  The livebait exception: no loop and no bell, so nothing hangs below the bait to plant in
  the rock. A pinched shot rides over what a bell snags in, and the sculpin swims where a brown
  expects to see one. This is browns-program tackle, so it never goes out on the 4&nbsp;lb spool.
</p>'''


RIGGING_REFERENCE = [
    {
        "title": "The White River rig (spin)",
        "intro": "One piece of leader, tied at home: the bell on the bottom end, a "
                 "loop 7 in above it that the main line clinches to, and the hook leg "
                 "running on from the loop to the hook. The diagram is the rig. What "
                 "follows is how to size it, tune it and fish it, not how to tie it.",
        "figure": SPIN_RIG_SVG,
        "items": [
            "Tune the hook leg, never the weight leg: the sinker leg is 7 in on every rig, the hook leg is 44, 32 or 20 in — 44 at minimum flow, 32 around 1 unit, 20 from 2 units up — and you change it by swapping to the next pre-tied rig, not by retying on the water. Faster water wants it shorter, because a long leg lays flat; minimum flow wants it long. Trim to tune, swap up when the water drops",
            "The whole rig is tied in the species program's line — 4 lb mono = rainbows, 8 lb fluoro = browns — because there is no base to hide behind: the main line clinches straight to the loop, so the fish inspects the rig's own line and a snag costs the whole rig. That is why they are pre-tied in numbers, and why the main line is spooled at or above the rig's test, so the knot at the loop is where it breaks",
            "The rubber-band breakaway — on probation (hard to tie on, collects weed; it may go): finish the bell end with a small overhand loop instead of clinching it to the bell, girth-hitch a #16 orthodontic rubber band through that loop, pass the band's free end through the bell's eye and back over the bell. A snagged bell then tears the band and the rig comes back",
            "Pre-tie the rigs at home, wound on a foam disc: a few at each hook-leg length in each line class, plus a couple of #1 sculpin rigs. An evening's work that turns a mid-drift re-rig into a ten-second swap",
            "Bell sinker numbers (local shorthand): #10 = 1/8 oz · #9 = 3/16 · #8 = 1/4 · #7 = 3/8 · #6 = 1/2 · #5 = 3/4 · #4 = 1 oz — bells only, skip the rubber-core sinkers. Starting size by flow band: minimum #10 · 1 unit #8 · 2–3 units #7–#6 · 4+ units #6–#4. Calibrate on the water: it should tick bottom on the swing and slip when the tip lifts, never plant",
            "Hook by bait: eggs or Mice Tail #6–#8 · whole crawler #2–#4 Aberdeen · red worm #4 · sculpin/shrimp/crawdad #1–#2 · minnow #6 through both lips · corn or single egg #10–#12",
        ],
    },
    {
        "title": "The split-shot rig (spin)",
        "intro": "The livebait drift exception — sculpin and minnows skip the Y entirely. "
                 "One straight leader, a pinched shot, and the bait swimming free.",
        "figure": SPLIT_SHOT_RIG_SVG,
        "items": [
            "Leader straight from the swivel (or tied direct) to a #1 drop-shot hook — no loop, no bell. This rig fishes the browns program's baits, so the leader is the 8 lb fluoro spool",
            "Pinch one split shot about a foot above the hook; stack a second or third as the current demands. Calibrate like the Y: it should tick bottom on the swing and slip when the tip lifts, never plant",
            "A pinched shot rides over what a hanging bell snags in, and the bait swims naturally — the whole reason this rig exists",
            "Sculpin: hooked through the lips, presented at the openings around the base of big rocks — where they live and where a brown expects to see one. Legal to catch your own (Bait prep below)",
            "Minnows, from 1 unit up: 3 in, hooked through both lips, cast quartering upstream and drifted naturally past structure and drop-offs, feeding line to stretch the drift — drift speed is the whole game; at 3–5 units stack shot to match the push and work the bank lane",
        ],
    },
    {
        "title": "Bait prep (spin)",
        "intro": "",
        "items": [
            "Inflating a crawler: hook it FIRST, then inject 4–5 air bubbles spaced along a large crawler with a worm blower; use the smallest hook that will hold it",
            "Mice Tail / floating worm: run the hook through the center of the worm and out ~½ in behind the head so it floats horizontally — head-hooked it hangs vertically, which is wrong",
            "No floating bait? Thread a mini marshmallow up the hook shank — the other documented flotation method on this river",
            "Keep mono on the hook leg of any floating rig — fluoro sinks and kills the lift",
            "Calibrate weight on the water: cast quartering upstream and let it settle. Right weight holds, then slips a few inches and re-grabs when you lift the tip. Never moves = too heavy; never stops = too light",
            "Catching sculpin — verified legal: banded and Ozark sculpin (the species in this tailwater) are named legal baitfish, and a hand dip net (1 in mesh or finer) is legal for personal use while sport fishing, day or night (AGFC Code 32.04). Flip rocks on shallow cobble and gravel shoal margins at minimum flow with the net held tight downstream — easiest after dark, when they sit out exposed. Keep only sculpin and return every other species immediately; never collect within 100 yards of the dam (32.05); never take them across the state line (32.03)",
            "Minnow traps for sculpin are the slow backup, not the plan: an overnight soak (oily bait, trap flush on the bottom in cobble, or off the dock) yields a handful at best — the dip net outproduces it in 20 minutes. Arkansas wrinkle: traps are limited to 1 gallon capacity with a 1.5 in throat (32.04.D) — a standard Gee torpedo trap is oversized and illegal here",
        ],
    },
    {
        "title": "Boat strategy — tie, drift, or anchor",
        "intro": "Tying to the bank is the default. Drifting and anchoring are both real "
                 "options with their places — and one hard rule: most drownings on this "
                 "river involve an anchor thrown during generation.",
        "items": [
            "TIE (the default): from the BOW, bow pointed upstream — a stern- or side-tied boat in current gets rolled or swamped. Slip knot / quick-release at the cleat, sharp fixed-blade knife in a sheath within arm's reach",
            "Tie HIGH to a tree and leave slack; re-tend the rope every 20–30 minutes once water is coming — a tight, low rope on a rising river pulls a gunwale under",
            "Tie in the slack or eddy and cast to the seam where slow meets fast — put the boat by the fast water, fish the slower water. When a spot quits, move: untie, drop 100 yards, retie",
            "DRIFT (the coverage option): set up at the head of a run, drift the bank lane at current speed, motor back up, repeat. The cost is a rod — the driver is on the tiller and mostly can't fish, so rotate who drives. Earns its keep from 1 unit up, where a tied boat's lanes get thin",
            "On the drift, drop one bell size — a boat moving with the current needs less weight to tick bottom than a tied one",
            "ANCHOR (very low water only): safe at minimum flow. From real current up, NEVER anchor — tie high or run a drag chain instead (legal on the White, banned on the Norfork)",
            "Know what's downstream before committing to a spot — there is no warning siren below the dam",
        ],
    },
    {
        "title": "Presentations from a tied boat (spin)",
        "intro": "The boat can't move, so the bait has to.",
        "items": [
            "45° upstream cast + natural swing: sink on slack, follow with the rod tip as it drifts past, let it come tight below the boat and HOLD — many takes come at the dangle",
            "Downstream cast and hold: the current keeps the leader straight and lifts the bait in the column — the technique for two whole crawlers. Don't yank it back when it starts to rise",
            "Walk the rig down: lift the tip to unweight the sinker, feed 3–6 ft of line, let it re-settle, repeat — turns a fixed position into a 100-yard drift. Fan it: near seam, a rod-length out, far seam",
            "Float rig: set the bait 1–3 ft off bottom, cast up, feed the float 40–80 ft downstream under control, reel back, repeat",
            "Spinners by the clock: quartering upstream (10–11 o'clock) is primary — sink first, steady retrieve, the take comes on the swing. Then straight across at 9 o'clock. Then the downstream hang — the blade turns on current alone, a free presentation only a stationary boat gets. Feed line in 3–6 ft steps to walk it downstream",
            "Snag avoidance: get the bait up off the rock, run a lighter sacrificial sinker leg, prefer bell over egg sinkers in rock, and don't over-weight — a planted sinker is a snagged sinker",
            "Three-up lane discipline (bow tied upstream): stern fishes the long straight-downstream hold in the boat's own lane, middle fishes short on the near seam, bow works upstream-and-across to the far seam — three static lines that never cross. The bow seat also owns the rope: re-tend it and pull the quick-release. Two-up with a driver: the stern/driver inherits the downstream lanes — the two-crawler hold and the spinner hang, the trophy water",
        ],
    },
    {
        "title": "Fly fishing from the tied boat (fly)",
        "intro": "A tied-off boat is a fixed position — and swinging streamers works best "
                 "wading or from fixed positions. The swing is the primary method here, "
                 "not a consolation prize.",
        "items": [
            "Tightline the near seam from the seat: flick 8–15 ft upstream, lead down with the tip high — the highest fish-per-hour presentation from a seat, and the only one that works well in wind",
            "Swing sequence: cast across and slightly down, one upstream mend, let it come tight, swing, then hang and pulse 6–10 seconds at the dangle. Cover water by lengthening 20, 25, 30, 35 ft — don't strike at the grab, let it come tight",
            "Keep casts compact: roll cast, side-arm, or a Belgian/oval cast — a 9-ft rod and a beaded nymph at eye level with someone seated behind you is a real injury risk",
            "Strip into a five-gallon bucket with a couple inches of water in it — the line stays put and out from underfoot",
            "The boat makes its own soft water — a drag-free lane to fish when nothing else is reachable from the tie-up",
            "Fly casting needs a two-man boat: fly angler forward, the other rod fishing straight downstream from the stern in the boat's own lane — different quadrants, the lines never cross. Three aboard, the fly rod stays cased: a 9-ft rod and a beaded fly at eye level with two seated people behind you is a real injury risk",
            "One rod per angler, attended, is the law — no propping a second rod in a holder while casting",
        ],
    },
    {
        "title": "River etiquette",
        "intro": "",
        "items": [
            "Downstream boats hold mid-river; upstream boats hug the bank. The downstream boat has priority running a shoal unless one is already occupied",
            "No-wake around tied or anchored boats and anyone standing in the water",
            "Never run between a fisherman and the bank",
        ],
    },
]


def light_windows_for(current_time):
    """Sunrise/sunset and the dawn/dusk windows at the White Hole pin for the day."""
    tz = current_time.tzinfo or SPOT_TZ
    lat, lon = SPOT_COORDS["White Hole"]
    return suncalc.light_windows(current_time.date(), lat, lon, tz)


def _find_flow_change(current_cfs, forecast_timeline):
    """
    Find the first scheduled SWPA hour that meaningfully changes the flow
    (>= 2000 CFS difference from what's at White Hole now).

    Returns (direction, entry, from_cfs) where direction is 'rise' or
    'drop' and from_cfs is the flow the change replaces (the scheduled hour
    before it, or the current flow for the first hour), or None.
    """
    if not forecast_timeline:
        return None
    previous_cfs = current_cfs
    for entry in forecast_timeline:
        if entry["cfs"] - current_cfs >= 2000:
            return ("rise", entry, previous_cfs)
        if current_cfs - entry["cfs"] >= 2000:
            return ("drop", entry, previous_cfs)
        previous_cfs = entry["cfs"]
    return None


def _find_incoming_change(current_cfs, timeline_data):
    """
    The first plug already released and still on its way that changes the
    flow by >= 2000 CFS — not merely the nearest one, because a same-level
    reading often sits ahead of the real rise or drop. (direction, item) or None.
    """
    for item in timeline_data or []:
        if item.get("status") != "incoming":
            continue
        if item["cfs"] - current_cfs >= 2000:
            return ("rise", item)
        if current_cfs - item["cfs"] >= 2000:
            return ("drop", item)
    return None


def _drop_when(item, current_time):
    """'starts dropping ~4:10 PM and is fully down ~5:40 PM' for a released cut."""
    start = item.get("recession_start")
    down = clock(item["arrival_time"], current_time)
    if start is not None and start <= current_time:
        return f"is dropping now and fully down ~{down}"
    if start is not None:
        return f"starts dropping ~{clock(start, current_time)} and is fully down ~{down}"
    return f"reaches White Hole ~{down}"


def next_water_line(current_cfs, current_time, timeline_data=None, forecast_timeline=None):
    """
    One plain sentence for the top of the report: the next rise or drop at
    White Hole and what to do about it — released water first, the schedule
    second, and an honest 'nothing on the way' when neither has one.
    Returns (direction or None, sentence).
    """
    change = _find_incoming_change(current_cfs, timeline_data)
    if change:
        direction, item = change
        if direction == "rise":
            return ("rise", f"A rise to {item['cfs']:,} CFS ({format_generators(item['cfs'])}) has left "
                            f"the dam and reaches White Hole ~{clock(item['arrival_time'], current_time)}. "
                            f"Be off the bars and upstream of it, or tied high, before then")
        return ("drop", f"A drop to {item['cfs']:,} CFS has left the dam and {_drop_when(item, current_time)}. "
                        f"The first hour of the drop is the bite window")
    scheduled = _find_flow_change(current_cfs, forecast_timeline)
    if scheduled:
        direction, entry, from_cfs = scheduled
        released = clock(entry["scheduled_time"], current_time, minutes=False)
        if direction == "rise":
            eta = dict(spot_arrival_times(entry["scheduled_time"], entry["cfs"], from_cfs))["White Hole"]
            return ("rise", f"A rise to {entry['cfs']:,} CFS ({format_generators(entry['cfs'])}) is scheduled "
                            f"for {released} and should reach White Hole ~{clock(eta, current_time)}. "
                            f"Be off the bars and upstream of it, or tied high, before then")
        name, start, end = next(w for w in spot_recession_windows(entry["scheduled_time"], from_cfs, entry["cfs"])
                                if w[0] == "White Hole")
        return ("drop", f"A drop to {entry['cfs']:,} CFS is scheduled for {released}; White Hole falls "
                        f"{_window_str('', start, end, current_time).strip()}. The first hour of the drop "
                        f"is the bite window")
    if timeline_data is None and forecast_timeline is None:
        return (None, "No dam readings or schedule loaded for this preview — the live page says what is coming")
    return (None, "No rise or drop has been released or scheduled that the page knows of — the arrivals table above is the check")


def build_timing(current_cfs, current_time, timeline_data=None, forecast_timeline=None):
    """
    Build live timing guidance from the repo's flow model:
    - incoming water already released (actual dam readings)
    - the next scheduled change (SWPA forecast)
    - per-spot arrival ETAs via calculate_travel_time
    """
    timing = [
        "Fish the generation change: the leading edge of a rise and the first hour "
        "of falling water beat any time on the clock",
    ]
    season, _ = get_effective_season(current_time)
    timing.extend(SEASON_CONTENT[season]["timing"])

    # The day's low-light windows — the browns program's hours
    light = light_windows_for(current_time)
    if light:
        timing.append(
            f"Low light today: dawn {clock(light['dawn'][0])}–{clock(light['dawn'][1])} "
            f"(sunrise {clock(light['sunrise'])}) · dusk {clock(light['dusk'][0])}–"
            f"{clock(light['dusk'][1])} (sunset {clock(light['sunset'])}) — the browns "
            f"program's hours; at low water fish the dusk window into dark"
        )

    # Water already in transit (actual readings)
    change = _find_incoming_change(current_cfs, timeline_data)
    if change:
        direction, item = change
        if direction == "rise":
            timing.append(
                f"RISE EN ROUTE: {item['cfs']:,} CFS "
                f"({format_generators(item['cfs'])}) reaches White Hole "
                f"~{clock(item['arrival_time'], current_time)} — "
                f"cast worms near the banks in the first hour, then fish the "
                f"{BAND_CONTENT[get_flow_band(item['cfs'])]['label']} program"
            )
        else:
            timing.append(
                f"DROP EN ROUTE: the cut to {item['cfs']:,} CFS {_drop_when(item, current_time)} — "
                f"the first hour of the drop is a prime bite window; it's a "
                f"recession, not a step, so the window is the whole span"
            )

    # Next scheduled change (SWPA)
    change = _find_flow_change(current_cfs, forecast_timeline)
    if change:
        direction, entry, from_cfs = change
        when = clock(entry["scheduled_time"], current_time, minutes=False)
        if direction == "rise":
            etas = spot_arrival_times(entry["scheduled_time"], entry["cfs"], from_cfs)
            eta_str = " · ".join(
                f"{name} ~{clock(eta, current_time)}" for name, eta in etas
            )
            timing.append(
                f"SCHEDULED RISE — be below the front and fish it up; downstream "
                f"water stays low longer. Reaches {eta_str} "
                f"({entry['cfs']:,} CFS, {format_generators(entry['cfs'])}, "
                f"released at {when})"
            )
        else:
            windows = spot_recession_windows(entry["scheduled_time"], from_cfs, entry["cfs"])
            eta_str = " · ".join(
                _window_str(name, start, end, current_time) for name, start, end in windows
            )
            timing.append(
                f"SCHEDULED DROP — fish the first hour of the drop at each spot; "
                f"upstream falls first. Falling water, start of the drop–fully down: "
                f"{eta_str} (cut to {entry['cfs']:,} CFS at {when})"
            )

    return timing


def water_notes(water_quality, season, current_time=None):
    """
    Measured temperature/oxygen lines for the top of the report (from the USGS
    gauges), or the season's generic fallback when no reading is available.
    """
    temp_line, do_line = describe_water_quality(water_quality)
    if not temp_line and not do_line:
        return [WATER_FALLBACK_NOTES[season]]
    source = water_quality["site_label"]
    when = clock(water_quality["observed"], current_time) if current_time else ""
    notes = [line for line in (temp_line, do_line) if line]
    notes[-1] += f" ({source}, {when})" if when else f" ({source})"
    dam = (water_quality or {}).get("dam")
    if dam:
        notes.append(dam_water_line(
            water_quality, clock(dam["observed"], current_time) if current_time else None))
    return notes


# Tap-to-pick labels for the band selector (ported from the White Hole Book's
# flow selector, 2026-09-21): short name + the CFS range, in FLOW_BANDS order
BAND_PICKER = {
    "minimum": ("Min flow", "under 2,000"),
    "one_unit": ("~1 unit", "2,000–5,000"),
    "two_three_units": ("2–3 units", "5,000–10,000"),
    "four_five_units": ("3–5 units", "10,000–16,500"),
    "high": ("Heavy", "16,500+"),
}


def _band_block(band):
    """Everything band-specific for one panel. The season's adds are not
    folded in here: they render once under This season, not in every panel."""
    content = BAND_CONTENT[band]
    return {
        "key": band,
        "label": content["label"],
        "picker": BAND_PICKER[band],
        "summary": content["summary"],
        "sources": content["sources"],
        "go": content["go"],
        "where": content["where"],
        "boat": content["boat"],
        "wading": content["wading"],
        "spin": {
            "rig": content["spin"]["rig"],
            "notes": list(content["spin"]["notes"]),
        },
        "fly": {
            "setup": content["fly"]["setup"],
            "notes": list(content["fly"]["notes"]),
        },
        "experiments": experiments_for(band),
        "experiment_titles": experiment_titles_for(band),
        "evidence": evidence_lines(band),
    }


def build_today(cfs, current_time, band, timeline_data=None, forecast_timeline=None):
    """
    The four lines a reader needs before anything else, generated from the
    live band and the flow model: the water, where to go, the rig and bait,
    and the next rise or drop. [(label, text), ...]
    """
    content = BAND_CONTENT[band]
    wading, boating = get_fishing_condition(cfs)
    direction, next_line = next_water_line(cfs, current_time, timeline_data, forecast_timeline)
    verdict = f"{wading[0].upper()}{wading[1:]}, {boating}"
    if direction == "rise" and band == "minimum":
        verdict += " — until the rise gets here"
    return [
        ("Water", f"{content['label']} — {cfs:,} CFS at White Hole ({format_generators(cfs)}). {verdict}."),
        ("Go", content["go"]),
        ("Rig", f"{content['spin']['rig']}; {CORE_BAIT_SHORT}"),
        ("Next", next_line),
    ]


def _gear_by_action(season_content):
    """{action: {kind: [items]}} — the core list plus the season's adds."""
    return {
        action: {
            kind: (list(GEAR_CHECK[kind].get(action, []))
                   + season_content["gear_add"].get(kind, {}).get(action, []))
            for kind, _ in GEAR_KINDS
        }
        for action, _ in GEAR_ACTIONS
    }


def generate_fishing_report(white_hole_cfs, current_time,
                            timeline_data=None, forecast_timeline=None,
                            water_quality=None):
    """
    Build the structured fishing report for current conditions.

    Always returns a full report. Outside the trip windows (March-April,
    September-October) the upcoming window's playbook is shown with
    'in_window' False so the renderer can label it as a preview.
    water_quality is the USGS reading from water_quality.get_water_quality
    (None when unavailable) and renders under the flow line as 'water'.
    """
    season, in_window = get_effective_season(current_time)

    band = get_flow_band(white_hole_cfs)
    season_content = SEASON_CONTENT[season]
    wading, boating = get_fishing_condition(white_hole_cfs)

    # Every band renders as a panel; the live one is shown, the rest sit
    # behind the tap-to-pick strip so the whole ladder is on the page
    bands = [_band_block(key) for _, _, key in FLOW_BANDS]
    current = next(b for b in bands if b["key"] == band)
    spin = current["spin"]
    fly = current["fly"]
    content = BAND_CONTENT[band]
    gear_actions = _gear_by_action(season_content)

    return {
        "in_window": in_window,
        "season": season,
        "season_label": season_content["label"],
        "band": band,
        "band_label": content["label"],
        "cfs": white_hole_cfs,
        "generators": format_generators(white_hole_cfs),
        "wading": wading,
        "boating": boating,
        "summary": content["summary"],
        "sources": content["sources"],
        "season_sources": season_content["sources"],
        "evidence": current["evidence"],
        "today": build_today(white_hole_cfs, current_time, band, timeline_data, forecast_timeline),
        "new_here": NEW_HERE,
        "core": {**CORE_PROGRAM, "evidence": core_evidence_line()},
        "experiments": EXPERIMENTS,
        "parked": PARKED,
        "bands": bands,
        "go": content["go"],
        "where": content["where"],
        "boat": content["boat"],
        "timing": build_timing(white_hole_cfs, current_time,
                               timeline_data, forecast_timeline),
        "spin": spin,
        "fly": fly,
        "water": water_notes(water_quality, season, current_time),
        "season_notes": list(season_content["notes"]),
        # The season's tackle adds, once — spin and fly kept apart
        "season_adds": {"spin": list(season_content["spin_add"]),
                        "fly": list(season_content["fly_add"])},
        "regulations": REGULATIONS,
        # Flat per kind (action order) for callers that only care what is on
        # the list; gear_actions is what the page renders
        "gear_check": {
            kind: [item for action, _ in GEAR_ACTIONS for item in gear_actions[action][kind]]
            for kind, _ in GEAR_KINDS
        },
        "gear_actions": gear_actions,
        "rigging": RIGGING_REFERENCE,
    }


# ---------------------------------------------------------------------------
# HTML rendering (a section spliced into the conditions page, or standalone)
# ---------------------------------------------------------------------------

PROGRAM_BADGES = {
    "browns": ("🟤 browns — trophy, all released", "#7b4a12"),
    "rainbows": ("🌈 rainbows &amp; others — keep 2 under 14 in", "#9d2f4c"),
}


def _items_html(items):
    return "".join(f"<li>{item}</li>" for item in items)


def _map_links_html():
    """Map links for landmarks with pinned coordinates."""
    if not SPOT_COORDS:
        return ""
    links = " · ".join(
        f'<a href="https://www.google.com/maps?q={lat},{lon}" target="_blank" '
        f'style="color: #2b6cb0;">📍 {name}</a>'
        for name, (lat, lon) in SPOT_COORDS.items()
    )
    return f'<p style="margin: 6px 0; font-size: 0.9em;">{links}</p>'


def _today_html(report):
    """The lead: water, where, rig, next — then the gauge lines under it."""
    lines = "".join(
        f'<p style="margin: 4px 0;"><strong>{label}:</strong> {text}</p>'
        for label, text in report["today"])
    water = "".join(
        f'<p style="color: #555; margin: 2px 0; font-size: 0.9em;">{line}</p>'
        for line in report["water"])
    return f'''
        <div style="background-color: #ebf8ff; border-left: 4px solid #2b6cb0; border-radius: 8px; padding: 12px 15px; margin-top: 12px;">
            <h4 style="color: #2c3e50; margin: 0 0 6px;">Today at White Hole</h4>
            {lines}
            <div style="margin-top: 8px;">{water}</div>
        </div>'''


def _rules_line_html():
    """The on-the-water rules, open, one line — the ticket you forget."""
    return (f'<p style="margin: 10px 0 4px; font-size: 0.95em;"><strong>Rules:</strong> {REGULATIONS_HINT} '
            f'— <a href="#wh-before-trip" style="color: #2b6cb0;">full regulations below</a></p>')


def _new_here_html(items):
    """The glossary, collapsed, with the map pins at the end of it."""
    return _collapsible_html(
        "New to this river?",
        f'<ul style="margin: 5px 0 5px 5px;">{_items_html(items)}</ul>{_map_links_html()}',
        "CFS, units, the places, the rig, the baits")


def _season_adds_html(adds):
    """The season's tackle adds, once, spin and fly as separate short lists."""
    parts = []
    for kind, label in (("spin", "🎣 Spin this season"), ("fly", "🪶 Fly this season")):
        if adds.get(kind):
            parts.append(f'<p style="margin: 8px 0 2px;"><strong>{label}</strong></p>'
                         f'<ul style="margin: 0 0 0 5px;">{_items_html(adds[kind])}</ul>')
    return "".join(parts)


def _sources_footnote_html():
    """One collapsed Sources block for the whole report, in place of a grey
    line under every section."""
    items = []
    for label, url in SOURCES.values():
        items.append(f'<a href="{url}" target="_blank" style="color: #2b6cb0;">{label}</a>' if url else label)
    body = f'''<ul style="margin: 5px 0 5px 5px;">{_items_html(items)}</ul>
                <p style="color: #666; font-size: 0.9em; margin: 8px 0 0;">
                    The research brief tags every claim by confidence; the journal's catch rows are what
                    confirm or retire the reported ones, and the Journal lines on this page are those rows.
                    Arrival times come from this page's travel model, not the brief's. Regulations change —
                    verify with AGFC before fishing.</p>'''
    return _collapsible_html("Sources", body, "where this comes from")


def _collapsible_html(title, body, hint=""):
    """One collapsed reference block; hint is the short read beside the title."""
    hint_html = (f' <span style="font-weight: normal; color: #666;">— {hint}</span>'
                 if hint else "")
    return f'''
        <details style="margin-bottom: 8px;">
            <summary style="cursor: pointer; font-weight: bold; padding: 8px 10px; background: #f7fafc; border-radius: 8px;">{title}{hint_html}</summary>
            <div style="padding: 5px 15px;">
                {body}
            </div>
        </details>'''


def _rigging_html(rigging):
    """Collapsible reference blocks — static content, kept out of the way."""
    blocks = []
    for section in rigging:
        intro = (f'<p style="color: #666; margin: 8px 0 4px;">{section["intro"]}</p>'
                 if section["intro"] else "")
        figure = section.get("figure", "")
        blocks.append(_collapsible_html(section["title"], f'''{intro}
                {figure}
                <ul style="margin: 5px 0 5px 5px;">{_items_html(section["items"])}</ul>'''))
    return "".join(blocks)


REGULATIONS_HINT = ("2 rainbows under 14 in, all other trout released, "
                    "single hook with bait, one rod")


def _regulations_html(regulations):
    return _collapsible_html(
        "Regulations",
        f'<ul style="margin: 5px 0 5px 5px;">{_items_html(regulations)}</ul>',
        REGULATIONS_HINT)


def _gear_check_html(gear_actions):
    """The gear check grouped by what each item asks for; spin, fly and boat
    stay separate lists inside every group. The owned-and-packed list is the
    kit as it stands — one tap further in, so the page leads with the jobs."""
    groups = []
    counts = []
    for action, heading in GEAR_ACTIONS:
        kinds = gear_actions[action]
        total = sum(len(items) for items in kinds.values())
        if not total:
            continue
        if action in ("buy", "verify"):
            counts.append(f"{total} to {action}")
        lists = "".join(
            f'''
                <p style="margin: 8px 0 4px;"><strong>{label}</strong></p>
                <ul style="margin: 0 0 0 5px;">{_items_html(kinds[kind])}</ul>'''
            for kind, label in GEAR_KINDS if kinds[kind])
        if action == "pack":
            groups.append(f'''
                <details style="margin: 14px 0 0;">
                    <summary style="cursor: pointer; color: #2c3e50; font-weight: bold; border-bottom: 1px solid #e2e8f0; padding-bottom: 3px;">{heading} ({total}) <span style="font-weight: normal; color: #666;">— the kit as it stands</span></summary>{lists}
                </details>''')
        else:
            groups.append(f'''
                <h5 style="color: #2c3e50; margin: 14px 0 2px; font-size: 1em; border-bottom: 1px solid #e2e8f0; padding-bottom: 3px;">{heading} ({total})</h5>{lists}''')
    return _collapsible_html("Gear check", "".join(groups),
                             " · ".join(["before the trip"] + counts))


def _evidence_html(text):
    return f'<p style="color: #666; font-size: 0.85em; margin: 2px 0 6px;">{text}</p>'


def _core_program_html(core):
    """The core program, expanded: the rig, the bait, the dawn hardware, where."""
    return f'''
        <div style="background-color: #fffaf0; border-left: 4px solid #dd6b20; border-radius: 8px; padding: 12px 15px; margin-top: 18px;">
            <h4 style="color: #2c3e50; margin: 0 0 8px;">{core["title"]}</h4>
            <ul style="margin: 0 0 0 5px;">{_items_html(core["lines"])}</ul>
            {_evidence_html(core["evidence"])}
        </div>'''


def _experiments_html(experiments):
    """Things to try: a compact list — title, program badge, the idea, what to
    bring, and the journal only where it has something to say."""
    items = []
    for x in experiments:
        badge, colour = PROGRAM_BADGES[x["program"]]
        journal = ("" if x["status"].startswith("untested")
                   else f'<span style="display: block; color: #666; font-size: 0.85em;">Journal: {x["status"]}</span>')
        items.append(f'''
            <li style="margin: 0 0 10px;"><strong>{x["title"]}</strong>
                <span style="margin-left: 6px; font-size: 0.8em; color: {colour};">{badge}</span><br>
                <span style="color: #444;">{x["text"]}</span>
                <span style="display: block; color: #666; font-size: 0.9em;">Bring: {x["needs"]}</span>{journal}</li>''')
    return (f'''
        <h4 style="color: #2c3e50; margin: 22px 0 2px;">Things to try — one or two a session</h4>
        <p style="color: #666; margin: 0 0 6px; font-size: 0.9em;">Picked the night before and in the boat before
        launch. An hour, or until the water changes, then back to the core. Most of these are for a brown;
        the fly rod is the exception.</p>
        <ul style="margin: 0 0 0 5px;">{"".join(items)}</ul>''')


def _parked_html(parked):
    items = [f"<strong>{p['what']}</strong> — {p['why']}" for p in parked]
    return _collapsible_html("Tried and parked", f'<ul style="margin: 0 0 0 5px;">{_items_html(items)}</ul>',
                             "what the river ruled out, and why")


PICKER_STYLE = '''<style>
.wh-flowpick { display: flex; gap: 6px; overflow-x: auto; padding: 4px 0 10px; -webkit-overflow-scrolling: touch; }
.wh-flowpick button { flex: 1 0 auto; min-width: 100px; cursor: pointer; font: inherit; background: #fff; border: 1px solid #cbd5e0; border-radius: 8px; padding: 10px 8px; color: #4a5568; text-align: center; line-height: 1.25; }
.wh-flowpick button .t { display: block; font-weight: 700; font-size: 0.95em; }
.wh-flowpick button .c { display: block; font-size: 0.85em; color: #4a5568; margin-top: 3px; }
.wh-flowpick button[aria-pressed="true"] { background: #2b6cb0; border-color: #2b6cb0; color: #fff; }
.wh-flowpick button[aria-pressed="true"] .c { color: rgba(255,255,255,.85); }
.wh-band-panel[hidden] { display: none; }
</style>'''

PICKER_SCRIPT = '''<script>
(function () {
  var buttons = Array.prototype.slice.call(document.querySelectorAll(".wh-flowpick button"));
  var panels = Array.prototype.slice.call(document.querySelectorAll(".wh-band-panel"));
  buttons.forEach(function (b) {
    b.addEventListener("click", function () {
      var key = b.getAttribute("data-band");
      buttons.forEach(function (o) { o.setAttribute("aria-pressed", o === b ? "true" : "false"); });
      panels.forEach(function (p) { p.hidden = p.getAttribute("data-band") !== key; });
    });
  });
})();
</script>'''


def _band_picker_html(report):
    """The tap-to-pick strip: every band, the live one pressed."""
    buttons = "".join(
        f'<button type="button" data-band="{b["key"]}" '
        f'aria-pressed="{"true" if b["key"] == report["band"] else "false"}">'
        f'<span class="t">{b["picker"][0]}</span><span class="c">{b["picker"][1]} CFS</span></button>'
        for b in report["bands"]
    )
    return (f'{PICKER_STYLE}<h4 style="color: #2c3e50; margin: 18px 0 6px;">The playbook by flow</h4>'
            f'<p style="color: #666; margin: 0 0 8px; font-size: 0.9em;">Tap a level. The live one is '
            f'selected; the others are what to do when the water changes — where the fish hold, the boat, the rig.</p>'
            f'<div class="wh-flowpick" role="group" aria-label="Flow band">{buttons}</div>')


def _band_panel_html(b, is_current):
    """One band's where / boat / wading / spin / fly, hidden unless it is the live band."""
    badge = ('<span style="margin-left: 8px; padding: 2px 8px; border-radius: 12px; font-size: 0.75em; '
             'background: #e6fffa; color: #319795;">at White Hole now</span>' if is_current else "")
    fly_notes = (f'<ul style="margin: 0 0 0 5px;">{_items_html(b["fly"]["notes"])}</ul>'
                 if b["fly"]["notes"] else "")
    fits = " · ".join(b["experiment_titles"]) if b["experiment_titles"] else "none at this level"
    evidence = "".join(_evidence_html(line) for line in b["evidence"])
    return f'''
        <!-- band:{b["key"]} -->
        <div class="wh-band-panel" data-band="{b["key"]}"{"" if is_current else " hidden"}>
        <p style="font-size: 1.05em; margin: 12px 0 4px;"><strong>{b["label"]}</strong>{badge}</p>
        <p style="color: #444;">{b["summary"]}</p>
        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Where to go</h4>
        <ul style="margin: 0 0 0 5px;">{_items_html(b["where"])}</ul>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Boat &amp; anchoring</h4>
        <ul style="margin: 0 0 0 5px;">{_items_html(b["boat"])}</ul>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Wading</h4>
        <ul style="margin: 0 0 0 5px;">{_items_html(b["wading"])}</ul>

        <div style="background-color: #f0f7f4; border-radius: 8px; padding: 15px; margin-top: 18px;">
            <h4 style="color: #2c3e50; margin: 0 0 8px;">🎣 Spin Fishing</h4>
            <p style="margin: 4px 0;"><strong>Rig:</strong> {b["spin"]["rig"]}</p>
            <ul style="margin: 0 0 0 5px;">{_items_html(b["spin"]["notes"])}</ul>
        </div>

        <div style="background-color: #f4f2f7; border-radius: 8px; padding: 15px; margin-top: 12px;">
            <h4 style="color: #2c3e50; margin: 0 0 8px;">🪶 Fly Fishing (9 ft 5-wt)</h4>
            <p style="margin: 4px 0;"><strong>Setup:</strong> {b["fly"]["setup"]}</p>
            {fly_notes}
        </div>

        <p style="margin: 10px 0 2px; color: #444;"><strong>Worth trying at this level:</strong> {fits}</p>
        {evidence}
        </div>'''


def render_fishing_report_html(report):
    """
    Render the fishing report as a collapsible section for the conditions
    page — collapsed by default, with the band and flow visible in the
    summary line. Off-window months carry a preview note.
    """
    preview_html = ""
    if not report["in_window"]:
        window = "September–October" if report["season"] == "fall" else "March–April"
        preview_html = f'''
        <p style="background-color: #ebf8ff; color: #2b6cb0; border-radius: 8px; padding: 8px 12px; margin: 10px 0; font-size: 0.9em;">
            Off-season preview — the next trip window is {window}. This is that window's playbook run against the current flow.</p>'''

    timing_html = _items_html(report["timing"])
    season_html = _items_html(report["season_notes"])

    # Order: what the reader needs now (today, the rules, the core, the live
    # band), then what the clock and the season add, then the bets, then the
    # reference blocks — collapsed — and one Sources block for the lot
    return f'''
    <details class="timeline-box">
        <summary style="cursor: default; list-style: none;">
            <h3 style="display: inline;">🎣 Fishing Report — Gaston's to Cranor's Island</h3>
            <span style="color: #666; margin-left: 8px;">{report["band_label"]} · {report["cfs"]:,} CFS</span>
        </summary>
        <p style="color: #666; margin: 12px 0 4px;">{report["season_label"]}</p>
        {preview_html}
        {_today_html(report)}
        {_rules_line_html()}
        {_new_here_html(report["new_here"])}

        {_core_program_html(report["core"])}

        {_band_picker_html(report)}
        {"".join(_band_panel_html(b, b["key"] == report["band"]) for b in report["bands"])}
        <!-- /bands -->

        <h4 style="color: #2c3e50; margin: 22px 0 6px;">Timing</h4>
        <ul style="margin: 0 0 0 5px;">{timing_html}</ul>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">This season</h4>
        <ul style="margin: 0 0 0 5px;">{season_html}</ul>
        {_season_adds_html(report["season_adds"])}

        {_experiments_html(report["experiments"])}

        <h4 id="wh-before-trip" style="color: #2c3e50; margin: 22px 0 6px;">Before the trip (reference)</h4>
        {_regulations_html(report["regulations"])}
        {_gear_check_html(report["gear_actions"])}
        {_parked_html(report["parked"])}

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Rigging &amp; techniques (reference)</h4>
        {_rigging_html(report["rigging"])}
        {_sources_footnote_html()}
        {PICKER_SCRIPT}
    </details>'''


# ---------------------------------------------------------------------------
# Standalone runner: generate the report at will (with overrides for preview)
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate the White Hole fishing report")
    parser.add_argument("--season", choices=["fall", "spring"],
                        help="Preview a trip-window season regardless of today's date")
    parser.add_argument("--cfs", type=int,
                        help="Preview a specific White Hole CFS instead of live data")
    parser.add_argument("--out", default="fishing_report.html",
                        help="Output HTML file (default: fishing_report.html)")
    args = parser.parse_args()

    from datetime import datetime as dt
    from data_fetcher import get_bull_shoals_data, DAM_TIMEZONE
    from water_calculator import calculate_timeline

    current_time = dt.now(DAM_TIMEZONE)
    if args.season:
        month = {"fall": 10, "spring": 4}[args.season]
        current_time = current_time.replace(month=month)

    timeline_data = None
    forecast_timeline = None

    if args.cfs is not None:
        cfs = args.cfs
    else:
        data = get_bull_shoals_data()
        if not data or (len(data) == 1 and data[0].get("error")):
            print("Could not fetch dam data; use --cfs to preview.")
            return
        data.sort(key=lambda x: x["date_time"])
        relevant = None
        for entry in reversed(data):
            flow = get_flow(entry)
            if flow is not None:
                arrival = entry["date_time"] + timedelta(hours=calculate_travel_time(flow))
                if arrival <= current_time:
                    relevant = entry
                    break
        cfs = get_flow(relevant) if relevant else get_flow(data[0])
        timeline_data = calculate_timeline(data, current_time)
        try:
            from forecast_fetcher import get_swpa_forecast
            from water_calculator import calculate_forecast_timeline
            swpa = get_swpa_forecast(current_time)
            if swpa:
                forecast_timeline = calculate_forecast_timeline(swpa, current_time)
        except Exception as e:
            print(f"Warning: no SWPA forecast: {e}")

    water_quality = None
    if args.cfs is None:
        try:
            from water_quality import get_water_quality
            water_quality = get_water_quality(current_time)
        except Exception as e:
            print(f"Warning: no USGS water quality: {e}")

    report = generate_fishing_report(cfs, current_time, timeline_data, forecast_timeline,
                                     water_quality=water_quality)
    section = render_fishing_report_html(report)
    # The standalone page exists to read the report — render it expanded
    section = section.replace('<details class="timeline-box">',
                              '<details open class="timeline-box">', 1)

    page = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>White Hole Fishing Report</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       line-height: 1.6; color: #333; max-width: 900px; margin: 0 auto;
       padding: 20px; background-color: #f7fafc; }}
.timeline-box {{ background-color: white; border-radius: 12px; padding: 20px;
                 margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
h3 {{ margin-top: 0; color: #2c3e50; }}
</style>
</head>
<body>
<h1>White Hole Fishing Report</h1>
<p style="color: #718096;">{current_time.strftime('%A, %B %d, %Y at %I:%M %p')} (Central)</p>
{section}
<p style="font-size: 0.85em; color: #718096; text-align: center;">&copy; {current_time.year} Brian Carroll. All rights reserved.</p>
</body>
</html>'''

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Fishing report saved to {args.out}")
    window_note = "" if report["in_window"] else " (off-season preview)"
    print(f"Band: {report['band_label']} — {report['cfs']:,} CFS "
          f"({report['generators']}){window_note}")


if __name__ == "__main__":
    main()
