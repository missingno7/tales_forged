from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATE = ROOT / "scripts" / "migrate_v1_replay.py"


class ReplayMigrationTests(unittest.TestCase):
    def test_pal_timeline_is_scaled_and_bound_to_v3_launch(self) -> None:
        launch = "a" * 64
        source_value = {
            "events": [
                {"kind": "fire1", "master_tick": 0, "value": 1},
                {"kind": "fire1", "master_tick": 910, "value": 0},
                {"kind": "key-raw", "master_tick": 1365, "value": 64},
            ],
            "format": "portforge-amiga-replay-v1",
            "machine_model": "pf-amiga-a500-ocs-pal-v1",
            "program_sha256": "b" * 64,
        }
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "legacy.json"
            destination = Path(temporary) / "migrated.json"
            source.write_text(json.dumps(source_value), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(MIGRATE),
                    str(source),
                    str(destination),
                    "--launch-sha256",
                    launch,
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            migrated = json.loads(destination.read_text(encoding="utf-8"))

        self.assertEqual(migrated["format"], "portforge-amiga-replay-v2")
        self.assertEqual(migrated["machine_model"], "pf-amiga-a500-ocs-pal-v3")
        self.assertEqual(migrated["launch_sha256"], launch)
        self.assertEqual(
            [event["master_tick"] for event in migrated["events"]],
            [0, 1816, 2724],
        )
        self.assertEqual(source_value["events"][1]["master_tick"], 910)

    def test_rejects_a_non_v1_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "wrong.json"
            destination = Path(temporary) / "migrated.json"
            source.write_text(
                json.dumps(
                    {
                        "events": [],
                        "format": "portforge-amiga-replay-v2",
                        "machine_model": "pf-amiga-a500-ocs-pal-v3",
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(MIGRATE),
                    str(source),
                    str(destination),
                    "--launch-sha256",
                    "a" * 64,
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("legacy PAL-v1", result.stderr)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
