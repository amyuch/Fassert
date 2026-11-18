"""Manifest-driven discharge DAG: a real two-hop separated proof."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent)]
from pipeline.crossmodel import build_and_attach  # noqa: E402

SOURCE = """1 sort bitvec 1
2 input 1 clock
3 state 1 flag
4 zero 1
5 one 1
6 init 1 3 4
7 next 1 3 4
8 bad 3 safe_flag
9 constraint 2
"""

DESTINATION = SOURCE + """10 state 1 observer
11 not 1 10
12 init 1 10 4
13 next 1 10 11
"""

CHECK = "module m; safe_flag: assert(!flag); endmodule\n"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class CrossModelManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / "source.btor").write_text(SOURCE)
        (self.base / "intermediate.btor").write_text(SOURCE + "; intermediate\n")
        (self.base / "destination.btor").write_text(DESTINATION)
        (self.base / "check.sv").write_text(CHECK)
        (self.base / "engine.log").write_text("UNSAT\n")
        did = sha(DESTINATION)
        self.case = {
            "schema_version": "pcd-case/0.1",
            "case": "crossmodel_toy",
            "acceptance": "complete",
            "claim_scope": "safety",
            "inputs": {"files": [{"path": "check.sv", "role": "checker"}],
                       "environment": {"top": "m", "reset": "reset", "frontend": "other"}},
            "build": {"kind": "btor", "recipe": {"command": ["true"]},
                      "outputs": [{"path": "destination.btor", "kind": "btor"}],
                      "expected_model": {"kind": "btor", "sha256": did}},
            "targets": [{"id": "root", "statement": "flag remains zero",
                         "claim_level": "root", "model_ref": "primary",
                         "required_properties": ["safe_flag"]}],
            "budgets": {"total_seconds": 30, "max_iterations": 1},
            "run_policy": {"mode": "dev", "oracle_paths": [], "pre_registered": True},
        }
        (self.base / "case.json").write_text(json.dumps(self.case))
        self.manifest = {
            "schema_version": "pcd-crossmodel/0.1",
            "case": "case.json",
            "out": "out",
            "primary": "dest",
            "models": {
                "src": {"path": "source.btor"},
                "mid": {"path": "intermediate.btor"},
                "dest": {"path": "destination.btor"},
            },
            "nodes": [
                {"id": "fact0", "kind": "replay", "model": "src",
                 "properties": ["safe_flag"], "assertion": "check.sv",
                 "log": "engine.log",
                 "run": {"command": ["ric3", "check", "source.btor", "ic3", "--prop", "0"],
                         "tool": "ric3", "version": "test"}},
                {"id": "xfer0", "kind": "transfer", "model": "mid",
                 "source": {"node": "fact0", "guarantee": "G_fact0"},
                 "dest_property": "safe_flag", "dest_guarantee": "D0"},
                {"id": "mid", "kind": "smt", "model": "mid", "method": "combinational",
                 "goal": {"kind": "property", "property": "safe_flag"},
                 "guarantee": "MID", "requires": [{"node": "xfer0", "guarantee": "D0"}]},
                {"id": "xfer1", "kind": "transfer", "model": "dest",
                 "source": {"node": "mid", "guarantee": "MID"},
                 "dest_property": "safe_flag", "dest_guarantee": "D1"},
            ],
            "target": {
                "id": "root", "goal_expr": "D1",
                "requires": [{"node": "xfer1", "guarantee": "D1"}],
                "required_properties": ["safe_flag"],
            },
        }
        (self.base / "manifest.json").write_text(json.dumps(self.manifest))

    def tearDown(self):
        self.tmp.cleanup()

    def test_two_hop_manifest_is_proved(self):
        report = build_and_attach(self.base / "manifest.json")
        self.assertEqual(report["status"], "proved", report)
        self.assertTrue(report["proved"])
        self.assertFalse(report["residual"])

    def test_mutated_projection_map_is_rejected(self):
        report = build_and_attach(self.base / "manifest.json")
        self.assertEqual(report["status"], "proved", report)
        proof_path = Path(report["out"]) / "proof.json"
        proof = json.loads(proof_path.read_text())
        transfer = next(n for n in proof["nodes"] if n["id"] == "xfer1")
        transfer["certificate"]["payload"]["state_map"] = {}
        proof_path.write_text(json.dumps(proof))
        from kernel import kernel
        result = kernel.check_paths(str(Path(report["out"]) / "case.json"), str(proof_path))
        self.assertNotEqual(result.status, "proved")
        self.assertTrue(any("mapping omits" in e.message for e in result.errors), result.as_dict())

    def test_cannot_replace_frozen_primary(self):
        from pipeline.core import PcdError
        self.manifest["primary"] = "src"
        (self.base / "manifest.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(PcdError, "frozen expected_model"):
            build_and_attach(self.base / "manifest.json")

    def test_cannot_drop_frozen_target_property(self):
        from pipeline.core import PcdError
        self.manifest["target"]["required_properties"] = []
        (self.base / "manifest.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(PcdError, "frozen required_properties"):
            build_and_attach(self.base / "manifest.json")


if __name__ == "__main__":
    unittest.main()
