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

The full report renders only during trip windows (March-April and
September-October); other months get a placeholder. Spin and fly sections
are kept strictly separate.

Standalone use:
    uv run python fishing_report.py [--season fall|spring] [--cfs N]
"""
from datetime import datetime, timedelta

from water_calculator import (
    calculate_travel_time, get_flow, format_generators, get_fishing_condition
)
from landmarks import GASTONS_MILE, LANDMARK_COORDS, WHITE_HOLE_MILE

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


# ---------------------------------------------------------------------------
# Band content. Spin and fly are separate by design; within each, 'browns'
# and 'rainbows' are separate programs with their own leader guidance.
# Do not merge any of them.
# ---------------------------------------------------------------------------

BAND_CONTENT = {
    "minimum": {
        "label": "Minimum flow (dead low)",
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
                "Sculpin on the split-shot rig (not the Y): leader straight to a #1 drop-shot hook or large snelled Octopus, split shot pinched a foot up — presented at the openings around the base of big rocks. THE trophy bait (catch your own flipping rocks; verify AGFC baitfish rules)",
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
            "Anchoring still reasonable at this level — but rig it to slip free",
        ],
        "spin": {
            "rig": "White River rig both programs: 1/4 oz bell (#8), hook leg 24–36 in, size 10 swivel. "
                   "'Leader' below = the line the whole Y is tied from.",
            "browns": [
                "Leader: 8 lb fluorocarbon",
                "Countdown jerkbaits (brown-trout, brook-trout patterns) counted down and twitched along the drop-offs",
                "3-in minnow on the split-shot rig, lips-hooked, drifted naturally behind structure and along drop-offs — drift speed is the whole game",
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
        "summary": "Fish move to the banks and flooded grass. No wading. Fish the edges, "
                   "not open water — and the brown-trout window starts opening.",
        "where": [
            "Bank edges and newly flooded grass/gravel that was dry an hour ago — soft current, dislodged food",
            "Inside bends and the shelf-to-channel drop-off",
            "Behind bank structure: logs, root wads, boulders",
            "Foam lines and defined runs in 4–5 ft along the banks",
        ],
        "boat": [
            "Anchor only with a plan — a bump in generation reaches this reach fast; tie high to a tree instead",
            "Tie from the BOW with slack, re-tend the rope every 20–30 minutes on rising water",
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
                "Fish the soft water the boat itself creates when nothing else is reachable",
            ],
        },
    },
    "four_five_units": {
        "label": "3–5 units (10,000–16,500 CFS)",
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
            "Debris starts moving at these flows; keep watch upstream",
        ],
        "spin": {
            "rig": "White River rig: 1/2 oz bell (#6), hook leg 18–24 in. "
                   "A tied boat needs roughly double the drift-chart weight to hold bottom. "
                   "'Leader' below = the line the whole Y is tied from.",
            "browns": [
                "Leader: 8 lb fluorocarbon — guide-class line for exactly this water",
                "3-in minnow on the split-shot rig (stack shot to match the push), lips-hooked, drifted along the bank edge — the documented high-water big-trout method",
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
                "The first hour of falling water is the best fly window of the day — be rigged for it",
            ],
            "rainbows": [
                "Sit this level out, or dredge a worm/egg under a heavily weighted indicator in true slack only",
            ],
        },
    },
    "high": {
        "label": "Heavy generation (16,500+ CFS)",
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

SEASON_CONTENT = {
    "fall": {
        "label": "Fall (September–October): pre-spawn browns",
        "notes": [
            "Browns are staging pre-spawn — aggression without redds. They've shifted to eating big: sculpin here run 5–6 in, so don't fish small for them",
            "Stage points: upper ends of holes (trophy browns found in as little as 5 ft), shoal-tail drop-offs, undercut banks and wood",
            "Water is at its annual warmest (~53–56°F) — the highest-metabolism window; fish will chase",
            "Dissolved oxygen is at its seasonal low: land fish fast, keep them wet",
            "Typical pattern: minimum flow through the morning, generation arriving afternoon/evening — run downstream early, fish the low water, work back up on the rise",
            "Rainbow forage: sowbug/scud > midge > worms-on-the-rise; brown forage: sculpin > crawdad > everything else",
            "Not a dry-fly month — nymphs and streamers; hoppers on warm afternoons are the exception",
        ],
        "spin_add": {
            "browns": [
                "Soft craw/hellgrammite plastic on the Ned head (tied direct) — the crawdad presentation earns its fall slot; soft-shell crawdads are a named top natural bait for browns",
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
            ],
            "fly": [
                "A few #10 hoppers in pink and black/purple (~$6) — the colors browns here reportedly favor",
            ],
        },
    },
    "spring": {
        "label": "Spring (March–April): post-spawn rainbows, front edge of the caddis",
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
    "Verify current limits by phone before the trip: AGFC 833-345-0325 (this fishery is under active emergency management)",
]

# Core, season-independent packing list, split spin/fly like everything else;
# each season appends its own gear_add items in generate_fishing_report
GEAR_CHECK = {
    "spin": [
        "Rainbow program leader: 4 lb clear/green mono (~$4) — the owned 20/30 lb fluoro is rope in this water",
        "Brown program leader: a spool of 8 lb fluorocarbon (~$8) — 4 lb is a rainbow tool; this one spool runs the whole browns program, spin and fly",
        "Verify the bells cover the band ladder — 1/8, 1/4, 3/8, 1/2 and 1 oz (#10/#8/#7/#6/#4), one starting size per flow band",
        "Quick weight changes (the river demands them): finish the rig's sinker leg with a small loop or cheap snap so bells swap without re-tying — skip rubber-core sinkers, they nick light mono and drop off",
        "Optional $3 upgrade: #6–#8 light-wire bait hooks (the #4 Aberdeens work, just oversized for PowerBait)",
    ],
    "fly": [
        "Rainbow program tippet: 4 lb-class fluoro (5X), likely already owned",
        "Fast-sinking VersiLeader/polyleader (~$15) — the 'insta-sink-tip' the brown streamer program runs on",
        "Brown program tippet: the same 8 lb fluoro spool as spin — 3–4 ft on the sink leader for the streamer swing",
    ],
}


# ---------------------------------------------------------------------------
# Static rigging & techniques reference. Renders as collapsible blocks after
# the gear check — informational, unchanged by flow or season. Spin and fly
# blocks stay separate; boat handling and etiquette are shared seamanship.
# ---------------------------------------------------------------------------

RIGGING_REFERENCE = [
    {
        "title": "Building the White River rig (spin)",
        "intro": "Not a Carolina rig and not a true three-way — one continuous piece of "
                 "leader split into a short weight leg and a long hook leg (the \"Y\").",
        "items": [
            "Start with 30–40 in of leader (4 lb for the rainbow program, 8 lb for browns)",
            "Tie a dropper loop 6–10 in from one end and cut one side of the loop — that's the Y",
            "Short leg (6–10 in): bell sinker. Long leg (18–36 in): hook",
            "Top end to the main line with a size 10–12 barrel swivel — or tie direct for bigger, spookier fish",
            "Tune it: faster water → shorten the hook leg to 18–24 in (a long leader lays flat); minimum flow → lengthen to 30–48 in; snaggy bottom → tie the sinker leg in lighter line so it breaks away, or attach the bell with a rubber band",
            "Bell sinker numbers (local shorthand): #10 = 1/8 oz · #9 = 3/16 · #8 = 1/4 · #7 = 3/8 · #6 = 1/2 · #5 = 3/4 · #4 = 1 oz. Starting size by flow band: minimum #10 · 1 unit #8 · 2–3 units #7 · 3–5 units #6 · heavy #4 — then adjust one size by the calibration rule",
            "Hook by bait: PowerBait #6–#8 · whole crawler #2–#4 Aberdeen · red worm #4 · sculpin/shrimp/crawdad #1–#2 · minnow #6 through both lips · corn or single egg #10–#12",
            "The livebait drift exception (sculpin, minnows) — skip the Y entirely: leader straight to the hook, split shot pinched ~a foot up (stack shot as the current demands). A pinched shot rides over what a hanging bell snags in, and the bait swims naturally",
        ],
    },
    {
        "title": "Bait prep (spin)",
        "intro": "",
        "items": [
            "Inflating a crawler: hook it FIRST, then inject 4–5 air bubbles spaced along a large crawler; use the smallest hook that will hold it",
            "Mice Tail / floating worm: run the hook through the center of the worm and out ~½ in behind the head so it floats horizontally — head-hooked it hangs vertically, which is wrong",
            "No floating bait? Thread a mini marshmallow up the hook shank — the other documented flotation method on this river",
            "Keep mono on the hook leg of any floating rig — fluoro sinks and kills the lift",
            "Calibrate weight on the water: cast quartering upstream and let it settle. Right weight holds, then slips a few inches and re-grabs when you lift the tip. Never moves = too heavy; never stops = too light",
        ],
    },
    {
        "title": "Tying the boat",
        "intro": "Most drownings on this river involve an anchor thrown during generation. "
                 "The tie-up is the safe method — done right.",
        "items": [
            "Tie from the BOW, bow pointed upstream — a stern- or side-tied boat in current gets rolled or swamped",
            "Slip knot / quick-release at the cleat, and keep a sharp fixed-blade knife in a sheath within arm's reach",
            "Tie HIGH to a tree and leave slack; re-tend the rope every 20–30 minutes once water is coming — a tight, low rope on a rising river pulls a gunwale under",
            "Tie in the slack or eddy and cast to the seam where slow meets fast — put the boat by the fast water, fish the slower water",
            "Rotate every 45–60 minutes: untie, drop 100 yards, retie",
            "Drag chains are legal on the White (banned on the Norfork) — the high-water alternative to anchoring",
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
            "Two anglers, two methods: the other rod fishes straight downstream from the stern in the boat's own lane; the fly angler sits forward, casting up-and-across to the OPPOSITE side. Different quadrants — the lines never cross",
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


def _find_flow_change(current_cfs, forecast_timeline):
    """
    Find the first scheduled SWPA hour that meaningfully changes the flow
    (>= 2000 CFS difference from what's at White Hole now).

    Returns (direction, entry) where direction is 'rise' or 'drop', or None.
    """
    if not forecast_timeline:
        return None
    for entry in forecast_timeline:
        if entry["cfs"] - current_cfs >= 2000:
            return ("rise", entry)
        if current_cfs - entry["cfs"] >= 2000:
            return ("drop", entry)
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

    # Water already in transit (actual readings)
    if timeline_data:
        incoming = [item for item in timeline_data if item["status"] == "incoming"]
        if incoming:
            nearest = incoming[0]
            if nearest["cfs"] - current_cfs >= 2000:
                timing.append(
                    f"RISE EN ROUTE: {nearest['cfs']:,} CFS "
                    f"({format_generators(nearest['cfs'])}) reaches White Hole "
                    f"~{nearest['arrival_time'].strftime('%I:%M %p').lstrip('0')} — "
                    f"cast worms near the banks in the first hour, then fish the "
                    f"{BAND_CONTENT[get_flow_band(nearest['cfs'])]['label']} program"
                )
            elif current_cfs - nearest["cfs"] >= 2000:
                timing.append(
                    f"DROP EN ROUTE: {nearest['cfs']:,} CFS reaches White Hole "
                    f"~{nearest['arrival_time'].strftime('%I:%M %p').lstrip('0')} — "
                    f"the first hour of falling water is a prime bite window"
                )

    # Next scheduled change (SWPA)
    change = _find_flow_change(current_cfs, forecast_timeline)
    if change:
        direction, entry = change
        etas = spot_arrival_times(entry["scheduled_time"], entry["cfs"])
        eta_str = " · ".join(
            f"{name} ~{eta.strftime('%I:%M %p').lstrip('0')}" for name, eta in etas
        )
        if direction == "rise":
            timing.append(
                f"SCHEDULED RISE to {entry['cfs']:,} CFS "
                f"({format_generators(entry['cfs'])}) at "
                f"{entry['scheduled_time'].strftime('%I %p').lstrip('0')}: {eta_str}. "
                f"Downstream water stays low longer — be below the front and fish it up"
            )
        else:
            timing.append(
                f"SCHEDULED DROP to {entry['cfs']:,} CFS at "
                f"{entry['scheduled_time'].strftime('%I %p').lstrip('0')}: "
                f"low water reaches {eta_str}"
            )

    return timing


def generate_fishing_report(white_hole_cfs, current_time,
                            timeline_data=None, forecast_timeline=None):
    """
    Build the structured fishing report for current conditions.

    Returns a dict; 'active' is False outside the trip windows (March-April,
    September-October), in which case only the placeholder text applies.
    """
    season = get_trip_season(current_time)
    if season is None:
        return {
            "active": False,
            "placeholder": "Fishing report runs during trip windows (March–April "
                           "and September–October). Flow conditions above still apply.",
        }

    band = get_flow_band(white_hole_cfs)
    content = BAND_CONTENT[band]
    season_content = SEASON_CONTENT[season]
    wading, boating = get_fishing_condition(white_hole_cfs)

    spin = {
        "rig": content["spin"]["rig"],
        "browns": list(content["spin"]["browns"]) + season_content["spin_add"]["browns"],
        "rainbows": list(content["spin"]["rainbows"]) + season_content["spin_add"]["rainbows"],
        "notes": list(content["spin"].get("notes", [])),
    }
    fly = {
        "setup": content["fly"]["setup"],
        "browns": (list(content["fly"]["browns"]) + season_content["fly_add"]["browns"]
                   if content["fly"]["browns"] else []),
        "rainbows": (list(content["fly"]["rainbows"]) + season_content["fly_add"]["rainbows"]
                     if content["fly"]["rainbows"] else []),
    }

    return {
        "active": True,
        "season": season,
        "season_label": season_content["label"],
        "band": band,
        "band_label": content["label"],
        "cfs": white_hole_cfs,
        "generators": format_generators(white_hole_cfs),
        "wading": wading,
        "boating": boating,
        "summary": content["summary"],
        "where": content["where"],
        "boat": content["boat"],
        "timing": build_timing(white_hole_cfs, current_time,
                               timeline_data, forecast_timeline),
        "spin": spin,
        "fly": fly,
        "season_notes": season_content["notes"],
        "regulations": REGULATIONS,
        "gear_check": {
            "spin": GEAR_CHECK["spin"] + season_content["gear_add"]["spin"],
            "fly": GEAR_CHECK["fly"] + season_content["gear_add"]["fly"],
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
        blocks.append(f'''
        <details style="margin-bottom: 8px;">
            <summary style="cursor: pointer; font-weight: bold; padding: 8px 10px; background: #f7fafc; border-radius: 8px;">{section["title"]}</summary>
            <div style="padding: 5px 15px;">
                {intro}
                <ul style="margin: 5px 0 5px 5px;">{_items_html(section["items"])}</ul>
            </div>
        </details>''')
    return "".join(blocks)


def _species_block_html(browns, rainbows):
    """Render the two species programs; either may be empty."""
    html = ""
    if browns:
        html += f'''
            <p style="margin: 10px 0 4px;"><strong style="color: #7b4a12;">🟤 {BROWNS_HEADER}</strong></p>
            <ul style="margin: 0 0 0 5px;">{_items_html(browns)}</ul>'''
    if rainbows:
        html += f'''
            <p style="margin: 10px 0 4px;"><strong style="color: #9d2f4c;">🌈 {RAINBOWS_HEADER}</strong></p>
            <ul style="margin: 0 0 0 5px;">{_items_html(rainbows)}</ul>'''
    return html


def render_fishing_report_html(report):
    """Render the fishing report as an HTML section for the conditions page."""
    if not report["active"]:
        return f'''
    <div class="timeline-box">
        <h3>🎣 Fishing Report</h3>
        <p style="color: #666;">{report["placeholder"]}</p>
    </div>'''

    timing_html = _items_html(report["timing"])
    where_html = _items_html(report["where"])
    boat_html = _items_html(report["boat"])
    season_html = _items_html(report["season_notes"])
    regs_html = _items_html(report["regulations"])

    spin = report["spin"]
    fly = report["fly"]
    spin_notes_html = ""
    if spin["notes"]:
        spin_notes_html = f'''
            <p style="margin: 10px 0 4px;"><strong>Notes:</strong></p>
            <ul style="margin: 0 0 0 5px;">{_items_html(spin["notes"])}</ul>'''

    return f'''
    <div class="timeline-box">
        <h3>🎣 Fishing Report — Gaston's to Cranor's Island</h3>
        <p style="color: #666; margin-bottom: 4px;">{report["season_label"]}</p>
        <p style="font-size: 1.1em; margin: 10px 0;"><strong>{report["band_label"]}</strong>
            — {report["cfs"]:,} CFS at White Hole ({report["generators"]})</p>
        <p style="color: #444;">{report["summary"]}</p>
        {_map_links_html()}
        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Where to go</h4>
        <ul style="margin: 0 0 0 5px;">{where_html}</ul>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Boat &amp; anchoring</h4>
        <ul style="margin: 0 0 0 5px;">{boat_html}</ul>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Timing</h4>
        <ul style="margin: 0 0 0 5px;">{timing_html}</ul>

        <div style="background-color: #f0f7f4; border-radius: 8px; padding: 15px; margin-top: 18px;">
            <h4 style="color: #2c3e50; margin: 0 0 8px;">🎣 Spin Fishing</h4>
            <p style="margin: 4px 0;"><strong>Rig:</strong> {spin["rig"]}</p>
            {_species_block_html(spin["browns"], spin["rainbows"])}
            {spin_notes_html}
        </div>

        <div style="background-color: #f4f2f7; border-radius: 8px; padding: 15px; margin-top: 12px;">
            <h4 style="color: #2c3e50; margin: 0 0 8px;">🪶 Fly Fishing (9 ft 5-wt)</h4>
            <p style="margin: 4px 0;"><strong>Setup:</strong> {fly["setup"]}</p>
            {_species_block_html(fly["browns"], fly["rainbows"])}
        </div>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Season notes</h4>
        <ul style="margin: 0 0 0 5px;">{season_html}</ul>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Regulations</h4>
        <ul style="margin: 0 0 0 5px;">{regs_html}</ul>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Gear check</h4>
        <p style="margin: 6px 0 4px;"><strong>🎣 Spin gear:</strong></p>
        <ul style="margin: 0 0 0 5px;">{_items_html(report["gear_check"]["spin"])}</ul>
        <p style="margin: 10px 0 4px;"><strong>🪶 Fly gear:</strong></p>
        <ul style="margin: 0 0 0 5px;">{_items_html(report["gear_check"]["fly"])}</ul>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Rigging &amp; techniques (reference)</h4>
        {_rigging_html(report["rigging"])}

        <p style="color: #999; font-size: 0.8em; margin-top: 15px;">
            Fishing content distilled from local sources (His Place, Dally's, Cotter Trout Dock,
            AGFC reports, OzarkAnglers); arrival times computed from this page's verified travel
            model. Regulations change — verify with AGFC before fishing.
        </p>
    </div>'''


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

    report = generate_fishing_report(cfs, current_time, timeline_data, forecast_timeline)
    section = render_fishing_report_html(report)

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
</body>
</html>'''

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Fishing report saved to {args.out}")
    if report["active"]:
        print(f"Band: {report['band_label']} — {report['cfs']:,} CFS ({report['generators']})")
    else:
        print(report["placeholder"])


if __name__ == "__main__":
    main()
