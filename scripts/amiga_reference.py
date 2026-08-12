#!/usr/bin/env python3
"""Prepare and compare reproducible A500 PAL reference captures.

WinUAE remains an independent oracle: this tool never converts PortForge
snapshots into WinUAE state.  It pins the emulator, ROM, and disk identities,
generates the required cycle-exact configuration, and compares independently
captured frame/audio sequences.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import wave
from array import array
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISK1 = ROOT / "assets" / "Duck Tales - The Quest for Gold (1989)(Disney Software)(Disk 1 of 2).adf"
DISK2 = ROOT / "assets" / "Duck Tales - The Quest for Gold (1989)(Disney Software)(Disk 2 of 2).adf"
EXPECTED_MEDIA = {
    "disk1": "8de0c89b541ca88c5c6754a2fd5b143231725041cd685d2efae1a2d629e2d968",
    "disk2": "7514f17734463e78ba16b39e454075f83d919bcace431c081570de88faf8259d",
}
PAL_FRAME_RATE = 28_375_160 / (312 * 1816)
FRAME_SUFFIXES = {".ppm", ".png", ".bmp", ".tif", ".tiff"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_file(path: Path, label: str) -> Path:
    path = path.resolve()
    if not path.is_file():
        raise SystemExit(f"{label} is absent: {path}")
    return path


def quote_config(path: Path) -> str:
    return str(path).replace("\\", "/")


def prepare(args: argparse.Namespace) -> int:
    winuae = require_file(args.winuae, "WinUAE executable")
    rom = require_file(args.rom, "Kickstart ROM")
    disk1 = require_file(args.disk1, "disk 1")
    disk2 = require_file(args.disk2, "disk 2")
    if sha256(disk1) != EXPECTED_MEDIA["disk1"]:
        raise SystemExit("disk 1 does not match the project-pinned ADF")
    if sha256(disk2) != EXPECTED_MEDIA["disk2"]:
        raise SystemExit("disk 2 does not match the project-pinned ADF")
    if rom.stat().st_size not in (262144, 524288):
        raise SystemExit("A500 Kickstart ROM must be 256 KiB or 512 KiB")
    lowered = rom.name.lower()
    modified_marker = any(marker in lowered for marker in ("[h ", "[b ", "[o "))
    if modified_marker and not args.allow_modified_rom:
        raise SystemExit(
            "the selected ROM is explicitly marked hacked/bad/overdumped; "
            "use a licensed, verified Kickstart 1.3 ROM (or pass "
            "--allow-modified-rom only for a non-authoritative experiment)"
        )

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    frames = output / "frames"
    audio = output / "audio"
    frames.mkdir(exist_ok=True)
    audio.mkdir(exist_ok=True)
    config = output / "ducktales-a500-pal-cycle-exact.uae"
    config.write_text(
        "\n".join(
            (
                "config_description=DuckTales independent A500 PAL oracle",
                "config_hardware=true",
                "config_host=true",
                # WinUAE's re-recorder requires this exact Quickstart base.
                "quickstart=A500,0",
                f"kickstart_rom_file={quote_config(rom)}",
                "chipset=ocs",
                "chipset_compatible=A500",
                "nr_floppies=2",
                "floppy0type=0",
                "floppy1type=0",
                f"floppy0={quote_config(disk1)}",
                f"floppy1={quote_config(disk2)}",
                "chipmem_size=1",
                "bogomem_size=2",
                "use_gui=yes",
                "sound_output=exact",
                "sound_frequency=44100",
                "sound_channels=stereo",
                "collision_level=full",
                "show_leds=false",
                "filesystem2=",
                "hardfile2=",
                "",
            )
        ),
        encoding="utf-8",
        newline="\n",
    )
    manifest = {
        "format": "portforge-amiga-reference-manifest-v1",
        "authoritative": not modified_marker,
        "machine": {
            "model": "A500",
            "video": "PAL",
            "chipset": "OCS",
            "cpu": "MC68000 cycle-exact",
            "chip_ram_bytes": 524288,
            "slow_ram_bytes": 524288,
        },
        "winuae": {"path": str(winuae), "sha256": sha256(winuae)},
        "kickstart": {
            "path": str(rom),
            "sha256": sha256(rom),
            "bytes": rom.stat().st_size,
            "modified_marker": modified_marker,
        },
        "media": [
            {"path": str(disk1), "sha256": sha256(disk1)},
            {"path": str(disk2), "sha256": sha256(disk2)},
        ],
        "config": {"path": str(config), "sha256": sha256(config)},
        "capture": {
            "input": "WinUAE re-recorder .inp paired with its .uss state",
            "video": "continuous screenshot, one image per emulated frame",
            "audio": "uncompressed 44100 Hz stereo WAV",
            "required_start": "scenario-specific .uss, before the first compared input",
        },
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"config: {config}")
    print(f"manifest: {manifest_path}")
    print(f"launch: \"{winuae}\" -f \"{config}\"")
    return 0


def frame_files(directory: Path) -> list[Path]:
    files = sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in FRAME_SUFFIXES
    )
    if not files:
        raise SystemExit(f"no frame images found in {directory}")
    return files


def ppm_rgb(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    if not data.startswith(b"P6"):
        raise ValueError("not a binary PPM")
    at = 2
    tokens: list[bytes] = []
    while len(tokens) < 3:
        while at < len(data) and chr(data[at]).isspace():
            at += 1
        if at < len(data) and data[at] == ord("#"):
            at = data.find(b"\n", at) + 1
            continue
        end = at
        while end < len(data) and not chr(data[end]).isspace():
            end += 1
        tokens.append(data[at:end])
        at = end
    while at < len(data) and chr(data[at]).isspace():
        at += 1
    width, height, maximum = map(int, tokens)
    if maximum != 255 or len(data) - at != width * height * 3:
        raise ValueError(f"unsupported PPM layout: {path}")
    return width, height, data[at:]


def normalized_rgb(
    path: Path, size: tuple[int, int], crop: str | None, magick: str
) -> bytes:
    if path.suffix.lower() == ".ppm" and crop is None:
        width, height, rgb = ppm_rgb(path)
        if (width, height) == size:
            return rgb
    executable = shutil.which(magick)
    if not executable:
        raise SystemExit(
            f"ImageMagick '{magick}' is required for crop/resize or non-PPM frames"
        )
    command = [executable, str(path), "-alpha", "off"]
    if crop:
        command += ["-crop", crop, "+repage"]
    command += ["-filter", "point", "-resize", f"{size[0]}x{size[1]}!", "rgb:-"]
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE)
    expected = size[0] * size[1] * 3
    if len(result.stdout) != expected:
        raise SystemExit(f"ImageMagick returned {len(result.stdout)} bytes, expected {expected}")
    return result.stdout


def series_metrics(frames: list[bytes]) -> dict[str, object]:
    hashes = [hashlib.sha256(frame).hexdigest() for frame in frames]
    changes = [
        sum(left != right for left, right in zip(frames[index - 1], frames[index]))
        for index in range(1, len(frames))
    ]
    return {
        "frames": len(frames),
        "duration_seconds_at_pal": len(frames) / PAL_FRAME_RATE,
        "unique_frames": len(set(hashes)),
        "consecutive_duplicates": sum(
            hashes[index] == hashes[index - 1] for index in range(1, len(hashes))
        ),
        "changed_rgb_bytes": {
            "minimum": min(changes, default=0),
            "maximum": max(changes, default=0),
            "mean": sum(changes) / len(changes) if changes else 0.0,
        },
        "rolling_sha256": hashlib.sha256("".join(hashes).encode("ascii")).hexdigest(),
    }


def mean_abs_error(left: bytes, right: bytes) -> float:
    return sum(abs(a - b) for a, b in zip(left, right)) / min(len(left), len(right))


def best_alignment(left: list[bytes], right: list[bytes], radius: int) -> dict[str, object]:
    best: tuple[float, int, int] | None = None
    best_key: tuple[float, int, int] | None = None
    for offset in range(-radius, radius + 1):
        left_start = max(0, -offset)
        right_start = max(0, offset)
        count = min(len(left) - left_start, len(right) - right_start, 180)
        if count <= 0:
            continue
        error = sum(
            mean_abs_error(left[left_start + i], right[right_start + i])
            for i in range(count)
        ) / count
        candidate = (error, offset, count)
        candidate_key = (error, abs(offset), offset)
        if best_key is None or candidate_key < best_key:
            best = candidate
            best_key = candidate_key
    if best is None:
        raise SystemExit("frame sequences do not overlap")
    return {"winuae_minus_portforge_frames": best[1], "mean_rgb_error": best[0], "sampled_frames": best[2]}


def wav_metrics(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        width = source.getsampwidth()
        rate = source.getframerate()
        count = source.getnframes()
        raw = source.readframes(count)
    if width != 2:
        raise SystemExit(f"only signed 16-bit WAV is supported: {path}")
    samples = array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "channels": channels,
        "rate": rate,
        "frames": count,
        "duration_seconds": count / rate,
        "peak": max((abs(value) for value in samples), default=0),
        "silent_sample_ratio": sum(value == 0 for value in samples) / max(1, len(samples)),
    }


def compare(args: argparse.Namespace) -> int:
    size = tuple(map(int, args.size.lower().split("x", 1)))
    pf_paths = frame_files(args.portforge_frames.resolve())
    wu_paths = frame_files(args.winuae_frames.resolve())
    pf_frames = [normalized_rgb(path, size, args.portforge_crop, args.magick) for path in pf_paths]
    wu_frames = [normalized_rgb(path, size, args.winuae_crop, args.magick) for path in wu_paths]
    report = {
        "format": "portforge-amiga-reference-comparison-v1",
        "normalization": {
            "size": list(size),
            "portforge_crop": args.portforge_crop,
            "winuae_crop": args.winuae_crop,
            "filter": "nearest-neighbor",
        },
        "portforge": {
            "directory": str(args.portforge_frames.resolve()),
            "video": series_metrics(pf_frames),
            "audio": wav_metrics(args.portforge_wav),
        },
        "winuae": {
            "directory": str(args.winuae_frames.resolve()),
            "video": series_metrics(wu_frames),
            "audio": wav_metrics(args.winuae_wav),
        },
        "alignment": best_alignment(pf_frames, wu_frames, args.max_offset),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="pin media and generate WinUAE config")
    prep.add_argument("--winuae", type=Path, default=Path(r"C:\Program Files\WinUAE\winuae64.exe"))
    prep.add_argument("--rom", type=Path, required=True)
    prep.add_argument("--disk1", type=Path, default=DISK1)
    prep.add_argument("--disk2", type=Path, default=DISK2)
    prep.add_argument("--output", type=Path, default=ROOT / "artifacts" / "reference" / "winuae")
    prep.add_argument("--allow-modified-rom", action="store_true")
    prep.set_defaults(handler=prepare)

    comp = commands.add_parser("compare", help="measure two independent capture sequences")
    comp.add_argument("--portforge-frames", type=Path, required=True)
    comp.add_argument("--winuae-frames", type=Path, required=True)
    comp.add_argument("--portforge-wav", type=Path)
    comp.add_argument("--winuae-wav", type=Path)
    comp.add_argument("--portforge-crop")
    comp.add_argument("--winuae-crop")
    comp.add_argument("--size", default="320x200")
    comp.add_argument("--max-offset", type=int, default=150)
    comp.add_argument("--magick", default="magick")
    comp.add_argument("--output", type=Path, default=ROOT / "artifacts" / "reference" / "comparison.json")
    comp.set_defaults(handler=compare)
    return result


def main() -> int:
    args = parser().parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
