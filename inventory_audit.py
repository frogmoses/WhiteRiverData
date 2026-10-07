"""
Drift check between the fishing report's gear and the tackle inventory.

The inventory of record is new-croton-fishing/reference/tackle-inventory.md
(CLAUDE.md, gear doctrine). The report never reads it at runtime — the Pi does
not have that repo and the page must render without it — but every item the
report presents as owned must trace to a row there, and a row that is pruned,
or whose hooks failed inspection, must not be presented as ready. That used
to be a re-audit someone had to remember (the last one: 2026-08-28); this
module makes it a test that fails when the file is present and drifted, and a
script the Croton side can run after an inventory edit.

Three registries below:
  OWNED_GEAR      — what the report names as owned: how the report says it
                    (`mention`) and how to find its inventory row (`row`)
  BUY_OR_VERIFY   — named by the report as NOT owned (gear-check buy items),
                    each with the inventory row that would mean it HAS been
                    bought (None where the category is uninventoried by
                    decision, so there is nothing to look for)
  UNINVENTORIED   — fly gear, which Brian keeps out of the inventory for now

`audit()` returns a list of findings; an empty list is a clean audit.
"""
import os
import re

from fishing_report import BAND_CONTENT, SEASON_CONTENT, GEAR_CHECK, RIGGING_REFERENCE

INVENTORY_PATH = os.path.expanduser(
    "~/CodeProjects/new-croton-fishing/reference/tackle-inventory.md")

# (label, how the report mentions it, how the inventory row reads)
OWNED_GEAR = [
    # rods and reels — the AR pair (the Cherrywood stopped travelling and the
    # report no longer names it)
    ("Daiwa Presso (AR)", r"Presso", r"AR \| \*\*6'\*\* Daiwa Presso"),
    ("St. Croix Premier PS60ULF", r"St\. Croix", r"PS60ULF"),
    ("Abu Garcia Black Max 30", r"Black Max", r"Black Max 30"),
    ("Pflueger President 20 (AR travel reel)", r"President", r"Pflueger President size 20"),
    ("Daiwa Exceler 2000 SH (AR travel reel)", r"Exceler", r"Daiwa Exceler 2000 SH"),
    # metal
    ("Kastmaster", r"Kastmaster", r"Kastmaster ×\d"),
    ("Cleo (gold)", r"\bCleo\b", r"Cleo gold"),
    ("Mepps Aglia #3", r"Aglia|Mepps", r"Mepps Aglia #3"),
    ("Mepps Black Fury #3", r"Black Fury", r"Black Fury #3"),
    ("Rooster Tail ¼ oz", r"Rooster Tail", r"Rooster Tail ¼ oz"),
    ("Panther Martin", r"Panther Martin", r"Panther Martin"),
    ("Johnson Beetle Spin 1/16", r"Beetle Spin", r"Beetle Spin 1/16"),
    # cranks and minnows
    ("sinking swimmers (Countdown class)", r"sinking swimmers|Countdown", r"Sinking swimmers ×\d"),
    ("suspending perch jerkbait", r"suspending perch", r"SUSPENDS"),
    # jigs, plastics, swimbaits
    ("marabou hair jigs", r"[Mm]arabou", r"marabou hair jigs"),
    ("Ned mushroom head 1/10 oz", r"Ned head", r"Mushroom heads 1/10 oz"),
    ("green pumpkin Senko", r"Senko", r"Yamamoto 5\" green pumpkin"),
    ("panfish ball head 1/16", r"panfish head", r"Ball heads 1/16"),
    ("2 in white curly grub", r"2 in white grub", r"Curly Tail Grub 2\" white"),
    ("pink-head crappie jig", r"crappie jig", r"Pre-rigged pink/white"),
    ("Keitech Swing Impact FAT", r"Keitech", r"Swing Impact FAT"),
    ("Owner Flashy Swimmer", r"Flashy Swimmer", r"Flashy Swimmer"),
    ("Zoom Tab Tail 4 in white pearl", r"Tab Tail", r"Tab Tail 4\" White Pearl"),
    # terminal
    ("Eagle Claw Aberdeen #4", r"Aberdeen", r"Aberdeen 202F-4"),
    ("Eagle Claw Aberdeen #6 (eggs and Mice Tails)", r"#6 Aberdeen", r"Aberdeen #6 ×\d"),
    # bought 2026-10-07 — the first fly item the inventory carries (its own
    # "Fly gear" section); the rest of the fly gear stays uninventoried
    ("RIO Trout VersiLeader (streamer sink leader)", r"VersiLeader|polyleader", r"RIO Trout VersiLeader ×\d"),
    ("Reaction Tackle #1 drop-shot hooks", r"drop-shot hook", r"Reaction Tackle #1 red"),
    ("size 10 swivels", r"swivel", r"size-10 ball-bearing swivels"),
    ("bell sinkers", r"bell sinker|oz bell", r"bell sinkers"),
    ("split shot", r"split shot", r"split shot"),
    ("egg sinkers", r"egg sinker", r"Egg sinkers"),
    ("rubber-core sinkers (told to skip)", r"rubber-core", r"rubber-core"),
    ("slip float", r"slip float", r"Slip float"),
    ("bobber stops", r"bobber stop", r"bobber stops"),
    ("rig beads", r"orange bead|rig bead", r"rig beads"),
    ("20 lb fluoro (butt / universal leader)", r"20 lb fluoro", r"20-lb fluoro universal"),
    ("30 lb fluoro (bite leader)", r"30 lb fluoro", r"30-lb fluoro bite"),
    # bought 2026-09-28 — all three came off the buy list below
    ("2 mm tippet rings", r"tippet ring", r"2 mm tippet rings ×\d"),
    ("#16 orthodontic rubber bands", r"rubber band", r"orthodontic elastics"),
    ("worm blower", r"worm blower", r"Magic 1004 Worm Blower"),
    ("Z-Man TRD CrawZ (the soft craw)", r"soft craw|TRD CrawZ", r"TRD CrawZ 2\.5\" Mudbug"),
    # found by the 'bought' check on its first run, 2026-09-28: the rainbow
    # hook-leader tier was on the buy list while the shelf held it three ways
    ("Maxima Chameleon 4 lb (rainbow hook leaders)", r"Maxima|Chameleon", r"Chameleon 4 lb"),
    # bought 2026-10-04 — the last line item on the spin buy list. The row
    # pattern stays tight on purpose: the shelf's 8 lb P-Line Floroclear is
    # fluoro-COATED copolymer (the Croton drop-shot leader spool) and the Maxima
    # 8 lb wheels are mono, and neither is the browns hook-leader spec. Brian
    # was asked whether the coating should count and said no (2026-09-28).
    ("8 lb fluorocarbon spool (browns hook leaders)", r"8 lb fluorocarbon",
     r"100% fluorocarbon[^|]*\| \*\*8 lb\*\*"),
]

