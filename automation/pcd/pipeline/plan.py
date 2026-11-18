"""Planner seam: manual, template, or external LLM proposals.

A proposal is frozen before discharge and never contains a status/verdict/level.
The runner adds execution provenance only when it assembles the proof.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import jsonschema

from checkers import expr as expr_mod

from .core import (
    PcdError,
    freeze_json,
    load_frozen_json,
    read_json,
    run_command,
    find_forbidden_status,
)
from .sketch import load_context

PROPOSAL_SCHEMA = Path(__file__).resolve().parents[1] / "schema" / "proposal.schema.json"


def _sanitize(name: str, fallback: str) -> str:
    out = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_.-")
    return out or fallback


def validate_proposal(doc: dict[str, Any]) -> None:
    schema = read_json(PROPOSAL_SCHEMA)
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(doc),
        key=lambda e: (tuple(str(p) for p in e.absolute_path), e.message),
    )
    if errors:
        details = []
        for e in errors:
            where = "/".join(str(p) for p in e.absolute_path) or "<root>"
            details.append(f"{where}: {e.message}")
        raise PcdError("proposal schema validation failed: " + "; ".join(details))
    bad = find_forbidden_status(doc)
    if bad:
        raise PcdError("proposal contains forbidden verdict/status fields: " + ", ".join(bad))


def _timeout_for(case: dict[str, Any], engine: str) -> int:
    return int(case["budgets"].get("engine_seconds", {}).get(engine, case["budgets"]["total_seconds"]))


def template_proposals(context: dict[str, Any], context_sha256: str) -> dict[str, Any]:
    case = context["case"]
    props = context["model"].get("properties", [])
    if not props:
        raise PcdError("template planner: model sketch has no bad properties")
    timeout_s = _timeout_for(case, "ric3")
    backend = str(case.get("run_policy", {}).get("template_backend", "portfolio"))
    if backend not in {"portfolio", "ic3", "kind", "bmc", "cill"}:
        raise PcdError(f"template planner: unsupported backend {backend!r}")

    nodes: list[dict[str, Any]] = []
    leaves: list[dict[str, Any]] = []
    for i, prop in enumerate(props):
        base = _sanitize(str(prop.get("name", "")), f"property_{i}")
        nid = f"property.{base}"
        suffix = 1
        while any(n["id"] == nid for n in nodes):
            suffix += 1
            nid = f"property.{base}_{suffix}"
        gname = f"G{i}"
        symbol = f"p_{i}"
        assertion_file = prop.get("assertion_file")
        hint: dict[str, Any] = {
            "evidence": "REPLAY",
            "format": "replay",
            "goal": gname,
            "engine": "ric3",
            "backend": backend,
            "timeout_s": timeout_s,
            "property_index": prop["index"],
            "assertion_name": str(prop.get("name", "")) or None,
            "note": (
                "cill checks all properties in one trusted inductiveness run"
                if backend == "cill"
                else f"{backend} reports a clean UNKNOWN on budget exhaustion"
            ),
        }
        if assertion_file:
            hint["assertion_file"] = assertion_file
        if not hint.get("assertion_name"):
            hint.pop("assertion_name", None)
        node = {
            "id": nid,
            "role": "observe",
            "kind": "replay",
            "phase": "any",
            "statement": f"engine checks bad property {prop.get('name', prop['index'])}",
            "requires": [],
            "provides": [
                {
                    "name": gname,
                    "expr": symbol,
                    "sort": "Bool",
                }
            ],
            "certificate_hint": hint,
        }
        if any(t.get("required_properties") for t in case["targets"]):
            node["provides"][0]["binding"] = {"kind": "btor-bad", "property": str(prop.get("name", ""))}
        nodes.append(node)
        leaves.append(
            {
                "node": nid,
                "guarantee": gname,
                "symbol": symbol,
                "prop": prop,
            }
        )

    targets = case["targets"]
    if len(targets) == 1:
        groups = [leaves]
    elif len(targets) == len(leaves):
        groups = [[leaf] for leaf in leaves]
    else:
        groups = [leaves for _ in targets]

    target_props: list[dict[str, Any]] = []
    for target, group in zip(targets, groups):
        reqs = [{"node": x["node"], "guarantee": x["guarantee"]} for x in group]
        goal_name = "GOAL"
        symbols = [x["symbol"] for x in group]
        goal_expr = symbols[0] if len(symbols) == 1 else "(and " + " ".join(symbols) + ")"
        # This is the only accepted encoding: the kernel regenerates it from
        # the guarantee formulas and rejects an arbitrary planner script.
        smt = expr_mod.canonical_script(symbols, goal_expr)
        composition_hint: dict[str, Any] = {
            "mode": "CHECKED",
            "checker": "z3-implication",
            "payload": {
                "premises": reqs,
                "goal": goal_name,
                "smt2": smt,
                "timeout_ms": 30000,
            },
            "notes": (
                "conjunction of independently discharged properties"
                if len(group) >= 2
                else "single-property implication; checked rather than structurally capped"
            ),
        }
        target_props.append(
            {
                "id": target["id"],
                "goal": goal_name,
                "requires": reqs,
                "tcb": [],
                "composition_hint": composition_hint,
            }
        )
        nodes.append(
            {
                "id": target["id"],
                "role": "compose",
                "kind": "linear",
                "phase": "any",
                "statement": target["statement"],
                "requires": reqs,
                "provides": [
                    {
                        "name": goal_name,
                        "expr": goal_expr,
                        "sort": "Bool",
                    }
                ],
                "certificate_hint": {
                    "evidence": "CHECKED",
                    "format": "smt-implication",
                    "checker": "z3-implication",
                    "goal": goal_name,
                    "payload": {
                        "premises": reqs,
                        "goal": goal_name,
                        "smt2": smt,
                    },
                },
            }
        )

    proposal = {
        "schema_version": "pcd-proposal/0.1",
        "case": case["id"],
        "planner": {
            "name": "template",
            "version": "0.1",
            "context_sha256": context_sha256,
        },
        "nodes": nodes,
        "targets": target_props,
        "metadata": {
            "rationale": "one engine obligation per model property, composed by conjunction",
        },
    }
    validate_proposal(proposal)
    return proposal


def _load_manual(path: Path, context: dict[str, Any], context_sha256: str) -> dict[str, Any]:
    doc = read_json(path)
    if doc.get("case") != context["case"]["id"]:
        raise PcdError(f"{path}: proposal case {doc.get('case')!r} does not match {context['case']['id']!r}")
    planner = doc.setdefault("planner", {})
    if not isinstance(planner, dict):
        raise PcdError(f"{path}: planner must be an object")
    planner.setdefault("name", "manual")
    planner.setdefault("version", "manual")
    if planner.get("context_sha256") and planner["context_sha256"] != context_sha256:
        raise PcdError(f"{path}: planner.context_sha256 does not match the frozen context")
    planner["context_sha256"] = context_sha256
    validate_proposal(doc)
    return doc


def _load_llm(command: str | None, run_dir: Path, context: dict[str, Any], context_sha256: str) -> dict[str, Any]:
    if not command:
        raise PcdError("llm planner requires --llm-command or PCD_LLM_COMMAND")
    context_path = run_dir / "context.json"
    cmd = command if isinstance(command, list) else ["sh", "-c", command]
    # Keep the context path as an explicit argument so an external planner does
    # not need to infer the run directory.
    if "{context}" in " ".join(cmd):
        cmd = [x.replace("{context}", str(context_path)) for x in cmd]
    else:
        cmd = cmd + [str(context_path)]
    log_path = run_dir / "logs" / "plan.log"
    result = run_command(
        cmd,
        cwd=run_dir,
        log_path=log_path,
        timeout_s=int(context["case"]["budgets"]["total_seconds"]),
        sandbox=context["case"]["run_policy"]["mode"] == "blind",
        sandbox_root=run_dir,
        sandbox_network=True,
    )
    if result["returncode"] != 0 or result["timed_out"]:
        raise PcdError(f"llm planner failed with exit {result['returncode']} (see {log_path})")
    # run_command redirects stdout into the log; strip the header introduced by
    # the runner and parse the remaining JSON.
    raw = log_path.read_text(encoding="utf-8", errors="replace")
    marker = "# ---\n"
    body = raw.split(marker, 1)[1] if marker in raw else raw
    try:
        doc = json.loads(body)
    except Exception as exc:  # noqa: BLE001
        raise PcdError(f"llm planner output is not JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise PcdError("llm planner output must be a JSON object")
    if doc.get("case") != context["case"]["id"]:
        raise PcdError("llm planner output case does not match the frozen case")
    planner = doc.setdefault("planner", {})
    if not isinstance(planner, dict):
        raise PcdError("llm planner output planner field must be an object")
    planner.setdefault("name", "llm")
    planner.setdefault("version", "external")
    if planner.get("context_sha256") and planner["context_sha256"] != context_sha256:
        raise PcdError("llm planner context_sha256 does not match the frozen context")
    planner["context_sha256"] = context_sha256
    validate_proposal(doc)
    return doc


def run_plan(
    run_dir: Path,
    case: dict[str, Any],
    *,
    planner: str,
    manual_path: str | None = None,
    llm_command: str | None = None,
    decomposition_path: str | None = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    context, context_sha256 = load_context(run_dir)
    if context["case"]["id"] != case["case"]:
        raise PcdError("context case does not match the case package")
    if planner == "template":
        doc = template_proposals(context, context_sha256)
    elif planner == "decompose":
        if not decomposition_path:
            raise PcdError("decompose planner requires --decomposition FILE")
        from .decompose import decomposition_proposals

        spec = read_json(Path(decomposition_path))
        doc = decomposition_proposals(context, context_sha256, spec)
    elif planner == "manual":
        if not manual_path:
            raise PcdError("manual planner requires --proposals FILE")
        doc = _load_manual(Path(manual_path), context, context_sha256)
    elif planner == "llm":
        doc = _load_llm(llm_command or os.environ.get("PCD_LLM_COMMAND"), run_dir, context, context_sha256)
    else:
        raise PcdError(f"unknown planner: {planner}")
    doc["planner"]["context_sha256"] = context_sha256
    validate_proposal(doc)
    freeze_json(run_dir / "proposals.json", doc)
    return doc


def load_proposals(run_dir: Path) -> tuple[dict[str, Any], str]:
    return load_frozen_json(Path(run_dir) / "proposals.json")
