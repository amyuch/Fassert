"""Kernel v2 negative-control tests.

Run from the PCD root with:

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from checkers import expr as expr_mod  # noqa: E402
from kernel import kernel  # noqa: E402

M1 = "btor:" + "a" * 64
M2 = "btor:" + "b" * 64

# The kernel now regenerates CHECKED SMT scripts from these formulas.  The
# formulas are intentionally simple but exercise Bool premises, integer
# arithmetic, a polynomial equation, and a tautological coverage guarantee.
POLY_EXPR = "(x + 1)^2 = x^2 + 2*x + 1"
COVER_EXPR = "(or q (not q))"
ROOT_EXPR = f"(and m {POLY_EXPR} {POLY_EXPR} {COVER_EXPR} q)"
ROOT_EXPR_COMPLETE = f"(and m {POLY_EXPR} {POLY_EXPR} {COVER_EXPR} q)"

SMT_CHAIN = expr_mod.canonical_script(
    ["m", POLY_EXPR, POLY_EXPR, COVER_EXPR, "q"],
    ROOT_EXPR,
)
SMT_CHAIN_COMPLETE = expr_mod.canonical_script(
    ["m", POLY_EXPR, POLY_EXPR, COVER_EXPR, "q"],
    ROOT_EXPR_COMPLETE,
)
SMT_BRIDGE = expr_mod.canonical_script(["m", POLY_EXPR], POLY_EXPR)
SMT_COVER = expr_mod.canonical_script([], COVER_EXPR)
SMT_TRANSFER = expr_mod.canonical_script(["q"], "q")

HELPER_GOOD = """module toy_helper;
  always @* begin
    h_manifold: assert (x > 0);
  end
