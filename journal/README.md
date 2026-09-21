# journal/

Free-form trip notes that become part of the fishing report's knowledge — the same model
as `new-croton-fishing/journal/`, with this river's vocabulary.

`predictions.csv` is a machine log: what the flow model said, every hour, nothing else. This
is the other half — what you saw and what the fish did. Water clarity at the ramp, where the
rise actually showed up, what the guide at the dock said, a bait that worked or didn't, the
rope that needed re-tending. Anything you want.

**Nothing here is attached to `predictions.csv`.** The builder looks up the model's numbers
for a catch by its clock time, at build time, and reports them beside the row. The log
stays a log; the journal stays unconstrained.

The folder can be empty. `build_journal.py` handles zero entries without complaining.

## Writing an entry

One Markdown file per entry in `journal/entries/`, named `YYYY-MM-DD-something.md`:

```bash
cp journal/TEMPLATE.md journal/entries/2026-10-06-white-hole.md
```

Then write. **The body is yours** — any Markdown, any length, any structure. Nothing in it is
parsed, reformatted, or validated. It is carried through to the digest verbatim.

The optional block at the top, between `---` lines, is the only structured part. Every field
in it is optional, including the block itself:

```markdown
---
date: 2026-10-06
title: First morning, dead low till noon
tags: low water, sculpin, drop
species: brown, rainbow
party: Dad, William
spot: White Hole
cfs_reported: 750
water_temp_f: 57
sky: overcast
wind: SW 5
---

Launched at 0700 at the White Hole ramp, ramp fine at min flow. Water was gin clear...
```

| Field | What it does |
|---|---|
| `date` | Sorts the entry and dates its catches. Defaults to the filename prefix |
| `title` | Heading in the digest. Defaults to the filename |
| `tags` | Free — grouped in the digest so a theme across trips is findable |
| `species` | Free — same, grouped separately because it is the common question |
| `party` | Who was in the boat. Three-up changes the lanes and cases the fly rod |
| `spot` | Where the day was mostly fished, in the report's names: `Gaston's`, `White Hole`, `Cranor's Island` — or your own words |
| `cfs_reported` | What the dock, the resort or the Corps line said the flow was — the number people were fishing by, to set beside the model's |
| `water_temp_f` | If you had a thermometer in it. The USGS gauge reading is attached automatically |
| `coords` | `lat, lon` decimal degrees, for a spot worth pinning |
| `sky`, `wind` | In your words, for the hours you fished |

Any other `key: value` you invent is kept and shown as-is.

### The catch table

The template carries a table under `## Catches`. One row per fish, in the vocabulary the
fishing report already uses, so a row can be counted against the advice that was on the
page that hour:

| Column | What goes in it |
|---|---|
| `species` | `rainbow`, `brown`, `cutthroat`, `brook`, `tiger`. The builder files browns under the browns program and everything else under rainbows & others — the same split as the report |
| `size` | inches (a weight if you have one) |
| `time` | clock time, Central, `HH:MM` — `14:35`. The most important cell: it is how the row finds the model's flow for that hour and its minutes vs sunset. `~14:30` is fine for a guess |
| `spot` | `Gaston's`, `White Hole`, `Cranor's Island`, or a landmark in your words |
| `water` | what the river was doing where you were: `rising`, `falling`, `steady`, `dead low`. Your read, not the model's — the builder puts the model's beside it so the two can disagree |
| `boat` | `tie`, `drift`, `anchor`, or `wade` |
| `rig` | `WR rig` (the White River rig), `split-shot`, `float`, `direct` (jerkbait, spinner, spoon or jig tied direct), `indicator`, `tightline`, `swing`, `dry` |
| `bait` | what was on: `sculpin`, `crawler`, `red worm`, `PowerBait pink`, `shrimp`, `egg`, `minnow`, `marabou jig`, `Countdown`, `Rooster Tail`, `sowbug #16`, `Woolly Bugger`, … The builder classes it (`sculpin`, `crawler`, `worm`, `powerbait`, `shrimp`, `egg`, `minnow`, `jig`, `spinner`, `spoon`, `jerkbait`, `swimbait`, `plastic`, `nymph`, `streamer`, `dry`) and warns when it can't |
| `lost` | leave blank for a landed fish; `x` for hooked and lost — the pattern was right about the fish |

A row with nothing but a species is still a row. Every blank is a question the post-trip
write-up asks.

### What the builder adds to each row

For a row with a date and time, `build_journal.py` reads `predictions.csv` for the run at or
just before that time (within two hours) and attaches `model_cfs` (the model's White Hole
flow), `model_band` (the report's band label), `model_state` (rising/falling/stable), and
the USGS `model_temp_f` / `model_do` from that run. **The model's flow is for White Hole**;
at Gaston's the same water is about an hour younger and at Cranor's an hour older — the
row keeps your `water` read for exactly that reason. It also computes `vs_sunset` (minutes,
`-90` before, `+45` after) and a `window` (dawn / midday / dusk / night / other) from sunset
at White Hole.

## Build it

```bash
uv run python scripts/build_journal.py            # build
uv run python scripts/build_journal.py --check    # validate only, write nothing
```

Outputs land in `journal/build/` (gitignored, regenerable — rebuilt from scratch every run):

| Output | What it is |
|---|---|
| `digest.md` | Every entry in full plus tag and species indexes — the one file to read before touching the report's doctrine |
| `index.json` | The same thing structured, for scripts |
| `catches.csv` | One row per fish, with the model's numbers attached |
| `catches_report.md` | The rows summarised by program, band, spot, rig, bait, water and window — and **crossed against the report's flow bands and programs**, so each block of advice shows how many fish stand behind it |

## What the builder will complain about

**Refuses to build**: an unterminated `---` block, a `date` that is not `YYYY-MM-DD`, a
`time` that is not `HH:MM`, or `coords` that are not two numbers.

**Warns and continues**: an entry with no resolvable date, a species, rig or bait the
vocabulary does not know, a catch with no `predictions.csv` row near its time (the log
started 2026-09-20, and the Pi may have been down), or `coords` far from the river.

## Doctrine changes come from here

The report's advice was written from local sources before a single row existed. When a
season of rows says a band's first bullet is wrong — the crawdad slot never produced, the
float rig outfished everything at one unit — the change is made in `fishing_report.py` with
the row count in the commit message, and the inventory's AR cells follow if gear moved
(CLAUDE.md, gear doctrine). The builder never edits the report; it only shows the evidence.
