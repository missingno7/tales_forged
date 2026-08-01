# DuckTales Amiga — PortForge project

DuckTales runs through PortForge's A500 OCS PAL runtime with both pinned ADFs,
direct-HUNK bootstrap, deterministic Paula audio, AmigaDOS services, MANX
overlays, Copper/blitter execution, and an explicit Port 2 input model.

```powershell
python scripts\play.py
```

Interactive play uses the oracle viewer. Press Space or Enter at the title,
use the arrow keys for the joystick, Enter or Ctrl for fire, F12 for a local
continuation snapshot, and Escape to quit. The verified path covers the title,
difficulty menu, story, map selection, and entry into the Launchpad travel
sequence. Later minigames, disk-2 progression, mid-scanline display changes,
sprite composition, and blitter line mode remain open verification work.

## Replay authority

The curated corpus is `artifacts/replays/cold5.pfreplay.json`, a bound
ReplayArtifactV2. The Amiga adapter exposes stable input-dispatch and VBlank
points from `profiles/replay-boundaries-v1.json`; ReplaySession owns boundary
ordinals, event/checkpoint cursors, continuation state, and terminal policy.
Artifact mode always requires a content-bound execution plan.

```powershell
python scripts\play.py --headless --replay-artifact cold5
python scripts\play.py --headless --record-artifact session `
  --input-schedule recovery/migration/cold5-input-schedule-v1.json
```

Recording consumes the neutral, absolute-time input schedule only as a one-way
source and emits semantic replay events. Playback rejects stale media, launch,
machine, boundary-profile, channel, plan, checkpoint, or continuation
identities. A passing run consumes all events and proves deterministic rerun,
machine/session snapshot roundtrip, canonical checkpoint equality, and
canonical-audio equality. Headless reports and EvidenceV3 are written beneath
`artifacts/amiga`.

## Recovery and generated execution

```powershell
python scripts\analyze.py
python port_forge\tools\pf_project.py semantic .
python port_forge\tools\pf_project.py frontier . --limit 20
python scripts\build_generated.py
python scripts\play.py --runtime generated
```

Analysis verifies the pinned media and EvidenceV3 binding, writes the resident
M68000 lift plan, and projects recovered blocks without claiming overlay or
whole-program closure. The generated runtime contains exact-byte-guarded
instructions plus observable interpreter/SMC fallback. Its verification uses
separate `oracle-interpreter` and `generated-plus-fallback` execution plans and
requires the complete ArtifactV2 terminal canonical state.

## Atlas and architecture gates

```powershell
python scripts\rebuild_atlas.py
python port_forge\tools\pf_project.py validate .
python port_forge\tools\pf_project.py platform conformance .
```

Atlas v2 is a disposable evidence projection. `rebuild_atlas.py` recollects
EvidenceV3 through ReplaySession, regenerates recovered blocks, and ingests
both sources; Atlas never records, executes, or verifies replay. Atlas
production requires a clean committed PortForge revision so its provenance
binding is reproducible.

The implementation catalog under `recovery/implementation-catalog.json`
resolves immutable plans for both runtime roles. Their detachment reports make
the remaining interpreter, original-code/media, guest-memory, platform-service,
and PortForge runtime dependencies explicit; this project does not claim a
detached native product.
