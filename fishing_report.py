"""
Fishing report generator for the Gaston's -> Cranor's Island reach of the
White River.

Content is distilled from a Claude Cowork research brief (fishing knowledge:
spots, rigs, baits, presentations, regulations) but ALL flow numbers, travel
times, and arrival ETAs come from this repo's verified model
(water_calculator). Where the brief's flow claims conflicted with the repo
(e.g. its "rise arrives in 90 minutes" surge-front table), the repo wins.

Advice is split by species into two programs, reflecting genuinely different
fisheries (and the regulations):
  - BROWNS — trophy program, all released. Wild fish eating big (5-6 in
    sculpin), holding on structure, crepuscular/nocturnal at low water.
    Heavier leaders: you cannot land this program's target on rainbow line.
  - RAINBOWS & OTHERS — numbers program (keep 2 rainbows under 14 in).
    Stocked invertebrate feeders in open drifts; light line is the game.
    Cutthroat/brook/tiger are incidental and fish like rainbows here.

Gear recommendations are restricted to Brian's owned tackle
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
    calculate_travel_time, get_flow, format_generators, get_fishing_condition,
    recession_window, clock, group_forecast_runs, significant_change
)
from landmarks import GASTONS_MILE, LANDMARK_COORDS, WHITE_HOLE_MILE
import suncalc
from water_quality import describe as describe_water_quality
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


def spot_arrival_times(release_time, cfs):
    """
    When water released at the dam reaches each reach landmark, using the
    repo's travel model scaled by river mile (same method as the chart).
    """
    tt_white_hole = calculate_travel_time(cfs)
    return [
        (name, release_time + timedelta(hours=tt_white_hole * (mile / WHITE_HOLE_MILE)))
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
}


def evidence_line(band, program):
    """'Journal: 3 fish on record (2026-10-06, 2026-10-07) — note' or the honest default."""
    e = EVIDENCE.get((band, program))
    if not e or not e.get("fish"):
        return "Journal: no fish on record yet for this block"
    dates = ", ".join(e.get("dates", []))
    note = f" — {e['note']}" if e.get("note") else ""
    return f"Journal: {e['fish']} fish on record ({dates}){note}"


def sources_html(keys):
    """A grey 'Sources:' line with links where a source has one."""
    parts = []
    for key in keys:
        label, url = SOURCES[key]
        short = label.split(" (")[0].split(" — ")[0]
        parts.append(f'<a href="{url}" target="_blank" style="color: #718096;">{short}</a>'
                     if url else short)
    return (f'<p style="color: #999; font-size: 0.8em; margin: 6px 0 0;">'
            f'Sources: {" · ".join(parts)}</p>')


# ---------------------------------------------------------------------------
# Band content. Spin and fly are separate by design; within each, 'browns'
# and 'rainbows' are separate programs with their own leader guidance.
# Do not merge any of them.
# ---------------------------------------------------------------------------

BAND_CONTENT = {
    "minimum": {
        "label": "Minimum flow (dead low)",
        "sources": ["his_place", "brief", "brian", "agfc_code"],
        "summary": "The river is a giant spring creek. Gravel bars exposed; prop strikes "
                   "are the boat risk and the White Hole ramp can be tricky to launch. "
                   "Wading is wide open. Fish see everything — go light for rainbows, "
                   "go dark (not light) for browns.",
        "where": [
            "The weed-bed edges a short run upstream of the White Hole ramp — sowbug and scud water; trout hold on the edges and pick",
            "The head of the White Hole where the deep water starts at the ramp and runs downstream",
            "The downstream lip (drop-off) of every shoal, where gravel falls into the run",
            "The seam where the main tongue runs past a moss/grass bed — the single most important low-water feature",
            "Undercut banks, root wads, log jams, boulder pockets (brown water)",
            "Cranor's Island — fish both sides, deepest water on the far side; downstream holds low water longest",
        ],
        "boat": [
            "Bank-tie is easy and anchoring is safe at this level",
            "Watch the prop over gravel bars; know the channel before running",
            "Low water lingers longest downstream — run down early, work back upstream as any afternoon water arrives",
        ],
        "spin": {
            "rig": "White River rig both programs: dropper-loop Y, 6–10 in sinker leg with a "
                   "1/8 oz bell (#10), size 10 barrel swivel up top, hook leg long "
                   "at this flow (30–48 in). Each program's 'Leader' below is the single piece "
                   "of line the whole Y is tied from — both legs; your main line stays as spooled.",
            "browns": [
                "Leader: 8 lb fluorocarbon, tied direct — drop the swivel for these fish. You can't land this program's target on 4 lb around wood; fish lower light instead of lighter line",
                "Sculpin on the split-shot rig (not the Y): leader straight to a #1 drop-shot hook, split shot pinched a foot up — presented at the openings around the base of big rocks. THE trophy bait — legal to catch your own (see Bait prep in the rigging reference)",
                "Whole inflated night crawler (hook first, then 4–5 air bubbles) on the White River rig — the long hook leg lets it float and drift",
                "Marabou jig in the 'sculpin' olive/brown, hopped along the deep slots at first and last light",
            ],
            "rainbows": [
                "Leader: 4 lb mono — this is 'the lighter the better' water, and the fish won't test it",
                "PowerBait pink or white floating worm / Mice Tail on the White River rig: floats ~a foot off bottom from a #4 light-wire Aberdeen (keep the hook leg mono — fluoro sinks and kills the lift)",
                "Also on the White River rig: 1½-in crawler or red-worm stubs, peeled shrimp chunks (survive current far better than dough), or the egg-bead variant — orange bead pegged a couple inches above a bare #4 on the hook leg",
                "Float rig — the highest-leverage method: slip float + bobber stop, 1/16 oz panfish head with a 2 in white grub or pink-head crappie jig, 1–3 ft off bottom, fed 40–80 ft downstream and repeated",
                "1/16 oz Beetle Spin or the small Panther Martin along seams and soft edges",
            ],
            "notes": [
                "One rod per angler in the water (regulation) — keep the other program's rod rigged and ready to swap, not fishing",
            ],
        },
        "fly": {
            "setup": "9 ft 5-wt (Recon). Mechanics are shared: tightline the near seam with a 10–12 ft "
                     "thin leader (the owned 20 lb fluoro makes the butt, down to a tippet ring), or swing on a "
                     "shortened 6–7½ ft leader. Species decide the tippet and the fly.",
            "browns": [
                "Tippet: 8 lb fluoro — nymphs and the streamer swing alike",
                "Olive Woolly Bugger #8–10 or black Girdle Bug #8–10 swung at first and last light",
                "Sunday Special #12 tungsten dredged through the deep slots where the big fish hold",
                "Swing the soft hackle through shoal tails and hang it 6–10 seconds at the dangle — a trophy-finding presentation",
            ],
            "rainbows": [
                "Tippet: 4 lb-class fluoro (5X)",
                "Gray sowbug #14–16 point + Zebra/Ruby Midge #16–18 dropper 18 in above, tightlined on the near seam",
                "Short indicator drift, 20–25 ft max, indicator ~1.5× depth; stick-on indicators hold on fine tippet at this flow",
                "Pink San Juan worm or peach/orange egg the moment any water starts moving up",
            ],
        },
    },
    "one_unit": {
        "label": "Around 1 unit (2,000–5,000 CFS)",
        "sources": ["his_place", "brief", "brian"],
        "summary": "The best all-round level. The channel runs cleanly and shoals are passable "
                   "with care. Wading is still possible with caution near edges.",
        "where": [
            "Seams where slow water meets the main current — tie in the slack, cast to the seam",
            "The head of the White Hole and the shoal-tail drop-offs",
            "Both sides of Cranor's Island (deepest water far side)",
            "Behind logs, rocks and boulders; downstream of islands; inside bends",
        ],
        "boat": [
            "Tie from the BOW, bow pointed upstream, slip knot at the cleat, knife within reach",
            "Rotate spots every 45–60 minutes: untie, drop 100 yards, retie",
            "Drifting works well at this level: drift the seams, motor back up, repeat — the driver's on the tiller and sits out, so rotate who drives",
        ],
        "spin": {
            "rig": "White River rig both programs: 1/4 oz bell (#8), hook leg 24–36 in, size 10 swivel. "
                   "'Leader' below = the line the whole Y is tied from.",
            "browns": [
                "Leader: 8 lb fluorocarbon",
                "Countdown jerkbaits (brown-trout, brook-trout patterns) counted down and twitched along the drop-offs",
                "3-in minnow on the split-shot rig, lips-hooked: cast quartering upstream and drift it naturally past structure and drop-offs, feeding line to stretch the drift — drift speed is the whole game",
                "TWO whole night crawlers on the White River rig — threaded on a #4, tails dangling, cast downstream from the tied boat and held",
                "The downstream hang with a spinner: let it swing dead below the boat and hold — the blade works on current alone",
                "Marabou 'sculpin' jig along the bottom of the slots",
            ],
            "rainbows": [
                "Leader: 4 lb mono",
                "Crawler stubs, PowerBait, shrimp on the White River rig through the seams",
                "1/4 oz spoons — Kastmaster chrome or chrome/blue, Little Cleo-class, gold w/ red accents. Gold in bright sun, silver/nickel under cloud",
                "1/4 oz Rooster Tail (flame/chartreuse) or Mepps Aglia #3, quartering upstream, sink first, steady retrieve — the take comes on the swing (Black Fury #3 on dark days)",
                "Float rig in the slower lanes, still effective to ~2 units",
            ],
            "notes": [
                "Never clip a snap swivel to a spinner — run an 18 in leader to a small barrel swivel up the line",
            ],
        },
        "fly": {
            "setup": "Indicator rig with real weight (Airlock/Thingamabobber class), the swing setup, "
                     "or the streamer sink-leader: fast-sinking VersiLeader/polyleader looped on the "
                     "floating line ('insta-sink-tip', ~$15).",
            "browns": [
                "Tippet: 8 lb fluoro on the sink leader; the same spool if nymphing the slots",
                "Olive Woolly Bugger #8–10 / black Girdle Bug #8–10, swung — not stripped — through bank seams and shoal tails",
                "Sunday Special #12 tungsten deep in the slots",
            ],
            "rainbows": [
                "Tippet: 4 lb-class fluoro (5X)",
                "Sowbug/midge pair under the indicator through the seams; lengthen the drift by feeding line",
                "Swing soft hackles, covering water by lengthening 20, 25, 30, 35 ft",
                "Egg and pink San Juan worm near the banks whenever the water is moving up",
            ],
        },
    },
    "two_three_units": {
        "label": "2–3 units (5,000–10,000 CFS)",
        "sources": ["his_place", "brief", "brian"],
        "summary": "Fish move to the banks and flooded grass. No wading. Fish the edges, "
                   "not open water — and the brown-trout window starts opening.",
        "where": [
            "Bank edges and newly flooded grass/gravel that was dry an hour ago — soft current, dislodged food",
            "Inside bends and the shelf-to-channel drop-off",
            "Behind bank structure: logs, root wads, boulders",
            "Foam lines and defined runs in 4–5 ft along the banks",
        ],
        "boat": [
            "Tie high to a tree, not the anchor — a bump in generation reaches this reach fast",
            "Tie from the BOW with slack, re-tend the rope every 20–30 minutes on rising water",
            "Bank-lane drifts are the coverage alternative to tying — trade the driver's rod for water covered",
            "Know what's downstream before committing to a spot; there is no warning siren on this river",
        ],
        "spin": {
            "rig": "White River rig both programs: 3/8 oz bell (#7), hook leg shortened to 18–24 in "
                   "(a long leader lays flat in faster water). 'Leader' below = the line the whole Y is tied from.",
            "browns": [
                "Leader: 8 lb fluorocarbon — the trophy window is open, fish accordingly",
                "Jerkbait prime time (2–4 units): Countdowns and the suspending perch deep jerkbait, twitch-pause along the banks",
                "Keitech Swing Impact FAT 3.3/3.8 on a Flashy Swimmer, or the 4 in white-pearl Tab Tail, swum along the bank edge — white is the named color for White River browns",
                "TWO whole crawlers on the White River rig (#4 or a #1 drop-shot hook), downstream and held in the soft lane",
                "Walk the White River rig down: lift, feed 3–6 ft, re-settle — a 100-yard drift from a fixed boat",
            ],
            "rainbows": [
                "Leader: 4 lb mono",
                "Worms cast near the banks in the first hour of the rise — a documented, predictable pattern, not folklore",
                "White River rig with crawler stubs or shrimp in the soft lanes off the main push",
                "Float rig only in true slack edges at this flow",
                "3/8 oz XPS spoon in the defined runs when the 1/4 oz won't stay down",
            ],
            "notes": [],
        },
        "fly": {
            "setup": "Streamer water: fast-sinking polyleader, weighted #6–10 flies, swung not stripped. "
                     "Nymphing gets hard at 3+ units from a seat.",
            "browns": [
                "Tippet: 8 lb fluoro on the sink leader",
                "Olive Woolly Bugger #8–10 / black Girdle Bug #8–10 swung through the bank seams — this is the program now",
                "Hang every swing at the dangle before recasting",
            ],
            "rainbows": [
                "Tippet: 4 lb-class fluoro (5X)",
                "Pink San Juan worm or egg dead-drifted tight to the flooded grass on the rise",
            ],
        },
    },
    "four_five_units": {
        "label": "3–5 units (10,000–16,500 CFS)",
        "sources": ["his_place", "brief", "brian"],
        "summary": "Boat water — and the big-brown window. Drag chain, not anchor. "
                   "Bank ties need a real eddy. No wading anywhere.",
        "where": [
            "Bank edges with soft water: real eddies, inside bends, current breaks behind structure",
            "The shelf where flooded bank drops to channel — big browns take station on it",
            "Slack pockets downstream of Cranor's Island",
        ],
        "boat": [
            "Do NOT anchor in current — this is how people drown on this river. Drag chain (legal on the White) or tie high in a genuine eddy",
            "Bow upstream, slip knot, knife in reach, re-tend the rope constantly",
            "Drifting the soft bank lane covers the minnow/swimbait water a tied boat can't reach — driver on the tiller, everyone else fishes",
            "Debris starts moving at these flows; keep watch upstream",
        ],
        "spin": {
            "rig": "White River rig: 1/2 oz bell (#6), hook leg 18–24 in. "
                   "A tied boat needs roughly double the drift-chart weight to hold bottom. "
                   "'Leader' below = the line the whole Y is tied from.",
            "browns": [
                "Leader: 8 lb fluorocarbon — guide-class line for exactly this water",
                "3-in minnow on the split-shot rig (stack shot to match the push), lips-hooked, drifted down the bank edge — from a tied boat, work the lane flowing past you with a quartering-upstream cast and fed line; on a boat drift, cover the whole bank. The documented high-water big-trout method",
                "Keitech FAT 3.8/4.3 on the 3/8 oz Flashy Swimmer swum along the bank",
                "Suspending perch jerkbait with long pauses in eddies and seams",
                "Two whole crawlers on the White River rig (#1 drop-shot hook), downstream and held",
            ],
            "rainbows": [
                "Leader: 4 lb mono",
                "Soft-water soaks only: whole crawler or shrimp on the White River rig in eddies and slack lanes off the push",
                "Honestly, this is a browns level — save the numbers game for the drop",
            ],
            "notes": [
                "Calibrate weight: the rig should hold, then slip a few inches when the tip is lifted. Never moves = too heavy; never stops = too light",
            ],
        },
        "fly": {
            "setup": "Honestly limited water for a floating-line 5-wt. If you fish it: the sink-leader "
                     "swing from a boat tied in a true eddy, or park the fly rod until the drop.",
            "browns": [
                "Tippet: 8 lb fluoro on the sink leader",
                "Olive Woolly Bugger / black Girdle Bug #8 swung slow and deep through eddy seams",
            ],
            "rainbows": [
                "Sit this level out, or dredge a worm/egg under a heavily weighted indicator in true slack only",
            ],
        },
    },
    "high": {
        "label": "Heavy generation (16,500+ CFS)",
        "sources": ["his_place", "brief"],
        "summary": "20,000+ CFS class water. Debris moving, no wading anywhere, and this is not "
                   "a small-rental-jon proposition. Fish true slack water only — or wait for the drop.",
        "where": [
            "True slack water only: backwaters, the inside of the biggest eddies, flooded margins out of the current",
            "Seriously consider not launching — watch the SWPA schedule for the cut and plan around the fall-out instead",
        ],
        "boat": [
            "Never anchor. Never tie in current. If afloat, stay in slack water and off the main flow",
            "Re-check the schedule and the ramp before committing — this level with a rental jon is a risk decision, not a tactics decision",
        ],
        "spin": {
            "rig": "White River rig: 1 oz bell (#4) or bank sinker, short leg — "
                   "slack-water soaks only.",
            "browns": [
                "Leader: 8 lb fluorocarbon",
                "4 in white Tab Tail or Keitech 4.3 on its swimbait head (tied direct), pitched along slack margins for a hunting brown",
            ],
            "rainbows": [
                "Leader: 4 lb mono",
                "Whole crawlers or shrimp soaked on the White River rig in true slack edges — that's the whole program",
            ],
            "notes": [
                "The honest play is timing, not tackle: fish the first hours after the cut, when the river drops back through the good bands",
            ],
        },
        "fly": {
            "setup": "The fly rod stays cased at this level.",
            "browns": [],
            "rainbows": [],
        },
    },
}

# What to say about temperature/oxygen when the USGS reading is unavailable
WATER_FALLBACK_NOTES = {
    "fall": "USGS tailwater reading unavailable — fall is the oxygen sag as the lake turns over: land fish fast, keep them wet",
    "spring": "USGS tailwater reading unavailable — expect cold, oxygen-rich water; slow the presentation down",
}

SEASON_CONTENT = {
    "fall": {
        "label": "Fall (September–October): pre-spawn browns",
        "sources": ["brief", "usgs"],
        "notes": [
            "Browns are staging pre-spawn — aggression without redds. They've shifted to eating big: sculpin here run 5–6 in, so don't fish small for them",
            "Stage points: upper ends of holes (trophy browns found in as little as 5 ft), shoal-tail drop-offs, undercut banks and wood",
            "Typical pattern: minimum flow through the morning, generation arriving afternoon/evening — run downstream early, fish the low water, work back up on the rise",
            "Rainbow forage: sowbug/scud > midge > worms-on-the-rise; brown forage: sculpin > crawdad > everything else",
            "Not a dry-fly month — nymphs and streamers; hoppers on warm afternoons are the exception",
        ],
        "spin_add": {
            "browns": [
                "The crawdad presentation earns its fall slot — soft-shell crawdads are a named top natural bait for browns: half a green-pumpkin Senko on the 1/10 oz Ned head (tied direct), or a soft craw plastic if bought (see gear check — not owned)",
            ],
            "rainbows": [
                "Orange scented-garlic PowerBait is the named fall color",
            ],
        },
        "fly_add": {
            "browns": [
                "A #10 hopper on warm afternoons — browns here reportedly favor pink and black/purple hoppers",
            ],
            "rainbows": [
                "Dry-dropper a hopper over the soft bank water on warm afternoons",
            ],
        },
        "gear_add": {
            "spin": [
                "Warm-water season line rule: fluoro hook legs (they sink) — except on floating-bait rigs, which stay mono",
                "Optional: a bag of soft craw/hellgrammite plastics (~$5, not owned) to upgrade the Ned-head crawdad presentation",
            ],
            "fly": [
                "A few #10 hoppers in pink and black/purple (~$6) — the colors browns here reportedly favor",
            ],
        },
    },
    "spring": {
        "label": "Spring (March–April): post-spawn rainbows, front edge of the caddis",
        "sources": ["brief", "agfc_regs"],
        "notes": [
            "Rainbows are post-spawn and feeding normally; stockings are still thin after the 2025 hatchery losses — temper numbers expectations, brown expectations are intact or better",
            "The caddis hatch truly fires at flows around 4,000 CFS or less and works upstream from the lower river — early April usually catches the front edge here, not the peak",
            "The tell: evening swarms of egg-laying caddis; activity picks up after 5 pm",
            "The bite skews later — mid-morning through afternoon, then the evening caddis window. Overcast and rainy days are the best days",
            "BWOs on grey days; shad get pulled through the dam on big water",
            "When Crooked Creek and the Buffalo rise on rain, the Corps cuts generation to protect Newport — rain can hand you surprise low water",
        ],
        "spin_add": {
            "browns": [
                "On big spring water, white swimbaits on their Flashy Swimmer heads (tied direct) imitate shad pulled through the dam — fish them along the banks",
            ],
            "rainbows": [
                "Yellow and orange egg colors are the named March–April producers — run them as the egg-bead variant or Power Eggs on the White River rig",
            ],
        },
        "fly_add": {
            "browns": [
                "Swing the caddis pupa — one of the best trophy-brown presentations of the spring",
            ],
            "rainbows": [
                "Add the Tailwater Soft Hackle in caddis green #14 (the swinging fly) and an Elk Hair Caddis #14 for the after-5-pm window",
            ],
        },
        "gear_add": {
            "spin": [
                "Cool-water season line rule: mono hook legs (they float with the drift)",
            ],
            "fly": [
                "Caddis consumables for the fly box: Tailwater Soft Hackle caddis-green #14 and Elk Hair Caddis #14",
            ],
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

# Core, season-independent packing list, split spin/fly like everything else;
# each season appends its own gear_add items in generate_fishing_report
GEAR_CHECK = {
    "spin": [
        "Rainbow program leader: 4 lb clear/green mono (~$4) — the owned 20/30 lb fluoro is rope in this water",
        "Brown program leader: a spool of 8 lb fluorocarbon (~$8) — 4 lb is a rainbow tool; this one spool runs the whole browns program, spin and fly",
        "2 mm tippet rings (~$6 for 10, not currently owned) for the cartridge version of the rig — plus an evening pre-tying the cartridge wallet (12/24/36 in hook leaders in both line classes)",
        "Verify the bells cover the band ladder — 1/8, 1/4, 3/8, 1/2 and 1 oz (#10/#8/#7/#6/#4), one starting size per flow band",
        "Quick weight changes (the river demands them): finish the rig's sinker leg with a small loop or cheap snap so bells swap without re-tying — skip rubber-core sinkers, they nick light mono and drop off",
        "Optional $3 upgrade: #6–#8 light-wire bait hooks (the #4 Aberdeens work, just oversized for PowerBait)",
        "Hand dip net for sculpin collection (~$8, e.g. Frabill 9x8 baitwell net) — fine mesh well under the 1 in legal max, short handle for one-hand work against the rocks",
        "Worm blower (~$3, not owned) — the inflated-crawler presentations depend on it",
        "Bait is bought fresh in Arkansas, not packed: night crawlers + red worms, PowerBait (pink/white floating worms or Mice Tails; orange-garlic in fall), Power Eggs, cocktail shrimp, corn — plus mini marshmallows for flotation",
        "Respool the AR rod pair (staged at Dad's) before fishing — the inventory's rod rack now carries their specs and a per-rod respool pick (recorded 2026-08-26; the spools stay unknown-test until the respool actually happens): the Presso is the rainbow rod on light mono, and the St. Croix out-tests the 4 lb rainbow cartridges and carries the spinner work — but its ultralight blank can never take the browns main",
        "The browns rod travels from NY: the 2-piece Berkley Cherrywood CWD702MS (7 ft medium, Abu Garcia Black Max 30). Respool DONE 2026-08-28 — it now carries a known mono main (spec in the inventory) that out-tests the 8 lb browns cartridge, so break-offs happen at the cartridge and never the main line. Pack it for any browns or high-generation agenda — it is the only rod aboard that casts the jerkbait class",
    ],
    "fly": [
        "Rainbow program tippet: 4 lb-class fluoro (5X) — VERIFY: fly gear isn't in the inventory yet",
        "Fly box audit (fly gear isn't inventoried yet — verify or buy): gray sowbug #14–16, Sunday Special #12–14 incl. tungsten, Zebra/Ruby Midge #16–18, pink San Juan worm, peach/orange egg, olive Woolly Bugger #8–10, black Girdle Bug #8–10, plus this season's adds",
        "Fast-sinking VersiLeader/polyleader (~$15) — the 'insta-sink-tip' the brown streamer program runs on",
        "Brown program tippet: the same 8 lb fluoro spool as spin — 3–4 ft on the sink leader for the streamer swing",
        "A 2 mm tippet ring finishes the tightline leader butt — same 10-pack as the spin cartridge rings",
    ],
    "boat": [
        "Tie-up rope (50+ ft) and a sharp fixed-blade knife in a sheath — the two non-negotiables",
        "Drag chain for 3+ units — check whether the resort provides one before buying",
        "Headlamp for the after-dark sculpin run",
        "Polarized glasses — the structure-reading tool at low water",
    ],
}


# ---------------------------------------------------------------------------
# Static rigging & techniques reference. Renders as collapsible blocks after
# the gear check — informational, unchanged by flow or season. Spin and fly
# blocks stay separate; boat handling and etiquette are shared seamanship.
# ---------------------------------------------------------------------------

# Inline diagram of the tippet-ring cartridge rig. Literal colours, because
# the report page has no CSS custom properties and no dark mode. The base is
# drawn in ink and the cartridge in orange: that split is the whole point of
# the system, so it carries the one colour distinction in the drawing.
SPIN_RIG_SVG = '''
<svg viewBox="0 0 420 356" role="img" aria-labelledby="rigttl"
     style="width:100%;max-width:430px;height:auto;display:block;margin:10px auto 0;">
  <title id="rigttl">The White River rig built as the tippet-ring cartridge system: main line to a
  barrel swivel, then a permanent 8 lb fluorocarbon base carrying a 12 inch butt and a dropper loop
  that splits into a short sinker leg with a bell sinker and an 8 inch stub ending in a 2 mm tippet
  ring; a swappable pre-tied cartridge clinches to that ring and runs down to the hook, where the
  bait rides up off the bottom</title>
  <g fill="none" stroke="#2d3748" stroke-width="1.6" stroke-linecap="round">
    <path d="M100 10 L100 44"/>
    <ellipse cx="100" cy="52" rx="5" ry="8" stroke-width="1.4"/>
    <path d="M100 60 L100 88"/>
    <circle cx="100" cy="95" r="6" stroke-width="1.4"/>
    <path d="M97 101 L83 246"/>
    <path d="M104 101 C 128 126, 152 148, 176 163"/>
  </g>
  <path d="M83 246 l-11 30 h22 z" fill="#4a5568" stroke="none"/>
  <g fill="none" stroke="#2d3748">
    <circle cx="182" cy="168" r="6" stroke-width="1.5"/>
    <circle cx="182" cy="168" r="2.6" stroke-width="1"/>
  </g>
  <path d="M187 172 C 228 200, 275 226, 320 246"
        fill="none" stroke="#c05621" stroke-width="1.9" stroke-linecap="round"/>
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
    <text x="114" y="28">main line, as spooled</text>
    <text x="114" y="56">size 10 barrel swivel</text>
    <text x="114" y="80" fill="#2b6cb0">12 in butt</text>
    <text x="114" y="99">dropper loop</text>
    <text x="2" y="180" fill="#2b6cb0">6–10 in</text>
    <text x="2" y="232">bell #10–#4</text>
    <text x="142" y="126" fill="#2b6cb0">8 in stub</text>
    <text x="196" y="160">2 mm tippet ring</text>
    <text x="112" y="252" fill="#c05621">cartridge  12 / 24 / 36 in</text>
    <text x="112" y="267">= hook leg  20 / 32 / 44 in</text>
    <text x="418" y="266" text-anchor="end">bait rides up</text>
  </g>
  <g font-family="SFMono-Regular, Menlo, Consolas, monospace" font-size="10" fill="#718096">
    <path d="M8 314 l22 0" fill="none" stroke="#2d3748" stroke-width="1.6" stroke-linecap="round"/>
    <text x="38" y="318">permanent base · 8 lb fluoro · stays on the rod</text>
    <path d="M8 338 l22 0" fill="none" stroke="#c05621" stroke-width="1.9" stroke-linecap="round"/>
    <text x="38" y="342">cartridge · clinched on · 4 lb rainbows, 8 lb browns</text>
  </g>
</svg>
<p style="font-size: 0.82em; color: #718096; text-align: center; margin: 8px auto 4px; max-width: 430px; line-height: 1.5;">
  The base never comes off the rod. A hook snag costs the cartridge and never the base, the ring or
  the bell, which is why a 4&nbsp;lb rainbow cartridge hangs under an 8&nbsp;lb base. The base sits
  more than 20&nbsp;in above the bait, so the fish only ever inspects cartridge-class line.
</p>'''


RIGGING_REFERENCE = [
    {
        "title": "Building the White River rig (spin)",
        "intro": "Not a Carolina rig and not a true three-way — one continuous piece of "
                 "leader split into a short weight leg and a long hook leg (the \"Y\").",
        "figure": SPIN_RIG_SVG,
        "items": [
            "Start with 40–50 in of leader (4 lb for the rainbow program, 8 lb for browns) — cutting one side of the loop burns roughly twice the finished tag length, so a 30 in strand comes up short",
            "Tie a dropper loop 6–10 in from one end and cut one side of the loop — that's the Y. The standing line runs on through the knot uncut; only the cut tag is a branch",
            "Short end above the knot (6–10 in) goes to the swivel, the long end below it (18–36 in) is the hook leg, and the cut tag (6–10 in) carries the bell. Keep that order — a fish then pulls against unbroken line through the junction, and the tag, which is the weakest part of a dropper loop, only ever holds lead",
            "Top end to the main line with a size 10–12 barrel swivel — or tie direct for bigger, spookier fish",
            "Tune it: faster water → shorten the hook leg to 18–24 in (a long leader lays flat); minimum flow → lengthen to 30–48 in; snaggy bottom → attach the bell to the tag with a rubber band so it breaks away and costs a sinker instead of the rig",
            "The tippet-ring upgrade — fixes the one-piece rig's can't-lengthen problem: tie the rig as a permanent 8 lb fluoro base (swivel, ~12 in butt, dropper loop + sinker leg, then an 8 in stub ending in a 2 mm tippet ring) and clinch pre-tied hook leaders ('cartridges') to the ring. Cartridge ladder: 12, 24 or 36 in for hook legs of 20, 32 or 44 in — 44 at minimum flow, 32 around 1 unit, 20 from 2 units up. Trim to tune; swap up when the water drops",
            "On the ring rig, the cartridge picks the species program — each program's 'Leader' spec applies to the cartridge: 4 lb mono = rainbows, 8 lb fluoro = browns. The 8 lb base sits 20+ in above the bait, so the fish inspects only cartridge-class line, and a 4 lb cartridge under the 8 lb base is automatically sacrificial: hook snags cost the cartridge, never the base, ring or bell",
            "Pre-tie the cartridge wallet at home, wound on a foam disc: a few of each length in each line class, plus a couple of #1 sculpin leaders. Improved clinch at the ring on both sides — a Palomar won't thread a 2 mm ring with a 3 ft leader",
            "Bell sinker numbers (local shorthand): #10 = 1/8 oz · #9 = 3/16 · #8 = 1/4 · #7 = 3/8 · #6 = 1/2 · #5 = 3/4 · #4 = 1 oz. Starting size by flow band: minimum #10 · 1 unit #8 · 2–3 units #7 · 3–5 units #6 · heavy #4 — then adjust one size by the calibration rule",
            "Hook by bait: PowerBait #6–#8 · whole crawler #2–#4 Aberdeen · red worm #4 · sculpin/shrimp/crawdad #1–#2 · minnow #6 through both lips · corn or single egg #10–#12",
            "The livebait drift exception (sculpin, minnows) — skip the Y entirely: leader straight to the hook, split shot pinched ~a foot up (stack shot as the current demands). A pinched shot rides over what a hanging bell snags in, and the bait swims naturally",
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
            "Tie in the slack or eddy and cast to the seam where slow meets fast — put the boat by the fast water, fish the slower water. Rotate every 45–60 minutes: untie, drop 100 yards, retie",
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

    # The day's low-light windows — the browns program's hours
    light = light_windows_for(current_time)
    if light:
        timing.append(
            f"Low light today: dawn {clock(light['dawn'][0])}–{clock(light['dawn'][1])} "
            f"(sunrise {clock(light['sunrise'])}) · dusk {clock(light['dusk'][0])}–"
            f"{clock(light['dusk'][1])} (sunset {clock(light['sunset'])}) — the browns "
            f"program's hours; at low water fish the dusk window into dark"
        )

    # Water already in transit (actual readings): the first incoming plug
    # that changes the band, not merely the nearest one — a same-level
    # reading often sits ahead of the real rise or drop
    if timeline_data:
        incoming = [item for item in timeline_data if item["status"] == "incoming"]
        for item in incoming:
            if item["cfs"] - current_cfs >= 2000:
                timing.append(
                    f"RISE EN ROUTE: {item['cfs']:,} CFS "
                    f"({format_generators(item['cfs'])}) reaches White Hole "
                    f"~{clock(item['arrival_time'], current_time)} — "
                    f"cast worms near the banks in the first hour, then fish the "
                    f"{BAND_CONTENT[get_flow_band(item['cfs'])]['label']} program"
                )
                break
            if current_cfs - item["cfs"] >= 2000:
                start = item.get("recession_start")
                down = clock(item["arrival_time"], current_time)
                if start is not None and start <= current_time:
                    when = f"is dropping now and fully down ~{down}"
                elif start is not None:
                    when = f"starts dropping ~{clock(start, current_time)} and is fully down ~{down}"
                else:
                    when = f"reaches White Hole ~{down}"
                timing.append(
                    f"DROP EN ROUTE: the cut to {item['cfs']:,} CFS {when} — "
                    f"the first hour of the drop is a prime bite window; it's a "
                    f"recession, not a step, so the window is the whole span"
                )
                break

    # Next scheduled change (SWPA)
    change = _find_flow_change(current_cfs, forecast_timeline)
    if change:
        direction, entry, from_cfs = change
        when = clock(entry["scheduled_time"], current_time, minutes=False)
        if direction == "rise":
            etas = spot_arrival_times(entry["scheduled_time"], entry["cfs"])
            eta_str = " · ".join(
                f"{name} ~{clock(eta, current_time)}" for name, eta in etas
            )
            timing.append(
                f"SCHEDULED RISE to {entry['cfs']:,} CFS "
                f"({format_generators(entry['cfs'])}) at {when}: {eta_str}. "
                f"Downstream water stays low longer — be below the front and fish it up"
            )
        else:
            windows = spot_recession_windows(entry["scheduled_time"], from_cfs, entry["cfs"])
            eta_str = " · ".join(
                _window_str(name, start, end, current_time) for name, start, end in windows
            )
            timing.append(
                f"SCHEDULED DROP to {entry['cfs']:,} CFS at {when}: "
                f"falling water {eta_str} (start of the drop–fully down). "
                f"Fish the first hour of the drop at each spot; upstream falls first"
            )

    timing.extend(schedule_outline(forecast_timeline, current_time))

    return timing


def schedule_outline(forecast_timeline, current_time):
    """
    One bullet per scheduled day: every significant change at White Hole in
    order, the peak marked — the night-before read of tomorrow, and the rest
    of today beyond the first change the SCHEDULED RISE/DROP bullet names.
    """
    if not forecast_timeline:
        return []
    bullets = []
    by_day = {}
    for run in group_forecast_runs(forecast_timeline):
        by_day.setdefault(run["start_time"].date(), []).append(run)
    for day, day_runs in sorted(by_day.items()):
        # The day's high point — unmarked when it is simply where the day
        # starts (a day that only falls from the current level has no peak)
        peak = max(day_runs, key=lambda r: r["cfs"])
        if peak is day_runs[0]:
            peak = None
        steps = []
        prev = None
        for run in day_runs:
            if prev is not None and significant_change(prev, run["cfs"]) is None and run is not peak:
                prev = run["cfs"]
                continue
            when = (f"falling ~{clock(run['recession_start'], current_time)}"
                    if run.get("change") == "falling" and run.get("recession_start")
                    else f"by ~{clock(run['arrival_time'], current_time)}")
            tag = " (peak)" if run is peak else ""
            steps.append(f"{run['cfs']:,} {when}{tag}")
            prev = run["cfs"]
        if day == current_time.date():
            label = "Rest of today at White Hole"
        elif day == current_time.date() + timedelta(days=1):
            label = f"Tomorrow ({day.strftime('%a')}) at White Hole"
        else:
            label = f"{day.strftime('%a')} at White Hole"
        bullets.append(f"{label}: " + " · ".join(steps))
    return bullets


def water_notes(water_quality, season, current_time=None):
    """
    Measured temperature/oxygen lines for the season notes (from the USGS
    gauges), or the season's generic fallback when no reading is available.
    """
    temp_line, do_line = describe_water_quality(water_quality)
    if not temp_line and not do_line:
        return [WATER_FALLBACK_NOTES[season]]
    source = water_quality["site_label"]
    when = clock(water_quality["observed"], current_time) if current_time else ""
    notes = [line for line in (temp_line, do_line) if line]
    notes[-1] += f" ({source}, {when})" if when else f" ({source})"
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


def _band_block(band, season_content):
    """Everything band-specific for one panel: content plus the season's adds."""
    content = BAND_CONTENT[band]
    return {
        "key": band,
        "label": content["label"],
        "picker": BAND_PICKER[band],
        "summary": content["summary"],
        "sources": content["sources"],
        "where": content["where"],
        "boat": content["boat"],
        "spin": {
            "rig": content["spin"]["rig"],
            "browns": list(content["spin"]["browns"]) + season_content["spin_add"]["browns"],
            "rainbows": list(content["spin"]["rainbows"]) + season_content["spin_add"]["rainbows"],
            "notes": list(content["spin"].get("notes", [])),
        },
        "fly": {
            "setup": content["fly"]["setup"],
            "browns": (list(content["fly"]["browns"]) + season_content["fly_add"]["browns"]
                       if content["fly"]["browns"] else []),
            "rainbows": (list(content["fly"]["rainbows"]) + season_content["fly_add"]["rainbows"]
                         if content["fly"]["rainbows"] else []),
        },
        "evidence": {program: evidence_line(band, program) for program in ("browns", "rainbows")},
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
    (None when unavailable) and leads the season notes.
    """
    season, in_window = get_effective_season(current_time)

    band = get_flow_band(white_hole_cfs)
    season_content = SEASON_CONTENT[season]
    wading, boating = get_fishing_condition(white_hole_cfs)

    # Every band renders as a panel; the live one is shown, the rest sit
    # behind the tap-to-pick strip so the whole ladder is on the page
    bands = [_band_block(key, season_content) for _, _, key in FLOW_BANDS]
    current = next(b for b in bands if b["key"] == band)
    spin = current["spin"]
    fly = current["fly"]
    content = BAND_CONTENT[band]

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
        "bands": bands,
        "where": content["where"],
        "boat": content["boat"],
        "timing": build_timing(white_hole_cfs, current_time,
                               timeline_data, forecast_timeline),
        "spin": spin,
        "fly": fly,
        "season_notes": water_notes(water_quality, season, current_time) + season_content["notes"],
        "regulations": REGULATIONS,
        "gear_check": {
            "spin": GEAR_CHECK["spin"] + season_content["gear_add"]["spin"],
            "fly": GEAR_CHECK["fly"] + season_content["gear_add"]["fly"],
            "boat": list(GEAR_CHECK["boat"]),
        },
        "rigging": RIGGING_REFERENCE,
    }


# ---------------------------------------------------------------------------
# HTML rendering (a section spliced into the conditions page, or standalone)
# ---------------------------------------------------------------------------

BROWNS_HEADER = "Browns — trophy program (all released)"
RAINBOWS_HEADER = "Rainbows &amp; others — numbers program (keep 2 under 14 in)"


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


def _rigging_html(rigging):
    """Collapsible reference blocks — static content, kept out of the way."""
    blocks = []
    for section in rigging:
        intro = (f'<p style="color: #666; margin: 8px 0 4px;">{section["intro"]}</p>'
                 if section["intro"] else "")
        figure = section.get("figure", "")
        blocks.append(f'''
        <details style="margin-bottom: 8px;">
            <summary style="cursor: pointer; font-weight: bold; padding: 8px 10px; background: #f7fafc; border-radius: 8px;">{section["title"]}</summary>
            <div style="padding: 5px 15px;">
                {intro}
                {figure}
                <ul style="margin: 5px 0 5px 5px;">{_items_html(section["items"])}</ul>
            </div>
        </details>''')
    return "".join(blocks)


def _evidence_html(text):
    return f'<p style="color: #999; font-size: 0.8em; margin: 2px 0 6px;">{text}</p>'


def _species_block_html(browns, rainbows, evidence=None):
    """Render the two species programs; either may be empty."""
    evidence = evidence or {}
    html = ""
    if browns:
        html += f'''
            <p style="margin: 10px 0 4px;"><strong style="color: #7b4a12;">🟤 {BROWNS_HEADER}</strong></p>
            <ul style="margin: 0 0 0 5px;">{_items_html(browns)}</ul>
            {_evidence_html(evidence["browns"]) if evidence.get("browns") else ""}'''
    if rainbows:
        html += f'''
            <p style="margin: 10px 0 4px;"><strong style="color: #9d2f4c;">🌈 {RAINBOWS_HEADER}</strong></p>
            <ul style="margin: 0 0 0 5px;">{_items_html(rainbows)}</ul>
            {_evidence_html(evidence["rainbows"]) if evidence.get("rainbows") else ""}'''
    return html


PICKER_STYLE = '''<style>
.wh-flowpick { display: flex; gap: 6px; overflow-x: auto; padding: 4px 0 10px; -webkit-overflow-scrolling: touch; }
.wh-flowpick button { flex: 1 0 auto; min-width: 88px; cursor: pointer; font: inherit; background: #fff; border: 1px solid #cbd5e0; border-radius: 8px; padding: 8px; color: #4a5568; text-align: center; line-height: 1.2; }
.wh-flowpick button .t { display: block; font-weight: 700; font-size: 0.85em; }
.wh-flowpick button .c { display: block; font-size: 0.7em; color: #718096; margin-top: 3px; }
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
            f'selected; the others are what to do when the water changes.</p>'
            f'<div class="wh-flowpick" role="group" aria-label="Flow band">{buttons}</div>')


def _band_panel_html(b, is_current):
    """One band's where / boat / spin / fly, hidden unless it is the live band."""
    spin_notes_html = ""
    if b["spin"]["notes"]:
        spin_notes_html = f'''
            <p style="margin: 10px 0 4px;"><strong>Notes:</strong></p>
            <ul style="margin: 0 0 0 5px;">{_items_html(b["spin"]["notes"])}</ul>'''
    badge = ('<span style="margin-left: 8px; padding: 2px 8px; border-radius: 12px; font-size: 0.75em; '
             'background: #e6fffa; color: #319795;">at White Hole now</span>' if is_current else "")
    return f'''
        <!-- band:{b["key"]} -->
        <div class="wh-band-panel" data-band="{b["key"]}"{"" if is_current else " hidden"}>
        <p style="font-size: 1.05em; margin: 12px 0 4px;"><strong>{b["label"]}</strong>{badge}</p>
        <p style="color: #444;">{b["summary"]}</p>
        {sources_html(b["sources"])}
        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Where to go</h4>
        <ul style="margin: 0 0 0 5px;">{_items_html(b["where"])}</ul>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Boat &amp; anchoring</h4>
        <ul style="margin: 0 0 0 5px;">{_items_html(b["boat"])}</ul>

        <div style="background-color: #f0f7f4; border-radius: 8px; padding: 15px; margin-top: 18px;">
            <h4 style="color: #2c3e50; margin: 0 0 8px;">🎣 Spin Fishing</h4>
            <p style="margin: 4px 0;"><strong>Rig:</strong> {b["spin"]["rig"]}</p>
            {_species_block_html(b["spin"]["browns"], b["spin"]["rainbows"], b["evidence"])}
            {spin_notes_html}
        </div>

        <div style="background-color: #f4f2f7; border-radius: 8px; padding: 15px; margin-top: 12px;">
            <h4 style="color: #2c3e50; margin: 0 0 8px;">🪶 Fly Fishing (9 ft 5-wt)</h4>
            <p style="margin: 4px 0;"><strong>Setup:</strong> {b["fly"]["setup"]}</p>
            {_species_block_html(b["fly"]["browns"], b["fly"]["rainbows"], b["evidence"])}
        </div>
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
    regs_html = _items_html(report["regulations"])

    return f'''
    <details class="timeline-box">
        <summary style="cursor: default; list-style: none;">
            <h3 style="display: inline;">🎣 Fishing Report — Gaston's to Cranor's Island</h3>
            <span style="color: #666; margin-left: 8px;">{report["band_label"]} · {report["cfs"]:,} CFS</span>
        </summary>
        <p style="color: #666; margin: 12px 0 4px;">{report["season_label"]}</p>
        {preview_html}
        <p style="font-size: 1.1em; margin: 10px 0;"><strong>{report["band_label"]}</strong>
            — {report["cfs"]:,} CFS at White Hole ({report["generators"]})</p>
        {_map_links_html()}

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Timing</h4>
        <ul style="margin: 0 0 0 5px;">{timing_html}</ul>

        {_band_picker_html(report)}
        {"".join(_band_panel_html(b, b["key"] == report["band"]) for b in report["bands"])}

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Season notes</h4>
        <ul style="margin: 0 0 0 5px;">{season_html}</ul>
        {sources_html(report["season_sources"])}

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Regulations</h4>
        <ul style="margin: 0 0 0 5px;">{regs_html}</ul>
        {sources_html(["agfc_regs", "agfc_code"])}

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Gear check</h4>
        <p style="margin: 6px 0 4px;"><strong>🎣 Spin gear:</strong></p>
        <ul style="margin: 0 0 0 5px;">{_items_html(report["gear_check"]["spin"])}</ul>
        <p style="margin: 10px 0 4px;"><strong>🪶 Fly gear:</strong></p>
        <ul style="margin: 0 0 0 5px;">{_items_html(report["gear_check"]["fly"])}</ul>
        <p style="margin: 10px 0 4px;"><strong>🛶 Boat &amp; trip gear:</strong></p>
        <ul style="margin: 0 0 0 5px;">{_items_html(report["gear_check"]["boat"])}</ul>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Rigging &amp; techniques (reference)</h4>
        {_rigging_html(report["rigging"])}
        {PICKER_SCRIPT}

        <p style="color: #999; font-size: 0.8em; margin-top: 15px;">
            Each block names its sources above. The research brief tags every claim by
            confidence; the journal's catch rows are what confirm or retire the reported
            ones. Arrival times come from this page's travel model, not the brief's.
            Regulations change — verify with AGFC before fishing.
        </p>
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
