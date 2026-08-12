# Amiga reference validation

PortForge replay verification proves repeatability, not hardware correctness.
The independent reference for A500 work is a pinned WinUAE A500 PAL
cycle-exact run using the same disk images.  A valid calibration case consists
of all of these files:

- `manifest.json`, including hashes of WinUAE, Kickstart, both ADFs, and the
  generated configuration;
- WinUAE's re-recorder `.inp` and paired startup `.uss`;
- one unfiltered screenshot for every emulated PAL frame;
- uncompressed 44.1 kHz stereo WAV;
- the corresponding PortForge ArtifactV2 recording, frame dump, and canonical
  WAV;
- the JSON comparison report.

The WinUAE state is not converted from a PortForge snapshot. Each emulator
must reach the scenario independently; otherwise the test is not an
independent oracle.

## 1. Prepare the reference machine

Use a licensed, verified Kickstart 1.3 ROM. The ROM installed on this machine
is named as a hacked `Guardian` image and the preparation tool deliberately
rejects it for authoritative captures.

```powershell
python scripts/amiga_reference.py prepare `
  --rom "D:\Amiga\ROMs\kick13.rom" `
  --output artifacts/reference/winuae
```

The command verifies the pinned ADF hashes and creates an A500/OCS/PAL
cycle-exact `.uae` file plus the provenance manifest. Launch the printed
WinUAE command. Do not add hard drives, JIT, accelerated CPU modes, or
immediate blits.

WinUAE's own re-recorder requirements are important: start with the `A500 most
compatible` Quickstart configuration, and vary only chipset, drive count,
memory, and Kickstart. Its `.inp` playback is paired with a `.uss` and detects
even a one-clock desynchronization.

## 2. Record scenario anchors

Create separate cases for `office-blink`, `flight-pacing`, and `cave-pacing`.
For each case:

1. Reach the scene in WinUAE, stop providing input at a visually unambiguous
   frame, and begin a re-recorder capture.
2. Save the recording so WinUAE emits its paired `.inp`, `.uss`, and disk
   copies.
3. Replay that pair. During playback enable continuous screenshots (one per
   emulated frame, capture before filtering) and uncompressed WAV recording.
4. Capture at least 600 PAL frames. A no-input interval is preferred because
   it avoids host keyboard timestamp ambiguity while still exposing flight
   scrolling, timers, animation cadence, and one-frame disappearances.

For a controlled-input case, describe inputs by frame relative to the first
captured frame (`100: left down`, `140: left up`, and so on). Record the same
relative schedule into a new PortForge artifact. Keep the raw WinUAE `.inp` as
the authority for repeatability on the reference side.

## 3. Capture PortForge frames

New captures must be recorded after the hardware-model change; older
snapshots and replays contain the retired synthetic VBlank-memory behavior.
The viewer and headless runner accept `--frame-dump` after `--`:

```powershell
python scripts/play.py --record-replay flight-reference -- `
  --frame-dump artifacts/reference/portforge/flight-live

python scripts/play.py --verify-replay flight-reference `
  --capture-audio artifacts/reference/portforge/flight.wav -- `
  --frame-dump artifacts/reference/portforge/flight
```

The dump filenames contain the absolute PortForge PAL frame ordinal. The
comparison uses sequence order, so the two emulators do not need matching
absolute frame numbers.

## 4. Compare measurements

WinUAE usually captures the full overscan area while PortForge currently emits
the 320x200 game presentation. Supply the measured WinUAE crop before resizing;
do not choose a crop that hides a discrepancy.

```powershell
python scripts/amiga_reference.py compare `
  --portforge-frames artifacts/reference/portforge/flight `
  --winuae-frames artifacts/reference/winuae/flight/frames `
  --winuae-crop 320x200+X+Y `
  --portforge-wav artifacts/reference/portforge/flight.wav `
  --winuae-wav artifacts/reference/winuae/flight/flight.wav `
  --output artifacts/reference/flight-comparison.json
```

The report records frame counts and PAL durations, consecutive duplicate
frames, per-frame pixel activity, a bounded constant-offset alignment, WAV
duration/rate/peak/silence, and rolling hashes. The useful pass conditions are:

- the same game events occur at the same aligned PAL frame;
- animation and movement have the same changed-frame cadence;
- no isolated PortForge-only blank/masked frame exists;
- WAV duration follows the same emulated interval and the PortForge canonical
  audio timeline has zero discontinuities;
- repeating either side produces the same sequence again.

Pixel hashes need not match when borders or palette conversion differ. A
large or changing alignment offset, different event frame, unexpected
duplicate-frame run, or one-sided transient is a failure even when the final
screenshots look similar.
