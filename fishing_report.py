"""
Fishing report generator for the Gaston's -> Narrows reach of the White River.

Content is distilled from WHITE_RIVER_RESEARCH_BRIEF.md (fishing knowledge:
spots, rigs, baits, presentations, regulations) but ALL flow numbers, travel
times, and arrival ETAs come from this repo's verified model
(water_calculator). Where the brief's flow claims conflicted with the repo
(e.g. its "rise arrives in 90 minutes" surge-front table), the repo wins.

Gear recommendations are restricted to Brian's owned tackle
(new-croton-fishing/reference/tackle-inventory.md) plus consumables.

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

# Reach landmarks, miles below the dam. Gaston's and White Hole match the
# repo's chart model (chart_generator.py); the Narrows extends it downstream.
REACH_SPOTS = [
    ("Gaston's", 4.0),
    ("White Hole", 7.0),
    ("The Narrows", 9.5),
]

WHITE_HOLE_MILE = 7.0  # the travel model's calibrated distance

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
# Band content. Sources: research brief §3.4 (level ladder), §5.6 (holding
# water), §6 (rigs/bait/hardware), §7 (tied-boat presentations), §8 (fly).
# Spin and fly are separate by design — do not merge them.
# ---------------------------------------------------------------------------

BAND_CONTENT = {
    "minimum": {
        "label": "Minimum flow (dead low)",
        "summary": "The river is a giant spring creek. Gravel bars exposed; prop strikes "
                   "are the boat risk and the White Hole ramp can be tricky to launch. "
                   "Wading is wide open. Fish see everything — light line, low light.",
        "where": [
            "The weed-bed edges a short run upstream of the White Hole ramp — sowbug and scud water; trout hold on the edges and pick",
            "The head of the White Hole where the deep water starts at the ramp and runs downstream",
            "The downstream lip (drop-off) of every shoal, where gravel falls into the run",
            "The seam where the main tongue runs past a moss/grass bed — the single most important low-water feature",
            "Undercut banks, root wads, log jams, boulder pockets",
            "The Narrows island — fish both sides, deepest water on the far side; downstream holds low water longest",
        ],
        "boat": [
            "Bank-tie is easy and anchoring is safe at this level",
            "Watch the prop over gravel bars; know the channel before running",
            "Low water lingers longest downstream — run down early, work back upstream as any afternoon water arrives",
        ],
        "spin": {
            "rig": "White River rig: 30–48 in of 4 lb leader (long at low water), dropper-loop Y with a "
                   "6–10 in sinker leg. Bell sinker 1/8–3/16 oz (#10–#9). #4 light-wire Aberdeen hook, "
                   "size 10 barrel swivel up top.",
            "baits": [
                "Inflated night crawler — hook first, then 4–5 air bubbles spaced along a large crawler; the light-wire Aberdeen lets it lift",
                "1½-in crawler or red-worm stub on the #4 for numbers",
                "Peeled cocktail shrimp, pea-sized chunk — survives current far better than dough",
                "PowerBait: pink or white floating worms / Mice Tail rigged to float horizontally, ~a foot off bottom (mono hook leg, not fluoro)",
                "Sculpin near the openings at the base of large rocks — catch your own flipping rocks; verify AGFC baitfish rules first",
                "Egg-bead rig: orange rig bead pegged a couple inches above a bare #4",
            ],
            "lures": [
                "Float rig (the highest-leverage method): slip float + bobber stop, 1/16 oz panfish head with a 2 in white grub or a pink-head crappie jig, bait riding 1–3 ft off bottom; cast up, feed it 40–80 ft downstream, reel back, repeat",
                "Olive/brown marabou jig (the 'sculpin' color) or white marabou under the float",
                "1/16 oz Beetle Spin or the small Panther Martin along seams and soft edges",
                "Gold spoon (Buoyant/K.O. class) only in low light — this water is too thin for hardware at midday",
            ],
            "notes": [
                "The lighter the better: 4 lb leader, small offerings, longer casts",
                "Fish dawn, dusk, and shade — big browns go nocturnal at dead low",
            ],
        },
        "fly": {
            "setup": "9 ft 5-wt (Recon). Two primary games: tightline the near seam with a 10–12 ft "
                     "thin leader (or 5 ft 20 lb + 3 ft 12 lb + tippet ring + 3–4 ft 4X–5X fluoro), "
                     "or swing a soft hackle on a shortened 6–7½ ft leader.",
            "flies": [
                "Gray sowbug #14–16 — the signature food, no seasonality",
                "Sunday Special #14 (tungsten #12 for depth)",
                "Zebra Midge #16–18 (black/nickel, red/nickel) and Ruby Midge #16–18",
                "Fluorescent pink San Juan worm — especially the first hour of any rise",
                "Peach/orange egg",
            ],
            "techniques": [
                "Tightline/high-stick the seam beside the boat: flick 8–15 ft upstream, lead down with the tip high — highest fish-per-hour from a seat, and the only thing that works in wind",
                "Swing: cast across and slightly down, one upstream mend, let it come tight, hang and pulse 6–10 seconds at the dangle; don't strike, let it come tight",
                "Short indicator drift, 20–25 ft max, indicator set ~1.5× depth; stick-on indicators hold on fine tippet at this flow",
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
            "Both sides of the Narrows island (deepest water far side)",
            "Behind logs, rocks and boulders; downstream of islands; inside bends",
        ],
        "boat": [
            "Tie from the BOW, bow pointed upstream, slip knot at the cleat, knife within reach",
            "Rotate spots every 45–60 minutes: untie, drop 100 yards, retie",
            "Anchoring still reasonable at this level — but rig it to slip free",
        ],
        "spin": {
            "rig": "White River rig, 24–36 in hook leg, 1/4 oz bell (#8), #4 Aberdeen, size 10 swivel, "
                   "4 lb leader.",
            "baits": [
                "Night crawlers — stubs for numbers, inflated whole crawlers for better fish",
                "Shrimp chunks; egg-bead rig with the orange beads",
                "PowerBait floating worms/eggs (orange/garlic in fall, pink/white in clear water)",
            ],
            "lures": [
                "1/4 oz spoons — the strongest tray for this river: Kastmaster (chrome, chrome/blue), Little Cleo-class, gold w/ red accents. Gold in bright sun, silver/nickel on cloudy mornings",
                "1/4 oz Rooster Tail (flame/chartreuse) or Mepps Aglia #3; Black Fury #3 on dark days. Cast quartering upstream (10–11 o'clock), sink first, steady retrieve — expect the take as it swings",
                "The downstream hang: let the spinner swing dead below the boat and hold it — the blade works on current alone; a free presentation only a tied boat gets",
                "Countdown minnows (brown-trout, brook-trout patterns) counted down along drop-offs",
                "Float rig still works to ~2 units — favor it in the slower lanes",
            ],
            "notes": [
                "Never clip a snap swivel to a spinner — 18 in leader to a small barrel swivel up the line",
            ],
        },
        "fly": {
            "setup": "Indicator rig with real weight (Airlock/Thingamabobber class), or the swing setup. "
                     "For streamers: loop a fast-sinking VersiLeader/polyleader on the floating line "
                     "('insta-sink-tip', ~$15) + 3–4 ft of 12–16 lb fluoro.",
            "flies": [
                "Sowbug #14–16 / Sunday Special #12–14 as the point fly, midge #16–18 dropper 18 in above",
                "Pink San Juan worm and egg patterns near the banks whenever the water is moving up",
                "Olive Woolly Bugger #8–10 or black Girdle Bug #8–10 on the sink leader",
            ],
            "techniques": [
                "Short indicator drifts in the seams; lengthen the drift by feeding line, not by casting farther",
                "Swing soft hackles through the shoal tails — cover water by lengthening 20, 25, 30, 35 ft",
                "Streamers are swung, not stripped, from the tied boat",
            ],
        },
    },
    "two_three_units": {
        "label": "2–3 units (5,000–10,000 CFS)",
        "summary": "Fish move to the banks and flooded grass. No wading. Fish the edges, "
                   "not open water — seams, foam lines and defined runs in 4–5 ft along the banks.",
        "where": [
            "Bank edges and newly flooded grass/gravel that was dry an hour ago — soft current, dislodged food",
            "Inside bends and the shelf-to-channel drop-off",
            "Behind bank structure: logs, root wads, boulders",
            "Foam lines and defined runs along the banks",
        ],
        "boat": [
            "Anchor only with a plan — a bump in generation reaches this reach fast; tie high to a tree instead",
            "Tie from the BOW with slack, re-tend the rope every 20–30 minutes on rising water",
            "Know what's downstream before committing to a spot; there is no warning siren on this river",
        ],
        "spin": {
            "rig": "White River rig, hook leg shortened to 18–24 in (a long leader lays flat in faster "
                   "water), 3/8 oz bell (#7), 4 lb leader. Drop-shot hooks (#1, red) ride "
                   "perpendicular off the tag — right for a whole crawler or sculpin.",
            "baits": [
                "TWO whole night crawlers threaded on a #4 with the tails dangling, cast downstream from the tied boat and held — the trophy technique for exactly this situation",
                "Minnow, lips-hooked, drifted naturally along drop-offs and behind structure",
                "Sculpin fished near bottom around big rock",
            ],
            "lures": [
                "Jerkbait window (best at 2–4 units): Countdown brown/brook-trout patterns, and the suspending perch deep jerkbait in the Smithwick Rogue slot — twitch-pause along the banks",
                "Keitech Swing Impact FAT 3.3/3.8 on Flashy Swimmer heads, or the 4 in white-pearl Tab Tail grubs, swum along the bank edge — white is the named color for White River browns",
                "3/8 oz XPS spoon when the 1/4 oz won't stay down",
                "Walk the rig down: lift, feed 3–6 ft, re-settle — turns the tied position into a 100-yard drift",
            ],
            "notes": [
                "First hour of the rise: worms cast near the banks — a documented, predictable pattern, not folklore",
            ],
        },
        "fly": {
            "setup": "Streamer program: fast-sinking polyleader on the floating line, 3–4 ft of 12–16 lb "
                     "fluoro, weighted #6–10 flies. Swung, not stripped. Nymphing gets hard at 3+ units.",
            "flies": [
                "Olive Woolly Bugger #8–10, black Girdle Bug #8–10 swung along the banks",
                "Pink San Juan worm or egg dead-drifted tight to the flooded grass on the rise",
            ],
            "techniques": [
                "Cast across, mend once, swing through the bank seam, hang at the dangle",
                "Fish the soft water the boat itself creates when nothing else is reachable",
                "Deep indicator work is marginal from a seat at this flow — the swing is the primary method",
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
            "Slack pockets downstream of the Narrows island",
        ],
        "boat": [
            "Do NOT anchor in current — this is how people drown on this river. Drag chain (legal on the White) or tie high in a genuine eddy",
            "Bow upstream, slip knot, knife in reach, re-tend the rope constantly",
            "Debris starts moving at these flows; keep watch upstream",
        ],
        "spin": {
            "rig": "White River rig with a 1/2 oz bell (#6) or a bank sinker, hook leg 18–24 in, "
                   "4–6 lb leader. A tied boat needs roughly double the drift-chart weight to hold bottom.",
            "baits": [
                "Two whole crawlers on a #4 or a #1 drop-shot hook, cast downstream and held in the soft lane",
                "3 in minnow, lips-hooked, drifted along the bank edge — the documented high-water big-trout method",
            ],
            "lures": [
                "Keitech FAT 3.8/4.3 on 1/4–3/8 oz Flashy Swimmer swum along the bank — the spin version of the guides' streamer program",
                "Suspending perch jerkbait with long pauses in eddies and seams",
                "3/8 oz XPS spoon in the deeper slots",
            ],
            "notes": [
                "Calibrate weight: the rig should hold, then slip a few inches when the tip is lifted. Never moves = too heavy; never stops = too light",
            ],
        },
        "fly": {
            "setup": "Honestly limited water for a floating-line 5-wt. If you fish it: the sink-leader "
                     "streamer swing from a boat tied in a true eddy, or park the fly rod until the drop.",
            "flies": [
                "Olive Woolly Bugger / black Girdle Bug #8 swung slow and deep through eddy seams",
            ],
            "techniques": [
                "Swing only — casting distance and depth control from a seat are both gone at this flow",
                "Watch for the drop instead: the first hour of falling water is the best fly window of the day",
            ],
        },
    },
    "high": {
        "label": "Heavy generation (16,500+ CFS)",
        "summary": "20,000+ CFS. Debris in the water, no wading anywhere, and this is not "
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
            "rig": "Heaviest bottom rig you can hold with owned bells/bank sinkers (3/4–1 oz class), "
                   "short leg, 6 lb leader — slack-water soaks only.",
            "baits": [
                "Whole crawlers or shrimp soaked in true slack edges",
            ],
            "lures": [
                "4 in white Tab Tail or Keitech 4.3 pitched along slack margins for a hunting brown",
            ],
            "notes": [
                "The honest play is timing, not tackle: fish the first hours after the cut, when the river drops back through the good bands",
            ],
        },
        "fly": {
            "setup": "The fly rod stays cased at this level.",
            "flies": [],
            "techniques": [
                "Plan the fly day around the fall-out: the drop back through 2–3 units and below is prime swing water",
            ],
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
            "Forage order: sculpin > crawdad > sowbug/scud > midge > worms-on-the-rise > terrestrials",
            "Not a dry-fly month — nymphs and streamers; a #10 hopper on warm afternoons is the exception",
        ],
        "spin_add": [
            "Soft craw/hellgrammite plastics and the Ned-head crawdad presentation earn their slot in fall — soft-shell crawdads are a named top natural bait for browns",
        ],
        "fly_add": [
            "Add a #10 hopper for warm afternoons (dry-dropper into the soft water)",
        ],
    },
    "spring": {
        "label": "Spring (March–April): post-spawn rainbows, front edge of the caddis",
        "notes": [
            "Rainbows are post-spawn and feeding normally; stockings are still thin after the 2025 hatchery losses — temper numbers expectations, brown expectations are intact or better",
            "The caddis hatch truly fires at flows around 4,000 CFS or less and works upstream from the lower river — early April usually catches the front edge here, not the peak",
            "The tell: evening swarms of egg-laying caddis; activity picks up after 5 pm",
            "The bite skews later — mid-morning through afternoon, then the evening caddis window. Overcast and rainy days are the best days",
            "BWOs on grey days; shad patterns still produce on big spring water",
            "When Crooked Creek and the Buffalo rise on rain, the Corps cuts generation to protect Newport — rain can hand you surprise low water",
        ],
        "spin_add": [
            "On big spring water, white swimbaits/grubs imitate shad pulled through the dam — fish them on the banks",
        ],
        "fly_add": [
            "Add the Tailwater Soft Hackle in caddis green #14 (the swinging fly) and an Elk Hair Caddis #14 for the evening window",
            "Subsurface caddis pupa/wets produce before, during and after the hatch — and are one of the best ways to find a trophy brown",
        ],
    },
}

REGULATIONS = [
    "Keep only 2 rainbows under 14 in; every other trout goes back immediately (Bull Shoals Dam to Norfork Access, effective Feb 2026) — browns are catch-and-release here",
    "Bait fishing = single hooking point per pole. Swap trebles for a single hook before tipping any spoon or spinner with shrimp/crawdad",
    "One rod per angler, attended at all times",
    "Trout permit required (16+) in addition to the fishing license",
    "Verify current limits by phone before the trip: AGFC 833-345-0325 (this fishery is under active emergency management)",
]

GEAR_CHECK = [
    "Leader material is the one purchase that matters: 4 lb clear/green mono or 4X–5X fluoro tippet — the owned 20/30 lb fluoro is invisible to nothing in this water",
    "Verify the bell-sinker assortment actually covers 1/8–1/2 oz before the trip",
    "Rubber-core sinkers are the sleeper: change weight without re-tying as generation changes",
    "Optional $3 upgrade: #6–#8 light-wire bait hooks (the #4 Aberdeens work, just oversized for PowerBait)",
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
        "baits": list(content["spin"]["baits"]),
        "lures": list(content["spin"]["lures"]),
        "notes": list(content["spin"]["notes"]) + season_content["spin_add"],
    }
    fly = {
        "setup": content["fly"]["setup"],
        "flies": list(content["fly"]["flies"]),
        "techniques": list(content["fly"]["techniques"]) + season_content["fly_add"],
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
        "gear_check": GEAR_CHECK,
    }


# ---------------------------------------------------------------------------
# HTML rendering (a section spliced into the conditions page, or standalone)
# ---------------------------------------------------------------------------

def _items_html(items):
    return "".join(f"<li>{item}</li>" for item in items)


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
    gear_html = _items_html(report["gear_check"])

    spin = report["spin"]
    fly = report["fly"]
    fly_flies_html = _items_html(fly["flies"]) if fly["flies"] else "<li>—</li>"

    return f'''
    <div class="timeline-box">
        <h3>🎣 Fishing Report — Gaston's to the Narrows</h3>
        <p style="color: #666; margin-bottom: 4px;">{report["season_label"]}</p>
        <p style="font-size: 1.1em; margin: 10px 0;"><strong>{report["band_label"]}</strong>
            — {report["cfs"]:,} CFS at White Hole ({report["generators"]})</p>
        <p style="color: #444;">{report["summary"]}</p>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Where to go</h4>
        <ul style="margin: 0 0 0 5px;">{where_html}</ul>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Boat &amp; anchoring</h4>
        <ul style="margin: 0 0 0 5px;">{boat_html}</ul>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Timing</h4>
        <ul style="margin: 0 0 0 5px;">{timing_html}</ul>

        <div style="background-color: #f0f7f4; border-radius: 8px; padding: 15px; margin-top: 18px;">
            <h4 style="color: #2c3e50; margin: 0 0 8px;">🎣 Spin Fishing</h4>
            <p style="margin: 4px 0;"><strong>Rig:</strong> {spin["rig"]}</p>
            <p style="margin: 10px 0 4px;"><strong>Baits:</strong></p>
            <ul style="margin: 0 0 0 5px;">{_items_html(spin["baits"])}</ul>
            <p style="margin: 10px 0 4px;"><strong>Lures:</strong></p>
            <ul style="margin: 0 0 0 5px;">{_items_html(spin["lures"])}</ul>
            <p style="margin: 10px 0 4px;"><strong>Notes:</strong></p>
            <ul style="margin: 0 0 0 5px;">{_items_html(spin["notes"])}</ul>
        </div>

        <div style="background-color: #f4f2f7; border-radius: 8px; padding: 15px; margin-top: 12px;">
            <h4 style="color: #2c3e50; margin: 0 0 8px;">🪶 Fly Fishing (9 ft 5-wt)</h4>
            <p style="margin: 4px 0;"><strong>Setup:</strong> {fly["setup"]}</p>
            <p style="margin: 10px 0 4px;"><strong>Flies:</strong></p>
            <ul style="margin: 0 0 0 5px;">{fly_flies_html}</ul>
            <p style="margin: 10px 0 4px;"><strong>Techniques:</strong></p>
            <ul style="margin: 0 0 0 5px;">{_items_html(fly["techniques"])}</ul>
        </div>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Season notes</h4>
        <ul style="margin: 0 0 0 5px;">{season_html}</ul>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Regulations</h4>
        <ul style="margin: 0 0 0 5px;">{regs_html}</ul>

        <h4 style="color: #2c3e50; margin: 18px 0 6px;">Gear check</h4>
        <ul style="margin: 0 0 0 5px;">{gear_html}</ul>

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