# Named by the report as things to buy or verify — must NOT be presented as
# owned. Third field: what the row would look like once it IS bought, so the
# audit notices a buy item the inventory has quietly taken delivery of (that
# is how the 2026-09-28 purchase went unnoticed until someone read both files).
# Keep these TIGHT — a loose pattern matches a near-miss on the shelf and cries
# wolf; the note on a row says which near-miss it is deliberately not matching.
BUY_OR_VERIFY = [
    ("hand dip net", r"dip net", r"dip net"),
    # decided 2026-09-28: the Cherrywood stops travelling and a rod matching its
    # blank is bought for Dad's. Owned when the rack grows an AR row for it.
    ("resident browns rod at Dad's", r"browns rod", r"AR \|[^|]*medium spinning"),
]

# Fly gear: uninventoried by Brian's standing decision (a future inventory
# section) — except the VersiLeaders, which have a row since 2026-10-07
UNINVENTORIED = [
    r"Recon", r"5-wt", r"Airlock|Thingamabobber", r"indicator",
    r"Woolly Bugger", r"Girdle Bug", r"Sunday Special", r"sowbug", r"Zebra|Ruby Midge",
    r"San Juan", r"[Hh]opper", r"Soft Hackle|soft hackle", r"Elk Hair", r"caddis pupa",
    r"egg pattern|peach/orange egg",
]

