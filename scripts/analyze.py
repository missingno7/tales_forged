#!/usr/bin/env python3
"""Build DuckTales resident M68000 recovery and Atlas block artifacts.

The PortForge analyzer owns generic ADF/HUNK decoding. This project launcher
owns the pinned DuckTales assets, the curated execution profile, artifact
paths, and the deliberately limited recovery claim. It never promotes a
static lift plan into a generated runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = Path("artifacts/amiga/ducktales-evidence.json")
ADDRESS_PATTERN = re.compile(r"^[0-9A-F]{6}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PinnedAsset:
    name: str
    path: Path
    sha256: str
    size: int


@dataclass(frozen=True)
class AnalysisConfig:
    root: Path
    portforge: Path
    image: PinnedAsset
    companions: tuple[PinnedAsset, ...]
    executable: str
    hunk_sha256: str
    machine_model: str
    load_base: int
    module_entry: int
    evidence: Path
    lift_plan: Path
    atlas_blocks: Path


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"{path}: expected a JSON object")
    return value


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _project_path(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{label} must be a non-empty project path")
    path = (root / value).resolve()
    if not _inside(root, path):
        raise RuntimeError(f"{label} escapes the project root: {value!r}")
    return path


def _pinned_asset(
    root: Path,
    assets_root: Path,
    name: str,
    record: Any,
) -> PinnedAsset:
    if not isinstance(record, dict):
        raise RuntimeError(f"{name} must be a pinned asset object")
    required = {"file", "sha256", "size"}
    if not required.issubset(record):
        raise RuntimeError(f"{name} is missing pinned file identity")
    digest = record["sha256"]
    size = record["size"]
    if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
        raise RuntimeError(f"{name}.sha256 is invalid")
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise RuntimeError(f"{name}.size is invalid")
    path = _project_path(
        root, str(assets_root.relative_to(root) / str(record["file"])), name
    )
    return PinnedAsset(name, path, digest, size)


def _amiga_address(value: Any, label: str) -> int:
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


def load_configuration(root: Path = PROJECT_ROOT) -> AnalysisConfig:
    root = root.resolve()
    project_path = root / "portforge.project.json"
    project = _load_object(project_path)
    if project.get("format") != "portforge-project-v1":
        raise RuntimeError(f"{project_path}: unsupported project format")
    game_path = _project_path(
        root, project.get("game", "game.json"), "project.game"
    )
    game = _load_object(game_path)
    if game.get("format") != "portforge-game-v0":
        raise RuntimeError(f"{game_path}: unsupported game format")
    if game.get("platform") != "amiga":
        raise RuntimeError(f"{game_path}: expected an Amiga project")

    portforge = _project_path(
        root, project.get("portforge", "port_forge"), "project.portforge"
    )
    assets_root = _project_path(
        root, project.get("assets", "assets"), "project.assets"
    )
    image = _pinned_asset(
        root, assets_root, "program", game.get("program")
    )
    program = game.get("program")
    executable = (
        program.get("executable") if isinstance(program, dict) else None
    )
    if not isinstance(executable, str) or not executable:
        raise RuntimeError("game.json program.executable is missing")
    hunk_sha256 = (
        program.get("hunk_sha256") if isinstance(program, dict) else None
    )
    if (
        not isinstance(hunk_sha256, str)
        or not SHA256_PATTERN.fullmatch(hunk_sha256)
    ):
        raise RuntimeError("game.json program.hunk_sha256 is invalid")

    machine = game.get("machine")
    if not isinstance(machine, dict):
        raise RuntimeError("game.json machine declaration is missing")
    if machine.get("profile") != "a500-ocs-pal":
        raise RuntimeError("static recovery requires profile a500-ocs-pal")
    if machine.get("direct_hunk_bootstrap") is not True:
        raise RuntimeError("static recovery requires direct-HUNK bootstrap")
    machine_model = "pf-amiga-a500-ocs-pal-v16"
    load_base = _amiga_address(
        machine.get("load_base"), "game.json machine.load_base"
    )
    module_entry = _amiga_address(
        machine.get("module_entry"), "game.json machine.module_entry"
    )

    raw_companions = game.get("companion_assets", {})
    if not isinstance(raw_companions, dict):
        raise RuntimeError("game.json companion_assets must be an object")
    companions = tuple(
        _pinned_asset(
            root, assets_root, f"companion_assets.{name}", record
        )
        for name, record in raw_companions.items()
    )

    artifacts = project.get("artifacts")
    if not isinstance(artifacts, dict):
        raise RuntimeError("project artifacts must be an object")
    lift_plan = _project_path(
        root, artifacts.get("lift_plan"), "artifacts.lift_plan"
    )
    atlas_blocks = _project_path(
        root, artifacts.get("blocks"), "artifacts.blocks"
    )
    evidence = _project_path(root, EVIDENCE_PATH.as_posix(), "profile evidence")
    return AnalysisConfig(
        root=root,
        portforge=portforge,
        image=image,
        companions=companions,
        executable=executable,
        hunk_sha256=hunk_sha256,
        machine_model=machine_model,
        load_base=load_base,
        module_entry=module_entry,
        evidence=evidence,
        lift_plan=lift_plan,
        atlas_blocks=atlas_blocks,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_asset(asset: PinnedAsset) -> None:
    if not asset.path.is_file():
        raise RuntimeError(f"{asset.name} is absent: {asset.path}")
    actual_size = asset.path.stat().st_size
    if actual_size != asset.size:
        raise RuntimeError(
            f"{asset.name} size mismatch: expected {asset.size}, "
            f"got {actual_size}"
        )
    actual_hash = _sha256(asset.path)
    if actual_hash != asset.sha256:
        raise RuntimeError(
            f"{asset.name} SHA-256 mismatch: expected {asset.sha256}, "
            f"got {actual_hash}"
        )


def verify_inputs(config: AnalysisConfig) -> str:
    _verify_asset(config.image)
    for companion in config.companions:
        _verify_asset(companion)
    evidence = _load_object(config.evidence)
    if evidence.get("format") != "pf-replay-evidence-v3":
        raise RuntimeError(
            f"{config.evidence}: expected pf-replay-evidence-v3"
        )
    bindings = evidence.get("bindings")
    replay_binding = (
        bindings.get("replay_artifact")
        if isinstance(bindings, dict)
        else None
    )
    replay_identity = (
        replay_binding.get("replay_identity")
        if isinstance(replay_binding, dict)
        else None
    )
    if (
        not isinstance(replay_binding, dict)
        or replay_binding.get("format") != "portforge-replay-v2"
        or not isinstance(replay_identity, dict)
    ):
        raise RuntimeError(
            f"{config.evidence}: ReplayArtifactV2 binding is missing"
        )
    if replay_identity.get("program_sha256") != config.image.sha256:
        raise RuntimeError(
            f"{config.evidence}: evidence belongs to another disk image"
        )
    if replay_identity.get("machine_model") != config.machine_model:
        raise RuntimeError(
            f"{config.evidence}: evidence belongs to another machine model"
        )
    for name in ("sha256", "replay_identity_sha256"):
        value = replay_binding.get(name)
        if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
            raise RuntimeError(
                f"{config.evidence}: replay binding {name} is invalid"
            )
    extensions = evidence.get("extensions")
    identity = (
        extensions.get("org.portforge.amiga.execution-image")
        if isinstance(extensions, dict)
        else None
    )
    if (
        not isinstance(identity, dict)
        or identity.get("format") != "pf-amiga-execution-image-v1"
        or identity.get("identity_model")
        != "adf-sha256+program+hunk-sha256+load-base+module-entry"
        or identity.get("program") != config.executable
        or identity.get("hunk_sha256") != config.hunk_sha256
        or identity.get("load_base") != config.load_base
        or identity.get("module_entry") != config.module_entry
    ):
        raise RuntimeError(
            f"{config.evidence}: exact direct-HUNK identity is missing or "
            "does not match the project"
        )
    return _sha256(config.evidence)


def _address(value: Any, label: str) -> int:
    if not isinstance(value, str) or not ADDRESS_PATTERN.fullmatch(value):
        raise RuntimeError(f"{label} is not a canonical 24-bit address")
    return int(value, 16)


def _identity(address: int) -> str:
    if not 0 <= address <= 0xFFFFFF:
        raise RuntimeError(f"address is outside Amiga memory: {address:#x}")
    return f"amiga:{address:06X}"


def lift_plan_to_atlas_blocks(
    plan: dict[str, Any],
    *,
    program_sha256: str,
    machine_model: str,
) -> dict[str, Any]:
    """Convert one validated lift plan to the Atlas recovered-block wire form."""

    if plan.get("format") != "portforge-amiga-lift-plan-v1":
        raise RuntimeError("analyzer returned an unsupported lift-plan format")
    if (
        plan.get("artifact_role")
        != "resident-static-recovery-plan-not-generated-port"
    ):
        raise RuntimeError("lift plan overstates or omits its artifact role")
    if plan.get("program_sha256") != program_sha256:
        raise RuntimeError("lift plan belongs to another disk image")
    if plan.get("machine_model") != machine_model:
        raise RuntimeError("lift plan belongs to another machine model")
    if plan.get("address_model") != "amiga-24-bit-linear":
        raise RuntimeError("lift plan has an unsupported address model")
    if plan.get("generated_execution_closure") is not False:
        raise RuntimeError("lift plan unexpectedly claims generated execution")
    if plan.get("generated_native_block_count") != 0:
        raise RuntimeError("lift plan unexpectedly claims generated blocks")

    raw_instructions = plan.get("instructions")
    if not isinstance(raw_instructions, list):
        raise RuntimeError("lift plan instructions must be an array")
    instructions: dict[int, dict[str, Any]] = {}
    for index, instruction in enumerate(raw_instructions):
        if not isinstance(instruction, dict):
            raise RuntimeError(f"instruction {index} is malformed")
        start = _address(
            instruction.get("address"), f"instruction {index}.address"
        )
        if start in instructions:
            raise RuntimeError(f"duplicate instruction address {start:06X}")
        length = instruction.get("length")
        if (
            not isinstance(length, int)
            or isinstance(length, bool)
            or length < 2
            or length % 2
            or start + length > 0x1000000
        ):
            raise RuntimeError(f"instruction {start:06X} has invalid length")
        instructions[start] = instruction

    raw_blocks = plan.get("blocks")
    if not isinstance(raw_blocks, list):
        raise RuntimeError("lift plan blocks must be an array")
    converted: list[tuple[int, int, dict[str, Any]]] = []
    block_entries: set[int] = set()
    previous_end = -1
    for index, block in enumerate(
        sorted(
            raw_blocks,
            key=lambda value: (
                value.get("entry", "")
                if isinstance(value, dict)
                else ""
            ),
        )
    ):
        if not isinstance(block, dict):
            raise RuntimeError(f"block {index} is malformed")
        entry = _address(block.get("entry"), f"block {index}.entry")
        end = _address(block.get("end"), f"block {index}.end")
        if entry in block_entries:
            raise RuntimeError(f"duplicate block entry {entry:06X}")
        if end <= entry or entry < previous_end:
            raise RuntimeError(f"block {entry:06X} has an invalid span")
        raw_addresses = block.get("instructions")
        if not isinstance(raw_addresses, list) or not raw_addresses:
            raise RuntimeError(f"block {entry:06X} has no instructions")
        addresses = [
            _address(value, f"block {entry:06X}.instructions")
            for value in raw_addresses
        ]
        if addresses[0] != entry or addresses != sorted(set(addresses)):
            raise RuntimeError(
                f"block {entry:06X} instruction order is inconsistent"
            )
        cursor = entry
        for instruction_address in addresses:
            instruction = instructions.get(instruction_address)
            if instruction is None:
                raise RuntimeError(
                    f"block {entry:06X} references an unknown instruction "
                    f"{instruction_address:06X}"
                )
            if instruction_address != cursor:
                raise RuntimeError(
                    f"block {entry:06X} has a non-contiguous instruction span"
                )
            cursor += instruction["length"]
        if cursor != end:
            raise RuntimeError(
                f"block {entry:06X} end does not match decoded bytes"
            )
        atlas_block = {
            "id": _identity(entry),
            "end": _identity(end),
            "instructions": len(addresses),
        }
        converted.append((entry, end, atlas_block))
        block_entries.add(entry)
        previous_end = end

    raw_seeds = plan.get("seeds")
    if not isinstance(raw_seeds, list):
        raise RuntimeError("lift plan seeds must be an array")
    seeded_entries: set[int] = set()
    for index, seed in enumerate(raw_seeds):
        if not isinstance(seed, dict):
            raise RuntimeError(f"seed {index} is malformed")
        value = _address(seed.get("address"), f"seed {index}.address")
        if value in block_entries:
            seeded_entries.add(value)
    module_entry = _address(plan.get("module_entry"), "module_entry")
    if module_entry in block_entries:
        seeded_entries.add(module_entry)

    return {
        "format": "pf-recovered-blocks-v1",
        "program_sha256": program_sha256,
        "identity_model": "amiga-24-bit-linear",
        "program_entries": len(seeded_entries),
        "entry_points": [
            _identity(value) for value in sorted(seeded_entries)
        ],
        "blocks": [record for _, _, record in converted],
    }


def _relative(config: AnalysisConfig, path: Path) -> str:
    return path.resolve().relative_to(config.root).as_posix()


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _canonical_json(value: dict[str, Any]) -> str:
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )


def run_analysis(
    config: AnalysisConfig,
    *,
    build: bool,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence_sha256 = verify_inputs(config)
    if build:
        runner(
            [
                sys.executable,
                str(config.portforge / "build.py"),
                "--no-tests",
                "--targets",
                "pf_amiga_analyze",
            ],
            cwd=config.portforge,
            check=True,
        )
    analyzer = config.portforge / "build" / "pf_amiga_analyze.exe"
    if not analyzer.is_file():
        analyzer = analyzer.with_suffix("")
    if not analyzer.is_file():
        raise RuntimeError(f"static analyzer is not built: {analyzer}")

    build_root = config.root / "build"
    build_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="amiga-analysis-", dir=build_root
    ) as temporary_name:
        staged_lift = Path(temporary_name) / "lift-plan.json"
        runner(
            [
                str(analyzer),
                _relative(config, config.image.path),
                config.executable,
                _relative(config, staged_lift),
                "--load-base",
                hex(config.load_base),
                "--profile",
                _relative(config, config.evidence),
            ],
            cwd=config.root,
            check=True,
        )
        plan = _load_object(staged_lift)
        plan_image = _project_path(
            config.root, plan.get("image"), "lift image"
        )
        if plan_image != config.image.path:
            raise RuntimeError("lift plan reports an unexpected image path")
        if plan.get("program") != config.executable:
            raise RuntimeError("lift plan reports an unexpected executable")
        profiles = plan.get("profiles")
        if not isinstance(profiles, list) or len(profiles) != 1:
            raise RuntimeError("lift plan must bind exactly one profile")
        profile = profiles[0]
        if not isinstance(profile, dict):
            raise RuntimeError("lift plan profile record is malformed")
        profile_path = _project_path(
            config.root, profile.get("path"), "lift profile"
        )
        if profile_path != config.evidence:
            raise RuntimeError("lift plan used unexpected profile evidence")
        if profile.get("sha256") != evidence_sha256:
            raise RuntimeError("lift plan profile digest is stale")

        blocks = lift_plan_to_atlas_blocks(
            plan,
            program_sha256=config.image.sha256,
            machine_model=config.machine_model,
        )
        lift_text = _canonical_json(plan)
        blocks_text = _canonical_json(blocks)

    _write_atomic(config.lift_plan, lift_text)
    _write_atomic(config.atlas_blocks, blocks_text)
    return plan, blocks


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Recover resident DuckTales M68000 blocks and materialize the "
            "Execution Atlas block source."
        )
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="use the existing port_forge/build/pf_amiga_analyze executable",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    options = argument_parser().parse_args(argv)
    config = load_configuration()
    plan, blocks = run_analysis(config, build=not options.no_build)
    print(f"lift plan: {_relative(config, config.lift_plan)}")
    print(f"Atlas blocks: {_relative(config, config.atlas_blocks)}")
    print(
        "recovered: "
        f"{plan['decoded_instruction_count']} resident instructions, "
        f"{len(blocks['blocks'])} basic blocks, "
        f"{plan['external_dynamic_seed_count']} external/dynamic seeds"
    )
    print(
        "closure: resident static evidence only; emitter eligibility does "
        "not claim whole-program or overlay closure"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        RuntimeError,
        ValueError,
        subprocess.SubprocessError,
    ) as error:
        print(f"analyze.py: {error}", file=sys.stderr)
        raise SystemExit(1)
