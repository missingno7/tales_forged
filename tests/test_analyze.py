#!/usr/bin/env python3
"""Focused tests for the DuckTales Amiga recovery launcher."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "analyze.py"
SPEC = importlib.util.spec_from_file_location("tales_analyze", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import {SCRIPT}")
analyze = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = analyze
SPEC.loader.exec_module(analyze)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sample_plan(
    program_sha256: str,
    profile_sha256: str = "b" * 64,
) -> dict:
    return {
        "format": "portforge-amiga-lift-plan-v1",
        "artifact_role": "resident-static-recovery-plan-not-generated-port",
        "image": "assets/disk1.adf",
        "program": "Fixture",
        "program_sha256": program_sha256,
        "hunk_sha256": "c" * 64,
        "machine_model": "pf-amiga-a500-ocs-pal-v1",
        "address_model": "amiga-24-bit-linear",
        "module_entry": "010000",
        "profiles": [
            {
                "path": "artifacts/amiga/ducktales-evidence.json",
                "sha256": profile_sha256,
                "format": "pf-atlas-evidence-v2",
            }
        ],
        "instructions": [
            {"address": "010000", "length": 2},
            {"address": "010002", "length": 4},
            {"address": "010010", "length": 2},
        ],
        "blocks": [
            {
                "entry": "010010",
                "end": "010012",
                "instructions": ["010010"],
            },
            {
                "entry": "010000",
                "end": "010006",
                "instructions": ["010000", "010002"],
            },
        ],
        "seeds": [
            {"address": "010010", "sources": ["profile"]},
            {"address": "010002", "sources": ["relocation"]},
            {"address": "010000", "sources": ["entry"]},
        ],
        "decoded_instruction_count": 3,
        "basic_block_count": 2,
        "external_dynamic_seed_count": 0,
        "generated_native_block_count": 0,
        "generated_execution_closure": False,
    }


class LiftConversionTests(unittest.TestCase):
    def test_conversion_is_canonical_and_atlas_compatible(self):
        program_sha256 = "a" * 64
        result = analyze.lift_plan_to_atlas_blocks(
            sample_plan(program_sha256),
            program_sha256=program_sha256,
            machine_model="pf-amiga-a500-ocs-pal-v1",
        )
        self.assertEqual(
            result,
            {
                "format": "pf-recovered-blocks-v1",
                "program_sha256": program_sha256,
                "identity_model": "amiga-24-bit-linear",
                "program_entries": 2,
                "entry_points": ["amiga:010000", "amiga:010010"],
                "blocks": [
                    {
                        "id": "amiga:010000",
                        "end": "amiga:010006",
                        "instructions": 2,
                    },
                    {
                        "id": "amiga:010010",
                        "end": "amiga:010012",
                        "instructions": 1,
                    },
                ],
            },
        )
        self.assertEqual(
            analyze._canonical_json(result),
            analyze._canonical_json(
                analyze.lift_plan_to_atlas_blocks(
                    sample_plan(program_sha256),
                    program_sha256=program_sha256,
                    machine_model="pf-amiga-a500-ocs-pal-v1",
                )
            ),
        )

    def test_conversion_rejects_inconsistent_instruction_span(self):
        plan = sample_plan("a" * 64)
        plan["blocks"][1]["end"] = "010008"
        with self.assertRaisesRegex(RuntimeError, "end does not match"):
            analyze.lift_plan_to_atlas_blocks(
                plan,
                program_sha256="a" * 64,
                machine_model="pf-amiga-a500-ocs-pal-v1",
            )

    def test_conversion_rejects_generated_execution_claim(self):
        plan = sample_plan("a" * 64)
        plan["generated_execution_closure"] = True
        with self.assertRaisesRegex(RuntimeError, "generated execution"):
            analyze.lift_plan_to_atlas_blocks(
                plan,
                program_sha256="a" * 64,
                machine_model="pf-amiga-a500-ocs-pal-v1",
            )


class AnalysisWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "assets").mkdir()
        (self.root / "artifacts/amiga").mkdir(parents=True)
        (self.root / "port_forge/build").mkdir(parents=True)
        self.disk1 = b"disk one"
        self.disk2 = b"disk two"
        (self.root / "assets/disk1.adf").write_bytes(self.disk1)
        (self.root / "assets/disk2.adf").write_bytes(self.disk2)
        self.program_sha256 = digest(self.disk1)
        self.evidence = {
            "format": "pf-atlas-evidence-v2",
            "program_sha256": self.program_sha256,
            "machine_model": "pf-amiga-a500-ocs-pal-v1",
            "replay": {"fingerprint": "d" * 64},
            "extensions": {
                "org.portforge.amiga.execution-image": {
                    "format": "pf-amiga-execution-image-v1",
                    "identity_model": (
                        "adf-sha256+program+hunk-sha256+load-base+"
                        "module-entry"
                    ),
                    "program": "Fixture",
                    "hunk_sha256": "c" * 64,
                    "load_base": 0x10000,
                    "module_entry": 0x10000,
                }
            },
        }
        self._write(
            "artifacts/amiga/ducktales-evidence.json", self.evidence
        )
        self.evidence_sha256 = digest(
            (
                self.root
                / "artifacts/amiga/ducktales-evidence.json"
            ).read_bytes()
        )
        self._write(
            "game.json",
            {
                "format": "portforge-game-v0",
                "platform": "amiga",
                "program": {
                    "file": "disk1.adf",
                    "sha256": self.program_sha256,
                    "hunk_sha256": "c" * 64,
                    "size": len(self.disk1),
                    "executable": "Fixture",
                },
                "companion_assets": {
                    "disk2": {
                        "file": "disk2.adf",
                        "sha256": digest(self.disk2),
                        "size": len(self.disk2),
                        "role": "companion disk",
                    }
                },
                "machine": {
                    "profile": "a500-ocs-pal",
                    "direct_hunk_bootstrap": True,
                    "load_base": "0x10000",
                    "module_entry": "0x10000",
                },
            },
        )
        self._write(
            "portforge.project.json",
            {
                "format": "portforge-project-v1",
                "game": "game.json",
                "portforge": "port_forge",
                "assets": "assets",
                "artifacts": {
                    "lift_plan": (
                        "artifacts/generated/amiga/lift-plan.json"
                    ),
                    "blocks": "artifacts/generated/amiga/blocks.json",
                },
            },
        )
        (self.root / "port_forge/build/pf_amiga_analyze.exe").write_bytes(
            b"fixture"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def _write(self, relative: str, value) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_workflow_verifies_assets_and_materializes_both_artifacts(self):
        config = analyze.load_configuration(self.root)
        commands = []

        def runner(command, *, cwd, check):
            self.assertTrue(check)
            commands.append((command, cwd))
            output = self.root / command[3]
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(
                    sample_plan(
                        self.program_sha256, self.evidence_sha256
                    )
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0)

        plan, blocks = analyze.run_analysis(
            config, build=False, runner=runner
        )
        self.assertEqual(plan["format"], "portforge-amiga-lift-plan-v1")
        self.assertEqual(blocks["format"], "pf-recovered-blocks-v1")
        self.assertEqual(len(commands), 1)
        command, cwd = commands[0]
        self.assertEqual(cwd, self.root)
        self.assertEqual(command[1], "assets/disk1.adf")
        self.assertEqual(command[2], "Fixture")
        self.assertEqual(
            command[-1], "artifacts/amiga/ducktales-evidence.json"
        )
        self.assertTrue(config.lift_plan.is_file())
        self.assertTrue(config.atlas_blocks.is_file())
        persisted = json.loads(
            config.atlas_blocks.read_text(encoding="utf-8")
        )
        self.assertEqual(persisted, blocks)

    def test_failed_analyzer_preserves_existing_outputs(self):
        config = analyze.load_configuration(self.root)
        config.lift_plan.parent.mkdir(parents=True)
        config.lift_plan.write_text("old lift", encoding="utf-8")
        config.atlas_blocks.write_text("old blocks", encoding="utf-8")

        def runner(command, *, cwd, check):
            raise subprocess.CalledProcessError(1, command)

        with self.assertRaises(subprocess.CalledProcessError):
            analyze.run_analysis(config, build=False, runner=runner)
        self.assertEqual(
            config.lift_plan.read_text(encoding="utf-8"), "old lift"
        )
        self.assertEqual(
            config.atlas_blocks.read_text(encoding="utf-8"), "old blocks"
        )

    def test_changed_companion_disk_fails_before_analyzer(self):
        config = analyze.load_configuration(self.root)
        (self.root / "assets/disk2.adf").write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeError, "size mismatch"):
            analyze.run_analysis(
                config,
                build=False,
                runner=lambda *args, **kwargs: self.fail(
                    "analyzer must not run"
                ),
            )


if __name__ == "__main__":
    unittest.main()