# Anything the report says that looks like a piece of gear must be covered by
# one of the three registries. Brand/model words and rigging hardware only —
# baits bought fresh in Arkansas are not gear.
GEAR_TOKENS = re.compile(
    r"Kastmaster|Cleo|Keitech|Flashy Swimmer|Tab Tail|Countdown|sinking swimmers|Rapala|Rogue|"
    r"Beetle Spin|Panther Martin|Rooster Tail|Mepps|Aglia|Black Fury|[Mm]arabou|Ned head|Senko|"
    r"Fire Tube|crappie jig|panfish head|slip float|bobber stop|Aberdeen|drop-shot hook|Kahle|"
    r"swivel|bell sinker|oz bell|bank sinker|egg sinker|split shot|rubber-core|Cherrywood|"
    r"Black Max|Presso|St\. Croix|Exceler|President|XPS|Phoebe|Dardevle|Spinnie|Thomas|"
    r"Trout Magnet|Zoom|Smithwick|Recon|5-wt|VersiLeader|polyleader|Airlock|Thingamabobber|"
    r"browns rod|"
    r"tippet ring|worm blower|dip net|20 lb fluoro|30 lb fluoro|suspending perch|"
    r"Woolly Bugger|Girdle Bug|Sunday Special|Zebra|Ruby Midge|San Juan|Soft Hackle|"
    r"Elk Hair|indicator|soft craw|TRD CrawZ|Maxima|Chameleon|2 in white grub|orange bead|rig bead|rubber band"
)

PRUNED_MARKER = re.compile(r"\*\*Pruned", re.I)
FAILED_MARKER = re.compile(r"failed inspection", re.I)


def _walk(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk(v)


def report_text():
    """Every string the fishing report can render, joined."""
    parts = []
    for source in (BAND_CONTENT, SEASON_CONTENT, GEAR_CHECK, RIGGING_REFERENCE):
        parts.extend(s for s in _walk(source) if not s.lstrip().startswith("<svg"))
    return "\n".join(parts)


def gear_check_text():
    return "\n".join(_walk(GEAR_CHECK))


def live_paragraphs(inventory_text):
    """The inventory minus its 'Pruned on repack day' paragraphs."""
    return [p for p in re.split(r"\n\s*\n", inventory_text) if not PRUNED_MARKER.search(p)]


def load_inventory(path=INVENTORY_PATH):
    """The inventory text, or None when the file is not on this machine."""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def registry_findings(text=None):
    """
    Problems internal to the report and its registries (no inventory needed):
    a registered item the report no longer mentions, or a gear token in the
    report that no registry covers.
    """
    text = report_text() if text is None else text
    findings = []
    for label, mention, _ in OWNED_GEAR:
        if not re.search(mention, text):
            findings.append(f"registry: '{label}' is registered as owned but the report no longer mentions it")
    covered = ([m for _, m, _ in OWNED_GEAR] + [m for _, m, _ in BUY_OR_VERIFY] + UNINVENTORIED)
    for token in sorted(set(GEAR_TOKENS.findall(text))):
        if not any(re.search(pat, token) for pat in covered):
            findings.append(f"unregistered: the report names '{token}' but no registry covers it "
                            "(add it to OWNED_GEAR, BUY_OR_VERIFY or UNINVENTORIED in inventory_audit.py)")
    return findings


def inventory_findings(inventory_text, text=None):
    """
    Drift between the report and the inventory: an owned item with no live
    row (missing or pruned), an owned item whose row says its hooks failed
    inspection without the gear check saying so, or a buy/verify item that the
    inventory now carries as owned.
    """
    live = live_paragraphs(inventory_text)
    live_text = "\n\n".join(live)
    gear_check = gear_check_text()
    findings = []
    for label, mention, row in OWNED_GEAR:
        hits = [p for p in live if re.search(row, p)]
        if not hits:
            if re.search(row, inventory_text):
                findings.append(f"pruned: '{label}' only matches a pruned paragraph of the inventory — "
                                "the report still presents it as owned")
            else:
                findings.append(f"missing: '{label}' (row pattern {row!r}) has no row in the inventory")
            continue
        # A table is one paragraph; the inspection verdict belongs to the row (line)
        hit_lines = [line for p in hits for line in p.splitlines() if re.search(row, line)]
        if any(FAILED_MARKER.search(line) for line in hit_lines) and not re.search(mention, gear_check):
            findings.append(f"inspect: the inventory says '{label}' failed hook inspection; "
                            "the gear check must say so")
    # The reverse drift: the report is still telling Brian to buy something the
    # inventory now carries. Cheaper to catch here than by reading both files.
    for label, _, row in BUY_OR_VERIFY:
        if row is None:
            continue
        if any(re.search(row, p) for p in live):
            findings.append(f"bought: '{label}' is on the report's buy/verify list, but the "
                            "inventory carries a live row for it — move it to OWNED_GEAR and "
                            "reword the gear check")
    return findings


def audit(inventory_text=None, text=None):
    """All findings. With inventory_text None, only the registry checks run."""
    findings = registry_findings(text)
    if inventory_text is not None:
        findings += inventory_findings(inventory_text, text)
    return findings
