from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "certify_amiga_oracle", ROOT / "scripts" / "certify_amiga_oracle.py"
)
assert SPEC and SPEC.loader
CERTIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CERTIFY)


def clean_report() -> dict:
    return {
        "format": "pf-amiga-run-v1",
        "execution_mode": "amiga-oracle",
        "status": "step-limit",
        "instructions": 1_000_000,
        "unknown_reads": 0,
        "unknown_writes": 0,
        "unsupported_cia_read_mask": 0,
        "unsupported_cia_write_mask": 0,
        "unsupported_custom_reads": [],
        "unsupported_custom_writes": [],
        "deterministic_rerun": True,
        "snapshot_roundtrip": True,
        "canonical_digest": "a" * 64,
        "diagnostic": "",
    }


class AmigaOracleCertificationTests(unittest.TestCase):
    def test_clean_strict_run_is_certifiable(self) -> None:
        self.assertEqual(CERTIFY.validate_report(clean_report(), 1_000_000), [])

    def test_any_unsupported_evidence_fails_closed(self) -> None:
        for field, value in (
            ("unknown_reads", 1),
            ("unknown_writes", 1),
            ("unsupported_cia_read_mask", 4),
            ("unsupported_cia_write_mask", 8),
            ("unsupported_custom_reads", [0xA8]),
            ("unsupported_custom_writes", [0x120]),
        ):
            with self.subTest(field=field):
                report = clean_report()
                report[field] = value
                self.assertTrue(
                    CERTIFY.validate_report(report, 1_000_000), report
                )

    def test_self_consistency_and_budget_are_required(self) -> None:
        for field, value in (
            ("deterministic_rerun", False),
            ("snapshot_roundtrip", False),
            ("instructions", 999_999),
            ("status", "frontier"),
        ):
            with self.subTest(field=field):
                report = clean_report()
                report[field] = value
                self.assertTrue(
                    CERTIFY.validate_report(report, 1_000_000), report
                )


if __name__ == "__main__":
    unittest.main()
