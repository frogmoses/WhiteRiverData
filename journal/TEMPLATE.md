---
date:
title:
tags:
species:
party:
spot:
cfs_reported:
water_temp_f:
coords:
sky:
wind:
---

Write whatever is worth remembering. Empty fields above are ignored, and you can delete
the whole block if you just want to write. See journal/README.md.

## Catches

One row per fish, in the report's words. `time` is Central `HH:MM` (it finds the model's
flow for that hour); `water` is what the river was doing where you were (rising / falling /
steady / dead low); `boat` is tie / drift / anchor / wade; `rig` is WR rig / split-shot /
float / direct / indicator / tightline / swing / dry; `bait` is what was on the hook;
`lost` is blank or `x`. `scripts/build_journal.py` reads this table into
`journal/build/catches.csv` with the model's numbers beside each row.

| species | size | time | spot | water | boat | rig | bait | lost |
|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |
