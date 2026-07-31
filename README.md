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
animations. Paula DMA audio is mixed deterministically, and Exec
`SetIntVector` audio handlers now advance/finish sample streams instead of
looping the last buffer and blocking foreground gameplay. Title and difficulty
screens render correctly, blank back buffers are no longer presented during
page flips, and graphics.library merged Copper lists execute from their real
instruction stream. Mid-scanline palette changes, sprite composition, blitter
line mode, full gameplay, and disk-2 progression have not yet been fully
verified.

Deterministic replay and Atlas workflows use the same launcher:

```powershell
python scripts\play.py --record-replay session
python scripts\play.py --snapshot amigasnap_YYYYMMDD_HHMMSS_fFRAME
python scripts\play.py --headless --steps 3000000 --snapshot amigasnap_YYYYMMDD_HHMMSS_fFRAME
python scripts\play.py --headless --steps 10000000 --replay-inputs smoke
python scripts\play.py --headless --steps 10000000 --replay-inputs smoke --update-atlas
```

Headless execution writes the run report, rendered PPM frame, and execution
evidence under `artifacts/amiga`. It restores a complete continuation and
requires the second run to match the first run's status, diagnostic, and
canonical state digest. Replays are bound to the pinned disk-1 SHA-256 and the
`pf-amiga-a500-ocs-pal-v3` machine profile. Recordings and snapshots from the
older cold-reset profile are intentionally rejected rather than relabeled,
because v3 models the display DMA and system-Copper state inherited from
AmigaDOS. The curated `cold5-v3` journal is an explicitly retimed migration
of the legacy PAL-v1 input timeline and is accepted as recovery authority only
after full oracle replay and canonical-rerun equality. F12 snapshots are stored under
`artifacts/snapshots` as `.pfamigasnapshot` files and can be resumed with the
same launcher. The pinned, call-ordered legacy-vector map in `game.json`
migrates only snapshot formats created before PortForge persisted exclusive
`SetIntVector` state; current snapshots carry the exact vector table directly,
including intentionally removed handlers.

Resident-code recovery uses the curated execution evidence without claiming a
generated whole-game runtime:

```powershell
python scripts\analyze.py
```

The command verifies both pinned ADFs and the evidence identity, writes the
resident M68000 lift plan to `artifacts/generated/amiga/lift-plan.json`, and
materializes the matching `pf-recovered-blocks-v1` Atlas source at
`artifacts/generated/amiga/blocks.json`. Overlay generations and unresolved
indirect transfers remain explicit recovery frontier items. Observed MANX
overlay loads are recovered independently under profile-and-generation-scoped
identities; those blocks remain evidence metadata until Atlas and generated
execution can preserve the same generation coordinate.

Build the machine-function evidence layer and inspect the next recovery
frontier with:

```powershell
python port_forge\tools\pf_project.py semantic .
python port_forge\tools\pf_project.py frontier . --limit 20
python port_forge\tools\pf_project.py context . amiga:012EAC
```

The semantic command first runs the complete curated replay through the
original M68000 oracle, regenerates the exact lift plan, and then derives
resident function boundaries only from the module entry and static or
observed calls. It writes provenance-bound function/CFG dossiers, explicitly
partial M68000 ABI cards, and instruction-cost histograms only for completed
captured calls under `artifacts/generated/semantic`. Register arguments,
clobbers, saved registers, stack arguments, and exit flags remain marked
unknown until the M68000 decoder has a read/write micro-op model; no empty
field is used to imply that an unknown effect does not exist.

The generated runtime is built and verified through the complete curated
`cold5-v3` replay with:

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
