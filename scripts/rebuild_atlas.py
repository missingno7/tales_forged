#!/usr/bin/env python3
"""Rebuild DuckTales dynamic and static Execution Atlas evidence atomically.

The command records a complete oracle profile for the curated replay,
regenerates resident-HUNK recovery, creates a fresh evidence-bound Atlas, and
adds the recovered blocks through PortForge's Amiga control plane. The prior
Atlas is retained under ``build/atlas-backups`` and restored on failure.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT_FORGE = ROOT / "port_forge"
ATLAS = ROOT / "artifacts" / "atlas.pfatlas"
EVIDENCE = ROOT / "artifacts" / "amiga" / "ducktales-evidence.json"
BLOCKS = ROOT / "artifacts" / "generated" / "amiga" / "blocks.json"
RUN_REPORT = ROOT / "artifacts" / "amiga" / "ducktales-run.json"
REPLAY = ROOT / "artifacts" / "replays" / "cold5.pfreplay.json"


def command(values: list[str], *, cwd: Path) -> None:
    print("$", subprocess.list2cmdline([str(value) for value in values]))
    subprocess.run([str(value) for value in values], cwd=cwd, check=True)


def ensure_clean_portforge() -> None:
    safe_git = [
        "git",
        "-c",
        f"safe.directory={PORT_FORGE.as_posix()}",
    ]
    revision = subprocess.run(
        [*safe_git, "rev-parse", "HEAD"],
        cwd=PORT_FORGE,
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        [*safe_git, "status", "--porcelain"],
        cwd=PORT_FORGE,
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    ).stdout.strip()
    if not revision or dirty:
        raise RuntimeError(
            "Atlas production requires a clean, committed PortForge revision"
        )


def default_steps() -> int:
    profile = json.loads(
        (
            ROOT / "profiles" / "ducktales_a500_ocs_pal.json"
        ).read_text(encoding="utf-8")
    )
    value = profile["verification"][
        "generated_replay_instruction_budget"
    ]
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RuntimeError("profile Atlas instruction budget is invalid")
    return value


def load_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path}: expected a JSON object")
    return value


def amiga_address(value, label: str) -> int:
    try:
        address = (
            value
            if isinstance(value, int) and not isinstance(value, bool)
            else int(value, 0)
            if isinstance(value, str)
            else -1
        )
    except ValueError as error:
        raise RuntimeError(f"{label} is not an address") from error
    if not 0 <= address <= 0xFFFFFF:
        raise RuntimeError(f"{label} is outside Amiga 24-bit memory")
    return address


def verify_existing_profile() -> None:
    evidence = load_object(EVIDENCE)
    run = load_object(RUN_REPORT)
    replay = load_object(REPLAY)
    game = load_object(ROOT / "game.json")
    events = replay.get("events")
    if not isinstance(events, list) or not events:
        raise RuntimeError("curated replay has no input timeline")
    ticks = [
        event["master_tick"]
        for event in events
        if isinstance(event, dict)
        and isinstance(event.get("master_tick"), int)
    ]
    if len(ticks) != len(events):
        raise RuntimeError("curated replay has an invalid input timeline")
    last_tick = max(ticks)
    extensions = evidence.get("extensions")
    identity = (
        extensions.get("org.portforge.amiga.execution-image")
        if isinstance(extensions, dict)
        else None
    )
    program = game.get("program")
    machine = game.get("machine")
    load_base = amiga_address(
        machine.get("load_base") if isinstance(machine, dict) else None,
        "game.json machine.load_base",
    )
    module_entry = amiga_address(
        machine.get("module_entry") if isinstance(machine, dict) else None,
        "game.json machine.module_entry",
    )
    exact_hunk_identity = (
        isinstance(program, dict)
        and isinstance(identity, dict)
        and identity.get("format") == "pf-amiga-execution-image-v1"
        and identity.get("identity_model")
        == "adf-sha256+program+hunk-sha256+load-base+module-entry"
        and identity.get("program") == program.get("executable")
        and identity.get("hunk_sha256") == program.get("hunk_sha256")
        and identity.get("load_base") == load_base
        and identity.get("module_entry") == module_entry
    )
    if (
        evidence.get("format") != "pf-atlas-evidence-v2"
        or evidence.get("program_sha256")
        != game["program"]["sha256"]
        or evidence.get("machine_model")
        != "pf-amiga-a500-ocs-pal-v1"
        or run.get("format") != "pf-amiga-run-v1"
        or run.get("execution_mode") != "amiga-oracle"
        or run.get("deterministic_rerun") is not True
        or run.get("snapshot_roundtrip") is not True
        or run.get("replay_events_total") != len(events)
        or run.get("replay_events_consumed") != len(events)
        or not isinstance(run.get("master_tick"), int)
        or run["master_tick"] < last_tick
        or not exact_hunk_identity
    ):
        raise RuntimeError(
            "existing oracle evidence is stale, incomplete, or unverified; "
            "rerun without --reuse-evidence"
        )


def inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def move_existing_atlas() -> Path | None:
    if not ATLAS.exists():
        return None
    backup_root = ROOT / "build" / "atlas-backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = backup_root / f"atlas-{stamp}.pfatlas"
    if not inside(ROOT / "build", backup):
        raise RuntimeError("refusing Atlas backup outside project build/")
    shutil.move(str(ATLAS), str(backup))
    return backup


def restore_after_failure(backup: Path | None) -> Path | None:
    failed: Path | None = None
    if ATLAS.exists():
        failed_root = ROOT / "build" / "atlas-failed"
        failed_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        failed = failed_root / f"atlas-{stamp}.pfatlas"
        if not inside(ROOT / "build", failed):
            raise RuntimeError("refusing failed Atlas move outside build/")
        shutil.move(str(ATLAS), str(failed))
    if backup is not None:
        if not inside(ROOT / "build", backup):
            raise RuntimeError("refusing Atlas restore from outside build/")
        shutil.move(str(backup), str(ATLAS))
    return failed


def rebuild(steps: int, *, reuse_evidence: bool = False) -> None:
    ensure_clean_portforge()
    if not reuse_evidence:
        command(
            [
                sys.executable,
                "scripts/play.py",
                "--runtime",
                "oracle",
                "--headless",
                "--steps",
                str(steps),
                "--replay-inputs",
                "cold5",
            ],
            cwd=ROOT,
        )
    if not EVIDENCE.is_file():
        raise RuntimeError(f"oracle run produced no evidence: {EVIDENCE}")
    verify_existing_profile()
    command([sys.executable, "scripts/analyze.py"], cwd=ROOT)
    if not BLOCKS.is_file():
        raise RuntimeError(f"analysis produced no Atlas blocks: {BLOCKS}")

    backup = move_existing_atlas()
    project_tool = PORT_FORGE / "tools" / "pf_project.py"
    try:
        command(
            [
                sys.executable,
                str(project_tool),
                "atlas",
                str(ROOT),
                "ingest-evidence",
                str(EVIDENCE),
            ],
            cwd=ROOT,
        )
        command(
            [
                sys.executable,
                str(project_tool),
                "atlas",
                str(ROOT),
                "ingest-blocks",
            ],
            cwd=ROOT,
        )
        command(
            [
                sys.executable,
                str(project_tool),
                "validate",
                str(ROOT),
            ],
            cwd=ROOT,
        )
    except Exception:
        failed = restore_after_failure(backup)
        if failed is not None:
            print(f"failed Atlas retained at {failed}", file=sys.stderr)
        raise
    if backup is not None:
        print(f"previous Atlas retained at {backup}")
    print(f"fresh Atlas: {ATLAS}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=default_steps())
    parser.add_argument(
        "--reuse-evidence",
        action="store_true",
        help=(
            "reuse the existing bound oracle evidence (for example the "
            "profile just produced by scripts/build_generated.py)"
        ),
    )
    options = parser.parse_args(argv)
    if options.steps < 1:
        parser.error("--steps must be positive")
    rebuild(options.steps, reuse_evidence=options.reuse_evidence)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (
        OSError,
        RuntimeError,
        KeyError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"rebuild_atlas.py: {error}", file=sys.stderr)
        sys.exit(1)
