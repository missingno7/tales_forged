# DuckTales replay evidence authority

`artifacts/replays/cold5.pfreplay.json` is the initial recovery corpus. It is
a standard-named prefix of the user-recorded `cold5.json` journal and is bound
to the pinned DT1 image and A500 OCS PAL machine model by the Amiga replay
loader. The prefix ends at event 163, the last input consumed before the
corrected audio-interrupt runtime exits deterministically. The seven later raw
events were attempts to advance the formerly frozen build and are deliberately
outside recovery authority; the original `cold5.json` remains untouched.

The older `cold`, `cold2`, `cold4`, `menu-input`, `smoke`, `title-fire`, and
`title-space` journals remain useful exploratory recordings, but they are not
recovery authority. They are deliberately excluded from `corpora.recovery`
because they stop earlier, exercise superseded input handling, or do not reach
the map/Launchpad path covered by `cold5`.

The replay is still a version-1 input journal. It does not yet contain
periodic canonical checkpoints, the companion DT2 identity, or a terminal
condition. Until an Amiga replay-v2 migration is complete, corpus verification
must bind the deterministic direct-HUNK bootstrap, both pinned ADFs,
`game.json`, the machine model, and the current PortForge producer revision
externally. This limitation is evidence metadata, not permission to infer
whole-game closure.
