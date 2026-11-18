#!/usr/bin/env python3
"""Regenerate a model-bound ADD composition example from bundled frozen evidence.

The source is a recorded successful ADD run. This is a checking demonstration,
not a fresh engine result or a blind planner experiment.
"""
from __future__ import annotations

import copy
import hashlib
import json
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PCD = HERE.parents[1]
sys.path[:0] = [str(PCD), str(PCD.parent)]
from checkers import composition, expr  # noqa: E402


def read(path: Path):
    return json.loads(path.read_text())


def write(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def artifact(path: Path) -> dict:
    return {"path": path.relative_to(HERE).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> None:
    runpy.run_path(str(HERE / "build/build.py"), run_name="__main__")
    seed = read(HERE / "evidence/source/proof.original.json")
    case = read(HERE / "evidence/source/case.original.json")
    source_art = artifact(HERE / "input/models/source.btor")
    destination_art = artifact(HERE / "models/observed.btor")
    source_id = "btor:" + source_art["sha256"]
    destination_id = "btor:" + destination_art["sha256"]
    if source_id != seed["primary_model"]:
        raise ValueError("bundled source model differs from the recorded engine proof")
    proof = {
        "schema_version": "pcd-proof/0.1", "case": "composition_add", "acceptance": "complete",
        "models": {"source": source_id, "primary": destination_id}, "primary_model": destination_id,
        "model_artifacts": {source_id: source_art, destination_id: destination_art},
        "nodes": [], "targets": [],
        "metadata": {"completeness": "complete", "run_mode": "dev", "planner": "frozen-example",
            "notes": "Existing ADD engine evidence; checked observer projection, no fresh engine run."},
    }
    leaves = [n for n in seed["nodes"] if n["certificate"]["evidence"] == "REPLAY"]
    for i, old in enumerate(leaves):
        node = copy.deepcopy(old)
        name = node["certificate"]["assertion"]["name"]
        if node["requires"]:
            raise ValueError("example source unexpectedly has conditional proof nodes")
        node["id"] = f"source.{name}"
        node["provides"] = [{"name": "S", "expr": f"src_{i}", "sort": "Bool",
            "binding": {"kind": "btor-bad", "property": name}}]
        node["certificate"]["goal"] = "S"
        node["certificate"]["run"]["log"] = "evidence/source/engine.log"
        node["certificate"]["run"]["log_sha256"] = artifact(HERE / "evidence/source/engine.log")["sha256"]
        node["certificate"]["assertion"]["file"] = node["certificate"]["assertion"]["file"].removeprefix("case/")
        transfer_id = f"transfer.{name}"
        node["reuse"] = {"source_model": source_id, "transfer_node": transfer_id,
            "assumption_match": ["model", "width", "guards", "phase", "transition"]}
        proof["nodes"].append(node)
        req = {"node": node["id"], "guarantee": "S"}
        proof["nodes"].append({
            "schema_version": "pcd-obligation/0.1", "id": transfer_id, "role": "transfer",
            "kind": "equivalence", "phase": "any", "model": destination_id,
            "statement": f"The recorded ADD property {name} holds on the observer extension",
            "requires": [req],
            "provides": [{"name": "D", "expr": f"dst_{i}", "sort": "Bool",
                "binding": {"kind": "btor-bad", "property": name}}],
            "certificate": {"evidence": "CHECKED", "format": composition.FORMAT,
                "checker": composition.CHECKER, "goal": "D", "verdict": "proved", "payload": {}},
        })
    store = composition.ModelStore(proof, str(HERE))
    payload = None
    for node in proof["nodes"]:
        if node["role"] != "transfer":
            continue
        ref = node["requires"][0]
        if payload is None:
            payload = composition.proposal(source_id, destination_id, ref["node"], ref["guarantee"], store)
        node["certificate"]["payload"] = {**payload, "source": ref}
    transfers = [n for n in proof["nodes"] if n["role"] == "transfer"]
    required = ["o_pc_wdata_match", "o_rd_wdata_match"]
    symbols = [n["provides"][0]["expr"] for n in transfers if n["provides"][0]["binding"]["property"] in required]
    goal = "(and " + " ".join(symbols) + ")"
    reqs = [{"node": n["id"], "guarantee": "D"} for n in transfers]
    prems = [n["provides"][0]["expr"] for n in transfers]
    script = expr.canonical_script(prems, goal)
    statement = "ADD PC and destination data satisfy the original checker on the observer extension"
    proof["nodes"].append({
        "schema_version": "pcd-obligation/0.1", "id": "root", "role": "compose", "kind": "linear",
        "phase": "any", "model": destination_id, "statement": statement, "requires": reqs,
        "provides": [{"name": "GOAL", "expr": goal, "sort": "Bool"}],
        "certificate": {"evidence": "CHECKED", "format": "smt-implication", "checker": "z3",
            "goal": "GOAL", "verdict": "proved", "payload": {"smt2": script}},
    })
    proof["targets"] = [{"id": "root", "statement": statement, "model": destination_id,
        "goal": "GOAL", "requires": reqs, "tcb": [], "composition": {"mode": "CHECKED", "checker": "z3-implication",
            "payload": {"premises": reqs, "goal": "GOAL", "smt2": script}}}]
    case["case"] = "composition_add"
    case["acceptance"] = "complete"
    case["description"] = "Frozen ADD proof with checked structural observer projection"
    case["build"] = {"kind": "btor", "recipe": {"command": ["python3", "build/build.py"]},
        "outputs": [{"kind": "btor", "path": "models/observed.btor"}],
        "expected_model": {"kind": "btor", "sha256": destination_art["sha256"]}}
    case["run_policy"] = {"mode": "dev", "oracle_paths": [], "planner": "manual", "pre_registered": False}
    case["targets"] = [{"id": "root", "statement": statement, "claim_level": "root",
        "model_ref": "primary", "required_properties": required}]
    write(HERE / "case.json", case)
    write(HERE / "proof.json", proof)
    print(f"prepared {len(transfers)} checked ADD property projections")


if __name__ == "__main__":
    main()
