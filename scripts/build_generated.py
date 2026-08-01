#!/usr/bin/env python3
"""Build and verify the evidence-bounded DuckTales Amiga generated runtime.

Pipeline:

1. regenerate the resident-HUNK lift plan from the curated recovery evidence;
2. emit byte-guarded M68000 hooks for PortForge's conservative instruction
   subset;
3. compile headless and Win32 generated+fallback runners; and
4. require the complete ``generated-baseline`` replay to end in exactly the
   same canonical state as the M68000 oracle.

The result is a hybrid generated runtime with explicit, observable interpreter
and self-modifying-code fallback. It is not a detached source port.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PORT_FORGE = ROOT / "port_forge"
GENERATED = ROOT / "artifacts" / "generated" / "amiga"
BUILD = ROOT / "build"
LIFT_PLAN = GENERATED / "lift-plan.json"
GENERATED_HEADER = GENERATED / "ducktales_amiga_gen.hpp"
VERIFICATION = GENERATED / "verification.json"
HEADLESS = BUILD / "ducktales_amiga_generated_run.exe"
VIEWER = BUILD / "ducktales_amiga_generated_view.exe"
REPLAY = ROOT / "artifacts" / "replays" / "cold5.pfreplay.json"
BOUNDARY_PROFILE = ROOT / "profiles" / "replay-boundaries-v1.json"
ORACLE_PLAN = ROOT / "artifacts" / "execution-plans" / "oracle-interpreter.json"
GENERATED_PLAN = (
    ROOT / "artifacts" / "execution-plans" / "generated-plus-fallback.json"
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pf_build = _load_module("portforge_build", PORT_FORGE / "build.py")


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"{path}: expected a JSON object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_inputs() -> tuple[dict[str, Any], Path, Path, Path, int]:
    game = load_object(ROOT / "game.json")
    profile = load_object(ROOT / "profiles" / "ducktales_a500_ocs_pal.json")
    bootstrap = profile.get("bootstrap")
    if (
        not isinstance(bootstrap, dict)
        or profile.get("program_sha256") != game["program"]["sha256"]
        or profile.get("hunk_sha256")
        != game["program"].get("hunk_sha256")
        or bootstrap.get("program")
        != game["program"]["executable"]
        or bootstrap.get("load_base") != "amiga:010000"
        or bootstrap.get("entry") != "amiga:010000"
    ):
        raise RuntimeError(
            "generated profile does not match the pinned direct-HUNK "
            "program identity"
        )
    disk1 = ROOT / "assets" / game["program"]["file"]
    disk2 = ROOT / "assets" / game["companion_assets"]["disk2"]["file"]
    replay = REPLAY
    verification = profile.get("verification", {})
    steps = verification.get("generated_replay_instruction_budget", 50_000_000)
    if not isinstance(steps, int) or steps < 1:
        raise RuntimeError(
            "profile verification.generated_replay_instruction_budget "
            "must be a positive integer"
        )
    for path in (disk1, disk2, replay, BOUNDARY_PROFILE, ORACLE_PLAN,
                 GENERATED_PLAN):
        if not path.is_file():
            raise RuntimeError(f"missing generated-runtime input: {path}")
    expected = {
        disk1: game["program"]["sha256"],
        disk2: game["companion_assets"]["disk2"]["sha256"],
    }
    for path, digest in expected.items():
        actual = sha256(path)
        if actual != digest:
            raise RuntimeError(
                f"{path.name}: sha256 {actual}; game.json pins {digest}"
            )
    return game, disk1, disk2, replay, steps


def run_checked(
    command: list[str],
    *,
    cwd: Path,
    echo_output: bool = True,
) -> subprocess.CompletedProcess:
    print("$", subprocess.list2cmdline([str(item) for item in command]))
    result = subprocess.run(
        [str(item) for item in command],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.stdout and echo_output:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(
            result.stderr,
            end="" if result.stderr.endswith("\n") else "\n",
            file=sys.stderr,
        )
    if result.returncode:
        raise subprocess.CalledProcessError(
            result.returncode,
            command,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result


def generate_sources() -> None:
    game = load_object(ROOT / "game.json")
    run_checked(
        [
            sys.executable,
            "build.py",
            "--no-tests",
            "--targets",
            "pf_amiga_analyze,pf_amiga_codegen,pf_amiga_run",
        ],
        cwd=PORT_FORGE,
    )
    run_checked(
        [sys.executable, "scripts/analyze.py", "--no-build"],
        cwd=ROOT,
    )
    run_checked(
        [
            str(PORT_FORGE / "build" / "pf_amiga_codegen.exe"),
            str(LIFT_PLAN),
            str(GENERATED_HEADER),
            "--expect-program-sha256",
            game["program"]["sha256"],
            "--expect-hunk-sha256",
            game["program"]["hunk_sha256"],
            "--expect-machine-model",
            "pf-amiga-a500-ocs-pal-v3",
        ],
        cwd=ROOT,
    )


def compile_runners() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    define = '-DPF_AMIGA_GENERATED_HEADER="ducktales_amiga_gen.hpp"'
    common = [
        str(pf_build.CXX),
        *pf_build.CXXFLAGS,
        "-I",
        str(GENERATED),
        "-I",
        str(PORT_FORGE),
        define,
    ]
    headless_command = [
        *common,
        str(PORT_FORGE / "tools" / "pf_amiga_run.cpp"),
        "-o",
        str(HEADLESS),
    ]
    viewer_command = [
        *common,
        str(PORT_FORGE / "tools" / "pf_amiga_view.cpp"),
        "-o",
        str(VIEWER),
        "-lgdi32",
        "-luser32",
        "-lwinmm",
    ]
    inputs = [
        GENERATED_HEADER,
        PORT_FORGE / "src",
        PORT_FORGE / "tools" / "pf_amiga_run.cpp",
        PORT_FORGE / "tools" / "pf_amiga_view.cpp",
    ]
    for output, command in (
        (HEADLESS, headless_command),
        (VIEWER, viewer_command),
    ):
        if pf_build.ensure_multi(output, command, inputs):
            print(f"built {output}")
        else:
            print(f"up to date: {output}")


def parse_runner_json(result: subprocess.CompletedProcess) -> dict[str, Any]:
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "generated verifier runner did not emit one JSON document"
        ) from error
    if not isinstance(value, dict) or value.get("format") != "pf-amiga-run-v1":
        raise RuntimeError("generated verifier returned an unexpected report")
    return value


def runner_result(
    game: dict[str, Any],
    disk1: Path,
    disk2: Path,
    replay: Path,
    steps: int,
    mode: str,
    *,
    runner: Path = HEADLESS,
    output: Path | None = None,
) -> dict[str, Any]:
    command = [
        str(runner),
        str(disk1),
        game["program"]["executable"],
        "--disk",
        str(disk2),
        "--vblank-signal",
        "0x2413e",
        "--steps",
        str(steps),
        "--replay-artifact",
        str(replay),
        "--boundary-profile",
        str(BOUNDARY_PROFILE),
        "--implementation-plan",
        str(GENERATED_PLAN if mode == "--native" else ORACLE_PLAN),
        "--strict",
        mode,
    ]
    if output is not None:
        command += ["--out", str(output)]
    result = run_checked(command, cwd=ROOT, echo_output=False)
    return parse_runner_json(result)


def replay_terminal(path: Path) -> tuple[int, str]:
    replay = load_object(path)
    if replay.get("format") != "portforge-replay-v2":
        raise RuntimeError(f"{path}: expected ReplayArtifactV2")
    terminal = replay.get("terminal")
    if not isinstance(terminal, dict):
        raise RuntimeError(f"{path}: ReplayArtifactV2 terminal is missing")
    stamp = terminal.get("stamp")
    boundary = (
        stamp.get("global_ordinal")
        if isinstance(stamp, dict)
        else None
    )
    digest = terminal.get("canonical_sha256")
    if (
        terminal.get("schema") != "pf-replay-terminal-v3"
        or not isinstance(stamp, dict)
        or stamp.get("schema") != "pf-boundary-stamp-v1"
        or stamp.get("outcome") != "terminal"
        or not isinstance(boundary, int)
        or isinstance(boundary, bool)
        or boundary < 0
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise RuntimeError(f"{path}: invalid ReplayArtifactV2 terminal")
    return boundary, digest


def replay_event_count(path: Path) -> int:
    replay = load_object(path)
    if replay.get("format") != "portforge-replay-v2":
        raise RuntimeError(f"{path}: expected ReplayArtifactV2")
    events = replay.get("events")
    if not isinstance(events, list) or not events:
        raise RuntimeError(f"{path}: generated-baseline replay has no events")
    return len(events)


def producer_state() -> dict[str, Any]:
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
    dirty = bool(
        subprocess.run(
            [
                *safe_git,
                "status",
                "--porcelain",
                "--untracked-files=no",
            ],
            cwd=PORT_FORGE,
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        ).stdout.strip()
    )
    return {
        "portforge_revision": revision,
        "portforge_dirty": dirty,
        "compiler": str(pf_build.CXX),
    }


def verification_inputs(
    disk1: Path, disk2: Path, replay: Path
) -> dict[str, str]:
    paths = {
        "disk1": disk1,
        "disk2": disk2,
        "replay": replay,
        "boundary_profile": BOUNDARY_PROFILE,
        "oracle_plan": ORACLE_PLAN,
        "generated_plan": GENERATED_PLAN,
        "lift_plan": LIFT_PLAN,
        "generated_header": GENERATED_HEADER,
        "headless_runner": HEADLESS,
        "viewer_runner": VIEWER,
        "game": ROOT / "game.json",
        "profile": ROOT / "profiles" / "ducktales_a500_ocs_pal.json",
    }
    return {name: sha256(path) for name, path in paths.items()}


def cached_verification_valid(
    inputs: dict[str, str], producer: dict[str, Any], steps: int
) -> bool:
    if not VERIFICATION.is_file():
        return False
    try:
        current = load_object(VERIFICATION)
    except RuntimeError:
        return False
    return (
        current.get("format")
        == "portforge-amiga-generated-verification-v2"
        and current.get("equivalent") is True
        and current.get("inputs") == inputs
        and current.get("producer") == producer
        and current.get("instruction_budget") == steps
    )


def comparable(report: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "status",
        "diagnostic",
        "instructions",
        "cpu_cycles",
        "master_tick",
        "frame",
        "raster_v",
        "raster_h",
        "pc",
        "status_register",
        "data_registers",
        "address_registers",
        "canonical_digest",
        "service_calls",
        "visible_output",
        "replay_events_consumed",
        "replay_events_total",
    )
    return {name: report.get(name) for name in fields}


def verify_generated() -> None:
    game, disk1, disk2, replay, steps = project_inputs()
    inputs = verification_inputs(disk1, disk2, replay)
    producer = producer_state()
    if cached_verification_valid(inputs, producer, steps):
        print(f"generated verification up to date: {VERIFICATION}")
        return

    # Refresh the authoritative profile before code generation. The generic
    # runner has no generated registry compiled into it, so this is an
    # unambiguous oracle producer. Re-analysis then consumes exactly this
    # corrected frame/callback/overlay evidence instead of a stale journal.
    oracle = runner_result(
        game,
        disk1,
        disk2,
        replay,
        steps,
        "--oracle",
        runner=PORT_FORGE / "build" / "pf_amiga_run.exe",
        output=ROOT / "artifacts" / "amiga",
    )
    generate_sources()
    compile_runners()
    inputs = verification_inputs(disk1, disk2, replay)
    generated = runner_result(
        game,
        disk1,
        disk2,
        replay,
        steps,
        "--native",
        output=BUILD / "generated-verification",
    )
    expected_events = replay_event_count(replay)
    terminal_boundary, terminal_digest = replay_terminal(replay)
    for label, report in (("generated", generated), ("oracle", oracle)):
        if report.get("deterministic_rerun") is not True:
            raise RuntimeError(f"{label} runner did not reproduce itself")
        if report.get("snapshot_roundtrip") is not True:
            raise RuntimeError(f"{label} snapshot roundtrip failed")
        if (
            report.get("replay_events_total") != expected_events
            or report.get("replay_events_consumed") != expected_events
        ):
            raise RuntimeError(
                f"{label} runner did not consume the complete replay journal"
            )
        if report.get("canonical_digest") != terminal_digest:
            raise RuntimeError(
                f"{label} runner did not reach the ArtifactV2 terminal state"
            )
    if generated.get("native_blocks", 0) <= 0:
        raise RuntimeError(
            "generated runner executed no generated M68000 instructions"
        )
    generated_state = comparable(generated)
    oracle_state = comparable(oracle)
    if generated_state != oracle_state:
        mismatches = [
            name
            for name in generated_state
            if generated_state[name] != oracle_state[name]
        ]
        raise RuntimeError(
            "generated/oracle replay mismatch: " + ", ".join(mismatches)
        )

    plan = load_object(LIFT_PLAN)
    report = {
        "format": "portforge-amiga-generated-verification-v2",
        "equivalent": True,
        "claim": (
            "byte-guarded generated subset plus observable interpreter/SMC "
            "fallback matches the M68000 oracle over generated-baseline"
        ),
        "program_sha256": game["program"]["sha256"],
        "hunk_sha256": game["program"]["hunk_sha256"],
        "companion_sha256": game["companion_assets"]["disk2"]["sha256"],
        "machine_model": plan["machine_model"],
        "load_base": plan["load_base"],
        "module_entry": plan["module_entry"],
        "replay_artifact": str(replay.relative_to(ROOT)).replace("\\", "/"),
        "replay_artifact_sha256": sha256(replay),
        "replay_terminal_boundary_ordinal": terminal_boundary,
        "replay_terminal_canonical_sha256": terminal_digest,
        "replay_event_count": expected_events,
        "boundary_profile": str(BOUNDARY_PROFILE.relative_to(ROOT)).replace(
            "\\", "/"
        ),
        "oracle_plan": str(ORACLE_PLAN.relative_to(ROOT)).replace("\\", "/"),
        "generated_plan": str(GENERATED_PLAN.relative_to(ROOT)).replace(
            "\\", "/"
        ),
        "instruction_budget": steps,
        "generated_instruction_count": plan.get(
            "conservative_emittable_instruction_count",
            sum(
                item.get("conservative_emitter_supported") is True
                for item in plan.get("instructions", [])
                if isinstance(item, dict)
            ),
        ),
        "executed_generated_blocks": generated["native_blocks"],
        "interpreter_fallback_steps": generated[
            "interpreter_fallback_steps"
        ],
        "state": generated_state,
        "inputs": inputs,
        "producer": producer,
    }
    GENERATED.mkdir(parents=True, exist_ok=True)
    VERIFICATION.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "generated/oracle equivalent: "
        f"{generated['native_blocks']} generated instructions, "
        f"{generated['interpreter_fallback_steps']} fallback steps -> "
        f"{VERIFICATION}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compile-only",
        action="store_true",
        help="generate and compile, but do not publish verification evidence",
    )
    options = parser.parse_args(argv)
    project_inputs()
    GENERATED.mkdir(parents=True, exist_ok=True)
    generate_sources()
    compile_runners()
    if not options.compile_only:
        verify_generated()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (
        OSError,
        RuntimeError,
        KeyError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"build_generated.py: {error}", file=sys.stderr)
        sys.exit(1)
