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
    def test_help_exposes_complete_development_workflows(self) -> None:
        result = subprocess.run(
            [sys.executable, str(PLAY), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for capability in (
            "--record-replay [NAME]",
            "--play-replay NAME",
            "--verify-replay NAME",
            "--inspect-replay NAME",
            "--snapshot NAME|PATH",
            "--snapshot-out NAME|PATH",
            "--inspect-snapshot NAME|PATH",
            "--verify-snapshot NAME|PATH",
            "--live-atlas [PATH]",
            "--update-atlas",
            "--headless",
            "--input-schedule PATH",
            "--capture-audio PATH",
            "F10",
            "F11",
            "F12",
            "--                      forward",
        ):
            self.assertIn(capability, result.stdout)

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
            "shared-amiga-calibration",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.splitlines()[-1]
        self.assertIn("pf_amiga_run.exe", command)
        self.assertIn(" --oracle ", command)
        self.assertIn(" --replay-artifact ", command)
        self.assertIn("shared-amiga-calibration.pfreplay.json", command)
        self.assertIn("oracle-interpreter.json", command)

    def test_replay_can_use_interactive_semantic_viewer(self) -> None:
        result = dry_run(
            "--runtime", "oracle", "--replay-artifact", "shared-amiga-calibration"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.splitlines()[-1]
        self.assertIn("pf_amiga_view.exe", command)
        self.assertNotIn(" --steps ", command)
        self.assertIn(" --replay-artifact ", command)
        self.assertIn("shared-amiga-calibration.pfreplay.json", command)

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
            "shared-amiga-calibration",
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

    def test_human_recording_uses_interactive_semantic_session(self) -> None:
        result = dry_run(
            "--runtime",
            "oracle",
            "--record-artifact",
            "human-session",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.splitlines()[-1]
        self.assertIn("pf_amiga_view.exe", command)
        self.assertNotIn(" --steps ", command)
        self.assertIn(" --record-artifact ", command)
        self.assertIn("human-session.pfreplay.json", command)
        self.assertIn(" --boundary-profile ", command)
        self.assertIn("oracle-interpreter.json", command)

    def test_unnamed_human_recording_uses_a_timestamped_artifact(self) -> None:
        result = dry_run("--runtime", "oracle", "--record-replay")
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.splitlines()[-1]
        self.assertIn("pf_amiga_view.exe", command)
        self.assertIn(" --record-artifact ", command)
        self.assertRegex(
            command,
            r"artifacts[\\/]replays[\\/]rec_\d{8}_\d{6}\.pfreplay\.json",
        )

    def test_interactive_recording_can_start_from_snapshot(self) -> None:
        result = dry_run(
            "--record-artifact",
            "from-save",
            "--snapshot",
            "checkpoint",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.splitlines()[-1]
        self.assertIn("pf_amiga_view.exe", command)
        self.assertIn("from-save.pfreplay.json", command)
        self.assertIn("checkpoint.pfamigasnapshot", command)

    def test_compatibility_replay_names_map_only_to_artifact_v2(self) -> None:
        for flag in ("--replay-inputs", "--play-replay"):
            with self.subTest(flag=flag):
                result = dry_run(
                    "--headless", flag, "shared-amiga-calibration"
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                command = result.stdout.splitlines()[-1]
                self.assertIn(" --replay-artifact ", command)
                self.assertNotIn(" --replay-inputs ", command)
                self.assertNotIn(" --play-replay ", command)
        recorded = dry_run("--record-replay", "human")
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        command = recorded.stdout.splitlines()[-1]
        self.assertIn(" --record-artifact ", command)
        self.assertNotIn(" --record-replay ", command)

    def test_strict_replay_verification_is_headless(self) -> None:
        result = dry_run("--verify-replay", "shared-amiga-calibration")
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.splitlines()[-1]
        self.assertIn("pf_amiga_run.exe", command)
        self.assertIn(" --replay-artifact ", command)
        self.assertIn(" --strict", command)

    def test_common_replay_and_snapshot_inspection_tools(self) -> None:
        replay = dry_run(
            "--inspect-replay", "shared-amiga-calibration", "--", "--json"
        )
        self.assertEqual(replay.returncode, 0, replay.stderr)
        command = replay.stdout.splitlines()[-1]
        self.assertIn("pf_artifact.exe inspect", command)
        self.assertIn("shared-amiga-calibration.pfreplay.json", command)
        self.assertTrue(command.endswith("--json"), command)

        snapshot = dry_run("--inspect-snapshot", "checkpoint")
        self.assertEqual(snapshot.returncode, 0, snapshot.stderr)
        self.assertIn(
            "pf_artifact.exe inspect-session",
            snapshot.stdout.splitlines()[-1],
        )
        self.assertIn(
            "checkpoint.pfamigasnapshot.pfsession.json",
            snapshot.stdout.splitlines()[-1],
        )
        verified = dry_run("--verify-snapshot", "checkpoint")
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertIn(
            "pf_artifact.exe verify-session",
            verified.stdout.splitlines()[-1],
        )

    def test_headless_snapshot_publication_and_audio_capture(self) -> None:
        result = dry_run(
            "--verify-replay", "shared-amiga-calibration",
            "--snapshot-out", "verified",
            "--capture-audio", "verified",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.splitlines()[-1]
        self.assertIn(" --snapshot-out ", command)
        self.assertIn("verified.pfamigasnapshot", command)
        self.assertIn(" --audio-wav ", command)
        self.assertIn("verified.wav", command)

        rejected = dry_run("--snapshot-out", "machine-only")
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn(
            "requires ArtifactV2 playback or recording",
            rejected.stderr,
        )

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
