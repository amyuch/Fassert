#!/usr/bin/env python3
"""Check an actual REMU bit-vector-to-integer quotient-update bridge.

This proves a local operator/transition contract, not the architectural REMU RD
claim. Existing CIll evidence is replay-bound; the new semantic checks rerun Z3.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PCD = HERE.parents[1]
sys.path[:0] = [str(PCD), str(PCD.parent)]
from checkers import btor, composition, emit_btor, expr, model_smt, semantics  # noqa: E402
from kernel import kernel  # noqa: E402


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def artifact(path):
    return {"path": path.relative_to(HERE).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    original = HERE / "input/models/source.btor"
    model = btor.Model(original)
    R, O = semantics.ref, semantics.operation
    q = R(model.find("wrapper.uut.pcd_div.pcpi_div.quotient"))
    mask = R(model.find("wrapper.uut.pcd_div.pcpi_div.quotient_msk"))
    dividend = R(model.find("wrapper.uut.pcd_div.pcpi_div.dividend"))
    divisor = R(model.find("wrapper.uut.pcd_div.pcpi_div.divisor"))
    phase = O("and", O("not", O("truth", R(model.find("reset")))), O("truth", R(model.find("h_remu_loop"))))
    zero, one = {"op": "bv", "width": 32, "value": "0"}, {"op": "bv", "width": 32, "value": "1"}
    low_mask = O("bvsub", O("bvshl", mask, one), one)
    lower_clear = O("implies", phase, O("eq", O("bvand", q, low_mask), zero))
    disjoint = O("implies", phase, O("eq", O("bvand", q, mask), zero))
    integer = O("implies", phase, O("eq", O("uint", O("bvor", q, mask)), O("add", O("uint", q), O("uint", mask))))
    step_guard = O("and", phase, O("not", O("truth", R(model.find("wrapper.uut.pcd_div.pcpi_div.start")))),
                   O("not", O("truth", R(model.find("reset"), 1))))
    step = O("implies", step_guard, O("eq", O("uint", R(model.find("wrapper.uut.pcd_div.pcpi_div.quotient"), 1)),
             O("ite", O("le", O("uint", divisor), O("uint", dividend)),
               O("add", O("uint", q), O("uint", mask)), O("uint", q))))
    target_predicate = O("implies", phase, O("eq", O("bvor", q, mask), O("bvadd", q, mask)))
    text, _ = emit_btor.append_property(original.read_text(), target_predicate, name="o_remu_or_add")
    primary_path = HERE / "models/observed.btor"
    primary_path.parent.mkdir(parents=True, exist_ok=True)
    primary_path.write_text(text)
    src_art, primary_art = artifact(original), artifact(primary_path)
    sid, pid = "btor:" + src_art["sha256"], "btor:" + primary_art["sha256"]
    seed = read(HERE / "evidence/source/proof.original.json")
    if sid != seed["primary_model"]:
        raise ValueError("source model does not match the recorded REMU engine proof")
    proof = {"schema_version": "pcd-proof/0.1", "case": "remu_operator_bridge", "acceptance": "complete",
             "models": {"source": sid, "primary": pid}, "primary_model": pid,
             "model_artifacts": {sid: src_art, pid: primary_art}, "nodes": [], "targets": [],
             "metadata": {"completeness": "complete", "run_mode": "dev", "planner": "frozen-example",
                          "notes": "REMU quotient operator/step bridge only; not architectural RD acceptance."}}
    helper_refs = []
    mapping = {str(n): str(n) for n in model.states + model.inputs}
    for i, old in enumerate(n for n in seed["nodes"] if n["certificate"]["evidence"] == "REPLAY"):
        node = copy.deepcopy(old)
        name = node["certificate"]["assertion"]["name"]
        node["id"] = "source." + name
        node["provides"] = [{"name": "S", "expr": f"src_{i}", "sort": "Bool",
                             "binding": {"kind": "btor-bad", "property": name}}]
        node["certificate"]["goal"] = "S"
        node["certificate"]["assertion"]["file"] = "input/rtl/" + Path(node["certificate"]["assertion"]["file"]).name
        node["certificate"]["run"]["log"] = "evidence/source/engine.log"
        node["certificate"]["run"]["log_sha256"] = artifact(HERE / "evidence/source/engine.log")["sha256"]
        tid = "transfer." + name
        node["reuse"] = {"source_model": sid, "transfer_node": tid,
                         "assumption_match": ["model", "width", "guards", "phase", "transition"]}
        ref = {"node": node["id"], "guarantee": "S"}
        proof["nodes"].extend([node, {"schema_version": "pcd-obligation/0.1", "id": tid,
            "role": "transfer", "kind": "equivalence", "phase": "any", "model": pid, "requires": [ref],
            "provides": [{"name": "D", "expr": f"dst_{i}", "sort": "Bool", "binding": {"kind": "btor-bad", "property": name}}],
            "certificate": {"evidence": "CHECKED", "format": composition.FORMAT, "checker": composition.CHECKER,
                "goal": "D", "verdict": "proved", "payload": {"source": ref,
                    "state_map": {k:v for k,v in mapping.items() if model.nodes[int(k)].op == "state"},
                    "input_map": {k:v for k,v in mapping.items() if model.nodes[int(k)].op == "input"}}}}])
        helper_refs.append({"node": tid, "guarantee": "D"})
    def lemma(name, predicate, method, requirements, binding=None):
        proof["nodes"].append({"schema_version": "pcd-obligation/0.1", "id": name,
            "role": "update" if method == "step" else "invariant", "kind": "inductive", "phase": "any",
            "model": pid, "requires": requirements,
            "provides": [{"name": "L", "expr": name + "_fact", "sort": "Bool",
                "binding": binding or {"kind": "btor-expression", "expression": predicate}}],
            "certificate": {"evidence": "CHECKED", "format": model_smt.FORMAT, "checker": model_smt.CHECKER,
                "goal": "L", "verdict": "proved", "payload": {"method": method, "timeout_ms": 5000}}})
        return {"node": name, "guarantee": "L"}
    low_ref = lemma("q_lower_clear", lower_clear, "induction", helper_refs)
    disjoint_ref = lemma("q_disjoint", disjoint, "combinational", helper_refs + [low_ref])
    integer_ref = lemma("q_integer", integer, "combinational", [disjoint_ref])
    step_ref = lemma("q_step", step, "step", helper_refs + [integer_ref])
    property_ref = lemma("operator_property", None, "combinational", [disjoint_ref, integer_ref],
                         {"kind": "btor-bad", "property": "o_remu_or_add"})
    requires = [property_ref, step_ref]
    goal = "(and operator_property_fact q_step_fact)"
    script = expr.canonical_script(["operator_property_fact", "q_step_fact"], goal)
    statement = "REMU active-loop quotient OR agrees with addition and the sampled integer quotient step"
    proof["nodes"].append({"schema_version": "pcd-obligation/0.1", "id": "root", "role": "compose",
        "kind": "linear", "phase": "any", "model": pid, "requires": requires,
        "provides": [{"name": "GOAL", "expr": goal, "sort": "Bool"}],
        "certificate": {"evidence": "CHECKED", "format": "smt-implication", "checker": "z3", "verdict": "proved",
                        "goal": "GOAL", "payload": {"smt2": script}}})
    proof["targets"] = [{"id": "root", "statement": statement, "model": pid, "goal": "GOAL", "requires": requires,
        "tcb": [], "composition": {"mode": "CHECKED", "checker": "z3-implication",
                                  "payload": {"premises": requires, "goal": "GOAL", "smt2": script}}}]
    inputs = [{**artifact(path), "role": "other"} for path in sorted((HERE / "input/rtl").iterdir()) if path.is_file()]
    case = {"schema_version": "pcd-case/0.1", "case": "remu_operator_bridge", "acceptance": "complete",
            "claim_scope": "safety", "description": "REMU operator bridge; not a full architectural instruction proof",
            "inputs": {"files": inputs, "environment": {"top": "testbench", "reset": "reset", "frontend": "yosys-slang"}},
            "build": {"kind": "btor", "recipe": {"command": ["python3", "prepare.py"]},
                "outputs": [{"kind": "btor", "path": "models/observed.btor"}],
                "expected_model": {"kind": "btor", "sha256": primary_art["sha256"]}},
            "targets": [{"id": "root", "statement": statement, "claim_level": "root", "model_ref": "primary",
                         "required_properties": ["o_remu_or_add"]}],
            "budgets": {"total_seconds": 60, "max_iterations": 1},
            "run_policy": {"mode": "dev", "planner": "manual", "oracle_paths": [], "pre_registered": False}}
    write(HERE / "case.json", case)
    write(HERE / "proof.json", proof)
    checked = kernel.check_paths(str(HERE / "case.json"), str(HERE / "proof.json"))
    write(HERE / "check.json", checked.as_dict())
    if not checked.accepted:
        raise RuntimeError(json.dumps(checked.as_dict(), indent=2))
    print("ACCEPT: actual REMU operator and sampled integer quotient-step bridge (not full RD)")


if __name__ == "__main__":
    main()
