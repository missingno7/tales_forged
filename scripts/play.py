#!/usr/bin/env python3
"""Run DuckTales through the current PortForge Amiga architecture.

Interactive play and human-authored ArtifactV2 recording use the viewer's
shared semantic live session. Headless recording remains available for fixed
test schedules; playback and verification are deterministic headless modes.
Anything after ``--`` is forwarded to the selected runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORT_FORGE = ROOT / "port_forge"
sys.path.insert(0, str(PORT_FORGE / "scripts"))
import player_runtime  # noqa: E402


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path}: expected a JSON object")
    return value


def verify_asset(facts: dict) -> Path:
    path = ROOT / "assets" / facts["file"]
    if not path.is_file():
        raise RuntimeError(f"missing {path}; see assets/README.md")
    if path.stat().st_size != facts["size"]:
        raise RuntimeError(f"{path.name}: size does not match game.json")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != facts["sha256"]:
        raise RuntimeError(f"{path.name}: SHA-256 does not match game.json")
    return path


def named_path(value: str, directory: Path, suffix: str) -> Path:
    path = Path(value)
    if path.parent == Path("."):
        path = directory / path
    if not path.suffix:
        path = path.with_name(path.name + suffix)
    return path.resolve()


def target_options(selection: player_runtime.PlayerSelection) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--steps", type=int, default=50_000_000)
    parser.add_argument("--no-verify", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--replay-artifact")
    parser.add_argument("--record-artifact")
    parser.add_argument("--input-schedule")
    parser.add_argument("--snapshot")
    parser.add_argument("--update-atlas", action="store_true")
    parser.add_argument("--live-atlas", nargs="?", const="__project_atlas__")
    parser.add_argument("--atlas-interval", type=int, default=1)
    try:
        options = parser.parse_args(selection.adapter_args)
    except SystemExit as error:
        raise player_runtime.PlayerConfigError(
            "invalid DuckTales player options; use --help"
        ) from error
    if options.steps < 1:
        raise player_runtime.PlayerConfigError("--steps must be positive")
    if options.atlas_interval < 1:
        raise player_runtime.PlayerConfigError(
            "--atlas-interval must be positive"
        )
    if options.replay_artifact and options.record_artifact:
        raise player_runtime.PlayerConfigError(
            "playback and recording are mutually exclusive"
        )
    if options.input_schedule and not options.record_artifact:
        raise player_runtime.PlayerConfigError(
            "--input-schedule requires --record-artifact"
        )
    return options


def require_generated_verification() -> None:
    path = ROOT / "artifacts/generated/amiga/verification.json"
    value = load_json(path)
    replay = ROOT / "artifacts/replays/cold5.pfreplay.json"
    boundary = ROOT / "profiles/replay-boundaries-v1.json"
    plan = ROOT / "artifacts/execution-plans/generated-plus-fallback.json"
    header = ROOT / "artifacts/generated/amiga/ducktales_amiga_gen.hpp"
    terminal = load_json(replay).get("terminal", {})
    inputs = value.get("inputs")
    if (
        value.get("format") != "portforge-amiga-generated-verification-v2"
        or value.get("equivalent") is not True
        or value.get("replay_artifact")
        != "artifacts/replays/cold5.pfreplay.json"
        or value.get("replay_artifact_sha256")
        != hashlib.sha256(replay.read_bytes()).hexdigest()
        or value.get("replay_terminal_canonical_sha256")
        != terminal.get("canonical_sha256")
        or not isinstance(inputs, dict)
        or inputs.get("replay")
        != hashlib.sha256(replay.read_bytes()).hexdigest()
        or inputs.get("boundary_profile")
        != hashlib.sha256(boundary.read_bytes()).hexdigest()
        or inputs.get("generated_plan")
        != hashlib.sha256(plan.read_bytes()).hexdigest()
        or inputs.get("generated_header")
        != hashlib.sha256(header.read_bytes()).hexdigest()
    ):
        raise player_runtime.PlayerConfigError(
            "generated runtime verification is absent or stale; run "
            "python scripts/build_generated.py"
        )


def main(argv: list[str] | None = None) -> int:
    source = list(sys.argv[1:] if argv is None else argv)
    if player_runtime.help_requested(source):
        print(player_runtime.render_help(__doc__))
        return 0
    selection = player_runtime.select_runtime(ROOT, source)
    if selection.runtime not in {"oracle", "generated"}:
        raise player_runtime.PlayerConfigError(
            f"unsupported DuckTales runtime: {selection.runtime}"
        )
    options = target_options(selection)
    cfg = load_json(ROOT / "game.json")
    program = cfg["program"]
    companion = cfg["companion_assets"]["disk2"]
    disk1 = ROOT / "assets" / program["file"]
    disk2 = ROOT / "assets" / companion["file"]
    explicit_steps = any(
        item == "--steps" or item.startswith("--steps=")
        for item in selection.adapter_args
    )
    artifact_mode = bool(options.replay_artifact or options.record_artifact)
    scheduled_recording = bool(
        options.record_artifact and options.input_schedule
    )
    interactive = not (
        options.headless
        or options.update_atlas
        or explicit_steps
        or scheduled_recording
    )
    if options.live_atlas and not interactive:
        raise player_runtime.PlayerConfigError(
            "--live-atlas requires interactive play"
        )
    if options.snapshot and options.replay_artifact:
        raise player_runtime.PlayerConfigError(
            "ReplayArtifactV2 supplies its own exact base snapshot"
        )

    role = (
        "generated-plus-fallback"
        if selection.runtime == "generated"
        else "oracle-interpreter"
    )
    plan = ROOT / "artifacts" / "execution-plans" / f"{role}.json"
    if selection.runtime == "generated":
        runner = ROOT / "build" / (
            "ducktales_amiga_generated_view.exe"
            if interactive
            else "ducktales_amiga_generated_run.exe"
        )
    else:
        runner_name = "pf_amiga_view" if interactive else "pf_amiga_run"
        runner = PORT_FORGE / "build" / f"{runner_name}.exe"

    runner_options: list[str] = []
    if options.replay_artifact:
        replay = named_path(
            options.replay_artifact,
            ROOT / "artifacts/replays",
            ".pfreplay.json",
        )
        runner_options += [
            "--replay-artifact", str(replay),
            "--boundary-profile",
            str(ROOT / "profiles/replay-boundaries-v1.json"),
            "--implementation-plan", str(plan),
        ]
    if options.record_artifact:
        replay = named_path(
            options.record_artifact,
            ROOT / "artifacts/replays",
            ".pfreplay.json",
        )
        runner_options += [
            "--record-artifact", str(replay),
            "--boundary-profile",
            str(ROOT / "profiles/replay-boundaries-v1.json"),
            "--implementation-plan", str(plan),
        ]
    if options.input_schedule:
        runner_options += [
            "--input-schedule", str((ROOT / options.input_schedule).resolve())
        ]
    if options.snapshot:
        snapshot = named_path(
            options.snapshot,
            ROOT / "artifacts/snapshots",
            ".pfamigasnapshot",
        )
        runner_options += ["--snapshot", str(snapshot)]
    if options.live_atlas:
        atlas = (
            ROOT / "artifacts/atlas.pfatlas"
            if options.live_atlas == "__project_atlas__"
            else Path(options.live_atlas).resolve()
        )
        runner_options += [
            "--live-atlas", str(atlas),
            "--atlas-interval", str(options.atlas_interval),
        ]
    if interactive and not artifact_mode:
        runner_options += [
            "--boundary-profile",
            str(ROOT / "profiles/replay-boundaries-v1.json"),
            "--implementation-plan", str(plan),
        ]

    if not selection.dry_run:
        if options.no_verify:
            player_runtime.require_artifact(disk1, selection)
            player_runtime.require_artifact(disk2, selection)
        else:
            disk1 = verify_asset(program)
            disk2 = verify_asset(companion)
        if artifact_mode or interactive:
            player_runtime.require_artifact(plan, selection)
        if selection.runtime == "generated":
            if not selection.no_build:
                subprocess.run(
                    [sys.executable, "scripts/build_generated.py"],
                    check=True,
                    cwd=ROOT,
                )
            player_runtime.require_artifact(runner, selection)
            require_generated_verification()
        elif selection.no_build:
            player_runtime.require_artifact(runner, selection)
        else:
            subprocess.run(
                [
                    sys.executable,
                    "build.py",
                    "--no-tests",
                    "--targets",
                    runner_name,
                ],
                check=True,
                cwd=PORT_FORGE,
            )

    command = [
        str(runner), str(disk1), program["executable"],
        "--disk", str(disk2),
        "--vblank-signal", "0x2413e",
    ]
    if not interactive:
        command += [
            "--steps", str(options.steps),
            "--out", str(ROOT / "artifacts/amiga"),
            "--native" if selection.runtime == "generated" else "--oracle",
            "--strict",
        ]
    command += [*runner_options, *selection.runner_args]
    code = player_runtime.run_selected(
        selection,
        command,
        cwd=ROOT,
        identity=[
            f"program identity: sha256:{program['sha256']}",
            f"HUNK identity: sha256:{program['hunk_sha256']}",
            f"companion identity: sha256:{companion['sha256']}",
            f"execution plan: {role}",
            "replay authority: ReplayArtifactV2 + shared live session"
            if artifact_mode
            else "presentation: interactive semantic-session viewer",
        ],
    )
    if code == 0 and options.update_atlas and not selection.dry_run:
        subprocess.run(
            [
                sys.executable,
                str(PORT_FORGE / "tools/pf_project.py"),
                "atlas", str(ROOT), "ingest-evidence",
                str(ROOT / "artifacts/amiga/ducktales-evidence.json"),
            ],
            check=True,
            cwd=ROOT,
        )
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        RuntimeError,
        player_runtime.PlayerConfigError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"play.py: {error}", file=sys.stderr)
        raise SystemExit(1)
