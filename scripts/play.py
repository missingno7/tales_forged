#!/usr/bin/env python3
"""Run DuckTales through the project-declared PortForge Amiga runtime.

Plain invocation selects the manifest default (currently ``oracle``) and opens
the interactive player. Space continues from the title. Arrows are joystick
directions; Enter/Ctrl is fire. F11 toggles replay recording and F12 saves a
continuation snapshot.

Target options:
  --steps N              guest instruction budget (default: 10000000)
  --no-verify            skip the pinned ADF size and SHA-256 checks
  --replay-inputs NAME   play NAME.pfreplay.json (or a path; legacy .json works)
  --play-replay NAME     alias for --replay-inputs
  --record-replay NAME   write the deterministic input journal
  --snapshot NAME        resume artifacts/snapshots/NAME.pfamigasnapshot
  --update-atlas         ingest this run's evidence into the project Atlas
  --live-atlas [PATH]    show the persisted Atlas beside interactive play
  --atlas-interval N     publish Live Atlas activity every N PAL frames
  --headless             run the deterministic two-pass verification probe

Anything after ``--`` is forwarded verbatim to the selected Amiga runner.
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


def game_json() -> dict:
    return json.loads((ROOT / "game.json").read_text(encoding="utf-8"))


def verify_asset(facts: dict) -> Path:
    path = ROOT / "assets" / facts["file"]
    if not path.is_file():
        raise RuntimeError(f"missing {path}; see assets/README.md")
    if path.stat().st_size != facts["size"]:
        raise RuntimeError(
            f"{path.name}: size {path.stat().st_size}; "
            f"game.json pins {facts['size']}"
        )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != facts["sha256"]:
        raise RuntimeError(
            f"{path.name}: sha256 {digest}\n"
            f"game.json pins {facts['sha256']}\n"
            "pass --no-verify only when intentionally investigating "
            "a different disk set"
        )
    return path


def target_options(
    selection: player_runtime.PlayerSelection,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--steps", type=int, default=10_000_000)
    parser.add_argument("--no-verify", action="store_true")
    parser.add_argument(
        "--replay-inputs", "--play-replay", dest="replay_inputs"
    )
    parser.add_argument("--record-replay")
    parser.add_argument("--snapshot")
    parser.add_argument("--update-atlas", action="store_true")
    parser.add_argument(
        "--live-atlas",
        nargs="?",
        const="__project_atlas__",
    )
    parser.add_argument("--atlas-interval", type=int, default=1)
    parser.add_argument("--headless", action="store_true")
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
    return options


def artifact_path(
    value: str,
    directory: Path,
    suffix: str,
    *,
    legacy_suffix: str | None = None,
) -> Path:
    path = Path(value)
    if path.parent == Path("."):
        path = directory / path
    if not path.suffix:
        preferred = path.with_name(path.name + suffix)
        legacy = (
            path.with_name(path.name + legacy_suffix)
            if legacy_suffix
            else None
        )
        path = (
            legacy
            if legacy is not None
            and legacy.is_file()
            and not preferred.is_file()
            else preferred
        )
    return path.resolve()


def verify_generated_runtime() -> dict:
    path = ROOT / "artifacts" / "generated" / "amiga" / "verification.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise player_runtime.PlayerConfigError(
            "generated runtime has no readable verification evidence at "
            f"{path}\nbuild it with: python scripts/build_generated.py"
        ) from error
    cfg = game_json()
    if (
        not isinstance(value, dict)
        or value.get("format")
        != "portforge-amiga-generated-verification-v1"
        or value.get("equivalent") is not True
        or value.get("program_sha256") != cfg["program"]["sha256"]
        or value.get("companion_sha256")
        != cfg["companion_assets"]["disk2"]["sha256"]
    ):
        raise player_runtime.PlayerConfigError(
            "generated runtime verification is invalid or belongs to "
            "different media\nbuild it with: "
            "python scripts/build_generated.py"
        )
    inputs = value.get("inputs")
    if not isinstance(inputs, dict):
        raise player_runtime.PlayerConfigError(
            "generated runtime verification has no input provenance"
        )
    paths = {
        "disk1": ROOT / "assets" / cfg["program"]["file"],
        "disk2": (
            ROOT
            / "assets"
            / cfg["companion_assets"]["disk2"]["file"]
        ),
        "replay": (
            ROOT
            / "artifacts"
            / "replays"
            / "cold5.pfreplay.json"
        ),
        "lift_plan": (
            ROOT
            / "artifacts"
            / "generated"
            / "amiga"
            / "lift-plan.json"
        ),
        "generated_header": (
            ROOT
            / "artifacts"
            / "generated"
            / "amiga"
            / "ducktales_amiga_gen.hpp"
        ),
        "headless_runner": (
            ROOT / "build" / "ducktales_amiga_generated_run.exe"
        ),
        "viewer_runner": (
            ROOT / "build" / "ducktales_amiga_generated_view.exe"
        ),
        "game": ROOT / "game.json",
        "profile": (
            ROOT / "profiles" / "ducktales_a500_ocs_pal.json"
        ),
    }
    for name, item in paths.items():
        try:
            digest = hashlib.sha256(item.read_bytes()).hexdigest()
        except OSError as error:
            raise player_runtime.PlayerConfigError(
                f"generated runtime input is absent: {item}\n"
                "build it with: python scripts/build_generated.py"
            ) from error
        if inputs.get(name) != digest:
            raise player_runtime.PlayerConfigError(
                f"generated runtime verification is stale: {item}\n"
                "build it with: python scripts/build_generated.py"
            )
    producer = value.get("producer")
    if (
        not isinstance(producer, dict)
        or producer.get("portforge_dirty") is not False
    ):
        raise player_runtime.PlayerConfigError(
            "generated runtime verification was not produced by a clean "
            "PortForge revision\nbuild it with: "
            "python scripts/build_generated.py"
        )
    safe_git = [
        "git",
        "-c",
        f"safe.directory={PORT_FORGE.as_posix()}",
    ]
    revision = subprocess.run(
        [*safe_git, "rev-parse", "HEAD"],
        cwd=PORT_FORGE,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    if producer.get("portforge_revision") != revision:
        raise player_runtime.PlayerConfigError(
            "generated runtime verification belongs to another PortForge "
            "revision\nbuild it with: python scripts/build_generated.py"
        )
    dirty = subprocess.run(
        [*safe_git, "status", "--porcelain", "--untracked-files=no"],
        cwd=PORT_FORGE,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    if dirty:
        raise player_runtime.PlayerConfigError(
            "generated runtime verification cannot authorize a dirty "
            "PortForge checkout\nrebuild from a clean revision with: "
            "python scripts/build_generated.py"
        )
    return value


def main(argv: list[str] | None = None) -> int:
    source = list(sys.argv[1:] if argv is None else argv)
    if player_runtime.help_requested(source):
        print(player_runtime.render_help(__doc__))
        return 0

    selection = player_runtime.select_runtime(ROOT, source)
    if selection.runtime not in {"oracle", "generated"}:
        raise player_runtime.PlayerConfigError(
            f"runtime {selection.runtime!r} is declared supported but "
            "DuckTales has no matching player adapter"
        )
    options = target_options(selection)
    cfg = game_json()
    disk1_facts = cfg["program"]
    disk2_facts = cfg["companion_assets"]["disk2"]
    disk1 = ROOT / "assets" / disk1_facts["file"]
    disk2 = ROOT / "assets" / disk2_facts["file"]
    explicit_steps = any(
        value == "--steps" or value.startswith("--steps=")
        for value in selection.adapter_args
    )
    interactive = not (
        options.headless
        or options.update_atlas
        or explicit_steps
    )
    if options.live_atlas and not interactive:
        raise player_runtime.PlayerConfigError(
            "--live-atlas requires interactive play"
        )
    if selection.runtime == "generated":
        runner = (
            ROOT
            / "build"
            / (
                "ducktales_amiga_generated_view.exe"
                if interactive
                else "ducktales_amiga_generated_run.exe"
            )
        )
    else:
        runner_name = "pf_amiga_view" if interactive else "pf_amiga_run"
        runner = PORT_FORGE / "build" / f"{runner_name}.exe"
    output = ROOT / "artifacts" / "amiga"
    if selection.runtime == "generated":
        output = output / "generated"
    runner_options: list[str] = []
    if options.replay_inputs:
        replay = artifact_path(
            options.replay_inputs,
            ROOT / "artifacts" / "replays",
            ".pfreplay.json",
            legacy_suffix=".json",
        )
        if not selection.dry_run:
            player_runtime.require_artifact(replay, selection)
        runner_options += ["--replay-inputs", str(replay)]
    if options.record_replay:
        replay = artifact_path(
            options.record_replay,
            ROOT / "artifacts" / "replays",
            ".pfreplay.json",
        )
        runner_options += ["--record-replay", str(replay)]
    if options.snapshot:
        if not interactive:
            raise player_runtime.PlayerConfigError(
                "--snapshot currently requires the interactive player; "
                "headless snapshot resume is not implemented"
            )
        snapshot = artifact_path(
            options.snapshot,
            ROOT / "artifacts" / "snapshots",
            ".pfamigasnapshot",
        )
        if not selection.dry_run:
            player_runtime.require_artifact(snapshot, selection)
        runner_options += ["--snapshot", str(snapshot)]
    if options.live_atlas:
        atlas = (
            ROOT / "artifacts" / "atlas.pfatlas"
            if options.live_atlas == "__project_atlas__"
            else Path(options.live_atlas)
        ).resolve()
        if not selection.dry_run:
            player_runtime.require_artifact(atlas, selection)
        runner_options += [
            "--live-atlas",
            str(atlas),
            "--atlas-interval",
            str(options.atlas_interval),
        ]

    if not selection.dry_run:
        if options.no_verify:
            player_runtime.require_artifact(disk1, selection)
            player_runtime.require_artifact(disk2, selection)
        else:
            disk1 = verify_asset(disk1_facts)
            disk2 = verify_asset(disk2_facts)
        if selection.runtime == "generated":
            if selection.no_build:
                player_runtime.require_artifact(runner, selection)
                verify_generated_runtime()
            else:
                subprocess.run(
                    [sys.executable, "scripts/build_generated.py"],
                    check=True,
                    cwd=ROOT,
                )
                player_runtime.require_artifact(runner, selection)
                verify_generated_runtime()
                if options.update_atlas:
                    subprocess.run(
                        [
                            sys.executable,
                            "build.py",
                            "--no-tests",
                            "--targets",
                            "pf_atlas",
                        ],
                        check=True,
                        cwd=PORT_FORGE,
                    )
        elif selection.no_build:
            player_runtime.require_artifact(runner, selection)
        else:
            subprocess.run(
                [
                    sys.executable,
                    "build.py",
                    "--no-tests",
                    "--targets",
                    f"{runner_name},pf_atlas"
                    if options.update_atlas
                    else runner_name,
                ],
                check=True,
                cwd=PORT_FORGE,
            )

    command = [
        str(runner),
        str(disk1),
        disk1_facts["executable"],
        "--disk",
        str(disk2),
        "--vblank-signal",
        "0x2413e",
    ]
    if not interactive:
        command += [
            "--steps",
            str(options.steps),
            "--out",
            str(output),
            (
                "--native"
                if selection.runtime == "generated"
                else "--oracle"
            ),
            "--strict",
        ]
    command += [*runner_options, *selection.runner_args]
    runtime_identity = (
        [
            "generated authority: automatically lifted, byte-guarded "
            "M68000 subset",
            "interpreter fallback: observable residual and SMC fallback",
            "verification: generated-baseline canonical equality with "
            "the M68000 oracle",
        ]
        if selection.runtime == "generated"
        else [
            "oracle authority: original Amiga M68K instructions",
        ]
    )
    code = player_runtime.run_selected(
        selection,
        command,
        cwd=ROOT,
        identity=[
            f"program identity: sha256:{disk1_facts['sha256']}",
            f"HUNK identity: sha256:{disk1_facts['hunk_sha256']}",
            f"companion identity: sha256:{disk2_facts['sha256']}",
            *runtime_identity,
            "presentation: interactive Win32 viewer"
            if interactive
            else "presentation: deterministic headless verification",
            "input: deterministic PortForge Amiga journal",
            "PortForge runtime: included",
        ],
    )
    if code == 0 and options.update_atlas and not selection.dry_run:
        evidence = output / "ducktales-evidence.json"
        subprocess.run(
            [
                sys.executable,
                str(PORT_FORGE / "tools" / "pf_project.py"),
                "atlas",
                str(ROOT),
                "ingest-evidence",
                str(evidence),
            ],
            check=True,
            cwd=ROOT,
        )
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (
        OSError,
        RuntimeError,
        player_runtime.PlayerConfigError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"play.py: {error}", file=sys.stderr)
        sys.exit(1)
