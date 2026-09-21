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

### The stage table

There is no discharge gauge between the dam and Norfork (checked against the USGS site
catalog 2026-09-21: Flippin 07055000 ran daily 1928–81, Cotter never had a continuous
record), so the travel model has never been checked against the river. The dock post at
the White Hole boat dock is the gauge: the dock floats, so the mark the deck sits at on
its post is the stage, and the jetty upstream of it does not change the level in the
eddy, only the current. Tape or paint the post every 6 in and read it.

The template carries a second table under `## Stage`. One row per reading:

| Column | What goes in it |
|---|---|
| `time` | Central `HH:MM`, same rules as a catch |
| `reading` | the mark the deck sits at — a number in whatever unit the post is marked in, the same unit every time (`14`, `14 in`, `2.5`). A row with a time and no reading is fine (`water` says what you saw) |
| `water` | `rising`, `falling`, `steady`, `dead low` — your read at that moment. **Leave it blank and the builder derives it** from the reading before it in the same entry (`water_source` = `derived`), so a plain series of numbers is enough |
| `note` | anything — "first push, foam line", "boats in both slips" |

Read the post every 15–20 minutes across a predicted arrival (the page says "arriving
~2:40 PM"). The first reading that moves is the observed arrival, bracketed by the reading
before it; for a drop the series traces the recession, which is what the window model
claims to predict.

### What the builder does with stage rows

Every reading gets the same `model_cfs` / `model_band` / `model_state` as a catch, plus the
run's `model_next_change` / `model_next_start` / `model_next_down`. Then, per entry, each
change of direction (a row that says or derives `rising` or `falling` after one that did
not) is an **event**, and the builder finds the prediction it tests: among runs in the six
hours before it, the one whose arrival in that direction lies closest to it — a `measured`
prediction (the model saw the water leave the dam) beats a `scheduled` one (it only had
the SWPA schedule). `stage_report.md` sets them side by side with the delta in minutes,
positive when the water came later than predicted. It also lists steady readings against
the model's flow for that hour: once that fills in, a glance at the post reads as a CFS.

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
| `stage.csv` | One row per dock-post reading, with the model's numbers attached |
| `stage_report.md` | **Predicted vs observed** for every rise or drop seen at the dock, the raw readings beside the model, and reading-vs-flow as the seed of a rating curve |

## What the builder will complain about

**Refuses to build**: an unterminated `---` block, a `date` that is not `YYYY-MM-DD`, a
`time` that is not `HH:MM`, or `coords` that are not two numbers.

**Warns and continues**: an entry with no resolvable date, a species, rig or bait the
vocabulary does not know, a catch or reading with no `predictions.csv` row near its time
(the log started 2026-09-20, and the Pi may have been down), a stage reading with no
leading number, a `water` word it cannot class, or `coords` far from the river.

## Doctrine changes come from here

The report's advice was written from local sources before a single row existed. When a
season of rows says a band's first bullet is wrong — the crawdad slot never produced, the
float rig outfished everything at one unit — the change is made in `fishing_report.py` with
the row count in the commit message, and the inventory's AR cells follow if gear moved
(CLAUDE.md, gear doctrine). The builder never edits the report; it only shows the evidence.
