# DuckTales replay evidence authority

`artifacts/replays/cold5-v1.legacy.json` is the preserved legacy recovery
corpus. It is a historical prefix of the user-recorded `cold5.json`; the
non-runnable extension keeps PortForge validation from mistaking its v1
envelope for a current replay. The legacy journal ends at event 163, the
last input consumed before the corrected
audio-interrupt runtime exits deterministically. The seven later raw events
were attempts to advance the formerly frozen build and are deliberately
outside recovery authority; the original `cold5.json` remains untouched.

`artifacts/replays/cold5-v3.pfreplay.json` is the v3 recovery corpus. The
migration tool scales every event tick by the exact PAL line-clock ratio
1816/910, upgrades the replay envelope to v2, and binds the complete v3 launch
identity. The source journal is never rewritten. A migrated file becomes
authority only after the strict M68000 oracle consumes every event and a
second run reaches the same status, diagnostic, and canonical state digest.

The older `cold`, `cold2`, `cold4`, `menu-input`, `smoke`, `title-fire`, and
`title-space` journals remain useful exploratory recordings, but they are not
recovery authority. They are deliberately excluded from `corpora.recovery`
because they stop earlier, exercise superseded input handling, or do not reach
the map/Launchpad path covered by `cold5-v3`.

Replay v2 binds the ordered DT1/DT2 media set, direct-HUNK bootstrap, machine
model, VBlank compatibility address, CLI arguments, and current launch
descriptor through `launch_sha256`. It still has no terminal condition or
periodic canonical checkpoints, so the project verification gate supplies an
explicit instruction budget and compares the terminal canonical state. This
is evidence for the curated path, not permission to infer whole-game closure.
