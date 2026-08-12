# DuckTales replay corpus provenance

`recovery/migration/cold5-input-schedule-v1.json` preserves the selected 171
host-input transitions from the historical recovery work in a neutral
`amiga.master-tick` schedule. It is a recording source, not a replay artifact,
checkpoint oracle, or Atlas source.

`artifacts/replays/shared-amiga-calibration.pfreplay.json` was freshly recorded
from that schedule through the Amiga ReplaySession adapter under
`pf-amiga-a500-ocs-pal-v13`. It binds the ordered DT1/DT2 media, the actual
CHIP-HUNK load/entry at `0x010008`, the full launch descriptor, semantic
boundary profile, exact base snapshot, supported channels, canonical
checkpoints, and terminal state. The oracle consumed all 171 events through
9,112 PAL frames and reproduced the complete terminal state across
deterministic rerun and continuation restore.

Only `shared-amiga-calibration` appears in the authoritative and
generated-baseline corpora. `cold5.pfreplay.json` and earlier exploratory
journals are retained only as migration evidence and have no active authority.
