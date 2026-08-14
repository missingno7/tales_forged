# DuckTales Amiga — PortForge project

DuckTales runs through PortForge's A500 OCS PAL runtime with both pinned ADFs,
direct-HUNK bootstrap, deterministic Paula audio, AmigaDOS services, MANX
overlays, Copper/blitter execution, and an explicit Port 2 input model.
The current machine identity is `pf-amiga-a500-ocs-pal-v23`; DuckTales' first
HUNK is CHIP-flagged and LoadSeg places its executable data at `amiga:010008`.

```powershell
python scripts\play.py
```

Interactive play uses the oracle viewer. Press Space or Enter at the title,
use the arrow keys for the joystick, Enter or Ctrl for fire, F10 for a
screenshot, F11 to start or finish an ArtifactV2 recording, F12 for a
continuation-bound snapshot, and Escape to quit. The verified path covers the title,
difficulty menu, story, map selection, and entry into the Launchpad travel
sequence. Later minigames, disk-2 progression, mid-scanline display changes,
sprite composition, and blitter line mode remain open verification work.

## Complete player interface

`python scripts\play.py --help` is the authoritative workflow inventory. The
launcher exposes interactive and headless ArtifactV2 recording/playback,
strict replay verification, replay/session inspection, snapshot resume and
publication, Live Atlas, evidence ingestion, canonical audio capture, runtime
selection, build control, and asset verification. Arguments after `--` are
forwarded unchanged to the selected viewer, runner, or shared artifact tool.
This retains low-level `--mute`, memory peek/address search, PC breakpoint,
synthetic fire-event, and canonical-projection diagnostics without making the
launcher reinterpret them.

The preferred replay names are `--record-replay` and `--play-replay`.
`--record-artifact`, `--replay-artifact`, and historical `--replay-inputs` are
clean aliases for ArtifactV2 only; no journal or retired replay loader exists.

## Replay authority

The curated corpus is `artifacts/replays/shared-amiga-calibration.pfreplay.json`, a bound
ReplayArtifactV2. The Amiga adapter exposes stable input-dispatch and VBlank
points from `profiles/replay-boundaries-v1.json`; ReplaySession owns boundary
ordinals, event/checkpoint cursors, continuation state, and terminal policy.
Artifact mode always requires a content-bound execution plan.

The historical `cold5` replay binds the retired machine timeline and remains
migration evidence only. Its separately preserved 171-event absolute-time
schedule is a neutral recording source: the current
`shared-amiga-calibration` artifact was freshly recorded from a v16 launch,
then translated to semantic boundary events. No retired snapshot, checkpoint,
or terminal digest is accepted as authority.

```powershell
python scripts\play.py --play-replay shared-amiga-calibration
python scripts\play.py --verify-replay shared-amiga-calibration
python scripts\play.py --record-replay my-playthrough
python scripts\play.py --headless --record-replay session `
  --input-schedule recovery/migration/cold5-input-schedule-v1.json
python scripts\play.py --inspect-replay shared-amiga-calibration
```

Interactive recording commits human input only when it becomes guest-visible
at the adapter's semantic input point. Headless recording consumes the neutral,
absolute-time input schedule only as a one-way test source and emits the same
semantic replay events. Playback rejects stale media, launch,
machine, boundary-profile, channel, plan, checkpoint, or continuation
identities. A passing run consumes all events and proves deterministic rerun,
machine/session snapshot roundtrip, canonical checkpoint equality, and
canonical-audio equality. Headless reports and EvidenceV3 are written beneath
`artifacts/amiga`.

The viewer is a host frontend, not a machine scheduler: it presents frames and
PCM already produced by the shared Amiga adapter and wall-clock throttles that
presentation. ReplaySession/live-session state owns committed input and replay
cursors. Snapshot safety means an exact, serializable continuation at a
declared semantic point, not global device inactivity; F12 writes the gameplay
snapshot together with an identity-bound `.pfsession.json` publication.
F12 works during ordinary play, recording, and playback. Recording
publications include the content-bound ArtifactV2 builder/session draft and
original base snapshot; playback publications content-bind the immutable
artifact attachment and exact playback continuation.

Snapshot and diagnostic workflows use the same launcher:

```powershell
python scripts\play.py --snapshot amigasnap_YYYYMMDD_HHMMSS_fFRAME
python scripts\play.py --verify-replay shared-amiga-calibration --snapshot-out verified-amiga
python scripts\play.py --inspect-snapshot verified-amiga
python scripts\play.py --verify-snapshot verified-amiga
python scripts\play.py --verify-replay shared-amiga-calibration --capture-audio shared-amiga
```

`--snapshot-out` is published only after the headless deterministic rerun and
snapshot roundtrip pass. Session inspection validates all attachment hashes;
it does not execute or mutate a replay.

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
python scripts\play.py --live-atlas
python scripts\play.py --live-atlas --atlas-interval 3
python scripts\play.py --verify-replay shared-amiga-calibration --update-atlas
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
