"""Integration tests for offline proof-package suites."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.bench import _package_provenance, run_bench  # noqa: E402
from pipeline.core import load_case, read_json  # noqa: E402
from kernel import kernel  # noqa: E402


class OfflineSuitePackageTest(unittest.TestCase):
    def test_official_suite_packages_are_proved(self) -> None:
        suite = read_json(ROOT / "suites" / "official_isa.json")
        self.assertEqual(suite.get("provenance"), "official")
        packages = suite.get("proof_packages") or {}
        self.assertEqual(set(packages), set(suite["cases"]))
        for case_ref in suite["cases"]:
            _, official = load_case(case_ref)
            package_dir = (ROOT / packages[case_ref]).resolve()
            _, package = load_case(package_dir)
            self.assertEqual(_package_provenance(official, package), [], case_ref)
            check = kernel.check_paths(
                str(package_dir / "case.json"), str(package_dir / "proof.json")
            ).as_dict()
            self.assertTrue(check["accepted"], (case_ref, check.get("errors")))
            self.assertEqual(check["targets"]["root"]["tcb"], [], case_ref)

    def test_offline_suite_runs_without_engine(self) -> None:
        suite = read_json(ROOT / "suites" / "offline.json")
        self.assertEqual(suite.get("provenance"), "none")
        self.assertEqual(len(suite["cases"]), 12)
        saved_checks = {
            ROOT / ref / "check.json": (ROOT / ref / "check.json").read_bytes()
            for ref in suite["proof_packages"].values()
        }
        with tempfile.TemporaryDirectory() as tmp:
            bench, path = run_bench(str(ROOT / "suites/offline.json"), runs_dir=tmp)
            self.assertTrue(bench["all_accepted"], bench)
            self.assertEqual(len(bench["cases"]), 12)
            for row in bench["cases"]:
                self.assertEqual(row["result"], "ACCEPT", row)
                self.assertEqual(row["accepted"], True, row)
                self.assertEqual(row["status"], "proved", row)
                self.assertTrue(row["package"], row)
            self.assertTrue(path.is_file())
            self.assertTrue(json.loads(path.read_text(encoding="utf-8"))["all_accepted"])
        for check, original in saved_checks.items():
            self.assertEqual(check.read_bytes(), original, "bench changed a frozen package check")


if __name__ == "__main__":
    unittest.main()
