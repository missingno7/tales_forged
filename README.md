# DuckTales Amiga — PortForge project

This project follows the standard PortForge launcher convention:

```powershell
python scripts\play.py
```

The command verifies both pinned ADFs, incrementally builds the Amiga runtime,
mounts `DT1` and `DT2`, and opens the interactive player. Press Space or Enter
to leave the title screen. Use the arrow keys for the required Amiga Port 2
joystick, Enter or Ctrl for the primary action, F11 to toggle deterministic
replay recording, F12 to save a continuation snapshot, and Escape to quit.

The original M68K game now recognizes both disks and runs past the former
`INSERT DISK 1` blocker. The verified playable path includes:

- the full-color title screen;
- Space-key input through the original `input.device` handler;
- loading additional data from `DT1:MAIN.ARC`;
- the difficulty menu, joystick navigation, and fire selection;
- the original story sequence;
- map navigation, destination selection, and entry into the Launchpad travel
  sequence.

The runtime implements the AmigaDOS volume list used by the game, multi-ADF
file access, MANX overlays, the required 68000 instructions, graphics.library
planar operations, and the block-mode OCS blitter used for moving objects and
animations. Title and difficulty screens render correctly, and blank back
buffers are no longer presented during page flips. Copper execution, blitter
line mode, later palette fidelity, full gameplay, and disk-2 progression have
not yet been fully verified.

Deterministic replay and Atlas workflows use the same launcher:

```powershell
python scripts\play.py --record-replay session
python scripts\play.py --snapshot amigasnap_YYYYMMDD_HHMMSS_fFRAME
python scripts\play.py --headless --steps 10000000 --replay-inputs smoke
python scripts\play.py --headless --steps 10000000 --replay-inputs smoke --update-atlas
```

Headless execution writes the run report, rendered PPM frame, and execution
evidence under `artifacts/amiga`. It restores a complete continuation and
requires the second run to match the first run's status, diagnostic, and
canonical state digest. Replays are bound to the pinned disk-1 SHA-256 and the
`a500-ocs-pal` machine profile. F12 snapshots are stored under
`artifacts/snapshots` as `.pfamigasnapshot` files and can be resumed with the
same launcher.

Resident-code recovery uses the curated execution evidence without claiming a
generated whole-game runtime:

```powershell
python scripts\analyze.py
```

The command verifies both pinned ADFs and the evidence identity, writes the
resident M68000 lift plan to `artifacts/generated/amiga/lift-plan.json`, and
materializes the matching `pf-recovered-blocks-v1` Atlas source at
`artifacts/generated/amiga/blocks.json`. Overlay generations and unresolved
indirect transfers remain explicit recovery frontier items.

The generated runtime is built and verified through the complete curated
`cold5` replay with:

```powershell
python scripts\build_generated.py
python scripts\play.py --runtime generated
```

The build regenerates the lift plan, emits exact-source-byte-guarded M68000
hooks, compiles headless and interactive runners, and requires the generated
subset plus observable interpreter/SMC fallback to finish with the same
canonical state as the M68000 oracle. It is an evidence-bounded hybrid
runtime, not a claim that every instruction or overlay has been lifted.

Rebuild both dynamic and recovered-static Execution Atlas data atomically:

```powershell
python scripts\rebuild_atlas.py
python scripts\play.py --live-atlas
```

The rebuild recollects the authoritative oracle profile, regenerates recovered
blocks, and replaces the Atlas only after all replay, media, identity, and
provenance gates pass. `--live-atlas` opens a second window showing current,
visited, historical, and static-only code while the game runs.
