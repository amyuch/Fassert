"""Theorem import, real-model induction, and assumption-discharge controls."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

import z3

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent)]
from checkers import btor, composition, emit_btor, expr, model_smt, semantics  # noqa: E402
from kernel import kernel  # noqa: E402
from pipeline.e2e import run_e2e  # noqa: E402
import test_composition as fixture_module  # noqa: E402

R = semantics.ref
O = semantics.operation


def native_node(model_id: str, binding: dict, *, nid="lemma", atom="native_fact", method="induction"):
    return {"schema_version": "pcd-obligation/0.1", "id": nid, "role": "invariant", "kind": "inductive",
            "phase": "any", "model": model_id, "requires": [],
            "provides": [{"name": "L", "expr": atom, "sort": "Bool", "binding": binding}],
            "certificate": {"evidence": "CHECKED", "format": model_smt.FORMAT, "checker": model_smt.CHECKER,
                            "goal": "L", "verdict": "proved", "payload": {"method": method, "timeout_ms": 2000}}}


class ModelSmtTest(unittest.TestCase):
    def test_product_low_bits_normalization_preserves_values(self):
        a, b = z3.BitVecs("low_product_a low_product_b", 4)
        exact = z3.Extract(3, 0, z3.SignExt(4, a) * z3.ZeroExt(4, b)) == a * b
        result = model_smt.prove([], exact, "low product", 2000)
        self.assertEqual(result["result"], "unsat")

    def test_product_congruence_uses_equal_operands(self):
        a, b, x, y = z3.BitVecs("congr_a congr_b congr_x congr_y", 32)
        result = model_smt.prove([a == x, b == y],
                                z3.Extract(31, 0, z3.ZeroExt(32, a) * z3.ZeroExt(32, b)) == x * y,
                                "equal product", 2000)
        self.assertEqual(result["result"], "unsat")

    def test_product_abstraction_does_not_prove_false_arithmetic(self):
        a = z3.BitVec("false_product_a", 4)
        with self.assertRaisesRegex(semantics.SemanticError, "sat"):
            model_smt.prove([], a * a == a, "false product", 2000)

    def test_high_product_slice_is_not_low_product(self):
        a, b = z3.BitVecs("high_product_a high_product_b", 4)
        with self.assertRaisesRegex(semantics.SemanticError, "sat"):
            model_smt.prove([], z3.Extract(7, 4, z3.ZeroExt(4, a) * z3.ZeroExt(4, b)) == a * b,
                            "high product", 2000)

    def setUp(self):
        self.fixture = fixture_module.CompositionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.base = self.fixture.base
        self.case = self.fixture.case
        self.proof = self.fixture.proof

    def evaluate(self):
        return kernel.evaluate(self.case, self.proof, str(self.base))

    def rejected(self, text):
        result = self.evaluate()
        self.assertFalse(result.accepted)
        self.assertTrue(any(text in issue.message for issue in result.errors), result.as_dict())

    def local_proof(self):
        did = self.proof["primary_model"]
        lemma = native_node(did, {"kind": "btor-bad", "property": "safe_flag"}, atom="destination_safe")
        root = self.proof["nodes"][2]
        root["requires"] = [{"node": "lemma", "guarantee": "L"}]
        self.proof["targets"][0]["requires"] = copy.deepcopy(root["requires"])
        self.proof["targets"][0]["composition"]["payload"]["premises"] = copy.deepcopy(root["requires"])
        self.proof["models"] = {"primary": did}
        self.proof["model_artifacts"] = {did: self.proof["model_artifacts"][did]}
        self.proof["nodes"] = [lemma, root]
        return lemma

    def discharge_proof(self):
        self.fixture.change_source(fixture_module.SOURCE + "10 not 1 3\n11 constraint 10\n")
        did = self.proof["primary_model"]
        lemma = native_node(did, {"kind": "btor-expression", "expression": O("not", O("truth", R(3)))})
        self.proof["nodes"].insert(0, lemma)
        transfer = next(n for n in self.proof["nodes"] if n["id"] == "transfer")
        ref = {"node": "lemma", "guarantee": "L"}
        transfer["requires"].append(ref)
        transfer["certificate"]["payload"]["discharge"] = {"10": ref}
        return lemma, transfer

    def test_checks_initial_and_next_from_actual_model(self):
        self.local_proof()
        result = self.evaluate()
        self.assertTrue(result.accepted, result.as_dict())
        record = result.composition["checked_edges"]["lemma"]
        self.assertEqual(set(record["checks"]), {"base", "step"})
        self.assertEqual(result.targets["root"]["evidence"], "CHECKED")

    def test_imports_z3_lemma_to_close_engine_constraint(self):
        self.discharge_proof()
        result = self.evaluate()
        self.assertTrue(result.accepted, result.as_dict())
        self.assertIn("10", result.composition["checked_edges"]["transfer"]["discharged_constraints"])
        self.assertEqual(result.targets["root"]["evidence"], "REPLAY")

    def test_rejects_missing_discharge(self):
        _, transfer = self.discharge_proof()
        transfer["requires"].pop()
        transfer["certificate"]["payload"].pop("discharge")
        self.rejected("constraint not established")

    def test_rejects_tautology_as_stronger_assumption(self):
        lemma, _ = self.discharge_proof()
        lemma["provides"][0]["binding"]["expression"] = {"op": "bool", "value": True}
        self.rejected("constraint discharge: sat")

    def test_rejects_witness_on_restricted_source_model(self):
        lemma, _ = self.discharge_proof()
        lemma["model"] = self.proof["models"]["source"]
        self.rejected("original destination model")

    def test_rejects_circular_assumption_discharge(self):
        lemma, _ = self.discharge_proof()
        lemma["requires"] = [{"node": "transfer", "guarantee": "D"}]
        self.rejected("dependency cycle")

    def test_declared_helper_assumption_is_bound_to_actual_discharge(self):
        self.discharge_proof()
        path = self.base / "assumption.sv"
        path.write_text("module h; environment_lemma: assume(!flag); endmodule\n")
        self.proof["helpers"] = [{"path": "assumption.sv", "model": self.proof["models"]["source"],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "assumes": [{"name": "environment_lemma", "node": "lemma", "constraint": "10"}]}]
        result = self.evaluate()
        self.assertTrue(result.accepted, result.as_dict())
        self.proof["helpers"][0]["assumes"][0]["constraint"] = "4"
        self.rejected("helper assumption needs a model/constraint binding")

    def test_rejects_supplied_initial_state(self):
        lemma = self.local_proof()
        lemma["certificate"]["payload"]["init"] = ["false"]
        self.rejected("supplied transitions")

    def test_rejects_supplied_transition_relation(self):
        lemma = self.local_proof()
        lemma["certificate"]["payload"]["step"] = ["false"]
        self.rejected("supplied transitions")

    def test_formal_case_cannot_bypass_guard_by_dropping_semantic_nodes(self):
        self.local_proof()
        root = self.proof["nodes"][1]
        root["requires"] = []
        root["provides"][0]["expr"] = "true"
        script = expr.canonical_script([], "true")
        root["certificate"]["payload"]["smt2"] = script
        self.proof["nodes"] = [root]
        target = self.proof["targets"][0]
        target["requires"] = []
        target["composition"]["payload"]["premises"] = []
        target["composition"]["payload"]["smt2"] = script
        self.rejected("no proved destination binding")

    def test_native_proof_detects_actual_changed_transition(self):
        self.local_proof()
        old = self.proof["primary_model"]
        changed = fixture_module.DESTINATION.replace("7 next 1 3 4", "7 next 1 3 5")
        artifact = self.fixture.write_model("destination.btor", changed)
        new = "btor:" + artifact["sha256"]
        self.proof["model_artifacts"] = {new: artifact}
        self.proof["models"]["primary"] = self.proof["primary_model"] = new
        self.case["build"]["expected_model"]["sha256"] = artifact["sha256"]
        for node in self.proof["nodes"]:
            node["model"] = new
        self.proof["targets"][0]["model"] = new
        self.rejected("model induction step: sat")

    def test_induction_step_cti_is_open_not_a_refutation(self):
        """A SAT induction step is a CTI; only a stronger invariant is missing."""
        self.local_proof()
        changed = fixture_module.DESTINATION.replace("7 next 1 3 4", "7 next 1 3 5")
        artifact = self.fixture.write_model("destination.btor", changed)
        new = "btor:" + artifact["sha256"]
        self.proof["model_artifacts"] = {new: artifact}
        self.proof["models"]["primary"] = self.proof["primary_model"] = new
        self.case["build"]["expected_model"]["sha256"] = artifact["sha256"]
        for node in self.proof["nodes"]:
            node["model"] = new
        self.proof["targets"][0]["model"] = new
        result = self.evaluate()
        self.assertEqual(result.status, "needs_check", result.as_dict())
        self.assertFalse(result.proved)
        self.assertTrue(any("induction CTI" in issue.message for issue in result.errors), result.as_dict())

    def test_transition_witness_cannot_discharge_a_state_constraint(self):
        lemma, _ = self.discharge_proof()
        lemma["certificate"]["payload"]["method"] = "step"
        lemma["provides"][0]["binding"]["expression"] = O("not", O("truth", R(3, 1)))
        self.rejected("transition-only theorem")

    def test_rejects_false_strengthening(self):
        lemma = self.local_proof()
        lemma["certificate"]["payload"]["invariants"] = [{"op": "bool", "value": False}]
        self.rejected("induction base: sat")

    def test_rejects_state_property_proved_only_on_a_step(self):
        lemma = self.local_proof()
        lemma["certificate"]["payload"]["method"] = "step"
        self.rejected("not certify a state property")

    def test_rejects_future_reference_in_invariant(self):
        lemma = self.local_proof()
        lemma["provides"][0]["binding"] = {"kind": "btor-expression", "expression": O("not", O("truth", R(3, 1)))}
        self.rejected("future values")

    def test_rejects_unbound_prose_premise(self):
        lemma = self.local_proof()
        unbound = copy.deepcopy(self.proof["nodes"][1])
        unbound["id"] = "unbound"
        unbound["role"] = "interface"
        unbound["requires"] = []
        unbound["provides"] = [{"name": "U", "expr": "true", "sort": "Bool"}]
        unbound["certificate"] = {"evidence": "CHECKED", "format": "smt-implication", "checker": "z3",
            "goal": "U", "verdict": "proved", "payload": {"smt2": "(assert false)\n(check-sat)\n"}}
        self.proof["nodes"].append(unbound)
        lemma["requires"] = [{"node": "unbound", "guarantee": "U"}]
        self.rejected("distinct Boolean atoms")

    def test_rejects_wrong_quotient_operator_without_invariant(self):
        path = self.base / "arith.btor"
        path.write_text("1 sort bitvec 4\n2 input 1 q\n3 input 1 msk\n")
        ctx = semantics.Context(btor.Model(path), "test")
        claim = ctx.lower(O("eq", O("bvor", R(2), R(3)), O("bvadd", R(2), R(3))))
        with self.assertRaisesRegex(semantics.SemanticError, "sat"):
            model_smt.prove([], claim.value, "OR-to-add", 2000)
        zero = {"op": "bv", "width": 4, "value": "0"}
        disjoint = ctx.lower(O("eq", O("bvand", R(2), R(3)), zero))
        self.assertEqual(model_smt.prove([disjoint.value], claim.value, "OR-to-add", 2000)["result"], "unsat")

    def test_unsigned_integer_lift_does_not_hide_wraparound(self):
        ctx = semantics.Context(btor.Model(self.base / "destination.btor"), "test")
        one = {"op": "bv", "width": 1, "value": "1"}
        integer_one = {"op": "int", "value": "1"}
        claim = ctx.lower(O("eq", O("uint", O("bvadd", R(3), one)), O("add", O("uint", R(3)), integer_one)))
        with self.assertRaisesRegex(semantics.SemanticError, "sat"):
            model_smt.prove([], claim.value, "integer lift", 2000)

    def test_signed_and_unsigned_lifts_are_distinct(self):
        ctx = semantics.Context(btor.Model(self.base / "destination.btor"), "test")
        claim = ctx.lower(O("eq", O("uint", R(3)), O("sint", R(3))))
        with self.assertRaisesRegex(semantics.SemanticError, "sat"):
            model_smt.prove([], claim.value, "signedness", 2000)

    def test_rejects_implicit_sort_coercion(self):
        ctx = semantics.Context(btor.Model(self.base / "destination.btor"), "test")
        with self.assertRaisesRegex(semantics.SemanticError, "identical sorts"):
            ctx.lower(O("eq", R(3), {"op": "int", "value": "0"}))

    def test_exporter_does_not_silently_replace_integer_semantics(self):
        predicate = O("eq", O("uint", R(3)), {"op": "int", "value": "0"})
        with self.assertRaisesRegex(semantics.SemanticError, "integer lifting"):
            emit_btor.append_constraint(fixture_module.DESTINATION, predicate)

    def test_exported_constraint_is_checked_as_actual_btor(self):
        predicate = O("not", O("truth", R(3)))
        text, ref = emit_btor.append_constraint(fixture_module.DESTINATION, predicate)
        model = btor.Model("<emitted>", text=text)
        ctx = semantics.Context(model, "export")
        logical = ctx.lower(predicate).value
        self.assertEqual(model_smt.prove([], logical == (ctx.ref(ref) == 1), "export semantics", 2000)["result"], "unsat")

    def test_next_substitution_preserves_actual_modular_update(self):
        path = self.base / "counter.btor"
        path.write_text("1 sort bitvec 4\n2 state 1 counter\n3 one 1\n4 add 1 2 3\n5 next 1 2 4\n")
        model = btor.Model(path)
        ctx = semantics.Context(model, "counter", inline_next=True)
        for value in range(16):
            result = z3.simplify(z3.substitute(ctx.ref(2, 1), (ctx.ref(2), z3.BitVecVal(value, 4))))
            self.assertEqual(result.as_long(), (value + 1) % 16)

    def test_optional_cvc5_backend_proves_bounded_uniqueness(self):
        if model_smt._cvc5 is None:
            self.skipTest("optional CVC5 backend is not installed")
        n, q, d, m = z3.BitVecs("n q d m", 32)
        widened = z3.ZeroExt(32, d) + z3.ZeroExt(32, n) * z3.ZeroExt(32, q) == z3.ZeroExt(32, m)
        claim = z3.Implies(z3.And(n > 0, widened, z3.ULT(d, n)), d == z3.URem(m, n))
        result = model_smt.prove([], claim, "bounded uniqueness", 10000)
        self.assertEqual(result["result"], "unsat")
        self.assertTrue(result["solver"].startswith("cvc5-"), result)
        self.assertIn("backend_query_sha256", result)

    def test_optional_backend_normalization_preserves_equivalence(self):
        if model_smt._bitwuzla is None:
            self.skipTest("optional Bitwuzla backend is not installed")
        x, y = z3.BitVecs("x y", 8)
        solver = z3.Solver()
        solver.add(z3.And(x == z3.BitVecVal(3, 8)))
        solver.add(z3.Or(y == z3.BitVecVal(4, 8)))
        solver.add(z3.Distinct(x))
        solver.add(x + y == z3.BitVecVal(7, 8))
        solver.add(z3.Not(x == z3.BitVecVal(9, 8)))
        raw = "(set-logic QF_BV)\n" + solver.to_smt2()
        normalized = model_smt._smt2_normalize(raw)
        original_formula = z3.And(*z3.parse_smt2_string(raw))
        normalized_formula = z3.And(*z3.parse_smt2_string(normalized))
        equivalence = z3.Solver()
        equivalence.add(z3.Xor(original_formula, normalized_formula))
        self.assertEqual(equivalence.check(), z3.unsat)

    def test_rejects_free_variable_or_unregistered_operator(self):
        ctx = semantics.Context(btor.Model(self.base / "destination.btor"), "test")
        with self.assertRaises(semantics.SemanticError):
            ctx.lower({"op": "var", "name": "invented"})

    def test_shared_uint_rewrites_against_concrete_bitvector_values(self):
        # Exhaustive small words check semantic boundaries independently of
        # the implementation's formula shape, including carry and underflow.
        for left in range(16):
            for right in range(16):
                x, y = z3.BitVecVal(left, 4), z3.BitVecVal(right, 4)
                for term, expected in [(x | y, left | right), (x + y, (left + right) % 16),
                                       (x - y, (left - right) % 16),
                                       (z3.Extract(2, 1, x), (left >> 1) & 3)]:
                    self.assertEqual(z3.simplify(semantics.unsigned_value(term)).as_long(), expected)

    def test_uint_comparison_keeps_different_widths_unsigned(self):
        ctx = semantics.Context(btor.Model(self.base / "destination.btor"), "test")
        minus_one = {"op": "bv", "width": 4, "value": "-1"}
        plus_one = {"op": "bv", "width": 8, "value": "1"}
        term = ctx.lower(O("gt", O("uint", minus_one), O("uint", plus_one)))
        self.assertTrue(z3.is_true(z3.simplify(term.value)))

    def test_manual_planner_discharges_a_model_bound_smt_proof(self):
        self.local_proof()
        package = self.base / "case"
        (package / "input/rtl").mkdir(parents=True)
        (package / "input/models").mkdir()
        (package / "build").mkdir()
        rtl = "module m; reg flag = 0; always @* begin safe_flag: assert(!flag); end endmodule\n"
        (package / "input/rtl/check.sv").write_text(rtl)
        (package / "input/models/model.btor").write_text(fixture_module.DESTINATION)
        (package / "build/build.py").write_text(
            "from pathlib import Path\n"
            "root=Path(__file__).resolve().parents[1]\n"
            "(root/'models').mkdir(exist_ok=True)\n"
            "(root/'models/model.btor').write_bytes((root/'input/models/model.btor').read_bytes())\n")
        self.case["inputs"]["files"] = [{"path": "input/rtl/check.sv", "role": "checker",
            "sha256": hashlib.sha256(rtl.encode()).hexdigest()}]
        self.case["build"]["recipe"] = {"command": ["python3", "build/build.py"]}
        self.case["build"]["outputs"][0]["path"] = "models/model.btor"
        (package / "case.json").write_text(json.dumps(self.case))
        proposals = {"schema_version": "pcd-proposal/0.1", "case": self.case["case"],
            "planner": {"name": "manual", "version": "test"}, "nodes": [], "targets": []}
        for node in self.proof["nodes"]:
            proposal = {k:copy.deepcopy(node[k]) for k in ["id", "role", "kind", "phase", "requires", "provides"]}
            proposal["statement"] = "Check the actual frozen model property"
            proposal["certificate_hint"] = copy.deepcopy(node["certificate"])
            proposal["certificate_hint"].pop("verdict")
            proposals["nodes"].append(proposal)
        target = copy.deepcopy(self.proof["targets"][0])
        proposals["targets"] = [{k:target[k] for k in ["id", "goal", "requires", "tcb"]}]
        proposals["targets"][0]["composition_hint"] = target["composition"]
        proposal_path = self.base / "proposal.json"
        proposal_path.write_text(json.dumps(proposals))
        run, directory = run_e2e(str(package), planner="manual", manual_path=str(proposal_path),
                                 runs_dir=str(self.base / "runs"))
        self.assertEqual(run["result"], "accepted", run)
        self.assertFalse(run["engine_included"])
        report = json.loads((directory / "report.json").read_text())
        self.assertFalse(report["engine_included"])
        self.assertGreater(report["timing"]["wall_seconds"], 0)
        self.assertEqual(report["composition_guard"]["status"], "checked")


class Smt2SerializationTest(unittest.TestCase):
    def test_deeply_nested_terms_do_not_recurse(self):
        term = "x"
        for _ in range(5000):
            term = ["not", term]
        text = model_smt._smt2_serialize(term)
        self.assertEqual(text.count("(not "), 5000)
        self.assertTrue(text.endswith("x" + ")" * 5000))


class SolverBridgeExamplesTest(unittest.TestCase):
    def test_z3_lemmas_are_imported_into_a_real_ric3_proof(self):
        package = ROOT / "examples/solver_bridge_mul"
        result = kernel.check_paths(str(package / "case.json"), str(package / "proof.json"))
        self.assertTrue(result.accepted, result.as_dict())
        edges = result.composition["checked_edges"]
        self.assertEqual(len(edges["close_imports"]["discharged_constraints"]), 2)
        self.assertEqual(set(edges["capture"]["checks"]), {"base", "step"})
        self.assertEqual(result.targets["root"]["evidence"], "REPLAY")

    def test_wrong_imported_constraint_witness_fails_semantic_check(self):
        package = ROOT / "examples/solver_bridge_mul"
        case = json.loads((package / "case.json").read_text())
        proof = json.loads((package / "proof.json").read_text())
        edge = next(n for n in proof["nodes"] if n["id"] == "close_imports")
        witnesses = edge["certificate"]["payload"]["discharge"]
        for key in witnesses:
            witnesses[key] = {"node": "retirement", "guarantee": "L"}
        edge["requires"] = [{"node": "engine", "guarantee": "P"}, {"node": "retirement", "guarantee": "L"}]
        result = kernel.evaluate(case, proof, str(package))
        self.assertFalse(result.accepted)
        self.assertTrue(any("constraint discharge: sat" in issue.message for issue in result.errors), result.as_dict())

    def test_real_remu_quotient_is_lifted_with_the_actual_sampling(self):
        package = ROOT / "examples/remu_operator_bridge"
        result = kernel.check_paths(str(package / "case.json"), str(package / "proof.json"))
        self.assertTrue(result.accepted, result.as_dict())
        edges = result.composition["checked_edges"]
        self.assertEqual(edges["q_integer"]["kind"], model_smt.FORMAT)
        self.assertEqual(edges["q_step"]["method"], "step")
        self.assertEqual(edges["q_step"]["checks"]["step"]["result"], "unsat")
        required = json.loads((package / "case.json").read_text())["targets"][0]["required_properties"]
        self.assertEqual(required, ["o_remu_or_add"])

    def test_real_remu_missing_reset_guard_is_not_a_valid_induction(self):
        package = ROOT / "examples/remu_operator_bridge"
        case = json.loads((package / "case.json").read_text())
        proof = json.loads((package / "proof.json").read_text())
        node = next(n for n in proof["nodes"] if n["id"] == "q_lower_clear")
        expression = node["provides"][0]["binding"]["expression"]
        expression["args"][0] = expression["args"][0]["args"][1]
        result = kernel.evaluate(case, proof, str(package))
        self.assertFalse(result.accepted)
        self.assertTrue(any("model induction base: sat" in issue.message for issue in result.errors), result.as_dict())

    def test_real_remu_current_quotient_cannot_replace_next_quotient(self):
        package = ROOT / "examples/remu_operator_bridge"
        case = json.loads((package / "case.json").read_text())
        proof = json.loads((package / "proof.json").read_text())
        node = next(n for n in proof["nodes"] if n["id"] == "q_step")
        expression = node["provides"][0]["binding"]["expression"]
        expression["args"][1]["args"][0]["args"][0].pop("frame")
        result = kernel.evaluate(case, proof, str(package))
        self.assertFalse(result.accepted)
        self.assertTrue(any("model step: sat" in issue.message for issue in result.errors), result.as_dict())


if __name__ == "__main__":
    unittest.main()
