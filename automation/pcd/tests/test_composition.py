"""Positive and negative controls for semantic model composition."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent)]
from checkers import bitproj, btor, composition, expr  # noqa: E402
from kernel import kernel  # noqa: E402


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


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


DIMENSIONS = ["model", "width", "guards", "phase", "transition"]


class StructuralProposalTest(unittest.TestCase):
    def test_property_roots_break_anonymous_state_ties(self) -> None:
        # Both destination states have identical colours; only the property
        # root distinguishes the real flag from the decoy.  The old pure-colour
        # proposal picks the first state and cannot map the stored property.
        source_text = """1 sort bitvec 1
2 input 1 clock
3 state 1 flag
4 zero 1
5 one 1
6 init 1 3 4
7 next 1 3 4
8 bad 3 safe_flag
"""
        destination_text = """1 sort bitvec 1
2 input 1 clock
3 state 1 decoy
4 zero 1
5 one 1
6 init 1 3 4
7 next 1 3 4
8 state 1 flag
9 init 1 8 4
10 next 1 8 4
11 bad 8 safe_flag
"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "source.btor").write_text(source_text)
            (base / "destination.btor").write_text(destination_text)
            source = btor.Model(base / "source.btor", text=source_text)
            destination = btor.Model(base / "destination.btor", text=destination_text)
            mapping = btor.propose_mapping(source, destination)
        self.assertEqual(mapping["3"], "8")


class CompositionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / "check.sv").write_text("module m; safe_flag: assert(!flag); endmodule\n")
        # Synthetic transcript tests model/command binding, not engine search.
        (self.base / "engine.log").write_text("UNSAT\n")
        self.source = self.write_model("source.btor", SOURCE)
        self.destination = self.write_model("destination.btor", DESTINATION)
        sid, did = "btor:" + self.source["sha256"], "btor:" + self.destination["sha256"]
        req = [{"node": "source", "guarantee": "S"}]
        script = expr.canonical_script(["destination_safe"], "destination_safe")
        self.case = {
            "schema_version": "pcd-case/0.1", "case": "composition_toy", "acceptance": "complete",
            "claim_scope": "safety", "inputs": {"files": [{"path": "check.sv", "role": "checker"}],
                "environment": {"top": "m", "reset": "reset", "frontend": "other"}},
            "build": {"kind": "btor", "recipe": {"command": ["true"]},
                "outputs": [{"path": "destination.btor", "kind": "btor"}],
                "expected_model": {"kind": "btor", "sha256": self.destination["sha256"]}},
            "targets": [{"id": "root", "statement": "flag remains zero", "claim_level": "root",
                "model_ref": "primary", "required_properties": ["safe_flag"]}],
            "budgets": {"total_seconds": 30, "max_iterations": 1},
            "run_policy": {"mode": "dev", "oracle_paths": [], "pre_registered": True},
        }
        common = {"schema_version": "pcd-obligation/0.1", "phase": "any", "kind": "replay"}
        self.proof = {
            "schema_version": "pcd-proof/0.1", "case": "composition_toy", "acceptance": "complete",
            "models": {"primary": did, "source": sid}, "primary_model": did,
            "model_artifacts": {sid: self.source, did: self.destination},
            "nodes": [
                {**common, "id": "source", "role": "observe", "model": sid, "requires": [],
                 "provides": [{"name": "S", "expr": "source_safe", "sort": "Bool",
                    "binding": {"kind": "btor-bad", "property": "safe_flag"}}],
                 "certificate": {"evidence": "REPLAY", "format": "replay", "verdict": "proved", "goal": "S",
                    "assertion": {"name": "safe_flag", "file": "check.sv"},
                    "run": {"id": "engine", "tool": "ric3", "version": "test", "model_sha256": sid,
                        "command": ["ric3", "check", "source.btor", "ic3", "--prop", "0"],
                        "log": "engine.log", "log_sha256": sha("UNSAT\n")}},
                 "reuse": {"source_model": sid, "assumption_match": ["model", "width", "guards", "phase", "transition"], "transfer_node": "transfer"}},
                {**common, "id": "transfer", "role": "transfer", "model": did, "requires": req,
                 "provides": [{"name": "D", "expr": "destination_safe", "sort": "Bool",
                    "binding": {"kind": "btor-bad", "property": "safe_flag"}}],
                 "certificate": {"evidence": "CHECKED", "format": composition.FORMAT,
                    "checker": composition.CHECKER, "verdict": "proved", "goal": "D",
                    "payload": {"source": req[0], "state_map": {"3": "3"}, "input_map": {"2": "2"}}}},
                {**common, "id": "root", "role": "compose", "model": did,
                 "requires": [{"node": "transfer", "guarantee": "D"}],
                 "provides": [{"name": "GOAL", "expr": "destination_safe", "sort": "Bool"}],
                 "certificate": {"evidence": "CHECKED", "format": "smt-implication", "checker": "z3",
                    "verdict": "proved", "goal": "GOAL", "payload": {"smt2": script}}},
            ],
            "targets": [{"id": "root", "statement": "flag remains zero", "model": did,
                "goal": "GOAL", "requires": [{"node": "transfer", "guarantee": "D"}], "tcb": [],
                "composition": {"mode": "CHECKED", "checker": "z3-implication",
                    "payload": {"premises": [{"node": "transfer", "guarantee": "D"}], "goal": "GOAL", "smt2": script}}}],
            "metadata": {"completeness": "complete", "run_mode": "dev"},
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_model(self, filename: str, text: str) -> dict:
        (self.base / filename).write_text(text)
        return {"path": filename, "sha256": sha(text)}

    def change_source(self, text: str) -> None:
        old = self.proof["models"]["source"]
        artifact = self.write_model("source.btor", text)
        new = "btor:" + artifact["sha256"]
        self.proof["models"]["source"] = new
        self.proof["model_artifacts"].pop(old)
        self.proof["model_artifacts"][new] = artifact
        node = self.proof["nodes"][0]
        node["model"] = node["certificate"]["run"]["model_sha256"] = node["reuse"]["source_model"] = new

    def result(self):
        return kernel.evaluate(self.case, self.proof, str(self.base))

    def rejected(self, text: str) -> None:
        result = self.result()
        self.assertFalse(result.accepted)
        self.assertTrue(any(i.rule == "K13" and text in i.message for i in result.errors), result.as_dict())

    def test_accepts_observer_extension_and_inherits_replay_assurance(self):
        result = self.result()
        self.assertTrue(result.accepted, result.as_dict())
        self.assertEqual(result.composition["status"], "checked")
        self.assertEqual(result.targets["root"]["evidence"], "REPLAY")

    def test_accepts_two_hop_separated_proof(self):
        """Engine fact -> intermediate model -> SMT root -> exact model.

        This is the discharge-DAG shape needed by MUL: the engine evidence and
        the arithmetic root live on different models, and the fact nodes are
        premises of an intermediate root rather than direct sources of the
        final transfer.
        """
        intermediate = self.write_model("intermediate.btor", SOURCE + "; intermediate\n")
        iid = "btor:" + intermediate["sha256"]
        mid = "btor:" + self.source["sha256"]
        did = "btor:" + self.destination["sha256"]
        self.proof["models"]["intermediate"] = iid
        self.proof["model_artifacts"][iid] = intermediate
        common = {"schema_version": "pcd-obligation/0.1", "phase": "any"}
        fact0 = {
            **common, "id": "fact0", "role": "observe", "kind": "replay", "model": mid,
            "requires": [],
            "provides": [{"name": "G0", "expr": "source_safe", "sort": "Bool",
                          "binding": {"kind": "btor-bad", "property": "safe_flag"}}],
            "certificate": {"evidence": "REPLAY", "format": "replay", "verdict": "proved", "goal": "G0",
                            "assertion": {"name": "safe_flag", "file": "check.sv"},
                            "run": {"id": "engine0", "tool": "ric3", "version": "test",
                                    "model_sha256": mid,
                                    "command": ["ric3", "check", "source.btor", "ic3", "--prop", "0"],
                                    "log": "engine.log", "log_sha256": sha("UNSAT\n")}},
            "reuse": {"source_model": mid, "assumption_match": DIMENSIONS, "transfer_node": "xfer0"},
        }
        xfer0 = {
            **common, "id": "xfer0", "role": "transfer", "kind": "equivalence", "model": iid,
            "requires": [{"node": "fact0", "guarantee": "G0"}],
            "provides": [{"name": "D0", "expr": "intermediate_safe", "sort": "Bool",
                          "binding": {"kind": "btor-bad", "property": "safe_flag"}}],
            "certificate": {"evidence": "CHECKED", "format": composition.FORMAT,
                            "checker": composition.CHECKER, "verdict": "proved", "goal": "D0",
                            "payload": {"source": {"node": "fact0", "guarantee": "G0"},
                                        "state_map": {"3": "3"}, "input_map": {"2": "2"}}},
            "reuse": {"source_model": iid, "assumption_match": DIMENSIONS, "transfer_node": "xfer1"},
        }
        middle = {
            **common, "id": "mid", "role": "observe", "kind": "inductive", "model": iid,
            "requires": [{"node": "xfer0", "guarantee": "D0"}],
            "provides": [{"name": "MID", "expr": "intermediate_safe", "sort": "Bool",
                          "binding": {"kind": "btor-bad", "property": "safe_flag"}}],
            "certificate": {"evidence": "CHECKED", "format": "btor-smt",
                            "checker": "pcd-btor-smt/0.1", "verdict": "proved", "goal": "MID",
                            "payload": {"method": "combinational"}},
            "reuse": {"source_model": iid, "assumption_match": DIMENSIONS, "transfer_node": "xfer1"},
        }
        xfer1 = {
            **common, "id": "xfer1", "role": "transfer", "kind": "equivalence", "model": did,
            "requires": [{"node": "mid", "guarantee": "MID"}],
            "provides": [{"name": "D1", "expr": "destination_safe", "sort": "Bool",
                          "binding": {"kind": "btor-bad", "property": "safe_flag"}}],
            "certificate": {"evidence": "CHECKED", "format": composition.FORMAT,
                            "checker": composition.CHECKER, "verdict": "proved", "goal": "D1",
                            "payload": {"source": {"node": "mid", "guarantee": "MID"},
                                        "state_map": {"3": "3"}, "input_map": {"2": "2"}}},
        }
        script = expr.canonical_script(["destination_safe"], "destination_safe")
        root = {
            **common, "id": "root", "role": "compose", "kind": "linear", "model": did,
            "requires": [{"node": "xfer1", "guarantee": "D1"}],
            "provides": [{"name": "GOAL", "expr": "destination_safe", "sort": "Bool"}],
            "certificate": {"evidence": "CHECKED", "format": "smt-implication", "checker": "z3",
                            "verdict": "proved", "goal": "GOAL", "payload": {"smt2": script}},
        }
        self.proof["nodes"] = [fact0, xfer0, middle, xfer1, root]
        self.proof["targets"] = [{
            "id": "root", "statement": "flag remains zero", "model": did, "goal": "GOAL",
            "requires": [{"node": "xfer1", "guarantee": "D1"}], "tcb": [],
            "composition": {"mode": "CHECKED", "checker": "z3-implication",
                            "payload": {"premises": [{"node": "xfer1", "guarantee": "D1"}],
                                        "goal": "GOAL", "smt2": script}},
        }]
        result = self.result()
        self.assertTrue(result.accepted, result.as_dict())
        self.assertEqual(result.status, "proved")
        self.assertTrue(all(o["discharged"] for o in result.obligations), result.residual)

    def test_accepts_source_with_fewer_environment_constraints(self):
        self.change_source(SOURCE.replace("9 constraint 2\n", ""))
        self.assertTrue(self.result().accepted, self.result().as_dict())

    def test_rejects_extra_source_assumption(self):
        self.change_source(SOURCE + "10 not 1 2\n11 constraint 10\n")
        self.rejected("constraint not established")

    def test_rejects_inconsistent_forgotten_initial_state(self):
        self.change_source(SOURCE + "10 state 1 unrelated\n11 not 1 10\n12 init 1 10 11\n13 next 1 10 10\n")
        self.rejected("relational source initialization")

    def test_rejects_failed_log_after_success_marker(self):
        text = "UNSAT\n# external timeout after 5s\n"
        (self.base / "engine.log").write_text(text)
        self.proof["nodes"][0]["certificate"]["run"]["log_sha256"] = sha(text)
        self.rejected("incomplete or failed engine")

    def test_rejects_unknown_engine_options(self):
        self.proof["nodes"][0]["certificate"]["run"]["command"].extend(["--assume", "1"])
        self.rejected("unsupported command options")

    def test_rejects_changed_initial_state(self):
        self.change_source(SOURCE.replace("6 init 1 3 4", "6 init 1 3 5"))
        self.rejected("initial-state")

    def test_rejects_changed_next_state(self):
        self.change_source(SOURCE.replace("7 next 1 3 4", "7 next 1 3 5"))
        self.rejected("transition")

    def test_rejects_changed_property_under_same_name(self):
        self.change_source(SOURCE.replace("8 bad 3 safe_flag", "8 bad 5 safe_flag"))
        self.rejected("destination property")

    def test_rejects_changed_model_file_without_new_hash(self):
        (self.base / "source.btor").write_text(SOURCE + "; changed\n")
        self.rejected("changed model artifact")

    def test_rejects_missing_state_mapping(self):
        self.proof["nodes"][1]["certificate"]["payload"]["state_map"] = {}
        self.rejected("omits source cone")

    def test_rejects_state_to_input_mapping(self):
        self.proof["nodes"][1]["certificate"]["payload"]["state_map"] = {"3": "2"}
        self.rejected("state/input kind")

    def test_rejects_width_change(self):
        self.change_source(SOURCE + "10 sort bitvec 2\n11 state 10 wide\n12 zero 10\n13 eq 1 11 12\n14 bad 13 wide_p\n")
        self.proof["nodes"][1]["certificate"]["payload"]["state_map"]["11"] = "3"
        self.rejected("bit-vector width")

    def test_rejects_wrong_engine_property_selection(self):
        self.proof["nodes"][0]["certificate"]["run"]["command"][-1] = "1"
        self.rejected("--prop")

    def test_rejects_bmc_as_proof(self):
        self.proof["nodes"][0]["certificate"]["run"]["command"][3] = "bmc"
        self.rejected("unsupported bound property engine")

    def test_accepts_multi_prop_whole_group_replay(self):
        # multi-prop without --prop proves the whole property group.  The
        # source model deliberately has a second property so this exercises the
        # whole-group branch rather than the single-property fallback.
        self.change_source(SOURCE + "10 not 1 3\n11 bad 10 other\n")
        self.proof["nodes"][0]["certificate"]["run"]["command"] = [
            "ric3", "check", "source.btor", "multi-prop",
        ]
        result = self.result()
        self.assertTrue(result.accepted, result.as_dict())
        self.assertEqual(result.status, "proved")

    def test_rejects_multi_prop_counterexample_before_unsat(self):
        text = "SAT\nUNSAT\n"
        (self.base / "engine.log").write_text(text)
        self.proof["nodes"][0]["certificate"]["run"]["command"] = [
            "ric3", "check", "source.btor", "multi-prop",
        ]
        self.proof["nodes"][0]["certificate"]["run"]["log_sha256"] = sha(text)
        self.rejected("counterexample result")

    def test_rejects_boolean_identity_transfer(self):
        node = self.proof["nodes"][1]
        node["certificate"] = {"evidence": "CHECKED", "format": "smt-implication", "checker": "z3",
            "verdict": "proved", "goal": "D", "payload": {"smt2": expr.canonical_script(["source_safe"], "destination_safe")}}
        self.rejected("cross-model premise")

    def test_rejects_unbound_source_property(self):
        self.proof["nodes"][0]["provides"][0].pop("binding")
        self.rejected("exact btor-bad binding")

    def test_rejects_root_that_drops_required_property(self):
        node = self.proof["nodes"][2]
        node["provides"][0]["expr"] = "true"
        script = expr.canonical_script(["destination_safe"], "true")
        node["certificate"]["payload"]["smt2"] = script
        self.proof["targets"][0]["composition"]["payload"]["smt2"] = script
        self.rejected("every required case property")

    def test_rejects_cross_model_boolean_alias(self):
        self.proof["nodes"][0]["provides"][0]["expr"] = "destination_safe"
        self.rejected("unqualified Boolean atom")

    def test_rejects_unapproved_primary_model(self):
        self.case["build"].pop("expected_model")
        self.rejected("frozen expected_model")

    def test_rejects_supplied_arithmetic_without_rtl_binding(self):
        node = self.proof["nodes"][2]
        node["certificate"]["format"] = "smt-induction"
        node["certificate"]["payload"] = {"vars": [{"name": "destination_safe", "sort": "Bool"}],
            "init": ["destination_safe"], "step": ["destination_safe_next"],
            "inv": ["destination_safe"], "goal": "destination_safe"}
        self.rejected("RTL-to-arithmetic lifting")

    def test_mapping_proposer_is_not_authoritative(self):
        store = composition.ModelStore(self.proof, str(self.base))
        self.proof["nodes"][1]["certificate"]["payload"] = composition.proposal(
            self.proof["models"]["source"], self.proof["primary_model"], "source", "S", store)
        self.assertTrue(self.result().accepted, self.result().as_dict())
        self.proof["nodes"][1]["certificate"]["payload"]["state_map"]["3"] = "10"
        self.rejected("transition")

    def test_rejects_unsupported_array_model(self):
        (self.base / "array.btor").write_text("1 sort bitvec 1\n2 sort array 1 1\n")
        with self.assertRaisesRegex(btor.BtorError, "bit-vector"):
            btor.Model(self.base / "array.btor")

    def test_rejects_malformed_operator_width(self):
        (self.base / "bad.btor").write_text("1 sort bitvec 1\n2 zero 1\n3 concat 1 2 2\n")
        with self.assertRaisesRegex(btor.BtorError, "width mismatch"):
            btor.Model(self.base / "bad.btor")

    def test_rejects_out_of_range_constant(self):
        (self.base / "bad.btor").write_text("1 sort bitvec 1\n2 constd 1 2\n")
        with self.assertRaisesRegex(btor.BtorError, "does not fit"):
            btor.Model(self.base / "bad.btor")

    def test_accepts_repacked_wiring_without_changing_bits(self):
        # A syntactic packing difference is normalized, while arithmetic
        # operators retain their widths and operand structure.
        (self.base / "a.btor").write_text("1 sort bitvec 1\n2 input 1 x\n3 uext 1 2 0\n4 bad 3 p\n")
        model = btor.Model(self.base / "a.btor")
        bits = model.bits(lambda n: n.symbol)
        self.assertEqual(bits[2], bits[3])

    def test_rejects_sampling_shift_even_when_names_match(self):
        self.change_source(SOURCE.replace("8 bad 3 safe_flag", "8 state 1 past_flag\n9 init 1 8 4\n10 next 1 8 3\n11 bad 8 safe_flag").replace("9 constraint 2", "12 constraint 2"))
        self.proof["nodes"][1]["certificate"]["payload"]["state_map"]["8"] = "3"
        self.rejected("transition")


class FreeBitProjectionTest(unittest.TestCase):
    SOURCE = """1 sort bitvec 1
2 sort bitvec 2
3 state 2 free
4 slice 1 3 0 0
5 slice 1 3 1 1
6 or 1 4 5
7 bad 6 p
"""

    DESTINATION = """1 sort bitvec 1
2 state 1 a
3 state 1 b
4 or 1 2 3
5 bad 4 p
"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.source = self.write_model("source.btor", self.SOURCE)
        self.destination = self.write_model("destination.btor", self.DESTINATION)
        sid, did = "btor:" + self.source["sha256"], "btor:" + self.destination["sha256"]
        self.proof = {
            "models": {"source": sid, "primary": did},
            "primary_model": did,
            "model_artifacts": {sid: self.source, did: self.destination},
            "nodes": [
                {"id": "source", "role": "observe", "model": sid, "requires": [],
                 "provides": [{"name": "S", "expr": "source_p", "sort": "Bool",
                    "binding": {"kind": "btor-bad", "property": "p"}}],
                 "certificate": {"evidence": "CHECKED", "format": composition.FORMAT,
                    "checker": composition.CHECKER, "verdict": "proved", "goal": "S"}},
                {"id": "transfer", "role": "transfer", "model": did,
                 "requires": [{"node": "source", "guarantee": "S"}],
                 "provides": [{"name": "D", "expr": "destination_p", "sort": "Bool",
                    "binding": {"kind": "btor-bad", "property": "p"}}],
                 "certificate": {"evidence": "CHECKED", "format": composition.FORMAT,
                    "checker": composition.CHECKER, "verdict": "proved", "goal": "D",
                    "payload": {"source": {"node": "source", "guarantee": "S"},
                        "state_map": {}, "input_map": {},
                        "free_map": {"3": ["2:0", "3:0"]}}}},
            ],
        }
        self.nodes = {node["id"]: node for node in self.proof["nodes"]}
        self.store = composition.ModelStore(self.proof, str(self.base))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_model(self, filename: str, text: str) -> dict:
        (self.base / filename).write_text(text)
        return {"path": filename, "sha256": sha(text)}

    def check(self):
        return composition.check_projection(self.nodes["transfer"], self.nodes, self.store)

    def test_accepts_cross_packed_free_bits(self) -> None:
        result = self.check()
        self.assertEqual(result["mapped_free_bits"], 2)

    def test_accepts_untrusted_bit_proposal_after_checking(self) -> None:
        source_node = self.nodes["source"]
        transfer = self.nodes["transfer"]
        source_guarantee = source_node["provides"][0]
        destination_guarantee = transfer["provides"][0]
        transfer["certificate"]["payload"] = composition.bit_proposal(
            source_node, transfer, source_guarantee, destination_guarantee, self.store)
        self.check()

    def test_provided_whole_atom_mapping_is_still_checked(self) -> None:
        source = self.write_model("source.btor", """1 sort bitvec 1
2 input 1 x
3 bad 2 p
""")
        destination = self.write_model("destination.btor", """1 sort bitvec 1
2 input 1 y
3 input 1 x
4 bad 3 p
""")
        sid = "btor:" + source["sha256"]
        did = "btor:" + destination["sha256"]
        old_sid = self.proof["models"]["source"]
        old_did = self.proof["models"]["primary"]
        self.proof["models"].update({"source": sid, "primary": did})
        self.proof["primary_model"] = did
        self.proof["model_artifacts"].pop(old_sid)
        self.proof["model_artifacts"].pop(old_did)
        self.proof["model_artifacts"][sid] = source
        self.proof["model_artifacts"][did] = destination
        self.proof["nodes"][0]["model"] = sid
        self.proof["nodes"][1]["model"] = did
        self.nodes = {node["id"]: node for node in self.proof["nodes"]}
        self.store = composition.ModelStore(self.proof, str(self.base))
        with self.assertRaisesRegex(bitproj.BitProjectionError, "wrong destination"):
            composition.bit_proposal(
                self.nodes["source"], self.nodes["transfer"],
                self.nodes["source"]["provides"][0],
                self.nodes["transfer"]["provides"][0],
                self.store, mapping={2: 2})

    def test_accepts_shared_destination_bits(self) -> None:
        self.destination = self.write_model("destination.btor", """1 sort bitvec 1
2 state 1 a
3 or 1 2 2
4 bad 3 p
""")
        did = "btor:" + self.destination["sha256"]
        old = self.proof["nodes"][1]["model"]
        self.proof["models"]["primary"] = did
        self.proof["primary_model"] = did
        self.proof["model_artifacts"].pop(old)
        self.proof["model_artifacts"][did] = self.destination
        self.proof["nodes"][1]["model"] = did
        self.proof["nodes"][1]["certificate"]["payload"]["free_map"]["3"] = ["2:0", "2:0"]
        self.nodes = {node["id"]: node for node in self.proof["nodes"]}
        self.store = composition.ModelStore(self.proof, str(self.base))
        self.check()

    def test_rejects_partial_free_map(self) -> None:
        self.proof["nodes"][1]["certificate"]["payload"]["free_map"]["3"] = ["2:0"]
        with self.assertRaisesRegex(composition.CompositionError, "exactly one destination bit"):
            self.check()

    def test_rejects_non_free_destination_bit(self) -> None:
        self.proof["nodes"][1]["certificate"]["payload"]["free_map"]["3"] = ["2:0", "4:0"]
        with self.assertRaisesRegex(composition.CompositionError, "free destination states"):
            self.check()

    def test_rejects_free_source_in_whole_atom_map(self) -> None:
        self.source = self.write_model("source.btor", """1 sort bitvec 1
2 state 1 free
3 bad 2 p
""")
        self.destination = self.write_model("destination.btor", """1 sort bitvec 1
2 state 1 a
3 bad 2 p
""")
        sid = "btor:" + self.source["sha256"]
        did = "btor:" + self.destination["sha256"]
        old_sid = self.proof["models"]["source"]
        old_did = self.proof["models"]["primary"]
        self.proof["models"].update({"source": sid, "primary": did})
        self.proof["primary_model"] = did
        self.proof["model_artifacts"].pop(old_sid)
        self.proof["model_artifacts"].pop(old_did)
        self.proof["model_artifacts"][sid] = self.source
        self.proof["model_artifacts"][did] = self.destination
        self.proof["nodes"][0]["model"] = sid
        self.proof["nodes"][1]["model"] = did
        payload = self.proof["nodes"][1]["certificate"]["payload"]
        payload["state_map"] = {"2": "2"}
        payload["free_map"] = {"2": ["2:0"]}
        self.nodes = {node["id"]: node for node in self.proof["nodes"]}
        self.store = composition.ModelStore(self.proof, str(self.base))
        with self.assertRaisesRegex(composition.CompositionError, "whole-atom mapping"):
            self.check()

    def test_rejects_one_source_bit_matched_to_independent_destination_bits(self) -> None:
        self.source = self.write_model("source.btor", """1 sort bitvec 1
2 state 1 free
3 or 1 2 2
4 bad 3 p
""")
        sid = "btor:" + self.source["sha256"]
        old = self.proof["models"]["source"]
        self.proof["models"]["source"] = sid
        self.proof["model_artifacts"].pop(old)
        self.proof["model_artifacts"][sid] = self.source
        self.proof["nodes"][0]["model"] = sid
        self.proof["nodes"][1]["certificate"]["payload"]["free_map"] = {"2": ["2:0"]}
        self.nodes = {node["id"]: node for node in self.proof["nodes"]}
        self.store = composition.ModelStore(self.proof, str(self.base))
        with self.assertRaisesRegex(composition.CompositionError, "mapped source property"):
            self.check()


class RealAddProjectionTest(unittest.TestCase):
    def test_frozen_real_add_observer_projection(self):
        package = ROOT / "examples" / "composition_add"
        result = kernel.check_paths(str(package / "case.json"), str(package / "proof.json"))
        self.assertTrue(result.accepted, result.as_dict())
        self.assertEqual(len(result.composition["checked_edges"]), 25)
        self.assertEqual(result.targets["root"]["evidence"], "REPLAY")

    def test_offline_compose_cli_checks_the_real_package(self):
        package = ROOT / "examples" / "composition_add"
        result = subprocess.run([str(ROOT / "pcd"), "compose", "--case", str(package / "case.json"),
                                 "--proof", str(package / "proof.json")], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(json.loads(result.stdout)["accepted"])


if __name__ == "__main__":
    unittest.main()
