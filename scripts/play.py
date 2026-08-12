#!/usr/bin/env python3
"""Run and inspect DuckTales through the shared PortForge architecture.

Plain invocation selects ``oracle``. Use ``--runtime generated`` for the
faster replay-derived AOT backend used on instruction-heavy 3D screens.

Interactive controls:
  F10                     save the currently published frame as a screenshot
  F11                     start/finish an ArtifactV2 recording
  F12                     publish a resumable machine + replay-session snapshot

Play and recording:
  --record-replay [NAME]  record ArtifactV2 under artifacts/replays/;
                          omit NAME for a timestamped interactive recording
  --play-replay NAME      play ArtifactV2 interactively
  --verify-replay NAME    replay twice headlessly with strict verification
  --headless              use the deterministic non-interactive runner
  --input-schedule PATH   fixed semantic input source for headless recording
  --steps N               headless guest instruction budget (default: 50000000)

Snapshots and output:
  --snapshot NAME|PATH    resume a machine/session snapshot
  --snapshot-out NAME|PATH
                          publish a verified headless snapshot and session state
  --inspect-snapshot NAME|PATH
                          inspect and content-verify a session publication
  --verify-snapshot NAME|PATH
                          content-verify a session publication
  --capture-audio PATH    write canonical headless PCM as WAV

Atlas and replay operations:
  --live-atlas [PATH]     attach the project's Live Execution Atlas
  --atlas-interval N      publish an Atlas update every N frames
  --update-atlas          ingest this verified headless run's EvidenceV3
  --inspect-replay NAME   validate and summarize an ArtifactV2

Compatibility names ``--record-artifact`` and ``--replay-artifact`` are
accepted. ``--record-replay``, ``--play-replay``, and ``--replay-inputs`` map
only to ArtifactV2; no retired journal or legacy replay reader is restored.

Diagnostics:
  --no-verify             skip pinned ADF size and SHA-256 checks

Advanced arguments after ``--`` include viewer ``--mute`` and runner
``--peek``, ``--find-address``, ``--break-pc``, ``--fire0-at``,
``--fire0-release-at``, and ``--canonical-projections`` where that runner mode
supports them. Runner validation remains authoritative for combinations.

Anything after ``--`` is forwarded verbatim to the selected runner or shared
artifact tool.
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
from player_util import timestamp  # noqa: E402


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


def run_artifact_operation(
    selection: player_runtime.PlayerSelection,
    options: argparse.Namespace,
) -> int | None:
    command_name: str | None = None
    artifact: Path | None = None
    if options.inspect_replay:
        command_name = "inspect"
        artifact = named_path(
            options.inspect_replay,
            ROOT / "artifacts/replays",
            ".pfreplay.json",
        )
    elif options.inspect_snapshot or options.verify_snapshot:
        command_name = (
            "inspect-session" if options.inspect_snapshot
            else "verify-session"
        )
        snapshot = named_path(
            options.inspect_snapshot or options.verify_snapshot,
            ROOT / "artifacts/snapshots",
            ".pfamigasnapshot",
        )
        artifact = Path(str(snapshot) + ".pfsession.json")
    if command_name is None or artifact is None:
        return None

    tool = PORT_FORGE / "build" / "pf_artifact.exe"
    if not selection.dry_run:
        player_runtime.require_artifact(artifact, selection)
        if selection.no_build:
            player_runtime.require_artifact(tool, selection)
        else:
            subprocess.run(
                [
                    sys.executable,
                    "build.py",
                    "--no-tests",
                    "--targets",
                    "pf_artifact",
                ],
                check=True,
                cwd=PORT_FORGE,
            )
    return player_runtime.run_selected(
        selection,
        [str(tool), command_name, str(artifact), *selection.runner_args],
        cwd=ROOT,
        identity=[
            "operation: shared ArtifactV2/session publication "
            + command_name,
            f"artifact: {artifact}",
            "authority: common PortForge replay contracts",
        ],
    )


def target_options(selection: player_runtime.PlayerSelection) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--steps", type=int, default=50_000_000)
    parser.add_argument("--no-verify", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--play-replay", "--replay-artifact", "--replay-inputs",
        dest="replay_artifact",
    )
    parser.add_argument(
        "--record-replay", "--record-artifact",
        dest="record_artifact",
        nargs="?",
        const="",
    )
    parser.add_argument("--verify-replay")
    parser.add_argument("--inspect-replay")
    parser.add_argument("--input-schedule")
    parser.add_argument("--snapshot")
    parser.add_argument("--snapshot-out")
    parser.add_argument("--inspect-snapshot")
    parser.add_argument("--verify-snapshot")
    parser.add_argument("--capture-audio")
    parser.add_argument("--update-atlas", action="store_true")
    parser.add_argument("--live-atlas", nargs="?", const="__project_atlas__")
    parser.add_argument("--atlas-interval", type=int, default=1)
    try:
        options = parser.parse_args(selection.adapter_args)
    except SystemExit as error:
        raise player_runtime.PlayerConfigError(
            "invalid DuckTales player options; use --help"
        ) from error
    if options.record_artifact == "":
        options.record_artifact = f"rec_{timestamp()}"
    if options.steps < 1:
        raise player_runtime.PlayerConfigError("--steps must be positive")
    if options.atlas_interval < 1:
        raise player_runtime.PlayerConfigError(
            "--atlas-interval must be positive"
        )
    replay_modes = sum(bool(value) for value in (
        options.replay_artifact,
        options.verify_replay,
        options.inspect_replay,
    ))
    if replay_modes > 1:
        raise player_runtime.PlayerConfigError(
            "playback, verification, and inspection are mutually exclusive"
        )
    operations = sum(bool(value) for value in (
        options.inspect_replay,
        options.inspect_snapshot,
        options.verify_snapshot,
    ))
    if operations > 1:
        raise player_runtime.PlayerConfigError(
            "only one inspection operation may be selected"
        )
    if operations and any((
        options.record_artifact,
        options.replay_artifact,
        options.verify_replay,
        options.snapshot,
        options.snapshot_out,
        options.input_schedule,
        options.update_atlas,
        options.live_atlas,
    )):
        raise player_runtime.PlayerConfigError(
            "inspection operations cannot be combined with execution"
        )
    if options.verify_replay:
        options.replay_artifact = options.verify_replay
        options.headless = True
    if options.replay_artifact and options.record_artifact:
        raise player_runtime.PlayerConfigError(
            "playback and recording are mutually exclusive"
        )
    if options.input_schedule and not options.record_artifact:
        raise player_runtime.PlayerConfigError(
            "--input-schedule requires --record-artifact"
        )
    if options.snapshot_out:
        options.headless = True
        if not (options.replay_artifact or options.record_artifact):
            raise player_runtime.PlayerConfigError(
                "--snapshot-out requires ArtifactV2 playback or recording "
                "so replay-session state can be published"
            )
    if options.capture_audio:
        options.headless = True
    return options


def require_generated_verification() -> None:
    path = ROOT / "artifacts/generated/amiga/verification.json"
    value = load_json(path)
    replay = (
        ROOT
        / "artifacts/replays/shared-amiga-calibration.pfreplay.json"
    )
    boundary = ROOT / "profiles/replay-boundaries-v1.json"
    plan = ROOT / "artifacts/execution-plans/generated-plus-fallback.json"
    header = ROOT / "artifacts/generated/amiga/ducktales_amiga_gen.hpp"
    terminal = load_json(replay).get("terminal", {})
    inputs = value.get("inputs")
    if (
        value.get("format") != "portforge-amiga-generated-verification-v2"
        or value.get("equivalent") is not True
        or value.get("replay_artifact")
        != "artifacts/replays/shared-amiga-calibration.pfreplay.json"
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
    operation_result = run_artifact_operation(selection, options)
    if operation_result is not None:
        return operation_result
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
    if options.snapshot_out:
        snapshot_out = named_path(
            options.snapshot_out,
            ROOT / "artifacts/snapshots",
            ".pfamigasnapshot",
        )
        runner_options += ["--snapshot-out", str(snapshot_out)]
    if options.capture_audio:
        audio = named_path(
            options.capture_audio,
            ROOT / "artifacts/audio",
            ".wav",
        )
        runner_options += ["--audio-wav", str(audio)]
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
