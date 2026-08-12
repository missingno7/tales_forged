from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "rebuild_atlas.py"
)
SPEC = importlib.util.spec_from_file_location(
    "tales_rebuild_atlas", SCRIPT
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import {SCRIPT}")
rebuild_atlas = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = rebuild_atlas
SPEC.loader.exec_module(rebuild_atlas)


class AtlasReplacementTests(unittest.TestCase):
    def test_semantic_projection_is_refreshed_before_atlas_ingestion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence.json"
            blocks = root / "blocks.json"
            evidence.write_text("{}\n", encoding="utf-8")
            blocks.write_text("{}\n", encoding="utf-8")
            calls: list[list[str]] = []

            def capture(values: list[str], *, cwd: Path) -> None:
                del cwd
                calls.append([str(value) for value in values])

            with ExitStack() as patches:
                patches.enter_context(mock.patch.object(rebuild_atlas, "ROOT", root))
                patches.enter_context(
                    mock.patch.object(rebuild_atlas, "EVIDENCE", evidence)
                )
                patches.enter_context(
                    mock.patch.object(rebuild_atlas, "BLOCKS", blocks)
                )
                patches.enter_context(
                    mock.patch.object(
                        rebuild_atlas, "ensure_clean_portforge", lambda: None
                    )
                )
                patches.enter_context(
                    mock.patch.object(
                        rebuild_atlas, "verify_existing_profile", lambda: None
                    )
                )
                patches.enter_context(
                    mock.patch.object(rebuild_atlas, "command", capture)
                )
                patches.enter_context(
                    mock.patch.object(
                        rebuild_atlas, "move_existing_atlas", lambda: None
                    )
                )
                patches.enter_context(
                    mock.patch.object(
                        rebuild_atlas,
                        "refresh_capability_evidence_hashes",
                        lambda: None,
                    )
                )
                rebuild_atlas.rebuild(1, reuse_evidence=True)

            analyze_index = next(
                index
                for index, values in enumerate(calls)
                if "scripts/analyze.py" in values
            )
            semantic_index = next(
                index
                for index, values in enumerate(calls)
                if "semantic" in values
            )
            atlas_index = next(
                index
                for index, values in enumerate(calls)
                if "atlas" in values
            )
            self.assertLess(analyze_index, semantic_index)
            self.assertLess(semantic_index, atlas_index)

    def test_failed_rebuild_restores_previous_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            old_root = rebuild_atlas.ROOT
            old_atlas = rebuild_atlas.ATLAS
            try:
                rebuild_atlas.ROOT = Path(temporary)
                rebuild_atlas.ATLAS = (
                    rebuild_atlas.ROOT
                    / "artifacts"
                    / "atlas.pfatlas"
                )
                rebuild_atlas.ATLAS.mkdir(parents=True)
                (rebuild_atlas.ATLAS / "old.txt").write_text(
                    "old", encoding="utf-8"
                )
                backup = rebuild_atlas.move_existing_atlas()
                self.assertIsNotNone(backup)
                self.assertFalse(rebuild_atlas.ATLAS.exists())

                rebuild_atlas.ATLAS.mkdir(parents=True)
                (rebuild_atlas.ATLAS / "new.txt").write_text(
                    "failed", encoding="utf-8"
                )
                failed = rebuild_atlas.restore_after_failure(backup)
                self.assertIsNotNone(failed)
                self.assertEqual(
                    (rebuild_atlas.ATLAS / "old.txt").read_text(
                        encoding="utf-8"
                    ),
                    "old",
                )
                self.assertEqual(
                    (failed / "new.txt").read_text(encoding="utf-8"),
                    "failed",
                )
            finally:
                rebuild_atlas.ROOT = old_root
                rebuild_atlas.ATLAS = old_atlas


if __name__ == "__main__":
    unittest.main()