endmodule
"""

HELPER_VACUOUS = """module toy_helper;
  always @* begin
    h_manifold: assert (x > 0 || 1'b1);
  end
endmodule
"""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class KernelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "logs").mkdir()
        (self.dir / "artifacts").mkdir()
        (self.dir / "input" / "rtl").mkdir(parents=True)
        (self.dir / "input" / "spec").mkdir(parents=True)
        (self.dir / "build").mkdir()

        self.manifold_log = "manifold: proved\n"
        self.alt_log = "alt: proved\n"
        (self.dir / "logs" / "manifold.log").write_text(self.manifold_log, encoding="utf-8")
        (self.dir / "logs" / "alt.log").write_text(self.alt_log, encoding="utf-8")
        (self.dir / "artifacts" / "compose.smt2").write_text(SMT_CHAIN, encoding="utf-8")
        (self.dir / "artifacts" / "compose_complete.smt2").write_text(
            SMT_CHAIN_COMPLETE, encoding="utf-8"
        )
        (self.dir / "helper_good.sv").write_text(HELPER_GOOD, encoding="utf-8")
        (self.dir / "helper_vacuous.sv").write_text(HELPER_VACUOUS, encoding="utf-8")
        (self.dir / "input" / "rtl" / "toy.sv").write_text("module toy; endmodule\n", encoding="utf-8")
        (self.dir / "input" / "spec" / "toy.spec").write_text("result == spec\n", encoding="utf-8")
        (self.dir / "build" / "build.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

        self.log1 = _sha(self.manifold_log)
        self.log2 = _sha(self.alt_log)
        self.compose_hash = _sha(SMT_CHAIN)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_case(self) -> dict:
        return {
            "schema_version": "pcd-case/0.1",
            "case": "toy",
            "acceptance": "legacy",
            "claim_scope": "safety",
            "inputs": {
                "files": [
                    {"path": "input/rtl/toy.sv", "role": "rtl"},
                    {"path": "input/spec/toy.spec", "role": "spec"},
                ],
                "environment": {"top": "toy", "reset": "reset", "frontend": "yosys-slang"},
            },
            "build": {
                "kind": "btor",
                "recipe": {"command": ["sh", "build/build.sh"]},
                "outputs": [{"path": "build/toy.btor", "kind": "btor"}],
            },
            "targets": [
                {
                    "id": "root",
                    "statement": "the toy result equals the spec",
                    "guard": "!reset",
                    "observation": "retire",
                    "claim_level": "root",
                    "model": M1,
                }
            ],
            "budgets": {"total_seconds": 60, "max_iterations": 2, "engine_seconds": {"z3": 30}},
            "run_policy": {
                "mode": "dev",
                "oracle_paths": ["oracle/"],
                "pre_registered": True,
                "planner": "manual",
            },
        }

    def _premises(self) -> list[dict]:
        return [
            {"node": "manifold", "guarantee": "G1"},
            {"node": "poly", "guarantee": "G2"},
            {"node": "bridge", "guarantee": "G3"},
            {"node": "coverage", "guarantee": "G4"},
            {"node": "xfer", "guarantee": "G6"},
        ]

    def _premises_complete(self) -> list[dict]:
        return [
            {"node": "manifold", "guarantee": "G1"},
            {"node": "poly", "guarantee": "G2"},
            {"node": "bridge", "guarantee": "G3"},
            {"node": "coverage", "guarantee": "G4"},
            {"node": "xfer", "guarantee": "G6"},
        ]

    def make_proof(self) -> dict:
        return {
            "schema_version": "pcd-proof/0.1",
            "case": "toy",
            "acceptance": "legacy",
            "models": {"primary": M1, "alt": M2},
            "primary_model": M1,
            "helpers": [
                {
                    "path": "helper_good.sv",
                    "asserts": [{"node": "manifold", "name": "h_manifold"}],
                }
            ],
            "nodes": [
                {
                    "schema_version": "pcd-obligation/0.1",
                    "id": "O0",
                    "role": "rtl_link",
                    "kind": "tcb",
                    "phase": "any",
                    "model": M1,
                    "statement": "front-end trust boundary",
                    "requires": [],
                    "provides": [{"name": "G0", "expr": "tcb_ok", "sort": "Bool"}],
                    "certificate": {
                        "evidence": "TCB",
                        "format": "tcb",
                        "verdict": "assumed",
                        "tcb": "toy front-end; model hash is identity, not equivalence",
                    },
                },
                {
                    "schema_version": "pcd-obligation/0.1",
                    "id": "manifold",
                    "role": "invariant",
                    "kind": "inductive",
                    "phase": "loop",
                    "model": M1,
                    "statement": "reachable manifold",
                    "requires": [],
                    "provides": [{"name": "G1", "expr": "m", "sort": "Bool"}],
                    "certificate": {
                        "evidence": "REPLAY",
                        "format": "replay",
                        "verdict": "proved",
                        "goal": "G1",
                        "run": {
                            "id": "run-manifold",
                            "command": ["toy-engine", "check", "toy.btor"],
                            "tool": "toy-engine",
                            "version": "0.1",
                            "model_sha256": M1,
                            "log": "logs/manifold.log",
                            "log_sha256": self.log1,
                        },
                        "assertion": {"name": "h_manifold", "file": "helper_good.sv"},
                    },
                },
                {
                    "schema_version": "pcd-obligation/0.1",
                    "id": "poly",
                    "role": "algebra",
                    "kind": "poly",
                    "phase": "any",
                    "model": M1,
                    "statement": "poly identity",
                    "requires": [],
                    "provides": [{"name": "G2", "expr": POLY_EXPR, "sort": "Bool"}],
                    "certificate": {
                        "evidence": "CHECKED",
                        "format": "poly",
                        "checker": "pcd-poly/0.1",
                        "verdict": "proved",
                        "goal": "G2",
                        "payload": {
                            "W": 32,
                            "subst": {"a": [[1, ["x"]], [1, []]]},
                            "lhs": [[1, ["a", "a"]]],
                            "rhs": [[1, ["x", "x"]], [2, ["x"]], [1, []]],
                        },
                    },
                },
                {
                    "schema_version": "pcd-obligation/0.1",
                    "id": "bridge",
                    "role": "interface",
                    "kind": "linear",
                    "phase": "any",
                    "model": M1,
                    "statement": "bridge the recurrence to the observation",
                    "requires": [
                        {"node": "manifold", "guarantee": "G1"},
                        {"node": "poly", "guarantee": "G2"},
                    ],
                    "provides": [{"name": "G3", "expr": POLY_EXPR, "sort": "Bool"}],
                    "certificate": {
                        "evidence": "CHECKED",
                        "format": "smt-implication",
                        "checker": "z3/5.1",
                        "verdict": "proved",
                        "goal": "G3",
                        "payload": {"smt2": SMT_BRIDGE},
                    },
                },
                {
                    "schema_version": "pcd-obligation/0.1",
                    "id": "coverage",
                    "role": "coverage",
                    "kind": "guarded",
                    "phase": "any",
                    "model": M1,
                    "statement": "the guard partition is exhaustive",
                    "requires": [],
                    "provides": [{"name": "G4", "expr": COVER_EXPR, "sort": "Bool"}],
                    "coverage": {
                        "guards": [
                            {"name": "taken", "expr": "p"},
                            {"name": "not_taken", "expr": "!p"},
                        ],
                        "exhaustive": True,
                        "checked_by": "coverage.certificate",
                    },
                    "certificate": {
                        "evidence": "CHECKED",
                        "format": "smt-implication",
                        "checker": "z3/5.1",
                        "verdict": "proved",
                        "goal": "G4",
                        "payload": {"smt2": SMT_COVER},
                    },
                },
                {
                    "schema_version": "pcd-obligation/0.1",
                    "id": "alt_inv",
                    "role": "invariant",
                    "kind": "inductive",
                    "phase": "loop",
                    "model": M2,
                    "statement": "source-model invariant reused through a transfer",
                    "requires": [],
                    "provides": [{"name": "G5", "expr": "q", "sort": "Bool"}],
                    "certificate": {
                        "evidence": "REPLAY",
                        "format": "replay",
                        "verdict": "proved",
                        "goal": "G5",
                        "run": {
                            "id": "run-alt",
                            "command": ["toy-engine", "check", "alt.btor"],
                            "tool": "toy-engine",
                            "version": "0.1",
                            "model_sha256": M2,
                            "log": "logs/alt.log",
                            "log_sha256": self.log2,
                        },
                    },
                    "reuse": {
                        "source_model": M2,
                        "assumption_match": ["model", "width", "guards", "phase", "transition"],
                        "transfer_node": "xfer",
                        "note": "toy transfer",
                    },
                },
                {
                    "schema_version": "pcd-obligation/0.1",
                    "id": "xfer",
                    "role": "transfer",
                    "kind": "equivalence",
                    "phase": "any",
                    "model": M1,
                    "statement": "transfer the source invariant to the primary model",
                    "requires": [{"node": "alt_inv", "guarantee": "G5"}],
                    "provides": [{"name": "G6", "expr": "q", "sort": "Bool"}],
                    "certificate": {
                        "evidence": "CHECKED",
                        "format": "smt-implication",
                        "checker": "z3/5.1",
                        "verdict": "proved",
                        "goal": "G6",
                        "payload": {"smt2": SMT_TRANSFER},
                    },
                },
                {
                    "schema_version": "pcd-obligation/0.1",
                    "id": "root",
                    "role": "compose",
                    "kind": "linear",
                    "phase": "any",
                    "model": M1,
                    "statement": "root composition",
                    "requires": self._premises(),
                    "provides": [{"name": "P", "expr": ROOT_EXPR, "sort": "Bool"}],
                    "certificate": {
                        "evidence": "CHECKED",
                        "format": "smt-implication",
                        "checker": "z3/5.1",
                        "verdict": "proved",
                        "goal": "P",
                        "payload": {"smt2": SMT_CHAIN},
                    },
                },
            ],
            "targets": [
                {
                    "id": "root",
                    "statement": "the toy result equals the spec",
                    "model": M1,
                    "goal": "P",
                    "requires": self._premises(),
                    "tcb": ["O0"],
                    "composition": {
                        "mode": "CHECKED",
                        "checker": "z3-implication",
                        "payload": {
                            "premises": self._premises(),
                            "goal": "P",
                            "smt2": SMT_CHAIN,
                        },
                        "artifact": {"path": "artifacts/compose.smt2", "sha256": self.compose_hash},
                    },
                }
            ],
            "metadata": {"run_mode": "dev", "planner": "manual", "completeness": "legacy"},
        }

    def make_complete_case(self) -> dict:
        case = self.make_case()
        case["acceptance"] = "complete"
        return case

    def make_complete_proof(self) -> dict:
        """A fully proved, TCB-free graph under complete acceptance."""
        proof = copy.deepcopy(self.make_proof())
        proof["acceptance"] = "complete"
        proof["metadata"]["completeness"] = "complete"
        proof["nodes"] = [n for n in proof["nodes"] if n["id"] != "O0"]
        premises = self._premises_complete()
        for target in proof["targets"]:
            target["requires"] = copy.deepcopy(premises)
            target["tcb"] = []
            target["composition"]["payload"]["premises"] = copy.deepcopy(premises)
            target["composition"]["payload"]["smt2"] = SMT_CHAIN_COMPLETE
            target["composition"]["artifact"] = {
                "path": "artifacts/compose_complete.smt2",
                "sha256": _sha(SMT_CHAIN_COMPLETE),
            }
        root = next(n for n in proof["nodes"] if n["id"] == "root")
        root["requires"] = copy.deepcopy(premises)
        root["provides"] = [{"name": "P", "expr": ROOT_EXPR_COMPLETE, "sort": "Bool"}]
        root["certificate"]["payload"]["smt2"] = SMT_CHAIN_COMPLETE
        # This fixture tests same-model logical closure. Cross-model complete
        # acceptance now has dedicated model-bound composition tests.
        source = next(n for n in proof["nodes"] if n["id"] == "alt_inv")
        source["model"] = M1
        source["certificate"]["run"]["model_sha256"] = M1
        source.pop("reuse", None)
        return proof

    def test_complete_rejects_legacy_boolean_model_transfer(self) -> None:
        proof = self.make_complete_proof()
        source = next(n for n in proof["nodes"] if n["id"] == "alt_inv")
        source["model"] = M2
        source["certificate"]["run"]["model_sha256"] = M2
        result = self.run_proof(proof, self.make_complete_case())
        self.assert_rejected_with(result, "K13")

    def test_complete_rejects_metadata_policy_downgrade(self) -> None:
        proof = self.make_complete_proof()
        proof["metadata"]["completeness"] = "legacy"
        result = self.run_proof(proof, self.make_complete_case())
        self.assert_rejected_with(result, "K12")

    def test_rejects_omitted_case_target(self) -> None:
        case = self.make_complete_case()
        target = copy.deepcopy(case["targets"][0])
        target["id"] = "missing_target"
        case["targets"].append(target)
        self.assert_rejected_with(self.run_proof(self.make_complete_proof(), case), "K1")

    def test_complete_rejects_grouped_self_premise(self) -> None:
        proof = self.make_complete_proof()
        node = next(n for n in proof["nodes"] if n["id"] == "bridge")
        node["requires"] = [{"node": "bridge", "guarantee": "G3"}]
        node["simultaneous_group"] = "claimed_group"
        node["certificate"]["payload"]["smt2"] = expr_mod.canonical_script([POLY_EXPR], POLY_EXPR)
        self.assert_rejected_with(self.run_proof(proof, self.make_complete_case()), "K3")

    def test_complete_rejects_modular_fact_as_integer_equality(self) -> None:
        proof = self.make_complete_proof()
        node = next(n for n in proof["nodes"] if n["id"] == "poly")
        node["provides"][0]["expr"] = "x + 4294967296 = x"
        self.assert_rejected_with(self.run_proof(proof, self.make_complete_case()), "K13")

    def run_proof(self, proof: dict | None = None, case: dict | None = None) -> kernel.CheckResult:
        proof = proof if proof is not None else self.make_proof()
        case = case if case is not None else self.make_case()
        case_path = self.dir / "case.json"
        proof_path = self.dir / "proof.json"
        case_path.write_text(json.dumps(case), encoding="utf-8")
        proof_path.write_text(json.dumps(proof), encoding="utf-8")
        return kernel.check_paths(str(case_path), str(proof_path))

    def add_root_premise(self, proof: dict, extra: dict) -> None:
        """Add a premise and regenerate the bound root script."""
        for target in proof["targets"]:
            target["requires"].append(dict(extra))
            target["composition"]["payload"]["premises"].append(dict(extra))
        root = next(n for n in proof["nodes"] if n["id"] == "root")
        root["requires"].append(dict(extra))
        exprs = ["m", POLY_EXPR, POLY_EXPR, COVER_EXPR, "q", "tcb_ok"]
        script = expr_mod.canonical_script(exprs, ROOT_EXPR)
        root["certificate"]["payload"]["smt2"] = script
        proof["targets"][0]["composition"]["payload"]["smt2"] = script

    def assert_rejected_with(self, result: kernel.CheckResult, rule: str) -> None:
        self.assertFalse(result.accepted, result.as_dict())
        rules = {e.rule for e in result.errors}
        self.assertIn(rule, rules, result.as_dict())

    # ------------------------------------------------------------------
    # Positive control
    # ------------------------------------------------------------------
    def test_accepts_minimal_valid_proof(self) -> None:
        result = self.run_proof()
        self.assertTrue(result.accepted, result.as_dict())
        self.assertEqual(result.targets["root"]["evidence"], "REPLAY")
        self.assertEqual(result.targets["root"]["composition"], "CHECKED")
        self.assertEqual(result.targets["root"]["tcb"], ["O0"])

    def test_structural_composition_is_capped(self) -> None:
        proof = self.make_proof()
        proof["targets"][0]["composition"] = {"mode": "STRUCTURAL"}
        result = self.run_proof(proof)
        self.assertTrue(result.accepted, result.as_dict())
        self.assertEqual(result.targets["root"]["composition"], "STRUCTURAL")
        self.assertTrue(any(w.rule == "K6" for w in result.warnings))

    def test_complete_accepts_tcb_free_proof(self) -> None:
        result = self.run_proof(self.make_complete_proof(), self.make_complete_case())
        self.assertTrue(result.accepted, result.as_dict())
        self.assertEqual(result.targets["root"]["composition"], "CHECKED")
        self.assertEqual(result.targets["root"]["tcb"], [])
        self.assertEqual(result.targets["root"]["tcb_deps"], [])

    def test_complete_is_default_when_acceptance_is_unset(self) -> None:
        proof = self.make_complete_proof()
        case = self.make_complete_case()
        proof.pop("acceptance")
        case.pop("acceptance")
        proof["metadata"].pop("completeness")
        result = self.run_proof(proof, case)
        self.assertTrue(result.accepted, result.as_dict())
        self.assertEqual(result.targets["root"]["composition"], "CHECKED")

    def test_complete_rejects_design_tcb(self) -> None:
        proof = self.make_complete_proof()
        proof["nodes"].append(
            {
                "schema_version": "pcd-obligation/0.1",
                "id": "design_tcb",
                "role": "rtl_link",
                "kind": "tcb",
                "phase": "any",
                "model": M1,
                "statement": "a design trust boundary",
                "requires": [],
                "provides": [{"name": "G0", "expr": "design_ok", "sort": "Bool"}],
                "certificate": {
                    "evidence": "TCB",
                    "format": "tcb",
                    "verdict": "assumed",
                    "tcb": "unproved design fact",
                },
            }
        )
        result = self.run_proof(proof, self.make_complete_case())
        self.assert_rejected_with(result, "K12")

    def test_complete_rejects_direct_target_tcb(self) -> None:
        proof = self.make_complete_proof()
        proof["targets"][0]["tcb"] = ["manifold"]
        result = self.run_proof(proof, self.make_complete_case())
        self.assert_rejected_with(result, "K12")

    def test_complete_rejects_structural_composition(self) -> None:
        proof = self.make_complete_proof()
        proof["targets"][0]["composition"] = {"mode": "STRUCTURAL"}
        result = self.run_proof(proof, self.make_complete_case())
        self.assert_rejected_with(result, "K12")

    def test_complete_rejects_nonproof_verdict(self) -> None:
        proof = self.make_complete_proof()
        manifold = next(n for n in proof["nodes"] if n["id"] == "manifold")
        manifold["certificate"]["verdict"] = "bmc_clean"
        result = self.run_proof(proof, self.make_complete_case())
        self.assert_rejected_with(result, "K12")

    def test_complete_rejects_helper_assertion_mismatch(self) -> None:
        proof = self.make_complete_proof()
        manifold = next(n for n in proof["nodes"] if n["id"] == "manifold")
        manifold["certificate"]["assertion"]["name"] = "different_assertion"
        result = self.run_proof(proof, self.make_complete_case())
        self.assert_rejected_with(result, "K12")

    def test_complete_rejects_helper_assertion_file_mismatch(self) -> None:
        proof = self.make_complete_proof()
        manifold = next(n for n in proof["nodes"] if n["id"] == "manifold")
        manifold["certificate"]["assertion"]["file"] = "different_file.sv"
        result = self.run_proof(proof, self.make_complete_case())
        self.assert_rejected_with(result, "K12")

    def test_complete_rejects_undeclared_helper_assumption(self) -> None:
        (self.dir / "helper_good.sv").write_text(
            HELPER_GOOD.replace(
                "endmodule",
                "  p_assume: assume (x > 0);\nendmodule",
            ),
            encoding="utf-8",
        )
        result = self.run_proof(self.make_complete_proof(), self.make_complete_case())
        self.assert_rejected_with(result, "K12")

    def test_complete_rejects_undeclared_property_assertion(self) -> None:
        (self.dir / "helper_good.sv").write_text(
            HELPER_GOOD.replace(
                "endmodule",
                "  p_other: assert property (x > 0);\nendmodule",
            ),
            encoding="utf-8",
        )
        result = self.run_proof(self.make_complete_proof(), self.make_complete_case())
        self.assert_rejected_with(result, "K12")

    # ------------------------------------------------------------------
    # Negative controls
    # ------------------------------------------------------------------
    def test_rejects_missing_target_premise(self) -> None:
        proof = self.make_proof()
        proof["targets"][0]["requires"] = proof["targets"][0]["requires"][:-1]
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K6")

    def test_rejects_diagnostic_premise(self) -> None:
        proof = self.make_proof()
        manifold = next(n for n in proof["nodes"] if n["id"] == "manifold")
        manifold["certificate"]["verdict"] = "bmc_clean"
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K3")

    def test_rejects_uncheckable_prose_evidence(self) -> None:
        proof = self.make_proof()
        poly = next(n for n in proof["nodes"] if n["id"] == "poly")
        poly["certificate"] = {
            "evidence": "CHECKED",
            "format": "miter",
            "checker": "manual hand-wave",
            "verdict": "proved",
            "goal": "G2",
            "payload": {"note": "trust me"},
        }
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K2")

    def test_rejects_unbound_artifact(self) -> None:
        proof = self.make_proof()
        bad = self.dir / "artifacts" / "bad.bin"
        bad.write_text("not the recorded artifact\n", encoding="utf-8")
        poly = next(n for n in proof["nodes"] if n["id"] == "poly")
        poly["certificate"]["artifact"] = {"path": "artifacts/bad.bin", "sha256": "0" * 64}
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K8")

    def test_rejects_certificate_goal_mismatch(self) -> None:
        proof = self.make_proof()
        bridge = next(n for n in proof["nodes"] if n["id"] == "bridge")
        bridge["certificate"]["goal"] = "G2"
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K2")

    def test_rejects_vacuous_helper(self) -> None:
        proof = self.make_proof()
        proof["helpers"][0]["path"] = "helper_vacuous.sv"
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K9")

    def test_rejects_planner_status(self) -> None:
        proof = self.make_proof()
        proof["metadata"]["planner"] = {"name": "llm", "status": "proved"}
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K10")

    def test_rejects_reuse_model_mismatch(self) -> None:
        proof = self.make_proof()
        alt = next(n for n in proof["nodes"] if n["id"] == "alt_inv")
        alt["reuse"]["source_model"] = M1
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K4")

    def test_rejects_transfer_pointing_at_non_transfer(self) -> None:
        proof = self.make_proof()
        alt = next(n for n in proof["nodes"] if n["id"] == "alt_inv")
        alt["reuse"]["transfer_node"] = "poly"
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K4")

    def test_rejects_uncovered_guard_partition(self) -> None:
        proof = self.make_proof()
        cov = next(n for n in proof["nodes"] if n["id"] == "coverage")
        cov["coverage"]["exhaustive"] = False
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K5")

    def test_rejects_bad_poly_certificate(self) -> None:
        proof = self.make_proof()
        poly = next(n for n in proof["nodes"] if n["id"] == "poly")
        poly["certificate"]["payload"] = {"W": 32, "lhs": [[1, []]], "rhs": []}
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K2")

    def test_rejects_false_poly_expression_with_valid_payload(self) -> None:
        proof = self.make_proof()
        poly = next(n for n in proof["nodes"] if n["id"] == "poly")
        # The legacy payload still witnesses the true identity, but it is not
        # the obligation formula anymore. Binding to the expression catches it.
        poly["provides"][0]["expr"] = "(x + 1)^2 = x^2 + 1"
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K2")

    def test_rejects_non_boolean_smt_premise(self) -> None:
        proof = self.make_proof()
        manifold = next(n for n in proof["nodes"] if n["id"] == "manifold")
        manifold["provides"][0]["sort"] = "Int"
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K2")

    def test_rejects_vacuous_poly_identity(self) -> None:
        proof = self.make_proof()
        poly = next(n for n in proof["nodes"] if n["id"] == "poly")
        poly["certificate"]["payload"] = {
            "W": 32,
            "lhs": [[1, ["y"]], [-1, ["x"]], [-1, []]],
            "rhs": [[1, ["y"]], [-1, ["x"]], [-1, []]],
        }
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K2")

    def test_rejects_vacuous_unsat_smt_script(self) -> None:
        proof = self.make_proof()
        bridge = next(n for n in proof["nodes"] if n["id"] == "bridge")
        bridge["certificate"]["payload"]["smt2"] = "(assert false)\n(check-sat)\n"
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K2")

    def test_rejects_vacuous_unsat_composition_script(self) -> None:
        proof = self.make_proof()
        proof["targets"][0]["composition"]["payload"]["smt2"] = "(assert false)\n(check-sat)\n"
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K6")

    def test_rejects_composition_premise_mismatch(self) -> None:
        proof = self.make_proof()
        comp = proof["targets"][0]["composition"]
        comp["payload"]["premises"] = comp["payload"]["premises"][:-1]
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K6")

    def test_rejects_case_target_model_mismatch(self) -> None:
        case = self.make_case()
        case["targets"][0]["model"] = M2
        result = self.run_proof(case=case)
        self.assert_rejected_with(result, "K1")

    def test_rejects_duplicate_node_id(self) -> None:
        proof = self.make_proof()
        proof["nodes"].append(copy.deepcopy(next(n for n in proof["nodes"] if n["id"] == "poly")))
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K1")

    def test_declared_tcb_premise_is_reported(self) -> None:
        proof = self.make_proof()
        extra = {"node": "O0", "guarantee": "G0"}
        self.add_root_premise(proof, extra)
        result = self.run_proof(proof)
        self.assertTrue(result.accepted, result.as_dict())
        self.assertEqual(result.targets["root"]["tcb"], ["O0"])
        self.assertEqual(result.targets["root"]["evidence"], "REPLAY")

    def test_rejects_undeclared_tcb_premise(self) -> None:
        proof = self.make_proof()
        extra = {"node": "O0", "guarantee": "G0"}
        self.add_root_premise(proof, extra)
        proof["targets"][0]["tcb"] = []
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K3")

    def test_accepts_cut_contract_with_checked_coverage(self) -> None:
        proof = self.make_proof()
        bridge = next(n for n in proof["nodes"] if n["id"] == "bridge")
        bridge["cut"] = {
            "boundary": "toy bridge",
            "entry": [{"node": "manifold", "guarantee": "G1"}],
            "step": [],
            "exit": [],
            "link": [{"node": "poly", "guarantee": "G2"}],
            "guards": [
                {"name": "taken", "expr": "p"},
                {"name": "not_taken", "expr": "!p"},
            ],
            "coverage": {"node": "coverage", "guarantee": "G4"},
            "assumption_cut": False,
        }
        result = self.run_proof(proof)
        self.assertTrue(result.accepted, result.as_dict())

    def test_accepts_explicit_assumption_cut_helper(self) -> None:
        proof = self.make_proof()
        assumption = {
            "schema_version": "pcd-obligation/0.1",
            "id": "h_assume",
            "role": "tcb",
            "kind": "tcb",
            "phase": "any",
            "model": M1,
            "statement": "explicit assumption helper",
            "requires": [],
            "provides": [{"name": "G7", "expr": "a", "sort": "Bool"}],
            "certificate": {
                "evidence": "TCB",
                "format": "tcb",
                "verdict": "assumed",
                "tcb": "declared cut assumption",
            },
            "helper": {"kind": "assumption"},
        }
        proof["nodes"].insert(-1, assumption)
        bridge = next(n for n in proof["nodes"] if n["id"] == "bridge")
        bridge["requires"].append({"node": "h_assume", "guarantee": "G7"})
        bridge["certificate"]["payload"]["smt2"] = expr_mod.canonical_script(
            ["m", POLY_EXPR, "a"], POLY_EXPR
        )
        bridge["cut"] = {
            "boundary": "assumption-gated bridge",
            "entry": [{"node": "manifold", "guarantee": "G1"}],
            "step": [],
            "exit": [],
            "link": [{"node": "poly", "guarantee": "G2"}],
            "assumption_cut": True,
            "assumptions": ["h_assume"],
        }
        proof["targets"][0]["tcb"].append("h_assume")
        result = self.run_proof(proof)
        self.assertTrue(result.accepted, result.as_dict())
        self.assertIn("h_assume", result.targets["root"]["tcb"])

    def test_rejects_cut_reference_not_in_requires(self) -> None:
        proof = self.make_proof()
        bridge = next(n for n in proof["nodes"] if n["id"] == "bridge")
        bridge["cut"] = {
            "boundary": "toy bridge",
            "entry": [],
            "step": [],
            "exit": [],
            "link": [{"node": "O0", "guarantee": "G0"}],
            "assumption_cut": False,
        }
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K11")

    def test_rejects_cut_guard_mismatch(self) -> None:
        proof = self.make_proof()
        bridge = next(n for n in proof["nodes"] if n["id"] == "bridge")
        bridge["cut"] = {
            "boundary": "toy bridge",
            "entry": [{"node": "manifold", "guarantee": "G1"}],
            "step": [],
            "exit": [],
            "link": [{"node": "poly", "guarantee": "G2"}],
            "guards": [{"name": "taken", "expr": "p"}],
            "coverage": {"node": "coverage", "guarantee": "G4"},
            "assumption_cut": False,
        }
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K11")

    def test_rejects_monitor_helper_with_tcb_evidence(self) -> None:
        proof = self.make_proof()
        o0 = next(n for n in proof["nodes"] if n["id"] == "O0")
        o0["helper"] = {"kind": "monitor"}
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K11")

    def test_rejects_assumption_helper_without_tcb(self) -> None:
        proof = self.make_proof()
        manifold = next(n for n in proof["nodes"] if n["id"] == "manifold")
        manifold["helper"] = {"kind": "assumption"}
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K11")

    def test_rejects_schema_invalid_replay_binding(self) -> None:
        proof = self.make_proof()
        manifold = next(n for n in proof["nodes"] if n["id"] == "manifold")
        del manifold["certificate"]["run"]["log_sha256"]
        result = self.run_proof(proof)
        self.assert_rejected_with(result, "K1")


if __name__ == "__main__":
    unittest.main()
