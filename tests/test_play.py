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

    def test_headless_oracle_is_explicit_and_uses_standard_replay(self) -> None:
        result = dry_run(
            "--runtime",
            "oracle",
            "--headless",
            "--steps",
            "100",
            "--replay-inputs",
            "cold5",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.splitlines()[-1]
        self.assertIn("pf_amiga_run.exe", command)
        self.assertIn(" --oracle ", command)
        self.assertIn("cold5.pfreplay.json", command)

    def test_forwarded_viewer_option_does_not_force_headless(self) -> None:
        result = dry_run("--runtime", "oracle", "--", "--mute")
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.splitlines()[-1]
        self.assertIn("pf_amiga_view.exe", command)
        self.assertTrue(command.endswith("--mute"), command)

    def test_headless_snapshot_uses_runner_and_legacy_vector_evidence(self) -> None:
        result = dry_run("--headless", "--snapshot", "checkpoint")
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.splitlines()[-1]
        self.assertIn("pf_amiga_run.exe", command)
        self.assertIn("checkpoint.pfamigasnapshot", command)
        self.assertIn("--recover-int-vector 7:0x240e6:1", command)
        self.assertIn("--recover-int-vector 10:0x24128:4", command)

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
            "--replay-inputs",
            "cold5",
        )
        self.assertEqual(headless.returncode, 0, headless.stderr)
        command = headless.stdout.splitlines()[-1]
        self.assertIn(
            "ducktales_amiga_generated_run.exe", command
        )
        self.assertIn(" --native ", command)
        self.assertNotIn(" --oracle ", command)

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
