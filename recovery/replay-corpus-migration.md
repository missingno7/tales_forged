# DuckTales replay corpus provenance

`recovery/migration/cold5-input-schedule-v1.json` preserves the selected 171
host-input transitions from the historical recovery work in a neutral
`amiga.master-tick` schedule. It is a recording source, not a replay artifact,
checkpoint oracle, or Atlas source.

`artifacts/replays/cold5.pfreplay.json` was freshly recorded from that schedule
through the Amiga ReplaySession adapter. It binds the ordered DT1/DT2 media,
direct-HUNK launch, A500 OCS PAL machine profile, semantic boundary profile,
exact base snapshot, supported channels, canonical checkpoints, and terminal
state. The oracle consumed all 171 events and reproduced the complete terminal
state across deterministic rerun and continuation restore.

Only this ArtifactV2 appears in the recovery and generated-baseline corpora.
Earlier exploratory journals are available from repository history and have no
active authority.
