#!/usr/bin/env python3
"""Certify DuckTales against PortForge's fail-closed Amiga OCS subset.

This is intentionally separate from replay equality. It runs the original
HUNK interpreter with strict unsupported-feature handling and requires a clean
capability trace, deterministic rerun, and exact persistent snapshot roundtrip.
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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_asset(record: dict, label: str) -> Path:
    path = ROOT / "assets" / record["file"]
    if not path.is_file():
        raise RuntimeError(f"missing {label}: {path}")
    if path.stat().st_size != record["size"]:
        raise RuntimeError(f"{label} size does not match game.json")
    if file_sha256(path) != record["sha256"]:
        raise RuntimeError(f"{label} SHA-256 does not match game.json")
    return path


def validate_report(report: dict, minimum_instructions: int) -> list[str]:
    errors: list[str] = []
    if report.get("format") != "pf-amiga-run-v1":
        errors.append("runner did not emit pf-amiga-run-v1")
    if report.get("execution_mode") != "amiga-oracle":
        errors.append("execution was not the M68000 oracle")
    if report.get("status") not in {"step-limit", "exited"}:
        errors.append(f"non-certifiable terminal status: {report.get('status')!r}")
    instructions = report.get("instructions")
    if not isinstance(instructions, int) or instructions < minimum_instructions:
        errors.append(
            f"executed {instructions!r} instructions, expected at least "
            f"{minimum_instructions}"
        )
    for field in ("unknown_reads", "unknown_writes",
                  "unsupported_cia_read_mask", "unsupported_cia_write_mask"):
        if report.get(field) != 0:
            errors.append(f"{field} is {report.get(field)!r}, expected zero")
    for field in ("unsupported_custom_reads", "unsupported_custom_writes"):
        if report.get(field) != []:
            errors.append(f"{field} is not empty")
    if report.get("deterministic_rerun") is not True:
        errors.append("deterministic rerun failed")
    if report.get("snapshot_roundtrip") is not True:
        errors.append("persistent snapshot roundtrip failed")
    digest = report.get("canonical_digest")
    if not isinstance(digest, str) or len(digest) != 64:
        errors.append("canonical digest is absent or malformed")
    if report.get("diagnostic"):
        errors.append(f"runner diagnostic is non-empty: {report['diagnostic']}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=1_000_000)
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.steps < 1:
        raise RuntimeError("--steps must be positive")

    game = json.loads((ROOT / "game.json").read_text(encoding="utf-8"))
    disk1 = require_asset(game["program"], "disk 1")
    disk2 = require_asset(game["companion_assets"]["disk2"], "disk 2")
    runner = PORT_FORGE / "build" / "pf_amiga_run.exe"
    if not args.no_build:
        subprocess.run(
            [sys.executable, "build.py", "--no-tests", "--targets",
             "pf_amiga_run"], cwd=PORT_FORGE, check=True
        )
    if not runner.is_file():
        raise RuntimeError(f"missing PortForge runner: {runner}")

    completed = subprocess.run(
        [str(runner), str(disk1), game["program"]["executable"],
         "--disk", str(disk2), "--steps", str(args.steps),
         "--oracle", "--strict"],
        cwd=ROOT, text=True, capture_output=True
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"strict runner exited {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    report = json.loads(completed.stdout)
    errors = validate_report(report, args.steps)
    certification = {
        "format": "tales-amiga-oracle-certification-v1",
        "certified": not errors,
        "program_sha256": game["program"]["sha256"],
        "companion_sha256": game["companion_assets"]["disk2"]["sha256"],
        "minimum_instructions": args.steps,
        "canonical_digest": report.get("canonical_digest"),
        "frame": report.get("frame"),
        "master_tick": report.get("master_tick"),
        "errors": errors,
    }
    text = json.dumps(certification, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if not errors else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, KeyError, ValueError,
            subprocess.CalledProcessError) as error:
        print(f"certify_amiga_oracle.py: {error}", file=sys.stderr)
        raise SystemExit(2)
