"""Unit tests for the lemma-chain decomposition planner."""
from __future__ import annotations

import unittest

from pipeline.core import PcdError, canonical_hash
from pipeline.decompose import decomposition_proposals
from pipeline.plan import validate_proposal


def _context() -> dict:
    return {
        "case": {
            "id": "demo_case",
            "budgets": {"engine_seconds": {"ric3": 60}, "total_seconds": 120},
            "targets": [{"id": "root", "statement": "demo"}],
        },
        "model": {
            "properties": [
                {"index": 0, "name": "h_reset", "assertion_file": "input/rtl/tb.sv"},
                {"index": 1, "name": "h_link", "assertion_file": "input/rtl/tb.sv"},
                {"index": 2, "name": "o_rs1", "assertion_file": "input/rtl/check.sv"},
                {"index": 3, "name": "o_rs2", "assertion_file": "input/rtl/check.sv"},
            ]
        },
    }


def _spec() -> dict:
    return {
        "schema_version": "pcd-decomposition/0.1",
        "id": "demo_chain",
        "case": "demo_case",
        "lemmas": [
            {
                "id": "reset",
                "property": "h_reset",
                "role": "invariant",
                "kind": "inductive",
                "phase": "entry",
                "statement": "reset lemma",
            },
            {
                "id": "link",
                "property": "h_link",
                "role": "operand",
                "kind": "inductive",
                "phase": "loop",
                "statement": "read-link lemma",
                "requires": ["reset"],
            },
        ],
        "targets": [
            {
                "id": "rs1",
                "property": "o_rs1",
                "statement": "rs1 target",
                "requires": ["link"],
            },
            {
                "id": "rs2",
                "property": "o_rs2",
                "statement": "rs2 target",
                "requires": ["link"],
            },
        ],
        "cuts": [
            {
                "id": "chain",
                "boundary": "demo boundary",
                "members": ["reset", "link", "rs1", "rs2"],
                "entry": ["reset"],
                "step": ["link"],
                "exit": ["link"],
                "link": ["rs1", "rs2"],
            }
        ],
    }


class DecompositionPlannerTests(unittest.TestCase):
    def test_builds_helper_chain_and_cut(self) -> None:
        ctx = _context()
        doc = decomposition_proposals(ctx, canonical_hash(ctx), _spec())
        validate_proposal(doc)
        nodes = {n["id"]: n for n in doc["nodes"]}
        self.assertIn("lemma.reset", nodes)
        self.assertIn("lemma.link", nodes)
        self.assertIn("target.rs1", nodes)
        self.assertIn("target.rs2", nodes)
        self.assertIn("cut.chain", nodes)
        self.assertEqual(nodes["lemma.reset"]["helper"]["kind"], "monitor")
        self.assertEqual(nodes["lemma.reset"]["phase"], "entry")
        self.assertEqual(nodes["target.rs1"]["provides"][0]["binding"],
                         {"kind": "btor-bad", "property": "o_rs1"})
        self.assertTrue(nodes["cut.chain"]["cut"]["link"])
        self.assertEqual(nodes["root"]["role"], "compose")
        self.assertEqual(doc["targets"][0]["id"], "root")
        # The root must consume both targets and the cut; the cut consumes the
        # lemma chain, so the target property is never an unbound premise.
        root_reqs = {r["node"] for r in nodes["root"]["requires"]}
        self.assertEqual(root_reqs, {"target.rs1", "target.rs2", "cut.chain"})
        cut_reqs = {r["node"] for r in nodes["cut.chain"]["requires"]}
        self.assertEqual(
            cut_reqs,
            {"lemma.reset", "lemma.link", "target.rs1", "target.rs2"},
        )

    def test_rejects_unbound_property(self) -> None:
        ctx = _context()
        spec = _spec()
        spec["lemmas"] = spec["lemmas"][:1]
        spec["targets"] = spec["targets"][:1]
        spec["cuts"] = []
        with self.assertRaises(PcdError):
            decomposition_proposals(ctx, canonical_hash(ctx), spec)

    def test_rejects_cut_fact_outside_members(self) -> None:
        ctx = _context()
        spec = _spec()
        spec["cuts"][0]["entry"] = ["rs1"]
        # rs1 is a member, so this is valid; now use a truly missing id.
        spec["cuts"][0]["step"] = ["missing"]
        with self.assertRaises(PcdError):
            decomposition_proposals(ctx, canonical_hash(ctx), spec)

    def test_sets_assign_methods_and_backward_assumptions(self) -> None:
        ctx = _context()
        spec = _spec()
        spec["targets"][0]["requires"] = []
        spec["sets"] = [
            {"id": "monitor", "method": "cill", "lemmas": ["reset", "link"]},
            {
                "id": "results",
                "method": "ic3",
                "assumes": ["link"],
                "targets": ["rs1", "rs2"],
            },
        ]
        doc = decomposition_proposals(ctx, canonical_hash(ctx), spec)
        validate_proposal(doc)
        nodes = {n["id"]: n for n in doc["nodes"]}
        self.assertEqual(nodes["lemma.reset"]["certificate_hint"]["backend"], "cill")
        self.assertEqual(nodes["target.rs1"]["certificate_hint"]["backend"], "ic3")
        self.assertIn(
            {"node": "lemma.link", "guarantee": "L_link"},
            nodes["target.rs1"]["requires"],
        )
        self.assertEqual(doc["metadata"]["sets"][0]["id"], "monitor")
        self.assertEqual(doc["metadata"]["sets"][1]["method"], "ic3")

    def test_rejects_forward_set_assumption(self) -> None:
        ctx = _context()
        spec = _spec()
        spec["sets"] = [
            {
                "id": "results",
                "method": "ic3",
                "assumes": ["link"],
                "targets": ["rs1", "rs2"],
            },
            {"id": "monitor", "method": "cill", "lemmas": ["reset", "link"]},
        ]
        with self.assertRaises(PcdError):
            decomposition_proposals(ctx, canonical_hash(ctx), spec)

    def test_rejects_same_set_assumption(self) -> None:
        ctx = _context()
        spec = _spec()
        spec["sets"] = [
            {
                "id": "one",
                "method": "cill",
                "lemmas": ["reset", "link"],
                "targets": ["rs1", "rs2"],
                "assumes": ["link"],
            }
        ]
        with self.assertRaises(PcdError):
            decomposition_proposals(ctx, canonical_hash(ctx), spec)

    def test_rejects_unknown_set_method(self) -> None:
        ctx = _context()
        spec = _spec()
        spec["sets"] = [
            {"id": "one", "method": "magic", "lemmas": ["reset", "link"], "targets": ["rs1", "rs2"]}
        ]
        with self.assertRaises(PcdError):
            decomposition_proposals(ctx, canonical_hash(ctx), spec)


if __name__ == "__main__":
    unittest.main()
