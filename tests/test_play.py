from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAY = ROOT / "scripts" / "play.py"


def dry_run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PLAY), "--dry-run", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


class PlayAdapterTests(unittest.TestCase):
    def test_plain_launch_is_interactive_oracle_viewer(self) -> None:
        result = dry_run("--runtime", "oracle")
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.splitlines()[-1]
        self.assertIn("pf_amiga_view.exe", command)
        self.assertNotIn(" --steps ", command)

    def test_headless_oracle_uses_artifact_and_explicit_plan(self) -> None:
        result = dry_run(
            "--runtime",
            "oracle",
            "--headless",
            "--steps",
            "100",
            "--replay-artifact",
            "cold5",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.splitlines()[-1]
        self.assertIn("pf_amiga_run.exe", command)
        self.assertIn(" --oracle ", command)
        self.assertIn(" --replay-artifact ", command)
        self.assertIn("cold5.pfreplay.json", command)
        self.assertIn("oracle-interpreter.json", command)

    def test_forwarded_viewer_option_does_not_force_headless(self) -> None:
        result = dry_run("--runtime", "oracle", "--", "--mute")
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.splitlines()[-1]
        self.assertIn("pf_amiga_view.exe", command)
        self.assertTrue(command.endswith("--mute"), command)

    def test_headless_snapshot_uses_runner(self) -> None:
        result = dry_run("--headless", "--snapshot", "checkpoint")
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.splitlines()[-1]
        self.assertIn("pf_amiga_run.exe", command)
        self.assertIn("checkpoint.pfamigasnapshot", command)
        self.assertNotIn("recover-int-vector", command)

    def test_generated_runtime_has_distinct_guarded_runners(self) -> None:
        interactive = dry_run("--runtime", "generated")
        self.assertEqual(
            interactive.returncode, 0, interactive.stderr
        )
        self.assertIn(
            "ducktales_amiga_generated_view.exe",
            interactive.stdout.splitlines()[-1],
        )
        self.assertIn(
            "fallback: interpreter-and-smc", interactive.stdout
        )

        headless = dry_run(
            "--runtime",
            "generated",
            "--headless",
            "--steps",
            "100",
            "--replay-artifact",
            "cold5",
        )
        self.assertEqual(headless.returncode, 0, headless.stderr)
        command = headless.stdout.splitlines()[-1]
        self.assertIn(
            "ducktales_amiga_generated_run.exe", command
        )
        self.assertIn(" --native ", command)
        self.assertNotIn(" --oracle ", command)
        self.assertIn("generated-plus-fallback.json", command)

    def test_recording_uses_neutral_schedule_and_artifact_contract(self) -> None:
        result = dry_run(
            "--headless",
            "--record-artifact",
            "fresh",
            "--input-schedule",
            "recovery/migration/cold5-input-schedule-v1.json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.splitlines()[-1]
        self.assertIn(" --record-artifact ", command)
        self.assertIn(" --input-schedule ", command)
        self.assertNotIn("--record-replay", command)
        self.assertNotIn("--replay-inputs", command)

    def test_legacy_replay_flags_are_unknown(self) -> None:
        for flag in ("--replay-inputs", "--record-replay"):
            with self.subTest(flag=flag):
                result = dry_run("--headless", flag, "cold5")
                self.assertNotEqual(result.returncode, 0)

    def test_live_atlas_is_interactive_and_uses_project_artifact(self) -> None:
        result = dry_run(
            "--runtime",
            "oracle",
            "--live-atlas",
            "--atlas-interval",
            "3",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.splitlines()[-1]
        self.assertIn("pf_amiga_view.exe", command)
        self.assertIn(" --live-atlas ", command)
        self.assertIn("atlas.pfatlas", command)
        self.assertIn(" --atlas-interval 3", command)

        rejected = dry_run("--headless", "--live-atlas")
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn(
            "--live-atlas requires interactive play",
            rejected.stderr,
        )


if __name__ == "__main__":
    unittest.main()
