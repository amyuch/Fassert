"""Computed disposition tests: proved, needs_check, reject, no stored tag."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kernel import kernel  # noqa: E402


class DispositionTest(unittest.TestCase):
    def setUp(self) -> None:
        from test_kernel import KernelTest

        self.fixture = KernelTest(methodName="runTest")
        self.fixture.setUp()

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def run_package(self, proof: dict, case: dict) -> kernel.CheckResult:
        case_path = self.fixture.dir / "case.json"
        proof_path = self.fixture.dir / "proof.json"
        case_path.write_text(json.dumps(case), encoding="utf-8")
        proof_path.write_text(json.dumps(proof), encoding="utf-8")
        return kernel.check_paths(str(case_path), str(proof_path))

    def test_complete_proof_is_proved(self) -> None:
        result = self.run_package(
            self.fixture.make_complete_proof(),
            self.fixture.make_complete_case(),
        )
        self.assertTrue(result.accepted, result.as_dict())
        self.assertEqual(result.status, "proved")
        self.assertEqual(result.residual, [])
        self.assertTrue(result.proved)
        self.assertTrue(all(o["discharged"] for o in result.obligations))

    def test_unproved_premise_is_needs_check_not_proved(self) -> None:
        proof = self.fixture.make_complete_proof()
        node = next(n for n in proof["nodes"] if n["id"] == "alt_inv")
        node["certificate"]["verdict"] = "unknown"
        result = self.run_package(proof, self.fixture.make_complete_case())
        self.assertFalse(result.accepted, result.as_dict())
        self.assertEqual(result.status, "needs_check")
        self.assertTrue(result.residual, result.as_dict())
        self.assertTrue(any(o["id"] == "node.alt_inv" for o in result.residual))

    def test_invalid_smt_witness_is_reject(self) -> None:
        proof = self.fixture.make_complete_proof()
        node = next(n for n in proof["nodes"] if n["id"] == "bridge")
        node["certificate"]["payload"]["smt2"] = "(set-logic QF_LIA)\n(assert false)\n"
        result = self.run_package(proof, self.fixture.make_complete_case())
        self.assertFalse(result.accepted, result.as_dict())
        self.assertEqual(result.status, "reject")
        self.assertTrue(result.fatal_errors, result.as_dict())

    def test_counterexample_is_reject_not_needs_check(self) -> None:
        proof = self.fixture.make_complete_proof()
        node = next(n for n in proof["nodes"] if n["id"] == "alt_inv")
        node["certificate"]["verdict"] = "cex"
        result = self.run_package(proof, self.fixture.make_complete_case())
        self.assertFalse(result.accepted, result.as_dict())
        self.assertEqual(result.status, "reject")
        self.assertTrue(result.fatal_errors, result.as_dict())

    def test_legacy_package_is_not_proved(self) -> None:
        result = self.run_package(self.fixture.make_proof(), self.fixture.make_case())
        self.assertTrue(result.accepted, result.as_dict())
        self.assertEqual(result.status, "needs_check")
        self.assertFalse(result.proved)
        self.assertTrue(any(o["id"] == "mode.complete" for o in result.residual))

    def test_stored_status_tag_is_rejected(self) -> None:
        proof = self.fixture.make_complete_proof()
        proof["status"] = "proved"
        result = self.run_package(proof, self.fixture.make_complete_case())
        self.assertFalse(result.accepted, result.as_dict())
        self.assertEqual(result.status, "reject")
        self.assertTrue(any(e.rule == "K1" for e in result.errors), result.as_dict())


if __name__ == "__main__":
    unittest.main()
