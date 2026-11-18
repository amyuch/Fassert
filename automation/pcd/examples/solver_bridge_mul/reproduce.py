#!/usr/bin/env python3
"""Reproduce a checked Z3-to-rIC3 lemma import over a 32-bit MUL pipeline."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PCD = HERE.parents[1]
sys.path[:0] = [str(PCD), str(PCD.parent)]
from checkers import btor, composition, emit_btor, expr, model_smt, semantics  # noqa: E402
from kernel import kernel  # noqa: E402
from pipeline.core import parse_verdict, run_command, tool_versions  # noqa: E402


def write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def artifact(path: Path):
    return {"path": path.relative_to(HERE).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--run-engine", action="store_true")
    args = parser.parse_args()
    if args.rebuild:
        built = run_command(["sh", "build/build.sh"], cwd=HERE, log_path=HERE / "evidence/build.log", timeout_s=30)
        if built["returncode"] or built["timed_out"]:
            raise RuntimeError("Yosys build failed")
    original = HERE / "models/original.btor"
    text = original.read_text()
    model = btor.Model(original)
    original_art = artifact(original)
    original_id = "btor:" + original_art["sha256"]
    R, O = semantics.ref, semantics.operation
    capture = O("implies", O("truth", R(model.find("captured"))),
                O("eq", O("extract", R(model.find("product")), hi=31, lo=0),
                  O("bvmul", R(model.find("captured_a")), R(model.find("captured_b")))))
    retirement = O("implies", O("truth", R(model.find("retired"))),
                   O("eq", R(model.find("result")), O("bvmul", R(model.find("retired_a")), R(model.find("retired_b")))))
    proof = {"schema_version": "pcd-proof/0.1", "case": "solver_bridge_mul", "acceptance": "complete",
             "models": {"primary": original_id}, "primary_model": original_id,
             "model_artifacts": {original_id: original_art}, "nodes": [], "targets": [],
             "metadata": {"completeness": "complete", "run_mode": "dev", "planner": "example",
                          "notes": "Typed Z3 lemmas, independently checked imported constraints, and rIC3 target proof."}}
    for name, predicate, requirements in [("capture", capture, []),
                                         ("retirement", retirement, [{"node": "capture", "guarantee": "L"}])]:
        proof["nodes"].append({"schema_version": "pcd-obligation/0.1", "id": name,
            "role": "invariant", "kind": "inductive", "phase": "any", "model": original_id,
            "requires": requirements,
            "provides": [{"name": "L", "expr": name + "_fact", "sort": "Bool",
                "binding": {"kind": "btor-expression", "expression": predicate}}],
            "certificate": {"evidence": "CHECKED", "format": model_smt.FORMAT, "checker": model_smt.CHECKER,
                "goal": "L", "verdict": "proved", "payload": {"method": "induction", "timeout_ms": 5000}}})
    nodes = {n["id"]: n for n in proof["nodes"]}
    store = composition.ModelStore(proof, str(HERE))
    construction_checks = {name: model_smt.check(node, nodes, store) for name, node in nodes.items()}
    write(HERE / "evidence/construction-checks.json", construction_checks)
    # The emitter is an untrusted construction step. Projection checking later
    # proves every emitted constraint follows from its original-model lemma.
    restricted, capture_constraint = emit_btor.append_constraint(text, capture, name="import_capture")
    restricted, retirement_constraint = emit_btor.append_constraint(restricted, retirement, name="import_retirement")
    restricted_path = HERE / "models/ric3.btor"
    restricted_path.write_text(restricted)
    restricted_art = artifact(restricted_path)
    restricted_id = "btor:" + restricted_art["sha256"]
    command = ["ric3", "check", "models/ric3.btor", "kind", "--prop", "0", "--time-limit", "15"]
    if args.run_engine:
        result = run_command(command, cwd=HERE, log_path=HERE / "evidence/engine.log", timeout_s=20)
        result["model"] = restricted_id
        result["version"] = tool_versions()["ric3"]
        write(HERE / "evidence/execution.json", result)
    execution = json.loads((HERE / "evidence/execution.json").read_text())
    log = HERE / "evidence/engine.log"
    if (execution["model"] != restricted_id or execution["returncode"] or execution["timed_out"]
            or execution["log_sha256"] != artifact(log)["sha256"]
            or parse_verdict(log.read_text(), backend="kind") != "proved"):
        raise RuntimeError("no matching successful frozen rIC3 execution; use --run-engine")
    proof["models"]["ric3"] = restricted_id
    proof["model_artifacts"][restricted_id] = restricted_art
    engine = {"schema_version": "pcd-obligation/0.1", "id": "engine", "role": "observe", "kind": "replay",
              "phase": "any", "model": restricted_id, "requires": [],
              "provides": [{"name": "P", "expr": "ric3_result", "sort": "Bool",
                            "binding": {"kind": "btor-bad", "property": "o_result"}}],
              "certificate": {"evidence": "REPLAY", "format": "replay", "verdict": "proved", "goal": "P",
                  "assertion": {"name": "o_result", "file": "input/rtl/mul.sv"},
                  "run": {"id": "ric3-import", "command": command, "tool": "ric3", "version": execution["version"],
                          "model_sha256": restricted_id, "log": "evidence/engine.log", "log_sha256": artifact(log)["sha256"]}},
              "reuse": {"source_model": restricted_id, "transfer_node": "close_imports",
                        "assumption_match": ["model", "width", "guards", "phase", "transition"]}}
    source = {"node": "engine", "guarantee": "P"}
    capture_ref, retirement_ref = {"node": "capture", "guarantee": "L"}, {"node": "retirement", "guarantee": "L"}
    mapping = {str(n): str(n) for n in model.states + model.inputs}
    proof["nodes"].extend([engine, {"schema_version": "pcd-obligation/0.1", "id": "close_imports",
        "role": "transfer", "kind": "equivalence", "phase": "any", "model": original_id,
        "requires": [source, capture_ref, retirement_ref],
        "provides": [{"name": "P", "expr": "original_result", "sort": "Bool",
                      "binding": {"kind": "btor-bad", "property": "o_result"}}],
        "certificate": {"evidence": "CHECKED", "format": composition.FORMAT, "checker": composition.CHECKER,
            "goal": "P", "verdict": "proved", "payload": {"source": source,
                "state_map": {k:v for k,v in mapping.items() if model.nodes[int(k)].op == "state"},
                "input_map": {k:v for k,v in mapping.items() if model.nodes[int(k)].op == "input"},
                "discharge": {str(capture_constraint): capture_ref, str(retirement_constraint): retirement_ref}}}}])
    requirements = [{"node": "close_imports", "guarantee": "P"}]
    script = expr.canonical_script(["original_result"], "original_result")
    statement = "The original 32-bit MUL pipeline retires the low product of the captured operands"
    proof["nodes"].append({"schema_version": "pcd-obligation/0.1", "id": "root", "role": "compose",
        "kind": "linear", "phase": "any", "model": original_id, "requires": requirements,
        "provides": [{"name": "GOAL", "expr": "original_result", "sort": "Bool"}],
        "certificate": {"evidence": "CHECKED", "format": "smt-implication", "checker": "z3",
                        "goal": "GOAL", "verdict": "proved", "payload": {"smt2": script}}})
    proof["targets"] = [{"id": "root", "statement": statement, "model": original_id, "goal": "GOAL",
        "requires": requirements, "tcb": [], "composition": {"mode": "CHECKED", "checker": "z3-implication",
            "payload": {"premises": requirements, "goal": "GOAL", "smt2": script}}}]
    case = {"schema_version": "pcd-case/0.1", "case": "solver_bridge_mul", "acceptance": "complete",
            "claim_scope": "safety", "description": "Checked Z3-to-rIC3 import on a real multiplier pipeline",
            "inputs": {"files": [{**artifact(HERE / "input/rtl/mul.sv"), "role": "rtl"}],
                       "environment": {"top": "bridge_mul", "reset": "reset", "clock": "clock", "frontend": "yosys"}},
            "build": {"kind": "btor", "recipe": {"command": ["sh", "build/build.sh"]},
                      "outputs": [{"path": "models/original.btor", "kind": "btor"}],
                      "expected_model": {"kind": "btor", "sha256": original_art["sha256"]}},
            "targets": [{"id": "root", "statement": statement, "claim_level": "root", "model_ref": "primary",
                         "required_properties": ["o_result"]}],
            "budgets": {"total_seconds": 60, "max_iterations": 1},
            "run_policy": {"mode": "dev", "planner": "manual", "oracle_paths": [], "pre_registered": False}}
    write(HERE / "case.json", case)
    write(HERE / "proof.json", proof)
    checked = kernel.check_paths(str(HERE / "case.json"), str(HERE / "proof.json"))
    write(HERE / "check.json", checked.as_dict())
    if not checked.accepted:
        raise RuntimeError(json.dumps(checked.as_dict(), indent=2))
    print("ACCEPT: actual-model Z3 induction, checked imported constraints, and rIC3 target proof")


if __name__ == "__main__":
    main()
