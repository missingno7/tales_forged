from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "build_generated.py"
)
SPEC = importlib.util.spec_from_file_location(
    "tales_build_generated", SCRIPT
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import {SCRIPT}")
build_generated = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = build_generated
SPEC.loader.exec_module(build_generated)


class GeneratedBuildContractTests(unittest.TestCase):
    def test_comparison_is_canonical_state_not_runtime_counters(self) -> None:
        report = {
            "execution_mode": "amiga-native",
            "native_blocks": 7,
            "interpreter_fallback_steps": 9,
            "status": "step-limit",
            "diagnostic": "",
            "instructions": 16,
            "cpu_cycles": 100,
            "master_tick": 200,
            "frame": 1,
            "raster_v": 2,
            "raster_h": 3,
            "pc": 0x10000,
            "status_register": 0x2000,
            "data_registers": [0] * 8,
            "address_registers": [0] * 8,
            "canonical_digest": "a" * 64,
            "service_calls": 4,
            "visible_output": True,
        }
        compared = build_generated.comparable(report)
        self.assertNotIn("execution_mode", compared)
        self.assertNotIn("native_blocks", compared)
        self.assertNotIn("interpreter_fallback_steps", compared)
        self.assertEqual(compared["canonical_digest"], "a" * 64)
        self.assertEqual(compared["cpu_cycles"], 100)

    def test_cached_verification_binds_every_input_and_clean_producer(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            old = build_generated.VERIFICATION
            try:
                build_generated.VERIFICATION = (
                    Path(temporary) / "verification.json"
                )
                inputs = {"generated_header": "a" * 64}
                producer = {
                    "portforge_revision": "b" * 40,
                    "portforge_dirty": False,
                    "compiler": "g++",
                }
                build_generated.VERIFICATION.write_text(
                    json.dumps(
                        {
                            "format": (
                                "portforge-amiga-generated-verification-v2"
                            ),
                            "equivalent": True,
                            "inputs": inputs,
                            "producer": producer,
                            "instruction_budget": 50,
                        }
                    ),
                    encoding="utf-8",
                )
                self.assertTrue(
                    build_generated.cached_verification_valid(
                        inputs, producer, 50
                    )
                )
                self.assertFalse(
                    build_generated.cached_verification_valid(
                        {"generated_header": "c" * 64},
                        producer,
                        50,
                    )
                )
                self.assertFalse(
                    build_generated.cached_verification_valid(
                        inputs,
                        {**producer, "portforge_dirty": True},
                        50,
                    )
                )
            finally:
                build_generated.VERIFICATION = old

    def test_replay_gate_uses_artifact_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            replay = Path(temporary) / "replay.json"
            replay.write_text(
                json.dumps(
                    {"format": "portforge-replay-v2",
                        "events": [
                            {"sequence": 0},
                            {"sequence": 1},
                            {"sequence": 2},
                        ],
                        "terminal": {
                            "schema": "pf-replay-terminal-v3",
                            "stamp": {
                                "schema": "pf-boundary-stamp-v1",
                                "global_ordinal": 40,
                                "outcome": "terminal",
                            },
                            "canonical_sha256": "a" * 64,
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                build_generated.replay_terminal(replay), (40, "a" * 64)
            )
            self.assertEqual(
                build_generated.replay_event_count(replay), 3
            )
            replay.write_text(
                json.dumps({
                    "format": "portforge-replay-v2",
                    "events": [{}],
                    "terminal": {
                        "schema": "pf-replay-terminal-v3",
                        "stamp": {
                            "schema": "pf-boundary-stamp-v1",
                            "global_ordinal": "40",
                            "outcome": "terminal",
                        },
                        "canonical_sha256": "a" * 64,
                    },
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                RuntimeError, "invalid ReplayArtifactV2 terminal"
            ):
                build_generated.replay_terminal(replay)


if __name__ == "__main__":
    unittest.main()
